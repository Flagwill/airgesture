#!/usr/bin/env python3
import argparse
from collections import Counter, deque
import json
from pathlib import Path
import threading
import time
from http import server
from socketserver import ThreadingMixIn

import serial

try:
    from gpiozero import LED
except Exception:
    LED = None


running = True
state_lock = threading.Lock()
LOG_PATH = Path("/home/ethanwwy/airgesture/airgesture_actions.log")

latest = {
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

led_controller = None
buzzer_controller = None
ir_controller = None


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirGesture K230 Control</title>
<style>
  html,body{margin:0;min-height:100%;background:#101417;color:#eef5f2;font-family:Arial,"Microsoft YaHei",sans-serif;}
  body{display:grid;grid-template-rows:auto 1fr;}
  header{padding:10px 14px;background:#1a2327;border-bottom:1px solid #2e3b41;display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
  h1{font-size:16px;margin:0 8px 0 0;color:#fff;}
  .pill{font-size:12px;line-height:1;color:#cbd8d4;background:#253138;border:1px solid #3a484e;padding:7px 9px;border-radius:4px;}
  .ok{color:#89f5b0;}
  .no{color:#ff9d9d;}
  .ready{color:#ffd36d;}
  .exec{color:#92d8ff;}
  main{padding:16px;display:grid;grid-template-columns:minmax(260px,520px) minmax(260px,1fr);gap:16px;align-items:start;}
  section{border:1px solid #2f3d42;background:#151c20;border-radius:6px;padding:14px;}
  h2{font-size:15px;margin:0 0 12px;color:#fff;font-weight:700;}
  .grid{display:grid;grid-template-columns:120px 1fr;gap:10px 12px;font-size:14px;}
  .key{color:#8fa19c;}
  .value{color:#eef5f2;word-break:break-word;}
  .big{font-size:32px;font-weight:700;letter-spacing:0;margin:8px 0 4px;}
  .sub{color:#9eb0ac;font-size:13px;}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{padding:8px;border-bottom:1px solid #273338;text-align:left;}
  th{color:#9fb0ad;font-weight:600;}
  td{color:#eef5f2;}
  @media(max-width:760px){main{grid-template-columns:1fr;padding:10px;} .big{font-size:26px;}}
</style>
</head>
<body>
<header>
  <h1>AirGesture K230</h1>
  <span class="pill" id="serial">Serial --</span>
  <span class="pill" id="data">Data --</span>
  <span class="pill" id="face">Face --</span>
  <span class="pill" id="wave">Wave --</span>
  <span class="pill" id="gesture">Gesture --</span>
  <span class="pill" id="state">State IDLE</span>
  <span class="pill" id="event">Event --</span>
</header>
<main>
  <section>
    <h2>Control</h2>
    <div class="big" id="command">--</div>
    <div class="sub" id="summary">Waiting for K230 data</div>
    <div class="grid" style="margin-top:16px">
      <div class="key">Power</div><div class="value" id="acPower">--</div>
      <div class="key">Temp</div><div class="value" id="acTemp">--</div>
      <div class="key">Mode</div><div class="value" id="acMode">--</div>
      <div class="key">Fan</div><div class="value" id="acFan">--</div>
      <div class="key">Last Action</div><div class="value" id="lastAction">--</div>
      <div class="key">LED</div><div class="value" id="led">--</div>
      <div class="key">K230 FPS</div><div class="value" id="fps">--</div>
      <div class="key">Last RX</div><div class="value" id="age">--</div>
      <div class="key">Raw</div><div class="value" id="raw">--</div>
    </div>
  </section>
  <section>
    <h2>History</h2>
    <table>
      <thead><tr><th>Time</th><th>Command</th><th>Gesture</th><th>Action</th></tr></thead>
      <tbody id="history"></tbody>
    </table>
  </section>
</main>
<script>
async function refresh(){
  try{
    const data = await fetch('/health', {cache:'no-store'}).then(r=>r.json());
    const serial = document.getElementById('serial');
    serial.textContent = 'Serial ' + (data.serial_ok ? 'OK' : 'NO');
    serial.className = 'pill ' + (data.serial_ok ? 'ok' : 'no');
    const dataPill = document.getElementById('data');
    dataPill.textContent = data.data_timeout ? 'Data TIMEOUT' : 'Data LIVE';
    dataPill.className = 'pill ' + (data.data_timeout ? 'no' : 'ok');
    const face = document.getElementById('face');
    face.textContent = 'Face ' + (data.face ? 'YES' : 'NO');
    face.className = 'pill ' + (data.face ? 'ok' : 'no');
    const wave = document.getElementById('wave');
    wave.textContent = 'Wave ' + (data.wave ? 'YES' : 'NO');
    wave.className = 'pill ' + (data.wave ? 'ready' : '');
    document.getElementById('gesture').textContent = 'Gesture ' + (data.gesture || 'NONE');
    const st = document.getElementById('state');
    st.textContent = 'State ' + (data.state || 'IDLE') + (data.ready_remaining ? ' ' + Number(data.ready_remaining).toFixed(1) + 's' : '');
    st.className = 'pill ' + (data.state === 'READY' ? 'ready' : data.state === 'EXECUTE' ? 'exec' : '');
    document.getElementById('event').textContent = data.event ? ('Event ' + data.event) : 'Event --';
    document.getElementById('command').textContent = data.command || '--';
    document.getElementById('summary').textContent = data.state === 'IDLE' ? 'Wave to activate' : data.state === 'READY' ? 'Show a stable right-hand gesture' : 'Command executed';
    const ac = data.ac || {};
    document.getElementById('acPower').textContent = ac.power ? 'ON' : 'OFF';
    document.getElementById('acTemp').textContent = (ac.temp || '--') + ' C';
    document.getElementById('acMode').textContent = ac.mode || '--';
    document.getElementById('acFan').textContent = ac.fan || '--';
    document.getElementById('lastAction').textContent = data.last_action || '--';
    document.getElementById('led').textContent = data.led || '--';
    document.getElementById('fps').textContent = Number(data.k230_fps || 0).toFixed(1);
    document.getElementById('age').textContent = data.last_rx_age == null ? '--' : Number(data.last_rx_age).toFixed(1) + 's';
    document.getElementById('raw').textContent = data.raw || '--';
    const rows = (data.history || []).map(x => `<tr><td>${x.time}</td><td>${x.command}</td><td>${x.gesture}</td><td>${x.action || ''}</td></tr>`).join('');
    document.getElementById('history').innerHTML = rows || '<tr><td colspan="4">No command yet</td></tr>';
  }catch(e){}
}
setInterval(refresh, 300);
refresh();
</script>
</body>
</html>""".encode("utf-8")


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        if self.path == "/health":
            with state_lock:
                body_state = dict(latest)
            body = (json.dumps(body_state, ensure_ascii=False) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)


class ThreadedHTTPServer(ThreadingMixIn, server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def parse_line(line):
    text = line.strip()
    if not text:
        return None
    parts = text.split(",")
    if parts[0] != "AG":
        return {"raw": text}
    data = {"raw": text}
    for item in parts[1:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key in ("face", "wave"):
            data[key] = value == "1" or value.lower() == "true"
        elif key == "seq":
            try:
                data[key] = int(value)
            except ValueError:
                pass
        elif key == "fps":
            try:
                data[key] = float(value)
            except ValueError:
                pass
        elif key == "gesture":
            data[key] = value.upper()
    return data


def command_from_gesture(gesture):
    mapping = {
        "FIST": "POWER_TOGGLE",
        "OPEN": "CANCEL",
        "ONE": "MODE_NEXT",
        "INDEX": "MODE_NEXT",
        "TWO": "TEMP_UP",
        "THUMB": "FAN_UP",
    }
    return mapping.get((gesture or "").upper())


class RgbLed:
    def __init__(self, red_pin, green_pin, blue_pin, active_high=True, enabled=True):
        self.enabled = enabled and LED is not None
        self.active_high = active_high
        self.mode = "OFF"
        self.flash_until = 0.0
        self.flash_color = (0.0, 0.0, 0.0)
        self.last_error_toggle = 0.0
        self.error_on = False
        self.idle_phase = 0
        self.red = None
        self.green = None
        self.blue = None
        if self.enabled:
            self.red = LED(red_pin, active_high=active_high)
            self.green = LED(green_pin, active_high=active_high)
            self.blue = LED(blue_pin, active_high=active_high)

    def set_rgb(self, red, green, blue):
        if not self.enabled:
            return
        self.red.value = 1 if red >= 0.5 else 0
        self.green.value = 1 if green >= 0.5 else 0
        self.blue.value = 1 if blue >= 0.5 else 0

    def pulse(self, color, duration=0.55):
        self.flash_color = color
        self.flash_until = time.time() + duration

    def update(self, serial_ok, state, data_timeout=False):
        now = time.time()
        if not self.enabled:
            self.mode = "DISABLED"
            return self.mode

        if now < self.flash_until:
            self.set_rgb(*self.flash_color)
            self.mode = "FLASH"
            return self.mode

        if not serial_ok or data_timeout:
            if now - self.last_error_toggle > 0.55:
                self.error_on = not self.error_on
                self.last_error_toggle = now
            self.set_rgb(0.8 if self.error_on else 0.0, 0.0, 0.0)
            self.mode = "DATA_TIMEOUT" if data_timeout else "SERIAL_ERROR"
            return self.mode

        if state == "READY":
            self.set_rgb(1.0, 1.0, 0.0)
            self.mode = "READY"
        elif state == "EXECUTE":
            self.set_rgb(0.0, 1.0, 0.0)
            self.mode = "EXECUTE"
        else:
            # Blue slow blink while idle.
            self.idle_phase = (self.idle_phase + 1) % 12
            level = 1.0 if self.idle_phase < 2 else 0.0
            self.set_rgb(0.0, 0.0, level)
            self.mode = "IDLE"
        return self.mode

    def close(self):
        if self.enabled:
            self.set_rgb(0.0, 0.0, 0.0)
            self.red.close()
            self.green.close()
            self.blue.close()


class ActiveLowBuzzer:
    def __init__(self, pin, enabled=True):
        self.enabled = enabled and LED is not None
        self.pin = None
        if self.enabled:
            self.pin = LED(pin, active_high=False)
            self.off()

    def on(self):
        if self.enabled:
            self.pin.on()

    def off(self):
        if self.enabled:
            self.pin.off()

    def pattern(self, items):
        if not self.enabled:
            return
        threading.Thread(target=self._run_pattern, args=(items,), daemon=True).start()

    def _run_pattern(self, items):
        for active, duration in items:
            if active:
                self.on()
            else:
                self.off()
            time.sleep(duration)
        self.off()

    def activated(self):
        self.pattern([(True, 0.08), (False, 0.08), (True, 0.08)])

    def confirmed(self):
        self.pattern([(True, 0.35)])

    def canceled(self):
        self.pattern([(True, 0.12)])

    def close(self):
        self.off()
        if self.enabled:
            self.pin.close()


def command_led_color(command):
    colors = {
        "POWER_TOGGLE": (0.0, 0.7, 0.9),
        "TEMP_UP": (1.0, 0.15, 0.0),
        "TEMP_DOWN": (0.0, 0.25, 1.0),
        "MODE_NEXT": (0.7, 0.0, 1.0),
        "FAN_UP": (0.0, 0.9, 0.25),
        "CANCEL": (0.8, 0.0, 0.0),
    }
    return colors.get(command, (0.0, 0.8, 0.2))


class VirtualAirConditioner:
    def __init__(self):
        self.power = False
        self.temp = 26
        self.modes = ["COOL", "HEAT", "DRY", "FAN"]
        self.mode_index = 0
        self.fans = ["AUTO", "LOW", "MID", "HIGH"]
        self.fan_index = 0
        self.action_count = 0
        self.last_action = ""

    def snapshot(self):
        return {
            "power": self.power,
            "temp": self.temp,
            "mode": self.modes[self.mode_index],
            "fan": self.fans[self.fan_index],
        }

    def execute(self, command):
        if command == "POWER_TOGGLE":
            self.power = not self.power
            text = "Power " + ("ON" if self.power else "OFF")
        elif command == "TEMP_UP":
            self.temp = min(30, self.temp + 1)
            text = "Temp " + str(self.temp) + " C"
        elif command == "TEMP_DOWN":
            self.temp = max(16, self.temp - 1)
            text = "Temp " + str(self.temp) + " C"
        elif command == "MODE_NEXT":
            self.mode_index = (self.mode_index + 1) % len(self.modes)
            text = "Mode " + self.modes[self.mode_index]
        elif command == "FAN_UP":
            self.fan_index = (self.fan_index + 1) % len(self.fans)
            text = "Fan " + self.fans[self.fan_index]
        else:
            text = "Unknown " + str(command)

        self.action_count += 1
        self.last_action = text
        return text


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


def write_action_log(command, gesture, action, ac_state):
    line = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": command,
        "gesture": gesture,
        "action": action,
        "ac": ac_state,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


class GestureStateMachine:
    def __init__(self, led=None, buzzer=None, ir=None):
        self.mode = "IDLE"
        self.ready_until = 0.0
        self.execute_until = 0.0
        self.event_until = 0.0
        self.event = ""
        self.command = ""
        self.release_required = None
        self.votes = deque(maxlen=8)
        self.history = deque(maxlen=12)
        self.ac = VirtualAirConditioner()
        self.led = led
        self.buzzer = buzzer
        self.ir = ir

    def _event(self, text, now, duration=1.1):
        self.event = text
        self.event_until = now + duration

    def update(self, now, face, wave, gesture):
        raw_cmd = command_from_gesture(gesture)
        ir_last_function = ""
        ir_last_status = ""

        if self.event and now > self.event_until:
            self.event = ""
        if self.mode == "EXECUTE" and now > self.execute_until:
            self.mode = "READY" if now < self.ready_until else "IDLE"
        if self.release_required and raw_cmd != self.release_required:
            self.release_required = None

        if self.mode == "IDLE":
            self.command = ""
            self.votes.clear()
            if face and wave:
                self.mode = "READY"
                self.ready_until = now + 5.0
                self.release_required = None
                if self.led:
                    self.led.pulse((1.0, 0.65, 0.0), 0.45)
                if self.buzzer:
                    self.buzzer.activated()
                self._event("WAVE ACTIVATED", now)
            elif wave and not face:
                self._event("LOOK AT CAMERA", now)

        elif self.mode == "READY":
            if now > self.ready_until:
                self.mode = "IDLE"
                self.command = ""
                self.votes.clear()
                self._event("TIMEOUT", now)
            elif not face:
                self.command = ""
                self.votes.clear()
                self._event("LOOK AT CAMERA", now, duration=0.7)
            elif self.release_required:
                self.command = "release hand"
                self.votes.clear()
            elif raw_cmd:
                self.votes.append(raw_cmd)
                common, count = Counter(self.votes).most_common(1)[0]
                self.command = common
                if count >= 3 and len(self.votes) >= 4:
                    ir_function = None
                    if self.ir:
                        if common == "POWER_TOGGLE":
                            ir_function = "power_off" if self.ac.power else "power_on"
                        elif common == "TEMP_UP":
                            ir_function = "temp_up"
                        elif common == "TEMP_DOWN":
                            ir_function = "temp_down"

                    if not ir_function or not self.ir or not self.ir.has(ir_function):
                        self.command = ""
                        self.votes.clear()
                        self._event("IR CODE MISSING", now, duration=0.8)
                        ir_last_status = "IR CODE MISSING"
                    else:
                        ok, status = self.ir.send(ir_function)
                        ir_last_function = ir_function
                        ir_last_status = status
                        if ok:
                            action_text = self.ac.execute(common)
                            write_action_log(common, gesture or "NONE", action_text, self.ac.snapshot())
                            if self.led:
                                self.led.pulse(command_led_color(common), 0.75)
                            if self.buzzer:
                                self.buzzer.confirmed()
                            self.mode = "EXECUTE"
                            self.execute_until = now + 0.9
                            self.ready_until = max(self.ready_until, now + 2.2)
                            self.command = common
                            self.release_required = raw_cmd
                            self.votes.clear()
                            self.history.appendleft(
                                {
                                    "time": time.strftime("%H:%M:%S"),
                                    "command": common,
                                    "gesture": gesture or "NONE",
                                    "action": action_text,
                                }
                            )
                            self._event("EXECUTE " + common, now)
                        else:
                            self.command = ""
                            self.votes.clear()
                            self._event(status, now, duration=0.8)
            else:
                self.command = ""
                self.votes.clear()

        return {
            "state": self.mode,
            "command": self.command,
            "event": self.event,
            "ready_remaining": max(0.0, self.ready_until - now) if self.mode in ("READY", "EXECUTE") else 0.0,
            "history": list(self.history),
            "ac": self.ac.snapshot(),
            "last_action": self.ac.last_action,
            "action_count": self.ac.action_count,
            "ir_last_function": ir_last_function,
            "ir_last_status": ir_last_status,
        }


def serial_loop(port, baud):
    global latest
    sm = GestureStateMachine(led_controller, buzzer_controller, ir_controller)
    buf = bytearray()
    ser = None
    last_rx_at = 0.0
    while running:
        try:
            if ser is None or not ser.is_open:
                ser = serial.Serial(port, baudrate=baud, timeout=0.2)
                with state_lock:
                    latest["serial_ok"] = True
                    latest["event"] = "SERIAL OPEN"
            chunk = ser.read(256)
            now = time.time()
            if not chunk:
                age = round(now - last_rx_at, 2) if last_rx_at else None
                data_timeout = bool(age is not None and age > 3.0)
                led_mode = led_controller.update(latest.get("serial_ok", False), latest.get("state", "IDLE"), data_timeout) if led_controller else "DISABLED"
                with state_lock:
                    latest["last_rx_age"] = age
                    latest["data_timeout"] = data_timeout
                    latest["led"] = led_mode
                continue
            buf.extend(chunk)
            while b"\n" in buf:
                raw, _, rest = buf.partition(b"\n")
                buf = bytearray(rest)
                line = raw.decode("utf-8", "replace")
                data = parse_line(line)
                if not data:
                    continue
                face = bool(data.get("face", False))
                wave = bool(data.get("wave", False))
                gesture = data.get("gesture", "NONE")
                control = sm.update(now, face, wave, gesture)
                led_mode = led_controller.update(True, control.get("state", "IDLE")) if led_controller else "DISABLED"
                last_rx_at = now
                with state_lock:
                    latest.update(
                        {
                            "serial_ok": True,
                            "last_rx_age": 0.0,
                            "raw": data.get("raw", line.strip()),
                            "seq": data.get("seq", latest.get("seq")),
                            "face": face,
                            "wave": wave,
                            "gesture": gesture,
                            "k230_fps": data.get("fps", latest.get("k230_fps", 0.0)),
                            "data_timeout": False,
                            "led": led_mode,
                            **control,
                        }
                    )
        except Exception as exc:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            with state_lock:
                latest["serial_ok"] = False
                latest["event"] = "SERIAL ERROR"
                latest["raw"] = repr(exc)
                latest["data_timeout"] = True
                latest["led"] = led_controller.update(False, "IDLE", True) if led_controller else "DISABLED"
            time.sleep(1)


def main():
    global led_controller, buzzer_controller, ir_controller
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
    parser.add_argument("--no-buzzer", action="store_true")
    parser.add_argument("--ir-codes-file", default="captures/ir05t_codes.jsonl")
    parser.add_argument("--ir-port", default="/dev/ttyAMA3")
    parser.add_argument("--ir-baud", type=int, default=9600)
    parser.add_argument("--no-ir", action="store_true")
    args = parser.parse_args()

    led_controller = RgbLed(
        args.led_red_pin,
        args.led_green_pin,
        args.led_blue_pin,
        active_high=not args.led_common_anode,
        enabled=not args.no_led,
    )
    buzzer_controller = ActiveLowBuzzer(args.buzzer_pin, enabled=not args.no_buzzer)
    ir_controller = IRCodeLibrary(args.ir_codes_file, args.ir_port, args.ir_baud, enabled=not args.no_ir)
    with state_lock:
        latest["ir_available"] = ir_controller.available_functions()
        latest["ir_last_status"] = "IR READY" if latest["ir_available"] else "IR CODE FILE EMPTY"

    t = threading.Thread(target=serial_loop, args=(args.serial_port, args.baud), daemon=True)
    t.start()

    httpd = ThreadedHTTPServer((args.host, args.port), Handler)
    print(f"K230 AirGesture control running on http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    finally:
        global running
        running = False
        if led_controller:
            led_controller.close()
        if buzzer_controller:
            buzzer_controller.close()
        httpd.server_close()


if __name__ == "__main__":
    main()
