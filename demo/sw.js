// Offline cache: after one load the demo runs without the venue Wi-Fi.
const VERSION = "vantage-lens-v1";
const PRECACHE = [
  "./", "index.html", "css/style.css", "manifest.webmanifest",
  "js/app.js", "js/halo.js", "js/audio.js", "js/overlay.js", "js/world.js", "js/props.js", "js/scenes.js", "js/reader.js", "js/inside.js", "js/hood.js",
  "vendor/three/three.module.js", "vendor/three/OrbitControls.js",
  "vendor/tesseract/tesseract.min.js", "vendor/tesseract/worker.min.js", "vendor/tesseract/tesseract-core-simd-lstm.wasm.js", "vendor/tesseract/tesseract-core-lstm.wasm.js", "vendor/tesseract/eng.traineddata",
];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.allSettled(PRECACHE.map(u => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
    const copy = res.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); return res;
  })));
});
