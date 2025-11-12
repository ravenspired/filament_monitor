"""
Helper script to program a demo NTAG215 filament tag.
Configures a Sunlu PLA spool with pre-computed geometry metadata.
"""

import math
from machine import SPI, Pin

from pn532_spi import PN532
import tag_storage


FILAMENT_DIAMETER_MM = 1.75
FILAMENT_AREA_MM2 = math.pi * (FILAMENT_DIAMETER_MM / 2) ** 2


def compute_spool_length(min_diameter_mm, max_diameter_mm, width_mm):
    core_radius = min_diameter_mm / 2.0
    outer_radius = max_diameter_mm / 2.0
    volume_mm3 = math.pi * width_mm * (outer_radius ** 2 - core_radius ** 2)
    length_mm = volume_mm3 / FILAMENT_AREA_MM2
    return length_mm / 1000.0


def wait_for_tag(pn532):
    print("Place an NTAG215 tag on the reader to program...")
    uid = None
    while uid is None:
        uid = pn532.read_passive_target(timeout=500)
    return uid


def main():
    spi = SPI(
        1,
        baudrate=1_000_000,
        polarity=0,
        phase=0,
        sck=Pin(10),
        mosi=Pin(11),
        miso=Pin(12),
    )
    cs = Pin(13, Pin.OUT)
    pn532 = PN532(spi, cs, debug=False)
    pn532.SAM_configuration()

    uid = wait_for_tag(pn532)
    print("Programming tag UID:", [hex(x) for x in uid])

    min_d = 52.0
    max_d = 200.0
    width = 67.0
    grams_full = 950.0
    meters_full = round(compute_spool_length(min_d, max_d, width), 3)

    tag_payload = {
        "ver": 1,
        "brand": "Sunlu",
        "type": "PLA",
        "fil_d": FILAMENT_DIAMETER_MM,
        "min_d": min_d,
        "max_d": max_d,
        "width": width,
        "grams_full": grams_full,
        "grams_rem": grams_full,
        "meters_full": meters_full,
        "meters_rem": meters_full,
    }

    try:
        tag_storage.write_ndef_json(pn532, tag_payload)
        print("Tag written successfully.")
        print("Payload:", tag_payload)
    except Exception as err:
        print("Failed to write tag:", err)


if __name__ == "__main__":
    main()

