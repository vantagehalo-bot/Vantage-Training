# Vantage Lens — the Halo on a tablet

A single web page that lets a visitor experience the Vantage Vision Halo without the
device. The decision logic is a line-for-line port of `vantage_core.py`, so every phrase,
threshold and repeat interval matches the firmware.

| Room | What happens |
|---|---|
| **Start** | Headset check with the firmware's two tones, voice choice, speech rate. |
| **Walk** | Abdullah's trip to the coffee shop in three virtual scenes (home, street, café). Split view: what a sighted person sees, and the Halo's own preview. The detector and the laser are simulated from the scene's ground truth, glass and black surfaces included. "Now by ear" blacks the screen out and replays what was said afterwards. **Leaving for work** is a small escape room: the picture is blurred like low vision, the Halo's boxes and voice sit on top, and the visitor finds the keys, feeds the dog and makes sure there is 100 AED in the wallet before the front door opens. Items move every game. |
| **Live** | The tablet camera as the Halo's eye. **Obstacles**: an on-device detector feeds the ported announcer, with range estimated from how big each object looks. **Ask**: preset questions ("What's in front of me?", "Is the way clear?", "What's on the menu?") answered from the current frame by a vision model, or from the detector when there is no key. **Read**: the reader, with on-device OCR or the vision model. |
| **Inside** | The printed visor (from the Fusion 360 export) with every part placed inside it, an explode slider, part photos and a card per part. A part's name tag shows when the mouse is over it (or the part is tapped), so the exploded view stays readable. |
| **Take home** | `take.html`: two QR codes (English voice, Arabic voice) that open the Live room on a visitor's own phone, and a print layout for the stall. A smaller code sits on the Start screen. The codes carry the public URL only, never the vision key. |
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

## Arabic

Start → Voice, or Settings → Voice language, switches what the Halo says to Arabic. The screens
stay in English for the people around the visitor. Arabic covers the ported announcer (alerts,
describe mode, the scene), the Ask questions and their answers, the reader's coaching, the
model's reading (Arabic print read as printed, other print as a faithful Arabic translation) and
the escape room. The phrases in `js/arabic.js` are written by hand in Modern Standard Arabic,
with numbers and counted nouns agreeing (مترين، ثلاثة أمتار، خمسين سنتيمترًا) and wording that
does not assume the listener's gender. The vision model is told the same rules. Speech uses the
device's Arabic voice (Majed on Apple devices); the Start screen says how to install one when
it is missing.

The free Gemini quota is shared by the whole booth, so auto reading asks the model once per page
and the device reads after that; Read now and the Ask questions always use the model.

## Controls

| Where | Gesture | Does |
|---|---|---|
| Walk, left pane | hold (Guide me) / thumb joystick (free) | walk |
| Walk, right pane | drag | look around |
| Walk | two-finger tap | speak the scene (the device's `s` key) |
| Walk, Leaving for work | face a thing up close | pick it up or use it (keys, wallet, note, dog food, bowl, door) |
| Walk, right pane | long press | mute / unmute |
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
* **Reader.** Tesseract on the tablet, or the vision model when a key is present (far better
  on packaging and signs). The on-device path takes the camera's largest still, crops to the
  text, denoises lightly, stretches the contrast and sharpens hard (`js/ocr-prep.js`; chosen by
  measuring about 1,100 recognitions of degraded phone frames, where it read 85 % of the words
  against 47 % for the first version). Tiny print is coached ("move closer") rather than guessed.
  Read now reads the card again; auto mode skips lines it has already read until the page
  leaves the frame. Only real words are read out: every word is checked against an English
  word list (274k words, `vendor/words/en.txt`, MIT) plus local terms (AED, Dubai, karak),
  numbers, units, prices, dates and product codes; a line that is mostly invented is dropped
  whole, and dropped words show as red boxes.

The footer line says this once; nothing else in the app pretends otherwise. The "Powered by
Jetson Nano" badge in the corner of the Walk and Live views is a drawing of the Jetson Orin
Nano Super developer kit (`assets/jetson-orin-nano-super.svg`); to show a photo instead, add
it to `assets/` and point the two badge `<img>` tags in `index.html` at it.

## Files

```
index.html          page shell
css/style.css       one dark theme: warm graphite, amber accent, Atkinson Hyperlegible Next + Mono
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
js/wordcheck.js     the dictionary filter that keeps invented words out of the reader
js/escape.js        the "Leaving for work" escape room
js/lang.js          voice language (English / Arabic), ?lang=ar
js/arabic.js        the Arabic phrases, number and noun agreement
js/qr.js            take-home QR codes
take.html           "Take Vantage home": QR codes to print for the stall
js/ocr-prep.js      OCR preprocessing
js/inside.js        exploded twin and part cards
js/hood.js          pipeline view, dashboard, log
sw.js               offline cache
vendor/             three.js 0.160, Tesseract.js 5.1.1 + eng.traineddata, the detector runtime
vendor/words/       English word list (sindresorhus/word-list, MIT)
vendor/qrcode/      qrcode-generator 1.4.4 (MIT)
assets/             visor GLB, part photos, poster, brand mark, Jetson Orin Nano Super drawing
```
