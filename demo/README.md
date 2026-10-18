# Vantage Lens — the Halo on a tablet

A single web page that lets a visitor experience the Vantage Vision Halo without the
device: hold the tablet, wear the Shokz, walk through a virtual home, street and café while
the Halo's own announcer narrates, then turn the camera on real print and on the display
model. The decision logic is a line-for-line port of `vantage_core.py`, so every phrase and
threshold matches the firmware.

Rooms: **Wear** (headset check, voice) → **Walk** (three scenes, split view, Guide me /
free joystick, describe mode, speak the scene, SOS) → **Now by ear** (black screen, steer
by sound, then a replay of what was heard and why) → **Read** (camera + on-device OCR,
reader coaching lines, pinch zoom) → **Inside** (exploded 3D twin of the V2 split-pack with
a card per part) → **Under the hood** (live pipeline, queue events, dashboard, log).

Everything is vendored: no CDN, no build step. After one load the service worker keeps it
working without Wi-Fi.

## Run it at the booth

The camera rooms need HTTPS (or `localhost`). Three ways, pick one:

1. **GitHub Pages (simplest).** Repository → Settings → Pages → Source: *GitHub Actions*.
   The workflow in `.github/workflows/pages.yml` publishes `demo/` on every push to the
   default branch. Open the Pages URL on the tablet once while online; it is cached after that.
2. **Laptop on a hotspot, HTTPS.**
   ```bash
   brew install mkcert && mkcert -install && mkcert 192.168.1.10   # the laptop's hotspot IP
   npx http-server demo -S -C 192.168.1.10.pem -K 192.168.1.10-key.pem -p 8443
   ```
   Open `https://192.168.1.10:8443/` on the tablet and accept the certificate (or AirDrop
   the mkcert root CA to the iPad and trust it in Settings → General → About → Certificate Trust).
3. **No camera needed?** Any static server works for Walk, Inside and Under the hood:
   `npx http-server demo -p 8080`.

On iPad use Safari. Pair the Shokz to the tablet in Bluetooth settings first; speech goes
to whatever the tablet's audio output is. Turn on Guided Access if visitors will be left alone with it.

## Controls

| Where | Gesture | Does |
|---|---|---|
| Walk, left pane | hold (Guide me) / thumb joystick (free) | walk |
| Walk, right pane | drag | look around |
| Walk | two-finger tap | speak the scene (the device's `s` key) |
| Walk | long press | mute / unmute |
| Walk | three-finger tap | describe mode |
| Walk | four-finger tap | Under the hood |
| Read | pinch | zoom 1×–3×, spoken when the pinch ends |
| Inside | drag / pinch / tap | orbit / zoom / part card |
| Laptop | W A S D or arrows, Q/E to turn, S speaks the scene, M mutes | |

## What is simulated, and how

* **IMX500.** Every labelled object in view is projected to the firmware's 640×480 frame.
  Boxes jitter a few percent, confidence is drawn from a per-class range, small or clipped
  objects score lower, and about one detection in twenty is missed. The ported tracker then
  needs two frames before it trusts anything, exactly as on the device.
* **TFmini Plus.** A raycast from the eye line, offset by the configurable mount offset,
  inside a 3.6° cone, 10 cm to 12 m. Glass and gloss-black surfaces return a weak signal
  (strength under 100), which the ported filter discards; the vision fallback then applies.
  Closing speed and time-to-contact are the firmware's least-squares fit over 0.5 s.
* **Headset.** Web Speech API through the tablet's audio output. The two-tone beep is the
  firmware's (880 Hz 90 ms, 40 ms gap, 1320 Hz 120 ms, after 150 ms of silence).
* **Reader.** Tesseract (English, fast model) on the tablet. Steadiness from frame
  difference, sharpness from the Laplacian, light from mean luminance, like the device's meters.

The footer line says this once; nothing else in the app pretends otherwise.

## Files

```
index.html          page shell
css/style.css
js/halo.js          port of vantage_core.py: tracker, LiDAR filter, fusion, announcer, speech queue
js/audio.js         beep, click, Web Speech, haptic
js/overlay.js       the device preview drawing
js/world.js         three.js renderer, player, IMX500 + TFmini simulation
js/props.js         furniture, people, street pieces
js/scenes.js        home / street / café layouts and moving actors
js/reader.js        Read room
js/inside.js        exploded twin and part cards
js/hood.js          pipeline view, dashboard, log
sw.js               offline cache
vendor/             three.js 0.160, Tesseract.js 5.1.1 + eng.traineddata (tessdata_fast)
```
