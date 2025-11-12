# TM1637 test script for Raspberry Pi Pico
# Requires tm1637.py from https://github.com/mcauser/micropython-tm1637

from machine import Pin
from time import sleep
from tm1637 import TM1637

# --- Pin definitions (adjust if needed)
CLK = Pin(1)   # clock
DIO = Pin(0)   # data

# --- Initialize display
tm = TM1637(clk=CLK, dio=DIO, brightness=7)

# --- Basic demo
tm.show("----")
sleep(0.5)
tm.show("boot")
sleep(1)
tm.show("   ")  # clear display

# --- Count from 0 to 99
for i in range(100):
    tm.number(i)
    sleep(0.05)

sleep(1)

# --- Show numbers with colon (e.g., a clock format)
for sec in range(10):
    tm.numbers(12, sec, colon=True)
    sleep(0.5)

sleep(1)

# --- Show some text
tm.show("dEAd")
sleep(1)
tm.show("bEEF")
sleep(1)

# --- Scroll a message
tm.scroll("hello", delay=250)

# --- Temperature example
for t in [-5, 20, 37, 100]:
    tm.temperature(t)
    sleep(1)

# --- Hex example
for val in range(0x123, 0x12A):
    tm.hex(val)
    sleep(0.5)

# --- Fade brightness test
for b in range(8):
    tm.brightness(b)
    tm.number(b)
    sleep(0.2)

tm.show("End ")
