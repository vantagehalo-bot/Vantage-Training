"""
Vantage object taxonomy: the 29 things the Vantage vision model is trained to see.

Two public datasets are merged into this one label set:

  * ROD - "Road Obstacle Detection" (Hugging Face: Abtinzandi/Obstacle-Detection-Dataset-YOLO,
    MIT licence, 24k street images from a pedestrian's point of view: stairs, manholes,
    poles, cones, crossings ...).
  * COCO 2017 (cocodataset.org, CC BY 4.0) - used for the indoor objects that a street
    dataset never shows: tables, sofas, beds, toilets, TVs, suitcases, traffic lights.

Every class also gets a hazard tier, which decides how urgently it is spoken.
"""

from __future__ import annotations

# (name, tier, spoken name)
#   tier 0 = DROP-OFF  (you could fall: stairs, open manhole)       -> spoken first, always
#   tier 1 = MOVING    (vehicles, bikes)                             -> high priority
#   tier 2 = OBSTACLE  (things you would walk into)                  -> normal priority
#   tier 3 = LANDMARK  (useful to know, not dangerous: signs, TV)    -> only when asked
CLASSES = [
    ("person",        2, "person"),
    ("bicycle",       1, "bicycle"),
    ("car",           1, "car"),
    ("motorcycle",    1, "motorbike"),
    ("bus",           1, "bus"),
    ("truck",         1, "truck"),
    ("dog",           2, "dog"),
    ("stairs",        0, "stairs"),
    ("sign",          3, "sign"),
    ("traffic light", 3, "traffic light"),
    ("pole",          2, "pole"),
    ("manhole",       0, "manhole"),
    ("tree",          2, "tree"),
    ("railing",       2, "railing"),
    ("crosswalk",     3, "crossing"),
    ("bench",         2, "bench"),
    ("traffic cone",  2, "cone"),
    ("fire hydrant",  2, "hydrant"),
    ("trash bin",     2, "bin"),
    ("potted plant",  2, "plant pot"),
    ("utility box",   2, "utility box"),
    ("chair",         2, "chair"),
    ("bike rack",     2, "bike rack"),
    ("table",         2, "table"),
    ("sofa",          2, "sofa"),
    ("bed",           2, "bed"),
    ("toilet",        3, "toilet"),
    ("tv",            3, "TV"),
    ("suitcase",      2, "suitcase"),
]

NAMES = [c[0] for c in CLASSES]
INDEX = {n: i for i, n in enumerate(NAMES)}
TIER = {c[0]: c[1] for c in CLASSES}
SPOKEN = {c[0]: c[2] for c in CLASSES}
TIER_NAMES = {0: "drop-off", 1: "moving", 2: "obstacle", 3: "landmark"}

# ROD class name -> Vantage class name (None = drop the box).
# "Building" and "Road" are dropped: a box around "the road" is not an obstacle and
# teaches the model to draw giant boxes.
ROD_MAP = {
    "Bike": "bicycle",
    "Building": None,
    "Car": "car",
    "Person": "person",
    "Stairs": "stairs",
    "Traffic sign": "sign",
    "Electrical Pole": "pole",
    "Road": None,
    "Motorcycle": "motorcycle",
    "Dustbin": "trash bin",
    "Dog": "dog",
    "Manhole": "manhole",
    "Tree": "tree",
    "Guard rail": "railing",
    "Pedestrian crosswalk": "crosswalk",
    "Truck": "truck",
    "Bus": "bus",
    "Bench": "bench",
    "Traffic Cone": "traffic cone",
    "Fire hydrant": "fire hydrant",
    "Teraffic Barrel": "traffic cone",   # (sic) typo is in the dataset's own data.yaml
    "Traffic Barrel": "traffic cone",
    "Plant Pot": "potted plant",
    "Electrical Box": "utility box",
    "Chair": "chair",
    "Bicycle Rack": "bike rack",
}

# COCO-80 class name -> Vantage class name. Anything not listed is dropped.
COCO_MAP = {
    "person": "person",
    "bicycle": "bicycle",
    "car": "car",
    "motorcycle": "motorcycle",
    "bus": "bus",
    "truck": "truck",
    "dog": "dog",
    "traffic light": "traffic light",
    "fire hydrant": "fire hydrant",
    "stop sign": "sign",
    "bench": "bench",
    "chair": "chair",
    "couch": "sofa",
    "potted plant": "potted plant",
    "bed": "bed",
    "dining table": "table",
    "toilet": "toilet",
    "tv": "tv",
    "suitcase": "suitcase",
}

# COCO images are only taken if they contain at least one of these. They are the
# classes ROD does not have (or barely has), so COCO fills the indoor gap instead of
# drowning the street data in yet more people and cars.
COCO_WANTED = {"table", "sofa", "bed", "toilet", "tv", "suitcase", "traffic light",
               "chair", "potted plant", "bench"}


if __name__ == "__main__":
    for i, (n, t, s) in enumerate(CLASSES):
        print(f"{i:2d}  {n:14s} {TIER_NAMES[t]:9s} spoken as '{s}'")
