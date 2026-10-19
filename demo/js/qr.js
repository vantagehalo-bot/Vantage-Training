// qr.js — the take-home code. Encodes the public demo URL opened straight into the Live
// room, in English or with the Arabic voice. Never carries the vision key: that stays on
// the booth tablet.
import qrcode from "../vendor/qrcode/qrcode.mjs";

export const CANONICAL = "https://vantagehalo-bot.github.io/Vantage-Training/";
/** The public page's base URL: this one when served from GitHub Pages, the canonical one otherwise. */
export function baseUrl() {
  try { if (/\.github\.io$/.test(location.hostname)) return location.origin + location.pathname.replace(/[^/]*$/, ""); } catch (_) {}
  return CANONICAL;
}
export const takeUrl = (lang = "en") => `${baseUrl()}?room=live${lang === "ar" ? "&lang=ar" : ""}`;

/** An SVG string: dark modules on a light quiet zone, crisp at any size. */
export function qrSvg(text, { dark = "#121110", light = "#ffffff", margin = 3, label = "QR code" } = {}) {
  const q = qrcode(0, "M"); q.addData(text); q.make();
  const n = q.getModuleCount(), size = n + margin * 2; let d = "";
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c + margin} ${r + margin}h1v1h-1z`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges" role="img" aria-label="${label}"><rect width="${size}" height="${size}" fill="${light}"/><path d="${d}" fill="${dark}"/></svg>`;
}
