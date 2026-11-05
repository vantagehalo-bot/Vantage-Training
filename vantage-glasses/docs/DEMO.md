# Vantage: the 60-second demo and the pitch

## Setup (do this before the room fills)

1. Phone on Wi-Fi or 4G, volume up, Vantage installed from Android Studio (`local.properties` has the key).
2. Open Vantage → Debug (bug icon) → Enable MockDeviceKit → Pair Ray-Ban Meta → Power, Unfolded, Donned on → Camera source: Back camera → close.
3. Start session → Preview. You should see the phone camera. Tap Look once to warm up TTS and the network.
4. Props: a medicine box or a printed sign, and a chair in the walking line.

## The 60 seconds

| Time | Say | Do |
|---|---|---|
| 0:00 | "Vantage is the guide in your ear for people who can't see what's ahead. We built it on a Raspberry Pi with LiDAR; today it runs on Meta glasses through the Device Access Toolkit, on the Mock Device Kit." | Hold the phone like glasses, pointing down the aisle. |
| 0:12 | "One tap. One picture. One breath." | Tap **Look**. Earcon, then: "Chair ahead, two metres, on your left. Keep right." Point at the latency chip: 0.1 s ack, ~3 s answer. |
| 0:25 | "Reading is the thing our testers asked for most." | Hold up the box. Tap **Read**. It reads the name and dose. |
| 0:40 | "And you can just ask." | Tap **Ask**: "Is there a door on my right?" Answer. |
| 0:50 | "Nothing is stored. Capture only on intent, no face identification, send, answer, delete. That line is on the screen the whole time." | Point at the privacy line. |
| 0:58 | "Next: real glasses, cap-touch trigger, Arabic." | Stop. |

## If it breaks

- No answer, spoken "No connection": switch Wi-Fi to hotspot, tap again. The repair line *is* part of the demo: say "that's the repair ladder working".
- Speech recognizer unavailable: use Look and Read only; say Ask is the voice path and show the transcript field.
- Preview black: Stop preview, Start preview. If still black, toggle Donned off/on in the Debug menu.

## Pitch (3 minutes, for the virtual pitchathon)

1. **Problem.** 285 million people worldwide live with low vision. A cane finds the obstacle; it doesn't say what it is, how far, or what the sign reads. Asking strangers costs independence.
2. **Who.** Blind and low-vision adults in the UAE who already use mobility aids; first testers from the Pi Vantage trial.
3. **Product.** Vantage: one tap, one picture, one breath. Three modes (Look, Read, Ask), earcons, "again / stop / help", Vantage's obstacle-distance-direction-instruction format. Audio first, screen second.
4. **Why Meta glasses.** Camera at eye level, open-ear speakers, hands stay on the cane. DAT 1.0 gives camera and audio today; the phone does the thinking; the Mock Device Kit let us build before hardware arrived.
5. **What we learned from the Pi.** Speech must be short and flicker-free; hysteresis and priority queues matter; people want reading more than scene description; bone-conduction audio works in traffic.
6. **Trust.** Capture on intent, visible capture, no identification, no storage, key off the device before testers. PDPL mapped in docs/PRIVACY.md.
7. **Roadmap.** Real glasses and cap-touch (Nov); glasses Speech capability and Arabic replies; a user-initiated "walk with me" session with short low-frame-rate bursts; 30-case eval set passing twice before any tester build; GITEX demo in December.
8. **Ask.** Glasses for two testers, an intro to Meta's accessibility team, and feedback on the Arabic voice path.
