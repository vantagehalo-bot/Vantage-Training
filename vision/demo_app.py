#!/usr/bin/env python3
"""
Step 5 - THE EXPO DEMO.

A web page you open on a laptop: show a photo (or point the webcam), and it shows
side by side what the stock AI-camera model sees and what the Vantage model sees, plus
the exact sentence the wearer would hear - and speaks it out loud.

  pip install ultralytics gradio
  python vision/demo_app.py                       # then open http://localhost:7860
  python vision/demo_app.py --share               # public link for a phone / second screen

Optional "Ask Claude" button: a detailed scene description from Claude (needs internet and
ANTHROPIC_API_KEY). The on-device model is what keeps the wearer safe in real time; the
large model is the optional, slower "tell me more about this place" feature.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import taxonomy as tx  # noqa: E402
from describe import Det, describe  # noqa: E402
from draw import draw_detections  # noqa: E402

SPEAK_JS = """
(text) => {
  if (!text || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  window.speechSynthesis.speak(u);
}
"""

CSS = """
#title {text-align:center}
#title h1 {font-size: 2.1em; margin-bottom: 0}
#spoken textarea {font-size: 1.35em !important; font-weight: 600}
.legend span {display:inline-block; padding:2px 10px; margin:2px; border-radius:12px; color:#111;
              font-weight:600; font-size:0.9em}
"""

LEGEND = """
<div class="legend" style="text-align:center">
<span style="background:#e62828">Drop-off (stairs, manhole)</span>
<span style="background:#ff8c00">Moving (car, bike, bus)</span>
<span style="background:#e6c800">Obstacle (pole, chair, bin ...)</span>
<span style="background:#2896e6">Landmark (sign, crossing, TV)</span>
</div>
"""


class Engine:
    def __init__(self, weights: str, baseline: str, imgsz: int):
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.base = YOLO(baseline) if baseline else None
        self.imgsz = imgsz

    def _run(self, model, rgb, conf, mapping=None, imgsz=None):
        r = model.predict(rgb[:, :, ::-1], conf=conf, imgsz=imgsz or self.imgsz, verbose=False)[0]
        dets = []
        if r.boxes is not None:
            for b, c, k in zip(r.boxes.xyxyn.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
                name = r.names[int(k)]
                if mapping is not None:
                    name = mapping.get(name)
                    if name is None:
                        continue
                dets.append((name, float(c), tuple(b)))
        return dets

    def analyse(self, rgb, conf=0.35, compare=True, landmarks=True):
        if rgb is None:
            return None, None, "", [], ""
        t0 = time.perf_counter()
        ours = self._run(self.model, rgb, conf)
        ms = (time.perf_counter() - t0) * 1000
        bgr = rgb[:, :, ::-1]
        ours_img = draw_detections(bgr, ours, title="Vantage model")[:, :, ::-1]
        base_img = None
        if compare and self.base is not None:
            base = self._run(self.base, rgb, conf, mapping=tx.COCO_MAP, imgsz=640)  # its native size
            base_img = draw_detections(bgr, base, title="Stock AI camera model")[:, :, ::-1]
        sentence = describe([Det(*d) for d in ours], include_landmarks=landmarks)
        table = [[d[0], tx.TIER_NAMES[tx.TIER[d[0]]], f"{d[1]:.0%}",
                  describe([Det(*d)]).split(".")[0].split(" ", 1)[-1]]
                 for d in sorted(ours, key=lambda d: (tx.TIER[d[0]], -d[1]))]
        info = f"{len(ours)} objects in {ms:.0f} ms on this computer's CPU"
        return ours_img, base_img, sentence, table, info


def ask_claude(rgb, detections_text: str, model: str) -> str:
    if rgb is None:
        return "Take or upload a picture first."
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "Set ANTHROPIC_API_KEY to enable this optional feature."
    try:
        import anthropic
    except ImportError:
        return "pip install anthropic"
    small = rgb
    if max(rgb.shape[:2]) > 1024:
        s = 1024 / max(rgb.shape[:2])
        small = cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", small[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 85])
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=300,
        system=("You are the voice of Vantage, a wearable that guides a blind person. Describe the "
                "scene in at most 3 short spoken sentences: first anything that could make them trip, "
                "fall or collide, with direction (left / ahead / right) and rough distance, then one "
                "sentence of useful context (what kind of place this is, readable signs). No markdown."),
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(jpg.tobytes()).decode()}},
            {"type": "text", "text": f"The on-device detector reported: {detections_text or 'nothing'}. "
                                     "Describe the scene for the wearer."},
        ]}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def build_ui(engine: Engine, examples, claude_model: str):
    import gradio as gr

    with gr.Blocks(title="Vantage Vision Demo") as demo:
        gr.Markdown("# Vantage Vision\nAn AI model trained to see what a blind pedestrian needs to know.",
                    elem_id="title")
        gr.HTML(LEGEND)
        with gr.Tab("Photo"):
            with gr.Row():
                with gr.Column(scale=1):
                    inp = gr.Image(label="Show Vantage a scene", sources=["upload", "webcam", "clipboard"],
                                   type="numpy", height=360)
                    conf = gr.Slider(0.1, 0.9, value=0.35, step=0.05, label="Confidence threshold")
                    with gr.Row():
                        compare = gr.Checkbox(value=True, label="Compare with stock model")
                        landmarks = gr.Checkbox(value=True, label="Mention landmarks")
                    btn = gr.Button("Analyse", variant="primary")
                    if examples:
                        gr.Examples(examples=[[str(e)] for e in examples], inputs=[inp],
                                    label="Example scenes (from the unseen test set)")
                with gr.Column(scale=2):
                    spoken = gr.Textbox(label="What the wearer hears", elem_id="spoken", lines=2)
                    with gr.Row():
                        speak = gr.Button("🔊 Speak it")
                        info = gr.Markdown()
                    with gr.Row():
                        out_base = gr.Image(label="Stock AI camera model (COCO)", height=380)
                        out_ours = gr.Image(label="Vantage model (our training)", height=380)
                    table = gr.Dataframe(headers=["object", "type", "confidence", "where"],
                                         label="Detections", wrap=True)
                    with gr.Accordion("Ask Claude for a detailed description (optional, needs internet)",
                                      open=False):
                        ask = gr.Button("Ask Claude")
                        claude_out = gr.Textbox(label="Claude says", lines=3)

            def run(img, c, cmp, lm):
                return engine.analyse(img, c, cmp, lm)

            outs = [out_ours, out_base, spoken, table, info]
            for trig in (btn.click, inp.change):
                trig(run, [inp, conf, compare, landmarks], outs).then(None, [spoken], None, js=SPEAK_JS)
            speak.click(None, [spoken], None, js=SPEAK_JS)
            ask.click(lambda img, s: ask_claude(img, s, claude_model), [inp, spoken], [claude_out]) \
               .then(None, [claude_out], None, js=SPEAK_JS)

        with gr.Tab("Live webcam"):
            gr.Markdown("Point the laptop camera at the room. Detections update a few times per second.")
            with gr.Row():
                cam = gr.Image(sources=["webcam"], streaming=True, type="numpy", label="Camera")
                live = gr.Image(label="Vantage model", streaming=True)
            live_text = gr.Textbox(label="What the wearer hears", elem_id="spoken")

            def live_fn(img):
                o, _, s, _, _ = engine.analyse(img, 0.4, compare=False, landmarks=False)
                return o, s

            cam.stream(live_fn, [cam], [live, live_text], stream_every=0.25, time_limit=600)

        with gr.Tab("How it works"):
            gr.Markdown(HOW_IT_WORKS)
    return demo


HOW_IT_WORKS = """
### From photos to a talking wearable - in 5 steps

1. **Collect** - 24,000 street photos taken from a pedestrian's eye level (ROD dataset) are
   merged with indoor photos from COCO, then all labels are mapped to **29 Vantage classes**
   sorted by danger: drop-offs, moving vehicles, obstacles and landmarks.
2. **Train** - we start from YOLO11n, a small fast detector that already knows basic shapes,
   and fine-tune it on our data. It sees each photo dozens of times, with random lighting,
   zoom and mirror changes, so it copes with real-world conditions.
3. **Test** - we measure it on photos it has **never seen**. The stock camera model cannot
   detect stairs, manholes, poles or cones at all; ours can.
4. **Shrink** - the model is converted to 8-bit integers (about 4x smaller) and compiled for the
   Sony IMX500 chip inside the Raspberry Pi AI Camera. **The AI runs inside the camera**, using
   almost no battery or CPU on the Pi.
5. **Speak** - detections are fused with the LiDAR distance and turned into one short sentence
   on the bone-conduction headset: *"Stairs ahead, close."* The vibration motor buzzes faster
   as obstacles get nearer.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", default=str(HERE / "models" / "vantage.pt"))
    ap.add_argument("--baseline", default="yolo11n.pt", help="stock COCO model ('' to disable)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--examples", default=str(HERE / "examples"))
    ap.add_argument("--claude-model", default="claude-opus-5-5")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to allow other devices on the network")
    ap.add_argument("--share", action="store_true", help="create a temporary public gradio.live link")
    args = ap.parse_args()

    if not Path(args.weights).exists():
        print(f"Model not found: {args.weights}\nTrain one first (vision/train.py) or download vantage.pt "
              "from the Colab notebook into vision/models/.")
        return 1
    engine = Engine(args.weights, args.baseline, args.imgsz)
    engine.analyse(np.zeros((320, 320, 3), np.uint8))  # warm-up
    ex_dir = Path(args.examples)
    examples = sorted(p for p in ex_dir.glob("*.jpg")) if ex_dir.exists() else []
    demo = build_ui(engine, examples, args.claude_model)
    import gradio as gr
    demo.queue().launch(server_name=args.host, server_port=args.port, share=args.share,
                        css=CSS, theme=gr.themes.Soft())
    return 0


if __name__ == "__main__":
    sys.exit(main())
