// ocr-prep.js — gets a camera frame ready for Tesseract: grey, cropped to the text,
// scaled so letters are about the size the engine reads best, lighting evened out.
// Returns { canvas, scale, offsetX, offsetY } so word boxes map back to the frame.

export const OCR_PARAMS = {
  tessedit_pageseg_mode: "6",      // one uniform block of text
  user_defined_dpi: "300",
  preserve_interword_spaces: "1",
};

/**
 * @param {HTMLCanvasElement} src  full-size capture
 * @param {object} metrics          live metrics from the reader (light, text, ...)
 */
export function prepareForOcr(src, metrics = {}) {
  const sctx = src.getContext("2d", { willReadFrequently: true });
  const W = src.width, H = src.height;
  const img = sctx.getImageData(0, 0, W, H), d = img.data;
  const g = new Uint8ClampedArray(W * H);
  for (let i = 0, j = 0; i < d.length; i += 4, j++) g[j] = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000;

  // crop to where the strong horizontal transitions are (the text), with a margin
  const rowHits = new Uint16Array(H), colHits = new Uint16Array(W);
  for (let y = 0; y < H; y++) for (let x = 1; x < W; x++) if (Math.abs(g[y * W + x] - g[y * W + x - 1]) > 40) { rowHits[y]++; colHits[x]++; }
  let y0 = 0, y1 = H - 1, x0 = 0, x1 = W - 1;
  const rowT = W * 0.02, colT = H * 0.02;
  while (y0 < H - 1 && rowHits[y0] < rowT) y0++; while (y1 > y0 && rowHits[y1] < rowT) y1--;
  while (x0 < W - 1 && colHits[x0] < colT) x0++; while (x1 > x0 && colHits[x1] < colT) x1--;
  if (y1 - y0 < H * 0.05 || x1 - x0 < W * 0.05) { y0 = 0; y1 = H - 1; x0 = 0; x1 = W - 1; }
  const m = Math.round(Math.min(W, H) * 0.03);
  x0 = Math.max(0, x0 - m); y0 = Math.max(0, y0 - m); x1 = Math.min(W - 1, x1 + m); y1 = Math.min(H - 1, y1 + m);
  const cw = x1 - x0 + 1, ch = y1 - y0 + 1;

  // estimate letter height from the spacing of text rows, scale so x-height ≈ 20-30 px
  let runs = 0, inRun = false; for (let y = y0; y <= y1; y++) { const on = rowHits[y] >= rowT; if (on && !inRun) runs++; inRun = on; }
  const rowPitch = runs ? ch / runs : 40;
  const scale = Math.max(1, Math.min(3, 36 / Math.max(12, rowPitch)));

  // even out the lighting: divide by a heavily blurred copy (box blur via integral image)
  const bg = boxBlur(g, W, H, Math.max(15, Math.round(Math.min(W, H) / 20)));
  const out = document.createElement("canvas"); out.width = Math.round(cw * scale); out.height = Math.round(ch * scale);
  const tmp = document.createElement("canvas"); tmp.width = cw; tmp.height = ch;
  const timg = tmp.getContext("2d").createImageData(cw, ch), td = timg.data;
  let dark = 0;
  for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) {
    const i = (y0 + y) * W + (x0 + x); let v = g[i] / Math.max(1, bg[i]) * 180; v = v < 0 ? 0 : v > 255 ? 255 : v;
    if (v < 110) dark++;
    const o = (y * cw + x) * 4; td[o] = td[o + 1] = td[o + 2] = v; td[o + 3] = 255;
  }
  // white text on a dark sign: flip so Tesseract sees dark on light
  if (dark > cw * ch * 0.5) for (let o = 0; o < td.length; o += 4) { td[o] = td[o + 1] = td[o + 2] = 255 - td[o]; }
  tmp.getContext("2d").putImageData(timg, 0, 0);
  const octx = out.getContext("2d"); octx.imageSmoothingEnabled = true; octx.imageSmoothingQuality = "high";
  octx.drawImage(tmp, 0, 0, out.width, out.height);
  return { canvas: out, scale, offsetX: x0, offsetY: y0, rowPitch };
}

function boxBlur(g, W, H, r) {
  const I = new Float64Array((W + 1) * (H + 1));
  for (let y = 1; y <= H; y++) { let s = 0; for (let x = 1; x <= W; x++) { s += g[(y - 1) * W + (x - 1)]; I[y * (W + 1) + x] = I[(y - 1) * (W + 1) + x] + s; } }
  const out = new Float32Array(W * H);
  for (let y = 0; y < H; y++) { const ya = Math.max(0, y - r), yb = Math.min(H, y + r + 1);
    for (let x = 0; x < W; x++) { const xa = Math.max(0, x - r), xb = Math.min(W, x + r + 1);
      const s = I[yb * (W + 1) + xb] - I[ya * (W + 1) + xb] - I[yb * (W + 1) + xa] + I[ya * (W + 1) + xa];
      out[y * W + x] = s / ((yb - ya) * (xb - xa)); } }
  return out;
}
