import os
import numpy as np
import logging
import config

# Try importing openwakeword. If not installed yet, handle gracefully.
try:
    from openwakeword.model import Model
except ImportError:
    Model = None

logger = logging.getLogger("Prim.WakeWord")

class WakeWordDetector:
    def __init__(self, wakeword_name=config.WAKE_WORD_MODEL, threshold=config.WAKE_WORD_THRESHOLD):
        self.threshold = threshold
        self.model_name = wakeword_name
        self.model = None

        if Model is None:
            logger.warning("openwakeword package is not installed. Wake word detection will be disabled.")
            return

        try:
            # Check if custom "prim.onnx" model exists
            if os.path.exists(config.CUSTOM_WAKE_WORD_PATH):
                logger.info(f"Loading custom wake word model from {config.CUSTOM_WAKE_WORD_PATH}")
                self.model = Model(
                    wakeword_models=[config.CUSTOM_WAKE_WORD_PATH],
                    inference_framework="onnx"
                )
                self.model_name = list(self.model.models.keys())[0]
            else:
                logger.info(f"Loading built-in openWakeWord model '{self.model_name}' (ONNX framework)...")
                # Load only the target model explicitly to bypass TFLite checks
                self.model = Model(
                    wakeword_models=[self.model_name],
                    inference_framework="onnx"
                )
                # Check loaded keys
                available_models = list(self.model.models.keys())
                if available_models:
                    self.model_name = available_models[0]
                else:
                    raise RuntimeError("No wake word models loaded.")
            
            logger.info(f"Wake word detector active. Listening for '{self.model_name}' (threshold {self.threshold})")
        except Exception as e:
            logger.error(f"Error initializing openWakeWord: {e}")
            self.model = None

    def reset(self):
        """Resets the internal prediction buffers of openWakeWord model."""
        if self.model is not None:
            try:
                self.model.reset()
                logger.debug("Wake word model internal buffers reset.")
            except Exception as e:
                logger.error(f"Failed to reset wake word model: {e}")

    def process(self, audio_chunk_int16: np.ndarray) -> bool:
        """
        Processes a 1280-sample chunk of 16-bit 16kHz PCM.
        Returns True if the wake word is detected.
        """
        if self.model is None:
            return False

        try:
            # openwakeword predict accepts numpy int16 array of 1280 samples
            # Returns a dict of model_name -> probability
            predictions = self.model.predict(audio_chunk_int16)
            score = predictions.get(self.model_name, 0.0)
            
            if score >= self.threshold:
                logger.info(f"Wake word '{self.model_name}' detected! Score: {score:.3f}")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error in wake word processing: {e}")
            return False
