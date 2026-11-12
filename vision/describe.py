"""
Turns raw detections into one short sentence a blind user can act on.

  [stairs 0.91 (0.40,0.55,0.62,0.98), chair 0.80 ..., chair 0.77 ...]
      -> "Stairs ahead, very close. Two chairs on your left."

Order: drop-offs first (stairs, manholes), then moving things, then obstacles; within a
tier, the closest first (a bigger box that reaches lower in the frame is closer).
"""

from __future__ import annotations

import collections
import dataclasses
from typing import Iterable, List, Optional

try:
    from . import taxonomy as tx
except ImportError:  # run as a plain script
    import taxonomy as tx

NUM_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five"}


@dataclasses.dataclass
class Det:
    label: str
    conf: float
    box: tuple  # x0, y0, x1, y1 normalised to 0..1

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def closeness(self) -> float:
        """0..1 - box height plus how low its bottom edge is (objects near you sit low)."""
        h = self.box[3] - self.box[1]
        return min(1.0, 0.6 * h + 0.4 * self.box[3])

    @property
    def tier(self) -> int:
        return tx.TIER.get(self.label, 2)


def direction(cx: float) -> str:
    if cx < 0.35:
        return "on your left"
    if cx > 0.65:
        return "on your right"
    return "ahead"


def distance_word(c: float) -> Optional[str]:
    if c > 0.75:
        return "very close"
    if c > 0.5:
        return "close"
    return None


def plural(word: str) -> str:
    if word.endswith(("s", "sh", "ch", "x")):
        return word + "es"
    if word.endswith("y") and word[-2:] not in ("ay", "ey", "oy"):
        return word[:-1] + "ies"
    return word + "s"


def describe(dets: Iterable[Det], max_items: int = 3, include_landmarks: bool = True) -> str:
    dets = [d for d in dets if include_landmarks or d.tier < 3]
    if not dets:
        return "Path looks clear."
    # group same label + same direction ("two chairs on your left")
    groups = collections.OrderedDict()
    for d in sorted(dets, key=lambda d: (d.tier, -d.closeness)):
        key = (d.label, direction(d.cx))
        groups.setdefault(key, []).append(d)
    parts: List[str] = []
    for (label, where), ds in groups.items():
        name = tx.SPOKEN.get(label, label)
        n = len(ds)
        near = distance_word(max(d.closeness for d in ds))
        if n == 1:
            phrase = f"{name[0].upper()}{name[1:]} {where}"
        else:
            phrase = f"{NUM_WORDS.get(n, str(n))} {plural(name)} {where}"
        if near:
            phrase += f", {near}"
        parts.append(phrase + ".")
        if len(parts) >= max_items:
            break
    return " ".join(parts)


if __name__ == "__main__":
    demo = [Det("chair", 0.8, (0.05, 0.5, 0.25, 0.9)), Det("chair", 0.7, (0.25, 0.5, 0.38, 0.85)),
            Det("stairs", 0.9, (0.4, 0.55, 0.62, 0.98)), Det("tv", 0.6, (0.7, 0.2, 0.9, 0.4))]
    print(describe(demo))
