import os
import re
import queue
import threading
import requests
import numpy as np
import sounddevice as sd
import logging
import config

try:
    from kokoro_onnx import Kokoro
except ImportError:
    Kokoro = None

logger = logging.getLogger("Prim.Synthesizer")

class AudioPlayer:
    """Thread-safe non-blocking audio player that allows immediate interruption."""
    def __init__(self):
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.interrupt_event = threading.Event()
        self.stream = None
        self.thread = None
        self.playing = False
        self._start_worker()

    def _start_worker(self):
        self.stop_event.clear()
        self.interrupt_event.clear()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        try:
            self.stream = sd.OutputStream(
                samplerate=config.OUTPUT_SAMPLE_RATE,
                channels=config.OUTPUT_CHANNELS,
                dtype='float32'
            )
            self.stream.start()
        except Exception as e:
            logger.error(f"Error starting sounddevice OutputStream: {e}")
            return

        while not self.stop_event.is_set():
            try:
                # Polling wait to allow checking stop_event
                chunk = self.queue.get(timeout=0.05)
                if chunk is None:
                    self.queue.task_done()
                    continue
                
                self.playing = True
                self.interrupt_event.clear()
                
                # Ensure the stream is active before writing (in case it was aborted)
                if self.stream.stopped:
                    try:
                        self.stream.start()
                    except Exception as start_err:
                        logger.error(f"Error starting stream in worker: {start_err}")
                
                # Write in small blocks to allow rapid lock-free interruption
                block_size = 1024
                for offset in range(0, len(chunk), block_size):
                    if self.interrupt_event.is_set() or self.stop_event.is_set():
                        break
                    block = chunk[offset:offset+block_size]
                    try:
                        self.stream.write(block)
                    except Exception as write_err:
                        logger.error(f"Write error: {write_err}")
                        break
                
                self.queue.task_done()
            except queue.Empty:
                self.playing = False
                continue
            except Exception as e:
                logger.error(f"Exception in audio playback worker: {e}")
                self.playing = False
                break

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

    def play(self, samples: np.ndarray):
        """Queue raw float32 samples to play."""
        self.queue.put(samples)

    def stop(self):
        """Instantly aborts current playback and flushes the queue."""
        # Signal the worker to stop writing the current chunk immediately
        self.interrupt_event.set()
        
        # Purge remaining queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except (queue.Empty, ValueError):
                break
                
        # Abort the soundcard active playback buffer to stop sound instantly
        if self.stream:
            try:
                self.stream.abort()
            except Exception as e:
                logger.warning(f"Error aborting stream: {e}")
                
        self.playing = False


class SpeechSynthesizer:
    def __init__(self, model_path=config.TTS_MODEL_PATH, voices_path=config.TTS_VOICES_PATH):
        self.model_path = model_path
        self.voices_path = voices_path
        self.kokoro = None
        self.player = AudioPlayer()
        self.muted = False
        
        self._ensure_models_exist()
        self._init_kokoro()

    def _ensure_models_exist(self):
        """Downloads the Kokoro ONNX model and voices file if they are missing."""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        files_to_download = [
            (self.model_path, "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"),
            (self.voices_path, "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json")
        ]
        
        for file_path, url in files_to_download:
            if not os.path.exists(file_path):
                logger.info(f"Model asset missing: {file_path}. Downloading from {url}...")
                try:
                    response = requests.get(url, stream=True, timeout=60)
                    if response.status_code == 200:
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0
                        with open(file_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0 and downloaded % (8192 * 100) == 0:
                                        percent = (downloaded / total_size) * 100
                                        logger.info(f"Downloading {os.path.basename(file_path)}: {percent:.1f}%")
                        logger.info(f"Successfully downloaded {os.path.basename(file_path)}.")
                    else:
                        raise RuntimeError(f"Download failed with status: {response.status_code}")
                except Exception as e:
                    raise RuntimeError(f"Failed to download required asset {os.path.basename(file_path)}: {e}")

    def _init_kokoro(self):
        if Kokoro is None:
            logger.warning("kokoro-onnx package is not installed. Synthesizer will be disabled.")
            return
        try:
            import onnxruntime as ort
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            available = ort.get_available_providers()
            if 'CUDAExecutionProvider' in available:
                logger.info("Initializing Kokoro TTS model on GPU (CUDAExecutionProvider)...")
                sess = ort.InferenceSession(self.model_path, providers=providers)
                self.kokoro = Kokoro.from_session(sess, self.voices_path)
                logger.info("Kokoro TTS model loaded successfully on GPU.")
            else:
                logger.info("Initializing Kokoro TTS model on CPU...")
                self.kokoro = Kokoro(self.model_path, self.voices_path)
                logger.info("Kokoro TTS model loaded successfully on CPU.")
        except Exception as e:
            logger.error(f"Error initializing Kokoro TTS: {e}")
            self.kokoro = None

    def generate_and_play(self, text: str):
        """Synthesizes text and plays it immediately."""
        if self.muted:
            logger.debug(f"Speech synthesizer is muted. Skipping playback of: '{text}'")
            return

        if self.kokoro is None:
            logger.warning(f"TTS skipped (not initialized). Output: {text}")
            return

        text = text.strip()
        if not text:
            return

        try:
            # Generate raw audio samples
            # Kokoro output sample rate is 24000Hz
            logger.debug(f"Synthesizing text segment: '{text}'")
            samples, sample_rate = self.kokoro.create(
                text,
                voice=config.TTS_DEFAULT_VOICE,
                speed=config.TTS_SPEED,
                lang="en-us"
            )
            
            # Queue to player
            self.player.play(samples.astype(np.float32))
        except Exception as e:
            logger.error(f"Error during TTS synthesis of '{text}': {e}")

    def is_playing(self) -> bool:
        """Returns True if the system is currently playing speech."""
        return self.player.playing or not self.player.queue.empty()

    def stop(self):
        """Instantly stops playback."""
        self.player.stop()
