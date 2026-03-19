@echo off
REM MemoFast - Başlatıcı
cd /d "%~dp0"

REM Eğer zaten bir kopya çalışıyorsa (opsiyonel temizlik)
REM taskkill /f /im python.exe /fi "windowtitle eq MemoFast*" /t 2>nul

if exist "python_enbed\python.exe" (
    start "" "python_enbed\python.exe" "memofast_gui.py"
) else (
    start "" python "memofast_gui.py"
)

exit
