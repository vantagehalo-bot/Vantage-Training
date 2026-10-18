# Vantage Lens — the Halo on a tablet

A single web page that lets a visitor experience the Vantage Vision Halo without the
device. The decision logic is a line-for-line port of `vantage_core.py`, so every phrase,
threshold and repeat interval matches the firmware.

| Room | What happens |
|---|---|
| **Start** | Headset check with the firmware's two tones, voice choice, speech rate. |
| **Walk** | Abdullah's trip to the coffee shop in three virtual scenes (home, street, café). Split view: what a sighted person sees, and the Halo's own preview. The detector and the laser are simulated from the scene's ground truth, glass and black surfaces included. "Now by ear" blacks the screen out and replays what was said afterwards. |
| **Live** | The tablet camera as the Halo's eye. **Obstacles**: an on-device detector feeds the ported announcer, with range estimated from how big each object looks. **Ask**: preset questions ("What's in front of me?", "Is the way clear?", "What's on the menu?") answered from the current frame by a vision model, or from the detector when there is no key. **Read**: the reader, with on-device OCR or the vision model. |
| **Inside** | The printed visor (from the Fusion 360 export) with every part placed inside it, an explode slider, labels, part photos and a card per part. |
| **Pipeline** | The live pipeline, speech queue events, the dashboard and the log. Settings → Pipeline, or a four-finger tap in Walk. |

Everything the page needs is vendored: no CDN at runtime, no build step. After one load
the service worker keeps it working without Wi-Fi.

## Set up for the booth

1. **Open it over HTTPS.** The camera needs it. The GitHub Pages workflow publishes `demo/`
   at the repository's Pages URL on every push. On a laptop, `localhost` also counts as
   secure: `npx http-server demo -p 8080` and open `http://localhost:8080/`.
2. **Pair the Shokz** to the tablet in Bluetooth settings. Speech goes to the tablet's audio output.
3. **Add the free vision key** (Settings → Vision model). Sign in at `aistudio.google.com`,
   choose *Get API key*, paste it. It stays in the browser's storage on that device. You can
   also open the page once as `index.html?key=AIza…` to store it. Google's free tier
   has a daily quota per model; the app walks down a list of free models when one is
   exhausted, and the model id can be overridden in the same panel. Without a key, the Ask
   panel still answers from the on-device detector and the reader uses on-device OCR.
4. **Load it once while online** so the fonts and models are cached, then it runs offline
   (except the vision model, which needs the network when you ask a question).
5. On iPad use Safari. Turn on Guided Access if visitors will be left alone with it.

## Controls

| Where | Gesture | Does |
|---|---|---|
| Walk, left pane | hold (Guide me) / thumb joystick (free) | walk |
| Walk, right pane | drag | look around |
| Walk | two-finger tap | speak the scene (the device's `s` key) |
| Walk | long press | mute / unmute |
| Walk | three-finger tap | describe mode |
| Walk | four-finger tap | Pipeline |
| Live, Read | pinch | zoom 1×–3×, spoken when the pinch ends |
| Inside | drag / pinch / tap | orbit / zoom / part card |
| Laptop | W A S D or arrows, Q/E to turn, S speaks the scene, M mutes | |

## What is simulated, and how

* **Walk.** The IMX500 is simulated by projecting every labelled object into the firmware's
  640×480 frame with the jitter, confidence spread and misses of a real detector; the
  ported tracker then needs two frames before it trusts anything. The TFmini is a raycast
  inside a 3.6° cone, 10 cm to 12 m; glass and gloss black return a weak signal, which the
  ported filter discards, so the vision fallback applies. Closing speed and time-to-contact
  are the firmware's least-squares fit over 0.5 s.
* **Live.** The detector runs on the tablet (see `js/detector.js` for which network). Range
  comes from the object's typical height divided by how tall its box is, honest to about
  15 % for upright things. Whatever covers the centre of the frame owns the range reading,
  the way the laser beam does on the device.
* **Headset.** Web Speech API through the tablet's audio output. The two-tone beep is the
  firmware's (880 Hz 90 ms, 40 ms gap, 1320 Hz 120 ms, after 150 ms of silence).
* **Reader.** Tesseract on the tablet with the preprocessing in `js/ocr-prep.js`, or the
  vision model when a key is present (far better on packaging and signs).

The footer line says this once; nothing else in the app pretends otherwise.

## Files

```
index.html          page shell
css/style.css       one dark theme: warm graphite, amber accent, Plex Sans / Mono / Serif
js/app.js           rooms, settings, the Walk loop, by-ear mode and replay
js/halo.js          port of vantage_core.py: tracker, LiDAR filter, fusion, announcer, speech queue
js/audio.js         beep, click, Web Speech, haptic
js/overlay.js       the device preview drawing
js/world.js         three.js renderer, player, IMX500 + TFmini simulation
js/props.js         furniture, people, street pieces, floor surfaces
js/scenes.js        home / street / café layouts and moving actors
js/live.js          Live room: camera modes, detector loop, Ask panel
js/camera.js        the shared camera stream, frame grabs, zoom, torch
js/detector.js      on-device object detector
js/range.js         range from box height
js/ai.js            Gemini client (free tier), question presets, local fallback answers
js/reader.js        the reader
js/ocr-prep.js      OCR preprocessing
js/inside.js        exploded twin and part cards
js/hood.js          pipeline view, dashboard, log
sw.js               offline cache
vendor/             three.js 0.160, Tesseract.js 5.1.1 + eng.traineddata, the detector runtime
assets/             visor GLB, part photos, poster, brand mark
```
