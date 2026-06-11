# AirGesture

AirGesture is a Raspberry Pi side control service for K230 gesture data. The main program reads serial messages from K230, runs a small control state machine, drives LED/buzzer feedback, sends learned IR05T air-conditioner codes, and exposes a web status page.

## Layout

- `airgesture/` - reusable application package.
- `k230_airgesture_control.py` - compatibility entry point for the main service.
- `scripts/` - hardware probes, monitors, capture tools, and diagnostics.
- `captures/` - learned IR codes and captured images.
- `run_env_check.sh` - environment smoke check wrapper.

## Main Service

Run the main program from the project root:

```sh
python k230_airgesture_control.py
```

Equivalent package entry point:

```sh
python -m airgesture
```

Useful options:

```sh
python k230_airgesture_control.py \
  --serial-port /dev/serial0 \
  --baud 115200 \
  --buzzer-frequency 3000 \
  --ir-codes-file captures/ir05t_codes.jsonl \
  --ir-port /dev/ttyAMA3 \
  --port 8081
```

The buzzer output is a 50% duty PWM square wave for passive buzzers without an internal oscillator. Use `--buzzer-frequency` to set 2000-5000 Hz; the default is 3000 Hz.

The web UI is served at `http://<host>:8081/`. Runtime actions are logged to `airgesture_actions.log` by default; override this with `--log-path`.

## Utility Scripts

Run scripts from the project root so relative paths like `captures/ir05t_codes.jsonl` continue to resolve correctly.

```sh
python scripts/ir05t_capture.py --duration 10
python scripts/ir05t_emit.py --index -1
python scripts/pi_k230_receiver.py
python scripts/rgb_led_test.py
python scripts/buzzer_test.py --frequency 3000
./run_env_check.sh
```
