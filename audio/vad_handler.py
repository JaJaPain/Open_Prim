import os
import requests
import numpy as np
import onnxruntime as ort
import logging
import config

logger = logging.getLogger("Prim.VAD")

class SileroVAD:
    def __init__(self, model_path=config.VAD_MODEL_PATH):
        self.model_path = model_path
        self._ensure_model_exists()
        
        # Initialize ONNX Runtime Session
        # Run on CPU for low footprint, as Silero VAD is tiny
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(self.model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        
        self.reset_states()
        logger.info("Silero VAD initialized successfully.")

    def _ensure_model_exists(self):
        """Downloads the Silero VAD ONNX model if it does not exist locally."""
        if not os.path.exists(self.model_path):
            logger.info(f"Silero VAD model not found at {self.model_path}. Downloading...")
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            
            # URLs to download silero_vad.onnx
            urls = [
                "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
                "https://huggingface.co/onnx-community/Silero-VAD-ONNX/resolve/main/silero_vad.onnx"
            ]
            
            success = False
            for url in urls:
                try:
                    logger.info(f"Attempting download from: {url}")
                    response = requests.get(url, timeout=30)
                    if response.status_code == 200:
                        with open(self.model_path, "wb") as f:
                            f.write(response.content)
                        logger.info("Silero VAD model downloaded successfully.")
                        success = True
                        break
                except Exception as e:
                    logger.warning(f"Failed download from {url}: {e}")
            
            if not success:
                raise RuntimeError(
                    f"Could not download Silero VAD model from any source. "
                    f"Please place silero_vad.onnx manually in {self.model_path}"
                )

    def reset_states(self):
        """Resets the LSTM cell state and context buffer."""
        # Silero VAD v5 expects a single state tensor of shape (2, batch_size, 128)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def process(self, audio_chunk: np.ndarray) -> float:
        """
        Processes a single audio chunk and returns speech probability.
        audio_chunk: 1D numpy float32 array normalized to [-1, 1].
                     Must be 512 samples long for 16kHz (32ms).
        """
        # Ensure chunk is 1D and correct size
        if audio_chunk.ndim > 1:
            audio_chunk = np.squeeze(audio_chunk)
        
        if len(audio_chunk) != 512:
            # Pad or truncate to 512 samples if necessary
            if len(audio_chunk) < 512:
                audio_chunk = np.pad(audio_chunk, (0, 512 - len(audio_chunk)), mode='constant')
            else:
                audio_chunk = audio_chunk[:512]
        
        # Reshape to (1, 512) for batch_size=1
        chunk_2d = np.expand_dims(audio_chunk, axis=0).astype(np.float32)
        
        # Prepend context to get 576 samples
        x = np.concatenate([self._context, chunk_2d], axis=1)
        
        # Save last 64 samples of current chunk + context as new context
        self._context = x[:, -64:]
        
        inputs = {
            "input": x,
            "sr": np.array(config.INPUT_SAMPLE_RATE, dtype=np.int64),
            "state": self._state
        }
        
        try:
            # Run inference: outputs [speech_prob, new_state]
            out, new_state = self.session.run(None, inputs)
            self._state = new_state
            return float(out[0][0])
        except Exception as e:
            logger.error(f"VAD Inference Error: {e}")
            return 0.0
