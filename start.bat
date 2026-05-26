@echo off
title Project Prim Launcher
cls
echo ===================================================
echo           Project Prim Voice Assistant
echo ===================================================
echo.

:: Force Python to use UTF-8 encoding (fixes CP1252/charmap errors on Windows)
set PYTHONUTF8=1

:: Check Python installation
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python and try again.
    pause
    exit /b 1
)

:: Check if Ollama is running locally
echo Checking Ollama status...
powershell -Command "$resp = Invoke-WebRequest -Uri 'http://localhost:11434' -UseBasicParsing -ErrorAction SilentlyContinue; if ($resp.StatusCode -eq 200) { exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
    echo [WARNING] Ollama is not responding on http://localhost:11434.
    echo Make sure Ollama is launched and has the target model ready:
    echo    ollama pull qwen2.5-coder:7b-instruct
    echo.
) else (
    echo [OK] Ollama is active.
)

:: Check for Virtual Environment
if not exist venv\Scripts\activate.bat (
    echo [INFO] Virtual environment not found. Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate Virtual Environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

:: Check and install dependencies
echo Verifying python dependencies...
python -c "import openwakeword, faster_whisper, kokoro_onnx, customtkinter, sounddevice, ollama, duckduckgo_search" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Missing dependencies. Installing from requirements.txt...
    python -m pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [OK] All dependencies verified.
)

:: Launch the application
echo Launching Project Prim...
echo.
python main.py
if errorlevel 1 (
    echo.
    echo [INFO] Application exited with code %errorlevel%.
    pause
)
