#!/usr/bin/env python3
"""
Step 4 - EXPORT FOR THE AI CAMERA.

The IMX500 sensor runs the network *on the camera chip itself*, so the Pi's CPU stays free.
For that, the model must be quantised to 8-bit integers and compiled by Sony's toolchain.
Ultralytics does both in one call (Linux x86 only - run this on Colab or a PC, not the Pi):

  python vision/export_imx.py --weights vision/models/vantage.pt

Produces vision/models/vantage_imx_model/ with packerOut.zip + labels.txt, and an ONNX
copy for the laptop demo. Then on the Pi:

  sudo apt install imx500-all
  imx500-package -i vantage_imx_model/packerOut.zip -o vantage_rpk
  python3 vantage_core.py --model vantage_rpk/network.rpk --labels vantage_imx_model/labels.txt \\
          --bbox-normalization --bbox-order xy
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default=str(HERE / "models" / "vantage.pt"))
    ap.add_argument("--data", default=str(HERE / "datasets" / "vantage" / "data.yaml"),
                    help="calibration images for 8-bit quantisation")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--skip-imx", action="store_true", help="only export ONNX")
    args = ap.parse_args()

    from ultralytics import YOLO

    w = Path(args.weights)
    model = YOLO(str(w))

    onnx = model.export(format="onnx", imgsz=args.imgsz, simplify=True)
    print(f"ONNX: {onnx}")

    if args.skip_imx:
        return 0
    if sys.platform != "linux":
        print("IMX export needs Linux x86 (use the Colab notebook).")
        return 1
    # nms=True puts box decoding + non-max suppression into the network, so the camera
    # outputs final boxes/scores/classes - exactly what vantage_core.py expects.
    out = model.export(format="imx", imgsz=args.imgsz, data=args.data, int8=True, nms=True)
    out = Path(out)
    labels = out / "labels.txt"
    if not labels.exists():
        labels.write_text("\n".join(model.names[i] for i in sorted(model.names)) + "\n")
    print(f"\nIMX500 package: {out}")
    for f in sorted(out.iterdir()):
        print(f"  {f.name:24s} {f.stat().st_size / 1e6:6.2f} MB")
    zipped = shutil.make_archive(str(out), "zip", out)
    print(f"\nCopy {zipped} to the Pi, unzip it, then:\n"
          f"  sudo apt install imx500-all\n"
          f"  imx500-package -i {out.name}/packerOut.zip -o vantage_rpk\n"
          f"  python3 vantage_core.py --model vantage_rpk/network.rpk --labels {out.name}/labels.txt "
          f"--bbox-normalization --bbox-order xy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
