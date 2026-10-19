// app.js — the journey: Wear → Walk (home, street, café) → by ear → replay, plus the
// camera rooms (Read, Inside) and the pipeline view. Wires the ported firmware logic in
// halo.js to the simulated sensors in world.js and the headset in audio.js.
import { defaultConfig, HaloPipeline, SpeechQueue, Priority, Level, levelName, priorityName } from "./halo.js";
import * as audio from "./audio.js";
import { drawOverlay } from "./overlay.js";
import { World } from "./world.js";
import { SCENES, ORDER } from "./scenes.js";
import { initLive } from "./live.js";
import * as ai from "./ai.js";
import { initInside } from "./inside.js";
import { initHood } from "./hood.js";
import { Escape } from "./escape.js";

const $ = (id) => document.getElementById(id);
const cfg = defaultConfig();
const state = {
  room: "start", scene: "home", mode: "guide", trust: false, replay: null, haptics: true,
  log: null, worldReady: false, sosSent: false,
};

// ------------------------------------------------------------------ pipeline + hood
const hood = initHood({ pipelineRoot: $("pipeline"), queueList: $("queueList"), queueEvents: $("queueEvents"), dash: $("dash"), logLines: $("logLines") });
const speech = new SpeechQueue(audio.backend, (ev) => { hood.onSpeechEvent(ev); onSpeechEvent(ev); });
const pipeline = new HaloPipeline(cfg, speech, (ev) => hood.onPipelineEvent(ev));
// a muted twin for the replay, so scrubbing never speaks
const silentSpeech = new SpeechQueue({ speak: (t, end) => { end(); return () => {}; }, beep: (end) => { end(); return () => {}; }, isSpeaking: () => false });
silentSpeech.muted = true;
const replayPipeline = new HaloPipeline(cfg, silentSpeech);

function onSpeechEvent(ev) {
  if (ev.type === "speaking" && state.log) state.log.speech.push({ t: state.log.clock(), text: ev.utt.text, prio: ev.utt.priority });
  if (ev.type === "speaking" && ev.utt.priority === Priority.CRITICAL) audio.haptic([80, 50, 80]);
}

// ------------------------------------------------------------------ rooms
const rooms = ["start", "walk", "live", "inside", "hood"];
let live = null, inside = null;
function showRoom(name) {
  for (const r of rooms) $(r).classList.toggle("active", r === name);
  document.querySelectorAll(".rooms button").forEach(b => b.classList.toggle("on", b.dataset.room === name));
  const prev = state.room; state.room = name;
  if (prev === "live" && name !== "live" && live) live.release();   // one camera at a time: Inside may open its own
  if (prev === "inside" && inside) inside.stop();
  if (name === "walk") { resizePanes(); if (!state.worldReady) loadScene(state.scene); }
  if (name === "live") { if (!live) live = initLive({
      video: $("liveCam"), overlay: $("liveOverlay"), startBtn: $("liveStart"), startNote: $("liveStartNote"), status: $("liveStatus"), torchBtn: $("torchBtn"), zoomLabel: $("zoomLabel"), meters: $("readMeters"), side: $("liveSide"),
      modes: [...document.querySelectorAll("#live .modes button")], panels: [...document.querySelectorAll("#live .panel")],
      det: { list: $("detList"), hazard: $("detHazard"), describe: $("detDescribe"), scene: $("detScene") },
      ask: { chips: $("askChips"), form: $("askForm"), input: $("askInput"), mic: $("askMic"), log: $("askLog"), keyNote: $("askKeyNote") },
      read: { out: $("readOut"), meters: { sharp: $("mSharp"), light: $("mLight"), steady: $("mSteady") }, buttons: { now: $("readNow"), prev: $("readPrev"), pause: $("readPause"), next: $("readNext"), auto: $("readAuto") } },
    }, { cfg, pipeline, speech, hood });
    live.start(); }
  if (name === "inside") { if (!inside) inside = initInside({ canvas: $("twin"), video: $("insideCam"), slider: $("explode"), card: { root: $("partCard"), title: $("cardTitle"), status: $("cardStatus"), line: $("cardLine"), detail: $("cardDetail"), spec: $("cardSpec"), close: $("cardClose"), img: $("cardImg") }, xray: $("xrayBtn"), reset: $("twinReset"), hint: $("insideHint"), labels: $("twinLabels"), list: $("twinList"), poster: $("poster"), posterBtn: $("posterBtn") }); inside.start(); }
  $("disclaimer").style.visibility = (name === "inside") ? "hidden" : "visible";
  if (name === "hood") hood.start(); else hood.stop();
}
document.querySelectorAll("[data-room]").forEach(b => b.addEventListener("click", (e) => { e.preventDefault(); audio.prewarm(); showRoom(b.dataset.room); }));

// ------------------------------------------------------------------ WEAR
$("beepBtn").addEventListener("click", () => {
  audio.prewarm(); audio.beep(() => { $("beepYes").hidden = false; });
});
$("beepYes").addEventListener("click", () => { $("stepBeep").classList.add("done"); $("beepYes").hidden = true; });

function populateVoices() {
  const vs = audio.listVoices(); const box = $("voices"); box.innerHTML = "";
  if (!vs.length) { box.innerHTML = '<span class="dim">System voice.</span>'; return; }
  // prefer a few distinct, natural-sounding voices
  const pick = []; const seen = new Set();
  const pref = /Samantha|Daniel|Karen|Moira|Google UK English|Google US English|Microsoft (Aria|Guy|Sonia)|Natural|Premium|Enhanced/i;
  for (const v of [...vs].sort((a, b) => (pref.test(b.name) ? 1 : 0) - (pref.test(a.name) ? 1 : 0))) {
    const key = v.name.replace(/\(.*\)/, "").trim(); if (seen.has(key)) continue; seen.add(key); pick.push(v); if (pick.length >= 4) break;
  }
  pick.forEach((v, i) => {
    const b = document.createElement("button"); b.textContent = v.name.replace(/Microsoft |Google /, "").split("(")[0].trim();
    b.addEventListener("click", () => { audio.setVoice(v); box.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); speech.say("Vantage ready", Priority.INFO, false, 5); $("stepVoice").classList.add("done"); });
    if (i === 0) { b.classList.add("on"); audio.setVoice(v); }
    box.appendChild(b);
  });
}
if (window.speechSynthesis) { populateVoices(); speechSynthesis.onvoiceschanged = populateVoices; }
$("rate").addEventListener("input", e => { const v = +e.target.value; $("rateVal").textContent = v; audio.setRateWpm(v); cfg.speechRate = v; });
$("goWalk").addEventListener("click", () => { audio.prewarm(); showRoom("walk"); speech.say("Vantage ready", Priority.INFO, false, 5); });
$("goLive").addEventListener("click", () => { audio.prewarm(); showRoom("live"); });

// ------------------------------------------------------------------ WALK
const worldCanvas = $("world"), haloCanvas = $("halo"), hctx = haloCanvas.getContext("2d");
let world = null;
function ensureWorld() {
  if (!world) {
    world = new World(worldCanvas, cfg);
    world.onBump = (p) => { if (state.log) state.log.bumps.push({ t: state.log.clock(), label: p.userData.label || "obstacle" }); audio.haptic(30); };
    world.onRailEnd = () => { if (!state.trust) setHint("End of the route. Pick another place, or go by ear."); };
  }
  return world;
}
let escape = null;
function setDescribe(on) { cfg.describe = on; $("describeBtn").classList.toggle("on", on); $("describeBtn").setAttribute("aria-pressed", on); }
function loadScene(id, { shuffle = 0 } = {}) {
  ensureWorld();
  const wasEscape = !!state.escape;
  state.scene = id;
  const def = SCENES[id]({ shuffle });
  if (def.escape && !wasEscape) { state.escape = { prevMode: state.mode, prevDescribe: cfg.describe }; state.mode = "free"; }
  if (!def.escape && wasEscape) { state.mode = state.escape.prevMode; setDescribe(state.escape.prevDescribe); state.escape = null; if (escape) escape.stop(); }
  world.load(def); world.setMode(state.mode);
  pipeline.reset(); replayPipeline.reset();
  state.worldReady = true;
  $("sceneTitle").textContent = def.title;
  $("leftLabel").textContent = def.escape ? "Your eyes, low vision" : "Sighted";
  $("walk").classList.toggle("escape", !!def.escape);
  $("guideBtn").disabled = !!def.escape; $("trustBtn").disabled = !!def.escape;
  $("guideBtn").classList.toggle("on", state.mode === "guide"); $("guideBtn").setAttribute("aria-pressed", state.mode === "guide");
  document.querySelectorAll("#sceneChips button").forEach(b => b.classList.toggle("on", b.dataset.scene === id));
  if (def.escape) {
    setDescribe(true);   // the Halo names each new thing it sees: that is how the keys are found
    if (!escape) escape = new Escape({ world, speech, ui: { panel: $("escPanel"), list: $("escList"), clock: $("escClock"), card: $("escCard"), cardTime: $("escTime"), cardLine: $("escLine") } });
    escape.start(def);
    setHint("Left thumb walks. Right thumb looks. Face a thing up close to pick it up.", 6000);
  } else setHint(state.mode === "guide" ? "Hold left to walk. Drag right to look." : "Left thumb walks. Right thumb looks.");
  hood.setScene(def);
}
$("escAgain").addEventListener("click", () => { audio.prewarm(); loadScene("escape"); });
$("escBack").addEventListener("click", () => loadScene("home"));
document.querySelectorAll("#sceneChips button").forEach(b => b.addEventListener("click", () => loadScene(b.dataset.scene)));

let hintTimer = 0;
function setHint(t, ms = 4000) { const h = $("walkHint"); h.textContent = t; h.style.opacity = 1; clearTimeout(hintTimer); hintTimer = setTimeout(() => h.style.opacity = 0, ms); }

function resizePanes() {
  const L = $("paneLeft"), R = $("paneRight");
  const lw = L.clientWidth, lh = L.clientHeight;
  if (world && lw && lh) world.resize(lw, lh);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  haloCanvas.width = Math.round(R.clientWidth * dpr); haloCanvas.height = Math.round(R.clientHeight * dpr);
}
window.addEventListener("resize", () => { if (state.room === "walk") resizePanes(); });

$("guideBtn").addEventListener("click", () => {
  state.mode = state.mode === "guide" ? "free" : "guide";
  $("guideBtn").classList.toggle("on", state.mode === "guide"); $("guideBtn").setAttribute("aria-pressed", state.mode === "guide");
  if (world) world.setMode(state.mode);
  setHint(state.mode === "guide" ? "Hold left to follow the route." : "Left thumb walks. Right thumb looks.");
});
$("describeBtn").addEventListener("click", () => { setDescribe(!cfg.describe); speech.say(cfg.describe ? "Describe mode on" : "Describe mode off", Priority.INFO, false, 3); });
$("sceneBtn").addEventListener("click", () => pipeline.speakScene());
$("muteBtn").addEventListener("click", toggleMute);
function toggleMute() { const m = speech.toggleMute(); $("muteBtn").setAttribute("aria-pressed", m); $("muteBtn").setAttribute("aria-label", m ? "Sound off" : "Sound on"); $("muteBtn").classList.toggle("on", m); if (!m) speech.say("Audio unmuted", Priority.INFO, false, 2); }

// SOS
$("sosBtn").addEventListener("click", () => {
  $("sos").hidden = false; state.sosSent = true;
  const p = world ? world.getPose() : { x: 0, z: 0 };
  $("sosLine").textContent = `SENT ${new Date().toLocaleTimeString([], { hour12: false })} · 25.2048 N, 55.2708 E`;
  speech.say("SOS sent. Your location has been shared with your contact.", Priority.CRITICAL, true, 6);
  setTimeout(() => { $("sosLine").textContent += " · SEEN BY YOUR CONTACT"; }, 3500);
});
$("sosClose").addEventListener("click", () => $("sos").hidden = true);

// ---- input: joystick / hold / look / gestures
const inputState = { pointers: new Map(), maxPointers: 0, downAt: 0, moved: false, longTimer: 0, joyId: null, joyOrigin: null, lookId: null, lastLook: null };
function attachWalkInput(el, side) {
  el.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button, .escape-card")) return;   // the result card's buttons take their own taps
    audio.prewarm(); el.setPointerCapture(e.pointerId);
    inputState.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, side });
    if (inputState.pointers.size === 1) { inputState.downAt = performance.now(); inputState.moved = false; inputState.maxPointers = 0;
      if (side === "right") inputState.longTimer = setTimeout(() => { if (!inputState.moved && inputState.pointers.size === 1) { toggleMute(); inputState.longFired = true; } }, 650); }
    inputState.maxPointers = Math.max(inputState.maxPointers, inputState.pointers.size);
    if (!world) return;
    if (side === "left" && inputState.joyId == null) {
      inputState.joyId = e.pointerId;
      if (state.mode === "guide" && !state.trust) world.input.hold = true;
      else { inputState.joyOrigin = { x: e.clientX, y: e.clientY }; const j = $("joy"); const r = el.getBoundingClientRect(); j.style.left = (e.clientX - r.left) + "px"; j.style.top = (e.clientY - r.top) + "px"; if (!state.trust) j.classList.add("show"); }
    } else if (inputState.lookId == null) { inputState.lookId = e.pointerId; inputState.lastLook = { x: e.clientX, y: e.clientY }; }
  });
  el.addEventListener("pointermove", (e) => {
    const p = inputState.pointers.get(e.pointerId); if (!p) return;
    if (Math.hypot(e.clientX - p.x, e.clientY - p.y) > 12) inputState.moved = true;
    if (!world) return;
    if (e.pointerId === inputState.joyId && inputState.joyOrigin) {
      const dx = e.clientX - inputState.joyOrigin.x, dy = e.clientY - inputState.joyOrigin.y, m = Math.hypot(dx, dy), R = 50;
      const k = m > R ? R / m : 1;
      world.input.jx = dx * k / R; world.input.jy = dy * k / R;
      $("joy").querySelector(".knob").style.transform = `translate(calc(-50% + ${dx * k}px), calc(-50% + ${dy * k}px))`;
    } else if (e.pointerId === inputState.lookId) {
      world.input.dx += e.clientX - inputState.lastLook.x; world.input.dy += e.clientY - inputState.lastLook.y;
      inputState.lastLook = { x: e.clientX, y: e.clientY };
    }
  });
  const up = (e) => {
    if (!inputState.pointers.has(e.pointerId)) return;
    inputState.pointers.delete(e.pointerId);
    if (e.pointerId === inputState.joyId) { inputState.joyId = null; inputState.joyOrigin = null; if (world) { world.input.hold = false; world.input.jx = 0; world.input.jy = 0; } $("joy").classList.remove("show"); $("joy").querySelector(".knob").style.transform = "translate(-50%,-50%)"; }
    if (e.pointerId === inputState.lookId) inputState.lookId = null;
    if (inputState.pointers.size === 0) {
      clearTimeout(inputState.longTimer);
      const dur = performance.now() - inputState.downAt;
      if (!inputState.moved && dur < 450 && !inputState.longFired) {
        if (inputState.maxPointers === 2) pipeline.speakScene();
        else if (inputState.maxPointers === 3) $("describeBtn").click();
        else if (inputState.maxPointers >= 4) showRoom("hood");
      }
      inputState.longFired = false;
    }
  };
  el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
}
attachWalkInput($("paneLeft"), "left"); attachWalkInput($("paneRight"), "right");
// keyboard, for a laptop
const keys = new Set();
const typing = (e) => { const t = e.target; return t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable); };
window.addEventListener("keydown", (e) => {
  if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
  if (state.room !== "walk" && state.room !== "hood") return;
  keys.add(e.key.toLowerCase());
  if (e.key === "s") pipeline.speakScene(); if (e.key === "m") toggleMute();
});
window.addEventListener("keyup", (e) => keys.delete(e.key.toLowerCase()));
window.addEventListener("blur", () => keys.clear());
function applyKeys() {
  if (!world || (state.room !== "walk" && state.room !== "hood")) return;
  const f = (keys.has("w") || keys.has("arrowup")) ? -1 : (keys.has("s") && false) ? 1 : (keys.has("arrowdown") ? 1 : 0);
  const s = (keys.has("d") || keys.has("arrowright")) ? 1 : (keys.has("a") || keys.has("arrowleft")) ? -1 : 0;
  if (f || s) { if (state.mode === "guide" && !state.trust) world.input.hold = f < 0; else { world.input.jy = f; world.input.jx = s * 0.6; } }
  else if (!inputState.joyId) { world.input.hold = false; if (!inputState.joyOrigin) { world.input.jx = 0; world.input.jy = 0; } }
  if (keys.has("q")) world.input.dx -= 6; if (keys.has("e")) world.input.dx += 6;
}

// ---- main loop
let lastT = 0;
function frame(ts) {
  requestAnimationFrame(frame);
  const now = ts / 1000; const dt = Math.min(0.05, lastT ? now - lastT : 0.016); lastT = now;
  if ((state.room !== "walk" && state.room !== "hood") || !world || !state.worldReady) return;
  applyKeys();
  if (state.replay) { renderReplay(); return; }
  world.update(dt, now);
  if (escape && escape.active) escape.update(dt);
  const l = world.lidar(); pipeline.pushLidar(l.cm, l.strength, now);
  const dets = world.detect(now);
  pipeline.step(dets, now);
  world.render();
  drawHaloPane(pipeline);
  if (state.log) {
    const L = state.log; const t = L.clock();
    if (t - L.lastPose >= 0.1) { L.lastPose = t; const p = world.getPose(); L.poses.push({ t, ...p, wt: world.t, level: pipeline.hazard.level }); }
    if (state.trust && (world.atGoal() || t > 90)) finishTrust("You reached the door.");
  }
  hood.setDashboard({ fps: pipeline.fps, lidar: pipeline.lidarSample, raw: l, tracks: pipeline.tracks, hazard: pipeline.hazard, speech, cfg, pose: world.getPose() });
}
requestAnimationFrame(frame);

const blurA = document.createElement("canvas"), blurB = document.createElement("canvas");
/** Low vision without ctx.filter (Safari has none): shrink twice, stretch back with smoothing. */
function drawBlurred(ctx, src, W, H) {
  blurA.width = Math.max(8, Math.round(W / 4)); blurA.height = Math.max(6, Math.round(H / 4));
  blurB.width = Math.max(4, Math.round(W / 22)); blurB.height = Math.max(3, Math.round(H / 22));
  const a = blurA.getContext("2d"), b = blurB.getContext("2d");
  a.imageSmoothingQuality = b.imageSmoothingQuality = ctx.imageSmoothingQuality = "high";
  a.drawImage(src, 0, 0, blurA.width, blurA.height); b.drawImage(blurA, 0, 0, blurB.width, blurB.height);
  a.drawImage(blurB, 0, 0, blurA.width, blurA.height); ctx.drawImage(blurA, 0, 0, W, H);
}
function drawHaloPane(pl) {
  const W = haloCanvas.width, H = haloCanvas.height;
  hctx.save();
  if (state.escape) {
    drawBlurred(hctx, worldCanvas, W, H);
    hctx.fillStyle = "rgba(0,0,0,0.12)"; hctx.fillRect(0, 0, W, H);
  } else {
    hctx.drawImage(worldCanvas, 0, 0, W, H);
    hctx.globalCompositeOperation = "saturation"; hctx.fillStyle = "#808080"; hctx.fillRect(0, 0, W, H);
    hctx.globalCompositeOperation = "multiply"; hctx.fillStyle = "#b4b4b4"; hctx.fillRect(0, 0, W, H);
  }
  hctx.globalCompositeOperation = "source-over";
  const dpr = W / $("paneRight").clientWidth;
  hctx.scale(dpr, dpr);
  drawOverlay(hctx, W / dpr, H / dpr, { tracks: pl.tracks, hazard: pl.hazard, lidarSample: pl.lidarSample, speech: pl.speech, cfg, fps: pl.fps }, { haptics: state.haptics });
  hctx.restore();
}

// ------------------------------------------------------------------ TRUST (by ear) + REPLAY
function newLog() { const t0 = performance.now() / 1000; return { t0, clock: () => performance.now() / 1000 - t0, poses: [], speech: [], bumps: [], lastPose: -1 }; }
$("trustBtn").addEventListener("click", startTrust);
function startTrust() {
  audio.prewarm();
  state.trust = true; state.log = newLog();
  const prevMode = state.mode; state.mode = "free"; $("guideBtn").classList.remove("on");
  loadScene(state.scene, { shuffle: Math.floor(Math.random() * 1e6) + 1 });
  state._prevMode = prevMode;
  $("blackout").hidden = false; $("replay").hidden = true;
  $("blackoutText").textContent = "Screen off. Find the door at the far end by sound.";
  speech.say("By ear. Find the door.", Priority.INFO, false, 6);
}
$("finishTrust").addEventListener("click", () => finishTrust("You stopped here."));
function finishTrust(reason) {
  if (!state.trust) return;
  state.trust = false; $("blackout").hidden = true;
  const L = state.log; state.log = null;
  state.mode = state._prevMode || "guide"; $("guideBtn").classList.toggle("on", state.mode === "guide"); world.setMode(state.mode);
  openReplay(L, reason);
}
function openReplay(L, reason) {
  if (!L.poses.length) return;
  state.replay = { log: L, idx: 0 };
  world.frozen = true;
  const dur = L.poses[L.poses.length - 1].t;
  const crit = L.speech.filter(s => s.prio === Priority.CRITICAL).length;
  $("replaySummary").textContent = `${reason} ${Math.round(dur)} s by ear · ${L.speech.length} messages, ${crit} critical · ${L.bumps.length} contact${L.bumps.length === 1 ? "" : "s"}. Scrub to see what the Halo saw.`;
  const tl = $("timeline"); tl.innerHTML = "";
  const items = [...L.speech.map(s => ({ ...s, kind: "speech" })), ...L.bumps.map(b => ({ ...b, kind: "bump" }))].sort((a, b) => a.t - b.t);
  for (const it of items) {
    const li = document.createElement("li"); li.dataset.t = it.t;
    if (it.kind === "bump") { li.className = "bump"; li.innerHTML = `<span class="t">${it.t.toFixed(1)}s</span>contact with ${it.label}`; }
    else { li.className = it.prio === 0 ? "crit" : it.prio === 1 ? "warn" : ""; li.innerHTML = `<span class="t">${it.t.toFixed(1)}s</span><b>${priorityName(it.prio)}</b> ${it.text}`; }
    li.addEventListener("click", () => { $("scrub").value = Math.round(it.t / dur * 1000); syncRange($("scrub")); });
    tl.appendChild(li);
  }
  $("scrub").value = 0; syncRange($("scrub")); $("replay").hidden = false;
  replayPipeline.reset();
}
function renderReplay() {
  const R = state.replay, L = R.log; const dur = L.poses[L.poses.length - 1].t;
  const t = (+$("scrub").value / 1000) * dur;
  let i = 0; while (i < L.poses.length - 1 && L.poses[i + 1].t <= t) i++;
  const p = L.poses[i];
  world.updateActors(p.wt); world.setPose(p.x, p.z, p.yaw, p.pitch);
  const now = performance.now() / 1000;
  const l = world.lidar(); replayPipeline.pushLidar(l.cm, l.strength, now);
  replayPipeline.step(world.detect(now), now);
  world.render(); drawHaloPane(replayPipeline);
  document.querySelectorAll("#timeline li").forEach(li => li.classList.toggle("cur", Math.abs(+li.dataset.t - t) < 1.2));
}
$("replayClose").addEventListener("click", () => { state.replay = null; world.frozen = false; $("replay").hidden = true; loadScene(state.scene); });

// ------------------------------------------------------------------ SETTINGS
const bind = (id, label, key, scale = 1, fmt = v => v) => {
  $(id).addEventListener("input", e => { const v = +e.target.value * scale; cfg[key] = v; $(label).textContent = fmt(v); });
};
bind("sCritical", "vCritical", "criticalCm"); bind("sWarning", "vWarning", "warningCm");
bind("sRepeat", "vRepeat", "criticalRepeatS", 0.1, v => v.toFixed(1)); bind("sThreshold", "vThreshold", "scoreThreshold", 0.01, v => v.toFixed(2));
bind("sOffset", "vOffset", "lidarOffsetXCm");
$("sBeep").addEventListener("change", e => cfg.beep = e.target.checked);
$("sHaptic").addEventListener("change", e => state.haptics = e.target.checked);
// vision model key (kept on this device only)
function keyState() { const k = ai.getKey(); $("sKeyState").textContent = k ? `Key saved on this device (…${k.slice(-4)}).` : "No key. Questions are answered from the on-device detector only."; if (live) live.refreshKey(); }
$("sKey").value = ai.getKey(); keyState();
$("sKey").addEventListener("change", e => { ai.setKey(e.target.value); keyState(); });
$("sKey").addEventListener("input", e => { if (!e.target.value) { ai.setKey(""); keyState(); } });
$("sModel").value = ai.getModel() === ai.MODEL_CHAIN[0] ? "" : ai.getModel();
$("sModel").addEventListener("change", e => ai.setModel(e.target.value));
function openSettings(open) { $("settings").hidden = !open; $("scrim").hidden = !open; }
$("settingsBtn").addEventListener("click", () => openSettings($("settings").hidden));
$("settingsClose").addEventListener("click", () => openSettings(false));
$("scrim").addEventListener("click", () => openSettings(false));
// range tracks fill to their value
export function syncRange(r) { const min = +r.min || 0, max = +r.max || 100; r.style.setProperty("--p", `${((+r.value - min) / (max - min) * 100).toFixed(1)}%`); }
document.querySelectorAll("input[type=range]").forEach(r => { r.addEventListener("input", () => syncRange(r)); syncRange(r); });
$("hoodOpen").addEventListener("click", () => { openSettings(false); showRoom("hood"); });
$("hoodClose").addEventListener("click", () => showRoom("walk"));

// iOS zooms the page on a two-finger gesture whatever the viewport says; the reader owns the pinch
document.addEventListener("gesturestart", e => e.preventDefault(), { passive: false });
document.addEventListener("dblclick", e => { if (!/^(INPUT|TEXTAREA|BUTTON|A)$/.test(e.target.tagName)) e.preventDefault(); }, { passive: false });

// ------------------------------------------------------------------ boot
showRoom("start");
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.register("sw.js").catch(() => {});
  // a new deploy takes over: reload on the Start screen, never in the middle of a walk or a reading
  let pendingReload = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => { if (!hadController) return; if (state.room === "start" && !document.hidden) location.reload(); else pendingReload = true; });
  document.querySelectorAll("[data-room='start']").forEach(b => b.addEventListener("click", () => { if (pendingReload) setTimeout(() => location.reload(), 50); }));
}
window.__vantage = { cfg, state, speech, pipeline, get world() { return world; }, get live() { return live; }, get escape() { return escape; }, loadScene, showRoom };
