"""GPIO-backed LED and buzzer helpers."""

import threading
import time

try:
    from gpiozero import LED, PWMOutputDevice
except Exception:
    LED = None
    PWMOutputDevice = None


class LgpioPwmPin:
    def __init__(self, pin, frequency, active_low=True):
        import lgpio

        self.lgpio = lgpio
        self.pin = pin
        self.frequency = frequency
        self.off_level = 1 if active_low else 0
        self.chip = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.chip, pin, self.off_level)

    def on(self):
        self.lgpio.tx_pwm(self.chip, self.pin, self.frequency, 50)

    def off(self):
        try:
            self.lgpio.tx_pwm(self.chip, self.pin, 0, 0)
        finally:
            self.lgpio.gpio_write(self.chip, self.pin, self.off_level)

    def close(self):
        self.off()
        self.lgpio.gpiochip_close(self.chip)


class PigpioHardwarePwmPin:
    def __init__(self, pin, frequency, active_low=True):
        import pigpio

        self.pigpio = pigpio
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")
        self.pin = pin
        self.frequency = frequency
        self.off_level = 1 if active_low else 0
        self.pi.set_mode(pin, pigpio.OUTPUT)
        self.pi.write(pin, self.off_level)

    def on(self):
        self.pi.hardware_PWM(self.pin, self.frequency, 500000)

    def off(self):
        try:
            self.pi.hardware_PWM(self.pin, 0, 0)
        finally:
            self.pi.write(self.pin, self.off_level)

    def close(self):
        self.off()
        self.pi.stop()


class GpiozeroPwmPin:
    def __init__(self, pin, frequency, active_low=True):
        if PWMOutputDevice is None:
            raise RuntimeError("gpiozero PWMOutputDevice is not available")
        self.device = PWMOutputDevice(pin, active_high=not active_low, initial_value=0.0, frequency=frequency)

    def on(self):
        self.device.value = 0.5

    def off(self):
        self.device.value = 0.0

    def close(self):
        self.off()
        self.device.close()


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
    def __init__(self, pin, enabled=True, frequency=3000, driver="auto"):
        if not 2000 <= frequency <= 5000:
            raise ValueError("buzzer frequency must be between 2000 and 5000 Hz")
        self.enabled = False
        self.pin = None
        self.frequency = frequency
        self.driver = "disabled"
        self._thread = None
        self._stop_event = threading.Event()
        if enabled:
            self._open_pin(pin, frequency, driver)

    def _open_pin(self, pin, frequency, driver):
        drivers = {
            "lgpio": LgpioPwmPin,
            "pigpio": PigpioHardwarePwmPin,
            "gpiozero": GpiozeroPwmPin,
        }
        if driver == "off":
            return
        if driver == "auto":
            candidates = ("lgpio", "pigpio")
        else:
            candidates = (driver,)

        errors = []
        for name in candidates:
            pin_class = drivers.get(name)
            if pin_class is None:
                errors.append(f"{name}: unknown driver")
                continue
            try:
                self.pin = pin_class(pin, frequency, active_low=True)
            except Exception as exc:
                errors.append(f"{name}: {exc!r}")
                continue
            self.enabled = True
            self.driver = name
            return

        if errors:
            print("Buzzer disabled; PWM driver unavailable: " + "; ".join(errors), flush=True)

    def on(self):
        if self.enabled:
            self.pin.on()

    def off(self):
        if self.enabled:
            self.pin.off()

    def pattern(self, items):
        if not self.enabled:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.02)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_pattern, args=(items,), daemon=True)
        self._thread.start()

    def _run_pattern(self, items):
        for active, duration in items:
            if self._stop_event.is_set():
                break
            if active:
                self.on()
            else:
                self.off()
            if self._stop_event.wait(duration):
                break
        self.off()

    def activated(self):
        self.pattern([(True, 0.08), (False, 0.08), (True, 0.08)])

    def confirmed(self):
        self.pattern([(True, 0.35)])

    def canceled(self):
        self.pattern([(True, 0.12)])

    def close(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.1)
        self.off()
        if self.enabled:
            self.pin.close()
