# Vantage: privacy, security and trust

## Privacy copy (what the app says, on screen and in the store listing)

> **One picture is taken when you tap. Sent, answered, deleted. Nothing is stored.**
>
> Vantage takes a single picture from your glasses only when you press Look, Read or Ask, or say a command. You hear a short tone the moment it is taken. The picture and your question go to Meta's Model API over an encrypted connection to produce one spoken answer, then the picture is discarded from the phone. Vantage keeps no pictures, no audio and no transcripts. It never identifies people. You can stop at any time with the Stop button or the word "stop".

## What we capture, keep and send

| Data | Captured when | Kept | Sent to | Deleted |
|---|---|---|---|---|
| Camera frame (one, ≤768 px JPEG) | Wearer's trigger only | In memory for one call | Meta Model API (TLS) | Recycled right after the call |
| Spoken question | While the mic earcon plays, bounded by 1.2 s silence | Text only, on screen for the session | Meta Model API, as text | Cleared on next turn or app close |
| Answer | After the call | On screen until next turn | Nowhere | Cleared on next turn |
| Logs | Always | Device log buffer | Nowhere | Timings, mode and status codes only; **no frames, transcripts or tokens** |
| Location | Never | | | |

## Capture on intent, and bystanders

- No frame leaves the glasses without a tap or a spoken command. There is no always-on mode in this app.
- The earcon marks the capture; on real glasses the capture LED also lights. An indicator helps awareness, it is not consent.
- The prompt forbids identifying or describing faces, identities or protected characteristics; people are "a person". Face or voice identification would need Meta's approval and is out of scope.
- If someone objects: stop (button or "stop"), nothing was stored, so nothing needs deleting; the event is logged as a cancelled turn.

## Keys and processing

- Today (prototype) the Meta Model API key is read from `local.properties` into `BuildConfig`, which is excluded from git. This is the workshop pattern and is fine for a mock or Developer Mode build.
- Before any build is handed to testers, the call moves to a small backend that holds the key and issues short-lived tokens to the app. `MetaModelClient` is the one place to change.
- SDK pinned: `mwdat = 1.0.1`. Read the changelog before upgrading; Speech and Inputs are experimental.
- Processing location: Meta Model API. Before release we confirm retention, training use and processing country with Meta, and document the overseas-transfer basis under UAE PDPL (Federal Decree-Law No. 45 of 2021). Images and voice are personal data; derived descriptions are too.

## Five questions before it ships

1. **What personal data?** One camera frame (may include bystanders), one spoken question, both transient.
2. **Why, on what basis?** To describe the wearer's surroundings on request; consent, given per tap, withdrawable by not tapping or by "stop".
3. **Who receives it?** Meta Model API only. No analytics SDKs.
4. **Where does it go?** Meta's servers; country to be confirmed and stated in the notice.
5. **How long, who deletes?** Not stored by the app. Meta's retention for API inputs to be confirmed and stated.

## Security tests (pass / fail before each demo)

- Network drops mid-call → spoken "No connection right now. Try again in a moment.", UI returns to idle.
- Session ends during processing → stream teardown cascades, no crash, next tap says "I don't have a picture yet."
- API key missing → on-screen notice, spoken "Vantage isn't set up yet.", no call made.
- Debug logging on → `adb logcat` shows no image bytes, no transcript text, no bearer token.
- User asks for deletion → nothing to delete; the notice says so plainly.

## Release readiness

| Check | Status |
|---|---|
| Purpose stated in-app | Green |
| Permissions asked in context (camera via Meta AI app, mic on first Ask) | Green |
| Personal data minimised (one frame, downscaled) | Green |
| Processing location documented | Amber: confirm with Meta |
| Security controls (TLS, no logs, key off device) | Amber: key still on device in prototype |
| Retention and deletion | Green (none kept) |
| Bystanders (visible capture, no identification) | Green |
| Legal and platform review | Red until PDPL transfer basis and Meta review are done |
