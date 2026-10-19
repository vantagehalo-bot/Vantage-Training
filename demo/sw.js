// Offline cache: after one load the demo runs without the venue Wi-Fi.
// Page, styles and scripts: network first (a new deploy shows up on the next load), cache when
// the network is slow or gone. Vendored engines, models, fonts and assets: cache first.
const VERSION = "vantage-lens-v7";
const NETWORK_FIRST_MS = 3000;
const PRECACHE = [
  "./", "index.html", "css/style.css", "manifest.webmanifest",
  "js/app.js", "js/halo.js", "js/audio.js", "js/overlay.js", "js/world.js", "js/props.js", "js/scenes.js", "js/reader.js", "js/inside.js", "js/hood.js", "js/live.js", "js/camera.js", "js/ai.js", "js/range.js", "js/ocr-prep.js", "js/detector.js",
  "vendor/three/three.module.js", "vendor/three/OrbitControls.js", "vendor/three/GLTFLoader.js", "vendor/three/utils/BufferGeometryUtils.js",
  "assets/halo-visor.glb", "assets/halo-poster.jpg", "assets/logo-mark.png", "assets/parts/part-ai-camera.png", "assets/parts/part-cm5.png", "assets/parts/part-lidar.png", "assets/parts/part-nano-base.png", "assets/parts/part-openmove.png", "assets/parts/part-tof.png",
  "vendor/mediapipe/vision_bundle.js", "vendor/mediapipe/wasm/vision_wasm_internal.js", "vendor/mediapipe/wasm/vision_wasm_internal.wasm", "vendor/mediapipe/efficientdet_lite0_float16.tflite",
  "vendor/tesseract/tesseract.min.js", "vendor/tesseract/worker.min.js", "vendor/tesseract/tesseract-core-simd-lstm.wasm.js", "vendor/tesseract/tesseract-core-lstm.wasm.js", "vendor/tesseract/eng.traineddata",
];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.allSettled(PRECACHE.map(u => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
// clone before the body is handed to the page; opaque responses are kept only for the font hosts (a no-cors stylesheet link)
const store = (req, res) => {
  const font = /fonts\.(googleapis|gstatic)\.com$/.test(new URL(req.url).hostname);
  if (res && (res.ok || (res.type === "opaque" && font))) { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)).catch(() => {}); }
  return res;
};
const isCode = (u, req) => req.mode === "navigate" || /\.(html|css|js|webmanifest)$/.test(u.pathname) || u.pathname.endsWith("/");
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (u.hostname.endsWith("googleapis.com") && !u.hostname.startsWith("fonts.")) return;      // the model API is never cached
  const sameOrigin = u.origin === location.origin, font = u.hostname === "fonts.googleapis.com" || u.hostname === "fonts.gstatic.com";
  if (!sameOrigin && !font) return;
  if (sameOrigin && !u.pathname.includes("/vendor/") && !u.pathname.includes("/assets/") && isCode(u, e.request)) {
    e.respondWith(new Promise((resolve) => {
      let settled = false;
      const useCache = () => caches.match(e.request, { ignoreSearch: true }).then(hit => { if (!settled) { settled = true; resolve(hit || fetch(e.request)); } }).catch(() => { if (!settled) { settled = true; resolve(fetch(e.request)); } });
      const timer = setTimeout(useCache, NETWORK_FIRST_MS);
      fetch(e.request).then(res => { clearTimeout(timer); if (settled) { store(e.request, res); return; } settled = true; resolve(store(e.request, res)); }).catch(() => { clearTimeout(timer); useCache(); });
    }));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(res => store(e.request, res))));
});
