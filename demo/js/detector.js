// detector.js — the on-device object detector for the Live room: MediaPipe Tasks Vision
// running EfficientDet-Lite0 (COCO-80) in wasm on the tablet. Nothing leaves the device.
// Same family of small mobile detectors as the Halo's on-sensor network, same label set.
// Measured here: ~330 ms to load, 90-160 ms a frame on a software CPU; faster on a real one.
import { FilesetResolver, ObjectDetector } from "../vendor/mediapipe/vision_bundle.js";
import { COCO_LABELS } from "./halo.js";

const WASM_DIR = new URL("../vendor/mediapipe/wasm", import.meta.url).href;
const MODEL = new URL("../vendor/mediapipe/efficientdet_lite0_float16.tflite", import.meta.url).href;
const INPUT_W = 640;   // the model resizes to 320x320 internally; a smaller canvas saves the copy

const ALIAS = { "motorbike": "motorcycle", "aeroplane": "airplane", "sofa": "couch", "pottedplant": "potted plant", "diningtable": "dining table", "tvmonitor": "tv", "cellphone": "cell phone", "hair dryer": "hair drier" };
const normalise = (name) => { const n = String(name || "").toLowerCase().replace(/_/g, " ").trim(); return COCO_LABELS.includes(n) ? n : (ALIAS[n] || n); };

/**
 * Load the detector. onProgress gets a short word for the status line.
 * Returns { name, detect(video) -> [{label, score, box:[x,y,w,h] in video pixels}], close() }.
 */
export async function loadDetector({ onProgress = () => {}, scoreThreshold = 0.35, maxResults = 10, delegate = "CPU" } = {}) {
  onProgress("runtime");
  const fileset = await FilesetResolver.forVisionTasks(WASM_DIR);   // picks the SIMD or no-SIMD wasm pair
  onProgress("model");
  const det = await ObjectDetector.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO", scoreThreshold, maxResults,
  });
  const canvas = document.createElement("canvas"), ctx = canvas.getContext("2d", { willReadFrequently: true });
  let lastTs = -1;
  return {
    name: `EfficientDet-Lite0 (${delegate.toLowerCase()})`,
    async detect(video) {
      const vw = video.videoWidth, vh = video.videoHeight; if (!vw || !vh) return [];
      const s = Math.min(1, INPUT_W / vw);
      const w = Math.round(vw * s), h = Math.round(vh * s);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      ctx.drawImage(video, 0, 0, w, h);
      const ts = Math.max(performance.now(), lastTs + 1); lastTs = ts;   // strictly increasing, in ms
      const { detections } = det.detectForVideo(canvas, ts);           // synchronous, ~100 ms
      return (detections || []).map(d => {
        const c = d.categories && d.categories[0], b = d.boundingBox; if (!c || !b) return null;
        return { label: normalise(c.categoryName || c.displayName), score: c.score, box: [b.originX / s, b.originY / s, b.width / s, b.height / s] };
      }).filter(Boolean);
    },
    close() { try { det.close(); } catch (_) {} },
  };
}
