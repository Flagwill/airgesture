"""Gesture-driven control state machine."""

from collections import Counter, deque
import json
import time
from pathlib import Path

from .ac import VirtualAirConditioner
from .protocol import command_from_gesture


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


def write_action_log(log_path, command, gesture, action, ac_state):
    line = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": command,
        "gesture": gesture,
        "action": action,
        "ac": ac_state,
    }
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


class GestureStateMachine:
    def __init__(self, led=None, buzzer=None, ir=None, log_path="airgesture_actions.log"):
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
        self.log_path = log_path

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
                    ir_function = self._ir_function_for(common)
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
                            self._execute_command(common, gesture, raw_cmd, now)
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

    def _ir_function_for(self, command):
        if not self.ir:
            return None
        if command == "POWER_TOGGLE":
            return "power_off" if self.ac.power else "power_on"
        if command == "TEMP_UP":
            return "temp_up"
        if command == "TEMP_DOWN":
            return "temp_down"
        return None

    def _execute_command(self, command, gesture, raw_cmd, now):
        action_text = self.ac.execute(command)
        write_action_log(self.log_path, command, gesture or "NONE", action_text, self.ac.snapshot())
        if self.led:
            self.led.pulse(command_led_color(command), 0.75)
        if self.buzzer:
            self.buzzer.confirmed()
        self.mode = "EXECUTE"
        self.execute_until = now + 0.9
        self.ready_until = max(self.ready_until, now + 2.2)
        self.command = command
        self.release_required = raw_cmd
        self.votes.clear()
        self.history.appendleft(
            {
                "time": time.strftime("%H:%M:%S"),
                "command": command,
                "gesture": gesture or "NONE",
                "action": action_text,
            }
        )
        self._event("EXECUTE " + command, now)
