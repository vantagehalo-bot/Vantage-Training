// ocr-prep.js — camera frame → canvas ready for Tesseract.js recognize().
//
// Pipeline (chosen by measurement on synthetic phone frames of a medicine box, a menu
// and a paperback page: ±3° rotation, keystone, 1–1.5 px Gaussian blur, sensor noise,
// a 40 % lighting gradient, body x-height 10–14 px):
//   1. grey
//   2. crop to the text region (noise-adaptive edge activity, gaps bridged) — fewer pixels,
//      no table/background texture for Tesseract to hallucinate words from
//   3. (optional, off by default) upscale ×2 when the text is tiny — measured no gain down to 7 px x-height
//   4. light Gaussian denoise (σ 0.7)   ← the single most important step: sharpening or
//      binarising raw sensor noise is what makes Tesseract produce garbage
//   5. 2–98 % contrast stretch
//   6. strong unsharp mask (σ 1.5, amount 2.0) — a crude deconvolution of the camera blur
//   7. invert if the crop is mostly dark (white text on a dark sign)
// Adaptive binarisation (Sauvola / Bradley) and background division were measured and lost:
// they erode thin strokes at 10–14 px x-height and amplify noise into spurious words.
//
// Self-contained: no imports. Works on an HTMLCanvasElement or an ImageData.

export const OCR_PARAMS = {
  tessedit_pageseg_mode: "6",      // single uniform block — see numbers for 3/4/11
  user_defined_dpi: "300",
  preserve_interword_spaces: "1",
};
/** Pass as the 3rd argument of worker.recognize(): skips hOCR/TSV generation (faster). */
export const RECOGNIZE_OUTPUT = { text: true, blocks: true, hocr: false, tsv: false };

export const DEFAULTS = {
  denoiseSigma: 0.7,     // Gaussian σ before sharpening (at 1×; scaled with upscale)
  usmSigma: 1.5,         // unsharp radius (at 1×)
  usmAmount: 2.0,        // unsharp strength
  stretchLo: 0.02, stretchHi: 0.98,
  crop: true,            // crop to the text region
  cropMargin: 0.04,      // margin around the region, fraction of min(W, H)
  upscaleBelowXH: 0,     // upscale ×2 when the estimated x-height (px) is below this (0 = never;
                         // measured: no gain at x-height 7–14 px, Tesseract rescales lines itself)
  upscale: 2,
  maxPixels: 4.5e6,      // never hand Tesseract more than this (time grows ~linearly)
  invertIfDark: true,
};

/**
 * @param {HTMLCanvasElement|ImageData} source
 * @param {Partial<typeof DEFAULTS>} [opts]
 * @returns {{ canvas: HTMLCanvasElement, scale: number, offsetX: number, offsetY: number,
 *            region: {x0:number,y0:number,x1:number,y1:number}, xHeight: number, noise: number, inverted: boolean }}
 *   Word boxes from Tesseract map back to the source frame as  x / scale + offsetX,  y / scale + offsetY.
 */
export function prepareForOcr(source, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const { data, W, H } = pixels(source);
  const g = new Float32Array(W * H);
  for (let i = 0, j = 0; j < g.length; i += 4, j++) g[j] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];

  // ---- 2. text region (on a lightly blurred copy so the threshold tracks the noise level)
  const r = textRegion(g, W, H, o.cropMargin);
  const region = o.crop ? { x0: r.x0, y0: r.y0, x1: r.x1, y1: r.y1 } : { x0: 0, y0: 0, x1: W, y1: H };
  const cw = region.x1 - region.x0, ch = region.y1 - region.y0;
  let crop = g;
  if (cw !== W || ch !== H) { crop = new Float32Array(cw * ch); for (let y = 0; y < ch; y++) crop.set(g.subarray((region.y0 + y) * W + region.x0, (region.y0 + y) * W + region.x1), y * cw); }

  // ---- 3. upscale only when the text is tiny; shrink a crop that is still bigger than maxPixels
  //         (a 12 MP still of a menu: the print is large, Tesseract's time grows with the pixels)
  const xHeight = r.xHeight;
  let scale = 1;
  if (xHeight && xHeight < o.upscaleBelowXH && cw * ch * o.upscale * o.upscale <= o.maxPixels) scale = o.upscale;
  else if (cw * ch > o.maxPixels) scale = Math.sqrt(o.maxPixels / (cw * ch));
  let work = crop, ww = cw, wh = ch;
  if (scale !== 1) { const up = resample(crop, cw, ch, scale); work = up.g; ww = up.W; wh = up.H; scale = up.W / cw; }

  // ---- 4–6. denoise → stretch → unsharp (radii follow the scale; shrinking already averages the noise)
  const noise = noiseSigma(work, ww, wh);
  let out = gaussian(work, ww, wh, Math.max(0.5, o.denoiseSigma * scale));
  out = stretch(out, o.stretchLo, o.stretchHi);
  out = unsharp(out, ww, wh, Math.max(1, o.usmSigma * scale), o.usmAmount);

  // ---- 7. white-on-dark → dark-on-white: judge polarity by the middle of the crop (the page), not
  //         by the whole crop, which may still contain a dark table or a coloured band
  let inverted = false;
  if (o.invertIfDark) {
    const xs = ww >> 2, xe = ww - xs, ys = wh >> 2, ye = wh - ys, h = new Uint32Array(256); let n = 0;
    for (let y = ys; y < ye; y += 2) for (let x = xs; x < xe; x += 2) { h[out[y * ww + x] | 0]++; n++; }
    let acc = 0, med = 0; for (; med < 255; med++) { acc += h[med]; if (acc * 2 >= n) break; }
    if (med < 100) { inverted = true; for (let i = 0; i < out.length; i++) out[i] = 255 - out[i]; }
  }

  return { canvas: toCanvas(out, ww, wh), scale, offsetX: region.x0, offsetY: region.y0, region, xHeight, noise, inverted, pixels: ww * wh };
}

// ------------------------------------------------------------------ helpers
function pixels(src) {
  if (src instanceof ImageData || (src && src.data && src.width && src.height)) return { data: src.data, W: src.width, H: src.height };
  const W = src.width, H = src.height;
  const ctx = src.getContext("2d", { willReadFrequently: true });
  return { data: ctx.getImageData(0, 0, W, H).data, W, H };
}
function toCanvas(g, W, H) {
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d"), img = ctx.createImageData(W, H), d = img.data;
  for (let j = 0, i = 0; j < g.length; j++, i += 4) { const v = g[j] < 0 ? 0 : g[j] > 255 ? 255 : g[j]; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
  ctx.putImageData(img, 0, 0); return c;
}
/** Bicubic-quality upscale through the canvas resampler. */
function resample(g, W, H, f) {
  const c = toCanvas(g, W, H), o = document.createElement("canvas"); o.width = Math.round(W * f); o.height = Math.round(H * f);
  const ctx = o.getContext("2d", { willReadFrequently: true }); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
  ctx.drawImage(c, 0, 0, o.width, o.height);
  const d = ctx.getImageData(0, 0, o.width, o.height).data, out = new Float32Array(o.width * o.height);
  for (let i = 0, j = 0; j < out.length; i += 4, j++) out[j] = d[i];
  return { g: out, W: o.width, H: o.height };
}
function gaussian(g, W, H, sigma) {
  if (sigma <= 0) return Float32Array.from(g);
  const r = Math.ceil(sigma * 3), k = new Float32Array(2 * r + 1); let s = 0;
  for (let i = -r; i <= r; i++) { k[i + r] = Math.exp(-(i * i) / (2 * sigma * sigma)); s += k[i + r]; }
  for (let i = 0; i < k.length; i++) k[i] /= s;
  const tmp = new Float32Array(W * H), out = new Float32Array(W * H);
  for (let y = 0; y < H; y++) { const row = y * W; for (let x = 0; x < W; x++) { let a = 0; for (let i = -r; i <= r; i++) { const xx = x + i < 0 ? 0 : x + i >= W ? W - 1 : x + i; a += g[row + xx] * k[i + r]; } tmp[row + x] = a; } }
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { let a = 0; for (let i = -r; i <= r; i++) { const yy = y + i < 0 ? 0 : y + i >= H ? H - 1 : y + i; a += tmp[yy * W + x] * k[i + r]; } out[y * W + x] = a; }
  return out;
}
function unsharp(g, W, H, sigma, amount) {
  const b = gaussian(g, W, H, sigma), out = new Float32Array(g.length);
  for (let i = 0; i < g.length; i++) { const v = g[i] + amount * (g[i] - b[i]); out[i] = v < 0 ? 0 : v > 255 ? 255 : v; }
  return out;
}
function stretch(g, lo, hi) {
  const h = new Uint32Array(256); for (let i = 0; i < g.length; i++) h[g[i] < 0 ? 0 : g[i] > 255 ? 255 : g[i] | 0]++;
  const pct = p => { let acc = 0, t = p * g.length, v = 0; for (; v < 256; v++) { acc += h[v]; if (acc >= t) break; } return v; };
  const a = pct(lo), b = pct(hi), s = 255 / Math.max(1, b - a), out = new Float32Array(g.length);
  for (let i = 0; i < g.length; i++) { const v = (g[i] - a) * s; out[i] = v < 0 ? 0 : v > 255 ? 255 : v; }
  return out;
}
/** Noise σ from the median absolute 4-neighbour Laplacian (robust to edges). */
function noiseSigma(g, W, H) {
  const total = (W - 2) * (H - 2), step = Math.max(1, Math.floor(total / 30000)), vals = [];
  for (let i = W + 1; i < W * (H - 1) - 1; i += step) { const x = i % W; if (x === 0 || x === W - 1) continue; vals.push(Math.abs(4 * g[i] - g[i - 1] - g[i + 1] - g[i - W] - g[i + W])); }
  vals.sort((a, b) => a - b); return (vals[vals.length >> 1] || 0) * 1.4826 / Math.sqrt(20);
}
/**
 * Text region + size estimate, computed on a half-resolution copy (4× cheaper, same result):
 * bounding box of horizontal-edge activity (threshold follows the measured noise), gaps between
 * lines bridged; x-height ≈ 0.6 × the median inked-row-run height measured in narrow vertical
 * strips (narrow so a few degrees of rotation does not merge the lines).
 */
function textRegion(g, W, H, margin) {
  const W2 = W >> 1, H2 = H >> 1, h = new Float32Array(W2 * H2);
  for (let y = 0; y < H2; y++) for (let x = 0; x < W2; x++) { const i = 2 * y * W + 2 * x; h[y * W2 + x] = 0.25 * (g[i] + g[i + 1] + g[i + W] + g[i + W + 1]); }
  const d = gaussian(h, W2, H2, 0.6), T = Math.max(8, 6 * noiseSigma(d, W2, H2));
  const E = new Uint8Array(W2 * H2), rows = new Uint32Array(H2), cols = new Uint32Array(W2);
  for (let y = 0; y < H2; y++) for (let x = 1; x < W2 - 1; x++) if (Math.abs(d[y * W2 + x + 1] - d[y * W2 + x - 1]) > T) { E[y * W2 + x] = 1; rows[y]++; cols[x]++; }
  const run = (prof, N, min, bridge) => {
    const on = new Uint8Array(N); for (let i = 0; i < N; i++) on[i] = prof[i] >= min ? 1 : 0;
    let last = -1e9; for (let i = 0; i < N; i++) if (on[i]) { if (i - last <= bridge) for (let j = last + 1; j < i; j++) on[j] = 1; last = i; }
    let best = [0, 0], cur = -1; for (let i = 0; i <= N; i++) { if (i < N && on[i]) { if (cur < 0) cur = i; } else if (cur >= 0) { if (i - cur > best[1] - best[0]) best = [cur, i]; cur = -1; } }
    return best;
  };
  let [y0, y1] = run(rows, H2, W2 * 0.01, Math.round(H2 * 0.12));
  let [x0, x1] = run(cols, W2, H2 * 0.006, Math.round(W2 * 0.12));
  if (y1 - y0 < H2 * 0.05 || x1 - x0 < W2 * 0.05) { x0 = 0; y0 = 0; x1 = W2; y1 = H2; }
  // size: inked-row runs inside narrow strips across the region
  const sw = Math.max(8, Math.round((x1 - x0) / 12)), heights = [];
  for (let sx = x0; sx + sw <= x1; sx += sw) {
    let cur = -1; for (let y = y0; y <= y1; y++) {
      let n = 0; if (y < y1) for (let x = sx; x < sx + sw; x++) n += E[y * W2 + x];
      const on = y < y1 && n >= sw * 0.08;
      if (on && cur < 0) cur = y; else if (!on && cur >= 0) { const hh = y - cur; if (hh >= 2 && hh <= H2 * 0.15) heights.push(hh); cur = -1; }
    }
  }
  heights.sort((a, b) => a - b);
  const runH = heights.length >= 3 ? heights[heights.length >> 1] * 2 : 0;   // back to full-res px
  const m = Math.round(Math.min(W, H) * margin);
  return { x0: Math.max(0, 2 * x0 - m), y0: Math.max(0, 2 * y0 - m), x1: Math.min(W, 2 * x1 + m), y1: Math.min(H, 2 * y1 + m), xHeight: runH * 0.6 };
}
