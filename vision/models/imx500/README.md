# Vantage model for the Raspberry Pi AI Camera (IMX500)

Built from `vision/models/vantage.pt` (round 2, 9 epochs), 320x320 input, 8-bit quantised,
box decoding and non-max suppression inside the network. Uses 3.8 MB of the chip's 8 MB (48%).

| file | what it is |
|---|---|
| `packerOut.zip` | compiled network from Sony's converter |
| `labels.txt` | the 29 class names, in the model's output order |
| `model_imx_MemoryReport.json` | on-chip memory report |

On the Pi (from the repo folder):

```bash
sudo apt install imx500-all
imx500-package -i vision/models/imx500/packerOut.zip -o vision/models/imx500/rpk
python3 vantage_core.py --model vision/models/imx500/rpk/network.rpk \
    --labels vision/models/imx500/labels.txt --bbox-normalization --bbox-order xy
```

To rebuild: `python vision/export_imx.py --imgsz 320` on Linux x86 with Python 3.10-3.12,
Java 17+, `imx500-converter[pt]==3.19.2` and `pulp<3`.
