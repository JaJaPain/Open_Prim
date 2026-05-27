import numpy as np
import logging
import config

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger("Prim.Transcriber")

# Known Whisper hallucination phrases generated from near-silent or echo audio.
# These are extremely common phantom outputs and are never meaningful voice commands.
WHISPER_HALLUCINATIONS = {
    "thank you", "thanks", "thank you for watching", "thanks for watching",
    "subscribe", "like and subscribe", "please subscribe",
    "bye", "goodbye", "see you next time", "see you",
    "the end", "silence", "you", "so",
}

class AudioTranscriber:
    def __init__(self, model_name=config.STT_MODEL_NAME, device=config.STT_DEVICE, compute_type=config.STT_COMPUTE_TYPE):
        self.model = None
        if WhisperModel is None:
            logger.warning("faster-whisper is not installed. Speech transcription will be disabled.")
            return

        try:
            logger.info(f"Initializing Faster-Whisper model '{model_name}' on '{device}' ({compute_type})...")
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
            # Run dummy transcribe and force evaluation to verify CUDA libraries (cuBLAS/cuDNN) are loadable
            dummy_audio = np.zeros(16000, dtype=np.float32)
            segments, _ = self.model.transcribe(dummy_audio, language="en")
            list(segments)
            logger.info("Faster-Whisper initialized successfully on GPU.")
        except Exception as e:
            logger.warning(f"Could not load/run Faster-Whisper on {device} ({e}). Falling back to CPU with int8 quantization.")
            try:
                self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
                # Verify CPU transcriber works as well
                dummy_audio = np.zeros(16000, dtype=np.float32)
                segments, _ = self.model.transcribe(dummy_audio, language="en")
                list(segments)
                logger.info("Faster-Whisper initialized successfully on CPU.")
            except Exception as cpu_err:
                logger.error(f"Failed to load/run Whisper model on CPU: {cpu_err}")
                self.model = None

    def transcribe(self, audio_float32: np.ndarray) -> str:
        """
        Transcribes the given 1D float32 audio buffer (16kHz).
        Returns the transcribed text string.
        Filters out segments with high no-speech probability and known hallucination phrases.
        """
        if self.model is None:
            return "[Transcriber not initialized]"

        if len(audio_float32) == 0:
            return ""

        try:
            # transcribe returns a generator of segments, and transcription info
            # we specify language="en" to skip language detection latency
            # vad_filter uses Silero VAD to pre-screen audio and reject non-speech regions
            segments, info = self.model.transcribe(
                audio_float32, 
                beam_size=3,  # Smaller beam size for lower latency
                language="en", 
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_speech_duration_ms=250)
            )
            
            # Reconstruct transcript from segments, filtering out non-speech
            text_segments = []
            for segment in segments:
                # Skip segments where Whisper believes there is no speech
                if segment.no_speech_prob > 0.6:
                    logger.debug(f"Filtered non-speech segment (no_speech_prob={segment.no_speech_prob:.2f}): '{segment.text}'")
                    continue
                text_segments.append(segment.text)
                
            transcription = "".join(text_segments).strip()
            
            # Check against known hallucination phrases
            # Normalize by stripping punctuation and lowering case
            import string
            normalized = transcription.lower().translate(str.maketrans("", "", string.punctuation)).strip()
            if normalized in WHISPER_HALLUCINATIONS:
                logger.info(f"Filtered Whisper hallucination: '{transcription}' (normalized: '{normalized}')")
                return ""
            
            logger.info(f"Transcribed audio: '{transcription}' (Language probability: {info.language_probability:.2f})")
            return transcription
        except Exception as e:
            logger.error(f"Error during audio transcription: {e}")
            return ""
