"""GPIO-backed LED and buzzer helpers."""

import threading
import time

try:
    from gpiozero import LED, PWMOutputDevice
except Exception:
    LED = None
    PWMOutputDevice = None


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
    def __init__(self, pin, enabled=True, frequency=3000):
        if not 2000 <= frequency <= 5000:
            raise ValueError("buzzer frequency must be between 2000 and 5000 Hz")
        self.enabled = enabled and PWMOutputDevice is not None
        self.pin = None
        self.frequency = frequency
        if self.enabled:
            self.pin = PWMOutputDevice(pin, active_high=False, initial_value=0.0, frequency=frequency)

    def on(self):
        if self.enabled:
            self.pin.value = 0.5

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
