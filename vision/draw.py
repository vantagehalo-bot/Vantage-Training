"""Drawing helpers shared by the demo app and the evaluation report."""

from __future__ import annotations

import cv2
import numpy as np

try:
    from . import taxonomy as tx
except ImportError:
    import taxonomy as tx

# BGR colour per hazard tier: drop-off red, moving orange, obstacle yellow, landmark blue
TIER_BGR = {0: (40, 40, 230), 1: (0, 140, 255), 2: (0, 200, 230), 3: (230, 150, 40)}


def draw_detections(img: np.ndarray, dets, title: str = "") -> np.ndarray:
    """dets: [(label, conf, (x0, y0, x1, y1) normalised 0..1)]. Returns a new image."""
    out = img.copy()
    h, w = out.shape[:2]
    th = max(1, round(min(h, w) / 300))
    fs = max(0.45, min(h, w) / 900)
    for label, conf, (x0, y0, x1, y1) in sorted(dets, key=lambda d: -tx.TIER.get(d[0], 2)):
        col = TIER_BGR.get(tx.TIER.get(label, 2), (200, 200, 200))
        p0, p1 = (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h))
        cv2.rectangle(out, p0, p1, col, th + 1)
        txt = f"{label} {conf:.0%}"
        (tw, tht), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, th)
        ty = max(p0[1], tht + 6)
        cv2.rectangle(out, (p0[0], ty - tht - 6), (p0[0] + tw + 6, ty), col, -1)
        cv2.putText(out, txt, (p0[0] + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, fs, (20, 20, 20), th,
                    cv2.LINE_AA)
    if title:
        bar = int(34 * max(1.0, fs / 0.6))
        out = cv2.copyMakeBorder(out, bar, 0, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        cv2.putText(out, f"{title}  ({len(dets)} found)", (10, bar - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    fs * 1.1, (255, 255, 255), th, cv2.LINE_AA)
    return out


def side_by_side(a: np.ndarray, b: np.ndarray, gap: int = 8) -> np.ndarray:
    h = max(a.shape[0], b.shape[0])
    pad = lambda im: cv2.copyMakeBorder(im, 0, h - im.shape[0], 0, 0, cv2.BORDER_CONSTANT,  # noqa: E731
                                        value=(255, 255, 255))
    spacer = np.full((h, gap, 3), 255, np.uint8)
    return np.hstack([pad(a), spacer, pad(b)])
