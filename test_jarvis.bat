@echo off
chcp 65001 > nul
echo Teste Financial Jarvis Setup...
call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python test_setup.py
pause
