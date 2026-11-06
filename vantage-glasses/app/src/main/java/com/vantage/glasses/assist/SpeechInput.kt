// SpeechInput - the wearer's question, as text
//
// Kept behind an interface so the phone's recognizer (used on the Mock Device Kit today) can be
// swapped for the glasses' on-device Speech capability (session.addSpeech(), experimental in DAT 1.0)
// without touching the assist flow.

package com.vantage.glasses.assist

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import kotlin.coroutines.resume
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

sealed interface HeardResult {
  data class Heard(val text: String, val confidence: Float) : HeardResult

  data object NothingHeard : HeardResult

  data class Unavailable(val reason: String) : HeardResult
}

interface SpeechInput {
  /**
   * Listens for one utterance and returns when the wearer finishes (a pause, [finish], or the
   * recognizer's limit). [onPartial] streams the words as they are heard; [onLevel] the mic level
   * 0..1, so the screen can show that the voice is being picked up.
   */
  suspend fun listenOnce(
      languageTag: String = "en-US",
      onLevel: (Float) -> Unit = {},
      onPartial: (String) -> Unit = {},
  ): HeardResult

  /** The wearer says they are done (finger lifted, Done tapped): return what was heard so far. */
  fun finish()

  fun cancel()

  fun release()
}

/** Android's built-in recognizer, run on the phone's microphone. Must be driven from the main thread. */
class AndroidSpeechInput(private val context: Context) : SpeechInput {
  companion object {
    private const val TAG = "Vantage:Speech"
  }

  private var recognizer: SpeechRecognizer? = null

  override suspend fun listenOnce(
      languageTag: String,
      onLevel: (Float) -> Unit,
      onPartial: (String) -> Unit,
  ): HeardResult =
      withContext<HeardResult>(Dispatchers.Main) {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
          return@withContext HeardResult.Unavailable("no recognition service")
        }
        suspendCancellableCoroutine<HeardResult> { continuation ->
          val engine = SpeechRecognizer.createSpeechRecognizer(context)
          recognizer = engine
          var finished = false
          fun finish(result: HeardResult) {
            if (finished) return
            finished = true
            runCatching { engine.destroy() }
            if (recognizer === engine) recognizer = null
            if (continuation.isActive) continuation.resume(result)
          }
          engine.setRecognitionListener(
              object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) = Unit

                override fun onBeginningOfSpeech() = Unit

                override fun onRmsChanged(rmsdB: Float) {
                  // Typical range is about -2..10 dB; map to 0..1 for the meter.
                  onLevel(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
                }

                override fun onBufferReceived(buffer: ByteArray?) = Unit

                override fun onEndOfSpeech() = Unit

                override fun onPartialResults(partialResults: Bundle?) {
                  partialResults
                      ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                      ?.firstOrNull()
                      ?.let(onPartial)
                }

                override fun onEvent(eventType: Int, params: Bundle?) = Unit

                override fun onResults(results: Bundle?) {
                  val texts = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                  val scores = results?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)
                  val best = texts?.firstOrNull()?.trim()
                  if (best.isNullOrEmpty()) finish(HeardResult.NothingHeard)
                  else finish(HeardResult.Heard(best, scores?.firstOrNull() ?: -1f))
                }

                override fun onError(error: Int) {
                  // Transcripts are never logged; the error code is.
                  Log.i(TAG, "recognizer finished with error $error")
                  when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH,
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> finish(HeardResult.NothingHeard)
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                        finish(HeardResult.Unavailable("microphone permission"))
                    else -> finish(HeardResult.Unavailable("recognizer error $error"))
                  }
                }
              },
          )
          val intent =
              Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
                )
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
                // Let the wearer finish: a long pause, not the first breath, ends the question.
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2500L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 2000L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 6000L)
              }
          continuation.invokeOnCancellation { finish(HeardResult.NothingHeard) }
          engine.startListening(intent)
        }
      }

  override fun finish() {
    // stopListening makes the recognizer deliver onResults with what it has.
    recognizer?.let { runCatching { it.stopListening() } }
  }

  override fun cancel() {
    recognizer?.let { runCatching { it.cancel() } }
  }

  override fun release() {
    recognizer?.let { runCatching { it.destroy() } }
    recognizer = null
  }
}
