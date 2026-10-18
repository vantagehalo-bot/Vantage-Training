# Vantage Lens — the Halo, in your hands

A proposal for tomorrow's demo. One web app on the tablet. The visitor holds the tablet,
wears a Shokz headset paired to it, and walks through a virtual home, street and shop as a
Halo wearer, hearing exactly what the Halo would say. Then they turn the same tablet toward
the table to read real print and to open up the display model.

Constraints this is built for: the tablet is hand-held, nobody wears it. The booth has no
room to walk. The CM5 is not available. Shokz are available.

> Source of truth for every behaviour below is `vantage_core.py` and `vantage_reader.py`.
> The demo invents no feature the device does not have, and it uses the device's own words.
> That restraint is what keeps it from being tacky.

---

## 1. The one idea

**You can't walk the booth, so the world walks past the Halo.**

The visitor holds the tablet as a window. On screen is a first-person view of a place they
know: a kitchen at night, a pavement at rush hour, a pharmacy aisle. They move with a thumb.
Everything the Halo would do in that place happens for real, in software, on the tablet:
the detector finds the objects, the laser beam measures the thing it lands on, the announcer
decides what matters, and the Shokz speaks it into their cheekbones.

Why virtual is the stronger demo, not the fallback:

* **Ground truth.** The app knows where every object is, so the simulated TFmini is a true
  raycast with the real 3.6° beam, the real 12 m range, and the real failure modes (weak
  return off black and glass). The phone-camera version could only guess distance.
* **Scenes you cannot stage at a booth.** A cyclist closing at 5 m/s. A glass door. A
  cupboard door left open at head height. A platform edge. A dog.
* **Eyes-closed mode works without anyone moving.** The screen goes black and they steer
  through the kitchen by sound alone. That is the moment people remember, and it needs
  one square metre of floor.
* **The split view.** Left half: the world as a sighted person sees it. Right half: what the
  Halo sees, drawn exactly like the device's own preview. The gap between the two is the
  pitch.

The camera is still used, for the two things only a camera can do: reading real print on
the table, and opening the display model.

---

## 2. The journey

| Room | Input | What they do | Halo features proved |
|---|---|---|---|
| **Wear** | — | Headset check, pick a voice, "Vantage ready" | Bone-conduction audio, beep, voice settings |
| **Walk** | 3D scenes | Move through home / street / shop with the Halo narrating | Detection, tracker, fusion, LiDAR, TTC, hysteresis, describe mode, speak-scene |
| **Trust** | 3D, black screen | Same kitchen, by ear only | The product's reason to exist |
| **Read** | Camera | Point at the menu, the medicine box, the paperback on the table | Auto-capture, meters, OCR, sentence playback, zoom, failure coaching |
| **Inside** | Camera | Point at the display model, it opens into parts | Hardware: IMX500, TFmini Plus, CM5, Shokz |
| **Under the hood** | hidden | Live pipeline and dashboard | For technical judges |

Three minutes end to end, or ten in any one room.

---

## 3. Room by room

### 3.1 Wear (20 seconds)

Dark screen, one line: *"Put the headset on. Hold the tablet like a window."*

* The app plays the device's real two-tone beep (two short rising tones with 150 ms of
  leading silence so the Bluetooth sink wakes, as in the firmware). "Did you feel that?"
* Voice picker, three voices, rate slider at 175 wpm. The chosen voice says "Vantage ready",
  the device's own boot line.
* One small grey footer line, present wherever something is simulated and nowhere else:
  *"Simulated on this tablet. On the Halo the detector runs on the camera sensor and the
  distance comes from a laser."* It never repeats itself and nothing else apologises.

### 3.2 Walk (the core, 60 to 120 seconds)

**Layout.** The tablet in landscape. Left half, the world rendered plainly, soft light,
nothing stylised. Right half, the same view through the Halo: coloured boxes with label and
confidence, the target box red with its distance, the LiDAR crosshair, the distance bar with
50 cm and 100 cm ticks on the right edge, the flashing banner
`!! PERSON TOO CLOSE, 40 CENTIMETERS (TTC 0.6s)`, and the bottom line showing exactly what
was just spoken with its priority tag. A pinch swaps to full-screen Halo view. On a phone,
portrait, the two views stack.

**Movement.** Left thumb, a soft joystick: push forward to walk at a slow walking pace,
1 m/s. Right thumb drags to look. A "Guide me" toggle puts the visitor on a gentle rail
through the scene so they only choose how fast, which is how most visitors will use it.
A rail takes 40 seconds per scene and passes every set piece.

**Scenes** (pick two for the demo, ship three if time allows):

| Scene | Set pieces | Why it's there |
|---|---|---|
| **Home, evening** | Kitchen table and chairs; a chair pulled out into the path; a cupboard door left open at head height; a dog that wanders; a glass patio door; a hallway with a coat on a hook | Chair ahead → chair too close. The open cupboard is the one visitors wince at. The glass door is the LiDAR's weak-return case: the beam says nothing, the box fills the frame, the Halo says "Obstacle very close". The dog triggers "Dog on your left". |
| **Street, morning** | Pavement; bollards; a bus-stop sign reading "Trains to Central Station, Next departure 10:45"; pedestrians walking toward and past; a cyclist cutting across at 5 m/s; a parked bike; a kerb | "Person ahead, 1.5 meters, approaching fast" with the TTC visible. The cyclist shows pre-emption: an INFO message is swept out by a CRITICAL. The sign is readable in Read mode. |
| **Pharmacy** | Shelves; a shop assistant; a basket on the floor; a "Paracetamol 500 mg" box within reach; a low display stand | Floor-level obstacles, a person who stands still then moves, and a handoff into Read. |

The sign text and the paracetamol box are the strings the reader firmware already ships in
its own simulated scenes, so the two programs tell one story.

**The Halo logic is a straight port, not an imitation.** What the visitor hears is what a
wearer hears:

| Situation | Spoken | Priority and rule |
|---|---|---|
| Target under 50 cm | beep, then "Person too close, 40 centimeters" | CRITICAL. Pre-empts everything. Repeats every 2.5 s while it stays close. Repeats at once if the object changes. |
| Under 100 cm, or time-to-contact under 1.5 s | "Chair ahead, 80 centimeters, approaching fast" | WARNING |
| Close, not recognised | "Obstacle too close, 35 centimeters" | CRITICAL |
| No LiDAR return but a box over 55 % of frame height | "Person very close" | CRITICAL |
| Describe mode, newly confirmed object | "Dog on your left" (left third / centre / right third) | INFO |
| Two-finger tap (the device's `s` key) | "Person ahead, chair on your right. Distance ahead 1.2 meters" | INFO |
| Nothing | "Clear" once, then silence | INFO |

Also ported because they are what make it feel like a product: two consecutive frames before
an object is trusted; 8 cm hysteresis at both thresholds; messages past their max age
(1 to 2.5 s) are dropped unspoken; distances quantised to 5 cm under a metre and 0.1 m
above, said as "1 meter", "1.5 meters", "2 meters".

**Simulating the sensors honestly.**

* *IMX500 detector.* Each scene object carries its COCO label (person, chair, dog, bicycle,
  bottle, dining table, potted plant, tv, backpack, bench). Per frame the app projects the
  object's bounds to the screen, jitters the box a few pixels, draws a confidence from a
  per-class range (people 0.8 to 0.95, a chair side-on 0.55 to 0.8), drops a detection
  entirely 5 % of the time, and runs it through the ported IoU tracker. The result looks
  like a real detector output, flicker and all, which is exactly why the 2-hit rule exists
  and the visitor can watch it work.
* *TFmini Plus.* A raycast from the camera position, offset by the configurable mount
  offset, with a 3.6° cone (take the nearest hit inside the cone). Range 0.1 to 12 m.
  Materials are tagged: glass and gloss black return a weak signal (strength under 100), so
  the reading is discarded and the vision fallback kicks in, as in the firmware. Closing
  speed is the least-squares slope over the last 0.5 s, TTC is distance over speed.
* *Fusion.* The box that contains the beam's screen point owns the distance. Draw the
  crosshair there.

**Settings sheet** (swipe down): critical 50 cm, warning 100 cm, repeat 2.5 s, threshold
0.55, describe mode, LiDAR offset. A technical visitor dragging the critical threshold to
80 cm and watching the banner fire earlier is a stronger moment than any animation.

### 3.3 Trust (the moment)

After one scene, a single button: **"Now by ear."**

* The screen goes black except for a faint ring under the left thumb so they know where the
  joystick is. The kitchen reloads with the furniture shuffled so they cannot replay it from
  memory.
* They steer to the far door using only what the Shokz tells them. Twenty seconds. No timer
  on screen, no score, no sound effects beyond the Halo's own voice.
* When they reach the door, or tap the ring, the screen returns with a **replay**: a split
  view scrubbing through their path, the Halo view on the right, the spoken timeline
  underneath. "You turned here because you heard this." No fanfare. The replay is the reward.
* If they bumped something, the replay shows it, quietly. The Halo had said "Chair too
  close, 45 centimeters" 0.8 s before. That is honest and it is persuasive.

### 3.4 Read (camera)

The visitor turns the tablet toward the props on the table: a matte menu, a real medicine
box, a paperback. The screen becomes the reader preview:

* Text lines outlined, with live **sharp / light / steady** meters. Steady comes from the
  tablet's motion sensors, 0.7 s still as in the firmware. Sharp is the Laplacian variance
  of the text region. Light is mean luminance.
* Steady and sharp: the device's click, a burst of 5 frames, keep the sharpest, OCR on the
  tablet.
* Each word boxed and coloured by confidence; right panel shows the text with the spoken
  sentence highlighted. Swipe for next / previous sentence, tap to pause, pinch to zoom
  1× to 3× ("Zoom 2 times" spoken when the pinch stops; label green to 2×, orange above).
* Low confidence prefixes "Not sure, but it says…".
* **Show the coaching on purpose.** Lamp off: "It's too dark to read. Turn on a light or
  move closer to a window." Too close: "The text is too close. Move it a little farther
  away." Glossy box into the light: "There's glare on the text. Tilt it slightly away from
  the light." A device that explains its failures is one people trust.
* Slide the paperback slowly upward: only the new lines are read.

### 3.5 Inside (camera, the display model)

Point the tablet at the Halo on its stand. A 3D twin rises out of the camera view, anchored
to the model.

* **Recognition.** Browser image tracking (MindAR). Target: a printed card under the stand
  that says only "Vantage Halo" in the brand type, plus a photo of the model shot in booth
  light tomorrow morning. The card is the reliable anchor. An "Open the Halo" button in the
  corner does the same without the camera, for when the lighting wins.
* **Exploded view.** One slider along the bottom, from *assembled* to *apart*. Parts lift
  along their real mounting axes. Pinch to zoom, one finger to orbit. Nothing else on
  screen until a part is tapped.
* **Part cards.** Tap a part; the rest fades to wireframe.

  | Part | One line | The detail that lands |
  |---|---|---|
  | Raspberry Pi AI Camera, Sony IMX500 | "Sees and recognises. The network runs on the sensor itself." | "The processor never sees pixels. It receives boxes, labels and scores." A live counter of detections per second from the Walk scene still running underneath. |
  | Benewake TFmini Plus | "Measures distance with a laser, 100 times a second." | The 3.6° cone drawn out of the model. "0.1 to 12 m. Weak returns off glass and black are discarded, the rest is median-filtered." |
  | Compute Module 5 on the Waveshare carrier | "Fuses camera and laser, decides what to say." | The fusion animated: the cone lands on a box, the box turns red. |
  | Shokz bone-conduction headset | "Speech through the cheekbones. Ears stay open." | A pulse travels along the arm. "Bluetooth, auto-reconnect, a two-tone beep so critical alerts are felt." |
  | Battery and frame | runtime and weight, real figures | |

* **X-ray.** With the model recognised, sweep the tablet over the physical Halo and see the
  parts labelled in place. It is the photo people will take.

### 3.6 Under the hood (four-finger tap)

The real pipeline, live:

```
camera ─► tracker ─► fusion ─► announcer ─► speech queue ─► headset
LiDAR ──────────────┘
```

Messages from the running scene travel along it. An INFO sits in the queue, a CRITICAL
arrives and sweeps it out. A message ages past its limit and is dropped unspoken. Below,
the device's terminal dashboard: FPS, distance, strength, speed, TTC, object list, audio
sink, recent events. All live numbers. A toggle replays a 20-second log recorded from the
real device so a judge can compare the two.

---

## 4. What keeps it from being corny

* **No mascots, no confetti, no points.** The replay in Trust is the only reward.
* **One disclaimer, small, once.** Honest without apologising.
* **The device's own words throughout.** "Vantage ready", "Clear", "Not sure, but it says",
  "Zoom 2 times". If the deck later shows the real Halo stream, it matches what they heard.
* **Plain scenes.** Low-poly furniture with soft lighting, no cartoon shading, no sky
  gradients. The world should look like a quiet architectural model, not a game.
* **Dark UI, one accent** (the red the device uses for the target box), system font, and
  silence where silence is the point.
* **Failure shown on purpose.** The glass door, the reader's coaching lines, the "Obstacle"
  fallback. Products that admit limits read as real.

---

## 5. Build plan for tonight

One static page plus assets, served over HTTPS from the booth laptop (`mkcert` and a phone
hotspot) or GitHub Pages with everything cached by a service worker so it runs with the
venue Wi-Fi down. Test on the real tablet, not a laptop. Safari and Chrome differ on
speech and camera.

| Piece | Library | Notes |
|---|---|---|
| 3D scenes | three.js | Low-poly CC0 furniture (Kenney furniture and city kits are GLB and free). Tag each mesh with a COCO label and a material flag (`glass`, `black`). |
| Movement | Custom: nipple-style joystick + drag look; a spline rail for "Guide me" | Clamp to 1 m/s, collide with walls. |
| Detector sim | 60 lines | Project bounds to screen, jitter, confidence by class, 5 % miss, feed the tracker. |
| LiDAR sim | three.js `Raycaster` | Cone sampling with 5 rays, nearest hit, strength from material, 100 Hz tick independent of render rate. |
| Tracker, fusion, announcer | Hand port of `vantage_core.py` | About 300 lines: IoU tracker with 2-hit confirmation, hysteresis, priority queue with pre-emption and max-age drop, `spoken_distance`, `direction_of`, `SPOKEN_NAMES`. **Build this first.** It is the heart and it is shared by every room. |
| Speech | Web Speech API | Pre-warm one utterance on first tap so the first word isn't clipped. Beep and click are WebAudio oscillators with 150 ms leading silence. |
| Halo overlay | Canvas 2D | Identical drawing to the device preview. |
| OCR | Tesseract.js, `eng` cached | 1 to 2 s per capture. Same preprocessing as the reader: crop, grey, contrast, resize to ~30 px x-height, OSD rotate. |
| Steadiness | `DeviceMotionEvent` | 0.7 s under threshold. |
| 3D twin | `<model-viewer>` or three.js GLB | If there is no CAD, build it tonight from primitives: slab for the carrier, cube for the camera, cylinder for the LiDAR, arc for the headset. Clean primitives with good lighting beat a bad mesh. |
| Image tracking | MindAR image targets | Compile from the card and a photo. Always ship the button fallback. |

Order, with cut lines:

1. **Must ship.** Announcer port → Home scene → split view → Wear → Trust. Five hours.
2. **Should ship.** Street scene with the cyclist and the sign. Ninety minutes.
3. **Should ship.** Read. Two hours.
4. **Should ship.** Inside, button-triggered, with five cards. Two hours.
5. **Nice.** Marker tracking and X-ray. One hour, cut if MindAR misbehaves.
6. **Nice.** Pharmacy scene. Under the hood. One hour each.

Whole-demo fallback: `python3 vantage_core.py --simulate --stream-port 8080` on the laptop,
open the stream on the tablet. Real firmware, synthetic scene, five minutes to set up. Keep
it in a second tab all day.

---

## 6. The booth

* Tablet in a grippy case, landscape. A phone as a second station running the same page.
* Shokz paired to the tablet before doors open. A second pair paired to the phone.
* Reading props: a laminated matte menu, a real medicine box, a paperback. A small lamp
  with a switch, for the "too dark" line.
* The display model on its stand, the printed "Vantage Halo" card beneath it, the photo
  target shot in booth light that morning.
* A QR code that opens the page on a visitor's own phone. It works without the headset.

---

## 7. Three-minute script

1. *"Headset on. Hold this like a window. You're standing in a kitchen with the Halo on."*
   "Vantage ready."
2. Guide-me rail starts. Toward the table: "Chair ahead, 90 centimeters." Beep. "Chair too
   close, 45 centimeters." Point at the right half: *"Red box, that's the one the laser is
   on. The bar is the distance."*
3. The dog crosses: "Dog on your left." The open cupboard door at head height: "Obstacle too
   close, 35 centimeters." *"It doesn't need to know what it is to keep you from it."*
4. The glass door. The beam reads nothing; the box fills the frame; "Obstacle very close."
   *"Lasers don't see glass. The camera does. That's why there are two."*
5. *"Now by ear."* Black screen. They steer to the door. Twenty seconds. Replay. Let them
   look at it.
6. Street scene, thirty seconds: the cyclist. "Person ahead, 2 meters, approaching fast."
   Point at the TTC on the banner.
7. Turn the tablet to the table. The medicine box. Click. "Paracetamol 500 milligrams. Take
   1 or 2 tablets every 4 to 6 hours." Lamp off. "It's too dark to read."
8. Point at the model. Slide it apart. Camera: *"The network runs on the sensor."* LiDAR:
   the cone. Headset.
9. *"Scan this and it's on your phone."*

---

## 8. Open points

* The Vantage context document saved in your Claude memory is not reachable from this
  session. Everything above is from `README.md`, `vantage_core.py` and `vantage_reader.py`.
  Paste it or add it to the repo and the part cards, scene choices and pitch lines can be
  aligned to it.
* Battery, weight and runtime figures for the Inside cards need real numbers.
* A CAD or STEP file of the housing, exported to GLB, would replace the primitive twin.
* Which two scenes to ship if time runs short: Home and Street. Home carries the emotional
  moment; Street carries the technical one.
