from machine import SPI, Pin
from pn532_spi import PN532
import time

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(11), miso=Pin(12))
cs = Pin(13, Pin.OUT)
pn532 = PN532(spi, cs, debug=False)

pn532.SAM_configuration()

print("Place NTAG215 on the antenna...")
uid = None
while uid is None:
    uid = pn532.read_passive_target(timeout=2000)

print("Tag detected UID:", [hex(x) for x in uid])

# --- Dump all 135 pages (0–134) ---
print("Reading pages...")
for page in range(0, 135):
    data = pn532.ntag2xx_read_block(page)
    if data is None:
        print("Failed to read page", page)
        break
    print("Page {:03d}: {}".format(page, ' '.join('{:02X}'.format(b) for b in data)))
    #time.sleep_ms(10)
