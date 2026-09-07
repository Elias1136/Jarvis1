@echo off
chcp 65001 > nul
echo Starte Financial Jarvis Dashboard...
call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python dashboard.py
pause
