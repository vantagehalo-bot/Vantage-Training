// SceneMemory - what Vantage said in the last minute, so "again" and "where was the milk" work
// without another capture. Wiped on exit; never written to disk.

package com.vantage.glasses.assist

import android.os.SystemClock

data class ShelfItem(
    val name: String,
    val price: Double?,
    val currency: String,
    /** left | centre | right */
    val position: String,
    /** top | eye | bottom */
    val row: String,
    val note: String,
)

data class ShelfScene(
    val summary: String,
    val groups: List<String>,
    val items: List<ShelfItem>,
    val capturedAt: Long = SystemClock.elapsedRealtime(),
)

data class SpokenAnswer(
    val text: String,
    val mode: AssistMode,
    val question: String? = null,
    val at: Long = SystemClock.elapsedRealtime(),
)

class SceneMemory(private val ttlMs: Long = 60_000L) {
  private val answers = ArrayDeque<SpokenAnswer>()
  private var shelf: ShelfScene? = null

  fun remember(text: String, mode: AssistMode, question: String? = null) {
    answers.addFirst(SpokenAnswer(text, mode, question))
    while (answers.size > 4) answers.removeLast()
  }

  /** The conversation so far, oldest first, as (question, answer): what the model needs for follow-ups. */
  val conversation: List<Pair<String, String>>
    get() = recent.reversed().map { (it.question ?: it.mode.name.lowercase()) to it.text }

  fun rememberShelf(scene: ShelfScene) {
    shelf = scene
  }

  val recent: List<SpokenAnswer>
    get() {
      val now = SystemClock.elapsedRealtime()
      return answers.filter { now - it.at <= ttlMs }
    }

  val currentShelf: ShelfScene?
    get() = shelf?.takeIf { SystemClock.elapsedRealtime() - it.capturedAt <= ttlMs }

  fun clear() {
    answers.clear()
    shelf = null
  }
}
