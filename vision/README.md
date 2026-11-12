# Vantage Vision: our own trained obstacle detector

The AI Camera ships with a generic model trained on everyday photos (COCO). It knows
"person", "car" and "pizza", but it has **never seen stairs, a manhole, a pole or a
traffic cone**, which are the things a blind pedestrian most needs to know about. This
folder builds, trains, tests and ships our own model that does see them.

```
 photos + labels ──► build_dataset.py ──► train.py ──► evaluate.py ──► export_imx.py ──► Pi AI Camera
   (ROD + COCO)        29 classes          YOLO11n       vs stock model    8-bit, IMX500     + vantage_core.py
                                                                                              speaks: "Stairs ahead, close."
                                           demo_app.py ◄── laptop expo demo (webcam / photos, speaks out loud)
```

## The model

* **YOLO11n**, a 2.6 M-parameter real-time detector. It is the largest family Sony's IMX500
  chip runs, so the network executes **inside the camera** and the Pi's CPU stays free for
  LiDAR, speech and haptics.
* **Fine-tuned**, not trained from zero. It starts from weights that already learned shapes
  and textures from 118k COCO photos, then learns our 29 classes. This is transfer learning:
  hours instead of weeks.

## The data (`build_dataset.py`)

| source | what it adds | size | licence |
|---|---|---|---|
| [ROD: Road Obstacle Detection](https://huggingface.co/datasets/Abtinzandi/Obstacle-Detection-Dataset-YOLO) | street photos from a pedestrian's eye level: stairs, manholes, poles, cones, barrels, crossings, bins, bike racks, guard rails | 24,326 images / 40k boxes | MIT |
| [COCO 2017](https://cocodataset.org) (only images with these objects) | indoor obstacles: tables, sofas, beds, toilets, TVs, suitcases, plus traffic lights | ~6k images | CC BY 4.0 |

All labels are mapped onto one **Vantage taxonomy** (`taxonomy.py`) of 29 classes, each with
a hazard tier that decides how urgently it is spoken:

| tier | classes | how it is spoken |
|---|---|---|
| Drop-off | stairs, manhole | first, always |
| Moving | car, bus, truck, motorbike, bicycle | high priority |
| Obstacle | person, dog, pole, tree, railing, bench, cone, hydrant, bin, plant pot, utility box, chair, bike rack, table, sofa, bed, suitcase | normal |
| Landmark | sign, traffic light, crossing, toilet, TV | when describing the scene |

"Road" and "Building" boxes from ROD are dropped. A box around the whole road is not an
obstacle, and it teaches the model to draw giant boxes.

## Run it

### A. Full training on a free GPU (recommended)
Open `Vantage_Train_Colab.ipynb` in Google Colab, set *Runtime → T4 GPU*, and run all
cells. It takes about 2 hours and downloads `vantage_model_bundle.zip` with the trained
model, the IMX500 package and the evaluation charts.

### B. On any Linux/Mac/Windows PC
```bash
pip install ultralytics huggingface_hub pyarrow gradio
python vision/build_dataset.py                 # ~2 GB download, 15-30 min
python vision/train.py --epochs 60             # GPU: ~1.5 h.   CPU only: add --quick (1 h, lower accuracy)
python vision/evaluate.py                      # writes vision/reports/
python vision/export_imx.py                    # Linux x86 only (Colab is fine)
```

### C. Expo demo on a laptop
```bash
pip install ultralytics gradio
python vision/demo_app.py                      # open http://localhost:7860
```
* **Photo tab**: upload a photo, take one with the webcam, or click an example. It shows
  *stock model vs Vantage model* side by side and speaks the sentence the wearer would hear.
* **Live webcam tab**: real-time detection of the room.
* **How it works tab**: the 5-step story for visitors.
* *Ask Claude* (optional): a richer scene description from a large vision-language model
  (set `ANTHROPIC_API_KEY`). The on-device model keeps you safe in real time; the cloud
  model answers "what kind of place is this?".

### D. On the wearable (Raspberry Pi + AI Camera)
```bash
sudo apt install imx500-all
imx500-package -i vision/models/vantage_imx_model/packerOut.zip -o vision/models/vantage_rpk
python3 vantage_core.py --model vision/models/vantage_rpk/network.rpk \
    --labels vision/models/vantage_imx_model/labels.txt --bbox-normalization --bbox-order xy
```
Everything else (LiDAR fusion, "too close" warnings, Bluetooth speech, the dashboard) works
unchanged. The new classes are already in vantage_core's safety-critical list.

## Files

| file | what it does |
|---|---|
| `taxonomy.py` | the 29 classes, hazard tiers, spoken names, and the ROD→Vantage / COCO→Vantage label maps |
| `build_dataset.py` | downloads and merges the datasets into YOLO format, with per-class statistics |
| `train.py` | fine-tunes YOLO11n with augmentations suited to a body-worn camera |
| `evaluate.py` | test-set mAP, plus hazard recall vs the stock model, a chart and side-by-side example pictures |
| `export_imx.py` | 8-bit quantisation and IMX500 compile (also exports ONNX) |
| `describe.py` | detections → "Stairs ahead, close. Two chairs on your left." |
| `draw.py` | colour-coded boxes by hazard tier |
| `demo_app.py` | the Gradio expo demo |
| `Vantage_Train_Colab.ipynb` | the whole pipeline on a free Colab GPU |
| `models/vantage.pt` | trained weights |
| `reports/` | evaluation results and charts from the last run |

## Honest limitations (good to mention to judges)
* The model detects *what* and *where in the picture*. *How far* comes from the LiDAR and
  ToF sensors, which is why Vantage fuses them.
* Merged datasets have gaps: a COCO living-room photo may contain an unlabelled pole, and
  ROD street photos never contain beds. More of our own labelled photos from the wearer's
  camera would be the next improvement.
* Glass doors, kerbs and low branches are still missing classes. Collecting those is future work.
