#!/usr/bin/env python3
"""
Step 1 - BUILD THE DATASET.

Downloads two public datasets and merges them into one YOLO dataset that uses the
Vantage taxonomy (vision/taxonomy.py):

  ROD  (street obstacles seen from a pedestrian: stairs, manholes, poles, cones ...)
  COCO (indoor objects: tables, sofas, beds, toilets, TVs, suitcases, traffic lights)

Output (default vision/datasets/vantage/):
  images/{train,val,test}/*.jpg   labels/{train,val,test}/*.txt   data.yaml   stats.json

Usage:
  python vision/build_dataset.py                        # ROD + 4 COCO shards (~2 GB download)
  python vision/build_dataset.py --coco-shards 0        # ROD only
  python vision/build_dataset.py --max-train 3000       # small subset for a quick CPU run
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as tx  # noqa: E402

ROD_REPO = "Abtinzandi/Obstacle-Detection-Dataset-YOLO"
COCO_REPO = "detection-datasets/coco"
COCO_LABELS_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/coco2017labels.zip"
COCO80 = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
    "teddy bear", "hair drier", "toothbrush",
]


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------------------------

def parse_yolo_line(line: str):
    """Returns (cls, xc, yc, w, h) or None. Polygon lines are turned into their bounding box."""
    parts = line.split()
    if len(parts) < 5:
        return None
    try:
        cls = int(float(parts[0]))
        vals = [float(v) for v in parts[1:]]
    except ValueError:
        return None
    if len(vals) == 4:
        xc, yc, w, h = vals
    else:  # segmentation polygon: x1 y1 x2 y2 ...
        xs, ys = vals[0::2], vals[1::2]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        xc, yc, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    # clip to the image and drop degenerate boxes
    x0, y0 = max(0.0, xc - w / 2), max(0.0, yc - h / 2)
    x1, y1 = min(1.0, xc + w / 2), min(1.0, yc + h / 2)
    if x1 - x0 < 0.004 or y1 - y0 < 0.004:
        return None
    return cls, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0


def remap(lines, src_names, mapping):
    out = []
    for ln in lines:
        p = parse_yolo_line(ln)
        if p is None:
            continue
        cls, xc, yc, w, h = p
        if not 0 <= cls < len(src_names):
            continue
        dst = mapping.get(src_names[cls])
        if dst is None:
            continue
        out.append((tx.INDEX[dst], xc, yc, w, h))
    return out


def write_labels(path: Path, boxes) -> None:
    path.write_text("".join(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n" for c, x, y, w, h in boxes))


def place_image(src: Path, dst: Path, mode: str) -> None:
    if dst.exists():
        dst.unlink()
    if mode == "symlink":
        dst.symlink_to(src.resolve())
    elif mode == "hardlink":
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    else:
        shutil.copy2(src, dst)


# ---------------------------------------------------------------------------------------------
# ROD
# ---------------------------------------------------------------------------------------------

def download_rod(raw: Path) -> Path:
    dst = raw / "rod"
    if (dst / "data.yaml").exists() and (dst / "valid" / "images").exists():
        log(f"ROD already downloaded at {dst}")
        return dst
    from huggingface_hub import snapshot_download
    # Only the images: the boxes for all 24k images come in three small parquet files
    # (rod_label_table), which halves the number of requests to Hugging Face.
    log("Downloading ROD images (~1.5 GB, 24k files - takes 10-30 min) ...")
    snapshot_download(ROD_REPO, repo_type="dataset", local_dir=str(dst), max_workers=32,
                      allow_patterns=["*/images/*", "data.yaml"])
    return dst


def rod_label_table(raw: Path):
    """{image stem: [yolo label lines]} for every ROD image, from the dataset's metadata parquet."""
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download
    table = {}
    for split in ("train", "validation", "test"):
        p = hf_hub_download(ROD_REPO, f"default/{split}/0000.parquet", repo_type="dataset",
                            revision="refs/convert/parquet", local_dir=str(raw / "rod_meta"))
        for row in pq.read_table(p, columns=["file_name", "bboxes_yolo"]).to_pylist():
            boxes = json.loads(row["bboxes_yolo"] or "[]")
            table[Path(row["file_name"]).stem] = [
                f"{b['class_id']} {b['x_center']} {b['y_center']} {b['width']} {b['height']}" for b in boxes]
    return table


def rod_names(rod: Path):
    import yaml
    data = yaml.safe_load((rod / "data.yaml").read_text())
    names = data["names"]
    if isinstance(names, dict):
        names = [names[k] for k in sorted(names)]
    return list(names)


def add_rod(rod: Path, out: Path, stats, args, rng, raw: Path) -> None:
    names = rod_names(rod)
    meta = None  # label table from the metadata parquet, loaded only if label files are missing
    unknown = [n for n in names if n not in tx.ROD_MAP]
    if unknown:
        log(f"  warning: ROD classes not in the taxonomy (dropped): {unknown}")

    def list_images(split):
        img_dir = rod / split / "images"
        if not img_dir.exists():
            return img_dir, []
        # (the train split is spread over numbered sub-folders: images/0/, images/1/ ...)
        imgs = sorted(p for p in img_dir.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        rng.shuffle(imgs)
        return img_dir, imgs

    tr_dir, tr = list_images("train")
    va_dir, va = list_images("valid")
    te_dir, te = list_images("test")
    if not va and tr:
        # No validation split on disk (e.g. partial download): hold out part of train
        # instead, so the test split stays untouched for the final evaluation.
        k = min(args.val_from_train, len(tr) // 8)
        log(f"  ROD valid split missing - holding out {k} train images for validation")
        va, va_dir, tr = tr[:k], tr_dir, tr[k:]
        va_src = "train"
    else:
        va_src = "valid"
    for src_split, dst_split, img_dir, imgs, cap in (("train", "train", tr_dir, tr, args.max_train),
                                                     (va_src, "val", va_dir, va, args.max_val),
                                                     ("test", "test", te_dir, te, args.max_val)):
        if not imgs:
            log(f"  ROD split {src_split} missing - skipped")
            continue
        if cap:
            imgs = imgs[:cap]
        n_bg = 0
        for img in imgs:
            lbl = (rod / src_split / "labels" / img.relative_to(img_dir)).with_suffix(".txt")
            if lbl.exists():
                lines = lbl.read_text().splitlines()
            else:
                if meta is None:
                    log("  label files not downloaded - using the metadata parquet")
                    meta = rod_label_table(raw)
                lines = meta.get(img.stem, [])
            boxes = remap(lines, names, tx.ROD_MAP)
            if not boxes:
                # Images whose only boxes were "Road"/"Building" become background
                # examples; keep a few (they teach "nothing here"), skip the rest.
                n_bg += 1
                if n_bg > len(imgs) * 0.05:
                    continue
            name = f"rod_{img.stem}"
            place_image(img, out / "images" / dst_split / f"{name}{img.suffix.lower()}", args.files)
            write_labels(out / "labels" / dst_split / f"{name}.txt", boxes)
            stats[dst_split]["images"]["rod"] += 1
            for b in boxes:
                stats[dst_split]["boxes"][tx.NAMES[b[0]]] += 1
        log(f"  ROD {src_split:5s} -> {dst_split:5s}: {stats[dst_split]['images']['rod']} images")


# ---------------------------------------------------------------------------------------------
# COCO (indoor classes) - images come from the Hugging Face parquet mirror, labels from the
# official Ultralytics conversion, joined on the COCO image id.
# ---------------------------------------------------------------------------------------------

def load_coco_labels(raw: Path):
    zpath = raw / "coco2017labels.zip"
    if not zpath.exists():
        import urllib.request
        log("Downloading COCO labels (48 MB) ...")
        urllib.request.urlretrieve(COCO_LABELS_URL, zpath)
    labels = {}
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            n = info.filename
            if n.endswith(".txt") and "/labels/" in n and ("train2017" in n or "val2017" in n):
                labels[int(Path(n).stem)] = z.read(info).decode().splitlines()
    log(f"  COCO labels loaded for {len(labels)} images")
    return labels


def coco_shards(n_train: int):
    from huggingface_hub import HfApi
    files = [f.rfilename for f in HfApi().dataset_info(COCO_REPO).siblings]
    train = sorted(f for f in files if f.startswith("data/train-"))
    val = sorted(f for f in files if f.startswith("data/val-"))
    # val shard 0 -> our val split, val shard 1 -> our test split (indoor photos never trained on)
    return [("train", f) for f in train[:n_train]] + [("val", f) for f in val[:1]] + \
           [("test", f) for f in val[1:2]]


def add_coco(raw: Path, out: Path, stats, args, rng) -> None:
    if args.coco_shards <= 0:
        return
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    labels = load_coco_labels(raw)
    want = {tx.INDEX[n] for n in tx.COCO_WANTED}
    caps = {"train": args.max_coco_train, "val": args.max_coco_val, "test": args.max_coco_val}
    for dst_split, shard in coco_shards(args.coco_shards):
        if caps[dst_split] and stats[dst_split]["images"]["coco"] >= caps[dst_split]:
            continue
        log(f"  COCO shard {shard} (~480 MB) ...")
        path = hf_hub_download(COCO_REPO, shard, repo_type="dataset", local_dir=str(raw / "coco_hf"))
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=256, columns=["image_id", "image"]):
            for row in batch.to_pylist():
                if caps[dst_split] and stats[dst_split]["images"]["coco"] >= caps[dst_split]:
                    break
                iid = int(row["image_id"])
                boxes = remap(labels.get(iid, []), COCO80, tx.COCO_MAP)
                if not any(b[0] in want for b in boxes):
                    continue
                img = row["image"]
                data = img["bytes"] if isinstance(img, dict) else img
                if not data:
                    continue
                name = f"coco_{iid:012d}"
                (out / "images" / dst_split / f"{name}.jpg").write_bytes(data)
                write_labels(out / "labels" / dst_split / f"{name}.txt", boxes)
                stats[dst_split]["images"]["coco"] += 1
                for b in boxes:
                    stats[dst_split]["boxes"][tx.NAMES[b[0]]] += 1
        log(f"    COCO {dst_split}: {stats[dst_split]['images']['coco']} images so far")
        if not args.keep_shards:
            os.remove(path)


# ---------------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "datasets" / "vantage"))
    ap.add_argument("--raw", default=str(HERE / "datasets" / "raw"), help="download cache")
    ap.add_argument("--rod", default=None, help="existing ROD folder (skip the download)")
    ap.add_argument("--coco-shards", type=int, default=4,
                    help="COCO train parquet shards to scan (each ~480 MB, ~2.9k images; 0 = no COCO)")
    ap.add_argument("--max-train", type=int, default=0, help="cap ROD train images (0 = all)")
    ap.add_argument("--max-val", type=int, default=0, help="cap ROD val/test images (0 = all)")
    ap.add_argument("--val-from-train", type=int, default=1500,
                    help="if ROD's valid split is missing, hold out this many train images instead")
    ap.add_argument("--max-coco-train", type=int, default=0, help="cap COCO train images (0 = all)")
    ap.add_argument("--max-coco-val", type=int, default=0, help="cap COCO val images (0 = all)")
    ap.add_argument("--files", choices=["hardlink", "symlink", "copy"], default="hardlink",
                    help="how ROD images are placed in the output folder")
    ap.add_argument("--keep-shards", action="store_true", help="keep downloaded COCO parquet files")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    out, raw = Path(args.out), Path(args.raw)
    raw.mkdir(parents=True, exist_ok=True)
    if out.exists():
        shutil.rmtree(out)
    for s in ("train", "val", "test"):
        (out / "images" / s).mkdir(parents=True)
        (out / "labels" / s).mkdir(parents=True)

    rng = random.Random(args.seed)
    stats = {s: {"images": collections.Counter(), "boxes": collections.Counter()}
             for s in ("train", "val", "test")}

    rod = Path(args.rod) if args.rod else download_rod(raw)
    log("Adding ROD ...")
    add_rod(rod, out, stats, args, rng, raw)
    log("Adding COCO indoor subset ...")
    add_coco(raw, out, stats, args, rng)

    yaml_text = (f"# Vantage obstacle dataset - built by vision/build_dataset.py\n"
                 f"path: {out.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
                 f"nc: {len(tx.NAMES)}\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(tx.NAMES)))
    (out / "data.yaml").write_text(yaml_text)
    js = {s: {"images": dict(v["images"]), "boxes": {n: v["boxes"].get(n, 0) for n in tx.NAMES}}
          for s, v in stats.items()}
    (out / "stats.json").write_text(json.dumps(js, indent=2))

    log("\nDataset ready: " + str(out / "data.yaml"))
    log(f"{'class':14s} {'train':>7s} {'val':>6s} {'test':>6s}")
    for n in tx.NAMES:
        log(f"{n:14s} {js['train']['boxes'][n]:7d} {js['val']['boxes'][n]:6d} {js['test']['boxes'][n]:6d}")
    for s in ("train", "val", "test"):
        log(f"{s}: {sum(js[s]['images'].values())} images {js[s]['images']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
