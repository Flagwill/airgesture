#!/usr/bin/env python3
"""
Capture IR codes from IR05T learning module and store as JSONL.

Usage examples:
  python scripts/ir05t_capture.py --port /dev/ttyAMA3 --baud 9600 --out captures/ir05t_codes.jsonl --duration 10
  python scripts/ir05t_capture.py --port /dev/ttyAMA3 --baud 9600 --channel 1 --duration 15

Protocol (partial):
  - Enter learning:  FD FD F1 F2 DF  -> reply: FD FD +232 bytes + DF DF
  - Enter channel learning: FD FD FA 0N DF -> reply FA
  - Channel emit: FD FD FB 0N DF -> reply FB
"""
import argparse
import json
import time
from pathlib import Path

import serial


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def send_cmd(ser: serial.Serial, cmd_bytes: bytes):
    ser.write(cmd_bytes)
    ser.flush()


def build_frame(parts):
    return bytes(parts)


ENTER_LEARN = build_frame([0xFD, 0xFD, 0xF1, 0xF2, 0xDF])


def channel_learn_cmd(channel: int):
    return bytes([0xFD, 0xFD, 0xFA, channel & 0xFF, 0xDF])


def channel_emit_cmd(channel: int):
    return bytes([0xFD, 0xFD, 0xFB, channel & 0xFF, 0xDF])


def read_frame_from_buffer(buf: bytearray):
    # Look for header FD FD and trailer DF DF
    start = buf.find(b"\xFD\xFD")
    if start < 0:
        return None
    end = buf.find(b"\xDF\xDF", start + 2)
    if end < 0:
        return None
    # include header and trailer
    frame = bytes(buf[start : end + 2])
    # remove consumed bytes from buffer
    del buf[: end + 2]
    return frame


def capture_learning(port, baud, out_path: Path, duration: float, channel=None, enter=True):
    ser = serial.Serial(port, baudrate=baud, timeout=0.25)
    try:
        buf = bytearray()
        start_time = time.time()

        # Optionally send channel learn command first
        if channel is not None:
            cmd = channel_learn_cmd(channel)
            print("SEND:", hx(cmd))
            send_cmd(ser, cmd)
            # small pause
            time.sleep(0.15)

        if enter:
            print("Sending enter-learning command")
            send_cmd(ser, ENTER_LEARN)

        print(f"Listening up to {duration} seconds for learning frames...")
        with out_path.open("a", encoding="utf-8") as outf:
            while time.time() - start_time < duration:
                chunk = ser.read(512)
                if chunk:
                    buf.extend(chunk)
                    # Keep searching for complete frames
                    while True:
                        frame = read_frame_from_buffer(buf)
                        if frame is None:
                            break
                        now = time.time()
                        # frame begins with FD FD and ends with DF DF
                        # payload = frame[2:-2]
                        payload = frame[2:-2]
                        entry = {
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "timestamp": now,
                            "frame_hex": hx(frame),
                            "payload_len": len(payload),
                            "payload_hex": " ".join(f"{b:02X}" for b in payload),
                            "channel": channel,
                        }
                        print("CAPTURED:", entry["payload_len"], "bytes")
                        outf.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        outf.flush()
                else:
                    # no data, short sleep to avoid busy loop
                    time.sleep(0.02)
    finally:
        try:
            ser.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyAMA3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--out", default="captures/ir05t_codes.jsonl")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--channel", type=int, choices=range(1, 6), help="channel 1-5 for channel-specific learn/emit")
    parser.add_argument("--no-enter", dest="enter", action="store_false", help="do not send enter-learning command (useful if module already in learning)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Port={args.port} Baud={args.baud} Out={out_path} Duration={args.duration}s Channel={args.channel}")
    capture_learning(args.port, args.baud, out_path, args.duration, channel=args.channel, enter=args.enter)


if __name__ == "__main__":
    main()
