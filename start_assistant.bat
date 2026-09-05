@echo off
REM Lanza el asistente de voz (usa la carpeta donde esta este .bat, no ruta fija).
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" voice_assistant.py
pause
