#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vantage_core.py - Core real-time processing loop for the "Vantage" assistive wearable.

Hardware (prototype):
    * Raspberry Pi Compute Module 5 on a Waveshare carrier board, Raspberry Pi OS (Bookworm)
    * Raspberry Pi AI Camera (Sony IMX500, on-sensor neural network) on CAM0
    * Benewake TFmini Plus single-point LiDAR on the UART (/dev/serial0, 115200 baud)
    * Shokz bone-conduction headset paired over Bluetooth (A2DP sink via PipeWire)

What it does:
    1. Streams frames from the IMX500 and reads the object detections that the sensor's
       on-chip MobileNet-SSD network produces (no CPU inference needed).
    2. Reads the TFmini Plus in a background thread (9-byte 0x59 0x59 frames), validates
       the checksum, filters noise and estimates the closing speed / time-to-contact.
    3. Fuses both: the LiDAR beam is projected into the camera image, so the script knows
       WHICH detected object the distance belongs to ("person", "chair", ...).
    4. Speaks through the Bluetooth bone-conduction headset, e.g.
            "Person too close, 40 centimeters"
       with priorities, pre-emption, cooldowns and hysteresis so it is informative but
       not chatty.
    5. Shows everything live: an annotated preview window (boxes, LiDAR aim point,
       distance bar, alert banner, spoken text), an optional browser stream (MJPEG) for
       headless use, and a terminal dashboard.

Run `python3 vantage_core.py --help` for all options, or `--simulate` to test the whole
pipeline on any computer without the hardware attached.

Stop with Ctrl+C (or `q` / ESC in the preview window); every thread, the serial port,
the camera and the audio processes are shut down cleanly.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import enum
import json
import logging
import logging.handlers
import math
import os
import queue
import random
import re
import shutil
import signal
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from http import server as http_server
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - checked at start-up with a friendly message
    cv2 = None

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover
    serial = None

# picamera2 / IMX500 are only available on the Pi. Import lazily so --simulate works anywhere.
Picamera2 = None
IMX500 = None
NetworkIntrinsics = None


__version__ = "1.0.0"

LOG = logging.getLogger("vantage")


# =============================================================================================
# Labels
# =============================================================================================

# COCO-80 class names. The SSD MobileNetV2 FPN-Lite network shipped in the `imx500-models`
# package is trained on COCO. If the .rpk carries its own label list we use that instead;
# you can also pass --labels path/to/labels.txt (one label per line).
COCO_LABELS: List[str] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]

# Objects that matter most for a walking user. These get a slightly higher alert priority
# and are always announced, even in "quiet" mode.
SAFETY_CRITICAL_LABELS = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck", "train", "dog", "horse",
    "chair", "bench", "couch", "dining table", "bed", "potted plant", "fire hydrant",
    "stop sign", "traffic light", "suitcase", "refrigerator", "toilet",
}

# Friendlier spoken names for some COCO labels.
SPOKEN_NAMES = {
    "tv": "TV",
    "cell phone": "phone",
    "dining table": "table",
    "potted plant": "plant",
    "hair drier": "hair dryer",
    "sports ball": "ball",
}


# =============================================================================================
# Configuration
# =============================================================================================

@dataclasses.dataclass
class Config:
    # --- camera / model ---
    model: str = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
    labels_file: Optional[str] = None
    camera_num: Optional[int] = None          # None = auto (IMX500 finds itself; CAM0 normally 0)
    width: int = 640
    height: int = 480
    fps: Optional[float] = None               # None = model's recommended inference rate
    rotate_180: bool = False
    score_threshold: float = 0.55
    iou_threshold: float = 0.65
    max_detections: int = 10
    cam_hfov_deg: float = 66.3                # IMX500 AI camera: 78.3 deg diagonal -> ~66 deg H
    cam_vfov_deg: float = 52.1

    # --- lidar ---
    serial_port: str = "/dev/serial0"
    baud: int = 115200
    lidar_rate_hz: Optional[int] = None       # e.g. 100 to re-program the TFmini frame rate
    lidar_min_strength: int = 100             # TFmini Plus datasheet: < 100 is unreliable
    lidar_max_range_cm: int = 1200
    lidar_median_window: int = 5
    lidar_stale_s: float = 0.5
    lidar_offset_x_cm: float = 0.0            # LiDAR position relative to camera lens (+ = right)
    lidar_offset_y_cm: float = 0.0            # (+ = below)
    lidar_beam_deg: float = 3.6               # TFmini Plus field of view
    lidar_roi_min_frac: float = 0.06          # minimum aim-box size as a fraction of frame width

    # --- hazard logic ---
    critical_cm: float = 50.0
    warning_cm: float = 100.0
    hysteresis_cm: float = 8.0
    ttc_warning_s: float = 1.5                # time-to-contact that escalates a warning
    vision_close_frac: float = 0.55           # box height/frame height that implies "very close"
    min_track_hits: int = 2                   # frames an object must be seen before it is trusted

    # --- audio ---
    audio_enabled: bool = True
    audio_backend: str = "auto"               # auto | paplay | pw-play | aplay | pygame | espeak
    voice: str = "en-us"
    speech_rate: int = 175
    speech_volume: int = 160                  # espeak amplitude 0..200
    beep: bool = True
    critical_repeat_s: float = 2.5
    warning_repeat_s: float = 6.0
    describe: bool = False                    # also announce newly seen objects + direction
    describe_cooldown_s: float = 12.0
    bt_mac: Optional[str] = None              # auto (re)connect this Bluetooth device

    # --- ui ---
    show_preview: bool = True
    fullscreen: bool = False
    stream_port: int = 0                      # >0 enables http://<pi>:PORT MJPEG preview
    dashboard: bool = True
    dashboard_hz: float = 5.0
    log_file: str = "vantage.log"
    verbose: bool = False

    # --- testing ---
    simulate: bool = False
    simulate_lidar: bool = False
    simulate_camera: bool = False
    duration_s: float = 0.0                   # 0 = run forever


# =============================================================================================
# Small utilities
# =============================================================================================

def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def spoken_label(label: str) -> str:
    return SPOKEN_NAMES.get(label, label)


def spoken_distance(cm: Optional[float]) -> str:
    """Turn a distance into short, natural speech. Quantised so TTS caching works."""
    if cm is None:
        return ""
    if cm < 97.5:  # anything that would round to 100 cm is said as "1 meter"
        return f"{int(round(cm / 5.0) * 5)} centimeters"
    m = round(cm / 10.0) / 10.0
    if abs(m - round(m)) < 1e-6:
        return f"{int(round(m))} meter{'s' if round(m) != 1 else ''}"
    return f"{m:.1f} meters"


def direction_of(cx: float, width: int) -> str:
    rel = cx / max(width, 1)
    if rel < 0.33:
        return "on your left"
    if rel > 0.67:
        return "on your right"
    return "ahead"


class RateMeter:
    """Exponentially smoothed events-per-second counter."""

    def __init__(self, alpha: float = 0.15):
        self.alpha = alpha
        self.rate = 0.0
        self._last: Optional[float] = None

    def tick(self, now: Optional[float] = None) -> float:
        now = time.monotonic() if now is None else now
        if self._last is not None:
            dt = now - self._last
            if dt > 0:
                inst = 1.0 / dt
                self.rate = inst if self.rate == 0 else (1 - self.alpha) * self.rate + self.alpha * inst
        self._last = now
        return self.rate

    def decay(self, now: Optional[float] = None, timeout: float = 2.0) -> None:
        now = time.monotonic() if now is None else now
        if self._last is not None and now - self._last > timeout:
            self.rate = 0.0


class EventLog:
    """Thread-safe ring buffer of recent human-readable events (shown on the dashboard)."""

    def __init__(self, maxlen: int = 8):
        self._items: Deque[str] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with self._lock:
            self._items.append(f"{stamp} {msg}")
        LOG.info(msg)

    def items(self) -> List[str]:
        with self._lock:
            return list(self._items)


EVENTS = EventLog()


# =============================================================================================
# TFmini Plus LiDAR
# =============================================================================================

@dataclasses.dataclass
class LidarSample:
    distance_cm: Optional[float]   # filtered distance, None if the reading is invalid
    raw_cm: int                    # last raw distance from the sensor
    strength: int
    temperature_c: float
    valid: bool
    timestamp: float               # time.monotonic()
    velocity_cm_s: float = 0.0     # negative = getting closer
    ttc_s: Optional[float] = None  # time to contact, if approaching


class TFminiParser:
    """
    Byte-stream parser for the TFmini / TFmini Plus standard 9-byte output frame:

        [0] 0x59  [1] 0x59  [2] Dist_L  [3] Dist_H  [4] Strength_L  [5] Strength_H
        [6] Temp_L  [7] Temp_H  [8] Checksum = low byte of sum(bytes[0..7])

    It is a resynchronising state machine: garbage, partial frames or bad checksums are
    skipped without ever blocking or losing alignment for more than one frame.
    """

    HEADER = 0x59
    FRAME_LEN = 9

    def __init__(self) -> None:
        self._buf = bytearray()
        self.good_frames = 0
        self.bad_checksums = 0

    def feed(self, data: bytes) -> List[Tuple[int, int, float]]:
        self._buf.extend(data)
        out: List[Tuple[int, int, float]] = []
        buf = self._buf
        i = 0
        n = len(buf)
        while n - i >= self.FRAME_LEN:
            if buf[i] != self.HEADER or buf[i + 1] != self.HEADER:
                i += 1
                continue
            frame = buf[i:i + self.FRAME_LEN]
            if (sum(frame[:8]) & 0xFF) != frame[8]:
                self.bad_checksums += 1
                i += 1  # could be a false header inside data, resync one byte later
                continue
            dist, strength, temp_raw = struct.unpack_from("<HHH", frame, 2)
            # TFmini Plus: temperature = raw / 8 - 256 (deg C)
            out.append((dist, strength, temp_raw / 8.0 - 256.0))
            self.good_frames += 1
            i += self.FRAME_LEN
        del buf[:i]
        if len(buf) > 4096:  # never let a noisy line grow memory
            del buf[:-self.FRAME_LEN]
        return out


def tfmini_command(cmd_id: int, payload: bytes = b"") -> bytes:
    """Build a TFmini Plus command frame: 0x5A, len, id, payload..., checksum."""
    body = bytes([0x5A, 4 + len(payload), cmd_id]) + payload
    return body + bytes([sum(body) & 0xFF])


class LidarReader(threading.Thread):
    """
    Background reader for the TFmini Plus. Never blocks the camera loop: the main thread
    just calls `latest()` to grab the newest filtered sample. Automatically reconnects if
    the UART disappears and tries alternative device nodes if /dev/serial0 is missing.
    """

    CANDIDATE_PORTS = ["/dev/serial0", "/dev/ttyAMA0", "/dev/ttyAMA10", "/dev/ttyS0",
                       "/dev/ttyUSB0", "/dev/ttyACM0"]

    def __init__(self, cfg: Config, stop_event: threading.Event):
        super().__init__(name="lidar", daemon=True)
        self.cfg = cfg
        self.stop_event = stop_event
        self._lock = threading.Lock()
        self._latest: Optional[LidarSample] = None
        self._window: Deque[int] = collections.deque(maxlen=max(1, cfg.lidar_median_window))
        self._history: Deque[Tuple[float, float]] = collections.deque(maxlen=40)
        self._ser = None
        self.parser = TFminiParser()
        self.rate = RateMeter(alpha=0.05)
        self.port_in_use: Optional[str] = None
        self.status = "starting"
        self._last_frame_at = 0.0
        self._strict_probe = False   # after a silent port, only accept ports that show frames

    # -- public --------------------------------------------------------------------------

    def latest(self) -> Optional[LidarSample]:
        with self._lock:
            sample = self._latest
        if sample is None:
            return None
        if time.monotonic() - sample.timestamp > self.cfg.lidar_stale_s:
            self.status = "STALE (no frames)"
            return dataclasses.replace(sample, valid=False, distance_cm=None, ttc_s=None)
        return sample

    # -- internals -----------------------------------------------------------------------

    def _open(self) -> bool:
        if serial is None:
            self.status = "pyserial missing"
            return False
        ports = [self.cfg.serial_port] + [p for p in self.CANDIDATE_PORTS if p != self.cfg.serial_port]
        for port in ports:
            if not os.path.exists(port):
                continue
            try:
                ser = serial.Serial(port, self.cfg.baud, timeout=0.05)
                ser.reset_input_buffer()
            except (serial.SerialException, OSError) as exc:
                LOG.debug("cannot open %s: %s", port, exc)
                continue
            # Make sure we actually see TFmini frames on this port before committing to it.
            probe = TFminiParser()
            deadline = time.monotonic() + 0.6
            found = False
            while time.monotonic() < deadline:
                if probe.feed(ser.read(64)):
                    found = True
                    break
            if not found and (self._strict_probe or port != self.cfg.serial_port):
                ser.close()
                continue
            self._ser = ser
            self.port_in_use = port
            self._last_frame_at = time.monotonic()
            self.status = "OK" if found else "port open, waiting for frames"
            EVENTS.add(f"LiDAR on {port} @ {self.cfg.baud} ({'frames OK' if found else 'no frames yet'})")
            if self.cfg.lidar_rate_hz:
                self._set_frame_rate(self.cfg.lidar_rate_hz)
            return True
        if self._strict_probe:
            # Nothing anywhere produced frames: go back to waiting on the configured port.
            self._strict_probe = False
            self.status = "no TFmini frames on any port"
        else:
            self.status = "no serial port"
        return False

    def _set_frame_rate(self, hz: int) -> None:
        try:
            self._ser.write(tfmini_command(0x03, struct.pack("<H", int(hz))))
            self._ser.write(tfmini_command(0x11))  # save settings
            EVENTS.add(f"LiDAR frame rate set to {hz} Hz")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Could not set LiDAR frame rate: %s", exc)

    def _close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
        self._ser = None

    def _process(self, dist: int, strength: int, temp: float) -> None:
        now = time.monotonic()
        self.rate.tick(now)
        valid = (
            strength >= self.cfg.lidar_min_strength
            and strength != 65535            # saturated signal (e.g. retro-reflector)
            and 0 < dist <= self.cfg.lidar_max_range_cm
        )
        filtered: Optional[float] = None
        velocity = 0.0
        ttc: Optional[float] = None
        if valid:
            self._window.append(dist)
            filtered = float(np.median(self._window))
            self._history.append((now, filtered))
            velocity = self._estimate_velocity(now)
            if velocity < -5.0:  # approaching faster than 5 cm/s
                ttc = filtered / -velocity
        else:
            self._window.clear()
            self._history.clear()
        sample = LidarSample(filtered, dist, strength, temp, valid, now, velocity, ttc)
        with self._lock:
            self._latest = sample
        self.status = "OK" if valid else ("weak signal" if strength < self.cfg.lidar_min_strength else "out of range")

    def _estimate_velocity(self, now: float) -> float:
        """Least-squares slope of distance over the last ~0.5 s (cm/s)."""
        pts = [(t, d) for t, d in self._history if now - t <= 0.5]
        if len(pts) < 4:
            return 0.0
        t = np.array([p[0] for p in pts]) - pts[0][0]
        d = np.array([p[1] for p in pts])
        if t[-1] - t[0] < 0.15:
            return 0.0
        slope, _ = np.polyfit(t, d, 1)
        return float(slope)

    def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            if self._ser is None:
                if not self._open():
                    self.stop_event.wait(backoff)
                    backoff = min(backoff * 2, 10.0)
                    continue
                backoff = 1.0
            try:
                data = self._ser.read(self._ser.in_waiting or 9)
            except (OSError, Exception) as exc:  # noqa: BLE001  (SerialException subclasses OSError)
                EVENTS.add(f"LiDAR serial error: {exc} - reconnecting")
                self.status = "reconnecting"
                self._close()
                continue
            if data:
                for frame in self.parser.feed(data):
                    self._last_frame_at = time.monotonic()
                    self._process(*frame)
            elif time.monotonic() - self._last_frame_at > 3.0:
                # Port opens but stays silent: wrong UART, TX/RX swapped, or sensor unpowered.
                EVENTS.add(f"No LiDAR frames on {self.port_in_use} for 3 s - rescanning ports")
                self.status = "silent port - check wiring / UART config"
                self._strict_probe = True
                self._close()
                continue
            self.rate.decay()
        self._close()
        LOG.info("LiDAR thread stopped")


class SimulatedLidar(threading.Thread):
    """Produces a plausible distance profile (walk towards things, back off, repeat)."""

    def __init__(self, cfg: Config, stop_event: threading.Event):
        super().__init__(name="lidar-sim", daemon=True)
        self.cfg = cfg
        self.stop_event = stop_event
        self._lock = threading.Lock()
        self._latest: Optional[LidarSample] = None
        self._history: Deque[Tuple[float, float]] = collections.deque(maxlen=40)
        self.rate = RateMeter(alpha=0.05)
        self.port_in_use = "simulated"
        self.status = "OK (simulated)"
        self.parser = TFminiParser()
        self._t0 = time.monotonic()

    def latest(self) -> Optional[LidarSample]:
        with self._lock:
            return self._latest

    def run(self) -> None:
        while not self.stop_event.is_set():
            now = time.monotonic()
            t = now - self._t0
            # 16 s cycle between ~25 cm and ~260 cm, plus sensor noise
            d = 140 + 115 * math.cos(2 * math.pi * t / 16.0) + random.gauss(0, 1.5)
            d = max(12.0, d)
            self._history.append((now, d))
            pts = [(a, b) for a, b in self._history if now - a <= 0.5]
            vel = 0.0
            if len(pts) >= 4:
                tt = np.array([p[0] for p in pts]) - pts[0][0]
                vel = float(np.polyfit(tt, np.array([p[1] for p in pts]), 1)[0])
            ttc = d / -vel if vel < -5 else None
            sample = LidarSample(d, int(d), 1200, 38.0, True, now, vel, ttc)
            with self._lock:
                self._latest = sample
            self.parser.good_frames += 1
            self.rate.tick(now)
            self.stop_event.wait(0.01)  # 100 Hz


# =============================================================================================
# Detections and tracking
# =============================================================================================

@dataclasses.dataclass
class Detection:
    label: str
    score: float
    box: Tuple[int, int, int, int]  # x, y, w, h in preview pixels


@dataclasses.dataclass
class Track:
    track_id: int
    label: str
    score: float
    box: Tuple[float, float, float, float]
    hits: int = 1
    misses: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    announced_at: float = 0.0

    @property
    def confirmed(self) -> bool:
        return self.hits >= TRACK_MIN_HITS

    @property
    def ibox(self) -> Tuple[int, int, int, int]:
        x, y, w, h = self.box
        return int(x), int(y), int(w), int(h)

    @property
    def center(self) -> Tuple[float, float]:
        x, y, w, h = self.box
        return x + w / 2.0, y + h / 2.0


TRACK_MIN_HITS = 2  # overwritten from Config at start-up


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


class ObjectTracker:
    """
    Very small IoU tracker. The network output flickers from frame to frame; this keeps
    stable identities and smoothed boxes so speech does not stutter ("person... person...").
    """

    def __init__(self, max_misses: int = 6, smoothing: float = 0.5):
        self.tracks: Dict[int, Track] = {}
        self.max_misses = max_misses
        self.alpha = smoothing
        self._next_id = 1

    def update(self, detections: List[Detection], now: float) -> List[Track]:
        unmatched = set(self.tracks.keys())
        # Greedy matching: best IoU pairs first, same label only.
        pairs = []
        for di, det in enumerate(detections):
            for tid, trk in self.tracks.items():
                if trk.label != det.label:
                    continue
                score = iou(det.box, trk.box)
                if score > 0.2:
                    pairs.append((score, di, tid))
        pairs.sort(reverse=True)
        used_det, used_trk = set(), set()
        for _, di, tid in pairs:
            if di in used_det or tid in used_trk:
                continue
            used_det.add(di)
            used_trk.add(tid)
            det, trk = detections[di], self.tracks[tid]
            a = self.alpha
            trk.box = tuple(a * n + (1 - a) * o for n, o in zip(det.box, trk.box))  # type: ignore[assignment]
            trk.score = a * det.score + (1 - a) * trk.score
            trk.hits += 1
            trk.misses = 0
            trk.last_seen = now
            unmatched.discard(tid)
        for di, det in enumerate(detections):
            if di in used_det:
                continue
            tid = self._next_id
            self._next_id += 1
            self.tracks[tid] = Track(tid, det.label, det.score, tuple(map(float, det.box)),  # type: ignore[arg-type]
                                     first_seen=now, last_seen=now)
        for tid in list(unmatched):
            trk = self.tracks[tid]
            trk.misses += 1
            if trk.misses > self.max_misses:
                del self.tracks[tid]
        return self.confirmed()

    def confirmed(self) -> List[Track]:
        return [t for t in self.tracks.values() if t.confirmed]


# =============================================================================================
# Cameras
# =============================================================================================

class CameraBase:
    name = "camera"
    status = "init"
    model_name = "-"
    frame_size = (640, 480)

    def start(self) -> None: ...

    def read(self) -> Tuple[Optional[np.ndarray], Optional[List[Detection]]]:
        """Return (BGR frame, detections). detections is None when no new inference
        result arrived with this frame (keep the previous ones)."""
        raise NotImplementedError

    def stop(self) -> None: ...


CAMERA_STUCK_MSG = """
The camera stopped sending pictures (look for "Remote I/O error" above). This is the camera
hardware/driver, not this program. To recover:
  1. Shut down (sudo shutdown now), UNPLUG the power for 10 seconds, then power on.
     The camera only resets when it loses power - a normal restart is often not enough.
  2. Re-seat the camera ribbon cable at both ends (contacts facing the right way, latch closed).
  3. Test the camera on its own:  rpicam-hello -t 5s
  4. If it keeps happening: check power with  vcgencmd get_throttled  (should print 0x0)
     and the temperature with  vcgencmd measure_temp , and try running with --fast-sensor.
"""


def stop_camera_safely(picam2, log: logging.Logger) -> None:
    """picam2.stop() waits forever on a camera that stopped responding; never hang on exit."""
    def _close():
        for fn in (picam2.stop, picam2.close):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass
    t = threading.Thread(target=_close, name="camera-close", daemon=True)
    t.start()
    t.join(4.0)
    if t.is_alive():
        log.warning("The camera did not stop cleanly (not responding). Unplug the power for 10 s before the next run.")


class IMX500Camera(CameraBase):
    """Raspberry Pi AI Camera. Detection runs on the sensor; we only post-process outputs."""

    name = "IMX500 AI Camera"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.picam2 = None
        self.imx500 = None
        self.intrinsics = None
        self.labels: List[str] = []
        self.frame_size = (cfg.width, cfg.height)
        self.model_name = os.path.basename(cfg.model)

    def start(self) -> None:
        global Picamera2, IMX500, NetworkIntrinsics
        try:
            from picamera2 import Picamera2 as _P
            from picamera2.devices import IMX500 as _I
            from picamera2.devices.imx500 import NetworkIntrinsics as _N
        except ImportError as exc:
            raise RuntimeError(
                "picamera2 with IMX500 support is not installed.\n"
                "  sudo apt install imx500-all python3-picamera2\n"
                "(and if you use a venv, create it with --system-site-packages)") from exc
        Picamera2, IMX500, NetworkIntrinsics = _P, _I, _N

        if not os.path.exists(self.cfg.model):
            raise RuntimeError(f"Model not found: {self.cfg.model}\n  sudo apt install imx500-all")

        self.status = "loading network firmware"
        # IMX500() must be created BEFORE Picamera2(): it locates the AI camera and
        # prepares the network firmware upload.
        self.imx500 = IMX500(self.cfg.model)
        intr = self.imx500.network_intrinsics
        if not intr:
            intr = NetworkIntrinsics()
            intr.task = "object detection"
        elif getattr(intr, "task", "object detection") != "object detection":
            raise RuntimeError(f"Model task is '{intr.task}', expected 'object detection'")

        # Labels: --labels file > labels embedded in the .rpk > COCO-80 fallback
        if self.cfg.labels_file:
            with open(self.cfg.labels_file, "r", encoding="utf-8") as fh:
                intr.labels = [ln.strip() for ln in fh.read().splitlines()]
        elif getattr(intr, "labels", None) is None:
            intr.labels = list(COCO_LABELS)
        if hasattr(intr, "update_with_defaults"):
            intr.update_with_defaults()
        self.intrinsics = intr
        labels = list(intr.labels or COCO_LABELS)
        if getattr(intr, "ignore_dash_labels", False):
            labels = [lb for lb in labels if lb and lb != "-"]
        self.labels = labels

        cam_num = self.cfg.camera_num if self.cfg.camera_num is not None else self.imx500.camera_num
        self.picam2 = Picamera2(cam_num)
        fps = self.cfg.fps or getattr(intr, "inference_rate", None) or 30
        config = self.picam2.create_preview_configuration(
            main={"size": (self.cfg.width, self.cfg.height), "format": "RGB888"},  # BGR in memory
            controls={"FrameRate": float(fps)},
            buffer_count=12,
        )
        EVENTS.add(f"Uploading network '{self.model_name}' to IMX500 (first run can take ~1 min)")
        try:
            self.imx500.show_network_fw_progress_bar()
        except Exception:  # noqa: BLE001 - cosmetic only
            pass
        self.picam2.start(config, show_preview=False)
        if getattr(intr, "preserve_aspect_ratio", False):
            self.imx500.set_auto_aspect_ratio()
        self.status = f"running @{fps:g} fps target"
        EVENTS.add(f"Camera {cam_num} started {self.cfg.width}x{self.cfg.height}, {len(self.labels)} labels")

    def _label(self, idx: int) -> str:
        return self.labels[idx] if 0 <= idx < len(self.labels) else f"class {idx}"

    def _parse(self, metadata: dict) -> Optional[List[Detection]]:
        np_outputs = self.imx500.get_outputs(metadata, add_batch=True)
        if np_outputs is None:
            return None  # no new tensor attached to this frame
        intr = self.intrinsics
        input_w, input_h = self.imx500.get_input_size()
        thr = self.cfg.score_threshold

        if getattr(intr, "postprocess", "") == "nanodet":
            from picamera2.devices.imx500 import postprocess_nanodet_detection
            from picamera2.devices.imx500.postprocess import scale_boxes
            boxes, scores, classes = postprocess_nanodet_detection(
                outputs=np_outputs[0], conf=thr, iou_thres=self.cfg.iou_threshold,
                max_out_dets=self.cfg.max_detections)[0]
            boxes = scale_boxes(boxes, 1, 1, input_h, input_w, False, False)
        else:
            # Standard SSD post-processed output: boxes, scores, classes
            boxes, scores, classes = np_outputs[0][0], np_outputs[1][0], np_outputs[2][0]
            if getattr(intr, "bbox_normalization", False):
                boxes = boxes / input_h
            if getattr(intr, "bbox_order", "yx") == "xy":
                boxes = boxes[:, [1, 0, 3, 2]]

        dets: List[Detection] = []
        for box, score, cls in zip(boxes, scores, classes):
            if float(score) < thr:
                continue
            # converts (y0, x0, y1, x1) inference coords -> (x, y, w, h) in the main stream
            x, y, w, h = self.imx500.convert_inference_coords(tuple(box), metadata, self.picam2)
            dets.append(Detection(self._label(int(cls)), float(score), (int(x), int(y), int(w), int(h))))
            if len(dets) >= self.cfg.max_detections:
                break
        return dets

    def read(self) -> Tuple[Optional[np.ndarray], Optional[List[Detection]]]:
        request = self.picam2.capture_request()
        try:
            frame = request.make_array("main")
            metadata = request.get_metadata()
        finally:
            request.release()
        dets = self._parse(metadata)
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        if self.cfg.rotate_180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
            if dets:
                W, H = self.cfg.width, self.cfg.height
                for d in dets:
                    x, y, w, h = d.box
                    d.box = (W - x - w, H - y - h, w, h)
        return frame, dets

    def stop(self) -> None:
        if self.picam2 is not None:
            cam, self.picam2 = self.picam2, None
            stop_camera_safely(cam, LOG)
        self.status = "stopped"


class SimulatedCamera(CameraBase):
    """Synthetic scene with labelled objects drifting through the field of view."""

    name = "Simulated camera"
    model_name = "simulation"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.frame_size = (cfg.width, cfg.height)
        self._t0 = time.monotonic()
        self._next = 0.0
        W, H = self.frame_size
        yy, xx = np.mgrid[0:H, 0:W]
        base = np.zeros((H, W, 3), np.uint8)
        base[..., 0] = (40 + 60 * yy / H).astype(np.uint8)
        base[..., 1] = (35 + 40 * xx / W).astype(np.uint8)
        base[..., 2] = 30
        self._bg = base

    def start(self) -> None:
        self.status = "running (simulated)"

    def read(self) -> Tuple[Optional[np.ndarray], Optional[List[Detection]]]:
        # pace to ~30 fps
        now = time.monotonic()
        if self._next > now:
            time.sleep(self._next - now)
        self._next = max(now, self._next) + 1 / 30.0
        t = time.monotonic() - self._t0
        W, H = self.frame_size
        frame = self._bg.copy()
        dets: List[Detection] = []
        # A "person" that grows as the simulated LiDAR distance shrinks (same 16 s cycle)
        dist = 140 + 115 * math.cos(2 * math.pi * t / 16.0)
        scale = clamp(120.0 / max(dist, 20), 0.35, 2.4)
        pw, ph = int(110 * scale), int(min(H * 0.95, 240 * scale))
        px = int(W / 2 - pw / 2 + 60 * math.sin(t / 3.0))
        py = int(H / 2 - ph / 2)
        dets.append(Detection("person", 0.86 + 0.05 * math.sin(t), (px, py, pw, ph)))
        # A chair wandering on the left, a cup on the right
        cx = int(W * 0.12 + 40 * math.sin(t / 2.0))
        dets.append(Detection("chair", 0.71, (cx, int(H * 0.55), 90, 110)))
        if int(t) % 10 < 6:
            dets.append(Detection("cup", 0.62, (int(W * 0.8), int(H * 0.6), 40, 50)))
        for d in dets:
            x, y, w, h = d.box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (90, 90, 90), -1)
            cv2.putText(frame, d.label, (x + 4, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        noise = np.random.randint(0, 12, frame.shape, np.uint8)
        frame = cv2.add(frame, noise)
        # IMX500 delivers a new tensor roughly every frame, simulate occasional misses
        return frame, (dets if random.random() > 0.1 else None)


# =============================================================================================
# Sensor fusion / hazard assessment
# =============================================================================================

class Level(enum.IntEnum):
    CLEAR = 0
    CAUTION = 1    # something in the warning band
    CRITICAL = 2   # something closer than the critical threshold
    UNKNOWN = -1   # no usable LiDAR data and nothing obvious from vision


@dataclasses.dataclass
class Hazard:
    level: Level
    distance_cm: Optional[float]
    target: Optional[Track]
    source: str                    # "lidar+camera", "lidar", "vision"
    aim_box: Tuple[int, int, int, int]
    ttc_s: Optional[float] = None
    message: str = ""

    @property
    def target_label(self) -> Optional[str]:
        return self.target.label if self.target else None


class HazardAssessor:
    """
    Decides what is in front of the user and how dangerous it is.

    The TFmini beam is ~3.6 deg wide and mounted next to the camera, so it hits a small
    patch of the image. We project that patch (including parallax from the mounting
    offset) into pixel coordinates and pick the detected object that covers it - that is
    the object the distance belongs to.
    """

    def __init__(self, cfg: Config, frame_size: Tuple[int, int]):
        self.cfg = cfg
        self.W, self.H = frame_size
        self.fx = (self.W / 2.0) / math.tan(math.radians(cfg.cam_hfov_deg / 2.0))
        self.fy = (self.H / 2.0) / math.tan(math.radians(cfg.cam_vfov_deg / 2.0))
        self.level = Level.CLEAR

    def aim_box(self, distance_cm: Optional[float]) -> Tuple[int, int, int, int]:
        d = distance_cm if distance_cm and distance_cm > 1 else 200.0
        cx = self.W / 2.0 + self.fx * self.cfg.lidar_offset_x_cm / d
        cy = self.H / 2.0 + self.fy * self.cfg.lidar_offset_y_cm / d
        half = self.fx * math.tan(math.radians(self.cfg.lidar_beam_deg / 2.0))
        half = max(half, self.cfg.lidar_roi_min_frac * self.W / 2.0)
        x0 = int(clamp(cx - half, 0, self.W - 1))
        y0 = int(clamp(cy - half, 0, self.H - 1))
        x1 = int(clamp(cx + half, 0, self.W - 1))
        y1 = int(clamp(cy + half, 0, self.H - 1))
        return x0, y0, max(1, x1 - x0), max(1, y1 - y0)

    @staticmethod
    def _overlap_frac(aim: Tuple[int, int, int, int], box: Sequence[float]) -> float:
        ax, ay, aw, ah = aim
        bx, by, bw, bh = box
        ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
        return (ix * iy) / float(aw * ah)

    def _classify(self, d: float) -> Level:
        c, w, hy = self.cfg.critical_cm, self.cfg.warning_cm, self.cfg.hysteresis_cm
        # Hysteresis: once in a level, you have to move clearly out of it to leave.
        if self.level == Level.CRITICAL:
            if d < c + hy:
                return Level.CRITICAL
        if d < c:
            return Level.CRITICAL
        if self.level >= Level.CAUTION and d < w + hy:
            return Level.CAUTION
        if d < w:
            return Level.CAUTION
        return Level.CLEAR

    def assess(self, lidar: Optional[LidarSample], tracks: List[Track]) -> Hazard:
        dist = lidar.distance_cm if (lidar and lidar.valid) else None
        aim = self.aim_box(dist)

        # Which tracked object is the LiDAR looking at?
        target = None
        best = 0.0
        for trk in tracks:
            ov = self._overlap_frac(aim, trk.box)
            if ov <= 0.25:
                continue
            # prefer confident, safety-relevant objects that cover the beam well
            rank = ov * trk.score * (1.2 if trk.label in SAFETY_CRITICAL_LABELS else 1.0)
            if rank > best:
                best, target = rank, trk

        if dist is not None:
            level = self._classify(dist)
            ttc = lidar.ttc_s if lidar else None
            if level == Level.CLEAR and ttc is not None and ttc < self.cfg.ttc_warning_s \
                    and dist < self.cfg.warning_cm * 2:
                level = Level.CAUTION  # approaching quickly, warn early
            self.level = level
            src = "lidar+camera" if target else "lidar"
            return Hazard(level, dist, target, src, aim, ttc)

        # LiDAR unavailable (too close <10 cm, weak return, stale): fall back on vision.
        # A box filling most of the frame height means the object is very near.
        close = [t for t in tracks if t.box[3] / self.H >= self.cfg.vision_close_frac]
        if close:
            near = max(close, key=lambda t: t.box[3] * t.box[2])
            self.level = Level.CRITICAL if near.box[3] / self.H > 0.8 else Level.CAUTION
            return Hazard(self.level, None, near, "vision", aim)
        self.level = Level.UNKNOWN if lidar is None or not lidar.valid else Level.CLEAR
        return Hazard(self.level, None, None, "none", aim)


# =============================================================================================
# Audio: text-to-speech on the Bluetooth bone-conduction headset
# =============================================================================================

class Priority(enum.IntEnum):
    CRITICAL = 0
    WARNING = 1
    INFO = 2


@dataclasses.dataclass(order=True)
class Utterance:
    priority: int
    seq: int
    text: str = dataclasses.field(compare=False)
    created: float = dataclasses.field(compare=False, default=0.0)
    beep: bool = dataclasses.field(compare=False, default=False)
    max_age_s: float = dataclasses.field(compare=False, default=2.0)


class SpeechEngine(threading.Thread):
    """
    Priority speech queue.

    * espeak-ng renders text to WAV (cached, so repeated phrases start instantly).
    * The WAV is played with paplay / pw-play (PipeWire -> default sink -> Bluetooth
      headset), aplay, or pygame.mixer - whatever is available.
    * A CRITICAL message interrupts anything less important that is currently playing.
    * Stale messages are dropped: a distance that was true 2 s ago is not useful.
    """

    PLAYERS = ["paplay", "pw-play", "aplay"]

    def __init__(self, cfg: Config, stop_event: threading.Event):
        super().__init__(name="speech", daemon=True)
        self.cfg = cfg
        self.stop_event = stop_event
        self.q: "queue.PriorityQueue[Utterance]" = queue.PriorityQueue()
        self._seq = 0
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._playing_priority: Optional[int] = None
        self._tmp = tempfile.mkdtemp(prefix="vantage_tts_")
        self._cache: "collections.OrderedDict[str, str]" = collections.OrderedDict()
        self.muted = not cfg.audio_enabled
        self.last_spoken = ""
        self.last_spoken_at = 0.0
        self.tts = shutil.which("espeak-ng") or shutil.which("espeak")
        self.backend = self._pick_backend()
        self._pygame = None
        if self.backend == "pygame":
            self._init_pygame()
        self._beep_path = os.path.join(self._tmp, "beep.wav")
        self._write_beep(self._beep_path)

    # -- setup ---------------------------------------------------------------------------

    def _pick_backend(self) -> str:
        want = self.cfg.audio_backend
        if want != "auto":
            return want
        for p in self.PLAYERS:
            if shutil.which(p):
                return p
        try:
            import pygame  # noqa: F401
            return "pygame"
        except ImportError:
            pass
        return "espeak" if self.tts else "none"

    def _init_pygame(self) -> None:
        try:
            import pygame
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self._pygame = pygame
        except Exception as exc:  # noqa: BLE001
            EVENTS.add(f"pygame mixer failed ({exc}); falling back to espeak direct")
            self.backend = "espeak"

    @staticmethod
    def _write_beep(path: str, sr: int = 22050) -> None:
        """Two short rising tones - distinct from speech, easy to feel on bone conduction."""
        parts = []
        for f, dur in ((880, 0.09), (0, 0.04), (1320, 0.12)):
            t = np.arange(int(sr * dur)) / sr
            tone = np.sin(2 * np.pi * f * t) if f else np.zeros_like(t)
            env = np.minimum(1, np.minimum(t, t[::-1]) / 0.01) if len(t) else t
            parts.append(tone * env)
        # 150 ms of silence first: Bluetooth sinks often clip the first ~100 ms after idle
        audio = np.concatenate([np.zeros(int(sr * 0.15))] + parts)
        pcm = (audio * 0.8 * 32767).astype("<i2")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())

    # -- public API ----------------------------------------------------------------------

    def say(self, text: str, priority: Priority = Priority.INFO, beep: bool = False,
            max_age_s: float = 2.0) -> None:
        if self.muted or self.backend == "none":
            return
        with self._lock:
            self._seq += 1
            utt = Utterance(int(priority), self._seq, text, time.monotonic(), beep, max_age_s)
            # Pre-empt anything less important that is currently playing.
            if self._proc is not None and self._playing_priority is not None \
                    and priority < self._playing_priority:
                self._kill_current()
        if priority == Priority.CRITICAL:
            self._drain_below(Priority.CRITICAL)
        self.q.put(utt)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted:
            with self._lock:
                self._kill_current()
            self._drain_below(-1)
        return self.muted

    @property
    def busy(self) -> bool:
        return self._proc is not None or not self.q.empty()

    def stop(self) -> None:
        with self._lock:
            self._kill_current()
        self.q.put(Utterance(99, 1 << 30, "__quit__"))

    # -- internals -----------------------------------------------------------------------

    def _drain_below(self, prio: int) -> None:
        """Remove queued items whose priority is less urgent than `prio`."""
        keep = []
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            if item.priority <= prio:
                keep.append(item)
        for item in keep:
            self.q.put(item)

    def _kill_current(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        if self._pygame is not None:
            try:
                self._pygame.mixer.stop()
            except Exception:  # noqa: BLE001
                pass

    def _synth(self, text: str) -> Optional[str]:
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        if not self.tts:
            return None
        path = os.path.join(self._tmp, f"utt_{len(self._cache)}_{abs(hash(text)) % 10**8}.wav")
        cmd = [self.tts, "-v", self.cfg.voice, "-s", str(self.cfg.speech_rate),
               "-a", str(self.cfg.speech_volume), "-w", path, text]
        try:
            subprocess.run(cmd, check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("TTS failed for %r: %s", text, exc)
            return None
        self._cache[text] = path
        if len(self._cache) > 64:
            _, old = self._cache.popitem(last=False)
            try:
                os.remove(old)
            except OSError:
                pass
        return path

    def _play(self, path: str, priority: int) -> None:
        if self.backend == "pygame" and self._pygame is not None:
            snd = self._pygame.mixer.Sound(path)
            ch = snd.play()
            while ch is not None and ch.get_busy() and not self.stop_event.is_set():
                time.sleep(0.02)
            return
        if self.backend == "paplay":
            cmd = ["paplay", path]
        elif self.backend == "pw-play":
            cmd = ["pw-play", path]
        else:
            cmd = ["aplay", "-q", path]
        with self._lock:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._playing_priority = priority
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        finally:
            with self._lock:
                self._proc = None
                self._playing_priority = None

    def _speak_direct(self, text: str, priority: int) -> None:
        """Fallback: let espeak play by itself (uses the default PulseAudio/PipeWire sink)."""
        if not self.tts:
            return
        cmd = [self.tts, "-v", self.cfg.voice, "-s", str(self.cfg.speech_rate),
               "-a", str(self.cfg.speech_volume), text]
        with self._lock:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._playing_priority = priority
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        finally:
            with self._lock:
                self._proc = None
                self._playing_priority = None

    def run(self) -> None:
        EVENTS.add(f"Speech: tts={os.path.basename(self.tts) if self.tts else 'NONE'} player={self.backend}")
        while not self.stop_event.is_set():
            try:
                utt = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            if utt.text == "__quit__":
                break
            if self.muted or time.monotonic() - utt.created > utt.max_age_s:
                continue  # too old to be true any more
            self.last_spoken = utt.text
            self.last_spoken_at = time.monotonic()
            LOG.info("SAY[%s]: %s", Priority(utt.priority).name, utt.text)
            try:
                if self.backend == "espeak":
                    self._speak_direct(utt.text, utt.priority)
                    continue
                if utt.beep and self.cfg.beep:
                    self._play(self._beep_path, utt.priority)
                path = self._synth(utt.text)
                if path:
                    self._play(path, utt.priority)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("audio playback failed: %s", exc)
        shutil.rmtree(self._tmp, ignore_errors=True)
        LOG.info("Speech thread stopped")


class BluetoothMonitor(threading.Thread):
    """
    Watches the PipeWire/PulseAudio default sink so the dashboard can tell you whether
    audio is really going to the Shokz headset. Optionally (re)connects it by MAC and
    makes it the default sink.
    """

    def __init__(self, cfg: Config, stop_event: threading.Event):
        super().__init__(name="bluetooth", daemon=True)
        self.cfg = cfg
        self.stop_event = stop_event
        self.sink = "unknown"
        self.is_bluetooth = False
        self.device_name = ""
        self._has_pactl = shutil.which("pactl") is not None
        self._has_btctl = shutil.which("bluetoothctl") is not None
        self._was_bt: Optional[bool] = None

    @staticmethod
    def _run(cmd: List[str], timeout: float = 4.0) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    def _poll(self) -> None:
        if not self._has_pactl:
            self.sink = "pactl not found"
            return
        sinks = self._run(["pactl", "list", "short", "sinks"])
        bt_sinks = [ln.split("\t")[1] for ln in sinks.splitlines() if "bluez" in ln and "\t" in ln]
        default = self._run(["pactl", "get-default-sink"])
        if bt_sinks and default not in bt_sinks:
            # Headset is connected but not the default output: route audio to it.
            self._run(["pactl", "set-default-sink", bt_sinks[0]])
            EVENTS.add(f"Default audio sink -> {bt_sinks[0]}")
            default = bt_sinks[0]
        self.sink = default or "none"
        self.is_bluetooth = "bluez" in self.sink
        if self.is_bluetooth and self._has_btctl and self.cfg.bt_mac:
            info = self._run(["bluetoothctl", "info", self.cfg.bt_mac])
            m = re.search(r"Name:\s*(.+)", info)
            self.device_name = m.group(1).strip() if m else ""
        if self._was_bt is not None and self._was_bt != self.is_bluetooth:
            EVENTS.add("Bluetooth headset CONNECTED" if self.is_bluetooth else "Bluetooth headset LOST")
        self._was_bt = self.is_bluetooth

    def _reconnect(self) -> None:
        if not (self.cfg.bt_mac and self._has_btctl) or self.is_bluetooth:
            return
        EVENTS.add(f"Connecting Bluetooth {self.cfg.bt_mac} ...")
        self._run(["bluetoothctl", "connect", self.cfg.bt_mac], timeout=12)

    def run(self) -> None:
        last_reconnect = 0.0
        while not self.stop_event.is_set():
            self._poll()
            now = time.monotonic()
            if not self.is_bluetooth and now - last_reconnect > 20:
                last_reconnect = now
                self._reconnect()
            self.stop_event.wait(5.0)


# =============================================================================================
# Announcement policy (what to say, and when)
# =============================================================================================

class Announcer:
    """
    Turns hazard assessments into speech, following these rules:

      CRITICAL (< critical_cm):  beep + "<object> too close, <distance>"   pre-empts all,
                                 repeats every critical_repeat_s while it lasts, and
                                 immediately if the object changes.
      CAUTION  (< warning_cm or fast approach):  "<object> ahead, <distance>"
                                 repeats every warning_repeat_s.
      describe mode: newly confirmed objects "<object> on your left/right/ahead".
    """

    def __init__(self, cfg: Config, speech: Optional[SpeechEngine], frame_w: int):
        self.cfg = cfg
        self.speech = speech
        self.frame_w = frame_w
        self._last_level = Level.CLEAR
        self._last_label: Optional[str] = None
        self._last_said = 0.0
        self._described: Dict[str, float] = {}
        self.banner = ""

    def phrase(self, hz: Hazard) -> str:
        name = spoken_label(hz.target_label) if hz.target_label else "obstacle"
        dist = spoken_distance(hz.distance_cm)
        if hz.level == Level.CRITICAL:
            text = f"{name} too close"
            if dist:
                text += f", {dist}"
            elif hz.source == "vision":
                text = f"{name} very close"
        else:
            text = f"{name} ahead"
            if dist:
                text += f", {dist}"
            if hz.ttc_s is not None and hz.ttc_s < self.cfg.ttc_warning_s:
                text += ", approaching fast"
        return text[0].upper() + text[1:]

    def update(self, hz: Hazard, tracks: List[Track], now: float) -> None:
        label = hz.target_label
        if hz.level >= Level.CAUTION:
            hz.message = self.phrase(hz)
        self.banner = hz.message

        if hz.level == Level.CRITICAL:
            changed = self._last_level != Level.CRITICAL or label != self._last_label
            if changed or now - self._last_said >= self.cfg.critical_repeat_s:
                self._say(hz.message, Priority.CRITICAL, beep=changed, max_age=1.0)
                self._last_said = now
                if changed:
                    EVENTS.add(f"ALERT {hz.message}")
        elif hz.level == Level.CAUTION:
            escalated = self._last_level < Level.CAUTION or label != self._last_label
            if escalated or now - self._last_said >= self.cfg.warning_repeat_s:
                self._say(hz.message, Priority.WARNING, max_age=1.5)
                self._last_said = now
        elif self._last_level == Level.CRITICAL and hz.level == Level.CLEAR:
            self._say("Clear", Priority.INFO, max_age=1.0)

        if self.cfg.describe and hz.level < Level.CAUTION:
            for trk in tracks:
                if now - self._described.get(trk.label, -1e9) < self.cfg.describe_cooldown_s:
                    continue
                if trk.hits < max(TRACK_MIN_HITS, 4):
                    continue
                self._described[trk.label] = now
                cx, _ = trk.center
                self._say(f"{spoken_label(trk.label)} {direction_of(cx, self.frame_w)}",
                          Priority.INFO, max_age=2.5)
                break  # one description per frame, keep it calm

        self._last_level = hz.level
        self._last_label = label

    def _say(self, text: str, prio: Priority, beep: bool = False, max_age: float = 2.0) -> None:
        if self.speech is not None:
            self.speech.say(text, prio, beep=beep, max_age_s=max_age)


# =============================================================================================
# Preview rendering (window + MJPEG stream share the same annotated frame)
# =============================================================================================

COLORS = {
    Level.CRITICAL: (40, 40, 235),
    Level.CAUTION: (0, 190, 255),
    Level.CLEAR: (90, 210, 90),
    Level.UNKNOWN: (160, 160, 160),
}


def _label_color(label: str) -> Tuple[int, int, int]:
    h = (sum(ord(c) * 31 for c in label) % 180)
    hsv = np.uint8([[[h, 160, 230]]])
    b, g, r = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return int(b), int(g), int(r)


def _text(img, txt, org, scale=0.5, color=(255, 255, 255), thick=1, bg=None):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), base = cv2.getTextSize(txt, font, scale, thick)
    x, y = org
    if bg is not None:
        cv2.rectangle(img, (x - 3, y - th - 4), (x + tw + 3, y + base + 1), bg, -1)
    cv2.putText(img, txt, (x, y), font, scale, color, thick, cv2.LINE_AA)
    return tw, th


@dataclasses.dataclass
class Snapshot:
    """Everything the UI layers need, captured once per frame."""
    cam_fps: float = 0.0
    inf_fps: float = 0.0
    cam_status: str = "init"
    model: str = "-"
    frame_size: Tuple[int, int] = (0, 0)
    tracks: List[Track] = dataclasses.field(default_factory=list)
    lidar: Optional[LidarSample] = None
    lidar_status: str = "-"
    lidar_rate: float = 0.0
    lidar_port: str = "-"
    lidar_frames: int = 0
    lidar_bad: int = 0
    hazard: Optional[Hazard] = None
    audio_backend: str = "-"
    audio_sink: str = "-"
    audio_bt: bool = False
    muted: bool = False
    last_spoken: str = ""
    last_spoken_age: float = 1e9
    uptime: float = 0.0
    frames: int = 0


def draw_overlay(frame: np.ndarray, snap: Snapshot, cfg: Config, debug: bool = True) -> np.ndarray:
    img = frame
    H, W = img.shape[:2]
    hz = snap.hazard
    level = hz.level if hz else Level.UNKNOWN
    target_id = hz.target.track_id if (hz and hz.target) else None

    # --- object boxes --------------------------------------------------------------------
    for trk in snap.tracks:
        x, y, w, h = trk.ibox
        is_target = trk.track_id == target_id
        color = COLORS[level] if is_target and level >= Level.CAUTION else _label_color(trk.label)
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 3 if is_target else 2)
        tag = f"{trk.label} {trk.score * 100:.0f}%"
        if is_target and hz and hz.distance_cm is not None:
            tag += f"  {hz.distance_cm:.0f}cm"
        if debug:
            tag = f"#{trk.track_id} " + tag
        tag_y = y - 6 if y - 6 > 44 else y + 20  # keep clear of the top status bar
        _text(img, tag, (x + 4, tag_y), 0.5, (0, 0, 0) if not is_target else (255, 255, 255),
              1, bg=color)

    # --- LiDAR aim point -----------------------------------------------------------------
    if hz:
        ax, ay, aw, ah = hz.aim_box
        cxy = (ax + aw // 2, ay + ah // 2)
        col = COLORS[level]
        cv2.rectangle(img, (ax, ay), (ax + aw, ay + ah), col, 1)
        cv2.drawMarker(img, cxy, col, cv2.MARKER_CROSS, 18, 2)
        dtxt = f"{hz.distance_cm:.0f} cm" if hz.distance_cm is not None else "-- cm"
        _text(img, dtxt, (ax + aw + 6, ay + ah // 2 + 5), 0.55, col, 2)

    # --- top status bar ------------------------------------------------------------------
    cv2.rectangle(img, (0, 0), (W, 26), (20, 20, 20), -1)
    lid = snap.lidar
    lid_txt = (f"LiDAR {lid.distance_cm:.0f}cm s{lid.strength}" if lid and lid.valid and lid.distance_cm
               else f"LiDAR {snap.lidar_status}")
    audio_txt = "MUTED" if snap.muted else ("BT" if snap.audio_bt else "AUDIO")
    _text(img, f"VANTAGE  CAM {snap.cam_fps:4.1f}fps  NN {snap.inf_fps:4.1f}/s  {lid_txt}  [{audio_txt}]",
          (6, 18), 0.48, (230, 230, 230), 1)

    # --- distance bar (right edge) -------------------------------------------------------
    bar_x, bar_top, bar_bot = W - 22, 40, H - 70
    cv2.rectangle(img, (bar_x, bar_top), (bar_x + 12, bar_bot), (60, 60, 60), 1)
    max_cm = max(cfg.warning_cm * 3, 300)
    for thr, col in ((cfg.critical_cm, COLORS[Level.CRITICAL]), (cfg.warning_cm, COLORS[Level.CAUTION])):
        yy = int(bar_bot - (bar_bot - bar_top) * clamp(thr / max_cm, 0, 1))
        cv2.line(img, (bar_x - 4, yy), (bar_x + 16, yy), col, 1)
    if hz and hz.distance_cm is not None:
        frac = clamp(hz.distance_cm / max_cm, 0, 1)
        yy = int(bar_bot - (bar_bot - bar_top) * frac)
        cv2.rectangle(img, (bar_x + 1, yy), (bar_x + 11, bar_bot - 1), COLORS[level], -1)

    # --- alert banner --------------------------------------------------------------------
    if hz and hz.level >= Level.CAUTION and hz.message:
        col = COLORS[hz.level]
        flash = hz.level == Level.CRITICAL and int(time.monotonic() * 4) % 2 == 0
        cv2.rectangle(img, (0, H - 64), (W, H - 30), col if not flash else (255, 255, 255), -1)
        msg = ("!! " if hz.level == Level.CRITICAL else "") + hz.message.upper()
        if hz.ttc_s is not None and hz.ttc_s < 5:
            msg += f"  (TTC {hz.ttc_s:.1f}s)"
        _text(img, msg, (10, H - 41), 0.62, (255, 255, 255) if not flash else col, 2)
        if hz.level == Level.CRITICAL:
            cv2.rectangle(img, (0, 0), (W - 1, H - 1), col, 6)

    # --- what was spoken -----------------------------------------------------------------
    cv2.rectangle(img, (0, H - 28), (W, H), (20, 20, 20), -1)
    said = snap.last_spoken if snap.last_spoken_age < 6 else ""
    src = hz.source if hz else "-"
    _text(img, f"Spoken: \"{said}\"" if said else f"Spoken: -    fusion: {src}", (8, H - 9), 0.5,
          (120, 255, 255) if said else (170, 170, 170), 1)
    return img


class MjpegStreamer:
    """Tiny MJPEG server: open http://<pi-ip>:PORT/ in any browser to see the preview."""

    PAGE = b"""<!doctype html><html><head><meta name=viewport content="width=device-width">
<title>Vantage preview</title><style>body{margin:0;background:#111;color:#ddd;font:14px sans-serif}
img{width:100%;max-width:960px;display:block;margin:auto}pre{max-width:960px;margin:8px auto}</style>
</head><body><img src="/stream.mjpg"><pre id=s></pre><script>
setInterval(()=>fetch('/status.json').then(r=>r.json()).then(j=>{s.textContent=JSON.stringify(j,null,1)}),500)
</script></body></html>"""

    def __init__(self, port: int):
        self.port = port
        self._frame: Optional[bytes] = None
        self._status: dict = {}
        self._cond = threading.Condition()
        self.clients = 0
        self._httpd: Optional[socketserver.ThreadingMixIn] = None
        self._thread: Optional[threading.Thread] = None

    def publish(self, frame: np.ndarray, status: dict) -> None:
        if self.clients <= 0:
            self._status = status
            return
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return
        with self._cond:
            self._frame = jpg.tobytes()
            self._status = status
            self._cond.notify_all()

    def start(self) -> None:
        streamer = self

        class Handler(http_server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence default stderr logging
                pass

            def do_GET(self):  # noqa: N802
                if self.path in ("/", "/index.html"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(streamer.PAGE)
                elif self.path == "/status.json":
                    body = json.dumps(streamer._status).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/stream.mjpg":
                    self.send_response(200)
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
                    self.end_headers()
                    streamer.clients += 1
                    try:
                        while True:
                            with streamer._cond:
                                streamer._cond.wait(timeout=2.0)
                                frame = streamer._frame
                            if frame is None:
                                continue
                            self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\n")
                            self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                            self.wfile.write(frame + b"\r\n")
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        streamer.clients -= 1
                else:
                    self.send_error(404)

        class Server(socketserver.ThreadingMixIn, http_server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._httpd = Server(("0.0.0.0", self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="mjpeg", daemon=True)
        self._thread.start()
        EVENTS.add(f"Preview stream on http://<pi-ip>:{self.port}/")

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


# =============================================================================================
# Terminal dashboard
# =============================================================================================

class Dashboard(threading.Thread):
    ANSI = {
        "reset": "\x1b[0m", "bold": "\x1b[1m", "dim": "\x1b[2m",
        "red": "\x1b[91m", "yellow": "\x1b[93m", "green": "\x1b[92m", "cyan": "\x1b[96m",
        "grey": "\x1b[90m", "inv": "\x1b[7m",
    }

    def __init__(self, cfg: Config, stop_event: threading.Event, get_snapshot):
        super().__init__(name="dashboard", daemon=True)
        self.cfg = cfg
        self.stop_event = stop_event
        self.get_snapshot = get_snapshot
        self.tty = sys.stdout.isatty()
        if not self.tty:
            self.ANSI = {k: "" for k in self.ANSI}

    def _c(self, name: str, s: str) -> str:
        return f"{self.ANSI[name]}{s}{self.ANSI['reset']}"

    def _bar(self, cm: Optional[float], width: int = 40) -> str:
        if cm is None:
            return self._c("grey", "·" * width)
        max_cm = max(self.cfg.warning_cm * 3, 300)
        n = int(round(clamp(cm / max_cm, 0, 1) * width))
        col = "red" if cm < self.cfg.critical_cm else "yellow" if cm < self.cfg.warning_cm else "green"
        return self._c(col, "█" * n) + self._c("grey", "·" * (width - n))

    def render(self, s: Snapshot) -> str:
        c = self._c
        hz = s.hazard
        lines = []
        lines.append(c("bold", f" VANTAGE CORE v{__version__}") +
                     c("grey", f"   uptime {int(s.uptime // 60):02d}:{int(s.uptime % 60):02d}"
                               f"   frames {s.frames}   (Ctrl+C to quit)"))
        lines.append(c("grey", " " + "─" * 74))

        # Camera
        fps_col = "green" if s.cam_fps >= 20 else "yellow" if s.cam_fps >= 10 else "red"
        lines.append(f" {c('cyan', 'CAMERA')}   {c(fps_col, f'{s.cam_fps:5.1f} fps')}   "
                     f"NN {s.inf_fps:5.1f}/s   {s.frame_size[0]}x{s.frame_size[1]}   {s.cam_status}")
        lines.append(f"          model: {s.model}")

        # LiDAR
        lid = s.lidar
        if lid and lid.valid and lid.distance_cm is not None:
            dcol = "red" if lid.distance_cm < self.cfg.critical_cm else \
                "yellow" if lid.distance_cm < self.cfg.warning_cm else "green"
            vel = f"{lid.velocity_cm_s:+6.0f} cm/s"
            ttc = f"TTC {lid.ttc_s:4.1f}s" if lid.ttc_s is not None else "TTC   --"
            lines.append(f" {c('cyan', 'LIDAR')}    {c(dcol, c('bold', f'{lid.distance_cm:6.0f} cm'))}  "
                         f"str {lid.strength:5d}  {lid.temperature_c:4.1f}°C  {vel}  {ttc}")
        else:
            raw = f"(raw {lid.raw_cm} cm, str {lid.strength})" if lid else ""
            lines.append(f" {c('cyan', 'LIDAR')}    {c('grey', '   --- cm')}  {s.lidar_status} {raw}")
        lines.append(f"          {self._bar(lid.distance_cm if lid and lid.valid else None)}  "
                     f"{s.lidar_rate:5.0f} Hz  {s.lidar_port}  ok {s.lidar_frames}  bad {s.lidar_bad}")

        # Hazard
        if hz:
            name, col = {Level.CRITICAL: ("CRITICAL", "red"), Level.CAUTION: ("CAUTION", "yellow"),
                         Level.CLEAR: ("CLEAR", "green"), Level.UNKNOWN: ("NO DATA", "grey")}[hz.level]
            tgt = f"{hz.target_label} (#{hz.target.track_id})" if hz.target else "-"
            lines.append(f" {c('cyan', 'STATUS')}   {c(col, c('bold', f'{name:9s}'))} target: {tgt:22s} "
                         f"via {hz.source}")
            if hz.message:
                lines.append(f"          {c(col, '» ' + hz.message)}")
            else:
                lines.append("")
        lines.append(c("grey", " " + "─" * 74))

        # Detections
        lines.append(f" {c('cyan', 'DETECTIONS')} ({len(s.tracks)})")
        target_id = hz.target.track_id if (hz and hz.target) else None
        for trk in sorted(s.tracks, key=lambda t: -t.score)[:8]:
            x, y, w, h = trk.ibox
            mark = c("red", "◉") if trk.track_id == target_id else " "
            cx, _ = trk.center
            lines.append(f"  {mark} #{trk.track_id:<4d}{trk.label:16s} {trk.score * 100:5.1f}%  "
                         f"box x={x:4d} y={y:4d} w={w:4d} h={h:4d}  {direction_of(cx, s.frame_size[0] or 1)}")
        for _ in range(max(0, 8 - len(s.tracks))):
            lines.append("")
        lines.append(c("grey", " " + "─" * 74))

        # Audio
        sink = s.audio_sink if len(s.audio_sink) < 46 else s.audio_sink[:43] + "..."
        bt = c("green", "Bluetooth ✓") if s.audio_bt else c("yellow", "not Bluetooth")
        lines.append(f" {c('cyan', 'AUDIO')}    {s.audio_backend:8s} {bt}  {c('grey', sink)}"
                     + (c("red", "  MUTED") if s.muted else ""))
        said = s.last_spoken if s.last_spoken_age < 10 else ""
        lines.append(f"          last: {c('bold', said) if said else c('grey', '-')}")
        lines.append(c("grey", " " + "─" * 74))
        lines.append(f" {c('cyan', 'EVENTS')}")
        for ev in EVENTS.items()[-5:]:
            lines.append(c("grey", "  " + ev[:76]))
        return "\n".join(lines)

    def run(self) -> None:
        period = 1.0 / max(0.5, self.cfg.dashboard_hz)
        if self.tty:
            sys.stdout.write("\x1b[?25l\x1b[2J")  # hide cursor, clear screen
        last_plain = 0.0
        while not self.stop_event.is_set():
            snap = self.get_snapshot()
            if snap is not None:
                if self.tty:
                    out = self.render(snap)
                    # clear to end of each line so shorter lines don't leave garbage
                    out = "\x1b[H" + out.replace("\n", "\x1b[K\n") + "\x1b[K\x1b[J"
                    sys.stdout.write(out)
                    sys.stdout.flush()
                elif time.monotonic() - last_plain > 2.0:
                    last_plain = time.monotonic()
                    hz = snap.hazard
                    d = f"{hz.distance_cm:.0f}cm" if hz and hz.distance_cm is not None else "--"
                    objs = ", ".join(f"{t.label}:{t.score:.2f}" for t in snap.tracks) or "none"
                    print(f"[{time.strftime('%H:%M:%S')}] fps={snap.cam_fps:.1f} lidar={d} "
                          f"level={hz.level.name if hz else '-'} objs=[{objs}] said=\"{snap.last_spoken}\"",
                          flush=True)
            self.stop_event.wait(period)

    def restore_terminal(self) -> None:
        if self.tty:
            sys.stdout.write("\x1b[?25h\x1b[0m\n")
            sys.stdout.flush()


# =============================================================================================
# Application
# =============================================================================================

class VantageApp:
    WINDOW = "Vantage preview  (q quit | m mute | s speak scene | d debug)"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.stop_event = threading.Event()
        self.camera: CameraBase = (SimulatedCamera(cfg) if cfg.simulate or cfg.simulate_camera
                                   else IMX500Camera(cfg))
        self.lidar = (SimulatedLidar(cfg, self.stop_event) if cfg.simulate or cfg.simulate_lidar
                      else LidarReader(cfg, self.stop_event))
        self.speech: Optional[SpeechEngine] = SpeechEngine(cfg, self.stop_event)
        self.bt = BluetoothMonitor(cfg, self.stop_event)
        self.tracker = ObjectTracker()
        self.assessor = HazardAssessor(cfg, (cfg.width, cfg.height))
        self.announcer = Announcer(cfg, self.speech, cfg.width)
        self.streamer = MjpegStreamer(cfg.stream_port) if cfg.stream_port else None
        self.dashboard = Dashboard(cfg, self.stop_event, self.snapshot) if cfg.dashboard else None
        self.cam_rate = RateMeter()
        self.inf_rate = RateMeter()
        self._snap: Optional[Snapshot] = None
        self._snap_lock = threading.Lock()
        self._t_start = time.monotonic()
        self._frames = 0
        self._window_open = False
        self._debug = True

    # ---------------------------------------------------------------------------------------

    def snapshot(self) -> Optional[Snapshot]:
        with self._snap_lock:
            return self._snap

    def _build_snapshot(self, tracks: List[Track], lidar: Optional[LidarSample], hz: Hazard) -> Snapshot:
        sp = self.speech
        return Snapshot(
            cam_fps=self.cam_rate.rate, inf_fps=self.inf_rate.rate, cam_status=self.camera.status,
            model=self.camera.model_name, frame_size=self.camera.frame_size,
            tracks=[dataclasses.replace(t) for t in tracks], lidar=lidar,
            lidar_status=self.lidar.status, lidar_rate=self.lidar.rate.rate,
            lidar_port=self.lidar.port_in_use or "-", lidar_frames=self.lidar.parser.good_frames,
            lidar_bad=self.lidar.parser.bad_checksums, hazard=hz,
            audio_backend=sp.backend if sp else "off", audio_sink=self.bt.sink,
            audio_bt=self.bt.is_bluetooth, muted=sp.muted if sp else True,
            last_spoken=sp.last_spoken if sp else "",
            last_spoken_age=(time.monotonic() - sp.last_spoken_at) if sp and sp.last_spoken_at else 1e9,
            uptime=time.monotonic() - self._t_start, frames=self._frames,
        )

    @staticmethod
    def _status_json(s: Snapshot) -> dict:
        hz = s.hazard
        return {
            "fps": round(s.cam_fps, 1), "nn_rate": round(s.inf_fps, 1),
            "lidar_cm": None if not (s.lidar and s.lidar.valid) else round(s.lidar.distance_cm or 0, 1),
            "level": hz.level.name if hz else None, "target": hz.target_label if hz else None,
            "message": hz.message if hz else "", "spoken": s.last_spoken,
            "objects": [{"id": t.track_id, "label": t.label, "score": round(t.score, 2), "box": t.ibox}
                        for t in s.tracks],
        }

    def _describe_scene(self, tracks: List[Track], hz: Hazard) -> None:
        if not self.speech:
            return
        if not tracks:
            self.speech.say("Nothing detected", Priority.INFO)
            return
        parts = []
        for trk in sorted(tracks, key=lambda t: -t.box[2] * t.box[3])[:4]:
            cx, _ = trk.center
            parts.append(f"{spoken_label(trk.label)} {direction_of(cx, self.cfg.width)}")
        txt = ", ".join(parts)
        if hz.distance_cm is not None:
            txt += f". Distance ahead {spoken_distance(hz.distance_cm)}"
        self.speech.say(txt, Priority.INFO, max_age_s=4.0)

    def _handle_key(self, key: int, tracks: List[Track], hz: Hazard) -> None:
        if key in (ord("q"), 27):
            self.stop_event.set()
        elif key == ord("m") and self.speech:
            EVENTS.add("Audio MUTED" if self.speech.toggle_mute() else "Audio unmuted")
        elif key == ord("s"):
            self._describe_scene(tracks, hz)
        elif key == ord("d"):
            self._debug = not self._debug

    # ---------------------------------------------------------------------------------------

    def start(self) -> None:
        EVENTS.add(f"Vantage core {__version__} starting (simulate={self.cfg.simulate})")
        self.lidar.start()
        if self.speech:
            self.speech.start()
        self.bt.start()
        if self.streamer:
            self.streamer.start()
        self.camera.start()
        if self.dashboard:
            self.dashboard.start()
        if self.speech:
            self.speech.say("Vantage ready", Priority.INFO, max_age_s=5.0)

    def _camera_watchdog(self) -> None:
        """If the camera stops delivering frames, explain why and exit instead of hanging."""
        started = time.monotonic()
        while not self.stop_event.wait(0.5):
            last = self._last_frame_at
            limit = 5.0 if last else 90.0   # first start uploads the network firmware (~1 min)
            if time.monotonic() - (last or started) > limit:
                if self.dashboard:
                    self.dashboard.restore_terminal()
                print(CAMERA_STUCK_MSG, file=sys.stderr, flush=True)
                LOG.error("camera stopped delivering frames")
                if self.speech:
                    self.speech.say("Camera stopped working", Priority.CRITICAL, max_age_s=5)
                time.sleep(3.0)
                os._exit(3)

    def run(self) -> None:
        last_tracks: List[Track] = []
        deadline = self._t_start + self.cfg.duration_s if self.cfg.duration_s > 0 else None
        self._last_frame_at = 0.0
        threading.Thread(target=self._camera_watchdog, name="watchdog", daemon=True).start()
        while not self.stop_event.is_set():
            if deadline and time.monotonic() > deadline:
                break
            frame, dets = self.camera.read()
            self._last_frame_at = time.monotonic()
            if frame is None:
                continue
            now = time.monotonic()
            self._frames += 1
            self.cam_rate.tick(now)

            # 1) vision: update tracks only when the IMX500 delivered a new tensor
            if dets is not None:
                self.inf_rate.tick(now)
                last_tracks = self.tracker.update(dets, now)
            self.inf_rate.decay(now)

            # 2) lidar: grab the freshest filtered sample (non-blocking)
            lid = self.lidar.latest()

            # 3) fusion + speech decisions
            hz = self.assessor.assess(lid, last_tracks)
            self.announcer.update(hz, last_tracks, now)

            # 4) UI
            snap = self._build_snapshot(last_tracks, lid, hz)
            with self._snap_lock:
                self._snap = snap
            if self.cfg.show_preview or self.streamer:
                annotated = draw_overlay(frame, snap, self.cfg, self._debug)
                if self.streamer:
                    self.streamer.publish(annotated, self._status_json(snap))
                if self.cfg.show_preview:
                    self._show(annotated, last_tracks, hz)

    def _show(self, img: np.ndarray, tracks: List[Track], hz: Hazard) -> None:
        try:
            if not self._window_open:
                cv2.namedWindow(self.WINDOW, cv2.WINDOW_NORMAL)
                if self.cfg.fullscreen:
                    cv2.setWindowProperty(self.WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.resizeWindow(self.WINDOW, self.cfg.width, self.cfg.height)
                self._window_open = True
            cv2.imshow(self.WINDOW, img)
            key = cv2.waitKey(1) & 0xFF
            if key != 255:
                self._handle_key(key, tracks, hz)
            if cv2.getWindowProperty(self.WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                self.stop_event.set()  # window closed with the X button
        except cv2.error as exc:
            EVENTS.add(f"Preview window unavailable ({str(exc).splitlines()[0][:60]}), continuing headless")
            self.cfg.show_preview = False

    def shutdown(self) -> None:
        """Idempotent, ordered cleanup. Safe to call from any failure state."""
        self.stop_event.set()
        if self.speech:
            self.speech.stop()
        try:
            self.camera.stop()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("camera stop: %s", exc)
        if self.streamer:
            try:
                self.streamer.stop()
            except Exception:  # noqa: BLE001
                pass
        for th in (self.lidar, self.speech, self.bt, self.dashboard):
            if th is not None and th.is_alive():
                th.join(timeout=2.0)
        if self._window_open:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except Exception:  # noqa: BLE001
                pass
        if self.dashboard:
            self.dashboard.restore_terminal()
        LOG.info("Shutdown complete")


# =============================================================================================
# CLI
# =============================================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> Config:
    d = Config()
    p = argparse.ArgumentParser(
        description="Vantage assistive wearable core loop (IMX500 + TFmini Plus + Bluetooth TTS)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    g = p.add_argument_group("camera")
    g.add_argument("--model", default=d.model, help="IMX500 .rpk object detection network")
    g.add_argument("--labels", dest="labels_file", default=None, help="labels file (one per line)")
    g.add_argument("--camera-num", type=int, default=None, help="camera index (default: auto-detect IMX500)")
    g.add_argument("--width", type=int, default=d.width)
    g.add_argument("--height", type=int, default=d.height)
    g.add_argument("--fps", type=float, default=None, help="camera frame rate (default: model rate)")
    g.add_argument("--rotate-180", action="store_true", help="camera is mounted upside down")
    g.add_argument("--threshold", dest="score_threshold", type=float, default=d.score_threshold,
                   help="detection confidence threshold")
    g.add_argument("--max-detections", type=int, default=d.max_detections)
    g.add_argument("--hfov", dest="cam_hfov_deg", type=float, default=d.cam_hfov_deg)
    g.add_argument("--vfov", dest="cam_vfov_deg", type=float, default=d.cam_vfov_deg)

    g = p.add_argument_group("lidar")
    g.add_argument("--serial", dest="serial_port", default=d.serial_port)
    g.add_argument("--baud", type=int, default=d.baud)
    g.add_argument("--lidar-rate", dest="lidar_rate_hz", type=int, default=None,
                   help="re-program TFmini output rate (Hz), e.g. 100")
    g.add_argument("--min-strength", dest="lidar_min_strength", type=int, default=d.lidar_min_strength)
    g.add_argument("--lidar-offset-x", dest="lidar_offset_x_cm", type=float, default=d.lidar_offset_x_cm,
                   help="LiDAR is this many cm RIGHT of the camera lens (negative = left)")
    g.add_argument("--lidar-offset-y", dest="lidar_offset_y_cm", type=float, default=d.lidar_offset_y_cm,
                   help="LiDAR is this many cm BELOW the camera lens (negative = above)")

    g = p.add_argument_group("alerts")
    g.add_argument("--critical", dest="critical_cm", type=float, default=d.critical_cm,
                   help="'too close' distance (cm)")
    g.add_argument("--warning", dest="warning_cm", type=float, default=d.warning_cm,
                   help="'ahead' caution distance (cm)")
    g.add_argument("--repeat", dest="critical_repeat_s", type=float, default=d.critical_repeat_s,
                   help="seconds between repeated critical alerts")
    g.add_argument("--describe", action="store_true", help="also announce newly seen objects + direction")
    g.add_argument("--min-hits", dest="min_track_hits", type=int, default=d.min_track_hits)

    g = p.add_argument_group("audio")
    g.add_argument("--no-audio", dest="audio_enabled", action="store_false")
    g.add_argument("--audio-backend", default=d.audio_backend,
                   choices=["auto", "paplay", "pw-play", "aplay", "pygame", "espeak"])
    g.add_argument("--voice", default=d.voice, help="espeak voice, e.g. en-us, en-gb, en+f3")
    g.add_argument("--rate", dest="speech_rate", type=int, default=d.speech_rate, help="words per minute")
    g.add_argument("--volume", dest="speech_volume", type=int, default=d.speech_volume, help="0..200")
    g.add_argument("--no-beep", dest="beep", action="store_false")
    g.add_argument("--bt-mac", default=None, help="Bluetooth MAC of the Shokz headset to auto-connect")

    g = p.add_argument_group("display")
    g.add_argument("--headless", dest="show_preview", action="store_false", help="no preview window")
    g.add_argument("--fullscreen", action="store_true")
    g.add_argument("--stream-port", type=int, default=0, help="serve preview at http://<pi>:PORT/")
    g.add_argument("--no-dashboard", dest="dashboard", action="store_false")
    g.add_argument("--log-file", default=d.log_file)
    g.add_argument("-v", "--verbose", action="store_true")

    g = p.add_argument_group("testing")
    g.add_argument("--simulate", action="store_true", help="simulate camera AND lidar (no hardware)")
    g.add_argument("--simulate-lidar", action="store_true")
    g.add_argument("--simulate-camera", action="store_true")
    g.add_argument("--duration", dest="duration_s", type=float, default=0.0, help="stop after N seconds")
    g.add_argument("--version", action="version", version=__version__)

    ns = p.parse_args(argv)
    cfg = Config(**{k: v for k, v in vars(ns).items() if k in Config.__dataclass_fields__})
    return cfg


def setup_logging(cfg: Config) -> None:
    LOG.setLevel(logging.DEBUG if cfg.verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)-10s %(message)s")
    if cfg.log_file:
        fh = logging.handlers.RotatingFileHandler(cfg.log_file, maxBytes=2_000_000, backupCount=3)
        fh.setFormatter(fmt)
        LOG.addHandler(fh)
    if not cfg.dashboard or not sys.stdout.isatty():
        # The live dashboard owns the terminal; otherwise warnings go to stderr too.
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.WARNING)
        sh.setFormatter(fmt)
        LOG.addHandler(sh)


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = parse_args(argv)
    setup_logging(cfg)
    global TRACK_MIN_HITS
    TRACK_MIN_HITS = max(1, cfg.min_track_hits)

    if cv2 is None:
        print("OpenCV is required:  sudo apt install python3-opencv", file=sys.stderr)
        return 2
    if serial is None and not (cfg.simulate or cfg.simulate_lidar):
        print("pyserial is required:  sudo apt install python3-serial", file=sys.stderr)
        return 2
    if cfg.show_preview and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No desktop display found -> running headless. "
              "Use --stream-port 8080 to watch the preview in a browser.", file=sys.stderr)
        cfg.show_preview = False
    if os.geteuid() == 0:
        print("Warning: running as root. Bluetooth audio lives in your user's PipeWire session, "
              "so run WITHOUT sudo (add yourself to the 'dialout' group for the UART).", file=sys.stderr)

    app = VantageApp(cfg)

    # SIGTERM (systemd stop) behaves like Ctrl+C.
    def _sigterm(_signo, _frame):
        app.stop_event.set()
    signal.signal(signal.SIGTERM, _sigterm)

    error: Optional[BaseException] = None
    try:
        app.start()
        app.run()
    except KeyboardInterrupt:
        EVENTS.add("Ctrl+C received, shutting down")
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Fatal error")
        error = exc
    finally:
        app.shutdown()  # always: camera, serial port, audio processes, window, terminal
    if error is not None:
        print(f"\nFATAL: {error}\n(see {cfg.log_file} for the traceback)", file=sys.stderr)
        return 1
    print("Vantage stopped cleanly: camera closed, serial port closed, audio stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
