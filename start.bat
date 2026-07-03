@echo off
REM MemoFast - Baslatlci (Sade versiyon - UTF-8 sorunu var)
cd /d "%~dp0"

if exist "python_enbed\python.exe" (
    "python_enbed\python.exe" "memofast_gui.py"
) else (
    python "memofast_gui.py"
)

pause
exit /b %errorlevel%
