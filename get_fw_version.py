from machine import SPI, Pin
from pn532_spi import PN532

spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(10), mosi=Pin(11), miso=Pin(12))
cs = Pin(13, Pin.OUT)

pn532 = PN532(spi, cs, debug=True)

print("Getting firmware version...")
try:
    fw = pn532.get_firmware_version()
    print("Firmware:", fw)
except Exception as e:
    print("Error:", e)
