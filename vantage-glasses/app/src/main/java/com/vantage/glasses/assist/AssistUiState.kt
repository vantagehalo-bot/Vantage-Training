package com.vantage.glasses.assist

enum class AssistPhase {
  IDLE,
  LISTENING,
  CAPTURING,
  THINKING,
  SPEAKING,
}

data class AssistUiState(
    val phase: AssistPhase = AssistPhase.IDLE,
    val mode: AssistMode? = null,
    /** Live transcript while listening, then the final question. */
    val heard: String = "",
    /** The last thing Vantage said (answer or repair line). */
    val spoken: String = "",
    val lastWasError: Boolean = false,
    /** Time from tap to the acknowledging earcon, and tap to the start of the spoken answer. */
    val ackMillis: Long? = null,
    val totalMillis: Long? = null,
    val hasApiKey: Boolean = true,
    val language: AssistLanguage = AssistLanguage.ENGLISH,
    /** The last shelf scan, for the on-screen list. */
    val shelf: ShelfScene? = null,
    /** Why the last model call failed, for the screen (never spoken): kind and HTTP status. */
    val errorDetail: String? = null,
    /** Microphone level 0..1 while listening, for the meter. */
    val micLevel: Float = 0f,
) {
  val isBusy: Boolean
    get() = phase != AssistPhase.IDLE && phase != AssistPhase.SPEAKING

  val canRepeat: Boolean
    get() = spoken.isNotBlank() && !lastWasError
}
