// lang.js — which language the Halo speaks: "en" or "ar". Kept on this device; a link can
// carry ?lang=ar (the take-home QR does). Only the voice and the answers change: the
// screens stay in English for the people standing around the visitor.
const STORE = "vantage.lang";
const listeners = new Set();
let cur = "en";
try {
  const q = new URLSearchParams(location.search).get("lang");
  cur = (q === "ar" || q === "en") ? q : (localStorage.getItem(STORE) || "en");
  if (q) localStorage.setItem(STORE, cur);
} catch (_) {}
export const getLang = () => cur;
export const isAr = () => cur === "ar";
export function setLang(l) { cur = l === "ar" ? "ar" : "en"; try { localStorage.setItem(STORE, cur); } catch (_) {} listeners.forEach(f => f(cur)); }
export function onLang(f) { listeners.add(f); return () => listeners.delete(f); }
/** Pick the string for the current language. */
export const tr = (en, ar) => (cur === "ar" ? ar : en);
