#!/usr/bin/env python3
"""
Builds a one-page, self-contained explainer for the expo (vision/reports/expo.html) from the
real numbers of the last training run: dataset stats, training curve, test results and
side-by-side example pictures. Open it in any browser; it works offline.

  python vision/expo_page.py --run vision/runs/vantage --dataset vision/datasets/vantage
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as tx  # noqa: E402

TIER_VAR = {0: "--t-drop", 1: "--t-move", 2: "--t-obst", 3: "--t-land"}


def b64_jpg(path: Path, width: int = 1100, quality: int = 72) -> str:
    import cv2
    img = cv2.imread(str(path))
    if img.shape[1] > width:
        s = width / img.shape[1]
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def curve_svg(rows) -> str:
    """mAP50 per epoch as a small line chart (inline SVG, theme-aware via CSS vars)."""
    if not rows:
        return ""
    xs = [int(float(r["epoch"])) for r in rows]
    ys = [float(r["metrics/mAP50(B)"]) for r in rows]
    W, H, L, B, T, R = 560, 220, 44, 30, 14, 16
    ymax = max(0.1, round(max(ys) + 0.05, 1))
    xmin, xmax = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
    px = lambda x: L + (x - xmin) / (xmax - xmin) * (W - L - R)  # noqa: E731
    py = lambda y: H - B - y / ymax * (H - B - T)  # noqa: E731
    grid = []
    steps = 4
    for i in range(steps + 1):
        v = ymax * i / steps
        grid.append(f'<line x1="{L}" x2="{W - R}" y1="{py(v):.1f}" y2="{py(v):.1f}" class="grid"/>'
                    f'<text x="{L - 8}" y="{py(v) + 4:.1f}" class="axis" text-anchor="end">{v:.0%}</text>')
    for x in xs:
        if len(xs) <= 12 or x % 2 == 0 or x == xs[-1]:
            grid.append(f'<text x="{px(x):.1f}" y="{H - 10}" class="axis" text-anchor="middle">{x}</text>')
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
    area = f"{px(xs[0]):.1f},{py(0):.1f} {pts} {px(xs[-1]):.1f},{py(0):.1f}"
    end = (px(xs[-1]), py(ys[-1]))
    return (f'<svg viewBox="0 0 {W} {H}" class="curve" role="img" '
            f'aria-label="Validation mAP50 rose from {ys[0]:.0%} to {ys[-1]:.0%} over {len(xs)} epochs">'
            + "".join(grid)
            + f'<polygon points="{area}" class="area"/><polyline points="{pts}" class="line"/>'
            f'<circle cx="{end[0]:.1f}" cy="{end[1]:.1f}" r="4.5" class="dot"/>'
            f'<text x="{end[0] - 8:.1f}" y="{end[1] - 10:.1f}" class="endlabel" text-anchor="end">{ys[-1]:.0%}</text>'
            f'<text x="{(W + L) / 2:.0f}" y="{H}" class="axis" text-anchor="middle">training epoch</text></svg>')


def bars(rows) -> str:
    out = []
    for r in rows:
        tier = tx.TIER[r["class"]]
        new = "" if r["stock_knows_class"] else '<span class="new">new</span>'
        out.append(
            f'<div class="bar-row"><div class="bar-label"><i style="background:var({TIER_VAR[tier]})"></i>'
            f'{html.escape(r["class"])}{new}</div>'
            f'<div class="bar-track"><div class="bar stock" style="width:{r["stock_recall"] * 100:.1f}%"></div>'
            f'<div class="bar ours" style="width:{r["vantage_recall"] * 100:.1f}%"></div></div>'
            f'<div class="bar-num"><b>{r["vantage_recall"]:.0%}</b><span>{r["stock_recall"]:.0%}</span></div></div>')
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(HERE / "runs" / "vantage"))
    ap.add_argument("--dataset", default=str(HERE / "datasets" / "vantage"))
    ap.add_argument("--reports", default=str(HERE / "reports"))
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--note", default="", help="extra line under the results, e.g. how it was trained")
    args = ap.parse_args()

    run, rep = Path(args.run), Path(args.reports)
    ev = json.loads((rep / "eval.json").read_text())
    stats = json.loads((Path(args.dataset) / "stats.json").read_text())
    with open(run / "results.csv") as fh:
        curve = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(fh)]
    targs = {}
    if (run / "args.yaml").exists():
        import yaml
        targs = yaml.safe_load((run / "args.yaml").read_text())

    m, s = ev["metrics"], ev["summary"]
    rows = sorted((r for r in ev["classes"] if r["objects"] >= 5),
                  key=lambda r: (tx.TIER[r["class"]], -r["vantage_recall"]))
    new_rows = [r for r in rows if not r["stock_knows_class"]]
    new_found = sum(r["vantage_recall"] * r["objects"] for r in new_rows)
    new_total = sum(r["objects"] for r in new_rows)
    n_train = sum(stats["train"]["images"].values())
    n_val = sum(stats["val"]["images"].values())
    n_test = sum(stats["test"]["images"].values())
    n_boxes = sum(sum(v["boxes"].values()) for v in stats.values())
    epochs = len(curve)
    exs = sorted((rep / "examples").glob("*.jpg"))[: args.examples]
    ex_html = "\n".join(f'<figure><img src="{b64_jpg(p)}" alt="Left: stock camera model. Right: Vantage model, '
                        f'on a test photo it never trained on." loading="lazy"></figure>' for p in exs)
    class_chips = "".join(
        f'<li><i style="background:var({TIER_VAR[t]})"></i>{html.escape(n)}</li>' for n, t, _ in tx.CLASSES)
    imgsz = targs.get("imgsz", "?")
    note = html.escape(args.note) if args.note else (
        f"Trained for {epochs} epochs at {imgsz}px on a 4-core CPU as a proof of concept. "
        "The Colab notebook trains the full-size version on a free GPU.")

    page = TEMPLATE
    for k, v in {
        "{{N_TRAIN}}": f"{n_train:,}", "{{N_VAL}}": f"{n_val:,}", "{{N_TEST}}": f"{n_test:,}",
        "{{N_BOXES}}": f"{n_boxes:,}", "{{N_IMAGES}}": f"{n_train + n_val + n_test:,}",
        "{{OURS}}": f"{s['vantage_recall']:.0%}", "{{STOCK}}": f"{s['stock_recall']:.0%}",
        "{{NEW_RECALL}}": f"{(new_found / new_total) if new_total else 0:.0%}",
        "{{N_NEW}}": str(len(new_rows)), "{{EVAL_IMAGES}}": f"{s['images']:,}",
        "{{EVAL_OBJECTS}}": f"{s['objects']:,}",
        "{{MAP50}}": f"{m['mAP50']:.0%}", "{{PREC}}": f"{m['precision']:.0%}", "{{REC}}": f"{m['recall']:.0%}",
        "{{EPOCHS}}": str(epochs), "{{IMGSZ}}": str(imgsz), "{{NOTE}}": note,
        "{{CURVE}}": curve_svg(curve), "{{BARS}}": bars(rows), "{{EXAMPLES}}": ex_html,
        "{{CLASSES}}": class_chips, "{{N_CLASSES}}": str(len(tx.NAMES)),
    }.items():
        page = page.replace(k, v)
    out = Path(args.out) if args.out else rep / "expo.html"
    out.write_text(page)
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


TEMPLATE = r"""<title>Vantage Vision</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>
/* Layout: one reading column; full-width bands for the hero and results; tactile-paving dots as the only ornament.
   Type: Atkinson Hyperlegible (Braille Institute, made for low-vision readers) + IBM Plex Mono for figures. */
:root {
  --bg: #f4f6f8; --panel: #ffffff; --ink: #14202e; --muted: #556270; --line: #d9dfe6;
  --paving: #f2c300; --paving-ink: #3a2f00; --ours: #1f5fd1; --stock: #b5bdc7;
  --t-drop: #e0352b; --t-move: #f08a00; --t-obst: #e2b800; --t-land: #2e8bd8;
  --font: "Atkinson Hyperlegible", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0f151c; --panel: #17202a; --ink: #e8edf2; --muted: #9aa7b4; --line: #2a3542;
  --paving: #f2c300; --paving-ink: #2a2200; --ours: #6aa2ff; --stock: #4a5563; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #0f151c; --panel: #17202a; --ink: #e8edf2; --muted: #9aa7b4; --line: #2a3542;
  --paving: #f2c300; --paving-ink: #2a2200; --ours: #6aa2ff; --stock: #4a5563; color-scheme: dark }
* { box-sizing: border-box }
body { background: var(--bg); color: var(--ink); font: 17px/1.6 var(--font); margin: 0 }
.wrap { max-width: 980px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px));
        padding-right: max(16px, env(safe-area-inset-right, 0px)) }
h1, h2, h3 { line-height: 1.15; text-wrap: balance; margin: 0 }
h1 { font-size: clamp(2.3rem, 6vw, 3.6rem); letter-spacing: -0.01em }
h2 { font-size: 1.7rem; margin-bottom: 0.6rem }
h3 { font-size: 1.1rem }
p { margin: 0; max-width: 65ch }
.eyebrow { font: 600 0.78rem/1 var(--mono); letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted) }
.paving { height: 22px; background-color: var(--paving);
  background-image: radial-gradient(circle at 50% 50%, rgba(0,0,0,.18) 0 3.5px, transparent 4.5px);
  background-size: 18px 18px; background-position: 9px 2px }
header { padding-block: 48px 36px; display: grid; gap: 18px }
.lede { font-size: 1.2rem; color: var(--muted) }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 8px }
.stat { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px }
.stat b { display: block; font: 600 2.1rem/1.1 var(--mono); font-variant-numeric: tabular-nums }
.stat span { color: var(--muted); font-size: 0.95rem }
.stat.hl b { color: var(--ours) }
section { padding-block: 40px; display: grid; gap: 18px; border-top: 1px solid var(--line) }
figure { margin: 0 }
figure img { width: 100%; border-radius: 8px; border: 1px solid var(--line); display: block }
.figs { display: grid; gap: 14px }
.cap { color: var(--muted); font-size: 0.92rem }
ol.steps { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; counter-reset: s }
ol.steps li { counter-increment: s; display: grid; grid-template-columns: 44px 1fr; gap: 14px; align-items: start;
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px }
ol.steps li::before { content: counter(s); font: 600 1.1rem/44px var(--mono); text-align: center; width: 44px; height: 44px;
  border-radius: 50%; background: var(--paving); color: var(--paving-ink) }
ol.steps li div { min-width: 0; display: grid; gap: 4px }
ol.steps p { color: var(--muted) }
.tiers { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px }
.tier { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; display: grid; gap: 4px }
.tier h3 { display: flex; align-items: center; gap: 8px }
.tier p { color: var(--muted); font-size: 0.93rem }
i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; flex: none }
ul.chips { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px }
ul.chips li { display: flex; align-items: center; gap: 6px; border: 1px solid var(--line); background: var(--panel);
  border-radius: 999px; padding: 3px 11px 3px 9px; font-size: 0.9rem }
.sources { overflow-x: auto }
table { border-collapse: collapse; width: 100%; font-size: 0.95rem }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top }
th { font: 600 0.75rem/1.2 var(--mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted) }
td.num { font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap }
.legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.92rem; color: var(--muted) }
.legend span { display: flex; align-items: center; gap: 7px }
.sw { width: 22px; height: 10px; border-radius: 3px; display: inline-block }
.bar-row { display: grid; grid-template-columns: minmax(120px, 190px) 1fr 86px; gap: 12px; align-items: center; padding: 4px 0 }
.bar-label { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 0.95rem }
.new { font: 600 0.65rem/1 var(--mono); text-transform: uppercase; letter-spacing: 0.08em; padding: 3px 5px;
  border-radius: 4px; background: var(--paving); color: var(--paving-ink) }
.bar-track { display: grid; gap: 3px; min-width: 0 }
.bar { height: 9px; border-radius: 0 3px 3px 0; min-width: 2px }
.bar.stock { background: var(--stock) } .bar.ours { background: var(--ours) }
.bar-num { font: 500 0.85rem var(--mono); font-variant-numeric: tabular-nums; display: flex; gap: 10px; justify-content: flex-end }
.bar-num b { color: var(--ours) } .bar-num span { color: var(--muted) }
.curve { width: 100%; max-width: 560px; height: auto; display: block }
.curve .grid { stroke: var(--line); stroke-width: 1 } .curve .axis { fill: var(--muted); font: 11px var(--mono) }
.curve .line { fill: none; stroke: var(--ours); stroke-width: 2.5; stroke-linejoin: round }
.curve .area { fill: var(--ours); opacity: 0.12 } .curve .dot { fill: var(--ours) }
.curve .endlabel { fill: var(--ours); font: 600 13px var(--mono) }
.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 22px; align-items: start }
.two > * { min-width: 0 }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px; display: grid; gap: 10px }
.panel p { color: var(--muted) }
.quote { font-size: 1.35rem; font-weight: 700; border-left: 5px solid var(--paving); padding: 6px 0 6px 14px }
code { font: 0.9em var(--mono); background: var(--panel); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px }
footer { padding-block: 30px 50px; color: var(--muted); font-size: 0.88rem; border-top: 1px solid var(--line) }
@media (max-width: 560px) { .bar-row { grid-template-columns: 1fr 70px } .bar-track { grid-column: 1 / -1; grid-row: 2 } }
</style>

<div class="paving" aria-hidden="true"></div>
<div class="wrap">
<header>
  <span class="eyebrow">Vantage · assistive wearable · vision model</span>
  <h1>Teaching a camera to see what a blind pedestrian needs to know</h1>
  <p class="lede">The Raspberry Pi AI Camera ships with a general-purpose model that knows pizza and giraffes but has never seen
  stairs, a manhole, a pole or a traffic cone. We built a dataset, trained our own detector, and turned its output into one
  short spoken sentence.</p>
  <div class="stats">
    <div class="stat hl"><b>{{NEW_RECALL}}</b><span>of stairs, manholes, poles, cones and other hazards found in unseen photos. Stock model: 0%</span></div>
    <div class="stat"><b>{{N_NEW}}</b><span>hazard types the stock camera model cannot detect at all</span></div>
    <div class="stat"><b>{{N_IMAGES}}</b><span>labelled photos merged into {{N_CLASSES}} Vantage classes</span></div>
  </div>
</header>

<section>
  <h2>Same photo, two models</h2>
  <p>Left: the model that ships with the camera. Right: the Vantage model. These are test photos the model never saw during
  training. Box colour is the hazard type.</p>
  <div class="figs">{{EXAMPLES}}</div>
</section>

<section>
  <h2>From photos to a talking wearable</h2>
  <ol class="steps">
    <li><div><h3>Collect</h3><p>{{N_IMAGES}} photos with {{N_BOXES}} hand-drawn boxes from two public datasets: ROD (street obstacles
    photographed at a pedestrian's eye level) and COCO (indoor rooms). Every label is mapped to one shared list of {{N_CLASSES}} classes.</p></div></li>
    <li><div><h3>Train</h3><p>YOLO11n, a 2.6-million-parameter detector, starts from weights that already know general shapes and
    is fine-tuned on our classes. Random lighting, zoom and mirror changes teach it to cope with rain, night and a tilted head.</p></div></li>
    <li><div><h3>Test</h3><p>We measure it on {{N_TEST}} photos kept aside and never used for training, and compare it with the stock model.</p></div></li>
    <li><div><h3>Shrink</h3><p>The network is quantised to 8-bit integers and compiled for the Sony IMX500 chip. The AI then runs
    inside the camera itself, leaving the Pi free for LiDAR, speech and haptics.</p></div></li>
    <li><div><h3>Speak</h3><p>Detections are fused with LiDAR distance and ranked by danger, then read out on the bone-conduction
    headset. The vibration motor pulses faster as things get closer.</p></div></li>
  </ol>
  <p class="quote">"Stairs ahead, close. Two chairs on your left."</p>
</section>

<section>
  <h2>What it can see</h2>
  <p>Classes are ranked by how urgently a walking user needs to hear about them.</p>
  <div class="tiers">
    <div class="tier"><h3><i style="background:var(--t-drop)"></i>Drop-off</h3><p>Stairs and open manholes. Spoken first, always.</p></div>
    <div class="tier"><h3><i style="background:var(--t-move)"></i>Moving</h3><p>Cars, buses, trucks, motorbikes and bicycles.</p></div>
    <div class="tier"><h3><i style="background:var(--t-obst)"></i>Obstacle</h3><p>Anything you could walk into: poles, cones, bins, benches, chairs, tables, people.</p></div>
    <div class="tier"><h3><i style="background:var(--t-land)"></i>Landmark</h3><p>Signs, traffic lights, crossings, TVs. Useful context, never an alarm.</p></div>
  </div>
  <ul class="chips">{{CLASSES}}</ul>
  <div class="sources">
  <table>
    <thead><tr><th>Source</th><th>What it adds</th><th>Licence</th></tr></thead>
    <tbody>
      <tr><td>ROD: Road Obstacle Detection</td><td>Street scenes from a pedestrian's view: stairs, manholes, poles, cones, barrels, crossings, bins, bike racks, guard rails</td><td>MIT</td></tr>
      <tr><td>COCO 2017 (indoor subset)</td><td>Rooms and buildings: tables, sofas, beds, toilets, TVs, suitcases, plus traffic lights</td><td>CC BY 4.0</td></tr>
    </tbody>
  </table>
  </div>
  <p class="cap">Split: <span class="num">{{N_TRAIN}}</span> training, <span class="num">{{N_VAL}}</span> validation and
  <span class="num">{{N_TEST}}</span> test photos.</p>
</section>

<section>
  <h2>Results on photos it has never seen</h2>
  <div class="two">
    <div class="panel">
      <span class="eyebrow">Learning curve</span>
      {{CURVE}}
      <p>Detection accuracy (mAP50) on the validation set after each pass over the training data.</p>
    </div>
    <div class="panel">
      <span class="eyebrow">Test set</span>
      <table>
        <tbody>
          <tr><td>mAP50 (all {{N_CLASSES}} classes)</td><td class="num">{{MAP50}}</td></tr>
          <tr><td>Precision (boxes that are right)</td><td class="num">{{PREC}}</td></tr>
          <tr><td>Recall (objects that are found)</td><td class="num">{{REC}}</td></tr>
          <tr><td>Recall comparison sample</td><td class="num">{{EVAL_IMAGES}} photos, {{EVAL_OBJECTS}} objects</td></tr>
        </tbody>
      </table>
      <p>{{NOTE}}</p>
    </div>
  </div>
  <div class="legend"><span><b class="sw" style="background:var(--ours)"></b>Vantage model</span>
    <span><b class="sw" style="background:var(--stock)"></b>Stock camera model</span>
    <span><span class="new">new</span>class the stock model does not have</span></div>
  <div class="bars">{{BARS}}</div>
  <p class="cap">Share of real objects in the test photos that each model found (a hit means the right class and a box overlapping at least 50%).</p>
</section>

<section>
  <h2>Why a small model, and where a large one fits</h2>
  <div class="two">
    <div class="panel"><h3>On the camera: the trained detector</h3>
      <p>Runs about 15 times a second inside the IMX500, works offline, and costs almost no battery. Safety warnings
      cannot wait for a network round-trip, so this is what keeps the wearer from walking into things.</p></div>
    <div class="panel"><h3>On request: a vision-language model</h3>
      <p>A large model such as Claude can describe a whole scene or read a menu, but it needs the internet and a few seconds.
      Vantage uses it for "tell me about this place", never for collision warnings.</p></div>
  </div>
</section>

<section>
  <h2>Limits and next steps</h2>
  <div class="two">
    <div class="panel"><p>The camera tells us <em>what</em> and <em>which direction</em>. Distance comes from the LiDAR and
    time-of-flight sensors, which is why Vantage fuses them.</p></div>
    <div class="panel"><p>Glass doors, kerbs and low branches are not in any public dataset we found. Next: label our own photos
    taken from the wearable's camera and add them to training.</p></div>
  </div>
</section>
</div>
<footer><div class="wrap">Built with Ultralytics YOLO11, ROD (MIT) and COCO 2017 (CC BY 4.0). Code: <code>vision/</code> in the Vantage repository.</div></footer>
"""


if __name__ == "__main__":
    sys.exit(main())
