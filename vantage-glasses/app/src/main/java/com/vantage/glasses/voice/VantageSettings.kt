// VantageSettings - the same options as vantage_core.py, kept on the phone

package com.vantage.glasses.voice

import android.content.Context
import com.vantage.glasses.assist.AssistLanguage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

data class Settings(
    val criticalCm: Int = 50,
    val warningCm: Int = 100,
    val repeatSec: Float = 2.5f,
    val threshold: Float = 0.55f,
    val awarenessOn: Boolean = false,
    val describeMode: Boolean = false,
    val speechRate: Float = 1.15f,
    val language: AssistLanguage = AssistLanguage.ENGLISH,
    val gesturesOn: Boolean = true,
    val beepOn: Boolean = true,
)

class VantageSettings(context: Context) {
  private val prefs = context.applicationContext.getSharedPreferences("vantage", Context.MODE_PRIVATE)

  private val _state =
      MutableStateFlow(
          Settings(
              criticalCm = prefs.getInt("criticalCm", 50),
              warningCm = prefs.getInt("warningCm", 100),
              repeatSec = prefs.getFloat("repeatSec", 2.5f),
              threshold = prefs.getFloat("threshold", 0.55f),
              awarenessOn = prefs.getBoolean("awarenessOn", false),
              describeMode = prefs.getBoolean("describeMode", false),
              speechRate = prefs.getFloat("speechRate", 1.15f),
              language =
                  if (prefs.getString("language", "en") == "ar") AssistLanguage.ARABIC
                  else AssistLanguage.ENGLISH,
              gesturesOn = prefs.getBoolean("gesturesOn", true),
              beepOn = prefs.getBoolean("beepOn", true),
          ),
      )
  val state: StateFlow<Settings> = _state

  val value: Settings
    get() = _state.value

  fun update(block: (Settings) -> Settings) {
    val s = block(_state.value)
    _state.value = s
    prefs
        .edit()
        .putInt("criticalCm", s.criticalCm)
        .putInt("warningCm", s.warningCm)
        .putFloat("repeatSec", s.repeatSec)
        .putFloat("threshold", s.threshold)
        .putBoolean("awarenessOn", s.awarenessOn)
        .putBoolean("describeMode", s.describeMode)
        .putFloat("speechRate", s.speechRate)
        .putString("language", if (s.language == AssistLanguage.ARABIC) "ar" else "en")
        .putBoolean("gesturesOn", s.gesturesOn)
        .putBoolean("beepOn", s.beepOn)
        .apply()
  }
}
