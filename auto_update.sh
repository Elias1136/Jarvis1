#!/bin/bash
# Jarvis Auto-Updater
# Prueft jede Minute GitHub auf Aenderungen und startet Jarvis neu

REPO_DIR="/home/$USER/jarvis_git"
ENV_FILE="/home/$USER/jarvis/.env"
SETTINGS_FILE="/home/$USER/jarvis/jarvis_settings.json"

cd "$REPO_DIR" || exit 1

while true; do
    # GitHub auf neue Version pruefen
    git fetch origin main --quiet 2>/dev/null

    LOCAL=$(git rev-parse HEAD 2>/dev/null)
    REMOTE=$(git rev-parse origin/main 2>/dev/null)

    if [ "$LOCAL" != "$REMOTE" ]; then
        echo "[$(date)] Neue Version gefunden! Aktualisiere..."

        # Neue Dateien holen
        git pull origin main --quiet

        # .env und settings aus dem alten Ordner kopieren (werden nicht auf GitHub gespeichert)
        cp "$ENV_FILE" "$REPO_DIR/.env" 2>/dev/null || true
        cp "$SETTINGS_FILE" "$REPO_DIR/jarvis_settings.json" 2>/dev/null || true

        # Alte Python-Pakete aktualisieren falls noetig
        source "$REPO_DIR/venv/bin/activate" 2>/dev/null || python3 -m venv "$REPO_DIR/venv"
        pip install -r "$REPO_DIR/requirements.txt" --quiet

        # Jarvis neu starten
        pkill -f discord_bot.py 2>/dev/null
        sleep 2
        cd "$REPO_DIR"
        source venv/bin/activate
        nohup python3 discord_bot.py > jarvis.log 2>&1 &
        echo "[$(date)] Jarvis neu gestartet mit Version: $REMOTE"
    fi

    sleep 60
done
