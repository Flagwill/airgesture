#!/usr/bin/env python3
import argparse
import json
import time

import serial


def parse_airgesture_line(line):
    line = line.strip()
    if not line:
        return None
    parts = line.split(",")
    if parts[0] != "AG":
        return {"raw": line}

    data = {"type": "AG"}
    for item in parts[1:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if value in ("0", "1") and key in ("face", "wave"):
            data[key] = bool(int(value))
        else:
            try:
                data[key] = int(value)
            except ValueError:
                try:
                    data[key] = float(value)
                except ValueError:
                    data[key] = value
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.5)
    args = parser.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=args.timeout)
    print(f"Listening on {args.port} at {args.baud} baud")

    last_ping = 0.0
    buf = bytearray()
    while True:
        now = time.time()
        if now - last_ping > 3.0:
            ser.write(b"PING\n")
            last_ping = now

        chunk = ser.read(256)
        if not chunk:
            continue
        buf.extend(chunk)
        while b"\n" in buf:
            raw, _, rest = buf.partition(b"\n")
            buf = bytearray(rest)
            text = raw.decode("utf-8", "replace")
            data = parse_airgesture_line(text)
            if data is not None:
                print(json.dumps(data, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
