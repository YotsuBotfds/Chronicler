@echo off
REM Chronicler setup script for Windows — installs all dependencies and builds components.
REM Usage: setup.bat [--no-rust] [--api] [--gemini]

setlocal enabledelayedexpansion

set NO_RUST=0
set INSTALL_API=0
set INSTALL_GEMINI=0

:parse_args
if "%~1"=="" goto start
if "%~1"=="--no-rust"   set NO_RUST=1 & shift & goto parse_args
if "%~1"=="--api"       set INSTALL_API=1 & shift & goto parse_args
if "%~1"=="--gemini"    set INSTALL_GEMINI=1 & shift & goto parse_args
echo Unknown option: %~1
exit /b 1

:start
echo === Chronicler Setup ===
echo.

REM Check Python
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.13+ is required but not found.
    echo   Install from: https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [1/4] Found Python %%v

REM Create virtual environment
if not exist ".venv" (
    echo [2/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 exit /b 1
) else (
    echo [2/4] Virtual environment already exists
)

REM Activate
call .venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

REM Install Python dependencies
echo [3/4] Installing Python dependencies...
python -m pip install -e . --quiet
if errorlevel 1 exit /b 1

if %INSTALL_API%==1 (
    echo   Installing Claude API support...
    python -m pip install -e ".[api]" --quiet
    if errorlevel 1 exit /b 1
)

if %INSTALL_GEMINI%==1 (
    echo   Installing Gemini API support...
    python -m pip install -e ".[gemini]" --quiet
    if errorlevel 1 exit /b 1
)

REM Build Rust agent crate
if %NO_RUST%==1 (
    echo [4/4] Skipping Rust agent crate (--no-rust)
    goto done
)

where cargo >nul 2>nul
if errorlevel 1 (
    echo [4/4] Rust toolchain not found — skipping agent crate
    echo   Install from: https://rustup.rs/
    echo   Agent mode (--agents^) will not be available
    goto done
)

echo [4/4] Building Rust agent crate...
python -m pip install "maturin>=1.5,<2" --quiet
if errorlevel 1 exit /b 1
cd chronicler-agents
if errorlevel 1 exit /b 1
python -m maturin develop --release
if errorlevel 1 exit /b 1
cd ..
if errorlevel 1 exit /b 1

:done
echo.
echo === Setup Complete ===
echo.
echo To get started:
echo   .venv\Scripts\activate
echo   chronicler --seed 42 --turns 50 --simulate-only
echo.
echo For narration, run LM Studio with a model loaded, then:
echo   chronicler --seed 42 --turns 50

endlocal
