// VantagePrompts - what Vantage asks the model, and how it talks
//
// Vantage's spoken style, carried over from the Raspberry Pi wearable (vantage_core.py):
// obstacle first, then distance, then direction, then one instruction. "Person ahead, two metres.
// Keep left." One breath, under 20 words, numbers said the way people say them.

package com.vantage.glasses.assist

import java.util.Locale

/** The language Vantage listens and speaks in. Replies never flip to English unasked. */
enum class AssistLanguage(val tag: String, val locale: Locale, val label: String) {
  ENGLISH("en-US", Locale.US, "EN"),
  ARABIC("ar-AE", Locale("ar", "AE"), "AR");

  fun next(): AssistLanguage = if (this == ENGLISH) ARABIC else ENGLISH
}

enum class AssistMode {
  /** Scene and obstacles for safe movement. */
  LOOK,
  /** Read the text in view. */
  READ,
  /** A free question about what is in view. */
  ASK,
  /** A shelf, counter or aisle: items and prices, summarised, then drilled into by voice. */
  SHELF,
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

  val shelfSystem: String =
      """$SHARED_RULES
Task: SHELF. The picture shows a shop shelf, counter, fridge or aisle. Extract what is for sale and reply ONLY with JSON, no prose, no markdown fences:
{"summary": "<one spoken sentence, at most 12 words: how many things, what kinds, where, rough price range>",
 "groups": ["<one short spoken line per kind of product: kind, where it sits, price range>", ...],
 "items": [{"name": "<product as a person would say it, brand first>", "price": <number or null>, "currency": "AED", "position": "left|centre|right", "row": "top|eye|bottom", "note": "<size, flavour, offer, or empty>"}, ...]}
Rules: list at most 12 items, nearest and clearest first. Read prices exactly from tags; null when no tag is readable. Position is where the item sits in the picture from the wearer's view. Never invent an item or a price. If nothing is for sale say so in summary and leave items empty."""

  val askSystem: String =
      """$SHARED_RULES
Task: ASK. Answer the user's question about what is in the picture. If the answer is not visible, say what you would need to see ("show me the back of the box")."""

  /** The fixed user turn for each mode; ASK uses the spoken question. */
  fun userText(mode: AssistMode, question: String?): String =
      when (mode) {
        AssistMode.LOOK -> "What is ahead of me? Obstacles first."
        AssistMode.READ -> "Read this to me."
        AssistMode.SHELF -> "What is on this shelf, with prices?"
        AssistMode.ASK -> question?.trim().takeUnless { it.isNullOrBlank() }
                ?: "What am I looking at?"
      }

  private const val ARABIC_RULE =
      """
Language: reply ONLY in Arabic, simple spoken Modern Standard Arabic as an educated native speaker from the Gulf would say it aloud, with correct number and gender agreement; never a word-for-word translation. Numbers and distances as Arabic words with the correct counted-noun form (على بُعد مترين، ثلاثة أمتار، خمسين سنتيمترًا). Prices in dirhams as words (تسعة دراهم ونصف). Prefer verbal nouns and يُرجى over imperatives so the listener's gender is not assumed. Brand and medicine names as usually written in Arabic (بنادول، باراسيتامول). When reading text, read Arabic print as printed and give other print as a faithful Arabic translation keeping every number, dose and warning. In JSON replies, "summary", "groups", "name" and "note" are Arabic; keys stay English."""

  fun systemPrompt(mode: AssistMode, language: AssistLanguage = AssistLanguage.ENGLISH): String {
    val base =
        when (mode) {
          AssistMode.LOOK -> lookSystem
          AssistMode.READ -> readSystem
          AssistMode.ASK -> askSystem
          AssistMode.SHELF -> shelfSystem
        }
    return if (language == AssistLanguage.ARABIC) base + ARABIC_RULE else base
  }

  /** Spoken while the model works, if it takes longer than the acknowledge budget. */
  fun workingLine(mode: AssistMode, language: AssistLanguage = AssistLanguage.ENGLISH): String =
      if (language == AssistLanguage.ARABIC) {
        when (mode) {
          AssistMode.LOOK -> "أنظر."
          AssistMode.READ -> "أقرأ."
          AssistMode.ASK -> "لحظة."
          AssistMode.SHELF -> "أتفحّص الرف."
        }
      } else {
        when (mode) {
          AssistMode.LOOK -> "Looking."
          AssistMode.READ -> "Reading."
          AssistMode.ASK -> "On it."
          AssistMode.SHELF -> "Checking the shelf."
        }
      }

  // Voice commands: verb-first, three words or fewer. "again", "stop" and "help" always work.
  sealed interface Command {
    data object Again : Command

    data object Stop : Command

    data object Help : Command

    /** "What's around me": the on-device scene, no frame sent. */
    data object Scene : Command

    /** Shelf drill-downs answered from memory: more, exact, cheapest, where is X, price of X. */
    data object More : Command

    data object Exact : Command

    data object Cheapest : Command

    data class Where(val item: String) : Command

    data class PriceOf(val item: String) : Command

    data class Run(val mode: AssistMode, val question: String?) : Command
  }

  fun parseCommand(spoken: String): Command {
    val text = spoken.trim().lowercase(Locale.ROOT).trimEnd('.', '?', '!', '؟')
    val words = text.split(Regex("\\s+")).filter { it.isNotBlank() }
    if (words.isEmpty()) return Command.Run(AssistMode.LOOK, null)
    val first = words.first()
    val short = words.size <= 3
    // Arabic commands, verb first: look / read / again / stop / help.
    val arabicLook = setOf("انظر", "أنظر", "شوف", "شو قدامي", "ماذا أمامي", "ما أمامي")
    val arabicRead = setOf("اقرأ", "إقرأ", "اقرا", "اقرأ هذا")
    val arabicAgain = setOf("كرر", "أعد", "مرة ثانية", "مرة أخرى", "عيد")
    val arabicStop = setOf("توقف", "قف", "اسكت", "كفاية")
    val arabicHelp = setOf("مساعدة", "ساعدني")
    val arabicShelf = setOf("الرف", "افحص الرف", "ماذا على الرف", "الأسعار", "ما الأسعار", "المنتجات")
    val arabicScene = setOf("ماذا حولي", "ما حولي", "صف المكان", "المشهد")
    val arabicMore = setOf("المزيد", "زيادة", "التفاصيل", "كمل")
    val arabicExact = setOf("بالتفصيل", "كل شيء", "اقرأ الكل", "اقرأ كل شيء")
    val arabicCheapest = setOf("الأرخص", "ما الأرخص", "أرخص شيء")
    Regex("^(أين|وين)\\s+(.+)$").find(text)?.let { return Command.Where(it.groupValues[2].trim()) }
    Regex("^(كم سعر|سعر|بكم)\\s+(.+)$").find(text)?.let { return Command.PriceOf(it.groupValues[2].trim()) }
    Regex("^(where is|where's|where are|where was)\\s+(the |a |an )?(.+)$").find(text)?.let {
      return Command.Where(it.groupValues[3].trim())
    }
    Regex("^(price of|how much is|how much are|how much for|what does .* cost)\\s*(the |a |an )?(.*)$").find(text)?.let {
      val item = it.groupValues[3].trim().ifBlank { it.groupValues[1].removePrefix("what does ").removeSuffix(" cost") }
      return Command.PriceOf(item)
    }
    return when {
      text in arabicAgain -> Command.Again
      text in arabicStop -> Command.Stop
      text in arabicHelp -> Command.Help
      text in arabicShelf -> Command.Run(AssistMode.SHELF, null)
      text in arabicScene -> Command.Scene
      text in arabicMore -> Command.More
      text in arabicExact -> Command.Exact
      text in arabicCheapest -> Command.Cheapest
      text == "more" || text == "tell me more" || text == "details" || text == "next" -> Command.More
      text == "exact" || text == "everything" || text == "read them all" || text == "all of them" || text == "list them" ->
          Command.Exact
      text == "cheapest" || text == "what's cheapest" || text == "cheapest one" || text == "lowest price" -> Command.Cheapest
      text == "shelf" || text == "scan the shelf" || text == "what's on the shelf" || text == "whats on the shelf" ||
          text == "prices" || text == "what are the prices" || text == "what's for sale" || text == "products" ->
          Command.Run(AssistMode.SHELF, null)
      text == "what's around me" || text == "whats around me" || text == "what's around" || text == "scene" ||
          text == "describe the scene" || text == "around me" -> Command.Scene
      short && (text in arabicRead || first in arabicRead) -> Command.Run(AssistMode.READ, null)
      short && (text in arabicLook || first in arabicLook) -> Command.Run(AssistMode.LOOK, null)
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

  /** Every fixed line Vantage says, in both languages. */
  object Lines {
    fun help(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "قل انظر، اقرأ، الرف، أو اسأل سؤالاً. المزيد يفصّل. كرر يعيد. توقف يوقف."
        else "Say look, read, shelf, or ask a question. More gives details. Again repeats. Stop stops."

    fun noShelf(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لا يوجد رف محفوظ. قل الرف أولاً." else "No shelf yet. Say shelf first."

    fun notFound(item: String, l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لم أرَ $item على هذا الرف." else "I didn't see $item on this shelf."

    fun noPrices(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لم أتمكن من قراءة الأسعار. اقترب من اللافتات."
        else "I couldn't read the prices. Move closer to the tags."

    fun nothingForSale(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لا أرى منتجات هنا. وجّه نظرك نحو الرف."
        else "I don't see products here. Face the shelf."

    /** Repair ladder: never blame, never say "I didn't hear you", always end with something to do. */
    fun nothingHeard(attempt: Int, l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) {
          if (attempt <= 1) "قل انظر، أو اقرأ، أو سؤالاً. أو استخدم الأزرار."
          else "استخدم زر انظر أو اقرأ على الهاتف."
        } else {
          if (attempt <= 1) "Say look, read, or a question. Or use the buttons."
          else "Use the Look or Read button on the phone."
        }

    fun offline(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لا يوجد اتصال الآن. حاول بعد لحظة."
        else "No connection right now. Try again in a moment."

    fun timeout(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "استغرق هذا وقتاً طويلاً. اسأل مرة أخرى؟"
        else "That took too long. Ask again?"

    fun rejected(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لا أستطيع الرؤية الآن. حاول مرة أخرى."
        else "I can't reach my eyes right now. Try again."

    fun noKey(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "فانتج غير جاهز بعد. أضف مفتاح الخدمة على الهاتف."
        else "Vantage isn't set up yet. Add the API key on the phone."

    fun noFrame(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لا توجد صورة بعد. شغّل المعاينة وحاول مرة أخرى."
        else "I don't have a picture yet. Start the preview and try again."

    fun micOff(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "الميكروفون مغلق. استخدم زر انظر أو اقرأ."
        else "Microphone is off. Use the Look or Read button."

    fun voiceUnavailable(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "الصوت غير متاح هنا. استخدم زر انظر أو اقرأ."
        else "Voice isn't available here. Use the Look or Read button."

    fun nothingToRepeat(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لا شيء لأكرره بعد. اضغط انظر أو اقرأ."
        else "Nothing to repeat yet. Tap Look or Read."

    fun handOff(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "لنستخدم أزرار الهاتف الآن." else "Let's use the phone buttons for now."

    fun sorry(l: AssistLanguage) = if (l == AssistLanguage.ARABIC) "عذراً. " else "Sorry. "

    fun languageSwitched(l: AssistLanguage) =
        if (l == AssistLanguage.ARABIC) "العربية." else "English."
  }

  /** Make model output speakable: strip markdown, collapse whitespace, clamp runaway answers. */
  fun tidy(answer: String, mode: AssistMode): String {
    var text =
        answer
            .replace(Regex("[*_#`>\\[\\]]"), "")
            .replace(Regex("\\s+"), " ")
            .trim()
    val maxWords = if (mode == AssistMode.READ) 110 else 36
    val words = text.split(' ')
    if (words.size > maxWords) {
      text = words.take(maxWords).joinToString(" ").trimEnd(',', ';', ':') + "."
    }
    return text
  }
}
