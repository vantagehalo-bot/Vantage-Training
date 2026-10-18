// range.js — distance from a detection box when there is no laser: the object's known
// height divided by how tall it looks. Honest to about 15 % between 0.5 and 4 m for
// upright things, worse for things seen from odd angles. The Halo uses its TFmini for this.

// Typical real heights in metres of a whole object as the COCO detector boxes it.
const HEIGHT_M = {
  person: 1.65, bicycle: 1.0, car: 1.5, motorcycle: 1.1, bus: 3.0, train: 3.8, truck: 2.6, boat: 1.2,
  "traffic light": 1.0, "fire hydrant": 0.8, "stop sign": 0.75, "parking meter": 1.3, bench: 0.9,
  bird: 0.2, cat: 0.3, dog: 0.5, horse: 1.6, sheep: 0.9, cow: 1.4, backpack: 0.45, umbrella: 0.9,
  handbag: 0.3, suitcase: 0.6, bottle: 0.25, "wine glass": 0.18, cup: 0.1, bowl: 0.08,
  chair: 0.9, couch: 0.85, "potted plant": 0.6, bed: 0.6, "dining table": 0.75, toilet: 0.75,
  tv: 0.6, laptop: 0.25, mouse: 0.04, remote: 0.17, keyboard: 0.03, "cell phone": 0.15,
  microwave: 0.3, oven: 0.9, toaster: 0.2, sink: 0.3, refrigerator: 1.7, book: 0.24, clock: 0.3,
  vase: 0.3, scissors: 0.2, "teddy bear": 0.35, "hair drier": 0.2, toothbrush: 0.19,
};

/** Focal length in pixels for a frame of height H and a vertical field of view. */
export function focalPx(frameH, vfovDeg) { return (frameH / 2) / Math.tan((vfovDeg / 2) * Math.PI / 180); }

/** Estimated range in cm for a box, or null when the class has no useful height. */
export function rangeCm(label, box, frameH, vfovDeg, clippedTop = false, clippedBottom = false) {
  const H = HEIGHT_M[label]; if (!H) return null;
  const h = box[3]; if (h < 8) return null;
  // a box cut by the frame edge is taller than we see; be conservative
  const seen = clippedTop || clippedBottom ? h * 1.25 : h;
  const d = focalPx(frameH, vfovDeg) * H / seen * 100;
  return Math.max(15, Math.min(1200, d));
}
