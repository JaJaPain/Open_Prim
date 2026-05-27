import os
import re
import time
import queue
import threading
import logging
import numpy as np
import sounddevice as sd

import config
from audio.wake_word import WakeWordDetector
from audio.vad_handler import SileroVAD
from audio.transcriber import AudioTranscriber
from audio.synthesizer import SpeechSynthesizer
from brain.llm_client import OllamaLLMClient
from brain.memory_manager import MemoryManager
from ui.dashboard import PrimDashboard

# Set up logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Prim.Main")

class GuiLogHandler(logging.Handler):
    """Custom logging handler to route logs directly into the CustomTkinter GUI panel."""
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard

    def emit(self, record):
        msg = self.format(record)
        self.dashboard.add_log(msg)


class AGC:
    """Automatic Gain Control to dynamically adjust microphone input levels.
    Prevents digital clipping while boosting quiet speech signals.
    """
    def __init__(self, target_level=0.30, max_gain=50.0, min_gain=1.0, release_co=0.05):
        self.target_level = target_level
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.release_co = release_co
        self.current_gain = 1.0  # Start with 1.0 gain to prevent initial burst clipping

    def process(self, chunk: np.ndarray) -> np.ndarray:
        peak = np.max(np.abs(chunk))
        if peak > 1e-5:
            ideal_gain = self.target_level / peak
            ideal_gain = np.clip(ideal_gain, self.min_gain, self.max_gain)
            
            # Instant attack (gain reduction) to prevent clipping, slow release (gain recovery)
            if ideal_gain < self.current_gain:
                self.current_gain = ideal_gain
            else:
                self.current_gain = (1.0 - self.release_co) * self.current_gain + self.release_co * ideal_gain
            
        return np.clip(chunk * self.current_gain, -1.0, 1.0)


class VoiceAssistant:
    def __init__(self):
        # Queues and events
        self.audio_queue = queue.Queue()
        self.text_input_queue = queue.Queue()  # Queue for typed text input from the GUI
        self.stop_event = threading.Event()
        
        # State indicators
        self.state = "SLEEPING"  # SLEEPING, LISTENING, THINKING, SPEAKING
        self.interrupted = False
        self.manual_interrupt = False
        self.listening_start_time = 0.0
        self.sleep_cooldown_until = 0.0  # Timestamp until which wake word detection is suppressed after speech
        
        # Mute states
        self.mic_muted = False
        self.voice_muted = False
        
        # Buffer to keep track of assistant speech for interruption logs
        self.spoken_text_buffer = ""
        self.current_user_query = ""
        
        # Setup UI dashboard with callback mappings
        self.dashboard = PrimDashboard(
            interrupt_callback=self.trigger_manual_interrupt,
            close_callback=self.shutdown,
            text_input_callback=self._handle_text_input,
            mute_mic_callback=self._handle_mute_mic,
            mute_voice_callback=self._handle_mute_voice
        )
        
        # Route logger records to GUI console
        gui_handler = GuiLogHandler(self.dashboard)
        gui_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logging.getLogger().addHandler(gui_handler)
        
        # Initialize subcomponents
        self.memory_manager = MemoryManager()
        self.vad = SileroVAD()
        self.wake_word_detector = WakeWordDetector()
        self.agc = AGC(
            target_level=0.30,
            max_gain=50.0,
            min_gain=1.0,
            release_co=0.05
        )
        
        # Initialize heavier AI modules in a separate thread so the UI is responsive
        self.transcriber = None
        self.synthesizer = None
        self.llm_client = None
        
        self.init_thread = threading.Thread(target=self._initialize_ai_models, daemon=True)
        self.init_thread.start()
        
        # Initialize microphone audio input stream
        self.mic_stream = None
        
        # Start orchestration thread
        self.orch_thread = threading.Thread(target=self._orchestration_loop, daemon=True)
        self.orch_thread.start()

    def _initialize_ai_models(self):
        """Loads Whisper, Kokoro, and Ollama in the background to prevent GUI freeze."""
        logger.info("Initializing heavy model pipelines in background...")
        start_time = time.time()
        
        self.transcriber = AudioTranscriber()
        self.synthesizer = SpeechSynthesizer()
        self.synthesizer.muted = self.voice_muted
        self.llm_client = OllamaLLMClient()
        
        duration = time.time() - start_time
        logger.info(f"AI models initialized successfully in {duration:.2f}s.")
        self.dashboard.add_log("System fully ready! Listening for 'Prim' (or fallback wake word)...")

    def _mic_callback(self, indata, frames, time_info, status):
        """sounddevice stream callback pushing audio chunks to input queue."""
        if status:
            logger.warning(f"Microphone overflow status: {status}")
        # Convert to 1D and apply AGC
        chunk_1d = np.squeeze(indata)
        chunk_processed = self.agc.process(chunk_1d)
        
        if self.mic_muted:
            chunk_processed = np.zeros_like(chunk_processed)
            
        self.audio_queue.put(chunk_processed)

    def set_state(self, new_state: str):
        """Thread-safe update of state and UI."""
        self.state = new_state
        self.dashboard.set_status(new_state)
        logger.debug(f"State changed to: {new_state}")

    def trigger_manual_interrupt(self):
        """Triggered when the user clicks the INTERRUPT button in the GUI."""
        self.manual_interrupt = True

    def _handle_text_input(self, text: str):
        """Called from the GUI thread when user submits typed text. Queues it for the orchestration loop."""
        self.text_input_queue.put(text)

    def _handle_mute_mic(self, muted: bool):
        """Called from the GUI thread when user toggles microphone mute."""
        self.mic_muted = muted
        logger.info(f"Microphone mute state changed to: {muted}")

    def _handle_mute_voice(self, muted: bool):
        """Called from the GUI thread when user toggles voice output mute."""
        self.voice_muted = muted
        if self.synthesizer:
            self.synthesizer.muted = muted
        logger.info(f"Voice output mute state changed to: {muted}")

    def _play_thinking_filler(self, user_text: str):
        """Plays a brief spoken filler word based on user query keywords to reduce perceived latency."""
        import random
        from skills import SKILL_INSTANCES
        
        user_text_lower = user_text.lower()
        filler = None
        for skill in SKILL_INSTANCES.values():
            if skill.filler_keywords and any(w in user_text_lower for w in skill.filler_keywords):
                if skill.filler_phrases:
                    filler = random.choice(skill.filler_phrases)
                    break
            
        if filler:
            logger.info(f"Playing thinking filler: '{filler}'")
            self.dashboard.add_transcript("Prim (Thinking)", f"({filler})")
            self.synthesizer.generate_and_play(filler)

    def _process_typed_input(self, user_text: str, sentence_end_re, wakeword_buffer):
        """Handles typed text input: skips wake word/VAD/Whisper and goes straight to LLM → TTS."""
        logger.info(f"Processing typed input: '{user_text}'")
        self.dashboard.add_transcript("User", user_text)
        self.current_user_query = user_text
        
        self.set_state("THINKING")
        
        # Play thinking filler if query requires tool execution
        self._play_thinking_filler(user_text)
        
        # Build context messages and request LLM
        self.dashboard.add_log("Querying Qwen2.5 / Searching tools...")
        messages = self.llm_client.build_messages(user_text, self.memory_manager)
        
        # Get the stream generator from LLM
        token_stream = self.llm_client.chat_stream(messages)
        
        # Stream iteration logic
        self.spoken_text_buffer = ""
        full_response = ""
        text_accumulator = ""
        self.interrupted = False
        first_token = True
        
        for token in token_stream:
            if self.manual_interrupt:
                break
            
            if first_token:
                self.set_state("SPEAKING")
                # Purge mic queue
                while not self.audio_queue.empty():
                    try:
                        self.audio_queue.get_nowait()
                    except queue.Empty:
                        break
                self.wake_word_detector.reset()
                first_token = False
            
            full_response += token
            text_accumulator += token
            
            # Sentence-level text chunking for smoother TTS pacing
            sentences = sentence_end_re.split(text_accumulator)
            
            if len(sentences) > 2:
                for i in range(0, len(sentences) - 2, 2):
                    sentence_part = sentences[i] + sentences[i+1]
                    sentence_part = sentence_part.strip()
                    if sentence_part:
                        self.synthesizer.generate_and_play(sentence_part)
                        self.spoken_text_buffer += " " + sentence_part
                
                text_accumulator = sentences[-1]
            elif len(text_accumulator.split()) > 15:
                words = text_accumulator.split()
                chunk_to_speak = " ".join(words[:12])
                self.synthesizer.generate_and_play(chunk_to_speak)
                self.spoken_text_buffer += " " + chunk_to_speak
                text_accumulator = " ".join(words[12:])
        
        # Speak remaining trailing tokens
        if text_accumulator.strip() and not self.interrupted and not self.manual_interrupt:
            self.synthesizer.generate_and_play(text_accumulator.strip())
            self.spoken_text_buffer += " " + text_accumulator.strip()
        
        # Wait for TTS audio to complete playing
        while self.synthesizer.is_playing() and not self.interrupted and not self.manual_interrupt:
            time.sleep(0.05)
        
        # Handle interruption or normal completion
        if self.interrupted or self.manual_interrupt:
            self._handle_interruption()
            self.manual_interrupt = False
        else:
            logger.info("Typed input interaction complete. Recording log turn.")
            self.memory_manager.save_turn(self.current_user_query, full_response)
            self.dashboard.add_transcript("Prim", full_response)
            time.sleep(0.5)
        
        self.set_state("SLEEPING")
        self.wake_word_detector.reset()
        # Purge mic queue and set cooldown
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.sleep_cooldown_until = time.time() + 2.0

    def _orchestration_loop(self):
        """Core state machine looping in background."""
        # Wait for model components to fully load
        while self.transcriber is None or self.synthesizer is None or self.llm_client is None:
            time.sleep(0.1)

        # Start microphone recording stream
        try:
            self.mic_stream = sd.InputStream(
                samplerate=config.INPUT_SAMPLE_RATE,
                blocksize=config.INPUT_CHUNK_SIZE,
                channels=config.INPUT_CHANNELS,
                dtype='float32',
                callback=self._mic_callback
            )
            self.mic_stream.start()
            logger.info("Microphone input stream started.")
        except Exception as e:
            logger.error(f"Failed to start mic stream: {e}")
            self.dashboard.add_log("CRITICAL ERROR: Sound card input error. Wake word and VAD disabled.")
            return

        # Buffers for wake word checking
        wakeword_buffer = np.zeros(0, dtype=np.float32)
        
        # Audio accumulator for recording user speech
        recorded_audio = []
        speech_started = False
        silent_chunks = 0
        consecutive_user_speech_frames = 0
        
        # Punctuation separator for TTS segmentation
        # Only split on sentence-ending punctuation followed by whitespace.
        # This prevents splitting decimal numbers like "79.4" or "5.4 mph".
        sentence_end_re = re.compile(r"([.?!;]+(?=\s)|\n+)")

        while not self.stop_event.is_set():
            # Flush state controls
            if self.manual_interrupt:
                self._handle_interruption()
                self.manual_interrupt = False
                
                # Force transition to Listening
                self.set_state("LISTENING")
                recorded_audio = []
                speech_started = False
                silent_chunks = 0
                consecutive_user_speech_frames = 0
                self.vad.reset_states()
                wakeword_buffer = np.zeros(0, dtype=np.float32)
                continue

            # Check for typed text input from the GUI
            try:
                typed_text = self.text_input_queue.get_nowait()
                if typed_text:
                    self._process_typed_input(typed_text, sentence_end_re, wakeword_buffer)
                    wakeword_buffer = np.zeros(0, dtype=np.float32)
                    continue
            except queue.Empty:
                pass

            try:
                # Retrieve float32 audio chunk (already processed by AGC)
                chunk_1d = self.audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            # State Machine: SLEEPING (Listening for Wake Word)
            if self.state == "SLEEPING":
                # Post-speech cooldown: consume mic audio but skip wake word detection
                # to prevent Prim's own echo from triggering phantom interactions.
                if time.time() < self.sleep_cooldown_until:
                    continue
                
                # openWakeWord expects 1280 sample frames (80ms at 16kHz)
                wakeword_buffer = np.concatenate((wakeword_buffer, chunk_1d))
                
                # Process all available 1280-sample blocks (non-overlapping)
                while len(wakeword_buffer) >= 1280:
                    ww_chunk = wakeword_buffer[:1280]
                    # Convert float32 [-1, 1] to int16 PCM
                    ww_chunk_int16 = (ww_chunk * 32767.0).astype(np.int16)
                    
                    if self.wake_word_detector.process(ww_chunk_int16):
                        self.set_state("LISTENING")
                        logger.info("Wake word detected! Listening...")
                        self.dashboard.add_log("Wake word detected! Adjusting to LISTENING state...")
                        
                        # Clean up buffers & VAD states
                        recorded_audio = []
                        speech_started = False
                        silent_chunks = 0
                        consecutive_user_speech_frames = 0
                        self.vad.reset_states()
                        wakeword_buffer = np.zeros(0, dtype=np.float32)
                        
                        break  # Exit the while loop to handle state change
                    
                    # Advance the buffer by slicing out the processed 1280 samples (non-overlapping step)
                    wakeword_buffer = wakeword_buffer[1280:]

            # State Machine: LISTENING (Recording User Speech)
            elif self.state == "LISTENING":
                prob = self.vad.process(chunk_1d)
                self.dashboard.set_vad_probability(prob)
                
                # Check for interruption cooldown to filter out transient speaker bleed
                import time as tm
                if tm.time() - self.listening_start_time < 0.4:
                    recorded_audio = []
                    speech_started = False
                    silent_chunks = 0
                    continue
                
                # Store audio frames
                recorded_audio.append(chunk_1d)
                
                # State tracking
                if prob > config.VAD_SPEECH_THRESHOLD:
                    if not speech_started:
                        speech_started = True
                        logger.info("User speech onset detected...")
                    silent_chunks = 0
                else:
                    if speech_started:
                        silent_chunks += 1
                        # Each chunk represents 32ms of audio (512 samples at 16kHz)
                        silence_duration = silent_chunks * 0.032
                        if silence_duration >= config.VAD_SILENCE_LIMIT_SEC:
                            self.set_state("THINKING")
                            logger.info("User completed speaking (silence detected).")
                
                # Check for absolute listening timeout (if user didn't speak anything for 6.0 seconds)
                # 6 seconds = 187 blocks of 32ms
                if not speech_started and len(recorded_audio) > 187:
                    logger.info("Listening session timed out. No speech detected.")
                    self.dashboard.add_log("Listening timeout. Going back to sleep...")
                    self.set_state("SLEEPING")
                    recorded_audio = []
                    wakeword_buffer = np.zeros(0, dtype=np.float32)
                    self.wake_word_detector.reset()  # Reset wake word detector state history!
                    # Purge mic queue to avoid processing stale timeout audio
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break

            # State Machine: THINKING (Inference & News Search)
            elif self.state == "THINKING":
                self.dashboard.add_log("Transcribing vocal query...")
                
                # Combine accumulated recording chunks
                full_audio = np.concatenate(recorded_audio)
                
                # Reset buffers
                recorded_audio = []
                
                # STT Transcription
                user_text = self.transcriber.transcribe(full_audio)
                if not user_text:
                    self.dashboard.add_log("Transcription empty. Sleeping...")
                    self.set_state("SLEEPING")
                    wakeword_buffer = np.zeros(0, dtype=np.float32)
                    self.wake_word_detector.reset()  # Reset wake word detector state history!
                    # Purge mic queue to avoid processing stale transcription audio
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break
                    continue
                
                self.dashboard.add_transcript("User", user_text)
                self.current_user_query = user_text
                
                # Play thinking filler if query requires tool execution
                self._play_thinking_filler(user_text)
                
                # Build context messages and request LLM
                self.dashboard.add_log("Querying Qwen2.5 / Searching tools...")
                messages = self.llm_client.build_messages(user_text, self.memory_manager)
                
                # Get the stream generator from LLM
                token_stream = self.llm_client.chat_stream(messages)
                
                # Stream iteration logic
                self.spoken_text_buffer = ""
                full_response = ""
                text_accumulator = ""
                self.interrupted = False
                
                # Keep state as THINKING initially. We will transition to SPEAKING
                # and purge the queue only when the first actual token is received.
                # This prevents the speaker bleed from thinking fillers and tool call
                # latency from causing self-interruption.
                first_token = True
                
                for token in token_stream:
                    if self.manual_interrupt:
                        break
                    
                    if first_token:
                        self.set_state("SPEAKING")
                        # Purge mic queue to discard any accumulated audio from thinking filler playback & tool execution blocking
                        while not self.audio_queue.empty():
                            try:
                                self.audio_queue.get_nowait()
                            except queue.Empty:
                                break
                        wakeword_buffer = np.zeros(0, dtype=np.float32)
                        self.wake_word_detector.reset()
                        first_token = False
                    
                    full_response += token
                    text_accumulator += token
                    
                    # Interruption check: While LLM generates, the mic thread is active.
                    # We run openWakeWord on mic chunks to detect wake word interruption
                    while not self.audio_queue.empty():
                        try:
                            mic_chunk_1d = self.audio_queue.get_nowait()
                            
                            # Accumulate in wake word buffer
                            wakeword_buffer = np.concatenate((wakeword_buffer, mic_chunk_1d))
                            while len(wakeword_buffer) >= 1280:
                                ww_chunk = wakeword_buffer[:1280]
                                wakeword_buffer = wakeword_buffer[1280:]
                                
                                ww_chunk_int16 = (ww_chunk * 32767.0).astype(np.int16)
                                if self.wake_word_detector.process(ww_chunk_int16, threshold=0.88):
                                    logger.info("Wake word override detected during generation! Interrupting...")
                                    self.interrupted = True
                                    break
                        except queue.Empty:
                            break
                    
                    if self.interrupted:
                        break
                    
                    # Sentence-level text chunking for smoother TTS pacing
                    sentences = sentence_end_re.split(text_accumulator)
                    
                    if len(sentences) > 2:
                        for i in range(0, len(sentences) - 2, 2):
                            sentence_part = sentences[i] + sentences[i+1]
                            sentence_part = sentence_part.strip()
                            if sentence_part:
                                self.synthesizer.generate_and_play(sentence_part)
                                self.spoken_text_buffer += " " + sentence_part
                        
                        text_accumulator = sentences[-1]
                    elif len(text_accumulator.split()) > 15:
                        words = text_accumulator.split()
                        chunk_to_speak = " ".join(words[:12])
                        self.synthesizer.generate_and_play(chunk_to_speak)
                        self.spoken_text_buffer += " " + chunk_to_speak
                        text_accumulator = " ".join(words[12:])
                
                # Speak remaining trailing tokens
                if text_accumulator.strip() and not self.interrupted and not self.manual_interrupt:
                    self.synthesizer.generate_and_play(text_accumulator.strip())
                    self.spoken_text_buffer += " " + text_accumulator.strip()
                
                # Wait for TTS audio to complete playing, monitoring for wake word interrupt continuously
                while self.synthesizer.is_playing() and not self.interrupted and not self.manual_interrupt:
                    try:
                        mic_chunk_1d = self.audio_queue.get(timeout=0.02)
                        
                        # Accumulate in wake word buffer
                        wakeword_buffer = np.concatenate((wakeword_buffer, mic_chunk_1d))
                        while len(wakeword_buffer) >= 1280:
                            ww_chunk = wakeword_buffer[:1280]
                            wakeword_buffer = wakeword_buffer[1280:]
                            
                            ww_chunk_int16 = (ww_chunk * 32767.0).astype(np.int16)
                            if self.wake_word_detector.process(ww_chunk_int16, threshold=0.88):
                                logger.info("Wake word override detected during audio playback! Interrupting...")
                                self.interrupted = True
                                break
                    except queue.Empty:
                        continue
                
                # Handle Interruption Execution
                if self.interrupted or self.manual_interrupt:
                    self._handle_interruption()
                    self.manual_interrupt = False
                    
                    # Instantly return to LISTENING state to catch user speech
                    self.set_state("LISTENING")
                    self.listening_start_time = time.time()
                    speech_started = False
                    silent_chunks = 0
                    consecutive_user_speech_frames = 0
                    self.vad.reset_states()
                    wakeword_buffer = np.zeros(0, dtype=np.float32)
                    recorded_audio = []
                else:
                    # Normal completion
                    logger.info("Interaction complete. Recording log turn.")
                    self.memory_manager.save_turn(self.current_user_query, full_response)
                    self.dashboard.add_transcript("Prim", full_response)
                    
                    # Post-speech cooldown to wait out hardware sound card buffer latency and echo
                    time.sleep(0.5)
                    
                    self.set_state("SLEEPING")
                    wakeword_buffer = np.zeros(0, dtype=np.float32)
                    self.wake_word_detector.reset()  # Reset wake word detector state history!
                    # Clear mic queue
                    while not self.audio_queue.empty():
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break
                    
                    # Set a 2-second cooldown so Prim's echo doesn't re-trigger the wake word
                    self.sleep_cooldown_until = time.time() + 2.0

            # State Machine: SPEAKING (Passive placeholder, handled in THINKING logic for thread sync)
            elif self.state == "SPEAKING":
                # Loop safety fallback
                time.sleep(0.1)

    def _handle_interruption(self):
        """Core Immediate Flush Protocol execution."""
        logger.info("Executing Immediate Flush Protocol...")
        
        # 1. Stop active audio synthesis and soundcard stream instantly
        if self.synthesizer:
            self.synthesizer.stop()
            
        # Short sleep to allow the audio hardware to settle and stop
        time.sleep(0.2)
        
        # Clear mic queue to discard any speaker bleed from active playback/interruption transition
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
                
        # 2. Get spoken text up to this instant
        spoken_text = self.spoken_text_buffer.strip()
        logger.info(f"User interrupted assistant speech. Spoken text was: '{spoken_text}'")
        
        # 3. Log the interrupted state to the session markdown file
        self.memory_manager.save_interrupted_turn(self.current_user_query, spoken_text)
        
        # 4. Display interrupted response in GUI
        self.dashboard.add_transcript("Prim (Interrupted)", f"{spoken_text}...")
        self.dashboard.add_log("USER INTERRUPTED - Purged speech pipeline instantly.")

    def shutdown(self):
        """Gracefully terminates audio, UI, and helper worker threads."""
        logger.info("Shutting down voice assistant services...")
        self.stop_event.set()
        
        if self.mic_stream:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass
                
        if self.synthesizer:
            try:
                self.synthesizer.stop()
            except Exception:
                pass
                
        logger.info("Voice assistant shutdown complete.")


# Main runner
if __name__ == "__main__":
    assistant = VoiceAssistant()
    # start() is blocking and runs the main loop of CustomTkinter
    assistant.dashboard.start()
