// SpeechQueue - the firmware's speech queue: priority, max age, critical sweeps the rest
//
// Ported from vantage_core.py's announcer queue (and the Lens demo's audio.js). A CRITICAL message
// interrupts whatever is playing and drops anything less urgent still waiting. A message that goes
// stale before its turn is dropped rather than spoken late. Same-key messages replace each other,
// so a repeated alert never piles up.

package com.vantage.glasses.voice

import android.os.SystemClock
import com.vantage.glasses.assist.Earcon
import com.vantage.glasses.assist.SpokenOutput
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

enum class Priority(val rank: Int) {
  INFO(0),
  ANSWER(1),
  WARNING(2),
  CRITICAL(3),
}

class SpeechMessage(
    val text: String,
    val priority: Priority,
    val key: String = text,
    val maxAgeMs: Long = 4_000L,
    val beepFirst: Boolean = false,
    val createdAt: Long = SystemClock.elapsedRealtime(),
) {
  val isStale: Boolean
    get() = SystemClock.elapsedRealtime() - createdAt > maxAgeMs
}

class SpeechQueue(private val output: SpokenOutput, private val scope: CoroutineScope) {
  private val lock = Mutex()
  private val pending = ArrayList<SpeechMessage>()
  private val wake = Channel<Unit>(Channel.CONFLATED)
  private var current: SpeechMessage? = null
  private var worker: Job? = null

  /** What is being spoken right now, for the caption on screen. */
  private val _nowSpeaking = MutableStateFlow<SpeechMessage?>(null)
  val nowSpeaking: StateFlow<SpeechMessage?> = _nowSpeaking

  /** Events for the pipeline view: queued, spoken, dropped-stale, swept. */
  private val _events = MutableStateFlow<List<String>>(emptyList())
  val events: StateFlow<List<String>> = _events

  fun start() {
    if (worker != null) return
    worker =
        scope.launch {
          for (unit in wake) {
            drain()
          }
        }
  }

  suspend fun enqueue(message: SpeechMessage) {
    lock.withLock {
      pending.removeAll { it.key == message.key }
      if (message.priority == Priority.CRITICAL) {
        val swept = pending.count { it.priority.rank < Priority.CRITICAL.rank }
        pending.removeAll { it.priority.rank < Priority.CRITICAL.rank }
        if (swept > 0) log("swept $swept")
        val playing = current
        if (playing != null && playing.priority.rank < Priority.CRITICAL.rank) {
          output.stop()
          log("interrupted ${playing.priority.name.lowercase()}")
        }
      }
      pending.add(message)
      pending.sortByDescending { it.priority.rank }
      log("queued ${message.priority.name.lowercase()}: ${message.text.take(40)}")
    }
    wake.trySend(Unit)
  }

  /** Drops everything waiting and stops speech. The always-available "stop". */
  suspend fun clear() {
    lock.withLock { pending.clear() }
    output.stop()
  }

  val isBusy: Boolean
    get() = current != null || output.isSpeaking

  private suspend fun drain() {
    while (true) {
      val next =
          lock.withLock {
            while (pending.isNotEmpty() && pending[0].isStale) {
              val stale = pending.removeAt(0)
              log("dropped stale: ${stale.text.take(40)}")
            }
            if (pending.isEmpty()) null else pending.removeAt(0).also { current = it }
          } ?: return
      _nowSpeaking.value = next
      if (next.beepFirst) {
        output.earcon(Earcon.ALERT)
        kotlinx.coroutines.delay(420)
      }
      output.say(next.text)
      log("spoke: ${next.text.take(40)}")
      lock.withLock { if (current === next) current = null }
      _nowSpeaking.value = null
    }
  }

  private fun log(line: String) {
    _events.value = (_events.value + line).takeLast(12)
  }
}
