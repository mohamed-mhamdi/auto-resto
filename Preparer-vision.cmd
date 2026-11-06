@echo off
cd /d "%~dp0"
python -m venv .vision-env
if errorlevel 1 goto failed
".vision-env\Scripts\python.exe" -m pip install -r vision/requirements.txt
if errorlevel 1 goto failed
".vision-env\Scripts\python.exe" -c "import cv2, onnxruntime; print('Module vision installe.')"
pause
exit /b 0
:failed
echo Echec de l'installation. Verifiez Python et l'acces Internet.
pause
exit /b 1
