#!/usr/bin/env python3
import argparse
import time

from gpiozero import LED


def beep(pin, duration):
    pin.on()
    time.sleep(duration)
    pin.off()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=int, default=12)
    args = parser.parse_args()

    buzzer = LED(args.pin, active_high=False)
    buzzer.off()
    try:
        print("double short beep", flush=True)
        beep(buzzer, 0.08)
        time.sleep(0.08)
        beep(buzzer, 0.08)
        time.sleep(0.5)
        print("long confirm beep", flush=True)
        beep(buzzer, 0.35)
    finally:
        buzzer.off()
        buzzer.close()


if __name__ == "__main__":
    main()
