#!/usr/bin/env python3
"""
Step 3 - EVALUATE (and make the charts for the expo poster).

Two numbers matter:
  1. mAP50 of our model on the held-out TEST images (never seen in training).
  2. "Hazard recall": out of every real obstacle in the test images, how many does the
     model find? We compare our model with the stock COCO model the AI camera ships with
     - the stock model simply has no idea what stairs, manholes, poles or cones are.

  python vision/evaluate.py --weights vision/models/vantage.pt

Writes vision/reports/: eval.json, recall_chart.png, examples/*.jpg (side-by-side pictures).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as tx  # noqa: E402
from draw import draw_detections, side_by_side  # noqa: E402


def iou(a, b) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def load_gt(lbl: Path):
    out = []
    if lbl.exists():
        for ln in lbl.read_text().splitlines():
            p = ln.split()
            if len(p) == 5:
                c, x, y, w, h = int(p[0]), *map(float, p[1:])
                out.append((tx.NAMES[c], (x - w / 2, y - h / 2, x + w / 2, y + h / 2)))
    return out


def predict(model, img_path, conf, mapping=None, imgsz=640):
    """Returns [(vantage_label, conf, (x0,y0,x1,y1) normalised)]."""
    r = model.predict(str(img_path), conf=conf, imgsz=imgsz, verbose=False)[0]
    out = []
    if r.boxes is None:
        return out
    for b, c, k in zip(r.boxes.xyxyn.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
        name = r.names[int(k)]
        if mapping is not None:
            name = mapping.get(name)
            if name is None:
                continue
        out.append((name, float(c), tuple(b)))
    return out


def match_recall(gt, preds, stats):
    used = set()
    for label, gbox in gt:
        s = stats.setdefault(label, [0, 0])
        s[1] += 1
        best, bi = 0.0, -1
        for i, (pl, _, pbox) in enumerate(preds):
            if i in used or pl != label:
                continue
            v = iou(gbox, pbox)
            if v > best:
                best, bi = v, i
        if best >= 0.5:
            used.add(bi)
            s[0] += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default=str(HERE / "models" / "vantage.pt"))
    ap.add_argument("--baseline", default="yolo11n.pt", help="stock COCO model to compare against")
    ap.add_argument("--data", default=str(HERE / "datasets" / "vantage" / "data.yaml"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=600, help="test images used for the recall comparison")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=None, help="default: the size the model was trained at")
    ap.add_argument("--examples", type=int, default=12)
    ap.add_argument("--out", default=str(HERE / "reports"))
    args = ap.parse_args()

    from ultralytics import YOLO
    import cv2
    import yaml

    out = Path(args.out)
    (out / "examples").mkdir(parents=True, exist_ok=True)
    model = YOLO(args.weights)
    imgsz = args.imgsz
    if not imgsz:
        train_args = (model.ckpt or {}).get("train_args", {}) if isinstance(model.ckpt, dict) else {}
        imgsz = int(train_args.get("imgsz", 640))

    # 1) standard detection metrics on the full split
    print(f"Validating on the {args.split} split at {imgsz}px ...")
    m = model.val(data=args.data, split=args.split, imgsz=imgsz, plots=True, verbose=False,
                  project=str(out), name="val", exist_ok=True)
    per_class = {model.names[i]: float(m.box.maps[i]) for i in range(len(model.names))}
    metrics = {"mAP50": float(m.box.map50), "mAP50-95": float(m.box.map),
               "precision": float(m.box.mp), "recall": float(m.box.mr), "per_class_mAP50-95": per_class}
    print(json.dumps({k: v for k, v in metrics.items() if k != "per_class_mAP50-95"}, indent=2))

    # 2) hazard recall: ours vs the stock COCO model
    root = Path(yaml.safe_load(Path(args.data).read_text())["path"])
    imgs = sorted((root / "images" / args.split).iterdir())
    random.Random(0).shuffle(imgs)
    imgs = imgs[: args.n]
    base = YOLO(args.baseline)
    ours_stats, base_stats = {}, {}
    examples = []
    for i, p in enumerate(imgs):
        gt = load_gt(root / "labels" / args.split / (p.stem + ".txt"))
        po = predict(model, p, args.conf, imgsz=imgsz)
        pb = predict(base, p, args.conf, mapping=tx.COCO_MAP)
        match_recall(gt, po, ours_stats)
        match_recall(gt, pb, base_stats)
        # good showcase pictures: ones where we find a hazard the stock model cannot
        gain = len({d[0] for d in po if tx.TIER[d[0]] <= 2} - {d[0] for d in pb})
        examples.append((gain, p, po, pb))
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(imgs)} images")

    rows = []
    for name in tx.NAMES:
        o = ours_stats.get(name, [0, 0])
        b = base_stats.get(name, [0, 0])
        if o[1] == 0:
            continue
        rows.append({"class": name, "tier": tx.TIER_NAMES[tx.TIER[name]], "objects": o[1],
                     "vantage_recall": o[0] / o[1], "stock_recall": b[0] / b[1] if b[1] else 0.0,
                     "stock_knows_class": name in tx.COCO_MAP.values()})
    tot_o = sum(v[0] for v in ours_stats.values()), sum(v[1] for v in ours_stats.values())
    tot_b = sum(v[0] for v in base_stats.values()), sum(v[1] for v in base_stats.values())
    summary = {"images": len(imgs), "objects": tot_o[1],
               "vantage_found": tot_o[0], "stock_found": tot_b[0],
               "vantage_recall": tot_o[0] / max(1, tot_o[1]), "stock_recall": tot_b[0] / max(1, tot_b[1])}
    print(f"\nHazard recall on {len(imgs)} test images ({tot_o[1]} objects):")
    print(f"  Vantage model : {summary['vantage_recall']:.1%}")
    print(f"  Stock camera  : {summary['stock_recall']:.1%}")
    for r in rows:
        print(f"  {r['class']:14s} ours {r['vantage_recall']:5.0%}   stock {r['stock_recall']:5.0%}"
              f"{'' if r['stock_knows_class'] else '   (stock model has no such class)'}")

    (out / "eval.json").write_text(json.dumps({"metrics": metrics, "summary": summary, "classes": rows},
                                              indent=2))
    chart(rows, summary, out / "recall_chart.png")

    # 3) side-by-side example pictures
    examples.sort(key=lambda e: -e[0])
    for k, (_, p, po, pb) in enumerate(examples[: args.examples]):
        img = cv2.imread(str(p))
        a = draw_detections(img, po, title="Vantage model")
        b = draw_detections(img, pb, title="Stock AI camera model")
        cv2.imwrite(str(out / "examples" / f"{k:02d}_{p.stem}.jpg"), side_by_side(b, a))
    print(f"\nReport written to {out}")
    return 0


def chart(rows, summary, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted((r for r in rows if r["objects"] >= 5),  # tiny counts make noisy bars
                  key=lambda r: (tx.TIER[r["class"]], -r["vantage_recall"]))
    names = [f"{r['class']}" + ("" if r["stock_knows_class"] else " *") for r in rows]
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(rows) + 1.6), dpi=150)
    ax.barh(y - 0.2, [r["stock_recall"] * 100 for r in rows], 0.38, color="#b8bcc4", label="Stock AI camera model")
    ax.barh(y + 0.2, [r["vantage_recall"] * 100 for r in rows], 0.38, color="#2a7de1", label="Vantage model")
    for yi, r in zip(y, rows):
        ax.text(r["vantage_recall"] * 100 + 1, yi + 0.2, f"{r['vantage_recall']:.0%}", va="center", fontsize=7,
                color="#2a7de1")
    ax.set_yticks(y, names)
    fig.text(0.01, 0.005, "* = the stock model has no such class at all", fontsize=7, color="#555")
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of real objects found in unseen test photos")
    ax.set_title(f"Found {summary['vantage_recall']:.0%} of obstacles vs {summary['stock_recall']:.0%} "
                 f"for the stock model", fontsize=11)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
