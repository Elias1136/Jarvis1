@echo off
echo ============================================
echo   Financial Jarvis - Setup
echo ============================================
echo.

:: Python-Version pruefen
python --version
if errorlevel 1 (
    echo FEHLER: Python ist nicht installiert!
    echo Bitte Python 3.10+ von https://python.org herunterladen
    pause
    exit /b 1
)

:: Virtuelle Umgebung erstellen
echo [1/3] Erstelle virtuelle Python-Umgebung...
python -m venv venv

:: Aktivieren
echo [2/3] Aktiviere Umgebung...
call venv\Scripts\activate.bat

:: Pakete installieren
echo [3/3] Installiere Pakete...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ============================================
echo   Setup abgeschlossen!
echo ============================================
echo.
echo NAECHSTE SCHRITTE:
echo 1. Kopiere .env.example zu .env
echo    copy .env.example .env
echo 2. Oeffne .env und trage deine API-Keys ein
echo 3. Starte den Jarvis:
echo    venv\Scripts\activate && python jarvis.py
echo.
pause
