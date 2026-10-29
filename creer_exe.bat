@echo off
rem Crée un programme autonome dist\Musicotheque\Musicotheque.exe (à copier sur un autre PC sans Python)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lancez d'abord installer.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\pyinstaller.exe" --noconfirm --windowed --name Musicotheque ^
  --collect-all pedalboard --collect-all yt_dlp --hidden-import sounddevice ^
  --add-data "bin;bin" main.py
rem Les outils doivent être à côté de l'exe
xcopy /E /I /Y bin "dist\Musicotheque\bin" >nul
echo.
echo Programme cree : dist\Musicotheque\Musicotheque.exe
pause
