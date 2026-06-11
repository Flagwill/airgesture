"""K230 serial protocol parsing and gesture command mapping."""


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
