# Vantage for Meta glasses

**One tap. One picture. One breath.** Vantage is a guide in the ear for blind and low-vision people.
Point your head, tap Look, Read or Ask, and hear one spoken line: *"Scooter ahead, two metres, on
your right. Keep left."*

This is the Meta Wearables Studio build of Vantage. It is Meta's `CameraAccess` sample from the
[Device Access Toolkit](https://github.com/facebook/meta-wearables-dat-android) (DAT 1.0.1), plus one
layer, `app/src/main/java/com/vantage/glasses/assist/`, that takes one frame from the glasses
camera, sends it with a question to Muse Spark on Meta Model API, and speaks the answer through the
glasses. It runs today on the **Mock Device Kit**, where the phone's camera, mic and speaker stand
in for the glasses, with the same SDK calls as real glasses.

The original Vantage, a Raspberry Pi CM5 headset with an AI camera and LiDAR, lives one folder up
(`vantage_core.py`, `vantage_reader.py`). Its spoken format and its lessons (short, flicker-free
speech; reading matters most; hazards first) shaped this app.

## The product story on one page

- **Job story.** When I stop at a decision point with my cane in one hand, I want to know what is in
  front of me and what the sign or box says, so I can decide without asking a stranger.
- **Dialog.** docs/DIALOG.md: a six-turn happy path and two repair paths (didn't hear, no connection).
- **First turn running.** Tap Look on the mock device: earcon in under half a second, spoken answer in
  about three seconds, latency shown on screen.
- **Spec.** docs/SPEC.md, one page. **Privacy copy and PDPL notes.** docs/PRIVACY.md.
  **60-second demo and pitch.** docs/DEMO.md. **30-case eval set.** docs/EVALS.md.
  **Agent rules.** AGENTS.md (also CLAUDE.md).

## What it does

| Mode | Trigger | Vantage says |
|---|---|---|
| **Alerts** | Off by default; the "Alerts" pill or Settings turns obstacle mode on | On-device detector + the firmware's announcer: "Person too close, forty centimetres" with the two-tone beep; "Chair ahead, eighty centimetres". No frame leaves the phone. Silent during any Look / Read / Shelf / Ask turn and for three seconds after. |
| **Look** | Tap anywhere, Look button, "look" | Nearest hazard, distance, direction, one instruction. Under 20 words. |
| **Read** | Double tap, Read button, "read" | The text in view, in reading order. "More below" after ~80 words. |
| **Shelf** | Swipe up, Shelf button, "shelf", "prices" | The gist ladder: a 12-word gist, then "more" (one line per kind), "exact" (every item and price), "cheapest", "where is the milk", "price of the juice", all from memory. |
| **Ask** | Press and hold, Ask button, then speak | The answer first, under 20 words. |
| **Scene** | "what's around me" | The whole scene from the on-device detector. |

Always available: **Again** (swipe back), **Stop** (swipe down), **Help**. Earcons: listening, working,
click on capture, done, error, and the firmware's two-tone alert. The amber glow at the frame edge
grows as something gets closer; the hazard line reads CLEAR / CAUTION / STOP. Controls fade four
seconds after the last touch. Speech doubt is in the first person. People are never identified.

Settings (gear): the same sliders as vantage_core.py (critical and warning distance, repeat
interval, speech rate), awareness, describe mode, beep, gestures, voice language, the Ask question
chips in English and Arabic, and the speech-queue events (priority, stale drops, sweeps).

```
 glasses camera ──► DAT stream ──► preview surface ──PixelCopy──► one JPEG (≤768 px)
                                                                       │
 glasses mic ───► SpeechInput (phone recognizer today, DAT Speech later)│
                                                                       ▼
                     Muse Spark (Meta Model API, OpenAI-compatible) ◄──┘
                                                                       │
 glasses speakers ◄── SpokenOutput (Android TTS over Bluetooth) ◄──────┘
```

## Run it on the Mock Device Kit (no glasses needed)

You need Android Studio (Narwhal 2025.1.1 or newer), JDK 17+, Android SDK 36, an Android 12+ phone
with USB debugging on, and a Meta Model API key from [dev.meta.ai](https://dev.meta.ai/).

1. Copy `local.properties.example` to `local.properties`. Set `sdk.dir` and `meta_api_key`
   (`meta_model_id` defaults to `muse-spark-1.3`). This file is git-ignored.
2. Open the `vantage-glasses` folder in Android Studio, let Gradle sync, run **app** on the phone.
3. In the app tap the **Debug** (bug) button → **Enable MockDeviceKit** → **Pair Ray-Ban Meta** →
   switch on **Power**, **Unfolded**, **Donned** → **Camera source: Back camera** → close the sheet.
4. Tap **Start session**, then **Preview**. The phone camera now stands in for the glasses.
5. Tap **Look**. Allow the microphone the first time you tap **Ask**.

**Arabic.** Tap the **EN / AR** chip in the answer card. Replies, the recognizer and the voice all
switch; the fixed lines (help, repair ladder) are translated. The phone needs an Arabic
text-to-speech voice: Settings → General management → Text-to-speech → Google → Install voice
data → Arabic.

**Other models.** The client is OpenAI-compatible, so Gemini or OpenAI can stand in while Meta
billing is pending: see the commented lines in `local.properties.example`. Keep Muse Spark for
the Studio demo.

On real glasses: turn on Developer Mode in the Meta AI app, skip step 3, and tap **Connect my
glasses**. The camera permission is granted in the Meta AI app. Everything else is the same.

## Where things are

| File | What |
|---|---|
| `assist/AssistViewModel.kt` | The turn: earcon → one frame → model → speak → done. Latency budget, repair ladder, shelf ladder, scene memory. |
| `assist/ShelfTalk.kt` | Gist → More → Exact. Parses the model's JSON once; every follow-up is answered from memory. |
| `awareness/Announcer.kt` | vantage_core.py's decision logic: tracker, range from box height, hysteresis, repeats, describe mode. |
| `awareness/MediaPipeDetector.kt` | EfficientDet-Lite0 on the phone, the Lens demo's network. |
| `voice/Arabic.kt` | The Lens demo's Arabic grammar: counted nouns, distances, prices. |
| `voice/SpeechQueue.kt` | Priority queue: critical sweeps and interrupts, stale messages are dropped. |
| `ui/VantageOverlay.kt` | Hazard glow and line, caption card, shelf list, gesture layer, controls, settings sheet. |
| `assist/VantagePrompts.kt` | System prompts per mode, voice command grammar, repair lines, answer tidying. |
| `assist/MetaModelClient.kt` | Chat-completions call with the frame as a data URL. No frames or keys in logs. |
| `assist/SpeechInput.kt` | `SpeechInput` interface + Android recognizer. Swap for DAT Speech here. |
| `assist/SpokenOutput.kt` | Android TTS plus the four earcons. |
| `camera/CameraViewModel.kt` | Meta's lifecycle code, plus `grabFrame()` (PixelCopy, `capturePhoto()` fallback). |
| `ui/AssistPanel.kt` | Look / Read / Ask pills, transcript and answer card, always-visible privacy line. |

Build from the terminal with `./gradlew assembleDebug`; the Meta plugin's `mwdat-android` skills and
the docs MCP server (`https://mcp.developer.meta.com/wearables`) cover the SDK.

## Trust

One picture is taken when you tap. You hear a tone when it is taken. It is sent once over TLS,
answered, and dropped. Nothing is stored, nothing is logged, nobody is identified. The API key is
in `local.properties` for the prototype and moves to a backend before any tester build. Full notes,
UAE PDPL mapping and the release checklist: docs/PRIVACY.md.
