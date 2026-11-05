# Vantage for Meta glasses: agent rules

Read docs/SPEC.md first; it is the product in one page. Then the Meta DAT plugin skills (mwdat-android).

- The app is Meta's CameraAccess sample plus one layer: `app/src/main/java/com/vantage/glasses/assist/`. Keep the SDK lifecycle code as Meta wrote it.
- One trigger, one frame, one answer. Never stream frames to the model and never grab a frame without a tap or a spoken request.
- Spoken answers: answer first, under 20 words, obstacle then distance then direction then instruction. Numbers as words. Doubt in the first person. Edit prompts in `VantagePrompts.kt`, not in the view model.
- Acknowledge within 0.5 s (earcon), answer in about 3 s, never silent over 2 s. Every failure ends with something the wearer can do; at most three errors in a row; one apology.
- Never identify people. No face, voice or identity features, ever.
- Privacy: frames, transcripts and keys never reach logs. The frame is recycled right after the call. Secrets live in `local.properties` only.
- Speech stays behind `SpeechInput` so the glasses' Speech capability can replace the phone recognizer.
- Use `DatResult.fold / onSuccess / onFailure { error, _ -> }`; add capabilities only after `DeviceSessionState.STARTED`.
- Small steps: plan, build one step, run it on the Mock Device Kit, commit, tag (`step-1`, `step-2`, ...).
- Build: `./gradlew assembleDebug`. Tests: `./gradlew test`. Lint: `./gradlew lint`.
