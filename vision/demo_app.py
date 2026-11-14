#!/usr/bin/env python3
"""
THE EXPO DEMO - a clean, single-page web app that explains and demonstrates Vantage Vision.

  pip install ultralytics gradio
  python vision/demo_app.py                  # open http://localhost:7860
  python vision/demo_app.py --host 0.0.0.0   # reachable from a phone on the same Wi-Fi

Tabs
  Try it          photo / webcam / examples -> stock model vs Vantage model, spoken sentence
  Walk simulator  "walks" toward an obstacle: camera zooms in while a simulated LiDAR distance
                  falls; shows the warning level, the vibration motor and what gets spoken
  Sensor fusion   sliders for distance / object / direction -> the exact decision Vantage makes
  Robustness lab  rain, night, blur, tilt ... -> does the model still see it? (why we augment)
  Results         training curve, accuracy per class vs the stock model, dataset size
  How it works    the whole system explained in plain language
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as tx  # noqa: E402
from describe import Det, describe, direction  # noqa: E402
from draw import draw_detections  # noqa: E402

# Same thresholds as vantage_core.py / vantage_proximity.py on the wearable
CRITICAL_CM, WARNING_CM = 50, 100
HAPTIC_NEAR_CM, HAPTIC_FAR_CM = 15, 120

SPEAK_JS = """
(text) => {
  if (!text || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  window.speechSynthesis.speak(u);
}
"""

# Open in light mode regardless of the visitor's OS setting: the design is white on purpose.
HEAD = """
<script>
(() => { const u = new URL(window.location);
  if (u.searchParams.get('__theme') !== 'light') { u.searchParams.set('__theme', 'light'); window.location.replace(u); } })();
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap">
"""

CSS = """
:root { --ink:#111418; --muted:#6b7280; --line:#e8eaed; --soft:#f7f8f9; --accent:#111418;
        --drop:#e0352b; --move:#f08a00; --obst:#d9a900; --land:#2e8bd8; --ours:#1f5fd1; --stock:#c3c8cf; }
.gradio-container { max-width: 1180px !important; margin: 0 auto !important; background: #fff !important;
  font-family: Inter, system-ui, sans-serif !important; color: var(--ink) }
body, .gradio-container .main { background: #fff !important }
footer { display: none !important }
.block, .form { border-color: var(--line) !important; box-shadow: none !important }
.gr-group, .block.padded { border-radius: 12px !important }
button.primary { background: var(--ink) !important; color: #fff !important; border: none !important; border-radius: 999px !important }
button.secondary { background: #fff !important; border: 1px solid var(--line) !important; border-radius: 999px !important }
.tab-nav button, button[role="tab"] { font-weight: 500 !important; font-size: 15px !important }
button[role="tab"][aria-selected="true"] { color: var(--ink) !important; border-color: var(--ink) !important }
#hero { padding: 36px 4px 8px }
#hero h1 { font-size: 44px; line-height: 1.05; letter-spacing: -0.02em; margin: 0 0 10px; font-weight: 700 }
#hero p { font-size: 18px; color: var(--muted); max-width: 720px; margin: 0 }
.kicker { font: 500 12px/1 'JetBrains Mono', monospace; letter-spacing: .14em; text-transform: uppercase; color: var(--muted) }
.legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--muted); padding: 6px 4px 2px }
.legend span { display: inline-flex; align-items: center; gap: 7px }
.dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block }
#spoken textarea { font-size: 22px !important; font-weight: 600 !important; line-height: 1.35 !important;
  border: none !important; background: var(--soft) !important; border-radius: 12px !important; padding: 16px !important }
.note { color: var(--muted); font-size: 14px }
.prose { max-width: 760px }
.prose h2 { font-size: 26px; letter-spacing: -0.01em; margin: 28px 0 8px }
.prose h3 { font-size: 17px; margin: 18px 0 4px }
.prose p, .prose li { color: #374151; font-size: 16px; line-height: 1.65 }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 14px 0 }
.step { border: 1px solid var(--line); border-radius: 12px; padding: 16px }
.step b { display: block; font-size: 15px; margin: 6px 0 4px }
.step p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.5 }
.step .n { font: 500 12px 'JetBrains Mono', monospace; color: var(--muted) }
.flow { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0 }
.flow div { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; font-size: 14px; background: #fff }
.flow i { color: var(--muted); font-style: normal }
.panel { border: 1px solid var(--line); border-radius: 14px; padding: 20px; display: grid; gap: 14px; background: #fff }
.big { font: 700 56px/1 Inter, sans-serif; letter-spacing: -0.03em }
.big small { font-size: 20px; color: var(--muted); font-weight: 500 }
.pill { display: inline-block; padding: 5px 12px; border-radius: 999px; font-weight: 600; font-size: 13px; color: #fff }
.meter { height: 12px; background: var(--soft); border-radius: 999px; overflow: hidden }
.meter > div { height: 100%; border-radius: 999px; transition: width .2s }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px }
.lab { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em }
.val { font-size: 18px; font-weight: 600 }
.motor { width: 46px; height: 46px; border-radius: 50%; background: var(--ink); margin: 4px 0 }
@keyframes buzz { 0%,100% { transform: translate(0,0) } 25% { transform: translate(-2px,1px) } 75% { transform: translate(2px,-1px) } }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px }
.stat { border: 1px solid var(--line); border-radius: 12px; padding: 16px }
.stat b { display: block; font: 700 30px/1.1 Inter, sans-serif; letter-spacing: -0.02em }
.stat span { color: var(--muted); font-size: 13px }
.bar-row { display: grid; grid-template-columns: 170px 1fr 84px; gap: 12px; align-items: center; padding: 3px 0; font-size: 14px }
.bar-label { display: flex; align-items: center; gap: 8px }
.bar-track { display: grid; gap: 3px } .bar { height: 8px; border-radius: 0 3px 3px 0; min-width: 2px }
.bar.stock { background: var(--stock) } .bar.ours { background: var(--ours) }
.bar-num { font: 500 13px 'JetBrains Mono', monospace; display: flex; gap: 10px; justify-content: flex-end }
.bar-num b { color: var(--ours) } .bar-num span { color: var(--muted) }
.new { font: 600 10px 'JetBrains Mono', monospace; padding: 2px 5px; border-radius: 4px; background: #111418; color: #fff; letter-spacing: .05em }
.bar-label i { width: 10px; height: 10px; border-radius: 3px; display: inline-block }
.curve { width: 100%; max-width: 560px } .curve .grid { stroke: var(--line) } .curve .axis { fill: var(--muted); font: 11px 'JetBrains Mono', monospace }
.curve .line { fill: none; stroke: var(--ours); stroke-width: 2.5 } .curve .area { fill: var(--ours); opacity: .1 }
.curve .dot { fill: var(--ours) } .curve .endlabel { fill: var(--ours); font: 600 13px 'JetBrains Mono', monospace }
"""

TIER_COLOR = {0: "var(--drop)", 1: "var(--move)", 2: "var(--obst)", 3: "var(--land)"}
TIER_VAR = {0: "--drop", 1: "--move", 2: "--obst", 3: "--land"}

HERO = """
<div id="hero">
  <div class="kicker">Vantage · wearable guide for blind and low-vision people</div>
  <h1>Vantage Vision</h1>
  <p>A camera AI we trained ourselves to spot what a blind pedestrian needs to know: stairs, manholes, poles,
  cones, furniture and traffic. It runs inside the camera on the wearable and turns what it sees into one short spoken sentence.</p>
</div>
<div class="legend">
  <span><b class="dot" style="background:var(--drop)"></b>Drop-off: stairs, manhole</span>
  <span><b class="dot" style="background:var(--move)"></b>Moving: car, bus, bike</span>
  <span><b class="dot" style="background:var(--obst)"></b>Obstacle: pole, chair, bin, table</span>
  <span><b class="dot" style="background:var(--land)"></b>Landmark: sign, crossing, TV</span>
</div>
"""


# ---------------------------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------------------------

class Engine:
    def __init__(self, weights: str, baseline: str, imgsz: int):
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.base = YOLO(baseline) if baseline else None
        self.imgsz = imgsz

    def run(self, rgb, conf=0.35, base=False):
        model = self.base if base else self.model
        r = model.predict(rgb[:, :, ::-1], conf=conf, imgsz=640 if base else self.imgsz, verbose=False)[0]
        dets = []
        if r.boxes is not None:
            for b, c, k in zip(r.boxes.xyxyn.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
                name = r.names[int(k)]
                if base:
                    name = tx.COCO_MAP.get(name)
                    if name is None:
                        continue
                dets.append((name, float(c), tuple(b)))
        return dets


def draw(rgb, dets, title=""):
    return draw_detections(rgb[:, :, ::-1], dets, title=title)[:, :, ::-1]


def target_of(dets):
    """The detection Vantage would talk about first: most dangerous tier, then nearest."""
    if not dets:
        return None
    return min(dets, key=lambda d: (tx.TIER[d[0]], -Det(*d).closeness))


# ---------------------------------------------------------------------------------------------
# Decision logic shared by the simulators (mirrors vantage_core + vantage_proximity)
# ---------------------------------------------------------------------------------------------

def decide(label, where, dist_cm):
    tier = tx.TIER.get(label, 2)
    name = tx.SPOKEN.get(label, label)
    c = 0.0 if dist_cm >= HAPTIC_FAR_CM else 1.0 if dist_cm <= HAPTIC_NEAR_CM else \
        (HAPTIC_FAR_CM - dist_cm) / (HAPTIC_FAR_CM - HAPTIC_NEAR_CM)
    pulse_hz = 1 + 7 * c if c > 0 else 0
    if tier == 3:
        level, color, say = "Info", "var(--land)", f"{name.capitalize()} {where}."
    elif dist_cm <= CRITICAL_CM or (tier == 0 and dist_cm <= WARNING_CM):
        level, color = "Critical", "var(--drop)"
        say = f"Stop. {name.capitalize()} {where}, {int(round(dist_cm, -1))} centimetres."
    elif dist_cm <= WARNING_CM:
        level, color, say = "Warning", "var(--move)", f"{name.capitalize()} {where}, {dist_cm / 100:.1f} metres."
    else:
        level, color, say = "Aware", "var(--obst)" if tier < 3 else "var(--land)", f"{name.capitalize()} {where}."
    return dict(level=level, color=color, say=say, closeness=c, pulse_hz=pulse_hz, tier=tier)


def status_html(dist_cm, d, label, extra=""):
    shake = f"animation: buzz {max(0.06, 1 / max(d['pulse_hz'], 0.1)):.2f}s infinite;" if d["pulse_hz"] else ""
    return f"""
<div class="panel">
  <div class="row2">
    <div><div class="lab">LiDAR distance</div><div class="big">{dist_cm / 100:.2f}<small> m</small></div></div>
    <div><div class="lab">Alert level</div><div style="margin-top:10px"><span class="pill" style="background:{d['color']}">{d['level']}</span></div>
      <div class="note" style="margin-top:8px">{tx.TIER_NAMES[d['tier']]} · {label}</div></div>
  </div>
  <div><div class="lab">Vibration motor</div>
    <div style="display:flex;align-items:center;gap:14px">
      <div class="motor" style="{shake} opacity:{0.15 + 0.85 * d['closeness']:.2f}"></div>
      <div style="flex:1"><div class="meter"><div style="width:{d['closeness'] * 100:.0f}%;background:{d['color']}"></div></div>
      <div class="note" style="margin-top:6px">{d['closeness'] * 100:.0f}% strength · {d['pulse_hz']:.1f} pulses per second</div></div>
    </div>
  </div>
  {extra}
</div>"""


# ---------------------------------------------------------------------------------------------
# Tab callbacks
# ---------------------------------------------------------------------------------------------

def make_callbacks(E: Engine, claude_model: str):
    def analyse(img, conf, compare, landmarks):
        if img is None:
            return None, None, "", [], ""
        t0 = time.perf_counter()
        ours = E.run(img, conf)
        ms = (time.perf_counter() - t0) * 1000
        base_img = draw(img, E.run(img, conf, base=True), "Stock camera model") if compare and E.base else None
        sentence = describe([Det(*d) for d in ours], include_landmarks=landmarks)
        table = [[d[0], tx.TIER_NAMES[tx.TIER[d[0]]], f"{d[1]:.0%}", direction(Det(*d).cx)]
                 for d in sorted(ours, key=lambda d: (tx.TIER[d[0]], -d[1]))]
        info = f"{len(ours)} objects · {ms:.0f} ms on this computer's CPU (on the camera chip it runs at ~15 frames/s)"
        return draw(img, ours, "Vantage model"), base_img, sentence, table, info

    def walk(img, steps=28):
        if img is None:
            yield None, "<div class='note'>Pick a scene first.</div>", "", "Pick a scene first."
            return
        h, w = img.shape[:2]
        full = E.run(img, 0.3)
        tgt = target_of(full)
        cx, cy = ((tgt[2][0] + tgt[2][2]) / 2, (tgt[2][1] + tgt[2][3]) / 2) if tgt else (0.5, 0.6)
        last_level, said = None, ""
        log = []
        for i in range(steps + 1):
            t = i / steps
            dist = 400 - 365 * t                       # 4.0 m -> 0.35 m
            z = 1 + 1.8 * t                            # camera "walks" toward the target
            cw, ch = w / z, h / z
            x0 = int(np.clip(cx * w - cw / 2, 0, w - cw))
            y0 = int(np.clip(cy * h - ch / 2, 0, h - ch))
            crop = cv2.resize(img[y0:y0 + int(ch), x0:x0 + int(cw)], (w, h), interpolation=cv2.INTER_LINEAR)
            dets = E.run(crop, 0.3)
            t2 = target_of(dets) or tgt
            label = t2[0] if t2 else "obstacle"
            where = direction(Det(*t2).cx) if t2 else "ahead"
            d = decide(label, where, dist)
            if d["level"] != last_level:
                said = d["say"]
                last_level = d["level"]
                log.append(f"{dist / 100:.1f} m → <b>{d['level']}</b>: “{said}”")
            extra = "<div><div class='lab'>What the wearer heard</div><div class='note'>" + "<br>".join(log) + "</div></div>"
            yield draw(crop, dets, f"Walking · {dist / 100:.2f} m"), status_html(dist, d, label, extra), said, \
                f"Step {i}/{steps}"
            time.sleep(0.12)

    def fusion(label, where_pos, dist_cm):
        where = direction(where_pos / 100)
        d = decide(label, where, dist_cm)
        rules = f"""
<div><div class='lab'>Why</div><div class='note'>
<b>{label}</b> is a <b>{tx.TIER_NAMES[d['tier']]}</b> class.
Critical below {CRITICAL_CM} cm (drop-offs: below {WARNING_CM} cm), warning below {WARNING_CM} cm.
The motor starts at {HAPTIC_FAR_CM} cm and is at full strength by {HAPTIC_NEAR_CM} cm.
Landmarks are mentioned but never raise an alarm.</div></div>"""
        return status_html(dist_cm, d, label, rules), d["say"]

    def robust(img, light, rain, blur, tilt, flip, fog):
        if img is None:
            return None, None, ""
        a = img.astype(np.float32)
        a = a * light
        if fog:
            a = a * (1 - fog) + 235 * fog
        if rain:
            rng = np.random.default_rng(0)
            n = int(rain * 900)
            layer = np.zeros(img.shape[:2], np.uint8)
            for _ in range(n):
                x, y = rng.integers(0, img.shape[1]), rng.integers(0, img.shape[0])
                cv2.line(layer, (x, y), (x - 4, y + 18), 255, 1)
            a = np.where(layer[..., None] > 0, a * 0.5 + 110, a)
        a = np.clip(a, 0, 255).astype(np.uint8)
        if blur:
            k = int(blur) * 2 + 1
            a = cv2.GaussianBlur(a, (k, k), 0)
        if tilt:
            M = cv2.getRotationMatrix2D((a.shape[1] / 2, a.shape[0] / 2), tilt, 1.0)
            a = cv2.warpAffine(a, M, (a.shape[1], a.shape[0]), borderMode=cv2.BORDER_REFLECT)
        if flip:
            a = a[:, ::-1].copy()
        before = E.run(img, 0.35)
        after = E.run(a, 0.35)
        kept = len({d[0] for d in after} & {d[0] for d in before})
        msg = (f"Original: {len(before)} objects · changed: {len(after)} objects · "
               f"{kept} of {len({d[0] for d in before})} object types still recognised")
        return draw(img, before, "Original"), draw(a, after, "Changed conditions"), msg

    def ask_claude(img, spoken):
        if img is None:
            return "Take or upload a picture first."
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return "Optional feature: set ANTHROPIC_API_KEY before starting the demo to enable it."
        import anthropic
        small = img
        if max(img.shape[:2]) > 1024:
            s = 1024 / max(img.shape[:2])
            small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", small[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 85])
        msg = anthropic.Anthropic().messages.create(
            model=claude_model, max_tokens=300,
            system=("You are the voice of Vantage, a wearable that guides a blind person. In at most 3 short spoken "
                    "sentences: first anything they could trip on, fall down or walk into, with direction and rough "
                    "distance; then one sentence of context about the place. No markdown."),
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(jpg.tobytes()).decode()}},
                {"type": "text", "text": f"The on-camera detector said: {spoken or 'nothing'}. Describe the scene."}]}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    def live(img):
        if img is None:
            return None, ""
        dets = E.run(img, 0.4)
        return draw(img, dets), describe([Det(*d) for d in dets], include_landmarks=False)

    return analyse, walk, fusion, robust, ask_claude, live


# ---------------------------------------------------------------------------------------------
# Static content
# ---------------------------------------------------------------------------------------------

def results_html(reports: Path, run: Path, dataset_stats: Path | None) -> str:
    try:
        from expo_page import bars, curve_svg
        import csv
        ev = json.loads((reports / "eval.json").read_text())
    except Exception:  # noqa: BLE001
        return "<div class='note'>Run <code>python vision/evaluate.py</code> to fill this tab.</div>"
    s, m = ev["summary"], ev["metrics"]
    rows = sorted((r for r in ev["classes"] if r["objects"] >= 5),
                  key=lambda r: (tx.TIER[r["class"]], -r["vantage_recall"]))
    new = [r for r in rows if not r["stock_knows_class"]]
    new_rec = sum(r["vantage_recall"] * r["objects"] for r in new) / max(1, sum(r["objects"] for r in new))
    curve = ""
    csv_path = run / "results.csv" if (run / "results.csv").exists() else reports / "results.csv"
    if csv_path.exists():
        with open(csv_path) as fh:
            pts = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(fh)]
        curve = curve_svg(pts) if len(pts) >= 2 else \
            f"<p class='note'>Training in progress: {len(pts)} epoch(s) done so far. Restart the demo to refresh.</p>"
    n_img = ""
    if dataset_stats and dataset_stats.exists():
        st = json.loads(dataset_stats.read_text())
        n_img = f"{sum(sum(v['images'].values()) for v in st.values()):,}"
    bar_html = bars(rows).replace("var(--t-drop)", "var(--drop)").replace("var(--t-move)", "var(--move)") \
        .replace("var(--t-obst)", "var(--obst)").replace("var(--t-land)", "var(--land)")
    return f"""
<div class="prose" style="max-width:none">
<div class="stats">
  <div class="stat"><b style="color:var(--ours)">{new_rec:.0%}</b><span>of hazards the stock model cannot see (stairs, manholes, poles, cones ...) found by ours. Stock: 0%</span></div>
  <div class="stat"><b>{len(new)}</b><span>new hazard types the stock camera model has no class for</span></div>
  <div class="stat"><b>{m['mAP50']:.0%}</b><span>mAP50 on the test photos, all 29 classes</span></div>
  <div class="stat"><b>{n_img or '—'}</b><span>labelled photos in our dataset</span></div>
</div>
<h2>Learning curve</h2>
<p>Accuracy on validation photos after each pass ("epoch") over the training data.</p>
{curve}
<h2>Found in unseen test photos, per class</h2>
<div class="legend"><span><b class="dot" style="background:var(--ours)"></b>Vantage model</span>
<span><b class="dot" style="background:var(--stock)"></b>Stock camera model</span><span><span class="new">NEW</span> class the stock model lacks</span></div>
<div>{bar_html}</div>
<p class="note">Measured on {s['images']} test photos containing {s['objects']} real objects. A hit means the right class with a box
overlapping the true one by at least 50%. Everyday classes like person and car are already in the stock model;
our gain is the hazards it was never taught.</p>
</div>"""


HOW = f"""
<div class="prose">
<h2>The problem</h2>
<p>The Raspberry Pi AI Camera comes with a model trained on COCO, a famous set of everyday photos. It recognises 80
things, including pizza, giraffes and toothbrushes, but <b>not stairs, manholes, poles, traffic cones, railings or
pedestrian crossings</b>. Those are exactly what a blind person most needs to know about.</p>

<h2>What we built</h2>
<div class="steps">
  <div class="step"><span class="n">1 · Collect</span><b>Data</b><p>~21,000 labelled photos from two public datasets: ROD (street obstacles shot at eye level) and COCO (indoor rooms).</p></div>
  <div class="step"><span class="n">2 · Organise</span><b>29 classes</b><p>Every label is mapped into one list, sorted by danger: drop-offs, moving things, obstacles, landmarks.</p></div>
  <div class="step"><span class="n">3 · Train</span><b>Fine-tuning</b><p>YOLO11n (2.6 M parameters) starts from general vision knowledge and learns our classes from our photos.</p></div>
  <div class="step"><span class="n">4 · Test</span><b>Unseen photos</b><p>We score it on photos kept aside from training and compare with the stock model.</p></div>
  <div class="step"><span class="n">5 · Shrink</span><b>Into the camera</b><p>Converted to 8-bit numbers and compiled for the Sony IMX500, so the AI runs inside the camera chip.</p></div>
  <div class="step"><span class="n">6 · Speak</span><b>Sentence + buzz</b><p>Fused with LiDAR distance, ranked by danger, spoken on bone-conduction headphones, felt on a vibration motor.</p></div>
</div>

<h2>Inside the wearable</h2>
<div class="flow"><div>AI Camera<br><span class="note">what + where</span></div><i>→</i>
<div>LiDAR + ToF<br><span class="note">how far</span></div><i>→</i>
<div>Raspberry Pi CM5<br><span class="note">fuse + rank</span></div><i>→</i>
<div>Bone-conduction audio<br><span class="note">"Stairs ahead, close"</span></div><i>+</i>
<div>Vibration motor<br><span class="note">faster = closer</span></div></div>
<p>The camera says <i>what</i> is in front of you and in which direction. The TFmini Plus LiDAR and the VL53L3CX
time-of-flight sensor say <i>how far</i>. The Pi combines them: below {WARNING_CM} cm you get a warning, below {CRITICAL_CM} cm
(or {WARNING_CM} cm for stairs and manholes) a critical alert that interrupts anything else being said.</p>

<h2>How a computer learns to see</h2>
<h3>Labels</h3><p>A person draws a box around each object in a photo and names it. 21,000 photos give about 90,000 boxes.</p>
<h3>Training</h3><p>The model guesses boxes, gets told how wrong it was, and adjusts its 2.6 million numbers a tiny bit. Repeated
over every photo many times, the guesses get better. We start from a model that has already learned edges, shapes and
textures, so it only has to learn what our 29 things look like (transfer learning).</p>
<h3>Augmentation</h3><p>Each time a photo is shown it is changed slightly: brighter or darker, mirrored, zoomed, tilted, four
photos stitched together. The model never sees the exact same picture twice, so it learns the object rather than the photo.
Try it in the <b>Robustness lab</b> tab.</p>
<h3>Measuring honestly</h3><p>Some photos are locked away and never used for training. The scores in <b>Results</b> come only from those.</p>

<h2>Why a small model on the camera?</h2>
<p>Safety warnings must be instant and must work without internet. A small trained detector runs about 15 times a
second inside the camera and costs almost no battery. Large vision-language models such as Claude can describe a whole
scene in rich detail, but they need the internet and a few seconds, so Vantage uses them only for "tell me about this
place", never for collision warnings.</p>

<h2>Limits and next steps</h2>
<ul><li>No public dataset has glass doors, kerbs or low branches. Next we will label photos taken from the wearable itself.</li>
<li>The camera alone cannot measure distance, which is why Vantage pairs it with LiDAR and time-of-flight sensors.</li>
<li>More training on a GPU (the included Colab notebook) gives higher accuracy than this CPU-trained version.</li></ul>
</div>
"""


# ---------------------------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------------------------

def build_ui(E: Engine, examples, claude_model, reports, run, stats):
    import gradio as gr
    analyse, walk, fusion, robust, ask_claude, live = make_callbacks(E, claude_model)
    ex = [[str(e)] for e in examples]

    with gr.Blocks(title="Vantage Vision") as demo:
        gr.HTML(HERO)
        with gr.Tabs():
            with gr.Tab("Try it"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=4):
                        inp = gr.Image(label="Scene", sources=["upload", "webcam", "clipboard"], type="numpy", height=320)
                        if ex:
                            gr.Examples(ex, [inp], label="Example scenes (photos the model never trained on)",
                                        examples_per_page=12)
                        conf = gr.Slider(0.1, 0.9, value=0.35, step=0.05, label="Confidence threshold")
                        with gr.Row():
                            compare = gr.Checkbox(value=True, label="Compare with stock model")
                            landmarks = gr.Checkbox(value=True, label="Mention landmarks")
                    with gr.Column(scale=7):
                        spoken = gr.Textbox(label="What the wearer hears", elem_id="spoken", lines=2, interactive=False)
                        with gr.Row():
                            speak = gr.Button("Speak it", variant="primary", scale=0)
                            info = gr.Markdown(elem_classes="note")
                        with gr.Row():
                            out_base = gr.Image(label="Stock camera model", height=330, show_label=True)
                            out_ours = gr.Image(label="Vantage model (ours)", height=330)
                        table = gr.Dataframe(headers=["object", "type", "confidence", "where"], label="Detections")
                        with gr.Accordion("Ask Claude for a detailed description (optional, needs internet)", open=False):
                            ask = gr.Button("Ask Claude", variant="secondary")
                            claude_out = gr.Textbox(label="Claude says", lines=3)
                outs = [out_ours, out_base, spoken, table, info]
                for trig in (inp.change, conf.release, compare.change, landmarks.change):
                    trig(analyse, [inp, conf, compare, landmarks], outs)
                speak.click(None, [spoken], None, js=SPEAK_JS)
                ask.click(ask_claude, [inp, spoken], [claude_out]).then(None, [claude_out], None, js=SPEAK_JS)

            with gr.Tab("Walk simulator"):
                gr.Markdown("**Simulate walking toward an obstacle.** The camera image zooms in as you approach while a "
                            "simulated LiDAR distance falls from 4 m to 35 cm. Watch the alert level, the vibration motor "
                            "and what Vantage says change, exactly as on the wearable.", elem_classes="note")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=4):
                        w_in = gr.Image(label="Scene", type="numpy", height=280, sources=["upload", "webcam"])
                        if ex:
                            gr.Examples(ex, [w_in], label="Pick a scene", examples_per_page=12)
                        w_go = gr.Button("Start walking", variant="primary")
                        w_step = gr.Markdown(elem_classes="note")
                    with gr.Column(scale=7):
                        w_out = gr.Image(label="Camera view", height=380)
                        w_said = gr.Textbox(label="What the wearer hears", elem_id="spoken", interactive=False)
                        w_panel = gr.HTML()
                w_go.click(walk, [w_in], [w_out, w_panel, w_said, w_step])
                w_said.change(None, [w_said], None, js=SPEAK_JS)

            with gr.Tab("Sensor fusion"):
                gr.Markdown("**Play with the decision logic.** Choose what the camera sees, where it is and how far the "
                            "LiDAR says it is. This is the rule set running on the wearable.", elem_classes="note")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=4):
                        f_lab = gr.Dropdown(tx.NAMES, value="stairs", label="Camera sees")
                        f_pos = gr.Slider(0, 100, value=50, step=1, label="Position in view (0 = far left, 100 = far right)")
                        f_dist = gr.Slider(10, 400, value=180, step=5, label="LiDAR distance (cm)")
                        f_speak = gr.Button("Speak it", variant="secondary")
                    with gr.Column(scale=7):
                        f_said = gr.Textbox(label="What the wearer hears", elem_id="spoken", interactive=False)
                        f_panel = gr.HTML()
                for c in (f_lab, f_pos, f_dist):
                    c.change(fusion, [f_lab, f_pos, f_dist], [f_panel, f_said])
                f_speak.click(None, [f_said], None, js=SPEAK_JS)
                demo.load(fusion, [f_lab, f_pos, f_dist], [f_panel, f_said])

            with gr.Tab("Robustness lab"):
                gr.Markdown("**Does it still work at night, in rain or with a tilted head?** During training every photo "
                            "is randomly changed like this, so the model learns the object rather than the picture.",
                            elem_classes="note")
                with gr.Row(equal_height=False):
                    with gr.Column(scale=4):
                        r_in = gr.Image(label="Scene", type="numpy", height=260, sources=["upload", "webcam"])
                        if ex:
                            gr.Examples(ex, [r_in], label="Pick a scene", examples_per_page=12)
                        r_light = gr.Slider(0.15, 1.6, value=1.0, step=0.05, label="Light (night ← → glare)")
                        r_rain = gr.Slider(0, 1, value=0, step=0.05, label="Rain")
                        r_fog = gr.Slider(0, 0.8, value=0, step=0.05, label="Fog")
                        r_blur = gr.Slider(0, 10, value=0, step=1, label="Motion blur")
                        r_tilt = gr.Slider(-25, 25, value=0, step=1, label="Head tilt (degrees)")
                        r_flip = gr.Checkbox(label="Mirror image")
                    with gr.Column(scale=7):
                        with gr.Row():
                            r_a = gr.Image(label="Original", height=330)
                            r_b = gr.Image(label="Changed conditions", height=330)
                        r_msg = gr.Markdown()
                r_inputs = [r_in, r_light, r_rain, r_blur, r_tilt, r_flip, r_fog]
                r_in.change(robust, r_inputs, [r_a, r_b, r_msg])
                for c in (r_light, r_rain, r_blur, r_tilt, r_fog):
                    c.release(robust, r_inputs, [r_a, r_b, r_msg])
                r_flip.change(robust, r_inputs, [r_a, r_b, r_msg])

            with gr.Tab("Live camera"):
                gr.Markdown("Point this computer's webcam at the room. Detection updates several times a second.",
                            elem_classes="note")
                with gr.Row():
                    cam = gr.Image(sources=["webcam"], streaming=True, type="numpy", label="Webcam")
                    cam_out = gr.Image(label="Vantage model", streaming=True)
                cam_said = gr.Textbox(label="What the wearer hears", elem_id="spoken", interactive=False)
                cam.stream(live, [cam], [cam_out, cam_said], stream_every=0.3, time_limit=900)

            with gr.Tab("Results"):
                gr.HTML(results_html(reports, run, stats))

            with gr.Tab("How it works"):
                gr.HTML(HOW)
    return demo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default=str(HERE / "models" / "vantage.pt"))
    ap.add_argument("--baseline", default="yolo11n.pt", help="stock COCO model ('' to disable)")
    ap.add_argument("--imgsz", type=int, default=0, help="0 = the size the model was trained at")
    ap.add_argument("--examples", default=str(HERE / "examples"))
    ap.add_argument("--reports", default=str(HERE / "reports"))
    ap.add_argument("--run", default=str(HERE / "runs" / "vantage"), help="training run folder (learning curve)")
    ap.add_argument("--stats", default=str(HERE / "reports" / "stats.json"))
    ap.add_argument("--claude-model", default="claude-opus-5-5")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to allow phones on the same network")
    ap.add_argument("--share", action="store_true", help="temporary public gradio.live link")
    args = ap.parse_args()

    if not Path(args.weights).exists():
        print(f"Model not found: {args.weights}\nTrain one (vision/train.py) or put vantage.pt in vision/models/.")
        return 1
    imgsz = args.imgsz
    if not imgsz:
        import torch
        ck = torch.load(args.weights, map_location="cpu", weights_only=False)
        imgsz = int((ck.get("train_args") or {}).get("imgsz", 640))
    E = Engine(args.weights, args.baseline, imgsz)
    E.run(np.zeros((320, 320, 3), np.uint8))  # warm-up
    ex_dir = Path(args.examples)
    examples = sorted(ex_dir.glob("*.jpg")) if ex_dir.exists() else []
    demo = build_ui(E, examples, args.claude_model, Path(args.reports), Path(args.run), Path(args.stats))
    import gradio as gr
    theme = gr.themes.Base(primary_hue="neutral", neutral_hue="gray",
                           font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"])
    demo.queue().launch(server_name=args.host, server_port=args.port, share=args.share,
                        css=CSS, theme=theme, head=HEAD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
