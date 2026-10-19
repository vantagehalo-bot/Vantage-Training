// audio.js — the headset side: the firmware's two-tone beep, the reader's click,
// speech through the Web Speech API, and a haptic pulse where the device has one.

let ctx = null;
function ac() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state !== "running") ctx.resume().catch(() => {});   // "suspended", and iOS's "interrupted" after a call or Siri
  return ctx;
}

/** Two short rising tones (880 Hz 90 ms, 40 ms gap, 1320 Hz 120 ms) after 150 ms of
 *  silence, exactly as _write_beep() in vantage_core.py. Returns a cancel function. */
export function beep(onEnd) {
  const c = ac(); const t0 = c.currentTime + 0.15;
  const parts = [[880, 0.09], [0, 0.04], [1320, 0.12]];
  let t = t0; const nodes = [];
  for (const [f, dur] of parts) {
    if (f) {
      const o = c.createOscillator(), g = c.createGain();
      o.frequency.value = f; o.type = "sine";
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.8, t + 0.01);
      g.gain.setValueAtTime(0.8, t + dur - 0.01); g.gain.linearRampToValueAtTime(0, t + dur);
      o.connect(g).connect(c.destination); o.start(t); o.stop(t + dur); nodes.push(o);
    }
    t += dur;
  }
  haptic([60, 40, 90]);
  const timer = setTimeout(() => onEnd && onEnd(), (t - c.currentTime) * 1000 + 20);
  return () => { clearTimeout(timer); nodes.forEach(n => { try { n.stop(); } catch (_) {} }); };
}

/** The reader's soft capture click (short filtered noise burst). */
export function click() {
  const c = ac(); const dur = 0.03; const buf = c.createBuffer(1, c.sampleRate * dur, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
  const src = c.createBufferSource(); src.buffer = buf;
  const f = c.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = 2500; f.Q.value = 1.2;
  const g = c.createGain(); g.gain.value = 0.5;
  src.connect(f).connect(g).connect(c.destination); src.start();
  haptic(15);
}

export function haptic(pattern) {
  try { if (navigator.vibrate) navigator.vibrate(pattern); } catch (_) {}
}

// ------------------------------------------------------------------ speech

const tts = {
  voice: null, wpm: 175, volume: 1, warmed: false,
};

export function listVoices() {
  const vs = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  const en = vs.filter(v => /^en/i.test(v.lang));
  return (en.length ? en : vs);
}
export function setVoice(v) { tts.voice = v; }
export function setRateWpm(wpm) { tts.wpm = wpm; }
export function getRateWpm() { return tts.wpm; }

/** First-word clipping on Bluetooth is covered by the beep's leading silence in the
 *  firmware. Here, saying an empty utterance on the first tap wakes the engine. */
export function prewarm() {
  try { ac(); } catch (_) {}
  if (tts.warmed || !window.speechSynthesis) return;
  tts.warmed = true;
  // iOS lifts its gesture rule for the page the first time speak() runs inside a tap, so this must stay synchronous
  try { const u = new SpeechSynthesisUtterance("."); u.volume = 0.01; u.rate = 2; speechSynthesis.speak(u); } catch (_) {}
}
// iOS suspends audio when the page is hidden; bring the context back when it returns
document.addEventListener("visibilitychange", () => { if (!document.hidden && ctx && ctx.state !== "running") { try { ctx.resume().catch(() => {}); } catch (_) {} } });

/** Speak text; returns a cancel function. onEnd fires once, on end or cancel. */
let lastCancel = 0;
export function speak(text, onEnd) {
  if (!window.speechSynthesis) { const t = setTimeout(onEnd, 400 + 50 * text.length); return () => clearTimeout(t); }
  let done = false, started = false, u = null, startTimer = 0, watchdog = 0, delay = 0;
  const finish = () => { if (!done) { done = true; clearTimeout(startTimer); clearTimeout(watchdog); clearTimeout(delay); onEnd && onEnd(); } };
  const go = () => {
    if (done) return;
    u = new SpeechSynthesisUtterance(text);
    if (tts.voice) { u.voice = tts.voice; u.lang = tts.voice.lang || "en-US"; } else u.lang = "en-US";
    u.rate = Math.max(0.7, Math.min(1.4, tts.wpm / 160));   // engine rate 1 ≈ 160 wpm; iOS maps outside 0.9–1.15 poorly
    u.volume = tts.volume;
    u.onstart = () => { started = true; };
    u.onend = finish; u.onerror = finish;
    // Some engines never fire onend after cancel(), and a muted iPhone can report speaking without a start: two watchdogs
    // (the first scaled to the rate: 70 ms a character at 160 wpm, with a margin for a slow engine)
    watchdog = setTimeout(finish, 1500 + 70 * text.length * (160 / tts.wpm) * 1.5);
    startTimer = setTimeout(() => { if (!started) finish(); }, 4000);
    speechSynthesis.speak(u);
  };
  // Safari ≤ 26 can drop an utterance queued right after cancel(); leave a short gap
  const wait = 150 - (performance.now() - lastCancel);
  if (wait > 0) delay = setTimeout(go, wait); else go();
  return () => { try { speechSynthesis.cancel(); lastCancel = performance.now(); } catch (_) {} finish(); };
}

export function isSpeaking() { return !!(window.speechSynthesis && speechSynthesis.speaking); }

export const backend = { speak, beep, isSpeaking };
