@echo off
rem Recompile l'aide Windows avec HTML Help Workshop (hhc.exe)
cd /d "%~dp0"
set HHC="%ProgramFiles(x86)%\HTML Help Workshop\hhc.exe"
if not exist %HHC% set HHC=hhc.exe
%HHC% Musicotheque.hhp
copy /Y Musicotheque.chm ..\Musicotheque.chm >nul
echo Aide creee : aide\Musicotheque.chm
pause
