#!/usr/bin/env python3
"""
Send learned IR codes (from captures JSONL) via IR05T module.

Usage examples:
  python scripts/ir05t_emit.py --port /dev/ttyAMA3 --baud 9600 --file captures/ir05t_codes.jsonl --index -1
  python scripts/ir05t_emit.py --port /dev/ttyAMA3 --baud 9600 --file captures/ir05t_codes.jsonl --channel 1

Modes:
  - raw (default): read entry payload and send FD FD +payload+ DF DF
  - channel: send channel emit frame (FD FD FB <n> DF)
"""
import argparse
import json
import time
from pathlib import Path

import serial


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def load_entries(path: Path):
    entries = []
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                entries.append(json.loads(ln))
            except Exception:
                continue
    return entries


def parse_payload_bytes(entry):
    ph = entry.get("payload_hex")
    if ph:
        parts = [p for p in ph.split() if p]
        try:
            return bytes(int(x, 16) for x in parts)
        except Exception:
            pass
    # fallback: try extracting from frame_hex if present
    fh = entry.get("frame_hex")
    if fh:
        parts = [p for p in fh.split() if p]
        # expect frame = FD FD <payload...> DF DF
        if len(parts) >= 4 and parts[0].upper() == "FD" and parts[1].upper() == "FD" and parts[-1].upper() == "DF" and parts[-2].upper() == "DF":
            mid = parts[2:-2]
            try:
                return bytes(int(x, 16) for x in mid)
            except Exception:
                pass
    return None


def send_raw_payload(ser: serial.Serial, payload: bytes, expect_reply=True, reply_timeout=0.5):
    frame = b"\xFD\xFD" + payload + b"\xDF\xDF"
    print("SEND RAW:", hx(frame))
    ser.write(frame)
    ser.flush()
    if expect_reply:
        time.sleep(0.05)
        # read available
        rv = ser.read(512)
        if rv:
            print("REPLY:", hx(rv))
        else:
            print("No immediate reply")


def send_channel_emit(ser: serial.Serial, channel: int, expect_reply=True):
    # frame: FD FD FB NN DF (examples show single DF terminator)
    cmd = bytes([0xFD, 0xFD, 0xFB, channel & 0xFF, 0xDF])
    print("SEND CHANNEL EMIT:", hx(cmd))
    ser.write(cmd)
    ser.flush()
    if expect_reply:
        time.sleep(0.05)
        rv = ser.read(256)
        if rv:
            print("REPLY:", hx(rv))
        else:
            print("No immediate reply")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyAMA3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--file", default="captures/ir05t_codes.jsonl")
    parser.add_argument("--index", type=int, default=-1, help="index into JSONL (default last entry)")
    parser.add_argument("--channel", type=int, choices=range(1, 6), help="use channel emit instead of raw payload")
    parser.add_argument("--repeat", type=int, default=1, help="how many times to send")
    parser.add_argument("--delay", type=float, default=0.25, help="delay between repeats (s)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    p = Path(args.file)
    if not p.exists():
        print("File not found:", p)
        return

    entries = load_entries(p)
    if not entries:
        print("No entries in file")
        return

    idx = args.index
    if idx < 0:
        idx = len(entries) + idx
    if idx < 0 or idx >= len(entries):
        print("Index out of range")
        return

    entry = entries[idx]
    payload = parse_payload_bytes(entry)

    if args.channel is not None:
        if args.dry_run:
            print("DRY RUN: would send channel emit", args.channel)
            return
        ser = serial.Serial(args.port, baudrate=args.baud, timeout=0.2)
        try:
            for i in range(args.repeat):
                send_channel_emit(ser, args.channel)
                if i + 1 < args.repeat:
                    time.sleep(args.delay)
        finally:
            ser.close()
        return

    if payload is None:
        print("Could not parse payload from selected entry")
        return

    print("Selected entry time:", entry.get("time"))
    print("Payload bytes:", len(payload))
    print("Payload hex:", " ".join(f"{b:02X}" for b in payload))

    if args.dry_run:
        print("DRY RUN: not sending")
        return

    ser = serial.Serial(args.port, baudrate=args.baud, timeout=0.5)
    try:
        for i in range(args.repeat):
            send_raw_payload(ser, payload)
            if i + 1 < args.repeat:
                time.sleep(args.delay)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
