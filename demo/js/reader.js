// reader.js — the Read room: vantage_reader.py's behaviour on the tablet camera.
// Auto mode waits for text in view and a still camera (0.7 s), plays the click, grabs a
// burst of frames and keeps the sharpest, OCRs it on the tablet, then reads sentence by
// sentence. When it cannot read, it says why, in the reader's own words.
import * as audio from "./audio.js";

const STEADY_S = 0.7, BURST = 5, MIN_CONF = 60, READ_COOLDOWN_S = 3.5;
const COACH = {
  dark: "It's too dark to read. Turn on a light or move closer to a window.",
  glare: "There's glare on the text. Tilt it slightly away from the light.",
  close: "The text is too close. Move it a little farther away.",
  blur: "The picture is blurry. Hold still, or move the text a little farther away.",
  small: "The text is too small. Pinch to zoom in, or move a little closer.",
  none: "I can't see any text. Point the camera at a page or a sign.",
};

export function initReader(el) {
  const { video, overlay, view, out, status, meters, zoomLabel, buttons } = el;
  const octx = overlay.getContext("2d");
  const work = document.createElement("canvas"), wctx = work.getContext("2d", { willReadFrequently: true });
  const st = { running: false, stream: null, worker: null, workerReady: null, prevGray: null, steadySince: 0, lastRead: -1e9, busy: false, auto: true,
    zoom: 1, pinch: null, sentences: [], cur: -1, paused: false, speaking: false, cancelSpeak: null, readLines: new Set(), metrics: { sharp: 0, light: 0, steady: 0, text: 0 } };

  const setStatus = (t) => { status.textContent = t; };
  const say = (text, onEnd) => { if (st.cancelSpeak) st.cancelSpeak(); st.cancelSpeak = audio.speak(text, () => { st.cancelSpeak = null; onEnd && onEnd(); }); };

  async function startCamera() {
    try {
      st.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      video.srcObject = st.stream; await video.play();
      buttons.start.hidden = true; setStatus("Hold the text steady. I'll read it when the picture is sharp.");
    } catch (e) {
      setStatus("Camera not available. On iPad use Safari and allow the camera; the page must be served over HTTPS.");
    }
  }
  function ensureWorker() {
    if (st.workerReady) return st.workerReady;
    setStatus("Loading the reader…");
    st.workerReady = (async () => {
      if (!window.Tesseract) await new Promise((res, rej) => { const s = document.createElement("script"); s.src = "vendor/tesseract/tesseract.min.js"; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
      const base = new URL("vendor/tesseract/", location.href).href;
      st.worker = await Tesseract.createWorker("eng", 1, { workerPath: base + "worker.min.js", corePath: base, langPath: base, gzip: false, logger: () => {} });
      await st.worker.setParameters({ preserve_interword_spaces: "1" });
      return st.worker;
    })();
    return st.workerReady;
  }

  // ---- live analysis at ~8 Hz on a 240-px-wide grey frame
  function analyse() {
    if (!st.running) return;
    if (video.readyState >= 2 && video.videoWidth) {
      const W = 240, H = Math.round(W * video.videoHeight / video.videoWidth);
      work.width = W; work.height = H;
      drawZoomed(wctx, W, H);
      const d = wctx.getImageData(0, 0, W, H).data, g = new Float32Array(W * H);
      let sum = 0, sat = 0;
      for (let i = 0, j = 0; i < d.length; i += 4, j++) { const v = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; g[j] = v; sum += v; if (v > 245) sat++; }
      const light = sum / (W * H);
      // sharpness: variance of a 4-neighbour Laplacian
      let lsum = 0, lsq = 0, n = 0, edges = 0;
      for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
        const i = y * W + x, L = 4 * g[i] - g[i - 1] - g[i + 1] - g[i - W] - g[i + W];
        lsum += L; lsq += L * L; n++;
        if (Math.abs(g[i] - g[i + 1]) > 40) edges++;
      }
      const sharp = Math.sqrt(Math.max(0, lsq / n - (lsum / n) ** 2));
      // text-likeness: rows with many sharp horizontal transitions, clustered
      let textRows = 0;
      for (let y = 2; y < H - 2; y += 2) { let tr = 0; for (let x = 1; x < W - 1; x++) if (Math.abs(g[y * W + x] - g[y * W + x + 1]) > 35) tr++; if (tr > W * 0.08 && tr < W * 0.6) textRows++; }
      const text = textRows / (H / 2);
      let motion = 1;
      if (st.prevGray) { let md = 0; for (let i = 0; i < g.length; i += 3) md += Math.abs(g[i] - st.prevGray[i]); motion = md / (g.length / 3); }
      st.prevGray = g;
      const now = performance.now() / 1000;
      const steady = motion < 6;
      if (!steady) st.steadySince = now;
      const steadyFrac = Math.min(1, (now - st.steadySince) / STEADY_S);
      st.metrics = { sharp, light, steady: steadyFrac, text, sat: sat / (W * H), motion };
      meter(meters.sharp, Math.min(1, sharp / 18), sharp > 9 ? "" : "#ff9f1a");
      meter(meters.light, Math.min(1, light / 160), light > 60 && light < 235 ? "" : "#ff9f1a");
      meter(meters.steady, steadyFrac, steadyFrac >= 1 ? "" : "#aaa");
      drawLive(text, W, H, g);
      if (st.auto && !st.busy && !st.speaking && steadyFrac >= 1 && text > 0.12 && sharp > 7 && now - st.lastRead > READ_COOLDOWN_S) capture();
    }
    setTimeout(analyse, 120);
  }
  function meter(el, v, color) { el.style.setProperty("--v", `${Math.round(v * 100)}%`); el.style.setProperty("--c", color || "var(--green)"); }
  function drawZoomed(ctx, W, H) {
    const z = st.zoom, vw = video.videoWidth, vh = video.videoHeight;
    const sw = vw / z, sh = vh / z;
    ctx.drawImage(video, (vw - sw) / 2, (vh - sh) / 2, sw, sh, 0, 0, W, H);
  }
  function drawLive(text, W, H, g) {
    const r = view.getBoundingClientRect(); overlay.width = r.width; overlay.height = r.height;
    octx.clearRect(0, 0, overlay.width, overlay.height);
    if (st.lastBoxes && performance.now() / 1000 - st.lastRead < 6) { drawWordBoxes(); return; }
    // outline rows that look like text
    const sx = overlay.width / W, sy = overlay.height / H;
    octx.strokeStyle = "rgba(143,211,255,0.7)"; octx.lineWidth = 1;
    for (let y = 2; y < H - 2; y += 2) {
      let tr = 0, x0 = W, x1 = 0;
      for (let x = 1; x < W - 1; x++) if (Math.abs(g[y * W + x] - g[y * W + x + 1]) > 35) { tr++; x0 = Math.min(x0, x); x1 = Math.max(x1, x); }
      if (tr > W * 0.08 && tr < W * 0.6) { octx.beginPath(); octx.moveTo(x0 * sx, y * sy); octx.lineTo(x1 * sx, y * sy); octx.stroke(); }
    }
  }
  function drawWordBoxes() {
    const { boxes, W, H } = st.lastBoxes; const sx = overlay.width / W, sy = overlay.height / H;
    for (const b of boxes) {
      const c = b.conf >= 80 ? "#5ad25a" : b.conf >= MIN_CONF ? "#ffbe00" : "#eb2828";
      octx.strokeStyle = c; octx.lineWidth = 1.5; octx.strokeRect(b.x0 * sx, b.y0 * sy, (b.x1 - b.x0) * sx, (b.y1 - b.y0) * sy);
    }
  }

  // ---- capture → OCR → speak
  async function capture() {
    if (st.busy || !video.videoWidth) return;
    st.busy = true; st.lastRead = performance.now() / 1000;
    audio.click(); setStatus("Reading…");
    try {
      const worker = await ensureWorker();
      // burst: keep the sharpest of BURST frames
      let best = null;
      for (let i = 0; i < BURST; i++) {
        const c = document.createElement("canvas"); const scale = Math.min(1, 1600 / (video.videoWidth / st.zoom));
        c.width = Math.round(video.videoWidth / st.zoom * scale); c.height = Math.round(video.videoHeight / st.zoom * scale);
        const cx = c.getContext("2d", { willReadFrequently: true }); drawZoomed(cx, c.width, c.height);
        const s = sharpness(cx, c.width, c.height);
        if (!best || s > best.s) best = { c, cx, s };
        await new Promise(r => setTimeout(r, 45));
      }
      const { c, cx } = best;
      // grey, contrast stretch, mild sharpen: the reader's "even out the lighting" step
      const img = cx.getImageData(0, 0, c.width, c.height), d = img.data;
      let lo = 255, hi = 0; const hist = new Uint32Array(256);
      for (let i = 0; i < d.length; i += 4) { const v = Math.round(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]); d[i] = v; hist[v]++; }
      let acc = 0; for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc > d.length / 4 * 0.02 && lo === 255) lo = v; if (acc > d.length / 4 * 0.98) { hi = v; break; } }
      const rng = Math.max(1, hi - lo);
      for (let i = 0; i < d.length; i += 4) { const v = Math.max(0, Math.min(255, (d[i] - lo) * 255 / rng)); d[i] = d[i + 1] = d[i + 2] = v; }
      cx.putImageData(img, 0, 0);
      const { data } = await worker.recognize(c);
      const words = (data.words || []).filter(w => w.text.trim() && /[A-Za-z0-9]/.test(w.text));
      const good = words.filter(w => w.confidence >= MIN_CONF - 15);
      st.lastBoxes = { boxes: words.map(w => ({ ...w.bbox, conf: w.confidence })), W: c.width, H: c.height };
      if (good.length < 2) { coach(); return; }
      const meanConf = good.reduce((a, w) => a + w.confidence, 0) / good.length;
      const medH = median(good.map(w => w.bbox.y1 - w.bbox.y0));
      if (medH < 11) { say(COACH.small); setStatus(COACH.small); return; }
      // lines → drop junk, skip lines already read, split into sentences
      const lines = (data.lines || []).map(l => ({ text: l.text.replace(/\s+/g, " ").trim(), conf: l.confidence, words: l.words.filter(w => w.confidence >= MIN_CONF - 15).length }))
        .filter(l => l.text.length >= 2 && l.words >= 1 && /[A-Za-z0-9]{2,}/.test(l.text) && (l.text.match(/[A-Za-z0-9 .,;:'"!?()\-\/%]/g) || []).length / l.text.length > 0.75);
      const fresh = lines.filter(l => !st.readLines.has(norm(l.text)));
      if (!fresh.length) { setStatus("Nothing new on this page."); return; }
      fresh.forEach(l => st.readLines.add(norm(l.text)));
      const text = fresh.map(l => l.text).join("\n");
      st.sentences = splitSentences(text);
      renderText(meanConf < MIN_CONF);
      st.cur = -1; st.paused = false;
      if (meanConf < MIN_CONF) say("Not sure, but it says...", () => speakFrom(0)); else speakFrom(0);
      setStatus(`${st.sentences.length} sentence${st.sentences.length === 1 ? "" : "s"} · confidence ${Math.round(meanConf)}%`);
    } catch (e) {
      setStatus("The reader hit a problem: " + (e && e.message || e));
    } finally { st.busy = false; }
  }
  function coach() {
    const m = st.metrics; let key = "none";
    if (m.light < 55) key = "dark";
    else if (m.sat > 0.08) key = "glare";
    else if (m.sharp < 7) key = "blur";
    else if (m.text > 0.45) key = "close";
    else if (m.text > 0.1) key = "small";
    say(COACH[key]); setStatus(COACH[key]);
  }
  function speakFrom(i) {
    if (i >= st.sentences.length) { st.speaking = false; st.cur = -1; renderText(); return; }
    st.cur = i; st.speaking = true; renderText();
    say(st.sentences[i], () => { if (!st.paused && st.cur === i) speakFrom(i + 1); });
  }
  function renderText(unsure = false) {
    out.innerHTML = (unsure ? '<p class="unsure">Not sure, but it says…</p>' : "") +
      "<p>" + st.sentences.map((s, i) => `<span class="sent ${i === st.cur ? "cur" : i < st.cur ? "done" : ""}">${esc(s)}</span>`).join(" ") + "</p>";
    const cur = out.querySelector(".sent.cur"); if (cur) cur.scrollIntoView({ block: "nearest" });
  }

  // ---- controls
  buttons.start.addEventListener("click", () => { audio.prewarm(); startCamera(); });
  buttons.now.addEventListener("click", () => { audio.prewarm(); capture(); });
  buttons.pause.addEventListener("click", () => {
    if (!st.sentences.length) return;
    if (st.speaking && !st.paused) { st.paused = true; if (st.cancelSpeak) st.cancelSpeak(); st.speaking = false; buttons.pause.textContent = "Resume"; }
    else { st.paused = false; buttons.pause.textContent = "Pause"; speakFrom(Math.max(0, st.cur)); }
  });
  buttons.next.addEventListener("click", () => { if (st.sentences.length) { st.paused = false; speakFrom(Math.min(st.sentences.length - 1, st.cur + 1)); } });
  buttons.prev.addEventListener("click", () => { if (st.sentences.length) { st.paused = false; speakFrom(Math.max(0, st.cur - 1)); } });
  buttons.auto.addEventListener("click", () => { st.auto = !st.auto; buttons.auto.classList.toggle("on", st.auto); setStatus(st.auto ? "Auto: I read when the picture is steady." : "Manual: tap Read now."); });
  // pinch zoom 1×..3×, spoken when the pinch ends, like the mouse wheel on the device
  const pts = new Map();
  view.addEventListener("pointerdown", e => { pts.set(e.pointerId, [e.clientX, e.clientY]); if (pts.size === 2) st.pinch = { d: dist2(), z: st.zoom }; });
  view.addEventListener("pointermove", e => { if (!pts.has(e.pointerId)) return; pts.set(e.pointerId, [e.clientX, e.clientY]); if (pts.size === 2 && st.pinch) setZoom(st.pinch.z * dist2() / st.pinch.d, false); });
  const pu = e => { pts.delete(e.pointerId); if (pts.size < 2 && st.pinch) { st.pinch = null; setZoom(Math.round(st.zoom * 2) / 2, true); } };
  view.addEventListener("pointerup", pu); view.addEventListener("pointercancel", pu);
  view.addEventListener("wheel", e => { setZoom(st.zoom * (e.deltaY < 0 ? 1.1 : 0.9), false); clearTimeout(st.wheelT); st.wheelT = setTimeout(() => setZoom(Math.round(st.zoom * 2) / 2, true), 400); }, { passive: true });
  function dist2() { const a = [...pts.values()]; return Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]); }
  function setZoom(z, announce) {
    st.zoom = Math.max(1, Math.min(3, z));
    video.style.transform = `scale(${st.zoom})`;
    zoomLabel.textContent = `${st.zoom % 1 ? st.zoom.toFixed(1) : st.zoom}×`;
    zoomLabel.classList.toggle("lossy", st.zoom > 2);
    if (announce) say(`Zoom ${st.zoom % 1 ? st.zoom.toFixed(1) : st.zoom} times`);
  }

  return {
    start() { st.running = true; if (st.stream) video.play(); analyse(); },
    stop() { st.running = false; if (st.cancelSpeak) st.cancelSpeak(); st.speaking = false; if (st.stream) { st.stream.getTracks().forEach(t => t.stop()); st.stream = null; video.srcObject = null; buttons.start.hidden = false; } },
  };
}

function sharpness(ctx, W, H) {
  const step = Math.max(1, Math.floor(W / 320)); const d = ctx.getImageData(0, 0, W, H).data; let s = 0, n = 0;
  for (let y = step; y < H - step; y += step * 2) for (let x = step; x < W - step; x += step * 2) {
    const i = (y * W + x) * 4, l = 4 * d[i] - d[i - 4 * step] - d[i + 4 * step] - d[i - 4 * W * step] - d[i + 4 * W * step]; s += l * l; n++;
  }
  return Math.sqrt(s / Math.max(1, n));
}
const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
const norm = s => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const esc = s => s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
function splitSentences(text) {
  const out = []; for (const para of text.split(/\n+/)) {
    const parts = para.match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g) || [];
    for (const p of parts) { const t = p.trim(); if (t) out.push(t); }
  }
  return out;
}
