#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from airgesture.hardware import ActiveLowBuzzer


def beep(pin, duration):
    pin.on()
    time.sleep(duration)
    pin.off()


def main():
    def frequency(value):
        hz = int(value)
        if not 2000 <= hz <= 5000:
            raise argparse.ArgumentTypeError("must be between 2000 and 5000 Hz")
        return hz

    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=int, default=12)
    parser.add_argument("--frequency", type=frequency, default=3000)
    parser.add_argument("--driver", choices=("auto", "lgpio", "pigpio", "gpiozero", "off"), default="auto")
    args = parser.parse_args()

    buzzer = ActiveLowBuzzer(args.pin, frequency=args.frequency, driver=args.driver)
    try:
        if not buzzer.enabled:
            raise SystemExit("buzzer is disabled; no PWM driver could be opened")
        print(f"double short beep at {args.frequency} Hz", flush=True)
        beep(buzzer, 0.08)
        time.sleep(0.08)
        beep(buzzer, 0.08)
        time.sleep(0.5)
        print(f"long confirm beep at {args.frequency} Hz", flush=True)
        beep(buzzer, 0.35)
    finally:
        buzzer.close()


if __name__ == "__main__":
    main()
