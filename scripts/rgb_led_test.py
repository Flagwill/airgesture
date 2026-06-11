#!/usr/bin/env python3
import argparse
import time

from gpiozero import LED


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--red-pin", type=int, default=13)
    parser.add_argument("--green-pin", type=int, default=19)
    parser.add_argument("--blue-pin", type=int, default=16)
    parser.add_argument("--common-anode", action="store_true")
    args = parser.parse_args()

    active_high = not args.common_anode
    red = LED(args.red_pin, active_high=active_high)
    green = LED(args.green_pin, active_high=active_high)
    blue = LED(args.blue_pin, active_high=active_high)

    colors = [
        ("RED", (1, 0, 0)),
        ("GREEN", (0, 1, 0)),
        ("BLUE", (0, 0, 1)),
        ("YELLOW", (1, 0.45, 0)),
        ("CYAN", (0, 0.7, 1)),
        ("PURPLE", (0.5, 0, 1)),
        ("OFF", (0, 0, 0)),
    ]

    try:
        for name, (r, g, b) in colors:
            print(name, flush=True)
            red.value = 1 if r >= 0.5 else 0
            green.value = 1 if g >= 0.5 else 0
            blue.value = 1 if b >= 0.5 else 0
            time.sleep(1.2)
    finally:
        red.value = 0
        green.value = 0
        blue.value = 0
        red.close()
        green.close()
        blue.close()


if __name__ == "__main__":
    main()
