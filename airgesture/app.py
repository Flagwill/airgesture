"""Main AirGesture K230 control application."""

import argparse
import threading
import time

from .hardware import ActiveLowBuzzer, RgbLed
from .ir import IRCodeLibrary
from .protocol import parse_line
from .state import GestureStateMachine
from .web import ThreadedHTTPServer, make_handler


def initial_state():
    return {
        "serial_ok": False,
        "last_rx_age": None,
        "raw": "",
        "seq": None,
        "face": False,
        "wave": False,
        "gesture": "NONE",
        "k230_fps": 0.0,
        "state": "IDLE",
        "command": "",
        "event": "",
        "ready_remaining": 0.0,
        "history": [],
        "ac": {
            "power": False,
            "temp": 26,
            "mode": "COOL",
            "fan": "AUTO",
        },
        "last_action": "",
        "action_count": 0,
        "led": "OFF",
        "data_timeout": False,
        "ir_available": [],
        "ir_last_function": "",
        "ir_last_status": "",
    }


class AirGestureControlApp:
    def __init__(self, args):
        self.args = args
        self.running = True
        self.state_lock = threading.Lock()
        self.latest = initial_state()
        self.led = RgbLed(
            args.led_red_pin,
            args.led_green_pin,
            args.led_blue_pin,
            active_high=not args.led_common_anode,
            enabled=not args.no_led,
        )
        self.buzzer = ActiveLowBuzzer(
            args.buzzer_pin,
            enabled=not args.no_buzzer,
            frequency=args.buzzer_frequency,
            driver=args.buzzer_driver,
            duty_cycle=args.buzzer_duty_cycle,
        )
        self.ir = IRCodeLibrary(args.ir_codes_file, args.ir_port, args.ir_baud, enabled=not args.no_ir)
        with self.state_lock:
            self.latest["ir_available"] = self.ir.available_functions()
            self.latest["ir_last_status"] = "IR READY" if self.latest["ir_available"] else "IR CODE FILE EMPTY"

    def run(self):
        thread = threading.Thread(target=self.serial_loop, daemon=True)
        thread.start()

        handler = make_handler(self.latest, self.state_lock)
        httpd = ThreadedHTTPServer((self.args.host, self.args.port), handler)
        print(f"K230 AirGesture control running on http://{self.args.host}:{self.args.port}/", flush=True)
        try:
            httpd.serve_forever()
        finally:
            self.running = False
            self.led.close()
            self.buzzer.close()
            httpd.server_close()

    def serial_loop(self):
        import serial

        sm = GestureStateMachine(self.led, self.buzzer, self.ir, log_path=self.args.log_path)
        buf = bytearray()
        ser = None
        last_rx_at = 0.0
        while self.running:
            try:
                if ser is None or not ser.is_open:
                    ser = serial.Serial(self.args.serial_port, baudrate=self.args.baud, timeout=0.2)
                    with self.state_lock:
                        self.latest["serial_ok"] = True
                        self.latest["event"] = "SERIAL OPEN"

                chunk = ser.read(256)
                now = time.time()
                if not chunk:
                    self._mark_idle_tick(now, last_rx_at)
                    continue

                buf.extend(chunk)
                while b"\n" in buf:
                    raw, _, rest = buf.partition(b"\n")
                    buf = bytearray(rest)
                    self._handle_serial_line(raw, now, sm)
                    last_rx_at = now
            except Exception as exc:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass
                ser = None
                with self.state_lock:
                    self.latest["serial_ok"] = False
                    self.latest["event"] = "SERIAL ERROR"
                    self.latest["raw"] = repr(exc)
                    self.latest["data_timeout"] = True
                    self.latest["led"] = self.led.update(False, "IDLE", True)
                time.sleep(1)

    def _mark_idle_tick(self, now, last_rx_at):
        age = round(now - last_rx_at, 2) if last_rx_at else None
        data_timeout = bool(age is not None and age > 3.0)
        with self.state_lock:
            serial_ok = self.latest.get("serial_ok", False)
            state = self.latest.get("state", "IDLE")
        led_mode = self.led.update(serial_ok, state, data_timeout)
        with self.state_lock:
            self.latest["last_rx_age"] = age
            self.latest["data_timeout"] = data_timeout
            self.latest["led"] = led_mode

    def _handle_serial_line(self, raw, now, state_machine):
        line = raw.decode("utf-8", "replace")
        data = parse_line(line)
        if not data:
            return

        face = bool(data.get("face", False))
        wave = bool(data.get("wave", False))
        gesture = data.get("gesture", "NONE")
        control = state_machine.update(now, face, wave, gesture)
        led_mode = self.led.update(True, control.get("state", "IDLE"))
        with self.state_lock:
            self.latest.update(
                {
                    "serial_ok": True,
                    "last_rx_age": 0.0,
                    "raw": data.get("raw", line.strip()),
                    "seq": data.get("seq", self.latest.get("seq")),
                    "face": face,
                    "wave": wave,
                    "gesture": gesture,
                    "k230_fps": data.get("fps", self.latest.get("k230_fps", 0.0)),
                    "data_timeout": False,
                    "led": led_mode,
                    **control,
                }
            )


def build_parser():
    def buzzer_frequency(value):
        frequency = int(value)
        if not 2000 <= frequency <= 5000:
            raise argparse.ArgumentTypeError("must be between 2000 and 5000 Hz")
        return frequency

    def buzzer_duty_cycle(value):
        duty_cycle = int(value)
        if not 1 <= duty_cycle <= 99:
            raise argparse.ArgumentTypeError("must be between 1 and 99 percent")
        return duty_cycle

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--serial-port", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--led-red-pin", type=int, default=13)
    parser.add_argument("--led-green-pin", type=int, default=19)
    parser.add_argument("--led-blue-pin", type=int, default=16)
    parser.add_argument("--led-common-anode", action="store_true")
    parser.add_argument("--no-led", action="store_true")
    parser.add_argument("--buzzer-pin", type=int, default=12)
    parser.add_argument("--buzzer-frequency", type=buzzer_frequency, default=3000)
    parser.add_argument("--buzzer-duty-cycle", type=buzzer_duty_cycle, default=75)
    parser.add_argument("--buzzer-driver", choices=("auto", "lgpio", "pigpio", "gpiozero", "off"), default="auto")
    parser.add_argument("--no-buzzer", action="store_true")
    parser.add_argument("--ir-codes-file", default="captures/ir05t_codes.jsonl")
    parser.add_argument("--ir-port", default="/dev/ttyAMA3")
    parser.add_argument("--ir-baud", type=int, default=9600)
    parser.add_argument("--no-ir", action="store_true")
    parser.add_argument("--log-path", default="airgesture_actions.log")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    app = AirGestureControlApp(args)
    app.run()


if __name__ == "__main__":
    main()
