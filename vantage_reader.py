#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vantage_reader.py - Text reading mode for the "Vantage" assistive wearable.

Point the camera at text (a book page, a label, a sign, a screen) and Vantage reads it
out loud on the Bluetooth bone-conduction headset.

This is a separate program from vantage_core.py (obstacle mode) on purpose:
  * only one program can use the camera at a time, and
  * reading is never interrupted or drowned out by obstacle alerts.
It reuses the Bluetooth / LiDAR / browser-stream helpers from vantage_core.py, so keep
both files in the same folder.

Why OCR often "only reads a few letters", and what this file does about each cause:
  * low resolution        -> captures at 2028x1520 (or 4056x3040), never 640x480
  * shaky hands / blur    -> waits until the camera is steady, grabs a burst of frames
                             and keeps the sharpest one
  * shadows, uneven light -> flattens the illumination before recognition
  * wrong letter size     -> measures the letter height and rescales the image so
                             letters are ~30 px tall, the size Tesseract reads best
  * tilted text           -> measures the skew angle and straightens the image
  * white text on dark    -> detects the polarity and inverts
  * wrong layout guess    -> tries page / block / sparse-sign layouts, keeps the result
                             with the best confidence
  * garbage output        -> drops low-confidence words and junk lines instead of
                             reading noise out loud
  * silent failure        -> tells you WHY it could not read (too dark, blurry, too
                             small, glare...) so you know what to change

Run `python3 vantage_reader.py --help` for every option, `--self-test` to measure the
recognition quality on your Pi, and `--simulate` to try the whole thing without a camera.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import dataclasses
import difflib
import itertools
import json
import logging
import logging.handlers
import math
import os
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import wave
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - checked in main() with a friendly message
    cv2 = None

import vantage_core as vc

__version__ = "1.0.0"

LOG = logging.getLogger("vantage.reader")

Box = Tuple[int, int, int, int]  # x, y, w, h


# =============================================================================================
# Configuration
# =============================================================================================

@dataclasses.dataclass
class ReaderConfig:
    # --- camera ---
    camera_num: Optional[int] = None
    width: int = 2028
    height: int = 1520
    rotate_180: bool = False
    full_sensor: bool = True          # use the full 12 MP sensor so zoom keeps real detail

    # --- zoom (mouse scroll wheel) ---
    zoom_max: float = 3.0
    zoom_step: float = 1.15           # per wheel notch
    mouse: bool = True
    mouse_devices: List[str] = dataclasses.field(default_factory=list)  # empty = auto-detect
    mouse_grab: bool = False          # keep the mouse from also moving the desktop pointer

    # --- recognition ---
    lang: str = "eng"
    tessdata: Optional[str] = None
    ocr_threads: int = 2              # threads per Tesseract process (2 run in parallel)
    min_word_conf: float = 45.0       # words below this confidence are dropped
    sure_conf: float = 72.0           # below this mean confidence: "Not sure, but it says..."
    min_read_conf: float = 60.0       # below this: don't read, explain what is wrong
    target_char_px: float = 30.0      # letter height Tesseract is fed
    max_ocr_s: float = 10.0           # time budget for the retries
    burst: int = 5                    # frames captured per read; the sharpest is used

    # --- auto mode ---
    auto: bool = True
    steady_s: float = 0.7             # camera must be still this long before reading
    motion_thresh: float = 4.0        # mean grey-level change between thumbnails
    scene_change: float = 12.0        # thumbnail difference that counts as "new text"
    repeat_after_s: float = 90.0      # don't re-read the same lines within this time

    # --- speech ---
    audio_enabled: bool = True
    voice: str = "en-us"
    rate: int = 165
    volume: int = 170
    bt_mac: Optional[str] = None

    # --- LiDAR (optional distance hints: "move it farther away") ---
    use_lidar: bool = False
    serial_port: str = "/dev/serial0"
    min_focus_cm: float = 20.0

    # --- ui ---
    show_preview: bool = True
    stream_port: int = 0
    save_debug: Optional[str] = None
    log_file: str = "vantage_reader.log"

    # --- testing ---
    simulate: bool = False
    images: List[str] = dataclasses.field(default_factory=list)
    speak_images: bool = False
    self_test: bool = False
    duration_s: float = 0.0


# =============================================================================================
# Small helpers
# =============================================================================================

def odd(n: float) -> int:
    n = max(3, int(round(n)))
    return n if n % 2 == 1 else n + 1


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def center_crop(img: np.ndarray, frac: float = 0.6) -> np.ndarray:
    h, w = img.shape[:2]
    ch, cw = int(h * frac), int(w * frac)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return img[y0:y0 + ch, x0:x0 + cw]


def alnum_count(s: str) -> int:
    return sum(ch.isalnum() for ch in s)


def ascii_safe(s: str) -> str:
    """OpenCV's built-in fonts only draw ASCII."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def norm_for_compare(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.lower()))


# =============================================================================================
# Image analysis: is there text, how big is it, is it sharp?
# =============================================================================================

@dataclasses.dataclass
class TextLayout:
    boxes: List[Box]               # text-line (or text-block) boxes, analysed image pixels
    n_chars: int                   # character-like blobs that sit in text lines
    char_h: float                  # typical character height (px), 0 = unknown
    dark_text: bool                # True = dark text on a light background
    n_lines: int = 0               # estimated number of text lines
    other_polarity_chars: int = 0  # chars found when assuming the opposite polarity


def _text_lines(bw: np.ndarray, dark: bool) -> TextLayout:
    """Group character-sized blobs of a binary image into text lines."""
    H, W = bw.shape
    empty = TextLayout([], 0, 0.0, dark)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n <= 3:
        return empty
    x, y, w, h, area = (stats[1:, i] for i in range(5))
    min_h = max(5, H // 220)
    ok = ((h >= min_h) & (h <= H * 0.25) & (w <= h * 4) & (area >= 8)
          & (area >= 0.10 * w * h) & (area <= 0.95 * w * h))
    idx = np.nonzero(ok)[0]
    if len(idx) < 3:
        return empty
    med_h = float(np.median(h[idx]))
    lut = np.zeros(n, np.uint8)
    lut[idx + 1] = 255
    mask = lut[labels]
    # Close the gaps between letters (and words) so each text line becomes one blob.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (odd(med_h * 1.1), max(1, int(med_h * 0.15))))
    joined = cv2.dilate(mask, kernel)
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    cx = np.clip(x[idx] + w[idx] // 2, 0, W - 1)
    cy = np.clip(y[idx] + h[idx] // 2, 0, H - 1)
    owner = lab2[cy, cx]
    counts = np.bincount(owner, minlength=n2)
    boxes: List[Box] = []
    n_lines = 0
    good_lines = np.zeros(n2, bool)
    for j in range(1, n2):
        bx, by, bw_, bh, _ = st2[j]
        is_line = counts[j] >= 2 and bw_ >= 1.5 * bh and bh <= 3.5 * med_h
        # tilted text: neighbouring lines merge into one taller block - still text
        is_block = counts[j] >= 12 and bh > 3.5 * med_h and bw_ >= 3 * med_h
        if is_line or is_block:
            boxes.append((int(bx), int(by), int(bw_), int(bh)))
            good_lines[j] = True
            n_lines += 1 if is_line else max(2, int(round(bh / (1.8 * med_h))))
    in_lines = good_lines[owner]
    if not in_lines.any():
        return empty
    char_h = float(np.median(h[idx][in_lines]))
    return TextLayout(boxes, int(in_lines.sum()), char_h, dark, n_lines)


def find_text(gray: np.ndarray) -> TextLayout:
    """Cheap classical text detector (~10 ms at 960x720). Tries both polarities."""
    H, W = gray.shape[:2]
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    block = odd(max(15, W / 40))
    found = []
    for dark in (True, False):
        src = g if dark else cv2.bitwise_not(g)
        # pixels clearly darker than their neighbourhood = ink
        bw = cv2.adaptiveThreshold(src, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 12)
        found.append(_text_lines(bw, dark))
    found.sort(key=lambda r: r.n_chars, reverse=True)
    best, other = found
    best.other_polarity_chars = other.n_chars
    return best


def edge_sharpness(gray: np.ndarray) -> float:
    """
    Contrast-normalised edge steepness, ~1/edge-width in pixels:
    about 0.4+ is crisp, below ~0.12 is blurry. Independent of lighting.
    """
    g = gray[::2, ::2] if min(gray.shape[:2]) > 900 else gray
    lo, hi = np.percentile(g, (2, 98))
    contrast = float(hi) - float(lo)
    if contrast < 25:
        return 0.0
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    top = float(np.percentile(mag, 99.5))
    scale = 2.0 if g is not gray else 1.0  # subsampling makes edges look 2x steeper
    return float(min(1.0, top / (4.0 * contrast * scale)))


# =============================================================================================
# Pre-processing for recognition
# =============================================================================================

def flatten_illumination(gray: np.ndarray, char_h: float) -> np.ndarray:
    """
    Divide by an estimate of the paper brightness so shadows, vignetting and uneven light
    disappear: the background becomes ~255 everywhere, ink stays dark.
    Expects dark text on a light background.
    """
    H, W = gray.shape
    k = 4 if min(H, W) > 800 else 2
    small = cv2.resize(gray, (max(1, W // k), max(1, H // k)), interpolation=cv2.INTER_AREA)
    ch = (char_h / k) if char_h > 0 else small.shape[1] / 80.0
    # max-filter removes the (dark) letters, leaving only the background
    r = odd(max(3, ch * 1.3))
    bg = cv2.dilate(small, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r)))
    bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=max(2.0, ch * 1.5))
    bg = cv2.resize(bg, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.divide(gray, np.maximum(bg, 1), scale=255)


def noise_sigma(gray: np.ndarray) -> float:
    """Robust estimate of the camera noise level (grey levels) from the Laplacian."""
    g = gray[::2, ::2] if gray.size > 4_000_000 else gray
    lap = cv2.Laplacian(g, cv2.CV_32F, ksize=1)
    return float(1.4826 * np.median(np.abs(lap)) / math.sqrt(20.0))


def denoise(gray: np.ndarray) -> np.ndarray:
    """Edge-preserving noise reduction, only when the image is actually noisy (dim light)."""
    sigma = noise_sigma(gray)
    if sigma < 2.0:
        return gray
    return cv2.bilateralFilter(gray, 5, sigmaColor=3.0 * sigma, sigmaSpace=2.0)


def text_region(layout: TextLayout, ws: float, shape: Tuple[int, int], char_h: float) -> Optional[Box]:
    """Bounding box (source pixels) around all detected text lines, with a generous margin."""
    if not layout.boxes:
        return None
    H, W = shape
    xs = [b[0] for b in layout.boxes] + [b[0] + b[2] for b in layout.boxes]
    ys = [b[1] for b in layout.boxes] + [b[1] + b[3] for b in layout.boxes]
    m = max(4 * char_h, 0.04 * max(W, H))
    x0, x1 = max(0, int(min(xs) / ws - m)), min(W, int(max(xs) / ws + m))
    y0, y1 = max(0, int(min(ys) / ws - m)), min(H, int(max(ys) / ws + m))
    if (x1 - x0) * (y1 - y0) > 0.85 * W * H:
        return None
    return x0, y0, x1 - x0, y1 - y0


def stretch_contrast(g: np.ndarray) -> np.ndarray:
    lo = float(np.percentile(g[::3, ::3], 0.2))
    if 5 < lo < 230:
        lut = np.clip((np.arange(256, dtype=np.float32) - lo) * 255.0 / (255.0 - lo), 0, 255).astype(np.uint8)
        g = cv2.LUT(g, lut)
    return g


def estimate_skew(dark_on_light: np.ndarray, max_angle: float = 10.0) -> float:
    """Projection-profile deskew: the angle that makes text rows sharpest."""
    H, W = dark_on_light.shape
    f = min(1.0, 800.0 / W)
    small = cv2.resize(dark_on_light, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else dark_on_light
    h, w = small.shape
    bw = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, odd(w / 30), 15)
    if cv2.countNonZero(bw) < 80:
        return 0.0

    def score(a: float) -> float:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        r = cv2.warpAffine(bw, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        d = np.diff(r.sum(axis=1, dtype=np.float64))
        return float(np.dot(d, d))

    best = max(np.arange(-max_angle, max_angle + 1e-6, 1.0), key=score)
    best = max(np.arange(best - 1.0, best + 1.0 + 1e-6, 0.2), key=score)
    return float(best)


def rotate_expand(img: np.ndarray, angle: float, pad: int) -> Tuple[np.ndarray, np.ndarray]:
    """Rotate without cutting corners, add a white border. Returns (image, 2x3 matrix)."""
    h, w = img.shape[:2]
    if abs(angle) < 1e-6:
        M = np.array([[1.0, 0.0, pad], [0.0, 1.0, pad]])
        return cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255), M
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw = int(math.ceil(w * cos + h * sin)) + 2 * pad
    nh = int(math.ceil(w * sin + h * cos)) + 2 * pad
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    out = cv2.warpAffine(img, M, (nw, nh), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return out, M


@dataclasses.dataclass
class Prepared:
    """An image ready for Tesseract plus the geometry to map boxes back to the frame."""
    gray: np.ndarray
    scale: float
    M: np.ndarray
    angle: float
    char_h: float           # letter height in the source frame (px), 0 = unknown
    dark_text: bool
    layout: TextLayout      # text analysis at `work_scale`
    work_scale: float
    offset: Tuple[int, int] = (0, 0)   # crop origin in the source frame
    rot: int = 0                       # extra 90/180/270 rotation applied (clockwise)
    _binary: Optional[np.ndarray] = None

    def rotated(self, rot: int) -> "Prepared":
        """Turn the prepared image by 90/180/270 degrees clockwise (upside-down text etc.)."""
        h, w = self.gray.shape
        if rot == 90:
            img, R = cv2.rotate(self.gray, cv2.ROTATE_90_CLOCKWISE), [[0, -1, h - 1], [1, 0, 0]]
        elif rot == 180:
            img, R = cv2.rotate(self.gray, cv2.ROTATE_180), [[-1, 0, w - 1], [0, -1, h - 1]]
        elif rot == 270:
            img, R = cv2.rotate(self.gray, cv2.ROTATE_90_COUNTERCLOCKWISE), [[0, 1, 0], [-1, 0, w - 1]]
        else:
            return self
        M = (np.vstack([R, [0, 0, 1]]) @ np.vstack([self.M, [0, 0, 1]]))[:2]
        return dataclasses.replace(self, gray=img, M=M, rot=(self.rot + rot) % 360, _binary=None)

    def binary(self) -> np.ndarray:
        if self._binary is None:
            blk = odd(max(31, 2.2 * (self.char_h * self.scale if self.char_h else 30)))
            b = cv2.adaptiveThreshold(self.gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, blk, 15)
            # remove speckles far smaller than a letter's dot
            n, labels, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(b), connectivity=8)
            min_area = max(4, int((self.char_h * self.scale if self.char_h else 30) ** 2 * 0.006))
            small = np.zeros(n, bool)
            small[1:] = stats[1:, cv2.CC_STAT_AREA] < min_area
            b[small[labels]] = 255
            self._binary = b
        return self._binary

    def to_source(self, box: Box) -> Box:
        x, y, w, h = box
        Minv = cv2.invertAffineTransform(self.M)
        pts = np.array([[x, y], [x + w, y], [x, y + h], [x + w, y + h]], np.float64)
        src = (pts @ Minv[:, :2].T + Minv[:, 2]) / self.scale + np.array(self.offset)
        x0, y0 = src.min(axis=0)
        x1, y1 = src.max(axis=0)
        return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


def prepare(img: np.ndarray, cfg: ReaderConfig, dark_text: Optional[bool] = None) -> Prepared:
    gray = to_gray(img)
    H, W = gray.shape
    ws = min(1.0, 2000.0 / max(W, H))
    work = cv2.resize(gray, None, fx=ws, fy=ws, interpolation=cv2.INTER_AREA) if ws < 1 else gray
    layout = find_text(work)
    dark = layout.dark_text if dark_text is None else dark_text
    char_h = layout.char_h / ws if layout.char_h else 0.0

    # Work only on the part of the frame that contains text: faster, and the dark noisy
    # surroundings cannot turn into fake "letters" once the lighting is normalised.
    offset = (0, 0)
    region = text_region(layout, ws, (H, W), char_h)
    if region is not None:
        x, y, w, h = region
        gray, offset = gray[y:y + h, x:x + w], (x, y)
        H, W = gray.shape
    gray = denoise(gray)
    if not dark:
        gray = cv2.bitwise_not(gray)
    norm = flatten_illumination(gray, char_h)

    if char_h > 0:
        s = float(np.clip(cfg.target_char_px / char_h, 0.25, 3.5))
    else:
        s = 2.0 if max(W, H) < 1200 else 1.0
    s = min(s, 4200.0 / max(W, H))
    if abs(s - 1.0) < 0.06:
        s, scaled = 1.0, norm
    else:
        scaled = cv2.resize(norm, None, fx=s, fy=s,
                            interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)

    angle = estimate_skew(scaled) if layout.n_chars >= 4 else 0.0
    if abs(angle) < 0.4:
        angle = 0.0
    final, M = rotate_expand(scaled, angle, pad=24)
    final = stretch_contrast(final)
    return Prepared(final, s, M, angle, char_h, dark, layout, ws, offset)


# =============================================================================================
# Tesseract
# =============================================================================================

@dataclasses.dataclass
class Word:
    text: str
    conf: float
    box: Box
    block: int = 0
    par: int = 0
    line: int = 0


def parse_tsv(tsv: str) -> List[Word]:
    words = []
    for row in tsv.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) < 12 or parts[0] != "5":
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(parts[10])
            box = (int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9]))
            words.append(Word(text, conf, box, int(parts[2]), int(parts[3]), int(parts[4])))
        except ValueError:
            continue
    return words


class Tesseract:
    """Thin wrapper around the `tesseract` command-line tool (no Python binding needed)."""

    def __init__(self, cfg: ReaderConfig):
        self.cfg = cfg
        self.bin = shutil.which("tesseract")
        if not self.bin:
            raise RuntimeError("Tesseract is not installed:\n"
                               "  sudo apt install tesseract-ocr tesseract-ocr-eng")
        out = subprocess.run([self.bin, "--version"], capture_output=True, text=True).stdout
        m = re.search(r"tesseract\s+v?(\d+)\.(\d+)", out)
        self.version = f"{m.group(1)}.{m.group(2)}" if m else "?"
        if m and int(m.group(1)) < 4:
            raise RuntimeError(f"Tesseract {self.version} is too old; version 4 or newer is needed")
        self.env = dict(os.environ, OMP_THREAD_LIMIT=str(max(1, cfg.ocr_threads)))
        langs = self.languages()
        missing = [lg for lg in cfg.lang.split("+") if langs and lg not in langs]
        if missing:
            raise RuntimeError(f"Tesseract language data missing: {', '.join(missing)}\n"
                               f"  sudo apt install " + " ".join(f"tesseract-ocr-{lg}" for lg in missing))

    def languages(self) -> List[str]:
        cmd = [self.bin, "--list-langs"]
        if self.cfg.tessdata:
            cmd += ["--tessdata-dir", self.cfg.tessdata]
        out = subprocess.run(cmd, capture_output=True, text=True, env=self.env).stdout
        return [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]

    def orientation(self, img: np.ndarray, timeout: float = 6.0) -> Tuple[int, float]:
        """Tesseract OSD: how many degrees (clockwise) the text must be turned to be upright."""
        ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        cmd = [self.bin, "stdin", "stdout", "--psm", "0", "--dpi", "300"]
        if self.cfg.tessdata:
            cmd += ["--tessdata-dir", self.cfg.tessdata]
        try:
            out = subprocess.run(cmd, input=buf.tobytes(), capture_output=True, timeout=timeout,
                                 env=self.env).stdout.decode(errors="ignore")
        except (subprocess.SubprocessError, OSError):
            return 0, 0.0
        rot = re.search(r"Rotate:\s*(\d+)", out)
        conf = re.search(r"Orientation confidence:\s*([\d.]+)", out)
        if not rot or not conf:
            return 0, 0.0   # no osd.traineddata, or too little text to decide
        return int(rot.group(1)) % 360, float(conf.group(1))

    def run(self, img: np.ndarray, psm: int, timeout: float = 30.0) -> List[Word]:
        ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if not ok:
            return []
        cmd = [self.bin, "stdin", "stdout", "--oem", "1", "--psm", str(psm), "-l", self.cfg.lang,
               "--dpi", "300", "-c", "preserve_interword_spaces=1"]
        if self.cfg.tessdata:
            cmd += ["--tessdata-dir", self.cfg.tessdata]
        cmd.append("tsv")
        try:
            p = subprocess.run(cmd, input=buf.tobytes(), capture_output=True, timeout=timeout, env=self.env)
        except subprocess.TimeoutExpired:
            LOG.warning("tesseract timed out (psm %d)", psm)
            return []
        if p.returncode != 0:
            LOG.warning("tesseract failed: %s", p.stderr.decode(errors="ignore")[:200])
            return []
        return parse_tsv(p.stdout.decode("utf-8", errors="replace"))


# =============================================================================================
# From words to clean, speakable text
# =============================================================================================

WEIRD_CHARS = set("|\\{}[]<>~^_`§¦®©")


def keep_word(w: Word, min_conf: float) -> bool:
    t = w.text
    n = alnum_count(t)
    if n == 0:
        return False
    weird = sum(ch in WEIRD_CHARS for ch in t)
    if weird and (weird / len(t) > 0.2 or w.conf < 85):
        return False
    if n >= 4:
        return w.conf >= min_conf
    if n >= 2:
        return w.conf >= min_conf + 15
    core = t.strip(".,;:!?'\"()")
    if core in ("a", "A", "I", "&") or core.isdigit():
        return w.conf >= min_conf + 15
    return w.conf >= 88  # lone letters are usually noise


def filter_line(line: List[Word], min_conf: float) -> List[Word]:
    cand = [w for w in line if alnum_count(w.text)]
    kept = [w for w in cand if keep_word(w, min_conf)]
    if not kept or len(kept) < 0.34 * len(cand):
        return []  # a line that is mostly garbage is probably texture, not text
    n = sum(alnum_count(w.text) for w in kept)
    mean = sum(alnum_count(w.text) * w.conf for w in kept) / n
    if n < 3 and mean < 75:
        return []
    return kept


def group_words(words: List[Word], sparse: bool) -> List[List[List[Word]]]:
    """-> paragraphs -> lines -> words, in reading order."""
    if not words:
        return []
    if not sparse:
        paras: "collections.OrderedDict[tuple, collections.OrderedDict]" = collections.OrderedDict()
        for w in words:
            paras.setdefault((w.block, w.par), collections.OrderedDict()).setdefault(w.line, []).append(w)
        return [list(lines.values()) for lines in paras.values()]

    # Sparse layouts (signs, labels): rebuild lines from the geometry.
    heights = sorted(w.box[3] for w in words)
    med = max(1, heights[len(heights) // 2])
    rows: List[List[Word]] = []
    cur: List[Word] = []
    cur_cy = 0.0
    for w in sorted(words, key=lambda w: w.box[1] + w.box[3] / 2):
        cy = w.box[1] + w.box[3] / 2
        if cur and abs(cy - cur_cy) > 0.6 * med:
            rows.append(cur)
            cur = []
        cur.append(w)
        cur_cy = sum(v.box[1] + v.box[3] / 2 for v in cur) / len(cur)
    if cur:
        rows.append(cur)
    lines: List[List[Word]] = []
    for row in rows:
        row.sort(key=lambda w: w.box[0])
        seg = [row[0]]
        for a, b in zip(row, row[1:]):
            if b.box[0] - (a.box[0] + a.box[2]) > 3 * med:  # far apart: separate items
                lines.append(seg)
                seg = []
            seg.append(b)
        lines.append(seg)
    paras_out: List[List[List[Word]]] = []
    para: List[List[Word]] = []
    prev_bottom: Optional[int] = None
    for ln in lines:
        top = min(w.box[1] for w in ln)
        if para and prev_bottom is not None and top - prev_bottom > 1.2 * med:
            paras_out.append(para)
            para = []
        para.append(ln)
        prev_bottom = max(w.box[1] + w.box[3] for w in ln)
    if para:
        paras_out.append(para)
    return paras_out


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
                         "—": " - ", "–": "-", "•": ",", "·": ","})


def clean_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_QUOTES)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)        # "word ." -> "word."
    return s.lstrip(" -_~|*").rstrip(" _~|*").strip()


def compose_paragraph(lines: List[List[Word]]) -> List[str]:
    """
    Join lines into speakable segments. Wrapped body text is joined (and de-hyphenated);
    short independent lines (signs, headings, list items) stay separate so they get a pause.
    """
    texts = [clean_text(" ".join(w.text for w in ln)) for ln in lines]
    widths = [max(w.box[0] + w.box[2] for w in ln) - min(w.box[0] for w in ln) for ln in lines]
    maxw = max(widths) if widths else 1
    segs: List[str] = []
    cur, cur_full, prev_words = "", False, 0
    for t, wd in zip(texts, widths):
        if not t:
            continue
        if not cur:
            cur = t
        elif cur.endswith("-") and len(cur) > 1 and cur[-2].isalpha() and t[0].islower():
            cur = cur[:-1] + t                      # "infor-" + "mation"
        elif (cur_full and prev_words >= 6) or t[0].islower() or cur.endswith(","):
            cur = cur + " " + t                     # wrapped line of the same sentence
        else:
            segs.append(cur)                        # sign / heading / list item: own phrase
            cur = t
        cur_full = wd >= 0.75 * maxw
        prev_words = len(t.split())
    if cur:
        segs.append(cur)
    return segs


_ABBREV = {"mr", "mrs", "ms", "dr", "st", "vs", "etc", "e.g", "i.e", "no", "fig", "jr", "sr",
           "prof", "approx", "dept", "inc", "ltd", "co", "mt", "ft", "rd", "ave", "tel", "ref"}


def split_sentences(text: str) -> List[str]:
    out, start = [], 0
    for m in re.finditer(r"[.!?]+[\"')\]]?(\s+)(?=[\"'(\[]?[A-Z0-9])", text):
        cand = text[start:m.start(1)].strip()
        last = cand.rsplit(" ", 1)[-1].rstrip(".!?\"')]").lower()
        if last in _ABBREV or (len(last) == 1 and last.isalpha()):
            continue
        out.append(cand)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def chunk_text(segment: str, max_len: int = 180) -> List[str]:
    """Sentence-sized pieces: speech starts fast and you can skip back/forward."""
    chunks = []
    for s in split_sentences(segment):
        while len(s) > max_len:
            cut = max(s.rfind(", ", 0, max_len), s.rfind("; ", 0, max_len), s.rfind(": ", 0, max_len))
            if cut < max_len * 0.4:
                cut = s.rfind(" ", 0, max_len)
            if cut <= 0:
                cut = max_len
            chunks.append(s[:cut + 1].strip())
            s = s[cut + 1:].strip()
        if s:
            chunks.append(s)
    return chunks


# =============================================================================================
# The recognition pipeline
# =============================================================================================

MSG_TOO_SMALL = "The text is too small. Move a little closer."
MSG_ZOOM_IN = "The text is too small. Scroll up to zoom in, or move a little closer."


@dataclasses.dataclass
class Attempt:
    method: str
    prep: Prepared
    image: np.ndarray
    paragraphs: List[List[List[Word]]]   # kept words only
    n_alnum: int
    n_words: int
    mean_conf: float
    score: float
    elapsed: float
    no_text: bool = False


@dataclasses.dataclass
class OcrOutcome:
    ok: bool
    chunks: List[str]
    gaps: List[float]                       # pause after each chunk (s)
    words: List[Tuple[str, float, Box]]     # kept words, boxes in source-frame pixels
    mean_conf: float
    n_words: int
    method: str
    elapsed: float
    frame: np.ndarray
    prepared: Optional[np.ndarray]
    sharpness: float
    brightness: float
    glare: float
    char_h: float
    layout_lines: int
    layout_chars: int
    attempts: List[str]
    diagnosis: str = ""
    cut_off: bool = False                   # text touches the frame edge (may continue outside)

    @property
    def text(self) -> str:
        out, cur = [], []
        for ch, gap in zip(self.chunks, self.gaps):
            cur.append(ch)
            if gap >= 0.4:
                out.append(" ".join(cur))
                cur = []
        if cur:
            out.append(" ".join(cur))
        return "\n".join(out)


class OcrPipeline:
    def __init__(self, cfg: ReaderConfig, engine: Tesseract):
        self.cfg = cfg
        self.engine = engine
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="tess")
        self._deadline = 0.0

    def _attempt(self, prep: Prepared, variant: str, psm: int, timeout: float) -> Attempt:
        t0 = time.monotonic()
        img = prep.gray if variant == "gray" else prep.binary()
        words = self.engine.run(img, psm, timeout=timeout)
        paragraphs = []
        for para in group_words(words, sparse=psm in (11, 12)):
            lines = [k for k in (filter_line(ln, self.cfg.min_word_conf) for ln in para) if k]
            if lines:
                paragraphs.append(lines)
        kept = [w for p in paragraphs for ln in p for w in ln]
        n = sum(alnum_count(w.text) for w in kept)
        mean = sum(alnum_count(w.text) * w.conf for w in kept) / n if n else 0.0
        score = sum(alnum_count(w.text) * (w.conf / 100.0) ** 2 for w in kept)
        name = (f"{variant}/psm{psm}" + ("" if prep.dark_text else "/inverted")
                + (f"/rot{prep.rot}" if prep.rot else ""))
        return Attempt(name, prep, img, paragraphs, n, len(kept), mean, score, time.monotonic() - t0)

    def _batch(self, prep: Prepared, plans: Sequence[Tuple[str, int]], attempts: List[Attempt]) -> Attempt:
        if any(v == "binary" for v, _ in plans):
            prep.binary()  # compute once, before the threads share it
        timeout = max(4.0, self._deadline - time.monotonic())
        futs = [self.pool.submit(self._attempt, prep, v, psm, timeout) for v, psm in plans]
        for f in futs:
            attempts.append(f.result())
        return max(attempts, key=lambda a: a.score)

    @staticmethod
    def _good(a: Attempt) -> bool:
        return a.mean_conf >= 82 and a.n_alnum >= 4

    def recognize(self, frames: Sequence[np.ndarray], distance_cm: Optional[float] = None) -> OcrOutcome:
        t0 = time.monotonic()
        deadline = self._deadline = t0 + self.cfg.max_ocr_s
        # 1. Lucky imaging: use the sharpest frame of the burst.
        ranked = sorted(((edge_sharpness(center_crop(to_gray(f))), i) for i, f in enumerate(frames)),
                        reverse=True)
        sharp, best_i = ranked[0]
        frame = frames[best_i]
        gray = to_gray(frame)
        brightness = float(gray.mean())
        glare = float((gray >= 250).mean())

        # 2. Pre-process, then try the layouts most likely to fit what we see.
        prep = prepare(frame, self.cfg)
        lay = prep.layout
        no_text = lay.n_chars < 4
        if no_text:               # nothing text-like: one quick look, then give up
            deadline = self._deadline = min(deadline, t0 + 4.0)
            plans, fallback = [("gray", 11)], []
        elif lay.n_lines >= 4:    # page / paragraph
            plans, fallback = [("gray", 3), ("binary", 6)], [("gray", 4), ("binary", 11)]
        elif lay.n_lines == 1:    # a single line: label, sign, button
            plans, fallback = [("gray", 11), ("gray", 7)], [("binary", 11), ("binary", 6)]
        else:                     # a few lines or nothing detected
            plans, fallback = [("gray", 11), ("gray", 6)], [("binary", 11), ("gray", 3)]

        attempts: List[Attempt] = []
        best = self._batch(prep, plans, attempts)
        if not self._good(best) and fallback and time.monotonic() < deadline:
            best = self._batch(prep, fallback, attempts)
        # 3. Upside down or sideways? Tesseract's orientation detector tells us how to turn it.
        if not self._good(best) and lay.n_chars >= 25 and time.monotonic() < deadline:
            rot, rconf = self.engine.orientation(prep.gray)
            if rot and rconf >= 2.0:
                best = self._batch(prep.rotated(rot), [("gray", 3), ("binary", 6)], attempts)
        # 4. Polarity was ambiguous? Try the opposite (white text on dark / dark on light).
        if (not self._good(best) and time.monotonic() < deadline
                and lay.other_polarity_chars >= 0.35 * max(1, lay.n_chars)):
            best = self._batch(prepare(frame, self.cfg, dark_text=not prep.dark_text), plans, attempts)
        # 5. Still poor? The second-sharpest frame may be luckier.
        if not self._good(best) and time.monotonic() < deadline and len(ranked) > 1:
            best = self._batch(prepare(frames[ranked[1][1]], self.cfg), plans[:1], attempts)

        best.no_text = no_text
        return self._outcome(best, attempts, frame, sharp, brightness, glare, prep,
                             time.monotonic() - t0, distance_cm)

    def _outcome(self, best: Attempt, attempts: List[Attempt], frame: np.ndarray, sharp: float,
                 brightness: float, glare: float, prep0: Prepared, elapsed: float,
                 distance_cm: Optional[float]) -> OcrOutcome:
        # Words touching the frame edge are usually cut in half ("orm had passed"): leave them
        # out and tell the user to zoom out / move back instead.
        H, W = frame.shape[:2]
        m = 0.012 * W

        def at_edge(w: Word) -> bool:
            x, y, bw, bh = best.prep.to_source(w.box)
            return x < m or y < m or x + bw > W - m or y + bh > H - m

        cut_off = False
        kept_paras: List[List[List[Word]]] = []
        for para in best.paragraphs:
            lines = []
            for ln in para:
                inside = [w for w in ln if not at_edge(w)]
                cut_off |= len(inside) < len(ln)
                if inside:
                    lines.append(inside)
            if lines:
                kept_paras.append(lines)
        if not kept_paras:          # everything touches the edge: better than nothing
            kept_paras = best.paragraphs

        chunks: List[str] = []
        gaps: List[float] = []
        paras: List[List[str]] = []
        for para in kept_paras:
            segs = compose_paragraph(para)
            # Tesseract sometimes starts a new paragraph in the middle of a sentence
            if (paras and segs and paras[-1] and segs[0][:1].islower()
                    and not re.search(r"[.!?:;]['\")]?$", paras[-1][-1])):
                paras[-1][-1] += " " + segs.pop(0)
            if segs:
                paras.append(segs)
        for segs in paras:
            for si, seg in enumerate(segs):
                pieces = chunk_text(seg)
                for pi, piece in enumerate(pieces):
                    chunks.append(piece)
                    last_piece = pi == len(pieces) - 1
                    gaps.append(0.0 if not last_piece else (0.25 if si < len(segs) - 1 else 0.45))
        words = [(w.text, w.conf, best.prep.to_source(w.box))
                 for p in kept_paras for ln in p for w in ln]
        ok = bool(chunks) and best.mean_conf >= self.cfg.min_read_conf
        # Plausibility: texture (bricks, fabric, noise) gives a few "words" out of lots of
        # character-like blobs, or words in a frame where no text was detected at all.
        if best.no_text and (best.mean_conf < 75 or best.n_alnum < 3):
            ok = False
        if best.n_alnum < 0.15 * prep0.layout.n_chars and best.mean_conf < 85:
            ok = False
        out = OcrOutcome(
            ok=ok, chunks=chunks, gaps=gaps, words=words, mean_conf=best.mean_conf,
            n_words=best.n_words, method=best.method, elapsed=elapsed, frame=frame,
            prepared=best.image, sharpness=sharp, brightness=brightness, glare=glare,
            char_h=prep0.char_h, layout_lines=prep0.layout.n_lines, layout_chars=prep0.layout.n_chars,
            attempts=[f"{a.method}:{a.mean_conf:.0f}%/{a.n_words}w" for a in attempts])
        out.cut_off = cut_off
        if not ok:
            out.diagnosis = self.diagnose(out, distance_cm)
        return out

    def diagnose(self, o: OcrOutcome, distance_cm: Optional[float]) -> str:
        if o.brightness < 45:
            return "It's too dark to read. Turn on a light or move closer to a window."
        if o.glare > 0.15:
            return "There's glare on the text. Tilt it slightly away from the light."
        if o.layout_chars < 4 and not o.chunks:
            return "I can't see any text. Point the camera at the text and hold it about 30 centimeters away."
        if distance_cm is not None and distance_cm < self.cfg.min_focus_cm:
            return "The text is too close. Move it a little farther away."
        if o.sharpness < 0.12:
            return "The picture is blurry. Hold still, or move the text a little farther away."
        if 0 < o.char_h < 12:
            return MSG_TOO_SMALL
        if o.chunks:
            return "I can only partly read this. Hold it straight and steady, in good light."
        return "I can see something like text, but can't read it. Hold it straight and steady, in good light."


# =============================================================================================
# Speech: interruptible, sentence-by-sentence reading on the Bluetooth headset
# =============================================================================================

@dataclasses.dataclass
class SpeechItem:
    text: str = ""
    cue: Optional[str] = None     # name of a short sound instead of speech
    chunk: int = -1               # index of the text chunk (for highlighting); -1 = none
    gap_s: float = 0.0            # silence after this item


def _write_tones(path: str, parts: Sequence[Tuple[float, float]], lead_s: float = 0.12,
                 amp: float = 0.6, sr: int = 22050) -> None:
    """Small WAV of (frequency, duration) tones. freq 0 = silence, -1 = soft click noise."""
    chunks = [np.zeros(int(sr * lead_s))]
    rng = np.random.default_rng(0)
    for f, dur in parts:
        t = np.arange(int(sr * dur)) / sr
        if f > 0:
            sig = np.sin(2 * np.pi * f * t)
        elif f < 0:
            sig = rng.uniform(-1, 1, len(t)) * np.exp(-t * 90)
        else:
            sig = np.zeros_like(t)
        if len(t):
            sig *= np.minimum(1, np.minimum(t, t[::-1]) / 0.008)
        chunks.append(sig)
    pcm = (np.concatenate(chunks) * amp * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


class ReaderVoice(threading.Thread):
    """
    Plays a list of SpeechItems one by one. espeak-ng renders each sentence to a WAV
    (the next sentence is rendered while the current one plays, so there are no gaps),
    played with paplay / pw-play / aplay, which send it to the default PipeWire sink:
    the Bluetooth headset. Any new request interrupts immediately; pause, resume,
    next/previous sentence and speed changes work while reading.
    """

    def __init__(self, cfg: ReaderConfig, stop_event: threading.Event):
        super().__init__(name="voice", daemon=True)
        self.cfg = cfg
        self.stop_event = stop_event
        self.tts = shutil.which("espeak-ng") or shutil.which("espeak")
        self.player = next((p for p in ("paplay", "pw-play", "aplay") if shutil.which(p)), None)
        self.enabled = cfg.audio_enabled and self.tts is not None
        self.muted = False
        self.rate = cfg.rate
        self._tmp = tempfile.mkdtemp(prefix="vantage_reader_")
        self._cond = threading.Condition()
        self._items: List[SpeechItem] = []
        self._pos = 0
        self._paused = False
        self._epoch = 0
        self._proc: Optional[subprocess.Popen] = None
        self._counter = itertools.count()
        self._cache: "collections.OrderedDict[tuple, concurrent.futures.Future]" = collections.OrderedDict()
        self._synth_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")
        self.active_chunk = -1
        self.last_text = ""
        self.last_audio_at = 0.0
        self.cues = {}
        for name, parts, lead in (
                ("shutter", [(-1, 0.05), (0, 0.04), (-1, 0.05)], 0.15),
                ("done", [(660, 0.08), (0, 0.03), (495, 0.12)], 0.05),
                ("error", [(330, 0.12), (0, 0.04), (262, 0.2)], 0.15),
                ("lead", [(0, 0.35)], 0.0)):
            path = os.path.join(self._tmp, f"cue_{name}.wav")
            _write_tones(path, parts, lead)
            self.cues[name] = path

    # -- public API (thread-safe) -----------------------------------------------------------

    def play(self, items: Sequence[SpeechItem]) -> None:
        """Replace whatever is playing with `items`."""
        if not self.enabled or self.muted:
            return
        with self._cond:
            self._items = list(items)
            self._pos = 0
            self._paused = False
            self._interrupt_locked()
            self._cond.notify_all()
        for it in items[:3]:
            self._prefetch(it)

    def say(self, text: str, cue: Optional[str] = None) -> None:
        items = [SpeechItem(cue=cue)] if cue else []
        self.play(items + [SpeechItem(text=text)])

    def cue(self, name: str) -> None:
        self.play([SpeechItem(cue=name)])

    def stop_reading(self) -> None:
        with self._cond:
            self._items, self._pos, self._paused = [], 0, False
            self._interrupt_locked()
            self.active_chunk = -1
            self._cond.notify_all()

    def toggle_pause(self) -> Optional[bool]:
        with self._cond:
            if not self._items:
                return None
            self._paused = not self._paused
            if self._paused:
                self._interrupt_locked()   # resume restarts the current sentence
            self._cond.notify_all()
            return self._paused

    def skip(self, delta: int) -> None:
        """Jump to the next (+1) or previous (-1) sentence."""
        with self._cond:
            chunk_pos = [i for i, it in enumerate(self._items) if it.chunk >= 0]
            if not chunk_pos:
                return
            cur = max([i for i in chunk_pos if i <= self._pos] or [chunk_pos[0]])
            k = chunk_pos.index(cur) + delta
            k = max(0, min(len(chunk_pos) - 1, k))
            self._pos = chunk_pos[k]
            self._paused = False
            self._interrupt_locked()
            self._cond.notify_all()

    def change_rate(self, delta: int) -> int:
        self.rate = int(max(80, min(320, self.rate + delta)))
        return self.rate

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted:
            self.stop_reading()
        return self.muted

    @property
    def busy(self) -> bool:
        with self._cond:
            return bool(self._items) and self._pos < len(self._items)

    @property
    def paused(self) -> bool:
        return self._paused

    def shutdown(self) -> None:
        self.stop_reading()
        with self._cond:
            self._cond.notify_all()
        self._synth_pool.shutdown(wait=False, cancel_futures=True)

    # -- internals ----------------------------------------------------------------------------

    def _interrupt_locked(self) -> None:
        self._epoch += 1
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    def _prefetch(self, item: SpeechItem) -> Optional[concurrent.futures.Future]:
        if item.cue or not item.text or not self.tts or self.player is None:
            return None
        key = (item.text, self.rate, self.cfg.voice)
        fut = self._cache.get(key)
        if fut is not None:
            self._cache.move_to_end(key)
            return fut
        fut = self._synth_pool.submit(self._synth, item.text, self.rate)
        self._cache[key] = fut
        while len(self._cache) > 80:
            _, old = self._cache.popitem(last=False)
            if old.done() and old.result():
                try:
                    os.remove(old.result())
                except OSError:
                    pass
        return fut

    def _synth(self, text: str, rate: int) -> Optional[str]:
        path = os.path.join(self._tmp, f"s{next(self._counter)}.wav")
        cmd = [self.tts, "-v", self.cfg.voice, "-s", str(rate), "-a", str(self.cfg.volume),
               "-w", path, "--stdin"]
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=20,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return path
        except (subprocess.SubprocessError, OSError) as exc:
            LOG.warning("TTS failed: %s", exc)
            return None

    def _run_player(self, cmd: List[str], epoch: int) -> bool:
        with self._cond:
            if self._epoch != epoch:
                return False
            try:
                self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as exc:
                LOG.warning("audio player failed: %s", exc)
                return True
            proc = self._proc
        while proc.poll() is None and not self.stop_event.is_set():
            try:
                proc.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            proc.terminate()
        with self._cond:
            self._proc = None
            self.last_audio_at = time.monotonic()
            return self._epoch == epoch

    def _play_item(self, item: SpeechItem, epoch: int) -> bool:
        if self.player is None:  # no WAV player: let espeak speak directly
            if item.text:
                return self._run_player([self.tts, "-v", self.cfg.voice, "-s", str(self.rate),
                                         "-a", str(self.cfg.volume), item.text], epoch)
            return True
        if item.cue:
            path = self.cues.get(item.cue)
        else:
            fut = self._prefetch(item)
            try:
                path = fut.result(timeout=25) if fut else None
            except Exception:  # noqa: BLE001
                path = None
        if not path:
            return True
        cmd = {"paplay": ["paplay", path], "pw-play": ["pw-play", path]}.get(self.player, ["aplay", "-q", path])
        return self._run_player(cmd, epoch)

    def run(self) -> None:
        while not self.stop_event.is_set():
            with self._cond:
                while not self.stop_event.is_set() and (self._paused or self._pos >= len(self._items)):
                    if self._items and self._pos >= len(self._items):
                        self._items, self._pos = [], 0     # finished reading
                        self.active_chunk = -1
                    self._cond.wait(0.2)
                if self.stop_event.is_set():
                    break
                pos, item, epoch = self._pos, self._items[self._pos], self._epoch
                if item.chunk >= 0:
                    self.active_chunk = item.chunk
                nxt = self._items[pos + 1] if pos + 1 < len(self._items) else None
            if nxt is not None:
                self._prefetch(nxt)
            if item.text:
                self.last_text = item.text
                LOG.info("SAY: %s", item.text)
            completed = self._play_item(item, epoch)
            with self._cond:
                if completed and item.gap_s > 0:
                    self._cond.wait_for(lambda: self._epoch != epoch or self.stop_event.is_set(),
                                        timeout=item.gap_s)
                if self._epoch == epoch:   # not interrupted or replaced meanwhile
                    self._pos = pos + 1
        shutil.rmtree(self._tmp, ignore_errors=True)


# =============================================================================================
# Cameras
# =============================================================================================

CAMERA_STUCK_MSG = """
The camera stopped sending pictures (look for "Remote I/O error" above). This is the camera
hardware/driver, not the reader. To recover:
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


class PiCamera:
    """The Raspberry Pi AI Camera (IMX500) used as a plain high-resolution camera."""

    def __init__(self, cfg: ReaderConfig):
        self.cfg = cfg
        self.picam2 = None
        self.size = (cfg.width, cfg.height)
        self.name = "camera"
        self.lossless_zoom = 1.0      # zoom you get before pixels are just enlarged
        self._base_crop: Optional[Tuple[int, int, int, int]] = None
        self._zoom = 1.0
        self._zoom_dirty = False

    def start(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError("picamera2 is not installed:  sudo apt install python3-picamera2") from exc
        try:
            from libcamera import Transform, controls
        except ImportError:
            Transform, controls = None, None

        num = self.cfg.camera_num
        if num is None:
            num = 0
            try:
                for i, info in enumerate(Picamera2.global_camera_info()):
                    if "imx500" in str(info.get("Model", "")).lower():
                        num = int(info.get("Num", i))
                        break
            except Exception:  # noqa: BLE001
                pass
        try:
            self.picam2 = Picamera2(num)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Could not open camera {num}: {exc}\n"
                               "If vantage_core.py is running, stop it first - only one program "
                               "can use the camera at a time.") from exc
        extra = {}
        if self.cfg.rotate_180 and Transform is not None:
            extra["transform"] = Transform(hflip=1, vflip=1)
        main = {"size": self.size, "format": "RGB888"}  # BGR byte order: ready for OpenCV
        configured = False
        full = tuple(self.picam2.camera_properties.get("PixelArraySize", (0, 0)))
        if self.cfg.full_sensor and full[0] > self.size[0]:
            # Read the whole 12 MP sensor (about 10 fps) and let the ISP scale it down. Zooming
            # then crops real sensor pixels: 2x zoom on a 2028-wide output is still pixel-sharp.
            try:
                self.picam2.configure(self.picam2.create_preview_configuration(
                    main=main, sensor={"output_size": full}, buffer_count=3, **extra))
                configured = True
                self.lossless_zoom = full[0] / self.size[0]
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Full-sensor mode not available (%s); using the default mode", exc)
        if not configured:
            self.picam2.configure(self.picam2.create_preview_configuration(main=main, buffer_count=3, **extra))
        self.picam2.start()
        self.size = tuple(self.picam2.camera_configuration()["main"]["size"])
        self.name = f"camera {num}"
        self._set_controls(controls)
        LOG.info("Camera %d started at %dx%d", num, *self.size)

    def _set_controls(self, controls) -> None:
        cc = self.picam2.camera_controls
        ctrls = {}
        try:
            if controls is not None:
                if "AeExposureMode" in cc:   # prefer short exposures: less motion blur
                    ctrls["AeExposureMode"] = controls.AeExposureModeEnum.Short
                if "AfMode" in cc:           # only cameras with autofocus (not the AI Camera)
                    ctrls["AfMode"] = controls.AfModeEnum.Continuous
                if "NoiseReductionMode" in cc:
                    ctrls["NoiseReductionMode"] = controls.draft.NoiseReductionModeEnum.HighQuality
            if "Sharpness" in cc:
                ctrls["Sharpness"] = 1.3
            if ctrls:
                self.picam2.set_controls(ctrls)
        except Exception as exc:  # noqa: BLE001 - nice to have, never fatal
            LOG.warning("Could not set camera controls %s: %s", list(ctrls), exc)

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._zoom_dirty = True

    def _apply_zoom(self) -> None:
        bx, by, bw, bh = self._base_crop
        w = int(bw / self._zoom) & ~1
        h = int(bh / self._zoom) & ~1
        crop = (bx + (bw - w) // 2, by + (bh - h) // 2, w, h)   # centred, same aspect ratio
        try:
            self.picam2.set_controls({"ScalerCrop": crop})
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Zoom failed: %s", exc)
        self._zoom_dirty = False

    def read(self) -> Tuple[np.ndarray, dict]:
        req = self.picam2.capture_request()
        try:
            frame = req.make_array("main")
            md = req.get_metadata()
        finally:
            req.release()
        if self._base_crop is None and md.get("ScalerCrop"):
            self._base_crop = tuple(int(v) for v in md["ScalerCrop"])  # the un-zoomed field of view
        if self._zoom_dirty and self._base_crop:
            self._apply_zoom()
        return frame, md

    def stop(self) -> None:
        if self.picam2 is not None:
            cam, self.picam2 = self.picam2, None
            stop_camera_safely(cam, LOG)


# --- synthetic scenes (used by --simulate and --self-test) ------------------------------------

SAMPLE_PAGE = [
    "Chapter 3: The Lighthouse",
    "",
    "The storm had passed by the time the boat reached the",
    "harbour. Maria tied the rope to the old iron ring and",
    "looked up at the lighthouse, its lamp still turning",
    "slowly against the grey morning sky.",
    "",
    "Nobody had lived there for twenty years, but every",
    "night the light came on at exactly nine o'clock.",
]
SAMPLE_SIGN = ["PLATFORM 3", "Trains to Central Station", "Next departure 10:45"]
SAMPLE_LABEL = ["Paracetamol 500 mg", "Take 1 or 2 tablets every", "4 to 6 hours. Do not take",
                "more than 8 tablets in 24 hours."]

_FONTS = {
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"],
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
}


def render_text_card(lines: Sequence[str], font_px: int, fg=(30, 30, 30), bg=(218, 228, 232),
                     serif: bool = True) -> np.ndarray:
    """Render text onto a card (BGR). Uses a TrueType font if Pillow is available."""
    margin = int(font_px * 1.2)
    line_h = int(font_px * 1.45)
    try:
        from PIL import Image, ImageDraw, ImageFont
        path = next((p for p in _FONTS[serif] if os.path.exists(p)), None)
        if path is None:
            raise ImportError
        font = ImageFont.truetype(path, font_px)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        W = int(max(probe.textlength(t, font=font) for t in lines if t) + 2 * margin)
        H = line_h * len(lines) + 2 * margin
        img = Image.new("RGB", (W, H), tuple(int(c) for c in bg[::-1]))
        draw = ImageDraw.Draw(img)
        for i, t in enumerate(lines):
            draw.text((margin, margin + i * line_h), t, font=font, fill=tuple(int(c) for c in fg[::-1]))
        return np.array(img)[:, :, ::-1].copy()
    except ImportError:
        scale = font_px / 30.0
        thick = max(1, font_px // 14)
        W = int(max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)[0][0] for t in lines if t)) + 2 * margin
        H = line_h * len(lines) + 2 * margin
        img = np.full((H, W, 3), bg, np.uint8)
        for i, t in enumerate(lines):
            cv2.putText(img, t, (margin, margin + i * line_h + font_px), cv2.FONT_HERSHEY_SIMPLEX,
                        scale, fg, thick, cv2.LINE_AA)
        return img


def compose_scene(card: np.ndarray, size: Tuple[int, int], angle: float = 0.0,
                  offset: Tuple[float, float] = (0, 0), desk=(70, 80, 90), shadow: float = 0.0,
                  dim: float = 1.0) -> np.ndarray:
    """Place a text card on a 'desk', rotated, with a light falloff from one side."""
    W, H = size
    ch, cw = card.shape[:2]
    s = min(1.0, 0.9 * W / cw, 0.9 * H / ch)
    M = cv2.getRotationMatrix2D((cw / 2, ch / 2), angle, s)
    M[0, 2] += W / 2 - cw / 2 + offset[0]
    M[1, 2] += H / 2 - ch / 2 + offset[1]
    warped = cv2.warpAffine(card, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    mask = cv2.warpAffine(np.full((ch, cw), 255, np.uint8), M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
    a = mask[..., None].astype(np.float32) / 255.0
    out = warped.astype(np.float32) * a + np.array(desk, np.float32) * (1 - a)
    if shadow > 0:
        out *= np.linspace(1 - shadow, 1.0, W, dtype=np.float32)[None, :, None]
    if dim != 1.0:
        out *= dim
    return np.clip(out, 0, 255).astype(np.uint8)


def degrade(img: np.ndarray, blur: float = 0.0, noise: float = 0.0,
            rng: Optional[np.random.Generator] = None) -> np.ndarray:
    out = cv2.GaussianBlur(img, (0, 0), blur) if blur > 0.05 else img
    if noise > 0:
        rng = rng or np.random.default_rng(0)
        out = np.clip(out.astype(np.int16) + rng.normal(0, noise, out.shape).astype(np.int16), 0, 255).astype(np.uint8)
    return out


class SimCamera:
    """Scripted scenes to try the reader without hardware: desk -> page -> desk -> sign."""

    def __init__(self, cfg: ReaderConfig):
        self.cfg = cfg
        self.size = (cfg.width, cfg.height)
        self.name = "simulated camera"
        self.rng = np.random.default_rng(1)
        W, H = self.size
        desk = np.zeros((H, W, 3), np.uint8)
        desk[:] = (70, 80, 90)
        page = render_text_card(SAMPLE_PAGE, font_px=max(14, W // 64))
        sign = render_text_card(SAMPLE_SIGN, font_px=max(20, W // 30), fg=(240, 240, 240), bg=(110, 60, 20),
                                serif=False)
        self.scenes = [("desk", 3.0, desk, 0.0),
                       ("page", 11.0, compose_scene(page, self.size, angle=2.0, shadow=0.3), 0.0),
                       ("desk", 3.0, desk, 0.0),
                       ("sign", 9.0, compose_scene(sign, self.size, angle=-3.0), 0.0)]
        self.total = sum(s[1] for s in self.scenes)
        self.noise = [self.rng.normal(0, 4, (H, W, 3)).astype(np.int16) for _ in range(3)]
        self._t0 = 0.0
        self._next = 0.0
        self.zoom = 1.0
        self.lossless_zoom = 1.0

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._next = self._t0

    def read(self) -> Tuple[np.ndarray, dict]:
        now = time.monotonic()
        if self._next > now:
            time.sleep(self._next - now)
        self._next = max(now, self._next) + 1 / 12.0
        t = (time.monotonic() - self._t0) % self.total
        for name, dur, base, _ in self.scenes:
            if t < dur:
                break
            t -= dur
        img = base
        if name != "desk":
            if t < 1.6:   # bringing the text into view: shaky and out of focus
                dx, dy = self.rng.normal(0, 25, 2)
                M = np.float32([[1, 0, dx], [0, 1, dy]])
                img = cv2.warpAffine(base, M, self.size, borderValue=(70, 80, 90))
                img = cv2.GaussianBlur(img, (0, 0), 3.0 * (1.6 - t) + 0.3)
            else:
                img = cv2.GaussianBlur(base, (0, 0), 0.6)
        if self.zoom > 1.001:
            W, H = self.size
            w, h = int(W / self.zoom), int(H / self.zoom)
            x, y = (W - w) // 2, (H - h) // 2
            img = cv2.resize(img[y:y + h, x:x + w], (W, H), interpolation=cv2.INTER_LINEAR)
        noisy = np.clip(img.astype(np.int16) + self.noise[int(t * 12) % 3], 0, 255).astype(np.uint8)
        return noisy, {"ExposureTime": 16000, "AnalogueGain": 2.0}

    def stop(self) -> None:
        pass


# =============================================================================================
# USB mouse: scroll wheel = zoom, buttons = read / stop / reset zoom
# =============================================================================================

class MouseInput(threading.Thread):
    """
    Reads USB mice straight from /dev/input/event* (Linux evdev). No extra packages, works
    whether or not the preview window has focus, and survives unplugging / re-plugging.
    """

    EV_KEY, EV_REL = 0x01, 0x02
    REL_WHEEL = 0x08
    BUTTONS = {0x110: "left", 0x111: "right", 0x112: "middle", 0x113: "side", 0x114: "extra"}
    EVENT = struct.Struct("llHHi")       # struct input_event: timeval, type, code, value
    EVIOCGRAB = 0x40044590

    def __init__(self, on_scroll: Callable[[int], None], on_button: Callable[[str], None],
                 stop_event: threading.Event, grab: bool = False, paths: Sequence[str] = ()):
        super().__init__(name="mouse", daemon=True)
        self.on_scroll = on_scroll
        self.on_button = on_button
        self.stop_event = stop_event
        self.grab = grab
        self.paths = list(paths)
        self._fds: Dict[str, int] = {}
        self._buf: Dict[int, bytes] = {}
        self._warned = False
        self.names: List[str] = []

    @staticmethod
    def find_mice() -> List[Tuple[str, str]]:
        """(device path, name) of every input device the kernel lists as a mouse."""
        try:
            with open("/proc/bus/input/devices", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            return []
        mice = []
        for block in text.split("\n\n"):
            handlers = re.search(r"H: Handlers=([^\n]*)", block)
            if not handlers:
                continue
            hs = handlers.group(1).split()
            event = next((h for h in hs if h.startswith("event")), None)
            if event and any(h.startswith("mouse") for h in hs):
                name = re.search(r'N: Name="([^"]*)"', block)
                mice.append(("/dev/input/" + event, name.group(1) if name else event))
        return mice

    def _open_new(self) -> None:
        found = [(p, os.path.basename(p)) for p in self.paths] if self.paths else self.find_mice()
        for path, name in found:
            if path in self._fds:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                if not self._warned:
                    self._warned = True
                    LOG.warning("No permission to read the mouse (%s). Run:  sudo usermod -aG input $USER  "
                                "then log out and back in.", path)
                continue
            except OSError:
                continue
            if self.grab:
                try:
                    import fcntl
                    fcntl.ioctl(fd, self.EVIOCGRAB, 1)
                except OSError:
                    pass
            self._fds[path] = fd
            self.names.append(name)
            LOG.info("Mouse: %s  (scroll = zoom, left = read, right = stop/repeat, middle = reset zoom)", name)

    def _close(self, path: str) -> None:
        fd = self._fds.pop(path, None)
        if fd is not None:
            self._buf.pop(fd, None)
            try:
                os.close(fd)
            except OSError:
                pass

    def _dispatch(self, data: bytes) -> None:
        size = self.EVENT.size
        wheel = 0
        for i in range(len(data) // size):
            _, _, etype, code, value = self.EVENT.unpack_from(data, i * size)
            if etype == self.EV_REL and code == self.REL_WHEEL:
                wheel += value                        # +1 per notch away from you
            elif etype == self.EV_KEY and value == 1 and code in self.BUTTONS:
                self.on_button(self.BUTTONS[code])
        if wheel:
            self.on_scroll(wheel)

    def run(self) -> None:
        next_scan = 0.0
        while not self.stop_event.is_set():
            now = time.monotonic()
            if now >= next_scan:                       # pick up mice plugged in later
                self._open_new()
                next_scan = now + 2.0
            if not self._fds:
                self.stop_event.wait(0.5)
                continue
            try:
                ready, _, _ = select.select(list(self._fds.values()), [], [], 0.25)
            except (OSError, ValueError):
                ready = []
            for path, fd in list(self._fds.items()):
                if fd not in ready:
                    continue
                try:
                    data = os.read(fd, self.EVENT.size * 64)
                except BlockingIOError:
                    continue
                except OSError:                        # unplugged
                    LOG.info("Mouse disconnected: %s", path)
                    self._close(path)
                    continue
                if not data:
                    self._close(path)
                    continue
                data = self._buf.pop(fd, b"") + data
                cut = len(data) - len(data) % self.EVENT.size
                if cut < len(data):
                    self._buf[fd] = data[cut:]
                self._dispatch(data[:cut])
        for path in list(self._fds):
            self._close(path)


# =============================================================================================
# Terminal keys (so it works over SSH / without the preview window too)
# =============================================================================================

class TerminalKeys(threading.Thread):
    def __init__(self, on_key: Callable[[str], None], stop_event: threading.Event):
        super().__init__(name="keys", daemon=True)
        self.on_key = on_key
        self.stop_event = stop_event
        self.fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        self._old = None

    def start(self) -> None:
        if self.fd is None:
            return
        import termios
        import tty
        self._old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)   # single key presses, Ctrl+C still works
        super().start()

    def run(self) -> None:
        while not self.stop_event.is_set():
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if r:
                ch = os.read(self.fd, 1).decode(errors="ignore")
                if ch:
                    self.on_key(ch)

    def restore(self) -> None:
        if self._old is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old)
            self._old = None


# =============================================================================================
# The reader application
# =============================================================================================

PREVIEW_W = 960      # analysis resolution for the live view
DISPLAY_W = 640      # preview window: camera view width ...
PANEL_W = 440        # ... plus the text panel
FONT = cv2.FONT_HERSHEY_SIMPLEX if cv2 is not None else 0
HELP = ("SPACE/left-click read | scroll or i/o zoom | 0 or middle-click zoom 1x | r repeat | p pause | "
        "x or right-click stop | n/b next/back | +/- speed | a auto | m mute | q quit")


def conf_color(conf: float) -> Tuple[int, int, int]:
    if conf >= 80:
        return (80, 210, 80)
    if conf >= 60:
        return (0, 200, 255)
    return (0, 120, 255)


def wrap_px(text: str, max_w: int, scale: float, thick: int = 1) -> List[str]:
    lines, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if cv2.getTextSize(t, FONT, scale, thick)[0][0] <= max_w:
            cur = t
            continue
        if cur:
            lines.append(cur)
        cur = word
        while cv2.getTextSize(cur, FONT, scale, thick)[0][0] > max_w and len(cur) > 4:
            lines.append(cur[:len(cur) // 2])
            cur = cur[len(cur) // 2:]
    if cur:
        lines.append(cur)
    return lines


def annotate(frame: np.ndarray, words: Sequence[Tuple[str, float, Box]]) -> np.ndarray:
    img = frame.copy()
    th = max(1, frame.shape[1] // 800)
    for text, conf, (x, y, w, h) in words:
        cv2.rectangle(img, (x, y), (x + w, y + h), conf_color(conf), th + 1)
        cv2.putText(img, f"{ascii_safe(text)} {conf:.0f}", (x, max(12, y - 4)), FONT, 0.4 * th + 0.2,
                    conf_color(conf), th, cv2.LINE_AA)
    return img


def save_debug(dirpath: str, outcome: OcrOutcome, tag: str) -> str:
    os.makedirs(dirpath, exist_ok=True)
    base = os.path.join(dirpath, f"{time.strftime('%Y%m%d_%H%M%S')}_{tag}")
    cv2.imwrite(base + "_frame.jpg", outcome.frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(base + "_result.jpg", annotate(outcome.frame, outcome.words), [cv2.IMWRITE_JPEG_QUALITY, 85])
    if outcome.prepared is not None:
        cv2.imwrite(base + "_prepared.png", outcome.prepared)
    with open(base + "_text.txt", "w", encoding="utf-8") as fh:
        fh.write(outcome.text + "\n\n")
        fh.write(json.dumps({
            "ok": outcome.ok, "mean_conf": round(outcome.mean_conf, 1), "words": outcome.n_words,
            "method": outcome.method, "elapsed_s": round(outcome.elapsed, 2),
            "sharpness": round(outcome.sharpness, 3), "brightness": round(outcome.brightness, 1),
            "glare": round(outcome.glare, 3), "char_height_px": round(outcome.char_h, 1),
            "layout_lines": outcome.layout_lines, "attempts": outcome.attempts,
            "diagnosis": outcome.diagnosis,
            "word_conf": [[t, round(c, 1)] for t, c, _ in outcome.words]}, indent=1))
    return base


def describe_outcome(o: OcrOutcome) -> str:
    head = (f"OCR {o.elapsed:.1f}s | conf {o.mean_conf:.0f}% | {o.n_words} words | {o.method} | "
            f"sharp {o.sharpness:.2f} | letters {o.char_h:.0f}px")
    if o.ok:
        body = "\n".join("    " + ln for ln in o.text.splitlines())
        return f"{head}\n{body}"
    return f"{head}\n    (not read) {o.diagnosis}"


class ReaderApp:
    def __init__(self, cfg: ReaderConfig):
        self.cfg = cfg
        self.stop_event = threading.Event()
        self.engine = Tesseract(cfg)
        self.pipeline = OcrPipeline(cfg, self.engine)
        self.voice = ReaderVoice(cfg, self.stop_event)
        core_cfg = vc.Config(bt_mac=cfg.bt_mac, serial_port=cfg.serial_port)
        self.bt = vc.BluetoothMonitor(core_cfg, self.stop_event)
        self.lidar = None
        if cfg.use_lidar:
            self.lidar = (vc.SimulatedLidar if cfg.simulate else vc.LidarReader)(core_cfg, self.stop_event)
        self.camera = SimCamera(cfg) if cfg.simulate else PiCamera(cfg)
        self.streamer = vc.MjpegStreamer(cfg.stream_port) if cfg.stream_port else None
        self.keys = TerminalKeys(self.handle_key, self.stop_event)
        self.mouse = (MouseInput(self._on_scroll, self._on_mouse_button, self.stop_event,
                                 grab=cfg.mouse_grab, paths=cfg.mouse_devices) if cfg.mouse else None)
        self.ocr_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        self.fps = vc.RateMeter()
        self._lock = threading.Lock()
        self.auto = cfg.auto
        self._t_start = time.monotonic()
        self._window_open = False
        # live analysis
        self._prev_thumb: Optional[np.ndarray] = None
        self._layout: Optional[TextLayout] = None
        self._sharp = 0.0
        self._motion = 99.0
        self._brightness = 0.0
        self._exposure_ms = 0.0
        self._frame_no = 0
        self._steady_since: Optional[float] = None
        self._absent_since: Optional[float] = None
        # capture / recognition
        self._manual_request = False
        self._capturing = False
        self._capture_manual = False
        self._burst: List[np.ndarray] = []
        self._burst_t0 = 0.0
        self._busy = False
        self._trigger_thumb: Optional[np.ndarray] = None
        self._trigger_at = 0.0
        self._rearmed = True
        self._fail_retries = 0
        # results
        self._result: Optional[OcrOutcome] = None
        self._result_at = 0.0
        self._result_thumb: Optional[np.ndarray] = None
        self._read_history: "collections.deque[Tuple[str, float]]" = collections.deque(maxlen=300)
        self._guidance = ""
        self._guidance_at = 0.0
        self._guidance_spoken_at = -1e9
        self._last_outcome_ok = True
        # zoom
        self.zoom = 1.0
        self._zoom_steps = 0
        self._zoom_reset = False
        self._zoom_changed_at = 0.0
        self._zoom_announced = True

    # -- key handling ----------------------------------------------------------------------------

    def handle_key(self, ch: str) -> None:
        k = ch.lower()
        if k in (" ", "\n", "\r"):
            self._manual_request = True
        elif k == "r":
            self._repeat()
        elif k == "p":
            st = self.voice.toggle_pause()
            if st is not None:
                LOG.info("Paused" if st else "Resumed")
        elif k == "x":
            self.voice.stop_reading()
        elif k == "n":
            self.voice.skip(+1)
        elif k == "b":
            self.voice.skip(-1)
        elif k in ("+", "="):
            LOG.info("Speech rate %d wpm", self.voice.change_rate(+15))
        elif k in ("-", "_"):
            LOG.info("Speech rate %d wpm", self.voice.change_rate(-15))
        elif k == "a":
            self.auto = not self.auto
            LOG.info("Auto reading %s", "ON" if self.auto else "OFF (press SPACE to read)")
            self.voice.say("Auto reading on" if self.auto else "Auto reading off")
        elif k == "m":
            LOG.info("Audio %s", "muted" if self.voice.toggle_mute() else "unmuted")
        elif k == "i":
            self._on_scroll(+1)
        elif k == "o":
            self._on_scroll(-1)
        elif k == "0":
            self._zoom_reset = True
        elif k in ("q", "\x1b"):
            self.stop_event.set()

    # -- mouse & zoom -----------------------------------------------------------------------------

    def _on_scroll(self, notches: int) -> None:
        with self._lock:
            self._zoom_steps += notches

    def _on_mouse_button(self, button: str) -> None:
        if button == "left":
            self._manual_request = True
        elif button == "right":
            if self.voice.busy:
                self.voice.stop_reading()
            else:
                self._repeat()
        elif button == "middle":
            self._zoom_reset = True

    def _update_zoom(self, now: float) -> None:
        with self._lock:
            steps, self._zoom_steps = self._zoom_steps, 0
        reset, self._zoom_reset = self._zoom_reset, False
        if steps or reset:
            z = 1.0 if reset else self.zoom * (self.cfg.zoom_step ** steps)
            z = float(np.clip(z, 1.0, max(1.0, self.cfg.zoom_max)))
            if abs(z - self.zoom) > 1e-3:
                self.zoom = z
                self.camera.set_zoom(z)
                self._zoom_changed_at = now
                self._zoom_announced = False
            return
        # Once the wheel has stopped, say the new zoom (unless it would interrupt reading).
        if not self._zoom_announced and now - self._zoom_changed_at > 0.8:
            self._zoom_announced = True
            LOG.info("Zoom %.1fx", self.zoom)
            if not self.voice.busy:
                level = f"{self.zoom:.1f}".rstrip("0").rstrip(".")
                self.voice.say("Zoom off" if self.zoom < 1.05 else f"Zoom {level} times")

    def _repeat(self) -> None:
        with self._lock:
            res = self._result
        if res and res.ok:
            self.voice.play(self._items_for(res, list(range(len(res.chunks)))))
        elif res and res.diagnosis:
            self.voice.say(res.diagnosis)

    # -- speech helpers --------------------------------------------------------------------------

    def _items_for(self, o: OcrOutcome, indices: Sequence[int], prefix: str = "") -> List[SpeechItem]:
        items: List[SpeechItem] = []
        # Bluetooth headsets go to sleep after a few silent seconds and clip the first word.
        if time.monotonic() - self.voice.last_audio_at > 3.0:
            items.append(SpeechItem(cue="lead"))
        if prefix:
            items.append(SpeechItem(text=prefix, gap_s=0.1))
        for i in indices:
            items.append(SpeechItem(text=o.chunks[i], chunk=i, gap_s=o.gaps[i] or 0.05))
        items.append(SpeechItem(cue="done"))
        return items

    def _guide(self, msg: str, speak: bool) -> None:
        now = time.monotonic()
        self._guidance, self._guidance_at = msg, now
        if speak and now - self._guidance_spoken_at > 12.0:
            self._guidance_spoken_at = now
            self.voice.say(msg, cue="error")

    # -- capture & recognition -------------------------------------------------------------------

    def _start_capture(self, manual: bool, thumb: np.ndarray, now: float) -> None:
        self._capturing, self._capture_manual = True, manual
        self._burst, self._burst_t0 = [], now
        self._trigger_thumb, self._trigger_at = thumb, now
        self._rearmed = False
        self.voice.cue("shutter")
        LOG.info("Capturing (%s)...", "button" if manual else "auto")

    def _submit(self) -> None:
        frames = self._burst
        self._burst, self._capturing, self._busy = [], False, True
        dist = None
        if self.lidar is not None:
            s = self.lidar.latest()
            dist = s.distance_cm if s and s.valid else None
        self.ocr_pool.submit(self._ocr_job, frames, self._capture_manual, dist)

    def _ocr_job(self, frames: List[np.ndarray], manual: bool, dist: Optional[float]) -> None:
        try:
            outcome = self.pipeline.recognize(frames, dist)
            self._handle_outcome(outcome, manual)
        except Exception:  # noqa: BLE001
            LOG.exception("Recognition failed")
            self.voice.say("Sorry, the reader had an error.", cue="error")
        finally:
            self._busy = False

    def _new_chunks(self, o: OcrOutcome, now: float) -> List[int]:
        """Chunks not already read recently (when you move along a page, read only new lines)."""
        recent = [t for t, at in self._read_history if now - at < self.cfg.repeat_after_s]
        fresh = []
        for i, ch in enumerate(o.chunks):
            n = norm_for_compare(ch)
            if not any(difflib.SequenceMatcher(None, n, r).ratio() >= 0.8 for r in recent):
                fresh.append(i)
        return fresh

    def _handle_outcome(self, o: OcrOutcome, manual: bool) -> None:
        now = time.monotonic()
        with self._lock:
            self._result, self._result_at = o, now
            self._result_thumb = self._trigger_thumb
        LOG.info(describe_outcome(o))
        if self.cfg.save_debug:
            LOG.info("debug images: %s_*", save_debug(self.cfg.save_debug, o, "manual" if manual else "auto"))
        self._last_outcome_ok = o.ok
        if o.diagnosis == MSG_TOO_SMALL and self.zoom < self.cfg.zoom_max - 0.05:
            o.diagnosis = MSG_ZOOM_IN
        if not o.ok:
            self._fail_retries += 1
            # Auto mode stays quiet unless it keeps failing on something that clearly is text.
            self._guide(o.diagnosis, speak=manual or (self._fail_retries >= 2 and o.layout_chars >= 25))
            return
        self._fail_retries = 0
        self._guidance = ""
        indices = list(range(len(o.chunks))) if manual else self._new_chunks(o, now)
        if not indices:
            LOG.info("(already read - point at new text, or press r to repeat)")
            return
        for i in indices:
            self._read_history.append((norm_for_compare(o.chunks[i]), now))
        prefix = "Not sure, but it says:" if o.mean_conf < self.cfg.sure_conf else ""
        items = self._items_for(o, indices, prefix)
        if o.cut_off:
            hint = ("Text goes past the edge, scroll down to zoom out." if self.zoom > 1.05
                    else "Text goes past the edge, move back a little.")
            items.insert(1 if items and items[0].cue == "lead" else 0, SpeechItem(text=hint, gap_s=0.2))
            self._guidance, self._guidance_at = hint, now
        self.voice.play(items)

    # -- per-frame logic -------------------------------------------------------------------------

    def _tick(self, frame: np.ndarray, md: dict) -> Tuple[np.ndarray, np.ndarray]:
        now = time.monotonic()
        self.fps.tick(now)
        self._frame_no += 1
        self._update_zoom(now)
        H, W = frame.shape[:2]
        small = cv2.resize(frame, (PREVIEW_W, int(PREVIEW_W * H / W)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        thumb = cv2.resize(gray, (64, 48), interpolation=cv2.INTER_AREA).astype(np.int16)
        if self._prev_thumb is not None:
            self._motion = float(np.mean(np.abs(thumb - self._prev_thumb)))
        self._prev_thumb = thumb
        self._brightness = float(gray.mean())
        self._exposure_ms = float(md.get("ExposureTime", 0)) / 1000.0

        if self._capturing:
            self._burst.append(frame)
            if len(self._burst) >= max(1, self.cfg.burst) or now - self._burst_t0 > 1.5:
                self._submit()
            return small, thumb

        # Text detection: every other frame while looking for text, less often while busy.
        idle = not (self._busy or self.voice.busy)
        if self._layout is None or (idle and self._frame_no % 2 == 0) or self._frame_no % 6 == 0:
            self._layout = find_text(gray)
        if self._frame_no % 3 == 0:
            self._sharp = edge_sharpness(center_crop(to_gray(frame)))

        lay = self._layout
        text_present = lay is not None and lay.n_chars >= 8
        if text_present:
            self._absent_since = None
        else:
            self._absent_since = self._absent_since or now
            if now - self._absent_since > 1.5:
                self._rearmed = True       # text went away: the next text is new
        if text_present and self._motion < self.cfg.motion_thresh:
            self._steady_since = self._steady_since or now
        else:
            self._steady_since = None

        if self._manual_request:
            self._manual_request = False
            if not self._busy:
                self._start_capture(True, thumb, now)
            return small, thumb

        if self.auto and not self._busy and self._steady_since and now - self._steady_since >= self.cfg.steady_s:
            changed = (self._trigger_thumb is None
                       or float(np.mean(np.abs(thumb - self._trigger_thumb))) > self.cfg.scene_change)
            retry = (not self._last_outcome_ok and self._fail_retries < 3 and now - self._trigger_at > 4.0)
            if self._rearmed or changed or retry:
                self._start_capture(False, thumb, now)
        return small, thumb

    # -- drawing ---------------------------------------------------------------------------------

    def _state_name(self, now: float) -> str:
        if self._capturing:
            return "CAPTURING - hold still"
        if self._busy:
            return "RECOGNISING..."
        if self.voice.busy:
            return "PAUSED" if self.voice.paused else "READING"
        if self._steady_since:
            return "TEXT FOUND - hold steady"
        return "LOOKING FOR TEXT" if self.auto else "PRESS SPACE TO READ"

    def _render(self, small: np.ndarray, thumb: np.ndarray, now: float) -> np.ndarray:
        h_disp = int(DISPLAY_W * small.shape[0] / small.shape[1])
        canvas = np.full((max(h_disp, 480), DISPLAY_W + PANEL_W, 3), 28, np.uint8)
        view = cv2.resize(small, (DISPLAY_W, h_disp), interpolation=cv2.INTER_AREA)
        sx = DISPLAY_W / small.shape[1]
        with self._lock:
            res, res_at, res_thumb = self._result, self._result_at, self._result_thumb

        same_scene = (res is not None and res_thumb is not None
                      and float(np.mean(np.abs(thumb - res_thumb))) < self.cfg.scene_change)
        if res is not None and res.words and same_scene and now - res_at < 15:
            fx = DISPLAY_W / res.frame.shape[1]
            for _, conf, (x, y, w, h) in res.words:
                cv2.rectangle(view, (int(x * fx), int(y * fx)), (int((x + w) * fx), int((y + h) * fx)),
                              conf_color(conf), 1)
        elif self._layout is not None:
            col = (0, 230, 255) if self._steady_since else (0, 160, 200)
            for x, y, w, h in self._layout.boxes:
                cv2.rectangle(view, (int(x * sx), int(y * sx)), (int((x + w) * sx), int((y + h) * sx)), col, 1)

        # top bar: mode + state
        cv2.rectangle(view, (0, 0), (DISPLAY_W, 26), (20, 20, 20), -1)
        state = self._state_name(now)
        cv2.putText(view, f"READER [{'AUTO' if self.auto else 'MANUAL'}]  {state}", (8, 18), FONT, 0.52,
                    (255, 255, 255), 1, cv2.LINE_AA)
        sharp_zoom = self.zoom <= getattr(self.camera, "lossless_zoom", 1.0) + 0.01
        cv2.putText(view, f"ZOOM {self.zoom:.1f}x", (DISPLAY_W - 100, 18), FONT, 0.52,
                    (80, 210, 80) if sharp_zoom else (0, 170, 255), 1, cv2.LINE_AA)
        if self._capturing or self._busy:
            cv2.rectangle(view, (0, 0), (DISPLAY_W - 1, h_disp - 1), (0, 200, 255), 4)

        # meters: sharpness, light, steadiness, distance
        y0 = 34
        meters = [("sharp", min(1.0, self._sharp / 0.4), self._sharp >= 0.15),
                  ("light", min(1.0, self._brightness / 140.0), 60 <= self._brightness <= 235),
                  ("steady", max(0.0, 1 - self._motion / (2 * self.cfg.motion_thresh)),
                   self._motion < self.cfg.motion_thresh)]
        for i, (name, frac, good) in enumerate(meters):
            x = 8 + i * 150
            cv2.putText(view, name, (x, y0 + 10), FONT, 0.42, (230, 230, 230), 1, cv2.LINE_AA)
            cv2.rectangle(view, (x + 50, y0), (x + 140, y0 + 12), (60, 60, 60), -1)
            cv2.rectangle(view, (x + 50, y0), (x + 50 + int(90 * frac), y0 + 12),
                          (80, 210, 80) if good else (0, 140, 255), -1)
        if self.lidar is not None:
            s = self.lidar.latest()
            d = f"{s.distance_cm:.0f} cm" if s and s.valid and s.distance_cm else "-- cm"
            cv2.putText(view, d, (8 + 3 * 150, y0 + 11), FONT, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        # bottom bar: guidance / exposure
        cv2.rectangle(view, (0, h_disp - 26), (DISPLAY_W, h_disp), (20, 20, 20), -1)
        hint = self._live_hint(small.shape[1])
        if self._guidance and now - self._guidance_at < 8:
            cv2.putText(view, ascii_safe(self._guidance)[:80], (8, h_disp - 8), FONT, 0.45, (0, 200, 255), 1,
                        cv2.LINE_AA)
        elif hint:
            cv2.putText(view, hint, (8, h_disp - 8), FONT, 0.45, (0, 200, 255), 1, cv2.LINE_AA)
        else:
            bt = "BT headset" if self.bt.is_bluetooth else "audio: not Bluetooth"
            cv2.putText(view, f"{self.fps.rate:4.1f} fps  exp {self._exposure_ms:.0f} ms  {bt}  "
                              f"rate {self.voice.rate} wpm", (8, h_disp - 8), FONT, 0.45, (190, 190, 190), 1,
                        cv2.LINE_AA)
        canvas[:h_disp, :DISPLAY_W] = view
        self._draw_panel(canvas, res, h_disp)
        return canvas

    def _live_hint(self, small_w: int) -> str:
        """On-screen zoom advice from the live text detection (not spoken)."""
        lay = self._layout
        if lay is None or lay.n_chars < 8 or self._busy or self._capturing:
            return ""
        letters_px = lay.char_h * self.camera.size[0] / small_w   # letter height in captured pixels
        if 0 < letters_px < 14 and self.zoom < self.cfg.zoom_max - 0.05:
            return "Text looks small - scroll up to zoom in"
        m = 0.01 * small_w
        H = small_w * self.camera.size[1] / self.camera.size[0]
        if any(x < m or x + w > small_w - m or y < m or y + h > H - m for x, y, w, h in lay.boxes):
            return "Text runs off the edge - scroll down to zoom out" if self.zoom > 1.05 else \
                "Text runs off the edge - move back a little"
        return ""

    def _draw_panel(self, canvas: np.ndarray, res: Optional[OcrOutcome], height: int) -> None:
        x0 = DISPLAY_W + 12
        width = PANEL_W - 24
        cv2.putText(canvas, "RECOGNISED TEXT", (x0, 24), FONT, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        if res is None:
            cv2.putText(canvas, "nothing read yet", (x0, 52), FONT, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
        else:
            info = (f"conf {res.mean_conf:.0f}%  {res.n_words} words  {res.elapsed:.1f}s  {res.method}"
                    if res.chunks else "no readable text")
            cv2.putText(canvas, info, (x0, 46), FONT, 0.42, (170, 170, 170), 1, cv2.LINE_AA)
            rows: List[Tuple[int, str]] = []
            if res.ok:
                for i, ch in enumerate(res.chunks):
                    for ln in wrap_px(ascii_safe(ch), width, 0.48):
                        rows.append((i, ln))
                    if res.gaps[i] >= 0.25:
                        rows.append((-1, ""))
            else:
                for ln in wrap_px(ascii_safe(res.diagnosis), width, 0.48):
                    rows.append((-2, ln))
            active = self.voice.active_chunk
            line_h = 20
            max_rows = (height - 90) // line_h
            first = next((r for r, (ci, _) in enumerate(rows) if ci == active), 0)
            start = max(0, min(first - 3, len(rows) - max_rows))
            y = 72
            for ci, ln in rows[start:start + max_rows]:
                if ci == active and ci >= 0:
                    cv2.rectangle(canvas, (x0 - 4, y - 15), (x0 + width, y + 5), (90, 70, 20), -1)
                col = (0, 200, 255) if ci == -2 else (240, 240, 240) if ci == active else (200, 200, 200)
                cv2.putText(canvas, ln, (x0, y), FONT, 0.48, col, 1, cv2.LINE_AA)
                y += line_h
        for i, ln in enumerate(wrap_px(HELP, width, 0.38)):
            cv2.putText(canvas, ln, (x0, height - 30 + i * 14), FONT, 0.38, (130, 130, 130), 1, cv2.LINE_AA)

    def _status(self) -> dict:
        res = self._result
        return {"state": self._state_name(time.monotonic()), "auto": self.auto,
                "sharpness": round(self._sharp, 3), "motion": round(self._motion, 1),
                "text": res.text if res and res.ok else "", "conf": round(res.mean_conf, 1) if res else None,
                "diagnosis": res.diagnosis if res else "", "speaking": self.voice.last_text}

    def _show(self, canvas: np.ndarray) -> None:
        try:
            if not self._window_open:
                cv2.namedWindow("Vantage reader", cv2.WINDOW_NORMAL)
                cv2.resizeWindow("Vantage reader", canvas.shape[1], canvas.shape[0])
                self._window_open = True
            cv2.imshow("Vantage reader", canvas)
            key = cv2.waitKey(1) & 0xFF
            if key != 255:
                self.handle_key(chr(key))
            if cv2.getWindowProperty("Vantage reader", cv2.WND_PROP_VISIBLE) < 1:
                self.stop_event.set()
        except cv2.error as exc:
            LOG.warning("Preview window unavailable (%s) - continuing without it", str(exc).splitlines()[0][:80])
            self.cfg.show_preview = False

    # -- lifecycle -------------------------------------------------------------------------------

    def start(self) -> None:
        LOG.info("Vantage reader %s | Tesseract %s | lang %s | voice %s via %s", __version__,
                 self.engine.version, self.cfg.lang, self.cfg.voice, self.voice.player or "espeak")
        if self.cfg.audio_enabled and not self.voice.tts:
            LOG.warning("No speech: espeak-ng not found (sudo apt install espeak-ng)")
        self.voice.start()
        self.bt.start()
        if self.lidar is not None:
            self.lidar.start()
        if self.streamer:
            self.streamer.start()
        self.camera.start()
        self.keys.start()
        if self.mouse is not None:
            self.mouse.start()
        LOG.info("Keys: %s", HELP)
        self.voice.say("Reader ready." + ("" if self.auto else " Press space to read."))

    def _camera_watchdog(self) -> None:
        """If the camera stops delivering frames, explain why and exit instead of hanging."""
        started = time.monotonic()
        while not self.stop_event.wait(0.5):
            last = self._last_frame_at
            limit = 5.0 if last else 15.0          # the first frame can take a while
            if time.monotonic() - (last or started) > limit:
                LOG.error(CAMERA_STUCK_MSG)
                self.voice.say("The camera stopped working. Please unplug the power for ten seconds.")
                time.sleep(4.0)
                self.keys.restore()
                os._exit(3)

    def run(self) -> None:
        deadline = self._t_start + self.cfg.duration_s if self.cfg.duration_s > 0 else None
        self._last_frame_at = 0.0
        threading.Thread(target=self._camera_watchdog, name="watchdog", daemon=True).start()
        while not self.stop_event.is_set():
            if deadline and time.monotonic() > deadline:
                break
            frame, md = self.camera.read()
            self._last_frame_at = time.monotonic()
            small, thumb = self._tick(frame, md)
            if self.cfg.show_preview or self.streamer:
                canvas = self._render(small, thumb, time.monotonic())
                if self.streamer:
                    self.streamer.publish(canvas, self._status())
                if self.cfg.show_preview:
                    self._show(canvas)

    def shutdown(self) -> None:
        self.stop_event.set()
        self.keys.restore()
        self.voice.shutdown()
        try:
            self.camera.stop()
        except Exception:  # noqa: BLE001
            pass
        if self.streamer:
            try:
                self.streamer.stop()
            except Exception:  # noqa: BLE001
                pass
        self.ocr_pool.shutdown(wait=True, cancel_futures=True)
        self.pipeline.pool.shutdown(wait=False, cancel_futures=True)
        for th in (self.voice, self.bt, self.lidar, self.keys, self.mouse):
            if th is not None and th.is_alive():
                th.join(timeout=2.0)
        if self._window_open:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except Exception:  # noqa: BLE001
                pass


# =============================================================================================
# --image and --self-test modes
# =============================================================================================

def run_images(cfg: ReaderConfig) -> int:
    pipeline = OcrPipeline(cfg, Tesseract(cfg))
    stop = threading.Event()
    voice = None
    if cfg.speak_images:
        voice = ReaderVoice(cfg, stop)
        voice.start()
    rc = 0
    for path in cfg.images:
        img = cv2.imread(path)
        if img is None:
            print(f"{path}: cannot read image", file=sys.stderr)
            rc = 1
            continue
        o = pipeline.recognize([img])
        print(f"\n=== {path}\n{describe_outcome(o)}")
        if cfg.save_debug:
            print(f"    debug: {save_debug(cfg.save_debug, o, os.path.splitext(os.path.basename(path))[0])}_*")
        if voice is not None:
            if o.ok:
                prefix = "Not sure, but it says:" if o.mean_conf < cfg.sure_conf else ""
                items = ([SpeechItem(text=prefix)] if prefix else []) + [
                    SpeechItem(text=c, chunk=i, gap_s=o.gaps[i]) for i, c in enumerate(o.chunks)]
                voice.play(items)
            else:
                voice.say(o.diagnosis)
            time.sleep(0.3)
            while voice.busy:
                time.sleep(0.1)
    stop.set()
    pipeline.pool.shutdown(wait=False)
    return rc


def word_accuracy(reference: str, hypothesis: str) -> float:
    ref = collections.Counter(re.findall(r"[a-z0-9]+", reference.lower()))
    hyp = collections.Counter(re.findall(r"[a-z0-9]+", hypothesis.lower()))
    total = sum(ref.values())
    return sum((ref & hyp).values()) / total if total else 0.0


def run_self_test(cfg: ReaderConfig) -> int:
    """Measure recognition on synthetic camera shots: 'naive' vs. this pipeline."""
    engine = Tesseract(cfg)
    pipeline = OcrPipeline(cfg, engine)
    size = (cfg.width, cfg.height)
    rng = np.random.default_rng(7)
    page, sign, label = (" ".join(SAMPLE_PAGE), " ".join(SAMPLE_SIGN), " ".join(SAMPLE_LABEL))
    W = size[0]
    cases = [
        ("book page, good light", page, render_text_card(SAMPLE_PAGE, W // 64),
         dict(angle=1.5, shadow=0.2), dict(blur=0.7, noise=3)),
        ("small print (medicine)", label, render_text_card(SAMPLE_LABEL, W // 110, serif=False),
         dict(angle=0.5), dict(blur=0.6, noise=3)),
        ("tilted 7 deg + shadow", page, render_text_card(SAMPLE_PAGE, W // 64),
         dict(angle=7.0, shadow=0.6), dict(blur=0.8, noise=4)),
        ("blurry + noisy", page, render_text_card(SAMPLE_PAGE, W // 64),
         dict(angle=1.0), dict(blur=1.9, noise=9)),
        ("white-on-dark sign", sign, render_text_card(SAMPLE_SIGN, W // 30, fg=(240, 240, 240),
                                                      bg=(110, 60, 20), serif=False),
         dict(angle=-3.0), dict(blur=0.8, noise=4)),
        ("dim, low contrast", label, render_text_card(SAMPLE_LABEL, W // 75, fg=(105, 105, 105),
                                                      bg=(160, 165, 170), serif=False),
         dict(dim=0.55), dict(blur=0.7, noise=6)),
    ]
    print(f"Self-test: Tesseract {engine.version}, frames {size[0]}x{size[1]}, lang {cfg.lang}\n")
    print(f"{'case':26s} {'naive 640x480':>14s} {'naive full-res':>15s} {'Vantage':>9s} {'conf':>6s} {'time':>6s}")
    totals = [0.0, 0.0, 0.0]
    for name, ref, card, scene_kw, deg_kw in cases:
        frame = degrade(compose_scene(card, size, **scene_kw), rng=rng, **deg_kw)
        g = to_gray(frame)
        naive_small = " ".join(w.text for w in engine.run(cv2.resize(g, (640, 480), interpolation=cv2.INTER_AREA), 3))
        naive_full = " ".join(w.text for w in engine.run(g, 3))
        o = pipeline.recognize([frame])
        accs = [word_accuracy(ref, naive_small), word_accuracy(ref, naive_full), word_accuracy(ref, o.text)]
        totals = [a + b for a, b in zip(totals, accs)]
        print(f"{name:26s} {accs[0]:13.0%} {accs[1]:14.0%} {accs[2]:9.0%} {o.mean_conf:5.0f}% {o.elapsed:5.1f}s")
        if cfg.save_debug:
            save_debug(cfg.save_debug, o, "selftest_" + re.sub(r"\W+", "_", name))
    n = len(cases)
    print(f"{'AVERAGE word accuracy':26s} {totals[0] / n:13.0%} {totals[1] / n:14.0%} {totals[2] / n:9.0%}")
    pipeline.pool.shutdown(wait=False)
    return 0


# =============================================================================================
# CLI
# =============================================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> ReaderConfig:
    d = ReaderConfig()
    p = argparse.ArgumentParser(
        description="Vantage text reader: point the camera at text, hear it on the Bluetooth headset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    g = p.add_argument_group("camera")
    g.add_argument("--camera-num", type=int, default=None, help="camera index (default: the AI camera)")
    g.add_argument("--size", default=f"{d.width}x{d.height}",
                   help="capture size; 4056x3040 = full sensor, best for small print")
    g.add_argument("--rotate-180", action="store_true", help="camera is mounted upside down")
    g.add_argument("--fast-sensor", dest="full_sensor", action="store_false",
                   help="use the binned 2x2 sensor mode (30 fps) instead of the full 12 MP mode (~10 fps); "
                        "zoom then only enlarges pixels")

    g = p.add_argument_group("zoom (USB mouse)")
    g.add_argument("--zoom-max", type=float, default=d.zoom_max, help="maximum zoom")
    g.add_argument("--zoom-step", type=float, default=d.zoom_step, help="zoom change per wheel notch")
    g.add_argument("--no-mouse", dest="mouse", action="store_false", help="don't use the mouse")
    g.add_argument("--mouse-device", dest="mouse_devices", action="append", default=[], metavar="PATH",
                   help="use this /dev/input/eventN device (default: every mouse found)")
    g.add_argument("--mouse-grab", action="store_true",
                   help="stop the mouse from also moving/clicking on the desktop while the reader runs")

    g = p.add_argument_group("recognition")
    g.add_argument("--lang", default=d.lang, help="Tesseract language(s), e.g. eng, eng+spa")
    g.add_argument("--tessdata", default=None, help="folder with .traineddata files (e.g. tessdata_best)")
    g.add_argument("--min-conf", dest="min_word_conf", type=float, default=d.min_word_conf,
                   help="drop words below this confidence")
    g.add_argument("--burst", type=int, default=d.burst, help="frames per capture (sharpest one is used)")
    g.add_argument("--ocr-threads", type=int, default=d.ocr_threads)

    g = p.add_argument_group("reading behaviour")
    g.add_argument("--manual", dest="auto", action="store_false",
                   help="only read when you press SPACE (default: read automatically when text is held steady)")
    g.add_argument("--steady", dest="steady_s", type=float, default=d.steady_s,
                   help="seconds the camera must be still before auto-reading")
    g.add_argument("--motion", dest="motion_thresh", type=float, default=d.motion_thresh,
                   help="how still is 'still' (higher = more tolerant of shaky hands)")

    g = p.add_argument_group("audio")
    g.add_argument("--no-audio", dest="audio_enabled", action="store_false")
    g.add_argument("--voice", default=d.voice, help="espeak-ng voice, e.g. en-us, en-gb, en+f3, es")
    g.add_argument("--rate", type=int, default=d.rate, help="reading speed, words per minute")
    g.add_argument("--volume", type=int, default=d.volume, help="0..200")
    g.add_argument("--bt-mac", default=None, help="Bluetooth MAC of the headset to auto-reconnect")

    g = p.add_argument_group("lidar")
    g.add_argument("--lidar", dest="use_lidar", action="store_true",
                   help="use the TFmini to say 'too close' when text is nearer than the lens can focus")
    g.add_argument("--serial", dest="serial_port", default=d.serial_port)

    g = p.add_argument_group("display / debugging")
    g.add_argument("--headless", dest="show_preview", action="store_false", help="no preview window")
    g.add_argument("--stream-port", type=int, default=0, help="serve the preview at http://<pi>:PORT/")
    g.add_argument("--save-debug", metavar="DIR", default=None,
                   help="save every captured frame, the processed image and the result to DIR")
    g.add_argument("--log-file", default=d.log_file)

    g = p.add_argument_group("testing")
    g.add_argument("--image", dest="images", nargs="+", default=[], metavar="FILE",
                   help="read text from image file(s) instead of the camera")
    g.add_argument("--speak", dest="speak_images", action="store_true", help="with --image: read results aloud")
    g.add_argument("--self-test", action="store_true", help="measure recognition quality and exit")
    g.add_argument("--simulate", action="store_true", help="simulated camera (no hardware)")
    g.add_argument("--duration", dest="duration_s", type=float, default=0.0, help="stop after N seconds")
    g.add_argument("--version", action="version", version=__version__)

    ns = p.parse_args(argv)
    m = re.fullmatch(r"(\d+)x(\d+)", ns.size)
    if not m:
        p.error("--size must look like 2028x1520")
    vals = {k: v for k, v in vars(ns).items() if k in ReaderConfig.__dataclass_fields__}
    return ReaderConfig(width=int(m.group(1)), height=int(m.group(2)), **vals)


def setup_logging(cfg: ReaderConfig) -> None:
    root = logging.getLogger("vantage")   # also catches vantage_core's Bluetooth/LiDAR messages
    root.setLevel(logging.INFO)
    if cfg.log_file:
        fh = logging.handlers.RotatingFileHandler(cfg.log_file, maxBytes=2_000_000, backupCount=2)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)-8s %(message)s"))
        root.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(sh)


def main(argv: Optional[Sequence[str]] = None) -> int:
    cfg = parse_args(argv)
    if cv2 is None:
        print("OpenCV is required:  sudo apt install python3-opencv", file=sys.stderr)
        return 2
    try:
        if cfg.self_test:
            return run_self_test(cfg)
        if cfg.images:
            return run_images(cfg)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    setup_logging(cfg)
    if cfg.show_preview and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No desktop display found -> no preview window. "
              "Use --stream-port 8080 to watch in a browser.", file=sys.stderr)
        cfg.show_preview = False
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("Warning: running as root. Bluetooth audio lives in your user's session, "
              "so run WITHOUT sudo.", file=sys.stderr)
    try:
        app = ReaderApp(cfg)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, lambda *_: app.stop_event.set())
    error: Optional[BaseException] = None
    try:
        app.start()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Fatal error")
        error = exc
    finally:
        app.shutdown()
    if error is not None:
        print(f"\nFATAL: {error}\n(see {cfg.log_file})", file=sys.stderr)
        return 1
    print("Reader stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
