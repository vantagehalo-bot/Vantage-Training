// wordcheck.js — keeps the reader honest: a word is spoken only when it is a real English
// word, a number, a unit, a price, a date or a short product code. Tesseract on a camera
// frame invents plausible-looking strings from texture and noise; this is where they stop.
// Word list: sindresorhus/word-list (MIT), 274k words, vendor/words/en.txt.

// Words the list leaves out but labels, menus and signs in the UAE use all the time
const EXTRA = `a i mg ml mcg kg km cm mm g l oz lb ltr pcs pc qty no nos exp mfg lot ref aed dhs dh usd eur gbp
vat incl excl tel fax www com ae uae dubai abu dhabi sharjah ajman fujairah ras khaimah umm quwain al el bin
karak chai shawarma falafel hummus labneh manakish zaatar mutabal fattoush tabbouleh shisha luqaimat
wifi ok pm am mon tue wed thu fri sat sun jan feb mar apr jun jul aug sep sept oct nov dec
etc approx max min dept st rd ave dr mr mrs ms ltd llc co inc fz fze`.split(/\s+/);
// Two-letter words worth trusting (the list holds many obscure ones that noise produces)
const TWO = new Set("am an as at be by do go he hi if in is it me my no of oh ok on or so to up us we".split(" "));

let dict = null, loading = null;
export function loadWords(url = "vendor/words/en.txt") {
  if (dict) return Promise.resolve(dict);
  if (loading) return loading;
  loading = fetch(url).then(r => { if (!r.ok) throw new Error(`word list ${r.status}`); return r.text(); })
    .then(t => { const s = new Set(t.split("\n").map(w => w.trim().toLowerCase()).filter(Boolean)); for (const w of EXTRA) if (w) s.add(w); dict = s; return s; })
    .catch(e => { loading = null; throw e; });
  return loading;
}
export const wordsReady = () => !!dict;

const NUMBERISH = [
  /^[(\[]?[-+]?\d+([.,:/]\d+)*[)\]]?%?$/,                       // 500  1.5  10:45  03/2028  25%
  /^\d+([.,]\d+)?(mg|mcg|ml|g|kg|l|cm|mm|km|m|oz|lb|x|pm|am|h|hr|hrs|min|s|°c|°|%)$/i,   // 500mg 2x 10am
  /^(aed|dhs?|usd|\$|€|£)\d+([.,]\d+)?$/i, /^\d+([.,]\d+)?(aed|dhs?)$/i,                   // AED18  18dhs
  /^#?\d{1,4}[a-z]{0,2}$/i,                                       // 12  2B  #4
  /^(?=.*\d)(?=.*[a-z])[a-z0-9]{3,10}$/i,                         // batch and lot codes: 2041B  A12C3
  /^\d{1,2}(st|nd|rd|th)$/i,
];

/** Strip quotes and punctuation at the edges; keep inner apostrophes, hyphens and dots. */
function core(token) { return token.replace(/^[^A-Za-z0-9$€£#(]+|[^A-Za-z0-9%°)]+$/g, ""); }

/** Is this token something real? `conf` is Tesseract's word confidence (0–100). */
export function isKnown(token, conf = 100) {
  const t = core(token); if (!t) return false;
  if (NUMBERISH.some(re => re.test(t))) return conf >= 50;
  if (!dict) return conf >= 80;                       // no list loaded: fall back to confidence alone
  if (/[-–]/.test(t) && dict.has(t.toLowerCase().replace(/[-–]/g, ""))) return true;   // Wi-Fi, e-mail
  const parts = t.split(/[-–\/]/).filter(Boolean);     // film-coated, and/or
  if (!parts.length) return false;
  return parts.every(p => knownWord(p, conf));
}
function knownWord(p, conf) {
  if (NUMBERISH.some(re => re.test(p))) return true;
  const w = p.toLowerCase().replace(/[’']s$/, "").replace(/[’'.]/g, "");
  if (!w) return false;
  if (/[^a-z]/.test(w)) return false;
  if (w.length === 1) return (w === "a" || w === "i") && conf >= 70;
  if (w.length === 2) return TWO.has(w) || (dict.has(w) && conf >= 85);
  if (w.length === 3 && conf < 55) return false;
  if (dict.has(w)) return true;
  // simple inflections the list may not hold
  for (const suf of ["s", "es", "ed", "ing", "ly"]) if (w.endsWith(suf) && dict.has(w.slice(0, -suf.length))) return true;
  // a name on a sign or a brand on a box: capitalised in print and read with high confidence
  return /^[A-Z][a-z]{3,}$/.test(p) && conf >= 90;
}

/**
 * Filter one OCR line: keep the known words, and the line only when most of it is real.
 * `words` are Tesseract word objects ({ text, confidence }). Returns the cleaned text or "".
 */
export function cleanLine(words) {
  const toks = words.map(w => ({ text: w.text.trim(), conf: w.confidence })).filter(w => w.text);
  if (!toks.length) return "";
  const keep = toks.filter(w => isKnown(w.text, w.conf));
  const letters = keep.filter(w => /[A-Za-z]{2,}/.test(w.text));
  if (!letters.length) return "";                                  // a line of stray numbers is noise
  if (keep.length / toks.length < 0.6) return "";                 // mostly invented: drop all of it
  if (keep.length === 1 && core(keep[0].text).length < 3) return "";
  return keep.map(w => w.text).join(" ").replace(/\s+([.,;:!?])/g, "$1").trim();
}
