@echo off
cd /d "%~dp0"
if not exist ".vision-env\Scripts\python.exe" (
  echo Lancez Preparer-vision.cmd avant de demarrer le replay.
  pause
  exit /b 1
)
".vision-env\Scripts\python.exe" evaluation/launch_replay.py
pause
