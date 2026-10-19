// ai.js — "Ask the Halo": a question about the camera frame, answered by a vision model.
// Provider: Google Gemini on its free tier, called straight from the browser with the
// visitor's key (stored only on this device). Without a key the local fallback answers
// from what the on-device detector and reader can see.
import { spokenLabel, spokenDistance, directionOf } from "./halo.js";
import { arLabel, arDirection, at, count } from "./arabic.js";

const KEY_STORE = "vantage.gemini.key", MODEL_STORE = "vantage.gemini.model";
// Free-tier Gemini models, best first. Flash-Lite models carry a usable daily quota on the
// free tier; the bigger Flash models are capped at a handful of requests a day. Model ids
// move fast, so the first one can be overridden in Settings and each failure falls through.
export const MODEL_CHAIN = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"];

export function getKey() {
  try {
    const q = new URLSearchParams(location.search);
    if (q.get("key")) { localStorage.setItem(KEY_STORE, q.get("key")); if (q.get("model")) localStorage.setItem(MODEL_STORE, q.get("model")); history.replaceState(null, "", location.pathname + location.hash); }
    return localStorage.getItem(KEY_STORE) || "";
  } catch (_) { return ""; }
}
export function setKey(k) { try { if (k) localStorage.setItem(KEY_STORE, k.trim()); else localStorage.removeItem(KEY_STORE); } catch (_) {} }
export function getModel() { try { return localStorage.getItem(MODEL_STORE) || MODEL_CHAIN[0]; } catch (_) { return MODEL_CHAIN[0]; } }
export function setModel(m) { try { if (m && m.trim()) localStorage.setItem(MODEL_STORE, m.trim()); else localStorage.removeItem(MODEL_STORE); } catch (_) {} }

/** The questions on the chip rail. `local` names the on-device answer when there is no key. */
export const QUESTIONS = [
  { id: "ahead", text: "What's in front of me?", ar: "ماذا يوجد أمامي؟", local: "scene" },
  { id: "clear", text: "Is the way clear?", ar: "هل الطريق خالٍ؟", local: "clear" },
  { id: "read", text: "Read this to me", ar: "اقرأ لي هذا", local: "read", mode: "read" },
  { id: "sign", text: "What does the sign say?", ar: "ماذا تقول اللافتة؟", local: "read", detail: true },
  { id: "people", text: "How many people are here?", ar: "كم شخصًا هنا؟", local: "people" },
  { id: "where", text: "Where am I?", ar: "أين أنا؟", local: "scene" },
  { id: "door", text: "Where is the door?", ar: "أين الباب؟", local: null },
  { id: "menu", text: "What's on the menu?", ar: "ماذا في قائمة الطعام؟", local: "read", detail: true },
  { id: "product", text: "What is this product?", ar: "ما هذا المنتج؟", local: "read", detail: true },
  { id: "colour", text: "What colour is this?", ar: "ما لون هذا؟", local: null },
];

const SYSTEM = `You are the voice of the Vantage Halo, a head-worn assistant for a blind person. You are looking through the Halo's camera at what is in front of them right now.
Answer in one or two short spoken sentences, plain words, no lists, no markdown, no preamble. Use "ahead", "on your left", "on your right", "above", "at your feet". Give rough distances in metres when they matter. Mention hazards first: steps, kerbs, vehicles, people moving toward them, things at head height. If you cannot tell, say so briefly and suggest one small action (turn slightly left, move closer).
When asked to read, read the text exactly as printed, in reading order, skipping decoration; for a menu read item and price; for a medicine box read the name, strength and the dose instructions. Never guess text you cannot see.`;

// The Arabic voice: Modern Standard Arabic as a native speaker says it aloud, not a word-for-word translation
const SYSTEM_AR = `
Answer in Modern Standard Arabic (الفصحى المبسطة), as an educated native speaker from the Gulf would say it aloud: natural, simple and grammatically correct, with correct number and gender agreement. Do not translate word for word from English.
Write numbers and distances as Arabic words with the correct counted-noun form, for example: على بُعد متر، على بُعد مترين، على بُعد ثلاثة أمتار، على بُعد خمسين سنتيمترًا. Use أمامك، على يسارك، على يمينك، فوقك، عند قدميك.
Do not assume the listener is male or female: prefer verbal nouns and يُرجى over imperatives.
Use no English words. Write brand and medicine names the way they are usually written in Arabic (باراسيتامول، بنادول). Prices in dirhams: ثمانية عشر درهمًا. No diacritics except where a word would otherwise be misread, and always write بُعد with its damma.
When asked to read: text printed in Arabic is read exactly as printed; text printed in English or another language is given as a faithful Arabic translation, keeping its order and every number, dose and warning.`;

function isGemini3(model) { return /gemini-(3|4)/.test(model); }
function buildBody({ question, frame, context, model, variant, detail, lang = "en" }) {
  const parts = [];
  parts.push({ text: (context ? `On-device detector right now: ${context}.\n` : "") + `Question: ${question}` });
  if (frame) parts.push({ inline_data: { mime_type: "image/jpeg", data: frame.b64 } });
  const gen = { maxOutputTokens: 1024, temperature: 0.2 };
  // variant 0: full config; 1: without media resolution; 2: thinking "low"; 3: bare
  if (variant < 3) {
    if (isGemini3(model)) gen.thinkingConfig = { thinkingLevel: variant >= 2 ? "low" : "minimal" };
    else gen.thinkingConfig = { thinkingBudget: 0 };
    if (variant < 1) gen.mediaResolution = detail ? "MEDIA_RESOLUTION_MEDIUM" : "MEDIA_RESOLUTION_LOW";
  }
  return { system_instruction: { parts: [{ text: lang === "ar" ? SYSTEM + SYSTEM_AR : SYSTEM }] }, contents: [{ role: "user", parts }], generationConfig: gen };
}

/** One call to one model. Retries the request shape on a 400 (config fields the model rejects). */
export async function askModel({ key, question, frame, context, model, detail = false, signal, lang = "en" }) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  const t0 = performance.now(); let lastErr = null;
  for (let variant = 0; variant < 4; variant++) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": key }, body: JSON.stringify(buildBody({ question, frame, context, model, variant, detail, lang })), signal });
    if (!res.ok) {
      let msg = `${res.status}`; try { const j = await res.json(); msg = (j.error && j.error.message) || msg; } catch (_) {}
      const err = new Error(msg); err.status = res.status; err.model = model; lastErr = err;
      if (res.status === 400 && !/API key|api_key|permission|quota/i.test(msg)) continue;   // shape rejected: simplify and try again
      throw err;
    }
    const j = await res.json();
    if (j.promptFeedback && j.promptFeedback.blockReason) { const err = new Error(`Blocked: ${j.promptFeedback.blockReason}`); err.status = 0; throw err; }
    const cand = j.candidates && j.candidates[0];
    const text = cand && cand.content && cand.content.parts ? cand.content.parts.filter(p => !p.thought && p.text).map(p => p.text).join("").trim() : "";
    if (!text) { const err = new Error(cand && cand.finishReason ? `No answer (${cand.finishReason})` : "No answer"); err.status = 0; throw err; }
    return { text: text.replace(/[^\S\n]+/g, " ").replace(/ ?\n ?/g, "\n").replace(/\n{2,}/g, "\n").trim(), ms: performance.now() - t0, model };
  }
  throw lastErr || new Error("Request rejected");
}

/** Ask, walking down the model chain when a model is missing, exhausted or unavailable. */
export async function ask(opts) {
  const chain = [getModel(), ...MODEL_CHAIN.filter(m => m !== getModel())];
  let lastErr = null;
  for (const model of chain) {
    try { return await askModel({ ...opts, model }); }
    catch (e) {
      lastErr = e;
      if (/API key|api_key|permission|PERMISSION_DENIED/i.test(e.message) || e.status === 401 || e.status === 403) throw e;   // the key is the problem, not the model
      if (e.status === 429 || e.status === 404 || e.status === 503 || e.status === 400) continue;
      throw e;
    }
  }
  throw lastErr;
}

export function explainError(e) {
  if (!e) return "unknown error";
  if (e.name === "TimeoutError" || e.name === "AbortError") return "the model took too long";
  if (e.status === 429) return /day|daily|RPD|per day/i.test(e.message) ? "today's free quota is used up" : "the free tier is busy, try again in a moment";
  if (e.status === 403 || e.status === 401 || /API key/i.test(e.message)) return "the key was rejected";
  if (e.status === 404) return "the model id is not available to this key";
  if (e.name === "TypeError") return "no network";
  return e.message.length > 80 ? e.message.slice(0, 80) + "…" : e.message;
}

/** What the detector sees, as one line of context for the model, and as a spoken sentence. */
export function describeDetections(tracks, hazard, frameW) {
  if (!tracks.length) return { line: "nothing recognised", spoken: "Nothing recognised in front of you." };
  // group the same thing in the same direction: "two people on your left, about 2 meters"
  const groups = new Map();
  for (const t of [...tracks].sort((a, b) => (a.rangeCm ?? 9e9) - (b.rangeCm ?? 9e9))) {
    const key = `${t.label}|${directionOf(t.center[0], frameW)}`;
    const g = groups.get(key) || { label: t.label, dir: directionOf(t.center[0], frameW), n: 0, near: null };
    g.n++; if (g.near == null && t.rangeCm != null) g.near = t.rangeCm; groups.set(key, g);
  }
  const WORDS = ["", "one", "two", "three", "four", "five", "six"];
  const items = [...groups.values()].slice(0, 5).map(g => {
    const name = spokenLabel(g.label); const plural = g.label === "person" ? "people" : name + (/s$/.test(name) ? "" : "s");
    const count = g.n === 1 ? `${/^[aeiou]/i.test(name) ? "an" : "a"} ${name}` : `${WORDS[g.n] || g.n} ${plural}`;
    const d = g.near != null ? `, about ${spokenDistance(g.near)}` : "";
    return `${count} ${g.dir}${d}`;
  });
  const line = items.join("; ");
  const joined = items.length === 1 ? items[0] : `${items.slice(0, -1).join("; ")}; and ${items[items.length - 1]}`;
  const spoken = `${joined[0].toUpperCase()}${joined.slice(1)}.`;
  return { line, spoken };
}

/** The same, spoken in Arabic: each thing on its own ("كرسي على يسارك، على بُعد مترين تقريبًا"). */
function arScene(tracks, frameW) {
  if (!tracks.length) return "لا شيء أمامك.";
  const items = [...tracks].sort((a, b) => (a.rangeCm ?? 9e9) - (b.rangeCm ?? 9e9)).slice(0, 4)
    .map(t => `${arLabel(t.label)} ${arDirection(directionOf(t.center[0], frameW))}` + (t.rangeCm != null ? ` ${at(t.rangeCm)} تقريبًا` : ""));
  return items.join("، و") + ".";
}
function arLocal(kind, { tracks, hazard, frameW }) {
  if (kind === "scene") return arScene(tracks, frameW);
  if (kind === "people") {
    const ppl = tracks.filter(t => t.label === "person"), n = ppl.length;
    if (!n) return "لا أحد أمامك.";
    const near = ppl.map(t => t.rangeCm).filter(v => v != null).sort((a, b) => a - b)[0];
    const head = n === 1 ? "شخص واحد أمامك" : n === 2 ? "شخصان أمامك" : `أمامك ${count(n, "person", "nom")}`;
    const tail = near == null ? "" : n === 1 ? `، ${at(near)} تقريبًا` : `، ${n === 2 ? "أقربهما" : "أقربهم"} ${at(near)} تقريبًا`;
    return head + tail + ".";
  }
  if (kind === "clear") {
    if (!hazard || hazard.level <= 0) return tracks.length ? `لا شيء قريب أمامك. ${arScene(tracks, frameW)}` : "لا شيء قريب أمامك.";
    const name = hazard.target ? arLabel(hazard.target.label) : "عائق";
    return `ليس تمامًا. ${name} أمامك${hazard.distanceCm != null ? `، ${at(hazard.distanceCm)} تقريبًا` : ""}.`;
  }
  return null;
}

/** Answer without a key, from the detector / hazard / reader. Returns null when it cannot. */
export function localAnswer(q, { tracks, hazard, frameW, cfg, lang = "en" }) {
  const kind = typeof q === "string" ? q : q.local;
  if (lang === "ar") return arLocal(kind, { tracks, hazard, frameW });
  if (kind === "scene") return describeDetections(tracks, hazard, frameW).spoken;
  if (kind === "people") {
    const n = tracks.filter(t => t.label === "person").length;
    if (!n) return "No one in front of you.";
    const near = tracks.filter(t => t.label === "person").map(t => t.rangeCm).filter(v => v != null).sort((a, b) => a - b)[0];
    return `${n === 1 ? "One person" : n + " people"} in front of you${near != null ? `, the nearest about ${spokenDistance(near)}` : ""}.`;
  }
  if (kind === "clear") {
    if (!hazard || hazard.level <= 0) return tracks.length ? "Nothing close ahead. " + describeDetections(tracks, hazard, frameW).spoken : "Nothing close ahead.";
    const name = hazard.target ? spokenLabel(hazard.target.label) : "something";
    return `Not quite. ${name[0].toUpperCase() + name.slice(1)} ahead${hazard.distanceCm != null ? `, about ${spokenDistance(hazard.distanceCm)}` : ""}.`;
  }
  return null;
}
