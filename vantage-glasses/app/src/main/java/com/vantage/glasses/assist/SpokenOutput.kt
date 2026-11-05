// SpokenOutput - the answer in the wearer's ear, plus earcons
//
// On the Mock Device Kit this is the phone speaker; on real glasses the same Android TTS routes over
// Bluetooth to the open-ear speakers. Four earcons (listening, working, done, error) acknowledge a
// tap within the 0.5 s budget, before any network work starts. A new request flushes the old answer.

package com.vantage.glasses.assist

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger
import kotlin.coroutines.resume
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.suspendCancellableCoroutine

enum class Earcon {
  LISTENING,
  WORKING,
  DONE,
  ERROR,
}

class SpokenOutput(context: Context) {
  companion object {
    private const val TAG = "Vantage:Speak"
  }

  private val ready = CompletableDeferred<Boolean>()
  private val engine: TextToSpeech =
      TextToSpeech(context.applicationContext) { status ->
        val ok = status == TextToSpeech.SUCCESS
        if (ok) applyDefaults()
        ready.complete(ok)
      }
  private val tones: ToneGenerator? =
      runCatching { ToneGenerator(AudioManager.STREAM_MUSIC, 85) }.getOrNull()
  private val utteranceCounter = AtomicInteger()

  // Speech speed is a user setting; blind users often want faster speech. 1.0 is the default.
  var speechRate: Float = 1.15f
    set(value) {
      field = value
      engine.setSpeechRate(value)
    }

  private fun applyDefaults() {
    val result = engine.setLanguage(Locale.getDefault())
    if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
      engine.setLanguage(Locale.US)
    }
    engine.setSpeechRate(speechRate)
  }

  fun earcon(kind: Earcon) {
    val tone =
        when (kind) {
          Earcon.LISTENING -> ToneGenerator.TONE_PROP_BEEP
          Earcon.WORKING -> ToneGenerator.TONE_PROP_ACK
          Earcon.DONE -> ToneGenerator.TONE_PROP_BEEP2
          Earcon.ERROR -> ToneGenerator.TONE_PROP_NACK
        }
    tones?.startTone(tone, 120)
  }

  /** Speaks [text], interrupting anything already playing, and returns once it has been spoken. */
  suspend fun say(text: String): Boolean {
    if (!ready.await()) {
      Log.w(TAG, "TTS engine failed to initialize")
      return false
    }
    val id = "vantage-${utteranceCounter.incrementAndGet()}"
    return suspendCancellableCoroutine { continuation ->
      engine.setOnUtteranceProgressListener(
          object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit

            override fun onDone(utteranceId: String?) {
              if (utteranceId == id && continuation.isActive) continuation.resume(true)
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
              if (utteranceId == id && continuation.isActive) continuation.resume(false)
            }

            override fun onError(utteranceId: String?, errorCode: Int) {
              if (utteranceId == id && continuation.isActive) continuation.resume(false)
            }

            override fun onStop(utteranceId: String?, interrupted: Boolean) {
              if (utteranceId == id && continuation.isActive) continuation.resume(false)
            }
          },
      )
      val queued = engine.speak(text, TextToSpeech.QUEUE_FLUSH, Bundle(), id)
      if (queued != TextToSpeech.SUCCESS && continuation.isActive) continuation.resume(false)
      continuation.invokeOnCancellation { engine.stop() }
    }
  }

  fun stop() {
    engine.stop()
  }

  val isSpeaking: Boolean
    get() = engine.isSpeaking

  fun release() {
    engine.stop()
    engine.shutdown()
    tones?.release()
  }
}
