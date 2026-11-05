package com.vantage.glasses.awareness

import android.graphics.Bitmap

/** One detected object. The box is normalised to the frame (0..1). */
data class Detection(
    val label: String,
    val score: Float,
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
) {
  val width: Float
    get() = right - left

  val height: Float
    get() = bottom - top

  val centreX: Float
    get() = (left + right) / 2f

  val centreY: Float
    get() = (top + bottom) / 2f

  fun covers(x: Float, y: Float): Boolean = x in left..right && y in top..bottom

  fun iou(o: Detection): Float {
    val iw = maxOf(0f, minOf(right, o.right) - maxOf(left, o.left))
    val ih = maxOf(0f, minOf(bottom, o.bottom) - maxOf(top, o.top))
    val inter = iw * ih
    val union = width * height + o.width * o.height - inter
    return if (union <= 0f) 0f else inter / union
  }
}

/** Where detections come from. The MediaPipe one runs on the phone; tests can fake it. */
interface Detector {
  fun detect(frame: Bitmap): List<Detection>

  fun close()
}
