from machine import SPI, Pin
from pn532_spi import PN532
import time

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(11), miso=Pin(12))
cs = Pin(13, Pin.OUT)
pn532 = PN532(spi, cs, debug=False)

print("Firmware:", pn532.get_firmware_version())
print("Configuring SAM...")
pn532.SAM_configuration()  # <--- this turns on the RF field

print("Waiting for tag...")
while True:
    uid = pn532.read_passive_target(timeout=2000)
    if uid:
        print("Tag detected:", [hex(x) for x in uid])
    else:
        print(".", end="")
        time.sleep(0.2)
