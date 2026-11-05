// Phrases - what the announcer says, in English and Arabic, matching the firmware
//
// English lines are vantage_core.py's own. Arabic lines use the grammar in Arabic.kt.

package com.vantage.glasses.voice

import com.vantage.glasses.assist.AssistLanguage

object Phrases {
  fun label(en: String, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) Arabic.label(en) else en

  /** "Person too close, forty centimetres." */
  fun tooClose(labelEn: String?, cm: Int, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) {
        val what = labelEn?.let { Arabic.label(it) } ?: Arabic.OBSTACLE
        "$what قريب جدًا، ${Arabic.at(cm)}"
      } else {
        "${(labelEn ?: "Obstacle").replaceFirstChar { it.uppercase() }} too close, ${English.distance(cm)}"
      }

  /** "Chair ahead, eighty centimetres, approaching fast." */
  fun ahead(labelEn: String?, cm: Int, approachingFast: Boolean, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) {
        val what = labelEn?.let { Arabic.label(it) } ?: Arabic.OBSTACLE
        "$what أمامك، ${Arabic.at(cm)}" + if (approachingFast) "، يقترب بسرعة" else ""
      } else {
        "${(labelEn ?: "Obstacle").replaceFirstChar { it.uppercase() }} ahead, ${English.distance(cm)}" +
            if (approachingFast) ", approaching fast" else ""
      }

  /** Box fills the frame but no range: "Person very close." */
  fun veryClose(labelEn: String, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) "${Arabic.label(labelEn)} قريب جدًا"
      else "${labelEn.replaceFirstChar { it.uppercase() }} very close"

  /** Describe mode: "Chair on your left." */
  fun seen(labelEn: String, directionEn: String, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) "${Arabic.label(labelEn)} ${Arabic.direction(directionEn)}"
      else "${labelEn.replaceFirstChar { it.uppercase() }} $directionEn"

  fun clear(l: AssistLanguage): String = if (l == AssistLanguage.ARABIC) "الطريق خالٍ" else "Clear ahead"

  /** The whole scene on request: "Two people ahead, a chair on your left." */
  fun scene(items: List<Pair<String, String>>, l: AssistLanguage): String {
    if (items.isEmpty()) return if (l == AssistLanguage.ARABIC) "لا أرى شيئًا قريبًا" else "Nothing in range"
    return if (l == AssistLanguage.ARABIC)
        Arabic.join(items.map { (label, dir) -> "${Arabic.label(label)} ${Arabic.direction(dir)}" })
    else English.join(items.map { (label, dir) -> "$label $dir" }).replaceFirstChar { it.uppercase() }
  }
}
