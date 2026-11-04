@echo off
REM Chronicler setup script for Windows — installs all dependencies and builds components.
REM Usage: setup.bat [--no-rust] [--native-venv] [--api] [--gemini]
REM
REM With uv the default .venv is installed exactly from uv.lock (uv sync --frozen).
REM Without uv it falls back to an UNLOCKED pip install -e . and says so.
REM Any chronicler_agents already in .venv is removed first. The Rust extension
REM is built into .venv, or with --native-venv into a separate native venv
REM (CHRONICLER_NATIVE_VENV, default USERPROFILE\.venvs\chronicler-native) so
REM .venv stays extension-free; scripts\check_python_env.py verifies the result.

setlocal enabledelayedexpansion

set NO_RUST=0
set SEPARATE_NATIVE=0
set INSTALL_API=0
set INSTALL_GEMINI=0

:parse_args
if "%~1"=="" goto start
if "%~1"=="--no-rust"   set "NO_RUST=1" & shift & goto parse_args
if "%~1"=="--native-venv" set "SEPARATE_NATIVE=1" & shift & goto parse_args
if "%~1"=="--api"       set "INSTALL_API=1" & shift & goto parse_args
if "%~1"=="--gemini"    set "INSTALL_GEMINI=1" & shift & goto parse_args
echo Unknown option: %~1
exit /b 1

:start
cd /d "%~dp0"
if not defined UV_PROJECT_ENVIRONMENT set "UV_PROJECT_ENVIRONMENT=.venv"
set "VENV=%UV_PROJECT_ENVIRONMENT%"
if not defined CHRONICLER_NATIVE_VENV set "CHRONICLER_NATIVE_VENV=%USERPROFILE%\.venvs\chronicler-native"
set "NATIVE_VENV=%CHRONICLER_NATIVE_VENV%"
set "TARGET_VENV=%VENV%"
if %SEPARATE_NATIVE%==1 set "TARGET_VENV=%NATIVE_VENV%"
set "UV_EXTRAS="
if %INSTALL_API%==1 set "UV_EXTRAS=!UV_EXTRAS! --extra api"
if %INSTALL_GEMINI%==1 set "UV_EXTRAS=!UV_EXTRAS! --extra gemini"

echo === Chronicler Setup ===
echo.

REM Check Python
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.13+ is required but not found.
    echo   Install from: https://www.python.org/downloads/
    exit /b 1
)
python -c "import sys; raise SystemExit(sys.version_info < (3, 13))"
if errorlevel 1 (
    echo ERROR: Python 3.13+ is required; the python on PATH is older or does not run.
    echo   Install from: https://www.python.org/downloads/
    exit /b 1
)
for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%p"

for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [1/4] Found Python %%v

REM Python dependencies: locked with uv, otherwise an unlocked pip fallback
where uv >nul 2>nul
if errorlevel 1 goto pip_fallback
set USE_UV=1
echo [2/4] Installing locked Python dependencies into %VENV% (uv sync --frozen)...
uv lock --check --python "%PYTHON_EXE%"
if errorlevel 1 exit /b 1
goto install_default

:pip_fallback
set USE_UV=0
echo [2/4] WARNING: uv not found; falling back to an UNLOCKED pip install into %VENV%.
echo   Versions are whatever the package index serves today, not uv.lock, so this
echo   environment may differ from CI. For the locked setup install uv and rerun:
echo   https://docs.astral.sh/uv/getting-started/installation/

:install_default
call :install_env "%VENV%"
if errorlevel 1 exit /b 1
if %USE_UV%==1 goto native
"%VENV%\Scripts\python.exe" -m pip show chronicler-agents >nul 2>nul
if errorlevel 1 goto native
echo   Removing the previously installed chronicler_agents from %VENV%
"%VENV%\Scripts\python.exe" -m pip uninstall -y chronicler-agents --quiet
if errorlevel 1 exit /b 1

REM Build Rust agent crate into .venv, or with --native-venv into the native venv
:native
set BUILT_NATIVE=0
if %NO_RUST%==1 goto skip_native
where cargo >nul 2>nul
if errorlevel 1 goto no_cargo

echo [3/4] Building Rust agent crate into %TARGET_VENV%...
if %SEPARATE_NATIVE%==0 goto native_maturin
call :install_env "%NATIVE_VENV%"
if errorlevel 1 exit /b 1

:native_maturin
set "MATURIN_FLAGS="
if %USE_UV%==0 goto native_activate
uv pip install --quiet --python "%TARGET_VENV%\Scripts\python.exe" "maturin>=1.5,<2"
if errorlevel 1 exit /b 1
REM A uv venv has no pip.
set "MATURIN_FLAGS=--uv"

:native_activate
REM Activation sets VIRTUAL_ENV, which maturin develop installs into.
call "%TARGET_VENV%\Scripts\activate.bat"
if errorlevel 1 exit /b 1
if %USE_UV%==1 goto native_build
python -m pip install "maturin>=1.5,<2" --quiet
if errorlevel 1 exit /b 1

:native_build
cd chronicler-agents
if errorlevel 1 exit /b 1
python -m maturin develop --release --locked %MATURIN_FLAGS%
if errorlevel 1 exit /b 1
cd ..
if errorlevel 1 exit /b 1
call "%TARGET_VENV%\Scripts\deactivate.bat"
set BUILT_NATIVE=1
goto verify

:skip_native
echo [3/4] Skipping Rust agent crate (--no-rust)
goto verify

:no_cargo
echo [3/4] Rust toolchain not found — skipping agent crate
echo   Install from: https://rustup.rs/
echo   Agent mode (--agents) will not be available

:verify
echo [4/4] Verifying environments...
if %BUILT_NATIVE%==1 if %SEPARATE_NATIVE%==0 goto verify_native
"%VENV%\Scripts\python.exe" scripts\check_python_env.py --expect no-native
if errorlevel 1 goto bad_default
if %BUILT_NATIVE%==0 goto done

:verify_native
"%TARGET_VENV%\Scripts\python.exe" scripts\check_python_env.py --expect native
if errorlevel 1 goto bad_native

:done
echo.
echo === Setup Complete ===
echo.
echo To get started:
echo   %VENV%\Scripts\activate
echo   chronicler --seed 42 --turns 50 --simulate-only
if %BUILT_NATIVE%==0 goto narration
if %SEPARATE_NATIVE%==0 goto agents_default
echo.
echo Agent mode (--agents) runs from the native venv:
echo   "%NATIVE_VENV%\Scripts\activate"
echo   chronicler --seed 42 --turns 100 --agents hybrid --simulate-only
goto narration

:agents_default
echo   chronicler --seed 42 --turns 100 --agents hybrid --simulate-only

:narration
echo.
echo For narration, run LM Studio with a model loaded, then:
echo   chronicler --seed 42 --turns 50

endlocal
exit /b 0

:bad_default
echo ERROR: %VENV% is not a clean no-native environment for this checkout; see above.
exit /b 1

:bad_native
echo ERROR: %TARGET_VENV% does not hold a compiled chronicler_agents for this checkout; see above.
exit /b 1

REM Install the project into the given environment: an exact uv sync of uv.lock,
REM or an unlocked editable pip install when uv is absent.
:install_env
if %USE_UV%==0 goto install_env_pip
set "UV_PROJECT_ENVIRONMENT=%~1"
uv sync --frozen --python "%PYTHON_EXE%" %UV_EXTRAS%
if errorlevel 1 exit /b 1
exit /b 0

:install_env_pip
if exist "%~1\Scripts\python.exe" goto install_env_pip_deps
"%PYTHON_EXE%" -m venv "%~1"
if errorlevel 1 exit /b 1

:install_env_pip_deps
"%~1\Scripts\python.exe" -m pip install -e . pytest pytest-asyncio --quiet
if errorlevel 1 exit /b 1
if %INSTALL_API%==1 "%~1\Scripts\python.exe" -m pip install -e ".[api]" --quiet
if errorlevel 1 exit /b 1
if %INSTALL_GEMINI%==1 "%~1\Scripts\python.exe" -m pip install -e ".[gemini]" --quiet
if errorlevel 1 exit /b 1
exit /b 0
