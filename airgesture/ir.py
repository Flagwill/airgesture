"""IR05T code loading and sending."""

import json
import time
from pathlib import Path


class IRCodeLibrary:
    def __init__(self, file_path, port, baud, enabled=True):
        self.file_path = Path(file_path)
        self.port = port
        self.baud = baud
        self.enabled = enabled
        self.codes = {}
        self.load()

    def load(self):
        self.codes.clear()
        if not self.enabled or not self.file_path.exists():
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        entry = json.loads(text)
                    except Exception:
                        continue
                    func = entry.get("function")
                    payload_hex = entry.get("payload_hex")
                    if not func or not payload_hex:
                        continue
                    try:
                        payload = bytes(int(part, 16) for part in payload_hex.split())
                    except Exception:
                        continue
                    self.codes[func] = payload
        except Exception:
            self.codes.clear()

    def available_functions(self):
        return sorted(self.codes.keys())

    def has(self, function):
        return function in self.codes

    def send(self, function):
        import serial

        if not self.enabled:
            return False, "IR DISABLED"
        payload = self.codes.get(function)
        if payload is None:
            return False, "IR CODE MISSING"
        frame = b"\xFD\xFD" + payload + b"\xDF\xDF"
        ser = serial.Serial(self.port, baudrate=self.baud, timeout=0.25)
        try:
            ser.reset_input_buffer()
            ser.write(frame)
            ser.flush()
            time.sleep(0.08)
        finally:
            ser.close()
        return True, function
