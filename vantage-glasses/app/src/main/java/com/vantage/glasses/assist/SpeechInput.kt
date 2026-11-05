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
  /** Listens for one utterance and returns when the recognizer finishes or gives up. */
  suspend fun listenOnce(onPartial: (String) -> Unit = {}): HeardResult

  fun cancel()

  fun release()
}

/** Android's built-in recognizer, run on the phone's microphone. Must be driven from the main thread. */
class AndroidSpeechInput(private val context: Context) : SpeechInput {
  companion object {
    private const val TAG = "Vantage:Speech"
  }

  private var recognizer: SpeechRecognizer? = null

  override suspend fun listenOnce(onPartial: (String) -> Unit): HeardResult =
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

                override fun onRmsChanged(rmsdB: Float) = Unit

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
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
                // Bounded listening: stop ~1.2 s after the wearer stops talking.
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1200L)
              }
          continuation.invokeOnCancellation { finish(HeardResult.NothingHeard) }
          engine.startListening(intent)
        }
      }

  override fun cancel() {
    recognizer?.let { runCatching { it.cancel() } }
  }

  override fun release() {
    recognizer?.let { runCatching { it.destroy() } }
    recognizer = null
  }
}
