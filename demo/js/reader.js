// reader.js — vantage_reader.py on the tablet camera, sharing the Live room's stream.
// Auto mode waits for text in view and a still camera (0.7 s), plays the click, grabs a
// burst of frames and keeps the sharpest, OCRs it on the device, then reads sentence by
// sentence. When it cannot read, it says why, in the reader's own words.
import * as audio from "./audio.js";
import { prepareForOcr, OCR_PARAMS, RECOGNIZE_OUTPUT } from "./ocr-prep.js";
import { loadWords, cleanLine, isKnown } from "./wordcheck.js";
import { isAr, tr } from "./lang.js";
import { AR } from "./arabic.js";

const STEADY_S = 0.7, MIN_CONF = 60, READ_COOLDOWN_S = 3.5, MIN_XHEIGHT_PX = 8, TORCH_BELOW = 70, PAGE_GONE_S = 1.5;
export const COACH = {
  dark: "It's too dark to read. Turn on a light or move closer to a window.",
  glare: "There's glare on the text. Tilt it slightly away from the light.",
  close: "The text is too close. Move it a little farther away.",
  blur: "The picture is blurry. Hold still, or move the text a little farther away.",
  small: "The text is too small. Pinch to zoom in, or move a little closer.",
  none: "No text in frame.",
};
const COACH_AR = {
  dark: "الإضاءة خافتة جدًا للقراءة. يُرجى تشغيل ضوء أو الاقتراب من نافذة.",
  glare: "هناك وهج على النص. يُرجى إمالته قليلًا بعيدًا عن الضوء.",
  close: "النص قريب جدًا. يُرجى إبعاده قليلًا.",
  blur: "الصورة غير واضحة. يُرجى تثبيت اليد، أو إبعاد النص قليلًا.",
  small: "النص صغير جدًا. يُرجى التكبير بإصبعين، أو الاقتراب قليلًا.",
  none: "لا يوجد نص في الصورة.",
};
const coachText = (k) => (isAr() ? COACH_AR : COACH)[k];

export class Reader {
  constructor({ camera, overlay, out, status, meters, zoomLabel, buttons, onBusy = () => {}, ai = null, isMuted = () => false, onTorch = () => {} }) {
    Object.assign(this, { camera, overlay, out, status, meters, zoomLabel, buttons, onBusy, ai, isMuted, onTorch });
    this.octx = overlay.getContext("2d");
    this.work = document.createElement("canvas"); this.wctx = this.work.getContext("2d", { willReadFrequently: true });
    this.st = { running: false, worker: null, workerReady: null, prevGray: null, steadySince: 0, lastRead: -1e9, busy: false, auto: true,
      sentences: [], cur: -1, paused: false, speaking: false, cancelSpeak: null, readLines: new Set(), metrics: {}, lastBoxes: null, timer: 0,
      textRect: null, goneSince: 0, torchAuto: false, dimSince: 0 };
    this._bind();
  }
  setStatus(t) { this.status.textContent = t; }
  say(text, onEnd) {
    if (this.st.cancelSpeak) this.st.cancelSpeak();
    if (this.isMuted()) { this.st.cancelSpeak = null; return; }   // muted: the text stays on screen, nothing is spoken
    this.st.cancelSpeak = audio.speak(text, () => { this.st.cancelSpeak = null; onEnd && onEnd(); });
  }

  ensureWorker() {
    const st = this.st; if (st.workerReady) return st.workerReady;
    this.setStatus("LOADING READER");
    st.workerReady = (async () => {
      if (!window.Tesseract) await new Promise((res, rej) => { const s = document.createElement("script"); s.src = "vendor/tesseract/tesseract.min.js"; s.onload = res; s.onerror = () => rej(new Error("tesseract.min.js did not load")); document.head.appendChild(s); });
      const base = new URL("vendor/tesseract/", location.href).href;
      st.worker = await Tesseract.createWorker("eng", 1, { workerPath: base + "worker.min.js", corePath: base, langPath: base, gzip: false, logger: () => {} });
      await st.worker.setParameters(OCR_PARAMS);
      return st.worker;
    })().catch(e => { st.workerReady = null; st.worker = null; throw e; });
    return st.workerReady;
  }

  // ---- live analysis at ~8 Hz on a small grey frame
  analyse() {
    const st = this.st; if (!st.running) return;
    if (this.camera.running) {
      const c = this.camera.grab(240, this.work); const W = c.width, H = c.height;
      const d = this.wctx.getImageData(0, 0, W, H).data, g = new Float32Array(W * H);
      let sum = 0, sat = 0;
      for (let i = 0, j = 0; i < d.length; i += 4, j++) { const v = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; g[j] = v; sum += v; if (v > 245) sat++; }
      const light = sum / (W * H);
      let lsum = 0, lsq = 0, n = 0;
      for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) { const i = y * W + x, L = 4 * g[i] - g[i - 1] - g[i + 1] - g[i - W] - g[i + W]; lsum += L; lsq += L * L; n++; }
      const sharp = Math.sqrt(Math.max(0, lsq / n - (lsum / n) ** 2));
      let textRows = 0; const rows = [];
      for (let y = 2; y < H - 2; y += 2) { let tr = 0, x0 = W, x1 = 0; for (let x = 1; x < W - 1; x++) if (Math.abs(g[y * W + x] - g[y * W + x + 1]) > 35) { tr++; x0 = Math.min(x0, x); x1 = Math.max(x1, x); } if (tr > W * 0.08 && tr < W * 0.6) { textRows++; rows.push([y, x0, x1]); } }
      const text = textRows / (H / 2);
      let motion = 1;
      if (st.prevGray && st.prevGray.length === g.length) { let md = 0; for (let i = 0; i < g.length; i += 3) md += Math.abs(g[i] - st.prevGray[i]); motion = md / (g.length / 3); }
      st.prevGray = g;
      const now = performance.now() / 1000;
      if (!(motion < 6)) st.steadySince = now;
      const steadyFrac = Math.min(1, (now - st.steadySince) / STEADY_S);
      st.metrics = { sharp, light, steady: steadyFrac, text, sat: sat / (W * H), motion };
      // where the text sits, as fractions of the frame: the burst picks its sharpest frame there
      if (rows.length >= 3) { let x0 = W, x1 = 0; for (const r of rows) { x0 = Math.min(x0, r[1]); x1 = Math.max(x1, r[2]); } st.textRect = { x: x0 / W, y: rows[0][0] / H, w: (x1 - x0) / W, h: (rows[rows.length - 1][0] - rows[0][0] + 2) / H }; }
      // a page taken out of view for a moment means the next one is new, even if it says the same
      if (text < 0.04) { if (!st.goneSince) st.goneSince = now; else if (now - st.goneSince > PAGE_GONE_S) { if (st.readLines.size) st.readLines.clear(); st.modelArmed = true; st.pageDone = false; } } else st.goneSince = 0;
      // noise and blur, not shading, are what break OCR: light the page when the camera offers a torch
      if (this.camera.hasTorch && st.auto) {
        if (light < TORCH_BELOW && !st.torchAuto) { if (!st.dimSince) st.dimSince = now; else if (now - st.dimSince > 1.0) this.torch(true); }
        else st.dimSince = 0;
      }
      this.meter(this.meters.sharp, Math.min(1, sharp / 18), sharp > 9 ? "" : "var(--amber)");
      this.meter(this.meters.light, Math.min(1, light / 160), light > 60 && light < 235 ? "" : "var(--amber)");
      this.meter(this.meters.steady, steadyFrac, steadyFrac >= 1 ? "" : "var(--muted)");
      this.drawLive(rows, W, H);
      if (st.auto && !st.busy && !st.speaking && steadyFrac >= 1 && text > 0.12 && sharp > 7 && now - st.lastRead > READ_COOLDOWN_S && !st.pageDone) this.capture({ auto: true });
    }
    st.timer = setTimeout(() => this.analyse(), 120);
  }
  torch(on) { const st = this.st; if (st.torchAuto === on) return; st.torchAuto = on; this.camera.setTorch(on).then(ok => { if (ok) this.onTorch(on); else st.torchAuto = false; }); }
  meter(el, v, color) { if (!el) return; el.style.setProperty("--v", `${Math.round(v * 100)}%`); el.style.setProperty("--c", color || "var(--ok)"); }
  viewRect() {
    // where the (cover-fitted) video lands on the overlay canvas, in overlay pixels
    const r = this.overlay.getBoundingClientRect(); const W = r.width, H = r.height;
    const { sw, sh } = this.camera.cropRect(); if (!sw) return { W, H, x: 0, y: 0, w: W, h: H };
    const s = Math.max(W / sw, H / sh); const w = sw * s, h = sh * s;
    return { W, H, x: (W - w) / 2, y: (H - h) / 2, w, h };
  }
  drawLive(rows, W, H) {
    const v = this.viewRect(); this.overlay.width = v.W; this.overlay.height = v.H;
    const o = this.octx; o.clearRect(0, 0, v.W, v.H);
    if (this.st.lastBoxes && performance.now() / 1000 - this.st.lastRead < 8) { this.drawWordBoxes(v); return; }
    const sx = v.w / W, sy = v.h / H;
    o.strokeStyle = "rgba(240,168,48,0.55)"; o.lineWidth = 1;
    for (const [y, x0, x1] of rows) { o.beginPath(); o.moveTo(v.x + x0 * sx, v.y + y * sy); o.lineTo(v.x + x1 * sx, v.y + y * sy); o.stroke(); }
  }
  drawWordBoxes(v) {
    const { boxes, W, H } = this.st.lastBoxes; const o = this.octx;
    const s = Math.max(v.W / W, v.H / H), w = W * s, h = H * s; v = { x: (v.W - w) / 2, y: (v.H - h) / 2, w, h };   // a photo still may be 4:3 where the video is 16:9: fit its own shape, same centre
    const sx = v.w / W, sy = v.h / H;
    for (const b of boxes) {
      o.strokeStyle = b.conf >= 80 ? "#5ad25a" : b.conf >= MIN_CONF ? "#f0a830" : "#e24b3b";
      o.lineWidth = 1.5; o.strokeRect(v.x + b.x0 * sx, v.y + b.y0 * sy, (b.x1 - b.x0) * sx, (b.y1 - b.y0) * sy);
    }
  }

  // ---- capture → OCR → speak
  async capture({ viaModel = true, manual = false, auto = false } = {}) {
    const st = this.st; if (st.busy || !this.camera.running) return;
    if (manual) { st.readLines.clear(); st.pageDone = false; }   // Read now means read it again, even the same card
    st.busy = true; this.onBusy(true); st.lastRead = performance.now() / 1000;
    audio.click(); this.setStatus("READING");
    try {
      // a photo-pipeline still where the browser offers one, else the sharpest of a short burst (judged
      // where the text is); never shrunk here: OCR wants every pixel, ocr-prep caps the size itself
      const stillCanvas = await this.camera.still(3200, st.textRect);
      if (!st.running) return;   // the mode changed while the still was taken: say nothing over the next room
      if (!stillCanvas) { this.setStatus("No frame from the camera yet."); return; }
      const best = { c: stillCanvas };
      // the vision model reads far better than on-device OCR; use it when there is a key
      // the free quota is shared by the whole booth: in auto mode the model reads each page once, then the
      // device takes over until the page leaves the frame; Read now always asks the model
      if (viaModel && this.ai && this.ai.hasKey() && (!auto || st.modelArmed)) {
        st.modelArmed = false;
        try {
          const text = await this.ai.readFrame(best.c);
          if (!st.running) return;
          if (text) { st.pageDone = true; this.present(text, { source: "model", conf: 95 }); return; }   // this page is read: auto waits for the next one
        } catch (e) { this.setStatus(`Model unavailable (${e.message}); reading on the device.`); }
      }
      loadWords().catch(() => {});   // the dictionary that keeps invented words out; confidence alone if it fails
      const workerP = this.ensureWorker(); workerP.catch(() => {});   // loads while the frame is prepared; an early return must not leave it unhandled
      const prepared = prepareForOcr(best.c);
      // the print is too small for the engine: say so instead of reading noise
      // (the estimate counts background texture too, so only a clearly tiny reading stops here)
      if (prepared.xHeight && prepared.xHeight < MIN_XHEIGHT_PX * 0.6) { this.say(coachText("small")); this.setStatus(coachText("small")); return; }
      let worker;
      try { worker = await workerP; } catch (e) { this.setStatus("The reader could not load (" + (e && e.message || e) + "). Check the connection and try again."); return; }
      if (!st.running) return;
      const { data } = await worker.recognize(prepared.canvas, {}, RECOGNIZE_OUTPUT);
      if (!st.running) return;
      const allWords = data.words || (data.blocks || []).flatMap(b => b.paragraphs.flatMap(p => p.lines.flatMap(l => l.words)));
      const allLines = data.lines || (data.blocks || []).flatMap(b => b.paragraphs.flatMap(p => p.lines));
      const words = allWords.filter(w => w.text.trim() && /[A-Za-z0-9]/.test(w.text));
      const good = words.filter(w => w.confidence >= MIN_CONF - 15);
      const k = prepared.scale;
      st.lastBoxes = { boxes: words.map(w => ({ x0: w.bbox.x0 / k + prepared.offsetX, y0: w.bbox.y0 / k + prepared.offsetY, x1: w.bbox.x1 / k + prepared.offsetX, y1: w.bbox.y1 / k + prepared.offsetY, conf: isKnown(w.text, w.confidence) ? w.confidence : 0 })), W: best.c.width, H: best.c.height };   // red: dropped as not a word
      if (good.length < 2) { this.coach(); return; }
      const meanConf = good.reduce((a, w) => a + w.confidence, 0) / good.length;
      await Promise.race([loadWords().catch(() => {}), new Promise(r => setTimeout(r, 1500))]);
      const real = good.filter(w => isKnown(w.text, w.confidence) && /[A-Za-z]{2,}/.test(w.text));
      const medH = median((real.length >= 2 ? real : good).map(w => w.bbox.y1 - w.bbox.y0)) / k;   // word boxes run ascender to descender, about 1.5 x-heights
      if (medH < MIN_XHEIGHT_PX * 1.2) { this.say(coachText("small")); this.setStatus(coachText("small")); return; }
      await Promise.race([loadWords().catch(() => {}), new Promise(r => setTimeout(r, 1500))]);
      // only real words, numbers, units and codes are read out; a line that is mostly invented is dropped whole
      const lines = allLines.map(l => cleanLine(l.words || [])).filter(Boolean);
      if (!lines.length) { this.coach(); return; }
      this.present(lines.join("\n"), { source: "device", conf: meanConf });
    } catch (e) {
      this.setStatus("The reader hit a problem: " + (e && e.message || e));
    } finally { st.busy = false; this.onBusy(false); }
  }
  present(text, { source, conf }) {
    const st = this.st;
    const lines = text.split(/\n+/).map(s => s.trim()).filter(Boolean);
    // a line counts as read when most of its words match one already read: OCR rarely spells a line the same way twice
    const seen = (l) => { const a = new Set(norm(l).split(" ")); for (const r of st.readLines) { const b = new Set(r.split(" ")); let k = 0; for (const w of a) if (b.has(w)) k++; if (k / Math.max(a.size, b.size) >= 0.7) return true; } return false; };
    const fresh = lines.filter(l => !seen(l));
    if (!fresh.length) {
      this.setStatus(lines.length ? "NOTHING NEW ON THIS PAGE · TAP READ NOW TO HEAR IT AGAIN" : coachText("none"));
      if (!lines.length) this.coach(); else st.lastRead = performance.now() / 1000 + 12;   // the same card: no click and no OCR every few seconds
      return;
    }
    fresh.forEach(l => st.readLines.add(norm(l)));
    st.sentences = splitSentences(fresh.join("\n"));
    if (!st.sentences.length) { this.coach(); return; }
    const unsure = conf < MIN_CONF;
    this.render(unsure); st.cur = -1; st.paused = false;
    if (unsure) this.say(tr("Not sure, but it says...", AR.unsure), () => this.speakFrom(0)); else this.speakFrom(0);
    this.setStatus(`${st.sentences.length} SENTENCE${st.sentences.length === 1 ? "" : "S"} · ${source === "model" ? "VISION MODEL" : `ON-DEVICE · ${Math.round(conf)} %`}`);
  }
  coach() {
    const m = this.st.metrics; let key = "none";
    if (m.light < 55) key = "dark"; else if (m.sat > 0.08) key = "glare"; else if (m.sharp < 7) key = "blur"; else if (m.text > 0.45) key = "close"; else if (m.text > 0.1) key = "small";
    this.say(coachText(key)); this.setStatus(coachText(key));
  }
  speakFrom(i) {
    const st = this.st;
    if (i >= st.sentences.length || this.isMuted()) { st.speaking = false; st.cur = -1; this.render(); return; }
    st.cur = i; st.speaking = true; this.render();
    this.say(st.sentences[i], () => { if (!st.paused && st.cur === i) this.speakFrom(i + 1); });
  }
  render(unsure = false) {
    const st = this.st;
    this.out.innerHTML = (unsure ? `<p class="unsure" dir="auto">${tr("Not sure, but it says", AR.unsure)}</p>` : "") +
      '<p dir="auto">' + st.sentences.map((s, i) => `<span class="sent ${i === st.cur ? "cur" : i < st.cur ? "done" : ""}">${esc(s)}</span>`).join(" ") + "</p>";
    const cur = this.out.querySelector(".sent.cur"); if (cur) cur.scrollIntoView({ block: "nearest" });
  }
  stopSpeaking() { const st = this.st; st.paused = true; if (st.cancelSpeak) st.cancelSpeak(); st.speaking = false; }

  _bind() {
    const b = this.buttons, st = this.st;
    b.now.addEventListener("click", () => { audio.prewarm(); this.capture({ manual: true }); });
    b.pause.addEventListener("click", () => {
      if (!st.sentences.length) return;
      if (st.speaking && !st.paused) { this.stopSpeaking(); b.pause.textContent = "Resume"; }
      else { st.paused = false; b.pause.textContent = "Pause"; this.speakFrom(Math.max(0, st.cur)); }
    });
    b.next.addEventListener("click", () => { if (st.sentences.length) { st.paused = false; this.speakFrom(Math.min(st.sentences.length - 1, st.cur + 1)); } });
    b.prev.addEventListener("click", () => { if (st.sentences.length) { st.paused = false; this.speakFrom(Math.max(0, st.cur - 1)); } });
    b.auto.addEventListener("click", () => { st.auto = !st.auto; b.auto.classList.toggle("on", st.auto); b.auto.setAttribute("aria-pressed", st.auto); this.setStatus(st.auto ? "AUTO · READS WHEN THE PICTURE IS STEADY" : "MANUAL · TAP READ NOW"); });
  }
  setZoomLabel(z) { if (!this.zoomLabel) return; this.zoomLabel.textContent = `${z % 1 ? z.toFixed(1) : z}×`; this.zoomLabel.classList.toggle("lossy", z > 2); }
  start() { const st = this.st; if (st.running) return; st.running = true; st.modelArmed = true; st.prevGray = null; st.steadySince = performance.now() / 1000; this.analyse(); }
  stop() { const st = this.st; st.running = false; clearTimeout(st.timer); this.stopSpeaking(); if (st.torchAuto) this.torch(false); st.dimSince = 0; this.octx.clearRect(0, 0, this.overlay.width, this.overlay.height); }
}

const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
const norm = s => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const esc = s => s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
export function splitSentences(text) {
  const out = []; for (const para of text.split(/\n+/)) {
    const parts = para.match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g) || [];
    for (const p of parts) { const t = p.trim(); if (t) out.push(t); }
  }
  return out;
}
