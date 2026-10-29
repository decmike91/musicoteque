@echo off
chcp 65001 >nul
echo Installation de Musicotheque...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
