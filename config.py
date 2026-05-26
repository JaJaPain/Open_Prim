import os
import sys
import site

# Project root directory
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Register NVIDIA CUDA/cuDNN DLL directories on Windows to enable GPU acceleration
if sys.platform == "win32":
    # Collect possible site-packages paths
    paths = []
    # Project venv site-packages
    paths.append(os.path.join(ROOT_DIR, "venv", "Lib", "site-packages"))
    # System/active site-packages
    try:
        paths.extend(site.getsitepackages())
    except Exception:
        pass
        
    # Add each found NVIDIA bin directory to DLL search path and environment PATH
    for p in paths:
        if os.path.exists(p):
            for lib_name in ["cuda_runtime", "cublas", "cudnn", "cuda_nvrtc", "cufft", "curand", "cusparse", "cusolver", "nvtx"]:
                bin_path = os.path.join(p, "nvidia", lib_name, "bin")
                if os.path.exists(bin_path):
                    # Add to os.add_dll_directory for Python DLL loading
                    try:
                        os.add_dll_directory(bin_path)
                    except Exception:
                        pass
                    # Add to os.environ["PATH"] for standard library loading
                    if bin_path not in os.environ["PATH"]:
                        os.environ["PATH"] = bin_path + os.path.pathsep + os.environ["PATH"]

# Storage directories
STORAGE_DIR = os.path.join(ROOT_DIR, "storage")
MODELS_DIR = os.path.join(STORAGE_DIR, "models")
MEMORY_DIR = os.path.join(STORAGE_DIR, "memory")

# Create directories if they do not exist
for path in [MODELS_DIR, MEMORY_DIR]:
    os.makedirs(path, exist_ok=True)

# Audio Settings
INPUT_SAMPLE_RATE = 16000  # VAD, Whisper, openWakeWord require 16kHz
INPUT_CHANNELS = 1
INPUT_CHUNK_SIZE = 512    # 32ms chunks (512 samples) for direct Silero VAD alignment
MIC_GAIN = 60.0           # Deprecated: AGC in main.py dynamically controls gain now

OUTPUT_SAMPLE_RATE = 24000 # Kokoro outputs 24kHz
OUTPUT_CHANNELS = 1

# Wake Word Settings
WAKE_WORD_MODEL = "alexa"  # Fallback built-in model; we can also look for custom ONNX
WAKE_WORD_THRESHOLD = 0.5
CUSTOM_WAKE_WORD_PATH = os.path.join(MODELS_DIR, "prim.onnx")

# VAD Settings
VAD_MODEL_PATH = os.path.join(MODELS_DIR, "silero_vad.onnx")
VAD_SPEECH_THRESHOLD = 0.35
VAD_INTERRUPT_THRESHOLD = 0.75  # Higher VAD threshold to prevent speaker feedback self-interruption
VAD_MIN_RAW_PEAK = 0.015  # Minimum raw (unamplified) peak amplitude required to trigger voice interruption
VAD_SILENCE_LIMIT_SEC = 0.6  # Stop recording after this duration of silence

# Speech-to-Text (STT) Settings
STT_MODEL_NAME = "Systran/faster-distil-whisper-large-v3"  # Converted CTranslate2 model for faster-whisper
STT_DEVICE = "cuda"  # Can be "cuda" or "cpu"
STT_COMPUTE_TYPE = "float16"  # "float16" for GPU, "int8" or "float32" for CPU

# Text-to-Speech (TTS) Settings
TTS_MODEL_PATH = os.path.join(MODELS_DIR, "kokoro-v1.0.onnx")
TTS_VOICES_PATH = os.path.join(MODELS_DIR, "voices.json")
TTS_DEFAULT_VOICE = "af_bella"  # Premium female voice
TTS_SPEED = 1.0

# Ollama LLM Settings
OLLAMA_HOST = "http://localhost:11434"
LLM_MODEL = "qwen2.5-coder:7b"
LLM_SYSTEM_PROMPT = """You are Prim, a helpful, ultra-low latency local voice assistant.
Respond conversationally, concisely, and naturally. Since you are speaking to the user:
- Keep your answers short, ideally 1-3 sentences, unless the user asks for a detailed explanation.
- Do not output markdown lists, code blocks, or formatting tags unless specifically asked, as they are hard to read aloud.
- Use natural pauses and phrasing.
- If you call a tool, weave the tool output naturally into your spoken response.
- When the user tells you personal details (like where they live, their name, their interests, or preferences) or asks you to remember something, call the 'save_preference' tool to save that fact to memory so you remember it in future conversations.
- For weather queries, if the user does not specify a location, check user preferences to find where they live (e.g., Kokomo, Indiana) and use that for the 'fetch_weather' tool call.
"""
