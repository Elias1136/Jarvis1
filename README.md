# 💼 Financial Jarvis

Dein persoenlicher KI-Finanzanalyst - wie Bloomberg Terminal, aber mit Push-Nachrichten aufs Handy.

## Was kann er?

| Funktion | Details |
|---|---|
| 📊 Echtzeit-Kurse | Aktien & Krypto aus deiner Watchlist |
| 📰 News-Scanner | Finnhub, NewsAPI, 8x RSS-Feeds (inkl. Weisses Haus) |
| 🤖 KI-Filter | GPT-4o filtert unwichtige News heraus |
| 🚨 Push-Alarme | Telegram-Benachrichtigung bei wichtigen Ereignissen |
| ☀️ Morgen-Briefing | 07:00 Uhr - KI-Zusammenfassung der Marktlage |
| 🌙 Abend-Briefing | 20:00 Uhr - Rueckblick auf den Handelstag |
| 📅 Earnings-Kalender | Bevorstehende Quartalszahlen deiner Watchlist |
| 🏢 Fundamentaldaten | KGV, EPS, Marktkapitalisierung etc. |

## Setup (Schritt fuer Schritt)

### Schritt 1: Setup ausfuehren
Doppelklick auf setup.bat - das installiert alles automatisch.

### Schritt 2: API-Keys besorgen (alle kostenlos!)

**OpenAI** (das KI-Gehirn):
- https://platform.openai.com/api-keys
- ~0.01-0.05 Dollar pro Analyse

**Telegram Bot** (Push-Nachrichten):
1. Oeffne Telegram, schreibe an @BotFather
2. Schreibe: /newbot
3. Folge den Anweisungen -> Du bekommst einen Token
4. Schreibe an @userinfobot -> Du bekommst deine Chat-ID

**Finnhub** (Finanznews & Kurse):
- https://finnhub.io -> Kostenlos registrieren

**NewsAPI** (globale Nachrichten):
- https://newsapi.org -> Kostenlos registrieren

**Alpha Vantage** (Aktienkurse, optional):
- https://alphavantage.co -> Kostenlos registrieren

### Schritt 3: .env Datei erstellen
`
copy .env.example .env
`
Dann .env in einem Texteditor oeffnen und Keys eintragen.

### Schritt 4: Starten

**Automatischer Modus** (laeuft im Hintergrund, sendet Push-Nachrichten):
`
start_jarvis.bat
`

**Interaktives Dashboard** (manuelle Analysen):
`
start_dashboard.bat
`

## Datei-Struktur

`
FinancialJarvis/
  jarvis.py        <- Hauptprogramm (automatischer Modus)
  dashboard.py     <- Interaktives Terminal-Dashboard
  ai_analyst.py    <- KI-Gehirn (GPT-4o Analysen)
  data_fetcher.py  <- Alle Datenquellen (Kurse, News, RSS)
  notifier.py      <- Telegram Push-Nachrichten
  config.py        <- Einstellungen
  .env             <- Deine API-Keys (GEHEIM!)
  requirements.txt <- Python-Pakete
`

## Watchlist anpassen

Oeffne .env und aendere:
`
WATCHLIST_STOCKS=AAPL,NVDA,TSLA,MSFT,AMZN,SPY
WATCHLIST_CRYPTO=BTC-USD,ETH-USD,SOL-USD
`

## Haftungsausschluss

Dieses Tool liefert Informationen und KI-Analysen. Es ersetzt keine professionelle Anlageberatung. Alle Handelsentscheidungen liegen beim Nutzer.
