// AwarenessEngine - continuous obstacle awareness from the glasses stream, all on the phone
//
// Pulls a small frame from the preview a few times a second, runs the on-device detector, feeds the
// ported announcer, and queues what it says. No frame leaves the phone on this path. It yields to an
// Ask turn: while Vantage is listening, thinking or answering, only CRITICAL alerts get through.

package com.vantage.glasses.awareness

import android.graphics.Bitmap
import android.os.SystemClock
import android.util.Log
import com.vantage.glasses.assist.FrameSource
import com.vantage.glasses.voice.SpeechMessage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class AwarenessState(
    val running: Boolean = false,
    val level: HazardLevel = HazardLevel.CLEAR,
    val targetLabel: String? = null,
    val targetCm: Int? = null,
    val tracks: List<Tracked> = emptyList(),
    val fps: Float = 0f,
    val detectorReady: Boolean = true,
)

class AwarenessEngine(
    private val frameSource: FrameSource,
    private val detector: Detector,
    private val announcer: Announcer,
    private val scope: CoroutineScope,
    private val speak: suspend (SpeechMessage) -> Unit,
) {
  companion object {
    private const val TAG = "Vantage:Awareness"
    private const val FRAME_INTERVAL_MS = 250L
    private const val DETECT_EDGE_PX = 320
  }

  private val _state = MutableStateFlow(AwarenessState())
  val state: StateFlow<AwarenessState> = _state

  private var job: Job? = null

  /** Set by the assist flow: true while a turn is in progress. No alert at all gets through then. */
  @Volatile var yieldToAssist: Boolean = false

  /** Alerts also stay quiet for a moment after a turn, so an answer is never stepped on. */
  @Volatile var quietUntil: Long = 0L

  fun start() {
    if (job != null) return
    announcer.reset()
    job =
        scope.launch(Dispatchers.Default) {
          _state.value = _state.value.copy(running = true)
          var lastTick = SystemClock.elapsedRealtime()
          try {
            while (true) {
              val t0 = SystemClock.elapsedRealtime()
              val frame = frameSource.grabFrame()
              if (frame != null) {
                val small = downscale(frame)
                if (small !== frame) frame.recycle()
                val detections =
                    try {
                      detector.detect(small)
                    } finally {
                      small.recycle()
                    }
                val now = SystemClock.elapsedRealtime()
                val messages = announcer.update(detections, now)
                val target = announcer.confirmed.firstOrNull()
                val fps = 1000f / maxOf(1L, now - lastTick)
                lastTick = now
                _state.value =
                    AwarenessState(
                        running = true,
                        level = announcer.currentLevel,
                        targetLabel = target?.label,
                        targetCm = target?.rangeCm,
                        tracks = announcer.confirmed,
                        fps = fps,
                    )
                val muted = yieldToAssist || now < quietUntil
                for (m in messages) {
                  if (muted) continue
                  withContext(Dispatchers.Main) { speak(m) }
                }
              }
              val spent = SystemClock.elapsedRealtime() - t0
              delay(maxOf(40L, FRAME_INTERVAL_MS - spent))
            }
          } catch (e: CancellationException) {
            throw e
          } catch (e: Exception) {
            Log.e(TAG, "awareness loop stopped: ${e.javaClass.simpleName}: ${e.message}")
          } finally {
            _state.value = AwarenessState(running = false)
          }
        }
  }

  fun stop() {
    job?.cancel()
    job = null
    _state.value = AwarenessState(running = false)
  }

  val isRunning: Boolean
    get() = job != null

  fun sceneLine(): String = announcer.sceneLine()

  private fun downscale(frame: Bitmap): Bitmap {
    val longEdge = maxOf(frame.width, frame.height)
    if (longEdge <= DETECT_EDGE_PX) return frame
    val s = DETECT_EDGE_PX.toFloat() / longEdge
    return Bitmap.createScaledBitmap(
        frame,
        (frame.width * s).toInt().coerceAtLeast(1),
        (frame.height * s).toInt().coerceAtLeast(1),
        true,
    )
  }
}
