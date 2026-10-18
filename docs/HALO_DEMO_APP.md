# Vantage Lens — the Halo, on a tablet

A proposal for tomorrow's demo. One web app, opened in the tablet's browser, that *is* the
Halo for three minutes: the visitor wears the tablet, hears what a Halo wearer hears, reads
what a Halo wearer reads, and then points the same tablet at the display model to open it
up. No CM5, no app store, no venue Wi-Fi dependency.

> Source of truth for every behaviour below is `vantage_core.py` and `vantage_reader.py`.
> Nothing in the demo invents a feature the device does not have. Where the tablet has to
> approximate a sensor the Halo has (the LiDAR), the app says so in a quiet footnote rather
> than faking precision. That restraint is what keeps it from being corny.

---

## 1. The one idea

**The tablet is the Halo. The visitor is the wearer.**

Everything else follows from that. The tablet hangs on a neck strap at chest height, camera
facing out, exactly where the Halo sits. A Shokz headset is paired to the tablet, so the
voice arrives through the cheekbones, the way it really does. The screen shows the Halo's
own preview (the same boxes, crosshair, distance bar and banner the README describes), so
sighted visitors see what the device "thinks" while they hear what the wearer hears.

The journey has five rooms. A visitor can walk straight through in three minutes or stay in
one room for ten.

| Room | What they do | Which Halo feature it proves |
|---|---|---|
| **Wear** | Strap on, choose the voice, hear "Vantage ready" | Bluetooth bone-conduction audio, voice settings |
| **Walk** | Walk a 4 m course of chairs, a cone and a person | On-sensor detection, tracker, fusion, announcer, TTC, hysteresis, describe mode, speak-scene |
| **Trust** | Screen goes black, they do the course again by ear | The whole point of the product |
| **Read** | Point at a menu, a medicine box, a book page | Auto-capture, steadiness, sharp/light meters, OCR, sentence playback, zoom, failure coaching |
| **Inside** | Point at the display model, it opens into parts | The hardware story: IMX500, TFmini Plus, CM5, Shokz |

A sixth, hidden room, **Under the hood**, is for technical judges: the live pipeline with
real messages flowing, being pre-empted and being dropped when stale.

---

## 2. Room by room

### 2.1 Wear (20 seconds)

* Full-screen, dark, one line: *"Hang the tablet at your chest. Camera out."* A small
  silhouette shows the position. No logo splash.
* Headset check: the app plays the Halo's real two-tone beep (two short rising tones, 150 ms
  of leading silence so the Bluetooth sink wakes up, exactly like the firmware) and asks
  "Did you feel that?" A yes moves on. A no shows the pairing hint.
* Voice picker: three voices, speech rate slider (default 175 wpm like the device). Picking
  one says "Vantage ready" in that voice. That phrase is the device's own boot message.
* A single footer line, grey, small: *"Simulated on this tablet. On the Halo, detection runs
  on the camera sensor and distance comes from a laser rangefinder."* It stays on every
  screen that simulates. It is the only disclaimer in the app and it never repeats itself.

### 2.2 Walk (the core, 60 to 90 seconds)

The live camera, full screen, drawn exactly like the Halo preview:

* Every tracked object gets a coloured box with label and confidence. The target (the one
  the "beam" lands on) turns red and shows its distance.
* A crosshair marks the LiDAR aim point, dead centre, offset by the configurable mount offset.
* A vertical distance bar on the right edge with ticks at 50 cm and 100 cm.
* A flashing red banner: `!! PERSON TOO CLOSE, 40 CENTIMETERS (TTC 0.6s)`.
* The bottom line shows exactly what was just spoken, with a tiny priority tag
  (CRITICAL / WARNING / INFO).

**The announcer is a straight port of the device logic**, so what visitors hear is what a
wearer hears:

| Situation | Spoken | Priority |
|---|---|---|
| Target under 50 cm | beep, then "Person too close, 40 centimeters" | CRITICAL, pre-empts everything, repeats every 2.5 s, repeats at once if the object changes |
| Under 100 cm, or time-to-contact under 1.5 s | "Chair ahead, 80 centimeters, approaching fast" | WARNING |
| Close but not recognised | "Obstacle too close, 35 centimeters" | CRITICAL |
| Box fills over 55 % of the frame, no range | "Person very close" | CRITICAL |
| Describe mode, newly confirmed object | "Chair on your left" (left third / centre / right third) | INFO |
| Two-finger tap (the device's `s` key) | "Person ahead, chair on your right. Distance ahead 1.2 meters" | INFO |
| Nothing | "Clear" once, then silence | INFO |

Rules that must be ported too, because they are what make it feel like a product and not a
toy: an object needs 2 consecutive frames before it is trusted; 8 cm hysteresis at both
thresholds; messages older than 1 to 2.5 s are dropped unspoken; distances are quantised to
5 cm under a metre and to 0.1 m above, said as "1 meter", "1.5 meters", "2 meters".

**Where the distance comes from on a tablet.** The Halo measures range with the TFmini
Plus. A tablet browser cannot read the iPad's LiDAR, so the app estimates range from the
box height of the detected class (a standing person is about 1.7 m tall, a chair about
0.9 m, a bottle 0.25 m, from the camera's known field of view). This is accurate to roughly
10 to 15 % at 0.5 to 3 m, which is good enough for the thresholds to trigger where they
should. Closing speed and time-to-contact are the least-squares slope of that distance over
the last half second, same as the firmware. The footer line already covers this; nothing
else needs saying.

Controls, all gestures so the tablet can stay strapped on:

* Two-finger tap: speak the scene.
* Long press: mute / unmute ("Audio muted" / "Audio unmuted").
* Three-finger tap: describe mode on/off.
* Swipe down from top: the small settings sheet (critical 50 cm, warning 100 cm,
  repeat 2.5 s, threshold 0.55, LiDAR offset). Changing them live is a strong moment for a
  technical visitor: drag the critical threshold to 80 cm and the banner fires earlier.

### 2.3 Trust (the moment people remember)

After one pass of Walk, the app offers a single button: **"Now do it by ear."**

* The screen goes fully black except for a thin breathing ring. Everything is audio.
* The visitor (or a volunteer with them) walks the same 4 m course with eyes closed, guided
  only by the Shokz. A booth helper walks alongside, hand hovering, as you would with a real
  first-time user.
* When they tap the ring at the end, the screen comes back with a **replay**: a 10-second
  scrub of what the camera saw, with the spoken timeline underneath. "You stopped here
  because you heard this." Nothing animated or celebratory. The replay is the reward.
* Optional, one line: "Average time to warning: 0.4 s" if the number is good, omitted if
  it isn't.

This room is why the app exists. Keep it silent, dark and short.

### 2.4 Read

Switches the pipeline to the reader. Three props on the table: a restaurant menu, a
medicine box, a page of a paperback. The screen is the reader preview:

* Detected text lines outlined, with the live **sharp / light / steady** meters. Steadiness
  comes from the device motion sensors, 0.7 s still like the firmware. Sharpness is the
  Laplacian variance of the text region. Light is mean luminance.
* When steady and sharp, the app plays the device's short click, captures a burst of
  5 frames, keeps the sharpest, and runs on-device OCR.
* Each recognised word is boxed and colour-coded by confidence; the right panel shows the
  full text with the sentence being spoken highlighted.
* It reads sentence by sentence. Swipe left/right for next/previous sentence, tap to pause,
  pinch to zoom 1× to 3× ("Zoom 2 times" spoken when you stop pinching, label green up
  to 2×, orange above).
* Low confidence prefixes "Not sure, but it says…".
* **Failure coaching is a feature, not a bug, so show it.** Put the paperback under the
  darkest corner of the table: "It's too dark to read. Turn on a light or move closer to a
  window." Hold the menu too close: "The text is too close. Move it a little farther away."
  Tilt the glossy medicine box into the light: "There's glare on the text. Tilt it slightly
  away from the light." Visitors trust a device more when it tells them *why* it failed.
* Lines already read are not repeated when they move down the page. Demonstrate by sliding
  the paperback slowly upward.

### 2.5 Inside (the display model on the table)

The visitor points the tablet at the physical Halo on its stand. The app recognises it and
a 3D twin rises out of the camera view, anchored to the model.

* **Recognition.** Browser image tracking (MindAR, runs in Safari and Chrome without an
  install). The target is a photo of the model from the angle visitors will stand at, plus a
  printed card under the stand that says only "Vantage Halo" in the brand type. The card is
  the reliable anchor; the photo is the nice-to-have. A small "Open the Halo" button in the
  corner does the same thing without the camera, for when booth lighting defeats tracking.
* **Exploded view.** A single slider, bottom of the screen, from *assembled* to *apart*.
  Dragging it lifts the parts away from each other along their real mounting axes. Pinch to
  zoom, one finger to orbit. Everything else on screen is hidden until a part is tapped.
* **The parts and their cards.** Tap any part and the rest fades to a wireframe:

  | Part | One-line card | The detail that lands |
  |---|---|---|
  | Raspberry Pi AI Camera (Sony IMX500) | "Sees and recognises. The neural network runs on the sensor itself." | "The processor never sees pixels. It receives boxes, labels and scores." A live counter shows detections per second coming from the Walk room. |
  | Benewake TFmini Plus LiDAR | "Measures distance with a laser, 100 times a second." | 3.6° beam drawn as a thin cone out of the model; "0.1 to 12 m; the firmware drops weak returns and medians the rest." |
  | Compute Module 5 on Waveshare carrier | "Fuses camera and laser, decides what to say." | The fusion step animated: the beam cone lands on a box, the box turns red. |
  | Shokz bone-conduction headset | "Speech through the cheekbones. Ears stay open to the world." | A waveform travels along the headset arm; "Bluetooth, auto-reconnect, two-tone beep so critical alerts are felt, not just heard." |
  | Battery and frame | "A day on a charge." (use the real figure) | Weight and runtime. |

* **X-ray mode.** With the model recognised, a toggle lets the visitor sweep the tablet over
  the physical Halo and see the labelled parts overlaid in place, like an X-ray. Simple,
  reliable, and it is the photo people will take.

### 2.6 Under the hood (hidden, for judges)

Four-finger tap anywhere. A live diagram of the real pipeline:

```
camera ─► tracker ─► fusion ─► announcer ─► speech queue ─► headset
LiDAR ──────────────┘
```

Real messages flow along it as the Walk room runs. You see an INFO message sit in the queue,
then a CRITICAL arrive and sweep it out. You see a message age past its max age and be
dropped unspoken. Below it, the terminal dashboard the device shows over SSH: FPS,
distance, strength, speed, TTC, objects list, audio sink, recent events. All numbers are
real numbers from the running app, with the LiDAR fields labelled "est." A toggle switches
to a recorded 20-second log from the real device so judges can compare.

---

## 3. What makes it not tacky

* **No mascots, no confetti, no gamification.** The replay in Trust is the only reward.
* **One disclaimer, one place, small.** It is honest without apologising repeatedly.
* **The device's own words.** Every spoken phrase is lifted from the firmware. "Vantage
  ready", "Clear", "Not sure, but it says", "Zoom 2 times". If the pitch deck ever shows the
  real Halo stream, it will match what visitors already saw.
* **Dark UI, one accent colour** (the red the device uses for the target box), the system
  font, and silence where silence is the point.
* **Failure shown on purpose.** The reader's coaching lines, the "Obstacle" fallback when
  something is not recognised, the weak-signal note in the LiDAR card. Products that admit
  limits read as real.

---

## 4. Build plan for tonight

Everything is one static web page plus model files. It runs from a laptop on the booth
(HTTPS is required for camera access, so use `mkcert` on the laptop and a hotspot, or
GitHub Pages with the models cached by a service worker so it works offline after the
first load). Test on the actual tablet, not a laptop; Safari and Chrome differ on camera
and speech.

| Piece | Library | Why |
|---|---|---|
| Object detection | MediaPipe Tasks Vision `ObjectDetector` (EfficientDet-Lite0) or TF.js `coco-ssd` | Same COCO-80 label set as the Halo's MobileNet-SSD, so the same `SPOKEN_NAMES` table applies. 15 to 25 fps on a recent tablet. |
| Tracker, fusion, announcer | Port from `vantage_core.py` to JS by hand | About 300 lines: IoU tracker with 2-hit confirmation, hysteresis, priority queue with pre-emption and max-age drop, `spoken_distance`, `direction_of`. Do this first; it is the heart. |
| Range estimate | Box height × class prior / focal length | 40 lines. Priors for person, chair, bottle, cup, laptop, backpack, dog. Smooth, then slope for TTC. |
| Speech | Web Speech API `speechSynthesis` | Zero setup. Pre-warm one utterance on first tap so the first word is not clipped. The two-tone beep and click are 1 kHz / 1.3 kHz oscillators in WebAudio with 150 ms leading silence. |
| Haptic | `navigator.vibrate` on CRITICAL | Android only; silently absent on iPad. |
| OCR | Tesseract.js (eng, cached) | 1 to 2 s per capture on a tablet. Do the same preprocessing as the reader: crop to text, grey, contrast, resize to ~30 px x-height, deskew via the OSD. |
| Steadiness | `DeviceMotionEvent` | 0.7 s under threshold triggers capture. |
| 3D model | `<model-viewer>` or three.js with a GLB | If no CAD exists, build the twin from primitives tonight: a slab for the carrier, a cube for the camera, a cylinder for the LiDAR, a torus arc for the headset. Clean primitives with good lighting beat a bad mesh. |
| Image tracking | MindAR (image targets) | Compile the target from a photo of the model and the printed card. Always ship the "Open the Halo" button as fallback. |

Suggested order, with cut lines:

1. **Must ship.** Wear → Walk → Trust with the ported announcer and the Halo-style overlay.
   Pair Shokz. Neck strap. Four to five hours.
2. **Should ship.** Read with auto-capture, meters and coaching lines. Two to three hours.
3. **Should ship.** Inside with the slider and five part cards, button-triggered. Two hours.
4. **Nice.** Marker tracking for Inside, X-ray mode. One hour if MindAR cooperates, cut if not.
5. **Nice.** Under the hood diagram and recorded device log. One hour.

A fallback for the whole thing: `python3 vantage_core.py --simulate --stream-port 8080` on
the laptop and open the stream on the tablet. It is real firmware with a synthetic scene and
takes five minutes to set up. Keep it running in a second tab all day.

---

## 5. The booth

* A neck strap or chest harness for the tablet, so hands are free and the camera is at
  Halo height. A phone case with a lanyard loop works for a phone.
* Shokz paired to the tablet before the doors open. Keep a second pair paired to a phone.
* The course: two chairs offset, a traffic cone (it is in COCO as "stop sign"-adjacent;
  use a chair or a backpack instead if detection is unreliable), and a booth helper who
  steps in as the "person" at the 50 cm mark. Four metres is enough.
* Reading props: a laminated menu (matte, not glossy), a real medicine box, a paperback.
  Plus a desk lamp you can switch off for the "too dark" line.
* The display model on a stand, printed "Vantage Halo" card beneath it, the photo target
  shot in booth light that morning.
* A QR code on the table that opens the same page on a visitor's own phone, so they leave
  with it. The page works without the headset; speech comes from the phone speaker.

---

## 6. Three-minute script

1. *"Put this on. This is where the Halo sits."* Strap, Shokz on. "Vantage ready."
2. Walk toward the chair. They hear "Chair ahead, 90 centimeters", then the beep and
   "Chair too close, 45 centimeters". Point at the screen: *"Red box, that's the one the
   laser is on. The bar on the right is the distance."*
3. The helper steps in from the side. "Person on your left." Then they walk toward the
   helper: "Person ahead, 1.2 meters, approaching fast." Nobody has to say "time to contact";
   the banner shows it.
4. *"Now close your eyes."* Tap. Black screen. They walk the course by ear. Ten seconds.
   Screen comes back with the replay. Let them look at it without talking.
5. Pick up the medicine box. Hold still. Click. "Paracetamol 500 milligrams. Take 1 or 2
   tablets every 4 to 6 hours." Swipe to skip a sentence. Switch the lamp off: "It's too
   dark to read."
6. Point at the model. Slide it apart. Tap the camera: *"The network runs on the sensor.
   The computer never sees pixels."* Tap the LiDAR: the beam cone. Tap the headset.
7. *"Scan this and it's on your phone."*

---

## 7. Open points

* The Vantage context file and pitch decks mentioned in the brief are not in this
  repository or in any repository this session can reach. The hardware list, feature set and
  spoken phrases above come from `README.md`, `vantage_core.py` and `vantage_reader.py`. If
  the deck names features the firmware does not have yet, decide tonight whether they belong
  in the demo at all; the recommendation is no.
* Battery, weight and runtime figures for the Inside cards need real numbers.
* If there is a CAD or STEP file of the Halo housing, a GLB export tonight replaces the
  primitives and makes the Inside room considerably stronger.
