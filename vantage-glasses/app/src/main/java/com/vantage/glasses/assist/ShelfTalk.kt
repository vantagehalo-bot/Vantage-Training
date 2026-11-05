// ShelfTalk - the gist ladder for a shop shelf: Gist → More → Exact, plus cheapest / where / price
//
// The model extracts structure once (ShelfScene); this decides how much of it to say. The wearer
// climbs the ladder by voice, and every step after the first is answered from memory: no new
// frame, no new cost, no delay.

package com.vantage.glasses.assist

import com.vantage.glasses.voice.Arabic
import com.vantage.glasses.voice.English
import java.util.Locale
import org.json.JSONObject

object ShelfTalk {
  fun parse(text: String): ShelfScene? {
    val cleaned =
        text.trim().removePrefix("```json").removePrefix("```").removeSuffix("```").trim()
    val start = cleaned.indexOf('{')
    val end = cleaned.lastIndexOf('}')
    if (start < 0 || end <= start) return null
    return try {
      val root = JSONObject(cleaned.substring(start, end + 1))
      val groups = ArrayList<String>()
      root.optJSONArray("groups")?.let { g -> for (i in 0 until g.length()) g.optString(i).takeIf { it.isNotBlank() }?.let(groups::add) }
      val items = ArrayList<ShelfItem>()
      root.optJSONArray("items")?.let { arr ->
        for (i in 0 until arr.length()) {
          val o = arr.optJSONObject(i) ?: continue
          val name = o.optString("name").trim()
          if (name.isBlank()) continue
          val price = if (o.isNull("price")) null else o.optDouble("price").takeIf { !it.isNaN() }
          items.add(
              ShelfItem(
                  name = name,
                  price = price,
                  currency = o.optString("currency", "AED").ifBlank { "AED" },
                  position = o.optString("position", "ahead").lowercase(Locale.ROOT),
                  row = o.optString("row", "eye").lowercase(Locale.ROOT),
                  note = o.optString("note", ""),
              ),
          )
        }
      }
      ShelfScene(summary = root.optString("summary").trim(), groups = groups, items = items)
    } catch (e: Exception) {
      null
    }
  }

  private fun position(p: String, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) {
        when (p) {
          "left" -> "على اليسار"
          "right" -> "على اليمين"
          else -> "في الوسط"
        }
      } else {
        when (p) {
          "left" -> "on the left"
          "right" -> "on the right"
          else -> "in the centre"
        }
      }

  private fun row(r: String, l: AssistLanguage): String =
      if (l == AssistLanguage.ARABIC) {
        when (r) {
          "top" -> "الرف العلوي"
          "bottom" -> "الرف السفلي"
          else -> "مستوى النظر"
        }
      } else {
        when (r) {
          "top" -> "top shelf"
          "bottom" -> "bottom shelf"
          else -> "eye level"
        }
      }

  fun price(item: ShelfItem, l: AssistLanguage): String? {
    val p = item.price ?: return null
    return if (l == AssistLanguage.ARABIC) Arabic.price(p) else English.price(p)
  }

  /** Step 1. */
  fun gist(scene: ShelfScene, l: AssistLanguage): String {
    if (scene.items.isEmpty()) return scene.summary.ifBlank { VantagePrompts.Lines.nothingForSale(l) }
    val hint = if (l == AssistLanguage.ARABIC) " قل المزيد للتفاصيل." else " Say more for details."
    return scene.summary.ifBlank { fallbackGist(scene, l) } + hint
  }

  private fun fallbackGist(scene: ShelfScene, l: AssistLanguage): String {
    val n = scene.items.size
    val priced = scene.items.mapNotNull { it.price }
    return if (l == AssistLanguage.ARABIC) {
      val count = Arabic.count(n, "item", nominative = true)
      if (priced.isEmpty()) "$count على الرف."
      else "$count على الرف، من ${Arabic.price(priced.min())} إلى ${Arabic.price(priced.max())}."
    } else {
      val count = "${English.number(n)} items"
      if (priced.isEmpty()) "$count on the shelf."
      else "$count on the shelf, ${English.price(priced.min())} to ${English.price(priced.max())}."
    }
  }

  /** Step 2: one line per group. */
  fun more(scene: ShelfScene, l: AssistLanguage): String {
    if (scene.groups.isNotEmpty()) return scene.groups.joinToString(" ")
    val byPos = scene.items.groupBy { it.position }
    val lines =
        byPos.map { (pos, items) ->
          val names = items.take(3).map { it.name }
          val joined = if (l == AssistLanguage.ARABIC) Arabic.join(names) else English.join(names)
          "${position(pos, l).replaceFirstChar { it.uppercase() }}: $joined."
        }
    return lines.joinToString(" ")
  }

  /** Step 3: every item with its price. */
  fun exact(scene: ShelfScene, l: AssistLanguage): String =
      scene.items.joinToString(" ") { item ->
        val p = price(item, l)
        if (l == AssistLanguage.ARABIC) {
          "${item.name}${if (p != null) "، $p" else ""}، ${position(item.position, l)}، ${row(item.row, l)}."
        } else {
          "${item.name}${if (p != null) ", $p" else ""}, ${position(item.position, l)}, ${row(item.row, l)}."
        }
      }

  fun cheapest(scene: ShelfScene, l: AssistLanguage): String {
    val item = scene.items.filter { it.price != null }.minByOrNull { it.price!! }
        ?: return VantagePrompts.Lines.noPrices(l)
    val p = price(item, l)!!
    return if (l == AssistLanguage.ARABIC) "الأرخص ${item.name}، $p، ${position(item.position, l)}، ${row(item.row, l)}."
    else "Cheapest is ${item.name}, $p, ${position(item.position, l)}, ${row(item.row, l)}."
  }

  private fun find(scene: ShelfScene, query: String): ShelfItem? {
    val q = query.lowercase(Locale.ROOT).trim()
    if (q.isBlank()) return null
    val words = q.split(Regex("\\s+")).filter { it.length > 2 }
    return scene.items.firstOrNull { it.name.lowercase(Locale.ROOT).contains(q) }
        ?: scene.items.maxByOrNull { item ->
          val n = item.name.lowercase(Locale.ROOT)
          words.count { n.contains(it) }
        }?.takeIf { item -> words.any { item.name.lowercase(Locale.ROOT).contains(it) } }
  }

  fun where(scene: ShelfScene, query: String, l: AssistLanguage): String {
    val item = find(scene, query) ?: return VantagePrompts.Lines.notFound(query, l)
    return if (l == AssistLanguage.ARABIC) "${item.name} ${position(item.position, l)}، ${row(item.row, l)}."
    else "${item.name} is ${position(item.position, l)}, ${row(item.row, l)}."
  }

  fun priceOf(scene: ShelfScene, query: String, l: AssistLanguage): String {
    val item = find(scene, query) ?: return VantagePrompts.Lines.notFound(query, l)
    val p = price(item, l) ?: return VantagePrompts.Lines.noPrices(l)
    return if (l == AssistLanguage.ARABIC) "${item.name}، $p." else "${item.name}, $p."
  }
}
