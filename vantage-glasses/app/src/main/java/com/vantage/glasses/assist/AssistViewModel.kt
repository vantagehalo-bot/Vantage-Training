// AssistViewModel - the Vantage turn: trigger -> capture -> understand -> respond -> done
//
// Budget (UX session, p18): acknowledge < 0.5 s, spoken answer about 3 s, never silent > 2 s.
// - The earcon plays the moment the wearer taps or speaks, before any capture or network work.
// - If the model is still working after WORKING_LINE_AFTER_MS, Vantage says "Looking." so the
//   silence never passes two seconds.
// - A new trigger interrupts whatever is playing.
//
// Repair ladder (p25): never more than three errors in a row, no blame, one apology at most, and
// every failure ends with something the wearer can do.

package com.vantage.glasses.assist

import android.app.Application
import android.graphics.Bitmap
import android.os.SystemClock
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.vantage.glasses.BuildConfig
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Where the one frame comes from. The camera view model implements it; tests can fake it. */
interface FrameSource {
  suspend fun grabFrame(): Bitmap?
}

class AssistViewModel(
    application: Application,
    private val frameSource: FrameSource,
    private val speechInput: SpeechInput = AndroidSpeechInput(application),
    private val output: SpokenOutput = SpokenOutput(application),
    private val model: MetaModelClient =
        MetaModelClient(
            apiKey = BuildConfig.META_API_KEY,
            modelId = BuildConfig.META_MODEL_ID,
            apiBase = BuildConfig.META_API_BASE,
        ),
) : AndroidViewModel(application) {

  companion object {
    private const val TAG = "Vantage:Assist"
    private const val WORKING_LINE_AFTER_MS = 1_500L
    private const val MAX_ERROR_STREAK = 3
  }

  private val _uiState = MutableStateFlow(AssistUiState(hasApiKey = model.hasKey))
  val uiState: StateFlow<AssistUiState> = _uiState.asStateFlow()

  private var turnJob: Job? = null
  private var errorStreak = 0
  private var apologized = false

  // MARK: - Triggers (the silent path: buttons; the voice path: ask)

  fun look() = startTurn { runModelTurn(AssistMode.LOOK, null, startedAt = SystemClock.elapsedRealtime()) }

  fun read() = startTurn { runModelTurn(AssistMode.READ, null, startedAt = SystemClock.elapsedRealtime()) }

  /**
   * Voice path. [requestMicPermission] asks for RECORD_AUDIO in context (phone recognizer on the
   * mock); on real glasses the Speech capability needs no phone mic permission.
   */
  fun ask(requestMicPermission: suspend () -> Boolean) = startTurn {
    val startedAt = SystemClock.elapsedRealtime()
    output.earcon(Earcon.LISTENING)
    _uiState.update {
      it.copy(phase = AssistPhase.LISTENING, mode = AssistMode.ASK, heard = "", lastWasError = false)
    }
    if (!requestMicPermission()) {
      speakRepair("Microphone is off. Use the Look or Read button.", startedAt)
      return@startTurn
    }
    val heard = speechInput.listenOnce { partial -> _uiState.update { it.copy(heard = partial) } }
    when (heard) {
      is HeardResult.Heard -> {
        _uiState.update { it.copy(heard = heard.text) }
        when (val command = VantagePrompts.parseCommand(heard.text)) {
          VantagePrompts.Command.Again -> repeatLast()
          VantagePrompts.Command.Stop -> finishIdle()
          VantagePrompts.Command.Help -> speakLine(VantagePrompts.HELP_LINE, startedAt, isError = false)
          is VantagePrompts.Command.Run -> runModelTurn(command.mode, command.question, startedAt)
        }
      }
      HeardResult.NothingHeard -> {
        errorStreak++
        speakRepair(VantagePrompts.nothingHeardLine(errorStreak), startedAt)
      }
      is HeardResult.Unavailable -> {
        Log.w(TAG, "speech unavailable: ${heard.reason}")
        speakRepair("Voice isn't available here. Use the Look or Read button.", startedAt)
      }
    }
  }

  /** "again": say the last answer once more. Works by voice and by button. */
  fun again() = startTurn { repeatLast() }

  /** "stop": the always-available exit. */
  fun stop() {
    turnJob?.cancel()
    turnJob = null
    speechInput.cancel()
    output.stop()
    _uiState.update { it.copy(phase = AssistPhase.IDLE) }
  }

  fun help() = startTurn { speakLine(VantagePrompts.HELP_LINE, SystemClock.elapsedRealtime(), isError = false) }

  // MARK: - The turn

  private fun startTurn(block: suspend () -> Unit) {
    // A new trigger interrupts the old turn, including anything still being spoken.
    turnJob?.cancel()
    speechInput.cancel()
    output.stop()
    turnJob =
        viewModelScope.launch {
          try {
            block()
          } catch (e: CancellationException) {
            throw e
          } catch (e: Exception) {
            Log.e(TAG, "turn failed: ${e.javaClass.simpleName}")
            speakRepair(VantagePrompts.rejectedLine(), SystemClock.elapsedRealtime())
          }
        }
  }

  private suspend fun runModelTurn(mode: AssistMode, question: String?, startedAt: Long) {
    // 1. Acknowledge first, within the 0.5 s budget, before any work.
    output.earcon(Earcon.WORKING)
    val ackMillis = SystemClock.elapsedRealtime() - startedAt
    _uiState.update {
      it.copy(
          phase = AssistPhase.CAPTURING,
          mode = mode,
          heard = question ?: it.heard,
          ackMillis = ackMillis,
          totalMillis = null,
          lastWasError = false,
      )
    }

    // 2. Capture: one frame, only now.
    val frame = frameSource.grabFrame()
    if (frame == null) {
      speakRepair(VantagePrompts.noFrameLine(), startedAt)
      return
    }

    // 3. Understand. Keep the wearer informed if it runs long; never silent over two seconds.
    _uiState.update { it.copy(phase = AssistPhase.THINKING) }
    val workingLine =
        viewModelScope.launch {
          delay(WORKING_LINE_AFTER_MS)
          output.say(VantagePrompts.workingLine(mode))
        }
    val result =
        try {
          model.ask(
              frame = frame,
              systemPrompt = VantagePrompts.systemPrompt(mode),
              question = VantagePrompts.userText(mode, question),
          )
        } finally {
          // Send, answer, delete: the frame does not outlive the call.
          frame.recycle()
          workingLine.cancel()
        }

    // 4. Respond.
    when (result) {
      is ModelResult.Answer -> {
        errorStreak = 0
        val text = VantagePrompts.tidy(result.text, mode)
        val totalMillis = SystemClock.elapsedRealtime() - startedAt
        Log.i(TAG, "turn ok mode=$mode ack=${ackMillis}ms total=${totalMillis}ms")
        _uiState.update {
          it.copy(phase = AssistPhase.SPEAKING, spoken = text, totalMillis = totalMillis)
        }
        output.say(text)
        output.earcon(Earcon.DONE)
        finishIdle()
      }
      is ModelResult.Failure -> {
        Log.w(TAG, "turn failed mode=$mode kind=${result.kind} ${result.detail}")
        val line =
            when (result.kind) {
              ModelResult.Failure.Kind.NO_KEY -> VantagePrompts.noKeyLine()
              ModelResult.Failure.Kind.OFFLINE -> VantagePrompts.offlineLine()
              ModelResult.Failure.Kind.TIMEOUT -> VantagePrompts.timeoutLine()
              ModelResult.Failure.Kind.REJECTED,
              ModelResult.Failure.Kind.EMPTY -> VantagePrompts.rejectedLine()
            }
        errorStreak++
        speakRepair(line, startedAt)
      }
    }
  }

  private suspend fun repeatLast() {
    val last = _uiState.value
    if (!last.canRepeat) {
      speakLine("Nothing to repeat yet. Tap Look or Read.", SystemClock.elapsedRealtime(), isError = false)
      return
    }
    _uiState.update { it.copy(phase = AssistPhase.SPEAKING) }
    output.say(last.spoken)
    finishIdle()
  }

  private suspend fun speakRepair(line: String, startedAt: Long) {
    output.earcon(Earcon.ERROR)
    // One apology at most, and after three errors in a row stop talking: the screen still shows the
    // line, and the buttons keep working. Hand off instead of looping.
    val text =
        when {
          errorStreak >= MAX_ERROR_STREAK -> "Let's use the phone buttons for now."
          !apologized && errorStreak >= 2 -> {
            apologized = true
            "Sorry. $line"
          }
          else -> line
        }
    speakLine(text, startedAt, isError = true)
  }

  private suspend fun speakLine(text: String, startedAt: Long, isError: Boolean) {
    _uiState.update {
      it.copy(
          phase = AssistPhase.SPEAKING,
          spoken = text,
          lastWasError = isError,
          totalMillis = SystemClock.elapsedRealtime() - startedAt,
      )
    }
    output.say(text)
    finishIdle()
  }

  private fun finishIdle() {
    _uiState.update { it.copy(phase = AssistPhase.IDLE) }
  }

  override fun onCleared() {
    super.onCleared()
    turnJob?.cancel()
    speechInput.release()
    output.release()
  }

  class Factory(
      private val application: Application,
      private val frameSource: FrameSource,
  ) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
      if (modelClass.isAssignableFrom(AssistViewModel::class.java)) {
        @Suppress("UNCHECKED_CAST")
        return AssistViewModel(application, frameSource) as T
      }
      throw IllegalArgumentException("Unknown ViewModel class")
    }
  }
}
