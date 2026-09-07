@echo off
chcp 65001 > nul
echo Starte Financial Jarvis...
call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python jarvis.py
pause
