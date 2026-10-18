// live.js — the Live room: the tablet camera as the Halo's eye. Three modes share one
// stream: Obstacles (on-device detector → the ported announcer, with range estimated from
// box size in place of the laser), Ask (preset questions answered from the frame by a
// vision model, or locally from the detector), and Read (the reader).
import { Priority, Level, spokenLabel, HazardAssessor } from "./halo.js";
import * as audio from "./audio.js";
import { drawOverlay } from "./overlay.js";
import { Camera } from "./camera.js";
import { Reader } from "./reader.js";
import { rangeCm } from "./range.js";
import * as ai from "./ai.js";

const LIVE_THRESHOLD = 0.32;   // EfficientDet-Lite0 scores sit lower than the device network's 0.55

export function initLive(el, { cfg, pipeline, speech, hood }) {
  const { video, overlay, startBtn, startNote, status, modes, panels, det, ask, read, torchBtn, zoomLabel, meters } = el;
  const octx = overlay.getContext("2d");
  const camera = new Camera(video);
  const st = { mode: "obstacles", running: false, detector: null, detectorState: "idle", loop: 0, lastDets: [], frameW: cfg.width, frameH: cfg.height,
    vfov: 43, busy: false, asking: null, pinch: null, zoom: 1, lastSpeakScene: 0, transcript: [] };
  const aiBridge = {
    hasKey: () => !!ai.getKey(),
    async readFrame(canvas) {
      const small = document.createElement("canvas"); const k = Math.min(1, 1280 / canvas.width); small.width = Math.round(canvas.width * k); small.height = Math.round(canvas.height * k); small.getContext("2d").drawImage(canvas, 0, 0, small.width, small.height);
      const blob = await new Promise(r => small.toBlob(r, "image/jpeg", 0.8));
      const b64 = await new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result.split(",")[1]); fr.onerror = rej; fr.readAsDataURL(blob); });
      const r = await ai.ask({ key: ai.getKey(), question: "Read all the text in this picture exactly as printed, in reading order, one line per printed line. Output only the text.", frame: { b64 }, context: "", detail: true });
      return r.text.replace(/\s*[|•]\s*/g, "\n");
    },
  };
  const reader = new Reader({ camera, overlay, out: read.out, status, meters: read.meters, zoomLabel, buttons: read.buttons, ai: aiBridge });

  // ------------------------------------------------------------ camera lifecycle
  async function startCamera() {
    audio.prewarm();
    startBtn.disabled = true; startNote.textContent = "Opening the camera…";
    try {
      await camera.start();
      startBtn.parentElement.hidden = true;
      torchBtn.hidden = !camera.hasTorch;
      const { w, h } = camera.size; st.vfov = w / h > 1.5 ? 43 : 52;
      setMode(st.mode, true);
    } catch (e) {
      startBtn.disabled = false;
      startNote.textContent = location.protocol === "https:" || location.hostname === "localhost" ? `Camera not available (${e.name || e.message}). Allow the camera for this site and try again.` : "The camera needs HTTPS or localhost.";
    }
  }
  startBtn.addEventListener("click", startCamera);
  torchBtn.addEventListener("click", async () => { const on = !torchBtn.classList.contains("on"); if (await camera.setTorch(on)) torchBtn.classList.toggle("on", on); });

  // ------------------------------------------------------------ modes
  function setMode(mode, force = false) {
    if (!force && mode === st.mode) return;
    const prev = st.mode; st.mode = mode;
    modes.forEach(b => { b.classList.toggle("on", b.dataset.mode === mode); b.setAttribute("aria-selected", b.dataset.mode === mode); });
    panels.forEach(p => { p.hidden = p.dataset.mode !== mode; });
    if (meters) meters.hidden = mode !== "read" || !camera.running;
    if (prev === "read") { reader.stop(); setZoom(1); }
    if (!camera.running) return;
    if (mode === "read") { stopDetectLoop(); octx.clearRect(0, 0, overlay.width, overlay.height); reader.start(); status.textContent = "Hold the text steady. I read when the picture is sharp."; }
    else { startDetectLoop(); status.textContent = mode === "ask" ? "Tap a question, or type one." : "Looking…"; }
  }
  modes.forEach(b => b.addEventListener("click", () => { audio.prewarm(); setMode(b.dataset.mode); }));

  // ------------------------------------------------------------ detector loop
  async function ensureDetector() {
    if (st.detector) return st.detector;
    if (st.detectorState === "loading") return null;
    st.detectorState = "loading"; status.textContent = "Loading the detector…";
    try {
      const mod = await import("./detector.js");
      st.detector = await mod.loadDetector({ onProgress: (p) => { status.textContent = `Loading the detector… ${p}`; } });
      st.detectorState = "ready"; status.textContent = "Looking…";
      return st.detector;
    } catch (e) { st.detectorState = "failed"; status.textContent = `Detector unavailable: ${e.message}`; return null; }
  }
  function startDetectLoop() { if (st.running) return; st.running = true; pipeline.reset(); detectTick(); }
  function stopDetectLoop() { st.running = false; cancelAnimationFrame(st.loop); }
  async function detectTick() {
    if (!st.running) return;
    const d = await ensureDetector();
    if (!st.running) return;
    const now = performance.now() / 1000;
    let dets = null;
    if (d && camera.running) {
      try { dets = await d.detect(video); } catch (e) { dets = null; }
    }
    if (!st.running) return;
    feed(dets, now);
    draw();
    st.loop = requestAnimationFrame(() => detectTick());
  }
  /** Map detector boxes (video pixels) into the firmware frame, estimate range, run the pipeline. */
  function feed(dets, now) {
    const { w: vw, h: vh } = camera.size; if (!vw) return;
    const kx = cfg.width / vw, ky = cfg.height / vh;
    const mapped = (dets || []).map(dd => {
      const [x, y, w, h] = dd.box;
      const clippedTop = y <= 2, clippedBottom = y + h >= vh - 2;
      return { label: dd.label, score: dd.score, box: [x * kx, y * ky, w * kx, h * ky], rangeCm: rangeCm(dd.label, [x, y, w, h], vh, st.vfov, clippedTop, clippedBottom) };
    });
    st.lastDets = mapped;
    // the "beam": whichever box covers the centre of the frame owns the range reading
    const aim = pipeline.assessor.aimBox(null);
    let beam = null, best = 0;
    for (const m of mapped) { const ov = HazardAssessor.overlapFrac(aim, m.box); if (ov > 0.25 && ov * m.score > best) { best = ov * m.score; beam = m; } }
    if (beam && beam.rangeCm != null) pipeline.pushLidar(beam.rangeCm, 1000, now); else pipeline.pushLidar(null, 0, now);
    pipeline.step(dets ? mapped : null, now, LIVE_THRESHOLD);
    // carry the range onto the smoothed tracks for the overlay and the question context
    for (const t of pipeline.tracks) {
      const m = mapped.filter(x => x.label === t.label).sort((a, b) => dist2(a.box, t.box) - dist2(b.box, t.box))[0];
      t.rangeCm = m ? m.rangeCm : t.rangeCm;
    }
    updateDetList();
  }
  function dist2(a, b) { return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2; }
  function viewRect() {
    const r = overlay.getBoundingClientRect(); const W = r.width, H = r.height; const { w: vw, h: vh } = camera.size;
    if (!vw) return { W, H, x: 0, y: 0, w: W, h: H };
    const s = Math.max(W / vw, H / vh); const w = vw * s, h = vh * s;
    return { W, H, x: (W - w) / 2, y: (H - h) / 2, w, h };
  }
  function draw() {
    const v = viewRect(); const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (overlay.width !== Math.round(v.W * dpr) || overlay.height !== Math.round(v.H * dpr)) { overlay.width = Math.round(v.W * dpr); overlay.height = Math.round(v.H * dpr); }
    octx.save(); octx.setTransform(dpr, 0, 0, dpr, 0, 0); octx.clearRect(0, 0, v.W, v.H);
    drawOverlay(octx, v.W, v.H, { tracks: pipeline.tracks, hazard: pipeline.hazard, lidarSample: pipeline.lidarSample, speech, cfg, fps: pipeline.fps },
      { haptics: true, view: { x: v.x, y: v.y, w: v.w, h: v.h }, live: true, quiet: st.mode === "ask", bottomInset: 40 });
    octx.restore();
  }
  function updateDetList() {
    if (!det.list) return;
    const items = [...pipeline.tracks].sort((a, b) => (a.rangeCm ?? 9999) - (b.rangeCm ?? 9999)).slice(0, 6);
    det.list.innerHTML = items.length ? items.map(t => `<li><b>${spokenLabel(t.label)}</b><span>${t.rangeCm != null ? `~${(t.rangeCm / 100).toFixed(1)} m` : "—"}</span><em>${t.score.toFixed(2)}</em></li>`).join("") : '<li class="muted">Nothing recognised yet.</li>';
    det.hazard.textContent = pipeline.hazard && pipeline.hazard.message ? pipeline.hazard.message : "Clear";
    det.hazard.dataset.level = pipeline.hazard ? pipeline.hazard.level : 0;
  }
  det.describe.addEventListener("click", () => { cfg.describe = !cfg.describe; det.describe.classList.toggle("on", cfg.describe); det.describe.setAttribute("aria-pressed", cfg.describe); speech.say(cfg.describe ? "Describe mode on" : "Describe mode off", Priority.INFO, false, 3); });
  det.scene.addEventListener("click", () => pipeline.speakScene());

  // ------------------------------------------------------------ ask
  function renderChips() {
    ask.chips.innerHTML = "";
    for (const q of ai.QUESTIONS) {
      const b = document.createElement("button"); b.className = "chip"; b.textContent = q.text; b.dataset.id = q.id;
      b.addEventListener("click", () => askQuestion(q));
      ask.chips.appendChild(b);
    }
  }
  renderChips();
  function keyLine() {
    const has = !!ai.getKey();
    ask.keyNote.textContent = has ? "Answers come from Google's Gemini on its free tier. One frame leaves the tablet per question, and Google may use free-tier requests to improve its products." : "No key yet: answers come from the on-device detector. Add a free Gemini key in Settings for real answers.";
    ask.keyNote.classList.toggle("warn", !has);
  }
  keyLine();
  async function askQuestion(q) {
    if (st.asking) return;
    const text = typeof q === "string" ? q : q.text;
    if (!camera.running) { addTurn(text, "Open the camera first."); return; }
    if (q.mode === "read" || /^read\b/i.test(text)) { setMode("read"); setTimeout(() => reader.capture(), 350); addTurn(text, "Reading…", { pending: true }); return; }
    const key = ai.getKey();
    const turn = addTurn(text, key ? "Looking…" : "", { pending: true });
    st.asking = turn;
    try {
      const context = ai.describeDetections(pipeline.tracks, pipeline.hazard, cfg.width).line;
      let answer = null, meta = "";
      if (key) {
        const detail = !!(q.detail);
        const frame = await camera.jpeg(detail ? 1024 : 768, detail ? 0.75 : 0.65);
        const r = await ai.ask({ key, question: text, frame, context, detail });
        answer = r.text; meta = `${r.model.replace("gemini-", "")} · ${(r.ms / 1000).toFixed(1)} s`;
      } else {
        answer = ai.localAnswer(q, { tracks: pipeline.tracks, hazard: pipeline.hazard, frameW: cfg.width, cfg }) || "I can answer that with a vision key. Add a free Gemini key in Settings.";
        meta = "on-device";
      }
      setTurn(turn, answer, meta);
      speech.say(answer, Priority.INFO, false, 30);
    } catch (e) {
      const why = ai.explainError(e);
      const fallback = ai.localAnswer(q, { tracks: pipeline.tracks, hazard: pipeline.hazard, frameW: cfg.width, cfg });
      setTurn(turn, fallback ? `${fallback}` : `I couldn't reach the model: ${why}.`, fallback ? `on-device (model: ${why})` : "");
      if (fallback) speech.say(fallback, Priority.INFO, false, 30);
    } finally { st.asking = null; }
  }
  function addTurn(q, a, { pending = false } = {}) {
    const li = document.createElement("li"); li.className = "turn" + (pending ? " pending" : "");
    li.innerHTML = `<p class="q">${esc(q)}</p><p class="a">${esc(a)}</p><span class="meta"></span>`;
    ask.log.prepend(li); while (ask.log.children.length > 8) ask.log.lastChild.remove();
    return li;
  }
  function setTurn(li, a, meta) { li.classList.remove("pending"); li.querySelector(".a").textContent = a; li.querySelector(".meta").textContent = meta || ""; }
  ask.form.addEventListener("submit", (e) => { e.preventDefault(); const t = ask.input.value.trim(); if (!t) return; ask.input.value = ""; askQuestion(t); });
  // voice input where the browser offers it
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SR) {
    ask.mic.hidden = false;
    ask.mic.addEventListener("click", () => {
      const r = new SR(); r.lang = "en-US"; r.interimResults = false; r.maxAlternatives = 1;
      ask.mic.classList.add("on"); ask.input.placeholder = "Listening…";
      r.onresult = (ev) => { const t = ev.results[0][0].transcript; ask.input.value = t; askQuestion(t); ask.input.value = ""; };
      r.onend = () => { ask.mic.classList.remove("on"); ask.input.placeholder = "Ask anything about what's in front of you"; };
      r.onerror = () => { ask.mic.classList.remove("on"); ask.input.placeholder = "Couldn't hear that. Try again, or type."; };
      try { r.start(); } catch (_) { ask.mic.classList.remove("on"); }
    });
  } else ask.mic.hidden = true;

  // ------------------------------------------------------------ pinch zoom (read mode)
  const pts = new Map(); const stage = overlay.parentElement;
  stage.addEventListener("pointerdown", e => { if (st.mode !== "read") return; pts.set(e.pointerId, [e.clientX, e.clientY]); if (pts.size === 2) st.pinch = { d: dist2p(), z: st.zoom }; });
  stage.addEventListener("pointermove", e => { if (!pts.has(e.pointerId)) return; pts.set(e.pointerId, [e.clientX, e.clientY]); if (pts.size === 2 && st.pinch) setZoom(st.pinch.z * dist2p() / st.pinch.d, false); });
  const pu = e => { pts.delete(e.pointerId); if (pts.size < 2 && st.pinch) { st.pinch = null; setZoom(Math.round(st.zoom * 2) / 2, true); } };
  stage.addEventListener("pointerup", pu); stage.addEventListener("pointercancel", pu);
  stage.addEventListener("wheel", e => { if (st.mode !== "read") return; setZoom(st.zoom * (e.deltaY < 0 ? 1.1 : 0.9), false); clearTimeout(st.wheelT); st.wheelT = setTimeout(() => setZoom(Math.round(st.zoom * 2) / 2, true), 400); }, { passive: true });
  function dist2p() { const a = [...pts.values()]; return Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]); }
  function setZoom(z, announce) {
    st.zoom = Math.max(1, Math.min(3, z)); camera.setZoom(st.zoom);
    video.style.transform = camera._hwZoom > 1 ? "" : `scale(${st.zoom})`;
    reader.setZoomLabel(st.zoom);
    if (announce && st.zoom !== 1) audio.speak(`Zoom ${st.zoom % 1 ? st.zoom.toFixed(1) : st.zoom} times`);
  }

  function onResize() { if (camera.running && st.mode !== "read") draw(); }
  window.addEventListener("resize", onResize);

  return {
    start() { keyLine(); if (camera.running) setMode(st.mode, true); },
    stop() { stopDetectLoop(); reader.stop(); if (st.mode === "read") setZoom(1); },
    release() { this.stop(); camera.stop(); startBtn.parentElement.hidden = false; startBtn.disabled = false; },
    refreshKey: keyLine, camera, reader, debug: () => ({ dets: st.lastDets, detector: st.detector && st.detector.name, state: st.detectorState }),
    get mode() { return st.mode; },
  };
}
const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
