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
//
// Around the turns runs the awareness engine: the on-device detector and the firmware's announcer,
// speaking through a priority queue. It yields to a turn, except for critical alerts.

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
import com.vantage.glasses.awareness.Announcer
import com.vantage.glasses.awareness.AnnouncerConfig
import com.vantage.glasses.awareness.AwarenessEngine
import com.vantage.glasses.awareness.AwarenessState
import com.vantage.glasses.awareness.Detector
import com.vantage.glasses.voice.Priority
import com.vantage.glasses.voice.Settings
import com.vantage.glasses.voice.SpeechMessage
import com.vantage.glasses.voice.SpeechQueue
import com.vantage.glasses.voice.VantageSettings
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
    detector: Detector,
    private val settings: VantageSettings = VantageSettings(application),
    private val speechInput: SpeechInput = AndroidSpeechInput(application),
    private val output: SpokenOutput = SpokenOutput(application),
    private val model: MetaModelClient =
        MetaModelClient(
            apiKey = BuildConfig.META_API_KEY,
            modelId = BuildConfig.META_MODEL_ID,
            apiBase = BuildConfig.META_API_BASE,
            fallbackModels =
                BuildConfig.META_MODEL_FALLBACKS.split(',').map { it.trim() }.filter { it.isNotBlank() }
                    .ifEmpty { if (BuildConfig.META_API_BASE.contains("googleapis.com")) GEMINI_FALLBACKS else emptyList() },
        ),
) : AndroidViewModel(application) {

  companion object {
    private const val TAG = "Vantage:Assist"
    private const val WORKING_LINE_AFTER_MS = 1_500L
    private const val MAX_ERROR_STREAK = 3
    private const val QUIET_AFTER_TURN_MS = 3_000L
  }

  private val _uiState =
      MutableStateFlow(AssistUiState(hasApiKey = model.hasKey, language = settings.value.language))
  val uiState: StateFlow<AssistUiState> = _uiState.asStateFlow()

  val settingsState: StateFlow<Settings> = settings.state

  private val queue = SpeechQueue(output, viewModelScope)
  val nowSpeaking: StateFlow<SpeechMessage?> = queue.nowSpeaking
  val queueEvents: StateFlow<List<String>> = queue.events

  private val memory = SceneMemory()
  private val announcer = Announcer()
  private val awareness =
      AwarenessEngine(frameSource, detector, announcer, viewModelScope) { queue.enqueue(it) }
  val awarenessState: StateFlow<AwarenessState> = awareness.state

  private var turnJob: Job? = null
  private var errorStreak = 0
  private var apologized = false
  private var streaming = false

  private val language: AssistLanguage
    get() = settings.value.language

  init {
    queue.start()
    viewModelScope.launch {
      settings.state.collect { s ->
        announcer.config =
            AnnouncerConfig(
                criticalCm = s.criticalCm,
                warningCm = s.warningCm,
                repeatMs = (s.repeatSec * 1000).toLong(),
                describeMode = s.describeMode,
                beepOn = s.beepOn,
                language = s.language,
            )
        output.speechRate = s.speechRate
        _uiState.update { it.copy(language = s.language) }
        syncAwareness()
      }
    }
    viewModelScope.launch { output.setLanguage(language.locale) }
  }

  // MARK: - Stream and awareness

  /** Called by the screen when the glasses stream starts or stops. */
  fun setStreaming(live: Boolean) {
    streaming = live
    if (!live) memory.clear()
    syncAwareness()
  }

  private fun syncAwareness() {
    val wanted = streaming && settings.value.awarenessOn
    if (wanted && !awareness.isRunning) awareness.start()
    if (!wanted && awareness.isRunning) awareness.stop()
  }

  /** The Obstacles button: the only thing that starts the on-device detector. Vee confirms. */
  fun toggleAwareness() {
    val on = !settings.value.awarenessOn
    settings.update { it.copy(awarenessOn = on) }
    startTurn {
      speakLine(
          if (on) VantagePrompts.Lines.obstaclesOn(language) else VantagePrompts.Lines.obstaclesOff(language),
          SystemClock.elapsedRealtime(),
          isError = false,
      )
    }
  }

  /** Vee introduces herself on the welcome screen. */
  fun greet() = startTurn { speakLine(VantagePrompts.Lines.welcome(language), SystemClock.elapsedRealtime(), isError = false) }

  /** Vee says her eyes are open once the stream is live after Begin. */
  fun eyesOpen() = startTurn { speakLine(VantagePrompts.Lines.eyesOpen(language), SystemClock.elapsedRealtime(), isError = false) }

  fun toggleDescribe() = settings.update { it.copy(describeMode = !it.describeMode) }

  fun setCriticalCm(cm: Int) = settings.update { it.copy(criticalCm = cm.coerceIn(20, 120)) }

  fun setWarningCm(cm: Int) = settings.update { it.copy(warningCm = cm.coerceIn(60, 250)) }

  fun setRepeatSec(sec: Float) = settings.update { it.copy(repeatSec = sec.coerceIn(1f, 6f)) }

  fun setSpeechRate(rate: Float) = settings.update { it.copy(speechRate = rate.coerceIn(0.8f, 2.0f)) }

  fun toggleGestures() = settings.update { it.copy(gesturesOn = !it.gesturesOn) }

  fun toggleBeep() = settings.update { it.copy(beepOn = !it.beepOn) }

  /** EN <-> AR. Changes the prompt, the recognizer and the voice; confirms in the new language. */
  fun toggleLanguage() {
    val next = language.next()
    settings.update { it.copy(language = next) }
    startTurn {
      val hasVoice = output.setLanguage(next.locale)
      if (!hasVoice) Log.w(TAG, "no TTS voice for ${next.tag}")
      speakLine(VantagePrompts.Lines.languageSwitched(next), SystemClock.elapsedRealtime(), isError = false)
    }
  }

  // MARK: - Triggers (the silent path: buttons and gestures; the voice path: ask)

  fun look() = startTurn { runModelTurn(AssistMode.LOOK, null, startedAt = SystemClock.elapsedRealtime()) }

  fun read() = startTurn { runModelTurn(AssistMode.READ, null, startedAt = SystemClock.elapsedRealtime()) }

  fun shelf() = startTurn { runModelTurn(AssistMode.SHELF, null, startedAt = SystemClock.elapsedRealtime()) }

  /** The whole scene from the on-device detector. Nothing leaves the phone. */
  fun scene() = startTurn { speakLine(awareness.sceneLine(), SystemClock.elapsedRealtime(), isError = false) }

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
      speakRepair(VantagePrompts.Lines.micOff(language), startedAt)
      return@startTurn
    }
    val heard =
        speechInput.listenOnce(language.tag) { partial ->
          _uiState.update { it.copy(heard = partial) }
        }
    when (heard) {
      is HeardResult.Heard -> {
        _uiState.update { it.copy(heard = heard.text) }
        handleCommand(VantagePrompts.parseCommand(heard.text), heard.text, startedAt)
      }
      HeardResult.NothingHeard -> {
        errorStreak++
        speakRepair(VantagePrompts.Lines.nothingHeard(errorStreak, language), startedAt)
      }
      is HeardResult.Unavailable -> {
        Log.w(TAG, "speech unavailable: ${heard.reason}")
        speakRepair(VantagePrompts.Lines.voiceUnavailable(language), startedAt)
      }
    }
  }

  /** A typed or chip question: same path as voice, without the microphone. */
  fun askText(text: String) = startTurn {
    val startedAt = SystemClock.elapsedRealtime()
    _uiState.update { it.copy(heard = text, lastWasError = false) }
    handleCommand(VantagePrompts.parseCommand(text), text, startedAt)
  }

  private suspend fun handleCommand(command: VantagePrompts.Command, raw: String, startedAt: Long) {
    when (command) {
      VantagePrompts.Command.Again -> repeatLast()
      VantagePrompts.Command.Stop -> finishIdle()
      VantagePrompts.Command.Help -> speakLine(VantagePrompts.Lines.help(language), startedAt, isError = false)
      VantagePrompts.Command.Scene -> speakLine(awareness.sceneLine(), startedAt, isError = false)
      VantagePrompts.Command.More -> fromShelf(startedAt) { ShelfTalk.more(it, language) }
      VantagePrompts.Command.Exact -> fromShelf(startedAt) { ShelfTalk.exact(it, language) }
      VantagePrompts.Command.Cheapest -> fromShelf(startedAt) { ShelfTalk.cheapest(it, language) }
      is VantagePrompts.Command.Where -> fromShelf(startedAt) { ShelfTalk.where(it, command.item, language) }
      is VantagePrompts.Command.PriceOf -> fromShelf(startedAt) { ShelfTalk.priceOf(it, command.item, language) }
      is VantagePrompts.Command.Run -> runModelTurn(command.mode, command.question ?: raw.takeIf { command.mode == AssistMode.ASK }, startedAt)
    }
  }

  /** Shelf drill-downs come from memory. With no shelf in memory, scan one now. */
  private suspend fun fromShelf(startedAt: Long, line: (ShelfScene) -> String) {
    val scene = memory.currentShelf
    if (scene == null) {
      runModelTurn(AssistMode.SHELF, null, startedAt)
      return
    }
    speakLine(line(scene), startedAt, isError = false, remember = AssistMode.SHELF)
  }

  /** "again": say the last answer once more. Works by voice and by button. */
  fun again() = startTurn { repeatLast() }

  /** "stop": the always-available exit. Clears the queue too. */
  fun stop() {
    turnJob?.cancel()
    turnJob = null
    speechInput.cancel()
    viewModelScope.launch { queue.clear() }
    output.stop()
    awareness.quietUntil = SystemClock.elapsedRealtime() + QUIET_AFTER_TURN_MS
    awareness.yieldToAssist = false
    _uiState.update { it.copy(phase = AssistPhase.IDLE) }
  }

  fun help() = startTurn {
    speakLine(VantagePrompts.Lines.help(language), SystemClock.elapsedRealtime(), isError = false)
  }

  /** Speak one shelf item from the on-screen list. */
  fun speakItem(item: ShelfItem) = startTurn {
    val p = ShelfTalk.price(item, language)
    val text = if (p != null) "${item.name}, $p" else item.name
    speakLine(text, SystemClock.elapsedRealtime(), isError = false)
  }

  // MARK: - The turn

  private fun startTurn(block: suspend () -> Unit) {
    // A new trigger interrupts the old turn, including anything still being spoken.
    turnJob?.cancel()
    speechInput.cancel()
    output.stop()
    awareness.yieldToAssist = true
    turnJob =
        viewModelScope.launch {
          try {
            block()
          } catch (e: CancellationException) {
            throw e
          } catch (e: Exception) {
            Log.e(TAG, "turn failed: ${e.javaClass.simpleName}")
            speakRepair(VantagePrompts.Lines.rejected(language), SystemClock.elapsedRealtime())
          } finally {
            awareness.quietUntil = SystemClock.elapsedRealtime() + QUIET_AFTER_TURN_MS
            awareness.yieldToAssist = false
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

    // 2. Capture: one frame, only now. The click makes the capture audible.
    val frame = frameSource.grabFrame()
    if (frame == null) {
      speakRepair(VantagePrompts.Lines.noFrame(language), startedAt)
      return
    }
    output.earcon(Earcon.CLICK)

    // 3. Understand. Keep the wearer informed if it runs long; never silent over two seconds.
    _uiState.update { it.copy(phase = AssistPhase.THINKING) }
    val workingLine =
        viewModelScope.launch {
          delay(WORKING_LINE_AFTER_MS)
          output.say(VantagePrompts.workingLine(mode, language))
        }
    val result =
        try {
          model.ask(
              frame = frame,
              systemPrompt = VantagePrompts.systemPrompt(mode, language),
              question = VantagePrompts.userText(mode, question),
              history = if (mode == AssistMode.ASK) memory.conversation else emptyList(),
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
        _uiState.update { it.copy(errorDetail = null) }
        val totalMillis = SystemClock.elapsedRealtime() - startedAt
        Log.i(TAG, "turn ok mode=$mode ack=${ackMillis}ms total=${totalMillis}ms")
        if (mode == AssistMode.SHELF) {
          val scene = ShelfTalk.parse(result.text)
          if (scene == null) {
            // The model answered in prose; say it, tidied, rather than fail.
            val text = VantagePrompts.tidy(result.text, AssistMode.LOOK)
            _uiState.update { it.copy(phase = AssistPhase.SPEAKING, spoken = text, totalMillis = totalMillis) }
            memory.remember(text, mode)
            output.say(text)
          } else {
            memory.rememberShelf(scene)
            val text = ShelfTalk.gist(scene, language)
            _uiState.update {
              it.copy(phase = AssistPhase.SPEAKING, spoken = text, totalMillis = totalMillis, shelf = scene)
            }
            memory.remember(text, mode)
            output.say(text)
          }
        } else {
          val text = VantagePrompts.tidy(result.text, mode)
          _uiState.update { it.copy(phase = AssistPhase.SPEAKING, spoken = text, totalMillis = totalMillis) }
          memory.remember(text, mode, VantagePrompts.userText(mode, question))
          output.say(text)
        }
        output.earcon(Earcon.DONE)
        finishIdle()
      }
      is ModelResult.Failure -> {
        Log.w(TAG, "turn failed mode=$mode kind=${result.kind} ${result.detail}")
        val line =
            when (result.kind) {
              ModelResult.Failure.Kind.NO_KEY -> VantagePrompts.Lines.noKey(language)
              ModelResult.Failure.Kind.OFFLINE -> VantagePrompts.Lines.offline(language)
              ModelResult.Failure.Kind.TIMEOUT -> VantagePrompts.Lines.timeout(language)
              ModelResult.Failure.Kind.REJECTED,
              ModelResult.Failure.Kind.EMPTY -> VantagePrompts.Lines.rejected(language)
            }
        errorStreak++
        _uiState.update { it.copy(errorDetail = "${result.kind.name.lowercase()}: ${result.detail}".take(160)) }
        speakRepair(line, startedAt)
      }
    }
  }

  private suspend fun repeatLast() {
    val last = memory.recent.firstOrNull() ?: _uiState.value.takeIf { it.canRepeat }?.let { SpokenAnswer(it.spoken, it.mode ?: AssistMode.LOOK) }
    if (last == null) {
      speakLine(VantagePrompts.Lines.nothingToRepeat(language), SystemClock.elapsedRealtime(), isError = false)
      return
    }
    _uiState.update { it.copy(phase = AssistPhase.SPEAKING, spoken = last.text, lastWasError = false) }
    output.say(last.text)
    finishIdle()
  }

  private suspend fun speakRepair(line: String, startedAt: Long) {
    output.earcon(Earcon.ERROR)
    // One apology at most, and after three errors in a row stop talking: the screen still shows the
    // line, and the buttons keep working. Hand off instead of looping.
    val text =
        when {
          errorStreak >= MAX_ERROR_STREAK -> VantagePrompts.Lines.handOff(language)
          !apologized && errorStreak >= 2 -> {
            apologized = true
            VantagePrompts.Lines.sorry(language) + line
          }
          else -> line
        }
    speakLine(text, startedAt, isError = true)
  }

  private suspend fun speakLine(text: String, startedAt: Long, isError: Boolean, remember: AssistMode? = null) {
    _uiState.update {
      it.copy(
          phase = AssistPhase.SPEAKING,
          spoken = text,
          lastWasError = isError,
          totalMillis = SystemClock.elapsedRealtime() - startedAt,
      )
    }
    if (remember != null && !isError) memory.remember(text, remember)
    output.say(text)
    finishIdle()
  }

  private fun finishIdle() {
    _uiState.update { it.copy(phase = AssistPhase.IDLE) }
  }

  override fun onCleared() {
    super.onCleared()
    turnJob?.cancel()
    awareness.stop()
    speechInput.release()
    output.release()
    memory.clear()
  }

  class Factory(
      private val application: Application,
      private val frameSource: FrameSource,
      private val detector: Detector,
  ) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
      if (modelClass.isAssignableFrom(AssistViewModel::class.java)) {
        @Suppress("UNCHECKED_CAST")
        return AssistViewModel(application, frameSource, detector) as T
      }
      throw IllegalArgumentException("Unknown ViewModel class")
    }
  }
}
