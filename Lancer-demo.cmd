@echo off
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Installez Python 3.11 ou plus recent, puis relancez cette demo.
  pause
  exit /b 1
)
echo Ouvrez http://127.0.0.1:8765 dans votre navigateur.
python server.py --demo
pause
