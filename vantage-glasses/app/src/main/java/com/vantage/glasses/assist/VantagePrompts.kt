// VantagePrompts - what Vantage asks the model, and how it talks
//
// Vantage's spoken style, carried over from the Raspberry Pi wearable (vantage_core.py):
// obstacle first, then distance, then direction, then one instruction. "Person ahead, two metres.
// Keep left." One breath, under 20 words, numbers said the way people say them.

package com.vantage.glasses.assist

import java.util.Locale

enum class AssistMode {
  /** Scene and obstacles for safe movement. */
  LOOK,
  /** Read the text in view. */
  READ,
  /** A free question about what is in view. */
  ASK,
}

object VantagePrompts {

  private const val SHARED_RULES =
      """You are Vantage, a guide speaking into the ear of a blind or low-vision person who wears camera glasses. You see exactly one picture from their point of view.
Rules:
- Answer first. One breath: at most 20 words unless the user asked you to read text.
- Plain spoken English. Say numbers as words ("two metres", "three steps"). No lists, no markdown, no emoji.
- Directions from the wearer's view: "on your left", "ahead", "on your right", "low", "above".
- Never identify or describe anyone's face, identity, age, ethnicity or anything that could identify a person. Say "a person".
- If you are not sure, say so in the first person: "I'm not sure, but ...".
- If the picture is too dark, blurry or shows nothing useful, say that and tell them how to move their head ("tilt down a little", "turn slightly right")."""

  val lookSystem: String =
      """$SHARED_RULES
Task: LOOK. Help them move safely in the next few seconds.
Order: 1) the nearest obstacle or hazard: what it is, roughly how far in metres or steps, and where; 2) one instruction ("keep left", "stop", "clear ahead"); 3) if words remain, one short note on the scene (doorway, stairs, crossing, people).
Hazards first: steps, kerbs, holes, vehicles, bikes, scooters, poles, glass doors, wet floor, moving people.
Example: "Scooter ahead, two metres, on your right. Keep left."
Example: "Clear ahead. Doorway about four metres on your left.""""

  val readSystem: String =
      """$SHARED_RULES
Task: READ. Read the text in the picture aloud, in reading order, exactly as written. The 20-word limit does not apply here, but stop after about 80 words and say "more below" if there is more.
Start with the largest or most important text (title, product name, warning), then the rest. Skip decoration and logos.
If letters are cut off at an edge, read what you can and finish with "text continues past the right edge" (or left, top, bottom).
If there is no readable text, say "I don't see text. Move closer or tilt down a little.""""

  val askSystem: String =
      """$SHARED_RULES
Task: ASK. Answer the user's question about what is in the picture. If the answer is not visible, say what you would need to see ("show me the back of the box")."""

  /** The fixed user turn for each mode; ASK uses the spoken question. */
  fun userText(mode: AssistMode, question: String?): String =
      when (mode) {
        AssistMode.LOOK -> "What is ahead of me? Obstacles first."
        AssistMode.READ -> "Read this to me."
        AssistMode.ASK -> question?.trim().takeUnless { it.isNullOrBlank() }
                ?: "What am I looking at?"
      }

  fun systemPrompt(mode: AssistMode): String =
      when (mode) {
        AssistMode.LOOK -> lookSystem
        AssistMode.READ -> readSystem
        AssistMode.ASK -> askSystem
      }

  /** Spoken while the model works, if it takes longer than the acknowledge budget. */
  fun workingLine(mode: AssistMode): String =
      when (mode) {
        AssistMode.LOOK -> "Looking."
        AssistMode.READ -> "Reading."
        AssistMode.ASK -> "On it."
      }

  // Voice commands: verb-first, three words or fewer. "again", "stop" and "help" always work.
  sealed interface Command {
    data object Again : Command

    data object Stop : Command

    data object Help : Command

    data class Run(val mode: AssistMode, val question: String?) : Command
  }

  fun parseCommand(spoken: String): Command {
    val text = spoken.trim().lowercase(Locale.ROOT).trimEnd('.', '?', '!')
    val words = text.split(Regex("\\s+")).filter { it.isNotBlank() }
    if (words.isEmpty()) return Command.Run(AssistMode.LOOK, null)
    val first = words.first()
    val short = words.size <= 3
    return when {
      text == "again" || text == "repeat" || text == "say again" || text == "repeat that" ->
          Command.Again
      text == "stop" || text == "quiet" || text == "cancel" -> Command.Stop
      text == "help" || text == "what can you do" -> Command.Help
      short && (first == "read" || text.startsWith("read ")) -> Command.Run(AssistMode.READ, null)
      short &&
          (first == "look" ||
              first == "describe" ||
              text == "what's ahead" ||
              text == "whats ahead" ||
              text == "what is ahead") -> Command.Run(AssistMode.LOOK, null)
      else -> Command.Run(AssistMode.ASK, spoken.trim())
    }
  }

  const val HELP_LINE = "Say look, read, or ask a question. Again repeats. Stop stops."

  /** Repair ladder: never blame, never say "I didn't hear you", always end with something to do. */
  fun nothingHeardLine(attempt: Int): String =
      if (attempt <= 1) "Say look, read, or a question. Or use the buttons."
      else "Use the Look or Read button on the phone."

  fun offlineLine(): String = "No connection right now. Try again in a moment."

  fun timeoutLine(): String = "That took too long. Ask again?"

  fun rejectedLine(): String = "I can't reach my eyes right now. Try again."

  fun noKeyLine(): String = "Vantage isn't set up yet. Add the API key on the phone."

  fun noFrameLine(): String = "I don't have a picture yet. Start the preview and try again."

  /** Make model output speakable: strip markdown, collapse whitespace, clamp runaway answers. */
  fun tidy(answer: String, mode: AssistMode): String {
    var text =
        answer
            .replace(Regex("[*_#`>\\[\\]]"), "")
            .replace(Regex("\\s+"), " ")
            .trim()
    val maxWords = if (mode == AssistMode.READ) 110 else 32
    val words = text.split(' ')
    if (words.size > maxWords) {
      text = words.take(maxWords).joinToString(" ").trimEnd(',', ';', ':') + "."
    }
    return text
  }
}
