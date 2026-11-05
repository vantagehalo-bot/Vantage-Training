// MediaPipeDetector - EfficientDet-Lite0 on the phone, the same network the Vantage Lens demo runs
//
// Frames never leave the phone here. Only when the wearer asks a question does one frame go to the
// cloud model (see MetaModelClient).

package com.vantage.glasses.awareness

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.objectdetector.ObjectDetector

class MediaPipeDetector(context: Context, scoreThreshold: Float = 0.4f) : Detector {
  companion object {
    private const val TAG = "Vantage:Detector"
    private const val MODEL = "efficientdet_lite0.tflite"
  }

  private val detector: ObjectDetector? =
      try {
        val options =
            ObjectDetector.ObjectDetectorOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath(MODEL).build())
                .setRunningMode(RunningMode.IMAGE)
                .setScoreThreshold(scoreThreshold)
                .setMaxResults(8)
                .build()
        ObjectDetector.createFromOptions(context.applicationContext, options)
      } catch (e: Exception) {
        Log.e(TAG, "Could not load the detector: ${e.javaClass.simpleName}: ${e.message}")
        null
      }

  val isReady: Boolean
    get() = detector != null

  override fun detect(frame: Bitmap): List<Detection> {
    val d = detector ?: return emptyList()
    val w = frame.width.toFloat()
    val h = frame.height.toFloat()
    val result = d.detect(BitmapImageBuilder(frame).build())
    return result.detections().mapNotNull { det ->
      val cat = det.categories().firstOrNull() ?: return@mapNotNull null
      val box = det.boundingBox()
      Detection(
          label = cat.categoryName(),
          score = cat.score(),
          left = (box.left / w).coerceIn(0f, 1f),
          top = (box.top / h).coerceIn(0f, 1f),
          right = (box.right / w).coerceIn(0f, 1f),
          bottom = (box.bottom / h).coerceIn(0f, 1f),
      )
    }
  }

  override fun close() {
    runCatching { detector?.close() }
  }
}
