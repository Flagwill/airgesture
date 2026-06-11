#!/usr/bin/env python3
import argparse
import time

import serial


def read_probe(port, baud, seconds):
    ser = serial.Serial(port, baudrate=baud, timeout=0.2)
    chunks = []
    total = 0
    start = time.time()
    while time.time() - start < seconds:
        data = ser.read(256)
        if data:
            chunks.append(data)
            total += len(data)
    ser.close()
    raw = b"".join(chunks)
    return total, raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyAMA3")
    parser.add_argument("--seconds", type=float, default=2.5)
    parser.add_argument("--bauds", default="9600,19200,38400,57600,115200")
    args = parser.parse_args()

    for baud_text in args.bauds.split(","):
        baud = int(baud_text.strip())
        try:
            total, raw = read_probe(args.port, baud, args.seconds)
            print(f"BAUD {baud} BYTES {total}")
            if raw:
                print("TEXT", raw[:300].decode("utf-8", "replace"))
                print("HEX", raw[:120].hex(" "))
        except Exception as exc:
            print(f"BAUD {baud} ERROR {exc!r}")


if __name__ == "__main__":
    main()
