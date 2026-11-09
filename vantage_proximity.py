#!/usr/bin/env python3
"""
vantage_proximity.py - proximity haptics: the closer something is, the harder the
vibration motor buzzes.

Distance comes from the VL53L3CX time-of-flight sensor, read through the example
program of the ned14/VL53L3CX_rasppi driver (`bin/main`), which this script runs in
the background and whose output it parses. The motor is a 3-pin vibration module
(VCC / GND / IN) with IN on a GPIO pin, driven with PWM.

Feel:
  * nothing within --far          -> motor off
  * between --far and --near      -> buzzes in pulses that get stronger and faster
                                     as you get closer (like a parking sensor)
  * closer than --near            -> continuous, full-strength buzz
  * sensor goes quiet / errors    -> motor off (never stuck on)

Set up the driver once:
    sudo apt install -y build-essential git python3-gpiozero python3-lgpio
    git clone https://github.com/ned14/VL53L3CX_rasppi.git ~/VL53L3CX_rasppi
    cd ~/VL53L3CX_rasppi && make && make example

Run:
    python3 vantage_proximity.py                       # motor on GPIO17 (pin 11)
    python3 vantage_proximity.py --near 200 --far 1200 # change the range (mm)
    python3 vantage_proximity.py --mode intensity      # strength only, no pulsing
    python3 vantage_proximity.py --simulate            # no hardware: fake sensor + motor
"""

from __future__ import annotations

import argparse
import collections
import math
import os
import pty
import re
import select
import signal
import subprocess
import sys
import threading
import time
from typing import Deque, List, Optional, Tuple

DEFAULT_TOF_CMD = os.path.expanduser("~/VL53L3CX_rasppi/bin/main")

# VL53LX range status codes: 0 = valid. 3 = "target below minimum range", i.e. something
# is very close but the sensor cannot measure how close: treat it as touching distance.
VALID_STATUSES = {0}
TOO_CLOSE_STATUSES = {3}

COUNT_RE = re.compile(r"Count=\s*(\d+).*?#Objs=\s*(\d+)")
OBJ_RE = re.compile(r"status=\s*(\d+),\s*D=\s*(-?\d+)\s*mm")


# =============================================================================================
# Distance source
# =============================================================================================

class TofReader(threading.Thread):
    """
    Runs the driver's example program and parses its output. Each measurement looks like:

        Count=  226, #Objs=2 status=0, D=  713mm, S=..., Signal=..., Ambient=...
                             status=0, D= 1685mm, S=..., Signal=..., Ambient=...

    The nearest valid object of each measurement becomes the current distance.
    The program runs on a pseudo-terminal so it prints line by line instead of in
    big buffered chunks (which would add delay).
    """

    def __init__(self, cmd: List[str], stop: threading.Event):
        super().__init__(name="tof", daemon=True)
        self.cmd = cmd
        self.stop = stop
        self._lock = threading.Lock()
        self.distance_mm: Optional[float] = None   # None = nothing in range
        self.updated_at = 0.0
        self.frames = 0
        self.rate = 0.0
        self.status = "starting"
        self._proc: Optional[subprocess.Popen] = None

    def latest(self) -> Tuple[Optional[float], float]:
        with self._lock:
            return self.distance_mm, self.updated_at

    def _publish(self, objects: List[Tuple[int, int]]) -> None:
        dists = [0 if st in TOO_CLOSE_STATUSES else d
                 for st, d in objects if st in VALID_STATUSES | TOO_CLOSE_STATUSES and d >= 0]
        now = time.monotonic()
        with self._lock:
            self.distance_mm = float(min(dists)) if dists else None
            if self.updated_at:
                dt = now - self.updated_at
                if dt > 0:
                    self.rate = 0.9 * self.rate + 0.1 * (1.0 / dt) if self.rate else 1.0 / dt
            self.updated_at = now
            self.frames += 1

    def _run_once(self) -> None:
        master, slave = pty.openpty()
        try:
            self._proc = subprocess.Popen(self.cmd, stdout=slave, stderr=subprocess.STDOUT,
                                          stdin=subprocess.DEVNULL, close_fds=True)
        except OSError as exc:
            os.close(master)
            os.close(slave)
            self.status = f"cannot start driver: {exc}"
            return
        os.close(slave)
        self.status = "running"
        buf = b""
        expected = 0
        objects: List[Tuple[int, int]] = []
        try:
            while not self.stop.is_set():
                r, _, _ = select.select([master], [], [], 0.2)
                if not r:
                    if self._proc.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(master, 4096)
                except OSError:          # program exited (pty closed)
                    break
                if not chunk:
                    break
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    line = raw.decode(errors="ignore")
                    m = COUNT_RE.search(line)
                    if m:                                   # start of a new measurement
                        expected, objects = int(m.group(2)), []
                        if expected == 0:
                            self._publish([])
                    o = OBJ_RE.search(line)
                    if o and expected:
                        objects.append((int(o.group(1)), int(o.group(2))))
                        if len(objects) >= expected:
                            self._publish(objects)
                            expected, objects = 0, []
                    elif not m and line.strip() and self.frames == 0:
                        self.status = "driver says: " + line.strip()[:80]
        finally:
            os.close(master)
            self._kill()

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(2)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def run(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            self._run_once()
            if self.stop.is_set():
                break
            if not self.status.startswith(("cannot", "driver says")):
                self.status = "driver stopped - restarting"
            self.stop.wait(backoff)
            backoff = min(backoff * 2, 10.0)
        self._kill()


class SimulatedTof(threading.Thread):
    """Something approaches from 2 m to 5 cm and moves away again, every 12 seconds."""

    def __init__(self, stop: threading.Event):
        super().__init__(name="tof-sim", daemon=True)
        self.stop = stop
        self.distance_mm: Optional[float] = None
        self.updated_at = 0.0
        self.frames = 0
        self.rate = 30.0
        self.status = "simulated"

    def latest(self) -> Tuple[Optional[float], float]:
        return self.distance_mm, self.updated_at

    def run(self) -> None:
        t0 = time.monotonic()
        while not self.stop.wait(1 / 30):
            t = (time.monotonic() - t0) % 12.0
            d = 1025 + 975 * math.cos(2 * math.pi * t / 12.0)       # 50 .. 2000 mm
            self.distance_mm = None if d > 1900 else d
            self.updated_at = time.monotonic()
            self.frames += 1


# =============================================================================================
# Distance -> vibration
# =============================================================================================

def closeness(d: Optional[float], near: float, far: float) -> float:
    """0 = at or beyond `far` (or nothing seen), 1 = at or inside `near`."""
    if d is None or d >= far:
        return 0.0
    if d <= near:
        return 1.0
    return (far - d) / (far - near)


class Haptics(threading.Thread):
    """
    Drives the motor at 100 Hz from the latest closeness value.
      intensity : continuous buzz, strength follows closeness
      pulse     : on/off beats that speed up as things get closer, full strength
      both      : beats that speed up AND get stronger (default, easiest to feel)
    Coin motors don't spin below ~30-40% PWM, so strength is mapped into
    [min_duty, 1.0] once anything is in range.
    """

    def __init__(self, motor, mode: str, min_duty: float, stop: threading.Event):
        super().__init__(name="haptics", daemon=True)
        self.motor = motor
        self.mode = mode
        self.min_duty = min_duty
        self.stop = stop
        self.level = 0.0          # closeness 0..1, set by the main loop
        self.output = 0.0         # what the motor is actually set to (for display)

    def _value(self, now: float) -> float:
        c = self.level
        if c <= 0.0:
            return 0.0
        strength = self.min_duty + (1.0 - self.min_duty) * (c ** 1.5)
        if self.mode == "intensity" or c >= 0.999:
            return strength                         # inside `near`: continuous buzz
        # beats: 1 per second when far, ~8 per second when nearly at `near`
        period = 1.0 / (1.0 + 7.0 * c)
        on = (now % period) < period * 0.5
        if not on:
            return 0.0
        return 1.0 if self.mode == "pulse" else strength

    def run(self) -> None:
        while not self.stop.wait(0.01):
            v = self._value(time.monotonic())
            if abs(v - self.output) > 1e-3:
                self.motor.value = v
                self.output = v
        self.motor.value = 0.0


# =============================================================================================
# Main
# =============================================================================================

def bar(frac: float, width: int = 30) -> str:
    n = int(round(max(0.0, min(1.0, frac)) * width))
    return "#" * n + "." * (width - n)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Vibrate harder the closer something is (VL53L3CX ToF)")
    ap.add_argument("--pin", type=int, default=17, help="GPIO of the motor module's IN pin (GPIO17 = pin 11)")
    ap.add_argument("--near", type=float, default=150.0, help="mm: closer than this = continuous full buzz")
    ap.add_argument("--far", type=float, default=1200.0, help="mm: farther than this = motor off")
    ap.add_argument("--mode", choices=["both", "intensity", "pulse"], default="both")
    ap.add_argument("--min-duty", type=float, default=0.35,
                    help="weakest PWM that still makes your motor spin (0..1)")
    ap.add_argument("--pwm-hz", type=int, default=200, help="PWM frequency for the motor")
    ap.add_argument("--smooth", type=int, default=3, help="median of the last N readings (noise filter)")
    ap.add_argument("--stale", type=float, default=0.5, help="seconds without data before the motor stops")
    ap.add_argument("--tof-cmd", default=DEFAULT_TOF_CMD, help="the driver's example program")
    ap.add_argument("--simulate", action="store_true", help="fake sensor and motor (no hardware)")
    ap.add_argument("--duration", type=float, default=0.0, help="stop after N seconds (0 = run until Ctrl+C)")
    args = ap.parse_args(argv)
    if not 0 <= args.near < args.far:
        ap.error("--near must be smaller than --far")

    try:
        from gpiozero import Device, PWMOutputDevice
    except ImportError:
        print("gpiozero is missing:  sudo apt install -y python3-gpiozero python3-lgpio", file=sys.stderr)
        return 2
    if args.simulate:
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
    elif not os.path.exists(args.tof_cmd):
        print(f"ToF driver program not found: {args.tof_cmd}\n"
              "Build it first:\n"
              "  git clone https://github.com/ned14/VL53L3CX_rasppi.git ~/VL53L3CX_rasppi\n"
              "  cd ~/VL53L3CX_rasppi && make && make example", file=sys.stderr)
        return 2

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    motor = PWMOutputDevice(args.pin, frequency=args.pwm_hz, initial_value=0)
    if args.simulate:
        tof = SimulatedTof(stop)
    else:
        cmd = [args.tof_cmd]
        tof = TofReader(cmd, stop)
    haptics = Haptics(motor, args.mode, args.min_duty, stop)
    tof.start()
    haptics.start()

    recent: Deque[Optional[float]] = collections.deque(maxlen=max(1, args.smooth))
    last_frame = -1
    t_end = time.monotonic() + args.duration if args.duration > 0 else None
    tty = sys.stdout.isatty()
    next_print = 0.0
    print(f"Proximity haptics: motor on GPIO{args.pin}, buzz from {args.far:.0f} mm, "
          f"full at {args.near:.0f} mm, mode {args.mode}. Ctrl+C to stop.")
    try:
        while not stop.is_set():
            if t_end and time.monotonic() > t_end:
                break
            d, at = tof.latest()
            if tof.frames != last_frame:
                last_frame = tof.frames
                recent.append(d)
            fresh = at and time.monotonic() - at < args.stale
            if fresh:
                vals = [v for v in recent if v is not None]
                # nothing seen in most recent readings -> treat as clear
                dist = sorted(vals)[len(vals) // 2] if len(vals) * 2 > len(recent) else None
            else:
                dist = None
            haptics.level = closeness(dist, args.near, args.far) if fresh else 0.0

            dtxt = f"{dist:5.0f} mm" if dist is not None else ("  clear " if fresh else "  -- no data")
            line = (f"distance {dtxt}  motor [{bar(haptics.output)}] {haptics.output * 100:3.0f}%  "
                    f"{tof.rate:4.0f} Hz  {tof.status if not fresh else ''}")
            if tty:
                sys.stdout.write("\r" + line[:110].ljust(110))
                sys.stdout.flush()
            elif time.monotonic() >= next_print:      # logging to a file: twice a second
                next_print = time.monotonic() + 0.5
                print(line, flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        haptics.join(1.0)
        motor.value = 0
        motor.close()
        if isinstance(tof, TofReader):
            tof._kill()
        if tty:
            print()
        print("Stopped - motor off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
