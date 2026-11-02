@echo off
REM =====================================================================
REM  One-click build of SDLCOrchestrator.exe (Windows + Python required).
REM  Run this file from inside the sdlc_orchestrator folder.
REM =====================================================================
setlocal

echo [1/4] Creating a temporary build environment...
python -m venv .venv-build
call .venv-build\Scripts\activate.bat
if errorlevel 1 goto :fail

echo [2/4] Installing dependencies...
pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo [3/4] Building SDLCOrchestrator.exe - this can take several minutes...
pyinstaller --noconfirm --clean --onefile --name SDLCOrchestrator --collect-all streamlit launcher.py
if errorlevel 1 goto :fail

echo [4/4] Build finished.
echo.
echo NEXT STEPS:
echo   1. Copy dist\SDLCOrchestrator.exe into THIS folder, next to app.py.
echo   2. Copy config.example.json to config.json and paste your tokens in it.
echo   3. Double-click SDLCOrchestrator.exe and open http://localhost:8501.
echo.
echo NOTE: config.json is NOT inside the exe on purpose - it can be edited
echo or rotated without rebuilding, and the exe can be shared without secrets.
goto :end

:fail
echo.
echo BUILD FAILED - check the messages above.

:end
pause
endlocal
