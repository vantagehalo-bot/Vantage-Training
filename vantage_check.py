#!/usr/bin/env python3
"""
vantage_check.py - hardware check for the Vantage wearable.

Tests each part on its own and prints PASS / FAIL with the likely fix:
  * system  - power (under-voltage), temperature, user groups
  * camera  - the AI Camera is found, delivers a picture, brightness and sharpness
  * ai      - (optional, --ai) the IMX500 runs its object detector and reports objects
  * lidar   - TFmini Plus frames on the serial port, distance, signal strength
  * audio   - espeak-ng, audio player, Bluetooth headset is the output, plays a test phrase

Works over SSH - no desktop needed. Examples:
    python3 vantage_check.py                 # everything except the AI test
    python3 vantage_check.py --ai            # also check object detection (~1 min first time)
    python3 vantage_check.py --only lidar --live   # live distance readout until Ctrl+C
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, List, Tuple

import numpy as np

import vantage_core as vc

try:
    import cv2
except ImportError:
    cv2 = None

GREEN, RED, YELLOW, BOLD, RESET = "\x1b[92m", "\x1b[91m", "\x1b[93m", "\x1b[1m", "\x1b[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = BOLD = RESET = ""

RESULTS: List[Tuple[str, str, str]] = []   # (test, status, detail)


def report(test: str, status: str, detail: str, fix: str = "") -> None:
    colour = {"PASS": GREEN, "FAIL": RED, "WARN": YELLOW}.get(status, "")
    print(f"  {colour}{status:4s}{RESET}  {detail}")
    if fix and status != "PASS":
        for line in fix.splitlines():
            print(f"        -> {line}")
    RESULTS.append((test, status, detail))


def run(cmd: List[str], timeout: float = 5.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def with_timeout(fn: Callable, seconds: float):
    """Run fn in a thread; return (finished, result_or_exception). Never hangs the check."""
    box: dict = {}

    def target():
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        return False, None
    if "error" in box:
        return True, box["error"]
    return True, box.get("result")


# =============================================================================================

def check_system() -> None:
    print(f"\n{BOLD}SYSTEM{RESET}")
    thr = run(["vcgencmd", "get_throttled"])
    if not thr:
        report("power", "WARN", "vcgencmd not available (not a Raspberry Pi?)")
    else:
        val = int(thr.split("=")[-1], 16)
        if val == 0:
            report("power", "PASS", "no under-voltage or throttling since boot")
        else:
            now = "NOW" if val & 0x1 else "earlier since boot"
            report("power", "FAIL", f"under-voltage / throttling detected ({thr}, {now})",
                   "Use the official 27 W USB-C supply (5 V 5 A). Weak power makes the camera crash.")
    temp = run(["vcgencmd", "measure_temp"])
    if temp:
        t = float(temp.split("=")[-1].split("'")[0])
        report("temperature", "PASS" if t < 75 else "WARN", f"CPU {t:.0f} C",
               "Add a heatsink / fan; above ~80 C the board slows down and the camera can drop out.")
    user = pwd.getpwuid(os.getuid()).pw_name
    groups = {g.gr_name for g in grp.getgrall() if user in g.gr_mem}
    try:
        groups.add(grp.getgrgid(os.getgid()).gr_name)
    except KeyError:
        pass
    missing = [g for g in ("dialout", "input", "video") if g not in groups]
    if os.geteuid() == 0:
        report("user", "WARN", "running as root - Bluetooth audio will be silent",
               "Run without sudo.")
    elif missing:
        report("user", "WARN", f"user '{user}' is not in: {', '.join(missing)}",
               f"sudo usermod -aG {','.join(missing)} {user}   (then log out and back in)")
    else:
        report("user", "PASS", f"user '{user}' has serial, input and video access")


def check_camera(save: str) -> None:
    print(f"\n{BOLD}CAMERA{RESET}")
    try:
        from picamera2 import Picamera2
    except ImportError:
        report("camera", "FAIL", "picamera2 is not installed", "sudo apt install -y python3-picamera2")
        return
    ok, info = with_timeout(Picamera2.global_camera_info, 10)
    if not ok or isinstance(info, BaseException) or not info:
        report("camera", "FAIL", "no camera detected",
               "Power off, unplug, re-seat the ribbon cable at both ends (contacts the right way,\n"
               "latch closed), check it is in CAM0, then: rpicam-hello --list-cameras")
        return
    names = ", ".join(f"{i}: {c.get('Model', '?')}" for i, c in enumerate(info))
    has_imx500 = any("imx500" in str(c.get("Model", "")).lower() for c in info)
    report("detect", "PASS" if has_imx500 else "WARN", f"found {names}",
           "" if has_imx500 else "No IMX500 (AI Camera) found - the obstacle detector needs it.")
    num = next((i for i, c in enumerate(info) if "imx500" in str(c.get("Model", "")).lower()), 0)

    def grab():
        cam = Picamera2(num)
        try:
            cam.configure(cam.create_preview_configuration(main={"size": (2028, 1520), "format": "RGB888"}))
            cam.start()
            frames = [cam.capture_array("main") for _ in range(8)]   # let exposure settle
            return frames[-1]
        finally:
            vc.stop_camera_safely(cam, vc.LOG)

    t0 = time.monotonic()
    ok, frame = with_timeout(grab, 25)
    if not ok:
        report("capture", "FAIL", "camera opened but no picture within 25 s (camera not responding)",
               vc.CAMERA_STUCK_MSG.strip())
        return
    if isinstance(frame, BaseException):
        msg = str(frame).splitlines()[0][:100]
        busy = "busy" in msg.lower() or "acquire" in msg.lower()
        report("capture", "FAIL", f"could not capture: {msg}",
               "Another program is using the camera - stop vantage_core.py / vantage_reader.py first."
               if busy else vc.CAMERA_STUCK_MSG.strip())
        return
    gray = frame.mean(axis=2) if frame.ndim == 3 else frame
    report("capture", "PASS", f"{frame.shape[1]}x{frame.shape[0]} picture in {time.monotonic() - t0:.1f} s")
    b = float(gray.mean())
    report("brightness", "PASS" if 40 <= b <= 220 else "WARN", f"average brightness {b:.0f}/255",
           "Too dark: add light or check the lens cap. Too bright: point away from windows/lamps.")
    if cv2 is not None:
        g8 = gray.astype(np.uint8)
        sharp = float(cv2.Laplacian(g8, cv2.CV_64F).var())
        report("sharpness", "PASS" if sharp > 40 else "WARN", f"detail score {sharp:.0f} (higher = sharper)",
               "Blurry: clean the lens; for reading, turn the focus ring so text at ~30 cm is sharp.")
        cv2.imwrite(save, frame)
        print(f"        picture saved to {save} - open it to see what the camera sees")


def check_ai(model: str) -> None:
    print(f"\n{BOLD}AI CAMERA (object detection){RESET}")
    if not os.path.exists(model):
        report("ai", "FAIL", f"model not found: {model}", "sudo apt install -y imx500-all")
        return
    cfg = vc.Config(model=model)
    cam = vc.IMX500Camera(cfg)

    def detect():
        cam.start()
        seen, tensors = set(), 0
        end = time.monotonic() + 8
        while time.monotonic() < end:
            _, dets = cam.read()
            if dets is not None:
                tensors += 1
                seen.update(d.label for d in dets)
        return tensors, seen

    print("        loading the network onto the camera (first time ~1 minute)...")
    ok, res = with_timeout(detect, 120)
    with_timeout(cam.stop, 6)
    if not ok:
        report("ai", "FAIL", "no result within 2 minutes", vc.CAMERA_STUCK_MSG.strip())
    elif isinstance(res, BaseException):
        report("ai", "FAIL", f"error: {str(res).splitlines()[0][:100]}",
               "sudo apt install -y imx500-all python3-picamera2  then reboot")
    else:
        tensors, seen = res
        if tensors == 0:
            report("ai", "FAIL", "camera runs but the detector produced no results",
                   "Reinstall: sudo apt install --reinstall imx500-all, then unplug power 10 s.")
        else:
            objs = ", ".join(sorted(seen)) or "nothing in view (point it at a person, chair, bottle...)"
            report("ai", "PASS", f"{tensors} detection results in 8 s; saw: {objs}")


def check_lidar(port: str, live: bool) -> None:
    print(f"\n{BOLD}LIDAR (TFmini Plus){RESET}")
    try:
        import serial
    except ImportError:
        report("lidar", "FAIL", "pyserial is not installed", "sudo apt install -y python3-serial")
        return
    ports = [port] + [p for p in vc.LidarReader.CANDIDATE_PORTS if p != port]
    present = [p for p in ports if os.path.exists(p)]
    if not present:
        report("port", "FAIL", "no serial port exists",
               "sudo raspi-config -> Interface Options -> Serial Port: login shell NO, hardware YES\n"
               "echo dtparam=uart0=on | sudo tee -a /boot/firmware/config.txt  then reboot")
        return
    found = None
    for p in present:
        try:
            ser = serial.Serial(p, 115200, timeout=0.1)
        except (serial.SerialException, OSError) as exc:
            if "ermission" in str(exc):
                report("port", "FAIL", f"no permission to open {p}", "sudo usermod -aG dialout $USER  then log out/in")
                return
            continue
        parser = vc.TFminiParser()
        frames, t0 = [], time.monotonic()
        while time.monotonic() - t0 < 1.5:
            frames += parser.feed(ser.read(256))
        if frames:
            found = (p, ser, parser, frames, time.monotonic() - t0)
            break
        ser.close()
    if found is None:
        report("frames", "FAIL", f"no TFmini data on {', '.join(present)}",
               "Wiring: TFmini TX -> GPIO15 (pin 10), TFmini RX -> GPIO14 (pin 8), 5 V (pin 2), GND (pin 6).\n"
               "TX/RX must be crossed. The TFmini's LED/laser should glow faintly when powered.\n"
               "Make sure the serial console is disabled and dtparam=uart0=on is set.")
        return
    p, ser, parser, frames, dt = found
    rate = len(frames) / dt
    report("frames", "PASS", f"{len(frames)} frames on {p} ({rate:.0f} Hz), {parser.bad_checksums} bad checksums")
    if p != port:
        print(f"        note: data came from {p}, not {port} - run the programs with --serial {p}")
    dists = [d for d, s, _ in frames if s >= 100 and 0 < d <= 1200]
    strength = int(np.median([s for _, s, _ in frames]))
    temp = frames[-1][2]
    if dists:
        report("distance", "PASS", f"{np.median(dists):.0f} cm (signal strength {strength}, sensor {temp:.0f} C)")
    else:
        report("distance", "WARN", f"frames arrive but no valid distance (strength {strength})",
               "Point it at a wall 0.3-5 m away; black, shiny or glass surfaces give weak returns.")
    if live:
        print("        live distance - wave your hand in front of it (Ctrl+C to stop)")
        try:
            while True:
                fr = parser.feed(ser.read(256))
                if fr:
                    d, s, _ = fr[-1]
                    bar = "#" * int(min(d, 300) / 6)
                    sys.stdout.write(f"\r        {d:5d} cm  str {s:5d}  {bar:<50s}")
                    sys.stdout.flush()
        except KeyboardInterrupt:
            print()
    ser.close()


def check_audio(interactive: bool) -> None:
    print(f"\n{BOLD}AUDIO (Bluetooth bone conduction){RESET}")
    tts = shutil.which("espeak-ng") or shutil.which("espeak")
    if not tts:
        report("tts", "FAIL", "espeak-ng is not installed", "sudo apt install -y espeak-ng")
        return
    report("tts", "PASS", f"speech engine: {os.path.basename(tts)}")
    player = next((p for p in ("paplay", "pw-play", "aplay") if shutil.which(p)), None)
    report("player", "PASS" if player else "WARN", f"audio player: {player or 'none (espeak plays directly)'}",
           "sudo apt install -y pulseaudio-utils")
    if shutil.which("pactl"):
        sinks = run(["pactl", "list", "short", "sinks"])
        bt = [ln.split("\t")[1] for ln in sinks.splitlines() if "bluez" in ln and "\t" in ln]
        default = run(["pactl", "get-default-sink"])
        if bt and default in bt:
            report("bluetooth", "PASS", f"headset is the audio output ({default})")
        elif bt:
            run(["pactl", "set-default-sink", bt[0]])
            report("bluetooth", "PASS", f"headset connected; made it the default output ({bt[0]})")
        else:
            report("bluetooth", "FAIL", f"no Bluetooth headset connected (output is: {default or 'none'})",
                   "Turn the Shokz on. Connect it from the Bluetooth icon, or:\n"
                   "bluetoothctl connect XX:XX:XX:XX:XX:XX   (bluetoothctl devices lists the address)")
    else:
        report("bluetooth", "WARN", "pactl not found, cannot check the output device",
               "sudo apt install -y pulseaudio-utils")
    phrase = "Vantage audio test. If you can hear this, the headset works."
    stop = threading.Event()
    voice = vc.SpeechEngine(vc.Config(), stop)
    voice.start()
    print("        playing a test phrase...")
    voice.say(phrase, vc.Priority.CRITICAL, beep=True, max_age_s=10)
    end = time.monotonic() + 15
    idle_since = None
    while time.monotonic() < end:          # done = silent for 1.5 s (beep -> speech has a gap)
        if voice.busy:
            idle_since = None
        else:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since > 1.5:
                break
        time.sleep(0.1)
    stop.set()
    voice.stop()
    if interactive:
        ans = input("        Did you hear it on the bone-conduction headset? [y/n] ").strip().lower()
        if ans.startswith("y"):
            report("playback", "PASS", "test phrase heard")
        else:
            report("playback", "FAIL", "test phrase not heard",
                   "Check the headset volume and that it is not connected to your phone instead.\n"
                   "Try directly: espeak-ng 'hello'   and   pactl get-default-sink")
    else:
        report("playback", "PASS", "test phrase sent to the speaker (could not ask if you heard it)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Vantage hardware check")
    ap.add_argument("--only", choices=["system", "camera", "ai", "lidar", "audio"], action="append",
                    help="run only these checks (repeatable)")
    ap.add_argument("--ai", action="store_true", help="also check the IMX500 object detector")
    ap.add_argument("--live", action="store_true", help="lidar: show live distance until Ctrl+C")
    ap.add_argument("--serial", default="/dev/serial0")
    ap.add_argument("--model", default=vc.Config().model)
    ap.add_argument("--save", default="check_camera.jpg", help="where to save the test picture")
    ap.add_argument("--yes", action="store_true", help="don't ask questions (for scripts)")
    args = ap.parse_args()
    only = set(args.only or ["system", "camera", "lidar", "audio"] + (["ai"] if args.ai else []))
    interactive = sys.stdin.isatty() and not args.yes

    print(f"{BOLD}Vantage hardware check{RESET}")
    if "system" in only:
        check_system()
    if "camera" in only:
        check_camera(args.save)
    if "ai" in only:
        check_ai(args.model)
    if "lidar" in only:
        check_lidar(args.serial, args.live)
    if "audio" in only:
        check_audio(interactive)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    warns = [r for r in RESULTS if r[1] == "WARN"]
    print(f"\n{BOLD}SUMMARY{RESET}: {len(RESULTS) - len(fails) - len(warns)} passed, "
          f"{len(warns)} warnings, {len(fails)} failed")
    for test, _, detail in fails:
        print(f"  {RED}FAIL{RESET} {test}: {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
