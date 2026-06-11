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


def sweep(buzzer, frequencies, dwell, pause):
    for frequency in frequencies:
        print(f"beep at {frequency} Hz", flush=True)
        buzzer.frequency = frequency
        beep(buzzer, dwell)
        time.sleep(pause)


def main():
    def frequency(value):
        hz = int(value)
        if not 2000 <= hz <= 5000:
            raise argparse.ArgumentTypeError("must be between 2000 and 5000 Hz")
        return hz

    def duty_cycle(value):
        percent = int(value)
        if not 1 <= percent <= 99:
            raise argparse.ArgumentTypeError("must be between 1 and 99 percent")
        return percent

    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=int, default=12)
    parser.add_argument("--frequency", type=frequency, default=3000)
    parser.add_argument("--duty-cycle", type=duty_cycle, default=50)
    parser.add_argument("--start-frequency", type=frequency, default=2000)
    parser.add_argument("--stop-frequency", type=frequency, default=5000)
    parser.add_argument("--step-frequency", type=int, default=500)
    parser.add_argument("--dwell", type=float, default=0.12)
    parser.add_argument("--pause", type=float, default=0.12)
    parser.add_argument("--mode", choices=("single", "sweep", "both"), default="both")
    parser.add_argument("--driver", choices=("auto", "lgpio", "pigpio", "gpiozero", "off"), default="auto")
    args = parser.parse_args()

    if args.step_frequency <= 0:
        raise SystemExit("--step-frequency must be greater than 0")
    if args.start_frequency > args.stop_frequency:
        raise SystemExit("--start-frequency must be less than or equal to --stop-frequency")

    buzzer = ActiveLowBuzzer(args.pin, frequency=args.frequency, driver=args.driver, duty_cycle=args.duty_cycle)
    try:
        if not buzzer.enabled:
            raise SystemExit("buzzer is disabled; no PWM driver could be opened")

        if args.mode in ("single", "both"):
            print(f"double short beep at {args.frequency} Hz", flush=True)
            beep(buzzer, 0.08)
            time.sleep(0.08)
            beep(buzzer, 0.08)
            time.sleep(0.35)
            print(f"long confirm beep at {args.frequency} Hz", flush=True)
            beep(buzzer, 0.35)

        if args.mode in ("sweep", "both"):
            print(
                f"frequency sweep from {args.start_frequency} to {args.stop_frequency} Hz in steps of {args.step_frequency} Hz",
                flush=True,
            )
            frequencies = range(args.start_frequency, args.stop_frequency + 1, args.step_frequency)
            sweep(buzzer, frequencies, args.dwell, args.pause)
    finally:
        buzzer.close()


if __name__ == "__main__":
    main()
