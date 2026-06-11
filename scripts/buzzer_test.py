#!/usr/bin/env python3
import argparse
import time

from gpiozero import PWMOutputDevice


def beep(pin, duration):
    pin.value = 0.5
    time.sleep(duration)
    pin.value = 0.0


def main():
    def frequency(value):
        hz = int(value)
        if not 2000 <= hz <= 5000:
            raise argparse.ArgumentTypeError("must be between 2000 and 5000 Hz")
        return hz

    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=int, default=12)
    parser.add_argument("--frequency", type=frequency, default=3000)
    args = parser.parse_args()

    buzzer = PWMOutputDevice(args.pin, active_high=False, initial_value=0.0, frequency=args.frequency)
    try:
        print(f"double short beep at {args.frequency} Hz", flush=True)
        beep(buzzer, 0.08)
        time.sleep(0.08)
        beep(buzzer, 0.08)
        time.sleep(0.5)
        print(f"long confirm beep at {args.frequency} Hz", flush=True)
        beep(buzzer, 0.35)
    finally:
        buzzer.value = 0.0
        buzzer.close()


if __name__ == "__main__":
    main()
