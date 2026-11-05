// Announcer - the decision logic of vantage_core.py, on detections from the phone
//
// The Pi has a LiDAR for range; here range is estimated from how tall an object looks, honest to
// about 15–30 % for upright things. Whatever covers the centre of the frame owns the range reading,
// the way the laser beam does on the device. Everything else is the firmware's: a tracker that
// needs two frames before it trusts a box, hysteresis at the thresholds, repeats on a timer or at
// once when the target changes, and messages that go stale are never spoken.

package com.vantage.glasses.awareness

import android.os.SystemClock
import com.vantage.glasses.assist.AssistLanguage
import com.vantage.glasses.voice.Phrases
import com.vantage.glasses.voice.Priority
import com.vantage.glasses.voice.SpeechMessage

enum class HazardLevel {
  CLEAR,
  CAUTION,
  STOP,
}

data class Tracked(
    val detection: Detection,
    val rangeCm: Int,
    val hits: Int,
    val lastSeen: Long,
    val rangeHistory: List<Pair<Long, Int>>,
) {
  val label: String
    get() = detection.label

  val confirmed: Boolean
    get() = hits >= 2

  /** Closing speed in cm/s from a least-squares fit over the last half second. */
  val closingCmPerSec: Float
    get() {
      val h = rangeHistory.takeLast(6)
      if (h.size < 3) return 0f
      val t0 = h.first().first
      val xs = h.map { (it.first - t0) / 1000f }
      val ys = h.map { it.second.toFloat() }
      val mx = xs.average().toFloat()
      val my = ys.average().toFloat()
      var num = 0f
      var den = 0f
      for (i in xs.indices) {
        num += (xs[i] - mx) * (ys[i] - my)
        den += (xs[i] - mx) * (xs[i] - mx)
      }
      return if (den == 0f) 0f else -num / den
    }
}

data class AnnouncerConfig(
    val criticalCm: Int = 50,
    val warningCm: Int = 100,
    val repeatMs: Long = 2_500L,
    val describeMode: Boolean = false,
    val beepOn: Boolean = true,
    val language: AssistLanguage = AssistLanguage.ENGLISH,
)

class Announcer {
  companion object {
    /** Typical real heights in metres, for range from box height. */
    private val HEIGHT_M =
        mapOf(
            "person" to 1.65f, "chair" to 0.9f, "couch" to 0.85f, "dining table" to 0.75f, "bench" to 0.9f,
            "car" to 1.5f, "truck" to 3.0f, "bus" to 3.0f, "motorcycle" to 1.1f, "bicycle" to 1.0f,
            "dog" to 0.5f, "cat" to 0.3f, "potted plant" to 0.6f, "tv" to 0.6f, "laptop" to 0.25f,
            "bottle" to 0.25f, "cup" to 0.1f, "backpack" to 0.45f, "suitcase" to 0.6f, "umbrella" to 0.9f,
            "refrigerator" to 1.8f, "door" to 2.0f, "traffic light" to 1.0f, "stop sign" to 0.75f,
            "fire hydrant" to 0.7f, "bed" to 0.6f, "toilet" to 0.75f, "sink" to 0.3f, "oven" to 0.9f,
        )
    private const val DEFAULT_HEIGHT_M = 0.8f
    // Vertical field of view of the glasses camera, roughly; range = H / (boxFrac * 2 tan(fov/2)).
    private const val FOV_FACTOR = 1.4f
    private const val IOU_MATCH = 0.3f
    private const val TRACK_TTL_MS = 900L
    private const val WARNING_REANNOUNCE_MS = 6_000L
    private const val DESCRIBE_REANNOUNCE_MS = 10_000L
    private const val HYSTERESIS = 1.15f
    private const val FAST_CM_PER_SEC = 100f
  }

  private val tracks = ArrayList<Tracked>()
  private var level = HazardLevel.CLEAR
  private var lastCriticalAt = 0L
  private var lastCriticalLabel: String? = null
  private val warnedAt = HashMap<String, Long>()
  private val describedAt = HashMap<String, Long>()

  var config = AnnouncerConfig()

  val currentLevel: HazardLevel
    get() = level

  /** Confirmed tracks, nearest first. */
  val confirmed: List<Tracked>
    get() = tracks.filter { it.confirmed }.sortedBy { it.rangeCm }

  fun reset() {
    tracks.clear()
    level = HazardLevel.CLEAR
    lastCriticalAt = 0L
    lastCriticalLabel = null
    warnedAt.clear()
    describedAt.clear()
  }

  fun estimateRangeCm(d: Detection): Int {
    val h = HEIGHT_M[d.label] ?: DEFAULT_HEIGHT_M
    val frac = d.height.coerceAtLeast(0.02f)
    val m = h / (frac * FOV_FACTOR)
    return (m * 100).toInt().coerceIn(20, 1200)
  }

  fun direction(d: Detection): String =
      when {
        d.centreX < 0.38f -> "on your left"
        d.centreX > 0.62f -> "on your right"
        else -> "ahead"
      }

  /**
   * Feed one frame's detections. Returns the messages to queue, in order. The caller decides whether
   * speech is allowed right now (an Ask answer should not be cut by a warning, only by a critical).
   */
  fun update(detections: List<Detection>, now: Long = SystemClock.elapsedRealtime()): List<SpeechMessage> {
    track(detections, now)
    val out = ArrayList<SpeechMessage>()
    val l = config.language
    val live = tracks.filter { it.confirmed }
    if (live.isEmpty()) {
      level = HazardLevel.CLEAR
      return out
    }

    // The object covering the frame centre owns the range, like the laser beam; else the nearest.
    val target = live.firstOrNull { it.detection.covers(0.5f, 0.55f) } ?: live.minByOrNull { it.rangeCm }!!
    val range = target.rangeCm
    val fillsFrame = target.detection.height > 0.85f

    // Hysteresis at both thresholds.
    val critical = config.criticalCm
    val warning = config.warningCm
    val nextLevel =
        when (level) {
          HazardLevel.STOP ->
              if (range < critical * HYSTERESIS || fillsFrame) HazardLevel.STOP
              else if (range < warning) HazardLevel.CAUTION else HazardLevel.CLEAR
          HazardLevel.CAUTION ->
              if (range < critical || fillsFrame) HazardLevel.STOP
              else if (range < warning * HYSTERESIS) HazardLevel.CAUTION else HazardLevel.CLEAR
          HazardLevel.CLEAR ->
              if (range < critical || fillsFrame) HazardLevel.STOP
              else if (range < warning) HazardLevel.CAUTION else HazardLevel.CLEAR
        }
    level = nextLevel

    when (nextLevel) {
      HazardLevel.STOP -> {
        val changed = target.label != lastCriticalLabel
        if (changed || now - lastCriticalAt >= config.repeatMs) {
          val text =
              if (fillsFrame && range <= critical) Phrases.veryClose(target.label, l)
              else Phrases.tooClose(target.label, range, l)
          out.add(
              SpeechMessage(
                  text = text,
                  priority = Priority.CRITICAL,
                  key = "critical",
                  maxAgeMs = 1_500L,
                  beepFirst = config.beepOn,
                  createdAt = now,
              ),
          )
          lastCriticalAt = now
          lastCriticalLabel = target.label
        }
      }
      HazardLevel.CAUTION -> {
        val fast = target.closingCmPerSec > FAST_CM_PER_SEC
        val last = warnedAt[target.label] ?: 0L
        if (now - last >= WARNING_REANNOUNCE_MS || fast && now - last >= 1_500L) {
          out.add(
              SpeechMessage(
                  text = Phrases.ahead(target.label, range, fast, l),
                  priority = Priority.WARNING,
                  key = "warning",
                  maxAgeMs = 2_500L,
                  createdAt = now,
              ),
          )
          warnedAt[target.label] = now
        }
        lastCriticalLabel = null
      }
      HazardLevel.CLEAR -> lastCriticalLabel = null
    }

    // Describe mode: new things, with a direction, once each.
    if (config.describeMode) {
      for (t in live) {
        if (t === target && nextLevel != HazardLevel.CLEAR) continue
        val last = describedAt[t.label] ?: 0L
        if (now - last >= DESCRIBE_REANNOUNCE_MS) {
          out.add(
              SpeechMessage(
                  text = Phrases.seen(t.label, direction(t.detection), l),
                  priority = Priority.INFO,
                  key = "seen:${t.label}",
                  maxAgeMs = 4_000L,
                  createdAt = now,
              ),
          )
          describedAt[t.label] = now
        }
      }
    }
    return out
  }

  /** The whole scene on request (the firmware's `s` key). */
  fun sceneLine(): String =
      Phrases.scene(confirmed.map { it.label to direction(it.detection) }, config.language)

  private fun track(detections: List<Detection>, now: Long) {
    val matched = BooleanArray(detections.size)
    val next = ArrayList<Tracked>()
    for (t in tracks) {
      var best = -1
      var bestIou = IOU_MATCH
      for ((i, d) in detections.withIndex()) {
        if (matched[i] || d.label != t.label) continue
        val iou = d.iou(t.detection)
        if (iou > bestIou) {
          bestIou = iou
          best = i
        }
      }
      if (best >= 0) {
        matched[best] = true
        val d = detections[best]
        val r = estimateRangeCm(d)
        next.add(
            Tracked(
                detection = d,
                rangeCm = r,
                hits = t.hits + 1,
                lastSeen = now,
                rangeHistory = (t.rangeHistory + (now to r)).filter { now - it.first <= 600L },
            ),
        )
      } else if (now - t.lastSeen <= TRACK_TTL_MS) {
        next.add(t)
      }
    }
    for ((i, d) in detections.withIndex()) {
      if (!matched[i]) {
        val r = estimateRangeCm(d)
        next.add(Tracked(d, r, 1, now, listOf(now to r)))
      }
    }
    tracks.clear()
    tracks.addAll(next)
  }
}
