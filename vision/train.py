#!/usr/bin/env python3
"""
Step 2 - TRAIN.

Fine-tunes YOLO11n (2.6 M parameters - the largest family the Raspberry Pi AI Camera's
IMX500 chip runs) on the Vantage dataset. Starts from COCO-pretrained weights, so the
model already "knows" edges, shapes and people and only has to learn our 29 classes.

  GPU (Colab T4, ~1.5 h):  python vision/train.py --epochs 60
  CPU proof of concept:    python vision/train.py --quick          (~1 h on 4 cores)

Results land in vision/runs/<name>/ : weights/best.pt, results.png, confusion_matrix.png ...
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(HERE / "datasets" / "vantage" / "data.yaml"))
    ap.add_argument("--model", default="yolo11n.pt", help="starting weights (yolo11n.pt or yolov8n.pt for IMX500)")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=640, help="640 = what the IMX500 runs")
    ap.add_argument("--batch", type=int, default=-1, help="-1 = auto-fit GPU memory")
    ap.add_argument("--device", default=None, help="0 for GPU, cpu, or leave empty for auto")
    ap.add_argument("--name", default="vantage")
    ap.add_argument("--hours", type=float, default=None, help="stop after this many hours")
    ap.add_argument("--fraction", type=float, default=1.0, help="use this fraction of the train set")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--quick", action="store_true",
                    help="CPU proof of concept: 320 px, small batch, time-boxed to 1 hour")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    from ultralytics import YOLO

    kw = dict(
        data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        project=str(HERE / "runs"), name=args.name, exist_ok=True,
        fraction=args.fraction, workers=args.workers, seed=0, plots=True,
        patience=20, cos_lr=True, close_mosaic=10,
        # Augmentations tuned for a chest/head-mounted camera: no vertical flips (stairs
        # upside down are not stairs), mild rotation (the wearer tilts), strong
        # brightness/colour changes (indoor <-> outdoor, night).
        fliplr=0.5, flipud=0.0, degrees=5.0, hsv_v=0.5, hsv_s=0.6, scale=0.5, mosaic=1.0,
    )
    if args.device is not None:
        kw["device"] = args.device
    if args.hours:
        kw["time"] = args.hours
    if args.quick:
        kw.update(imgsz=320, batch=32, workers=4, device="cpu", mosaic=0.5,
                  time=args.hours or 1.0, epochs=max(args.epochs, 1), patience=100, close_mosaic=0)

    model = YOLO(args.model)
    if args.resume:
        last = HERE / "runs" / args.name / "weights" / "last.pt"
        model = YOLO(str(last))
        model.train(resume=True)
    else:
        model.train(**kw)

    best = HERE / "runs" / args.name / "weights" / "best.pt"
    if best.exists():
        dst = HERE / "models" / f"{args.name}.pt"
        dst.parent.mkdir(exist_ok=True)
        shutil.copy2(best, dst)
        print(f"\nBest weights copied to {dst}")
        print(f"Next: python vision/evaluate.py --weights {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
