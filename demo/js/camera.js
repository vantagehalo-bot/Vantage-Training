// camera.js — one rear-camera stream shared by every Live mode (obstacles, ask, read).
// Owns the <video>, frame grabs at a chosen size, digital zoom, and the torch where the
// browser offers one. Start it from a tap: iOS only opens the camera on a user gesture.

export class Camera {
  constructor(video) {
    this.video = video; this.stream = null; this.track = null; this.zoom = 1;
    this.caps = {}; this.facing = "environment"; this.onChange = () => {};
    this._grab = document.createElement("canvas"); this._gctx = this._grab.getContext("2d", { willReadFrequently: true });
  }
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
    // continuous focus where the browser lets us ask for it
    try { if (this.caps.focusMode && this.caps.focusMode.includes("continuous")) await this.track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }); } catch (_) {}
    this.onChange();
    return this.stream;
  }
  stop() {
    if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; this.track = null; this.video.srcObject = null; this.onChange(); }
  }
  get hasTorch() { return !!(this.caps && this.caps.torch); }
  async setTorch(on) {
    if (!this.track || !this.hasTorch) return false;
    try { await this.track.applyConstraints({ advanced: [{ torch: !!on }] }); return true; } catch (_) { return false; }
  }
  /** Digital zoom 1..3 (the reader's pinch). Uses the hardware zoom range when the camera has one. */
  async setZoom(z) {
    this.zoom = Math.max(1, Math.min(3, z));
    if (this.track && this.caps.zoom && this.caps.zoom.max >= 2) {
      const hw = Math.min(this.caps.zoom.max, Math.max(this.caps.zoom.min || 1, this.zoom));
      try { await this.track.applyConstraints({ advanced: [{ zoom: hw }] }); this._hwZoom = hw; return; } catch (_) {}
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
