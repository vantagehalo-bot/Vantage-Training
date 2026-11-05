# Vantage on Meta glasses: spec (one page)

**Who.** Blind and low-vision adults in the UAE who already walk with a cane or guide dog and want to know *what* is ahead, not just *that* something is ahead. First testers: the people who tried the Raspberry Pi Vantage headset.

**The moment.** Walking an unfamiliar indoor or street route (mall, metro station, office, pharmacy) and stopping at a decision point: a doorway, a crowd, a counter, a sign, a product shelf. The wearer wants an answer within one breath and then silence.

**What goes in.** One frame from the glasses camera, taken only on the wearer's trigger (a phone button today, cap-touch or a spoken command on glasses). For Ask, their question through the microphone. Nothing else: no GPS, no continuous video, no audio recording.

**What comes out.** One spoken line in the open-ear speakers, in Vantage's format: obstacle, distance, direction, instruction. "Scooter ahead, two metres, on your right. Keep left." For Read: the text, in reading order. For Ask: the answer first, under 20 words. Earcons for listening, working, done and error. "Again", "stop" and "help" always work.

**Three modes.**

| Mode | Trigger | Prompt focus | Output |
|---|---|---|---|
| Look | Look button, "look", "what's ahead" | Nearest hazard, then scene | One line, under 20 words |
| Read | Read button, "read" | Text in view, reading order | Up to about 80 words, "more below" |
| Ask | Ask button then speak | The wearer's question | Answer first, under 20 words |

**Architecture.** Phone does the work, glasses lend camera and audio (DAT 1.0). The app is Meta's CameraAccess sample plus an `assist` layer: `CameraViewModel.grabFrame()` (PixelCopy of the preview, `capturePhoto()` fallback) → `MetaModelClient` (Muse Spark on Meta Model API, OpenAI-compatible) → `SpokenOutput` (Android TTS, routed to the glasses over Bluetooth). Voice in is `SpeechInput`, phone recognizer today, glasses Speech capability later. On the Mock Device Kit the phone camera, mic and speaker stand in for the glasses, with the same SDK calls.

**Latency budget.** Earcon < 0.5 s. Spoken answer ≈ 3 s (frame downscaled to 768 px, 160 max tokens). "Looking." spoken at 1.5 s if the model is still working, so silence never passes 2 s. The screen shows ack and total time for every turn.

**Not in v1.** Continuous obstacle alerts (the Pi version does this with LiDAR; on glasses it must start from a user-initiated session), face or person identification (never), navigation directions, Arabic voice (planned: reply in the wearer's language).

**Trust story.** One picture is taken when you tap, you hear an earcon when it is taken, it is sent once over TLS, answered, and deleted. No frames, transcripts or keys in logs. See docs/PRIVACY.md.

**Done when.** The first turn runs on the Mock Device Kit with the phone's back camera; the 30-case eval set in docs/EVALS.md passes twice; a blind tester has used it in the room we will demo in.
