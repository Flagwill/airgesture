"""Air-conditioner state model used by the gesture state machine."""


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
