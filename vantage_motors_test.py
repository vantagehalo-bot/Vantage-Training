#!/usr/bin/env python3
"""
vantage_motors_test.py - check the 4 vibration motors on their own, before the
combined Vantage code.

Each motor is a 3-pin PWM module (VCC / GND / IN). IN goes to a GPIO pin:

    motor    meaning              GPIO   header pin
    left     obstacle on left     17     11
    right    obstacle on right    27     13
    ahead    obstacle ahead       22     15
    drop     stairs / drop-off    23     16
    VCC -> 5V (pin 2 or 4)    GND -> any GND (pin 6, 9, 14, 20)

Run:
    python3 vantage_motors_test.py              # full test: each motor, ramp, patterns
    python3 vantage_motors_test.py --only left  # one motor
    python3 vantage_motors_test.py --simulate   # no hardware, prints what it would do
"""

from __future__ import annotations

import argparse
import sys
import time

MOTORS = {"left": 17, "right": 27, "ahead": 22, "drop": 23}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=list(MOTORS), help="test just this motor")
    ap.add_argument("--min-duty", type=float, default=0.35, help="weakest PWM that still spins the motor")
    ap.add_argument("--pwm-hz", type=int, default=200)
    ap.add_argument("--simulate", action="store_true", help="no hardware")
    args = ap.parse_args()

    try:
        from gpiozero import Device, PWMOutputDevice
    except ImportError:
        print("gpiozero is missing:  sudo apt install -y python3-gpiozero python3-lgpio", file=sys.stderr)
        return 2
    if args.simulate:
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)

    names = [args.only] if args.only else list(MOTORS)
    motors = {n: PWMOutputDevice(MOTORS[n], frequency=args.pwm_hz, initial_value=0) for n in names}

    def say(msg: str) -> None:
        print(msg, flush=True)

    def buzz(m, strength: float, secs: float) -> None:
        m.value = strength
        time.sleep(secs)
        m.value = 0.0

    try:
        for n, m in motors.items():
            say(f"[1] {n:5s} (GPIO{MOTORS[n]}): 1 s full buzz - you should feel ONLY this one")
            buzz(m, 1.0, 1.0)
            time.sleep(0.6)

        for n, m in motors.items():
            say(f"[2] {n:5s}: strength ramp weak -> strong (find where it starts spinning)")
            for i in range(11):
                v = args.min_duty + (1 - args.min_duty) * i / 10
                m.value = v
                time.sleep(0.25)
            m.value = 0.0
            time.sleep(0.4)

        if not args.only:
            say("[3] patterns Vantage will use:")
            say("    approaching obstacle ahead: pulses get faster")
            for gap in (0.5, 0.35, 0.2, 0.1, 0.05):
                buzz(motors["ahead"], 1.0, 0.08)
                time.sleep(gap)
            time.sleep(0.6)
            say("    obstacle sweeping left -> right")
            for n in ("left", "ahead", "right"):
                buzz(motors[n], 1.0, 0.3)
            time.sleep(0.6)
            say("    STAIRS / DROP-OFF: three strong long pulses")
            for _ in range(3):
                buzz(motors["drop"], 1.0, 0.4)
                time.sleep(0.2)
        say("done - all motors off")
    except KeyboardInterrupt:
        pass
    finally:
        for m in motors.values():
            m.value = 0.0
            m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
