import requests
import logging
from datetime import datetime
from config import DISCORD_WEBHOOK_URL

logger = logging.getLogger(__name__)

def send_discord(message: str) -> bool:
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL.startswith("DEIN") or DISCORD_WEBHOOK_URL.startswith("1234"):
        logger.warning("Discord Webhook nicht konfiguriert - Nachricht wird nur geloggt")
        print(f"\n[DISCORD-VORSCHAU]\n{message}\n")
        return False

    payload = {"content": message}
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Discord-Nachricht erfolgreich gesendet")
        return True
    except Exception as e:
        logger.error(f"Discord-Fehler: {e}")
        return False

def send_alert(ticker: str, title: str, summary: str, source: str, urgency: str = "MITTEL"):
    emoji_map = {"HOCH": "🚨", "MITTEL": "⚠️", "NIEDRIG": "ℹ️"}
    emoji = emoji_map.get(urgency, "⚠️")
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    msg = (
        f"{emoji} **FINANCIAL JARVIS ALARM** {emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **Ticker:** {ticker}\n"
        f"📰 **Ereignis:** {title}\n\n"
        f"🤖 **KI-Analyse:**\n{summary}\n\n"
        f"🔗 **Quelle:** {source}\n"
        f"🕐 {timestamp}"
    )
    send_discord(msg)

def send_price_alert(ticker: str, price: float, change_pct: float, reason: str = ""):
    direction = "📈" if change_pct > 0 else "📉"
    sign = "+" if change_pct > 0 else ""
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    msg = (
        f"{direction} **KURSALARM: {ticker}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Preis:** \n"
        f"📊 **Veraenderung:** {sign}{change_pct:.2f}%\n"
        f"{f'🤖 {reason}' if reason else ''}\n"
        f"🕐 {timestamp}"
    )
    send_discord(msg)

def send_morning_briefing(briefing_text: str):
    date_str = datetime.now().strftime("%A, %d. %B %Y")
    msg = (
        f"☀️ **GUTEN MORGEN - MARKTBRIEFING**\n"
        f"📅 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{briefing_text}"
    )
    send_discord(msg)

def send_evening_briefing(briefing_text: str):
    date_str = datetime.now().strftime("%A, %d. %B %Y")
    msg = (
        f"🌙 **ABEND-BRIEFING**\n"
        f"📅 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{briefing_text}"
    )
    send_discord(msg)