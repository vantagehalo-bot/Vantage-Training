// halo.js — a line-for-line port of the decision logic in vantage_core.py.
// Nothing here is invented for the demo: spoken wording, thresholds, hysteresis,
// the IoU tracker, the beam-to-box fusion and the priority speech queue all follow
// the firmware. If you change a rule, change it in vantage_core.py first.

export const COCO_LABELS = [
  "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
  "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
  "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
  "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
  "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
  "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
  "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair",
  "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
  "remote","keyboard","cell phone","microwave","oven","toaster","sink",
  "refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush",
];

export const SAFETY_CRITICAL_LABELS = new Set([
  "person","bicycle","car","motorcycle","bus","truck","train","dog","horse",
  "chair","bench","couch","dining table","bed","potted plant","fire hydrant",
  "stop sign","traffic light","suitcase","refrigerator","toilet",
]);

export const SPOKEN_NAMES = {
  "tv": "TV", "cell phone": "phone", "dining table": "table",
  "potted plant": "plant", "hair drier": "hair dryer", "sports ball": "ball",
  "banknote": "money",   // the escape room's custom class
};

// Config defaults, same values as the dataclass in vantage_core.py.
export function defaultConfig() {
  return {
    width: 640, height: 480,
    camHfovDeg: 66.3, camVfovDeg: 52.1,
    lidarMinStrength: 100, lidarMaxRangeCm: 1200, lidarMedianWindow: 5, lidarStaleS: 0.5,
    lidarOffsetXCm: 0, lidarOffsetYCm: 0, lidarBeamDeg: 3.6, lidarRoiMinFrac: 0.06,
    criticalCm: 50, warningCm: 100, hysteresisCm: 8, ttcWarningS: 1.5,
    visionCloseFrac: 0.55, minTrackHits: 2,
    speechRate: 175, beep: true, criticalRepeatS: 2.5, warningRepeatS: 6.0,
    describe: false, describeCooldownS: 12.0,
    scoreThreshold: 0.55, maxDetections: 10,
  };
}

export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

export function spokenLabel(label) { return SPOKEN_NAMES[label] || label; }

export function spokenDistance(cm) {
  if (cm == null) return "";
  if (cm < 97.5) return `${Math.round(cm / 5) * 5} centimeters`;
  const m = Math.round(cm / 10) / 10;
  if (Math.abs(m - Math.round(m)) < 1e-6) {
    const r = Math.round(m);
    return `${r} meter${r !== 1 ? "s" : ""}`;
  }
  return `${m.toFixed(1)} meters`;
}

export function directionOf(cx, width) {
  const rel = cx / Math.max(width, 1);
  if (rel < 0.33) return "on your left";
  if (rel > 0.67) return "on your right";
  return "ahead";
}

export function iou(a, b) {
  const [ax, ay, aw, ah] = a, [bx, by, bw, bh] = b;
  const ix = Math.max(0, Math.min(ax + aw, bx + bw) - Math.max(ax, bx));
  const iy = Math.max(0, Math.min(ay + ah, by + bh) - Math.max(ay, by));
  const inter = ix * iy;
  const union = aw * ah + bw * bh - inter;
  return union > 0 ? inter / union : 0;
}

// ---------------------------------------------------------------------------- tracker

export class Track {
  constructor(id, label, score, box, now) {
    this.trackId = id; this.label = label; this.score = score; this.box = box.slice();
    this.hits = 1; this.misses = 0; this.firstSeen = now; this.lastSeen = now;
  }
  get center() { const [x, y, w, h] = this.box; return [x + w / 2, y + h / 2]; }
}

export class ObjectTracker {
  constructor(minHits = 2, maxMisses = 6, smoothing = 0.5) {
    this.tracks = new Map(); this.minHits = minHits; this.maxMisses = maxMisses;
    this.alpha = smoothing; this._nextId = 1;
  }
  update(detections, now) {
    const unmatched = new Set(this.tracks.keys());
    const pairs = [];
    detections.forEach((det, di) => {
      for (const [tid, trk] of this.tracks) {
        if (trk.label !== det.label) continue;
        const s = iou(det.box, trk.box);
        if (s > 0.2) pairs.push([s, di, tid]);
      }
    });
    pairs.sort((p, q) => q[0] - p[0]);
    const usedDet = new Set(), usedTrk = new Set();
    for (const [, di, tid] of pairs) {
      if (usedDet.has(di) || usedTrk.has(tid)) continue;
      usedDet.add(di); usedTrk.add(tid);
      const det = detections[di], trk = this.tracks.get(tid), a = this.alpha;
      trk.box = det.box.map((n, i) => a * n + (1 - a) * trk.box[i]);
      trk.score = a * det.score + (1 - a) * trk.score;
      trk.hits += 1; trk.misses = 0; trk.lastSeen = now;
      unmatched.delete(tid);
    }
    detections.forEach((det, di) => {
      if (usedDet.has(di)) return;
      const tid = this._nextId++;
      this.tracks.set(tid, new Track(tid, det.label, det.score, det.box, now));
    });
    for (const tid of unmatched) {
      const trk = this.tracks.get(tid);
      trk.misses += 1;
      if (trk.misses > this.maxMisses) this.tracks.delete(tid);
    }
    return this.confirmed();
  }
  confirmed() { return [...this.tracks.values()].filter(t => t.hits >= this.minHits); }
}

// ---------------------------------------------------------------------------- LiDAR filter
// The TFmini thread in the firmware: drop weak / saturated returns, median filter,
// least-squares closing speed over ~0.5 s, time-to-contact.

export class LidarFilter {
  constructor(cfg) { this.cfg = cfg; this.window = []; this.history = []; this.last = null; }
  push(rawCm, strength, now) {
    const c = this.cfg;
    let valid = rawCm != null && strength >= c.lidarMinStrength && strength !== 65535
      && rawCm > 0 && rawCm <= c.lidarMaxRangeCm;
    let filtered = null, velocity = null, ttc = null;
    if (valid) {
      this.window.push(rawCm);
      if (this.window.length > c.lidarMedianWindow) this.window.shift();
      const s = [...this.window].sort((a, b) => a - b);
      filtered = s[Math.floor(s.length / 2)];
      this.history.push([now, filtered]);
      while (this.history.length && now - this.history[0][0] > 0.5) this.history.shift();
      if (this.history.length >= 4) {
        const n = this.history.length;
        let sx = 0, sy = 0, sxx = 0, sxy = 0;
        for (const [t, d] of this.history) { sx += t; sy += d; sxx += t * t; sxy += t * d; }
        const den = n * sxx - sx * sx;
        if (Math.abs(den) > 1e-9) velocity = (n * sxy - sx * sy) / den;  // cm/s, negative = closing
        if (velocity != null && velocity < -5) ttc = filtered / -velocity;
      }
    } else {
      this.window.length = 0; this.history.length = 0;
    }
    this.last = { distanceCm: filtered, rawCm, strength, valid, t: now, velocity, ttcS: ttc };
    return this.last;
  }
  sample(now) {
    if (!this.last) return null;
    if (now - this.last.t > this.cfg.lidarStaleS) return { ...this.last, valid: false, stale: true };
    return this.last;
  }
}

// ---------------------------------------------------------------------------- fusion

export const Level = { UNKNOWN: -1, CLEAR: 0, CAUTION: 1, CRITICAL: 2 };
export const levelName = l => ({ "-1": "UNKNOWN", 0: "CLEAR", 1: "CAUTION", 2: "CRITICAL" })[l];

export class HazardAssessor {
  constructor(cfg) {
    this.cfg = cfg; this.W = cfg.width; this.H = cfg.height;
    this.fx = (this.W / 2) / Math.tan((cfg.camHfovDeg / 2) * Math.PI / 180);
    this.fy = (this.H / 2) / Math.tan((cfg.camVfovDeg / 2) * Math.PI / 180);
    this.level = Level.CLEAR;
  }
  aimBox(distanceCm) {
    const c = this.cfg;
    const d = distanceCm && distanceCm > 1 ? distanceCm : 200;
    const cx = this.W / 2 + this.fx * c.lidarOffsetXCm / d;
    const cy = this.H / 2 + this.fy * c.lidarOffsetYCm / d;
    let half = this.fx * Math.tan((c.lidarBeamDeg / 2) * Math.PI / 180);
    half = Math.max(half, c.lidarRoiMinFrac * this.W / 2);
    const x0 = clamp(cx - half, 0, this.W - 1), y0 = clamp(cy - half, 0, this.H - 1);
    const x1 = clamp(cx + half, 0, this.W - 1), y1 = clamp(cy + half, 0, this.H - 1);
    return [x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0)];
  }
  static overlapFrac(aim, box) {
    const [ax, ay, aw, ah] = aim, [bx, by, bw, bh] = box;
    const ix = Math.max(0, Math.min(ax + aw, bx + bw) - Math.max(ax, bx));
    const iy = Math.max(0, Math.min(ay + ah, by + bh) - Math.max(ay, by));
    return (ix * iy) / (aw * ah);
  }
  _classify(d) {
    const { criticalCm: c, warningCm: w, hysteresisCm: hy } = this.cfg;
    if (this.level === Level.CRITICAL && d < c + hy) return Level.CRITICAL;
    if (d < c) return Level.CRITICAL;
    if (this.level >= Level.CAUTION && d < w + hy) return Level.CAUTION;
    if (d < w) return Level.CAUTION;
    return Level.CLEAR;
  }
  assess(lidar, tracks) {
    const dist = lidar && lidar.valid ? lidar.distanceCm : null;
    const aim = this.aimBox(dist);
    let target = null, best = 0;
    for (const trk of tracks) {
      const ov = HazardAssessor.overlapFrac(aim, trk.box);
      if (ov <= 0.25) continue;
      const rank = ov * trk.score * (SAFETY_CRITICAL_LABELS.has(trk.label) ? 1.2 : 1.0);
      if (rank > best) { best = rank; target = trk; }
    }
    if (dist != null) {
      let level = this._classify(dist);
      const ttc = lidar.ttcS;
      if (level === Level.CLEAR && ttc != null && ttc < this.cfg.ttcWarningS && dist < this.cfg.warningCm * 2) {
        level = Level.CAUTION;
      }
      this.level = level;
      return { level, distanceCm: dist, target, source: target ? "lidar+camera" : "lidar", aimBox: aim, ttcS: ttc, message: "" };
    }
    const close = tracks.filter(t => t.box[3] / this.H >= this.cfg.visionCloseFrac);
    if (close.length) {
      const near = close.reduce((a, b) => (a.box[2] * a.box[3] >= b.box[2] * b.box[3] ? a : b));
      this.level = near.box[3] / this.H > 0.8 ? Level.CRITICAL : Level.CAUTION;
      return { level: this.level, distanceCm: null, target: near, source: "vision", aimBox: aim, ttcS: null, message: "" };
    }
    this.level = (!lidar || !lidar.valid) ? Level.UNKNOWN : Level.CLEAR;
    return { level: this.level, distanceCm: null, target: null, source: "none", aimBox: aim, ttcS: null, message: "" };
  }
}

// ---------------------------------------------------------------------------- speech queue

export const Priority = { CRITICAL: 0, WARNING: 1, INFO: 2 };
export const priorityName = p => ["CRITICAL", "WARNING", "INFO"][p];

/**
 * Priority speech queue, mirroring SpeechEngine in the firmware:
 *  - a CRITICAL message interrupts anything less important that is playing,
 *  - queued messages less important than a CRITICAL one are drained,
 *  - a message older than its max age is dropped instead of spoken.
 * `backend` must provide speak(text, onEnd) -> cancel fn, beep(onEnd), isSpeaking().
 * Emits events through `onEvent({type, ...})` for the HUD and the pipeline view.
 */
export class SpeechQueue {
  constructor(backend, onEvent = () => {}) {
    this.backend = backend; this.onEvent = onEvent;
    this.q = []; this._seq = 0; this.muted = false;
    this.current = null; this.lastSpoken = ""; this.lastPriority = null; this.lastSpokenAt = 0;
    this._cancelCurrent = null;
  }
  now() { return performance.now() / 1000; }
  say(text, priority = Priority.INFO, beep = false, maxAgeS = 2.0) {
    if (this.muted) return;
    const utt = { priority, seq: ++this._seq, text, created: this.now(), beep, maxAgeS };
    if (this.current && priority < this.current.priority) {
      this.onEvent({ type: "preempt", killed: this.current, by: utt });
      this._kill();
    }
    if (priority === Priority.CRITICAL) {
      const keep = this.q.filter(u => u.priority <= Priority.CRITICAL);
      for (const u of this.q) if (!keep.includes(u)) this.onEvent({ type: "drained", utt: u });
      this.q = keep;
    }
    this.q.push(utt);
    this.q.sort((a, b) => a.priority - b.priority || a.seq - b.seq);
    this.onEvent({ type: "queued", utt, queue: this.q.slice() });
    this._pump();
  }
  _kill() {
    if (this._cancelCurrent) { const c = this._cancelCurrent; this._cancelCurrent = null; c(); }
    this.current = null;
  }
  toggleMute() {
    this.muted = !this.muted;
    if (this.muted) { this._kill(); this.q.length = 0; }
    return this.muted;
  }
  get busy() { return !!this.current || this.q.length > 0; }
  _pump() {
    if (this.current || !this.q.length) return;
    const utt = this.q.shift();
    if (this.now() - utt.created > utt.maxAgeS) {
      this.onEvent({ type: "dropped", utt, reason: "stale" });
      return this._pump();
    }
    this.current = utt;
    this.onEvent({ type: "speaking", utt, queue: this.q.slice() });
    const speakIt = () => {
      if (this.current !== utt) return;
      this._cancelCurrent = this.backend.speak(utt.text, () => {
        if (this.current === utt) {
          this.lastSpoken = utt.text; this.lastPriority = utt.priority; this.lastSpokenAt = this.now();
          this.current = null; this._cancelCurrent = null;
          this.onEvent({ type: "spoken", utt });
          this._pump();
        }
      });
    };
    if (utt.beep) this._cancelCurrent = this.backend.beep(speakIt); else speakIt();
  }
}

// ---------------------------------------------------------------------------- announcer

export class Announcer {
  constructor(cfg, speech, onEvent = () => {}) {
    this.cfg = cfg; this.speech = speech; this.onEvent = onEvent;
    this._lastLevel = Level.CLEAR; this._lastLabel = null; this._lastSaid = 0;
    this._described = new Map(); this.banner = "";
  }
  phrase(hz) {
    const name = hz.target ? spokenLabel(hz.target.label) : "obstacle";
    const dist = spokenDistance(hz.distanceCm);
    let text;
    if (hz.level === Level.CRITICAL) {
      text = `${name} too close`;
      if (dist) text += `, ${dist}`;
      else if (hz.source === "vision") text = `${name} very close`;
    } else {
      text = `${name} ahead`;
      if (dist) text += `, ${dist}`;
      if (hz.ttcS != null && hz.ttcS < this.cfg.ttcWarningS) text += ", approaching fast";
    }
    return text[0].toUpperCase() + text.slice(1);
  }
  update(hz, tracks, now) {
    const label = hz.target ? hz.target.label : null;
    if (hz.level >= Level.CAUTION) hz.message = this.phrase(hz);
    this.banner = hz.message;
    if (hz.level === Level.CRITICAL) {
      const changed = this._lastLevel !== Level.CRITICAL || label !== this._lastLabel;
      if (changed || now - this._lastSaid >= this.cfg.criticalRepeatS) {
        this.speech.say(hz.message, Priority.CRITICAL, changed && this.cfg.beep, 1.0);
        this._lastSaid = now;
        if (changed) this.onEvent({ type: "alert", message: hz.message });
      }
    } else if (hz.level === Level.CAUTION) {
      const escalated = this._lastLevel < Level.CAUTION || label !== this._lastLabel;
      if (escalated || now - this._lastSaid >= this.cfg.warningRepeatS) {
        this.speech.say(hz.message, Priority.WARNING, false, 1.5);
        this._lastSaid = now;
      }
    } else if (this._lastLevel === Level.CRITICAL && hz.level === Level.CLEAR) {
      this.speech.say("Clear", Priority.INFO, false, 1.0);
    }
    if (this.cfg.describe && hz.level < Level.CAUTION) {
      for (const trk of tracks) {
        if (now - (this._described.get(trk.label) ?? -1e9) < this.cfg.describeCooldownS) continue;
        if (trk.hits < Math.max(this.cfg.minTrackHits, 4)) continue;
        this._described.set(trk.label, now);
        const [cx] = trk.center;
        this.speech.say(`${spokenLabel(trk.label)} ${directionOf(cx, this.cfg.width)}`, Priority.INFO, false, 2.5);
        break;
      }
    }
    this._lastLevel = hz.level; this._lastLabel = label;
  }
  // The `s` key on the device.
  describeScene(tracks, hz) {
    if (!tracks.length) { this.speech.say("Nothing detected", Priority.INFO); return; }
    const parts = [...tracks].sort((a, b) => b.box[2] * b.box[3] - a.box[2] * a.box[3]).slice(0, 4)
      .map(t => `${spokenLabel(t.label)} ${directionOf(t.center[0], this.cfg.width)}`);
    let txt = parts.join(", ");
    if (hz.distanceCm != null) txt += `. Distance ahead ${spokenDistance(hz.distanceCm)}`;
    this.speech.say(txt[0].toUpperCase() + txt.slice(1), Priority.INFO, false, 4.0);
  }
}

/** Wires tracker → fusion → announcer, like the main loop in vantage_core.py. */
export class HaloPipeline {
  constructor(cfg, speech, onEvent = () => {}) {
    this.cfg = cfg;
    this.tracker = new ObjectTracker(cfg.minTrackHits);
    this.lidar = new LidarFilter(cfg);
    this.assessor = new HazardAssessor(cfg);
    this.announcer = new Announcer(cfg, speech, onEvent);
    this.speech = speech;
    this.tracks = []; this.hazard = null; this.lidarSample = null;
    this.fps = 0; this._fpsT = 0;
  }
  reset() {
    this.tracker = new ObjectTracker(this.cfg.minTrackHits);
    this.lidar = new LidarFilter(this.cfg);
    this.assessor.level = Level.CLEAR;
    this.announcer._lastLevel = Level.CLEAR; this.announcer._lastLabel = null; this.announcer._described.clear();
    this.tracks = []; this.hazard = null; this.lidarSample = null;
  }
  pushLidar(rawCm, strength, now) { return this.lidar.push(rawCm, strength, now); }
  step(detections, now, threshold = this.cfg.scoreThreshold) {
    if (this._fpsT) this.fps = 0.9 * this.fps + 0.1 / Math.max(1e-3, now - this._fpsT);
    this._fpsT = now;
    const dets = detections ? detections.filter(d => d.score >= threshold).slice(0, this.cfg.maxDetections) : [];
    this.tracks = this.tracker.update(dets, now);
    this.lidarSample = this.lidar.sample(now);
    this.hazard = this.assessor.assess(this.lidarSample, this.tracks);
    this.announcer.update(this.hazard, this.tracks, now);
    return this.hazard;
  }
  speakScene() { if (this.hazard) this.announcer.describeScene(this.tracks, this.hazard); }
}
