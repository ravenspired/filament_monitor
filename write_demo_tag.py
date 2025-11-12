"""
Helper script to program a demo NTAG215 filament tag.
Supports a standard table for filament materials (PLA, PETG, TPU),
and allows starting with used spools (enter current grams).
"""

import math
from machine import SPI, Pin
from pn532_spi import PN532
import tag_storage


# ---------------------------------------------------------------------------
# Filament material properties
# density in g/cm³, packing factor = estimated winding efficiency
# ---------------------------------------------------------------------------
FILAMENT_TYPES = {
    "PLA":  {"density": 1.24, "packing": 0.90},
    "PETG": {"density": 1.27, "packing": 0.83},
    "TPU":  {"density": 1.20, "packing": 0.80},
}


# ---------------------------------------------------------------------------
# USER CONFIGURATION
# ---------------------------------------------------------------------------
FILAMENT_TYPE = "PLA"      # Choose: "PLA", "PETG", or "TPU"
BRAND = "Sunlu"            # Optional brand name
GRAMS_REMAIN = 280      # Current measured weight (spool only)
MIN_D = 82               # Inner hub diameter (mm)
MAX_D = 170              # Outer flange diameter (mm)
WIDTH = 52               # Spool width (mm)
FILAMENT_DIAMETER_MM = 1.75


# ---------------------------------------------------------------------------
# COMPUTATION FUNCTIONS
# ---------------------------------------------------------------------------
def filament_area_mm2(d_mm):
    """Cross-sectional area of filament."""
    return math.pi * (d_mm / 2) ** 2


def compute_spool_length(min_d, max_d, width, filament_d, packing_factor):
    """Estimate total length (m) if spool were full."""
    r_core = min_d / 2
    r_outer = max_d / 2
    area = filament_area_mm2(filament_d)
    vol_mm3 = math.pi * width * (r_outer**2 - r_core**2)
    vol_mm3 *= packing_factor
    length_m = vol_mm3 / area / 1000
    return length_m


def compute_weight_from_length(length_m, filament_d, density_g_cm3):
    """Convert filament length (m) → weight (g)."""
    area_mm2 = filament_area_mm2(filament_d)
    vol_mm3 = area_mm2 * (length_m * 1000)
    vol_cm3 = vol_mm3 / 1000.0
    return vol_cm3 * density_g_cm3


def compute_length_from_weight(weight_g, filament_d, density_g_cm3):
    """Convert filament weight (g) → length (m)."""
    vol_cm3 = weight_g / density_g_cm3
    vol_mm3 = vol_cm3 * 1000.0
    area_mm2 = filament_area_mm2(filament_d)
    length_m = vol_mm3 / area_mm2 / 1000.0
    return length_m


def wait_for_tag(pn532):
    print("Place an NTAG215 tag on the reader to program...")
    uid = None
    while uid is None:
        uid = pn532.read_passive_target(timeout=500)
    return uid


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    ftype = FILAMENT_TYPES[FILAMENT_TYPE]
    density = ftype["density"]
    packing = ftype["packing"]

    meters_full = round(compute_spool_length(MIN_D, MAX_D, WIDTH,
                                             FILAMENT_DIAMETER_MM, packing), 2)
    grams_full = round(compute_weight_from_length(meters_full,
                                                  FILAMENT_DIAMETER_MM, density), 1)

    meters_rem = round(compute_length_from_weight(GRAMS_REMAIN,
                                                  FILAMENT_DIAMETER_MM, density), 2)

    print(f"\n--- Filament Tag Data ---")
    print(f"Brand: {BRAND}")
    print(f"Type: {FILAMENT_TYPE}")
    print(f"Geometry: {MIN_D}-{MAX_D} mm x {WIDTH} mm")
    print(f"Density: {density} g/cm³ | Packing: {packing}")
    print(f"Full length:  {meters_full} m  (~{grams_full} g)")
    print(f"Remaining:    {meters_rem} m  ({GRAMS_REMAIN} g)\n")

    # Setup PN532
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

    tag_payload = {
        "ver": 1,
        "brand": BRAND,
        "type": FILAMENT_TYPE,
        "fil_d": FILAMENT_DIAMETER_MM,
        "min_d": MIN_D,
        "max_d": MAX_D,
        "width": WIDTH,
        "grams_full": grams_full,
        "grams_rem": GRAMS_REMAIN,
        "meters_full": meters_full,
        "meters_rem": meters_rem,
    }

    try:
        tag_storage.write_ndef_json(pn532, tag_payload)
        print("Tag written successfully.")
        print("Payload:", tag_payload)
    except Exception as err:
        print("Failed to write tag:", err)


if __name__ == "__main__":
    main()
