"""
Filament monitor for Raspberry Pi Pico using a TM1637 4-digit display
and a PN532 NFC reader to track filament usage stored on NTAG215 tags.

Pins follow the existing test scripts:
  - TM1637 CLK: GP1
  - TM1637 DIO: GP0
  - PN532 SPI1: SCK GP10, MOSI GP11, MISO GP12, CS GP13

The NFC tag stores a JSON document inside an NDEF Text record.
Expected JSON keys (all numeric values are floats in millimetres/grams/metres):
  ver, brand, type, fil_d, min_d, max_d, width,
  grams_full, grams_rem, meters_full, meters_rem

Every full rotation subtracts filament based on current radius and updates the tag.
The display continuously cycles: filament type -> grams remaining -> metres remaining.
"""

import math
import time
from machine import Pin, SPI
from tm1637 import TM1637Decimal

from pn532_spi import PN532
import tag_storage


# --- Hardware setup --------------------------------------------------------
DISPLAY_CLK = Pin(1)
DISPLAY_DIO = Pin(0)

SPI_BUS = SPI(
    1,
    baudrate=1_000_000,
    polarity=0,
    phase=0,
    sck=Pin(10),
    mosi=Pin(11),
    miso=Pin(12),
)
PN532_CS = Pin(13, Pin.OUT)


# --- Behaviour tuning ------------------------------------------------------
FILAMENT_DIAMETER_MM = 1.75
FILAMENT_AREA_MM2 = math.pi * (FILAMENT_DIAMETER_MM / 2) ** 2

TAG_ABSENCE_MS = 5000  # minimum gap without tag before counting a rotation
SCAN_TIMEOUT_MS = 100  # PN532 passive target timeout (ms)
LOOP_DELAY_MS = 50     # main loop pause
DISPLAY_INTERVAL_MS = 1000


# --- Utility functions -----------------------------------------------------
def length_from_radius(radius_mm, core_radius_mm, width_mm):
    """Return remaining filament length (m) for a given outer radius."""
    shell = max(radius_mm ** 2 - core_radius_mm ** 2, 0)
    if shell <= 0 or width_mm <= 0:
        return 0.0
    volume_mm3 = math.pi * width_mm * shell
    length_mm = volume_mm3 / FILAMENT_AREA_MM2
    return length_mm / 1000.0


def radius_from_length(length_m, core_radius_mm, width_mm, max_radius_mm):
    """Convert remaining length (m) into an equivalent outer radius (mm)."""
    if width_mm <= 0:
        return core_radius_mm
    length_mm = max(length_m, 0) * 1000.0
    shell = (length_mm * FILAMENT_AREA_MM2) / (math.pi * width_mm)
    radius_sq = core_radius_mm ** 2 + shell
    radius_mm = math.sqrt(max(radius_sq, core_radius_mm ** 2))
    if max_radius_mm is not None:
        radius_mm = min(radius_mm, max_radius_mm)
    return radius_mm


def meters_per_rotation(state):
    """Approximate filament consumed per rotation based on current radius."""
    core_radius = state["core_radius_mm"]
    max_radius = state["max_radius_mm"]
    width = state["width_mm"]
    remaining_length = state["data"]["meters_rem"]
    radius = radius_from_length(remaining_length, core_radius, width, max_radius)
    if radius <= 0:
        return 0.0
    circumference_mm = 2 * math.pi * radius
    return max(circumference_mm / 1000.0, 0.0)


def grams_per_meter_from_data(data):
    meters_full = data.get("meters_full", 0)
    grams_full = data.get("grams_full", 0)
    if meters_full > 0 and grams_full > 0:
        return grams_full / meters_full
    # Fallback density assumptions if metadata missing (PLA default).
    density = 1.24  # g/cm^3
    area_mm2 = FILAMENT_AREA_MM2
    area_cm2 = area_mm2 / 100.0  # convert mm^2 to cm^2
    grams_per_mm = density * area_cm2
    return grams_per_mm * 1000.0  # convert to grams per meter


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def normalise_tag_data(data):
    """Ensure required keys exist and derive secondary values."""
    required = ["min_d", "max_d", "width", "grams_rem", "meters_rem"]
    for key in required:
        if key not in data:
            raise ValueError("Tag missing '{}'".format(key))

    data.setdefault("ver", 1)
    data.setdefault("fil_d", FILAMENT_DIAMETER_MM)
    min_d = data["min_d"]
    max_d = data["max_d"]
    width = data["width"]

    core_radius = min_d / 2.0
    max_radius = max_d / 2.0

    meters_full = data.get("meters_full")
    if not meters_full or meters_full <= 0:
        meters_full = length_from_radius(max_radius, core_radius, width)
        data["meters_full"] = meters_full

    grams_full = data.get("grams_full")
    if not grams_full or grams_full <= 0:
        grams_full = data.get("grams_rem", 0)
        data["grams_full"] = grams_full

    data["grams_rem"] = clamp(data.get("grams_rem", grams_full), 0.0, grams_full)
    data["meters_rem"] = clamp(data.get("meters_rem", meters_full), 0.0, meters_full)

    g_per_m = grams_per_meter_from_data(data)

    return {
        "data": data,
        "core_radius_mm": core_radius,
        "max_radius_mm": max_radius,
        "width_mm": width,
        "g_per_m": g_per_m,
    }


def format_quantity(value, unit):
    value_int = clamp(int(round(value)), 0, 999)
    return "{:03d}.{}".format(value_int, unit)


# --- Display handling ------------------------------------------------------
class DisplayCycler:
    def __init__(self, tm1637_display):
        self._display = tm1637_display
        self._modes = ("type", "grams", "meters")
        self._index = 0
        self._next_tick = time.ticks_add(time.ticks_ms(), DISPLAY_INTERVAL_MS)
        self._current_uid = None
        self._last_payload = None
        self._display.show("----")

    def reset(self):
        self._current_uid = None
        self._last_payload = None
        self._index = 0
        self._next_tick = time.ticks_add(time.ticks_ms(), DISPLAY_INTERVAL_MS)
        self._display.show("----")

    def update(self, uid, state):
        if not uid or not state:
            if self._current_uid is not None:
                self.reset()
            return

        now = time.ticks_ms()
        if uid != self._current_uid:
            self._current_uid = uid
            self._index = 0
            self._next_tick = time.ticks_add(now, DISPLAY_INTERVAL_MS)

        if time.ticks_diff(now, self._next_tick) >= 0:
            self._index = (self._index + 1) % len(self._modes)
            self._next_tick = time.ticks_add(now, DISPLAY_INTERVAL_MS)

        mode = self._modes[self._index]
        payload = (mode, state["data"]["grams_rem"], state["data"]["meters_rem"])
        if payload == self._last_payload:
            return
        self._last_payload = payload

        if mode == "type":
            filament_type = state["data"].get("type", "----")
            text = (filament_type.upper() + "    ")[:4]
            self._display.show(text)

        elif mode == "grams":
            grams_text = format_quantity(state["data"]["grams_rem"], "G")
            self._display.show(grams_text)
        else:
            meters_text = format_quantity(state["data"]["meters_rem"], "L")
            self._display.show(meters_text)


# --- Main monitor ----------------------------------------------------------
def main():
    tm_display = TM1637Decimal(clk=DISPLAY_CLK, dio=DISPLAY_DIO, brightness=7)
    display_cycler = DisplayCycler(tm_display)

    pn532 = PN532(SPI_BUS, PN532_CS, debug=False)
    pn532.SAM_configuration()

    current_uid = None
    current_state = None
    last_detection_ms = 0
    seen_once = False

    print("Filament monitor ready. Waiting for tags...")

    while True:
        now = time.ticks_ms()
        uid = pn532.read_passive_target(timeout=SCAN_TIMEOUT_MS)
        uid_bytes = bytes(uid) if uid else None

        if uid_bytes:
            if current_uid != uid_bytes:
                try:
                    data = tag_storage.read_ndef_json(pn532)
                except Exception as err:
                    print("Failed to read tag:", err)
                    data = None

                if data is None:
                    print("Tag has no filament data.")
                    current_state = None
                    current_uid = None
                    seen_once = False
                else:
                    try:
                        current_state = normalise_tag_data(data)
                        current_uid = uid_bytes
                        seen_once = False
                        last_detection_ms = now
                        print("Loaded filament tag:", current_state["data"])
                    except Exception as err:
                        print("Tag parse error:", err)
                        current_state = None
                        current_uid = None
                        seen_once = False
            else:
                # Tag is still present
                last_detection_ms = now
                if not seen_once:
                    seen_once = True

        else:  # no tag currently seen
            if current_uid:
                # Check if it’s been gone long enough to count a rotation
                gap = time.ticks_diff(now, last_detection_ms)
                if current_state and seen_once and gap >= TAG_ABSENCE_MS:
                    consume_filament_rotation(pn532, current_state)
                elif gap >= TAG_ABSENCE_MS * 4:
                    # Fully reset state after prolonged absence
                    current_uid = None
                    current_state = None
                    seen_once = False


        display_cycler.update(current_uid, current_state)
        time.sleep_ms(LOOP_DELAY_MS)


def consume_filament_rotation(pn532, state):
    meters_step = meters_per_rotation(state)
    if meters_step <= 0:
        return

    grams_step = meters_step * state.get("g_per_m", grams_per_meter_from_data(state["data"]))
    data = state["data"]
    data["meters_rem"] = max(data["meters_rem"] - meters_step, 0.0)
    data["grams_rem"] = max(data["grams_rem"] - grams_step, 0.0)

    # Avoid negative values due to floating-point noise.
    data["meters_rem"] = round(max(data["meters_rem"], 0.0), 3)
    data["grams_rem"] = round(max(data["grams_rem"], 0.0), 3)

    try:
        tag_storage.write_ndef_json(pn532, data)
        print(
            "Rotation consumed: -{:.3f} m, -{:.3f} g -> remaining {:.3f} m / {:.3f} g".format(
                meters_step, grams_step, data["meters_rem"], data["grams_rem"]
            )
        )
    except Exception as err:
        print("Failed to update tag:", err)


if __name__ == "__main__":
    main()

