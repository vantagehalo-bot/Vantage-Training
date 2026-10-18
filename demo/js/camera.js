// camera.js — one rear-camera stream shared by every Live mode (obstacles, ask, read).
// Owns the <video>, frame grabs at a chosen size, digital zoom, and the torch where the
// browser offers one. Start it from a tap: iOS only opens the camera on a user gesture.

export class Camera {
  constructor(video) {
    this.video = video; this.stream = null; this.track = null; this.zoom = 1;
    this.caps = {}; this.facing = "environment"; this.onChange = () => {};
    this._grab = document.createElement("canvas"); this._gctx = this._grab.getContext("2d", { willReadFrequently: true });
    this._busy = Promise.resolve();   // iOS ≤ 26 misbehaves when applyConstraints and takePhoto overlap
    this.imageCapture = null; this.muted = false; this.onMute = () => {};
  }
  _serial(fn) { const p = this._busy.then(fn, fn); this._busy = p.catch(() => {}); return p; }
  get running() { return !!this.stream && this.video.readyState >= 2 && this.video.videoWidth > 0; }
  get size() { return { w: this.video.videoWidth || 0, h: this.video.videoHeight || 0 }; }

  async start() {
    if (this.stream) return this.stream;
    const tries = [
      { facingMode: { exact: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      { facingMode: { ideal: "environment" } },
      true,
    ];
    let last = null;
    for (const c of tries) {
      try { this.stream = await navigator.mediaDevices.getUserMedia({ video: c, audio: false }); break; }
      catch (e) { last = e; }
    }
    if (!this.stream) throw last || new Error("Camera unavailable");
    this.track = this.stream.getVideoTracks()[0];
    try { this.caps = this.track.getCapabilities ? this.track.getCapabilities() : {}; } catch (_) { this.caps = {}; }
    this.facing = (this.track.getSettings && this.track.getSettings().facingMode) || this.facing;
    this.video.srcObject = this.stream; this.video.muted = true; this.video.setAttribute("playsinline", "");
    await this.video.play().catch(() => {});
    // continuous focus where the browser lets us ask for it (Android; iOS focuses on its own)
    try { if (this.caps.focusMode && this.caps.focusMode.includes("continuous")) await this._serial(() => this.track.applyConstraints({ advanced: [{ focusMode: "continuous" }] })); } catch (_) {}
    try { if ("ImageCapture" in window) this.imageCapture = new ImageCapture(this.track); } catch (_) { this.imageCapture = null; }
    // iOS mutes the track while the page is hidden or a call comes in, and unmutes on return: no restart needed
    this.track.addEventListener("mute", () => { this.muted = true; this.onMute(true); });
    this.track.addEventListener("unmute", () => { this.muted = false; this.onMute(false); });
    this.onChange();
    return this.stream;
  }
  stop() {
    if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; this.track = null; this.video.srcObject = null; this.onChange(); }
  }
  get hasTorch() { return !!(this.caps && this.caps.torch); }
  async setTorch(on) {
    if (!this.track || !this.hasTorch) return false;
    try { await this._serial(() => this.track.applyConstraints({ advanced: [{ torch: !!on }] })); return true; } catch (_) { return false; }
  }
  /**
   * A still for reading: the camera's photo pipeline at its largest size where the browser
   * offers it (iOS 18.4+, Android Chrome), else the sharpest of a short burst of video frames.
   * Returns a canvas in the same crop as the live view.
   */
  async still(maxW = 2600) {
    if (this.imageCapture) {
      try {
        const blob = await this._serial(async () => {
          let opts = {};
          try { const pc = await this.imageCapture.getPhotoCapabilities(); if (pc && pc.imageWidth && pc.imageHeight) opts = { imageWidth: Math.min(pc.imageWidth.max, 4032), imageHeight: Math.min(pc.imageHeight.max, 3024) }; } catch (_) {}
          return this.imageCapture.takePhoto(opts);
        });
        const bmp = await createImageBitmap(blob);
        const z = this._hwZoom && this._hwZoom > 1 ? 1 : this.zoom;
        const sw = bmp.width / z, sh = bmp.height / z, scale = Math.min(1, maxW / sw);
        const c = document.createElement("canvas"); c.width = Math.round(sw * scale); c.height = Math.round(sh * scale);
        c.getContext("2d", { willReadFrequently: true }).drawImage(bmp, (bmp.width - sw) / 2, (bmp.height - sh) / 2, sw, sh, 0, 0, c.width, c.height);
        bmp.close && bmp.close();
        c.dataset.source = "photo";
        return c;
      } catch (_) { /* fall through to the video frames */ }
    }
    let best = null;
    for (let i = 0; i < 4; i++) {
      const c = this.grab(maxW, document.createElement("canvas")); if (!c) break;
      const s = frameSharpness(c);
      if (!best || s > best.s) best = { c, s };
      await new Promise(r => setTimeout(r, 40));
    }
    if (best) best.c.dataset.source = "video";
    return best ? best.c : null;
  }
  /** Digital zoom 1..3 (the reader's pinch). Uses the hardware zoom range when the camera has one. */
  async setZoom(z) {
    this.zoom = Math.max(1, Math.min(3, z));
    if (this.track && this.caps.zoom && this.caps.zoom.max >= 2) {
      const hw = Math.min(this.caps.zoom.max, Math.max(this.caps.zoom.min || 1, this.zoom));   // web zoom 1 = the main lens on iOS
      try { await this._serial(() => this.track.applyConstraints({ advanced: [{ zoom: hw }] })); this._hwZoom = hw; return; } catch (_) {}
    }
    this._hwZoom = 1;
  }
  /** The part of the frame the current zoom shows (source rect in video pixels). */
  cropRect() {
    const { w, h } = this.size; const z = this._hwZoom && this._hwZoom > 1 ? 1 : this.zoom;
    const sw = w / z, sh = h / z; return { sx: (w - sw) / 2, sy: (h - sh) / 2, sw, sh };
  }
  /** Draw the (zoomed) frame into a canvas no wider than maxW. Returns the canvas. */
  grab(maxW = 1280, canvas = this._grab) {
    const { sx, sy, sw, sh } = this.cropRect(); if (!sw || !sh) return null;
    const scale = Math.min(1, maxW / sw);
    canvas.width = Math.round(sw * scale); canvas.height = Math.round(sh * scale);
    const ctx = canvas === this._grab ? this._gctx : canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(this.video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    return canvas;
  }
  /** JPEG for the vision API: small enough to be quick, large enough to read print. */
  async jpeg(maxW = 1024, quality = 0.8) {
    const c = this.grab(maxW, document.createElement("canvas")); if (!c) return null;
    const blob = await new Promise(r => c.toBlob(r, "image/jpeg", quality));
    const b64 = await new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result.split(",")[1]); fr.onerror = rej; fr.readAsDataURL(blob); });
    return { b64, blob, width: c.width, height: c.height };
  }
}

function frameSharpness(c) {
  const ctx = c.getContext("2d", { willReadFrequently: true }); const W = c.width, H = c.height;
  const step = Math.max(1, Math.floor(W / 320)); const d = ctx.getImageData(0, 0, W, H).data; let s = 0, n = 0;
  for (let y = step; y < H - step; y += step * 2) for (let x = step; x < W - step; x += step * 2) {
    const i = (y * W + x) * 4, l = 4 * d[i] - d[i - 4 * step] - d[i + 4 * step] - d[i - 4 * W * step] - d[i + 4 * W * step]; s += l * l; n++;
  }
  return Math.sqrt(s / Math.max(1, n));
}
