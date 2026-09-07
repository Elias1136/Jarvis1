@echo off
chcp 65001 > nul
echo Starte Interaktiven Financial Jarvis Discord Bot...
call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python discord_bot.py
pause
