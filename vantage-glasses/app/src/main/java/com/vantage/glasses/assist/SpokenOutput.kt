// SpokenOutput - the answer in the wearer's ear, plus earcons
//
// On the Mock Device Kit this is the phone speaker; on real glasses the same Android TTS routes over
// Bluetooth to the open-ear speakers. Four earcons (listening, working, done, error) acknowledge a
// tap within the 0.5 s budget, before any network work starts. A new request flushes the old answer.

package com.vantage.glasses.assist

import android.content.Context
import com.vantage.glasses.voice.Earcons
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
  /** The firmware's two-tone beep before a critical alert. */
  ALERT,
  /** The reader's shutter click when a frame is taken. */
  CLICK,
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
  private val earcons = Earcons()
  private val utteranceCounter = AtomicInteger()

  // Speech speed is a user setting; blind users often want faster speech. 1.0 is the default.
  var speechRate: Float = 1.15f
    set(value) {
      field = value
      engine.setSpeechRate(value)
    }

  private var wantedLocale: Locale = Locale.US

  private fun applyDefaults() {
    applyLocale(wantedLocale)
    engine.setSpeechRate(speechRate)
  }

  private fun applyLocale(locale: Locale): Boolean {
    val result = engine.setLanguage(locale)
    val ok = result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED
    if (!ok) {
      Log.w(TAG, "TTS voice for ${locale.toLanguageTag()} not installed; falling back to en-US")
      engine.setLanguage(Locale.US)
    }
    return ok
  }

  /**
   * Switches the voice. Returns false when the phone has no voice for that language (install one
   * under Settings > General management > Text-to-speech > Install voice data).
   */
  suspend fun setLanguage(locale: Locale): Boolean {
    wantedLocale = locale
    if (!ready.await()) return false
    return applyLocale(locale)
  }

  fun earcon(kind: Earcon) {
    val name =
        when (kind) {
          Earcon.LISTENING -> "listening"
          Earcon.WORKING -> "working"
          Earcon.DONE -> "done"
          Earcon.ERROR -> "error"
          Earcon.ALERT -> "alert"
          Earcon.CLICK -> "click"
        }
    runCatching { earcons.play(name) }.onFailure { Log.w(TAG, "earcon failed: ${it.javaClass.simpleName}") }
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
  }
}
