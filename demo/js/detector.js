// detector.js — the on-device object detector for the Live room: COCO-80 classes, boxes in
// video pixels, nothing leaves the tablet. MediaPipe's EfficientDet-Lite0 is the primary
// (the same family of small mobile detectors as the Halo's on-sensor network); TF.js
// COCO-SSD is the fallback when the MediaPipe runtime cannot start.
import { COCO_LABELS } from "./halo.js";

const MP_BUNDLE = "vendor/mediapipe/vision_bundle.mjs", MP_WASM = "vendor/mediapipe/wasm", MP_MODEL = "vendor/mediapipe/efficientdet_lite0.tflite";
const TF_SCRIPT = "vendor/tfjs/tf.min.js", TF_COCO = "vendor/tfjs/coco-ssd.min.js", TF_MODEL = "vendor/tfjs/coco-ssd/model.json";

const normalise = (name) => {
  const n = name.toLowerCase().replace(/_/g, " ").trim();
  if (COCO_LABELS.includes(n)) return n;
  const alias = { "motorbike": "motorcycle", "aeroplane": "airplane", "sofa": "couch", "pottedplant": "potted plant", "diningtable": "dining table", "tvmonitor": "tv", "cellphone": "cell phone", "hair dryer": "hair drier" };
  return alias[n] || n;
};

function loadScript(src) { return new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = () => rej(new Error(`could not load ${src}`)); document.head.appendChild(s); }); }

async function loadMediaPipe(onProgress) {
  onProgress("runtime");
  const mod = await import(/* @vite-ignore */ new URL(MP_BUNDLE, location.href).href);
  const { FilesetResolver, ObjectDetector } = mod;
  const vision = await FilesetResolver.forVisionTasks(MP_WASM);
  onProgress("model");
  let det = null, delegate = "GPU";
  try {
    det = await ObjectDetector.createFromOptions(vision, { baseOptions: { modelAssetPath: MP_MODEL, delegate: "GPU" }, runningMode: "VIDEO", scoreThreshold: 0.3, maxResults: 12 });
  } catch (e) {
    delegate = "CPU";
    det = await ObjectDetector.createFromOptions(vision, { baseOptions: { modelAssetPath: MP_MODEL, delegate: "CPU" }, runningMode: "VIDEO", scoreThreshold: 0.3, maxResults: 12 });
  }
  let lastTs = -1;
  return {
    name: `MediaPipe EfficientDet-Lite0 (${delegate})`,
    async detect(video) {
      let ts = Math.round(performance.now()); if (ts <= lastTs) ts = lastTs + 1; lastTs = ts;
      const r = det.detectForVideo(video, ts);
      return (r.detections || []).map(d => {
        const c = d.categories && d.categories[0]; const b = d.boundingBox;
        return c && b ? { label: normalise(c.categoryName || c.displayName || ""), score: c.score, box: [b.originX, b.originY, b.width, b.height] } : null;
      }).filter(Boolean);
    },
    close() { try { det.close(); } catch (_) {} },
  };
}

async function loadTfjs(onProgress) {
  onProgress("runtime");
  if (!window.tf) await loadScript(TF_SCRIPT);
  if (!window.cocoSsd) await loadScript(TF_COCO);
  try { await window.tf.setBackend("webgl"); } catch (_) { await window.tf.setBackend("cpu"); }
  await window.tf.ready();
  onProgress("model");
  const model = await window.cocoSsd.load({ base: "lite_mobilenet_v2", modelUrl: TF_MODEL });
  return {
    name: `TF.js COCO-SSD (${window.tf.getBackend()})`,
    async detect(video) {
      const r = await model.detect(video, 12, 0.3);
      return r.map(d => ({ label: normalise(d.class), score: d.score, box: d.bbox.slice() }));
    },
    close() { try { model.dispose(); } catch (_) {} },
  };
}

/** Load whichever detector is available. onProgress gets a short word for the status line. */
export async function loadDetector({ onProgress = () => {} } = {}) {
  const errors = [];
  for (const [name, loader] of [["mediapipe", loadMediaPipe], ["tfjs", loadTfjs]]) {
    try { const d = await loader(onProgress); onProgress("ready"); return d; }
    catch (e) { errors.push(`${name}: ${e.message || e}`); }
  }
  throw new Error(errors.join("; "));
}
