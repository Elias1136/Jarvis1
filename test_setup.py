# ============================================================
# test_setup.py - Testet alle API-Verbindungen
# Starte mit: python test_setup.py
# ============================================================
import sys
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("  FINANCIAL JARVIS - Verbindungstest")
print("=" * 50)

all_ok = True

# --- 1. Umgebungsvariablen pruefen ---
print("\n[1] Pruefe Konfiguration...")
keys_to_check = {
    "GROQ_API_KEY":       "Groq AI",
    "DISCORD_WEBHOOK_URL": "Discord Webhook",
    "FINNHUB_API_KEY":    "Finnhub",
    "NEWSAPI_KEY":        "NewsAPI",
}
for key, name in keys_to_check.items():
    val = os.getenv(key, "")
    if not val or val.startswith("DEIN") or val.startswith("1234567"):
        print(f"  [!!]  {name}: NICHT GESETZT")
        all_ok = False
    else:
        print(f"  [OK] {name}: OK ({val[:8]}...)")


# --- 2. Yahoo Finance (kein Key noetig) ---
print("\n[2] Teste Yahoo Finance (kein Key noetig)...")
try:
    import requests
    url = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    price = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    print(f"  [OK] Yahoo Finance: AAPL = ")
except Exception as e:
    print(f"  [X] Yahoo Finance Fehler: {e}")
    all_ok = False


# --- 3. Finnhub testen ---
print("\n[3] Teste Finnhub...")
finnhub_key = os.getenv("FINNHUB_API_KEY", "")
if finnhub_key and not finnhub_key.startswith("DEIN"):
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": finnhub_key},
            timeout=10
        )
        count = len(r.json())
        print(f"  [OK] Finnhub: {count} aktuelle News geladen")
    except Exception as e:
        print(f"  [X] Finnhub Fehler: {e}")
else:
    print(f"  [--]  Finnhub: Key fehlt - uebersprungen")


# --- 4. RSS-Feed testen ---
print("\n[4] Teste RSS-Feeds...")
try:
    import feedparser
    feed = feedparser.parse("https://feeds.reuters.com/reuters/businessNews")
    count = len(feed.entries)
    print(f"  [OK] Reuters RSS: {count} Artikel geladen")
except Exception as e:
    print(f"  [X] RSS-Fehler: {e}")


# --- 5. Groq KI testen ---
print("
[5] Teste Groq KI...")
groq_key = os.getenv("GROQ_API_KEY", "")
if groq_key and not groq_key.startswith("gsk_DEIN"):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
        resp = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": "Antworte nur mit: Jarvis aktiv!"}],
            max_tokens=20
        )
        answer = resp.choices[0].message.content
        print(f"  [OK] Groq (Llama 3): '{answer}'")
    except Exception as e:
        print(f"  [X] Groq Fehler: {e}")
else:
    print("  [--]  Groq: Key fehlt - uebersprungen")

# --- 6. Discord testen ---
print("
[6] Teste Discord...")
discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
if discord_url and not discord_url.startswith("DEIN") and not discord_url.startswith("1234"):
    try:
        import requests
        r = requests.post(
            discord_url,
            json={"content": "✅ **Financial Jarvis Test erfolgreich!**
Alle Systeme sind bereit. Jarvis ist einsatzbereit!"},
            timeout=10
        )
        if r.status_code in [200, 204]:
            print("  [OK] Discord: Test-Nachricht gesendet! Schau auf deinen Server.")
        else:
            print(f"  [X] Discord Fehler: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"  [X] Discord Fehler: {e}")
else:
    print("  [--]  Discord: Webhook URL fehlt - uebersprungen")

# --- Zusammenfassung ---
print("\n" + "=" * 50)
if all_ok:
    print("  >>> ALLES BEREIT! Starte mit: start_jarvis.bat")
else:
    print("  [!!]  Einige Keys fehlen noch.")
    print("  Oeffne .env und trage die fehlenden Keys ein.")
    print("  Dann diesen Test nochmal ausfuehren.")
print("=" * 50)
