#!/usr/bin/env python3
import argparse
import time

import serial


def hx(data):
    return " ".join(f"{b:02X}" for b in data)


def transact(port, baud, tx, wait=0.35):
    ser = serial.Serial(port, baudrate=baud, timeout=0.15)
    ser.reset_input_buffer()
    ser.write(bytes(tx))
    ser.flush()
    time.sleep(wait)
    rx = ser.read(256)
    ser.close()
    return rx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyAMA3")
    parser.add_argument("--bauds", default="9600,19200,38400,57600,115200")
    args = parser.parse_args()

    bauds = [int(x.strip()) for x in args.bauds.split(",") if x.strip()]

    # Known commands from IR05 family protocol
    set_9600 = [0xFE, 0x55, 0xEF, 0xAA, 0xF1]
    set_long = [0xFE, 0xEC, 0xCE, 0x66, 0x00]
    emit_slot_01 = [0xFE, 0xDC, 0xBA, 0x66, 0x01]

    print("STEP 1: try force baud to 9600")
    matched = False
    for baud in bauds:
        try:
            rx = transact(args.port, baud, set_9600, 0.45)
            print(f"TX@{baud}: {hx(set_9600)}")
            print(f"RX@{baud}: {hx(rx)}")
            if rx == bytes([0xFE, 0x96, 0x00]):
                print("MATCH: protocol alive, baud now set to 9600")
                matched = True
                break
        except Exception as exc:
            print(f"ERR@{baud}: {exc!r}")

    if not matched:
        print("NO MATCH on baud-set command")
        return

    print("STEP 2: set long-code output")
    rx = transact(args.port, 9600, set_long, 0.35)
    print("TX@9600:", hx(set_long))
    print("RX@9600:", hx(rx))

    print("STEP 3: try emit slot 01")
    rx = transact(args.port, 9600, emit_slot_01, 0.35)
    print("TX@9600:", hx(emit_slot_01))
    print("RX@9600:", hx(rx))


if __name__ == "__main__":
    main()
