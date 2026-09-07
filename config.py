# ============================================================
# config.py - Zentrale Konfiguration fuer Financial Jarvis
# ============================================================
import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
FINNHUB_API_KEY     = os.getenv("FINNHUB_API_KEY", "")
NEWSAPI_KEY         = os.getenv("NEWSAPI_KEY", "")
ALPHAVANTAGE_KEY    = os.getenv("ALPHAVANTAGE_KEY", "")

# --- Watchlists ---
WATCHLIST_STOCKS  = [t.strip() for t in os.getenv("WATCHLIST_STOCKS", "AAPL,NVDA,TSLA").split(",")]
WATCHLIST_CRYPTO  = [t.strip() for t in os.getenv("WATCHLIST_CRYPTO", "BTC-USD,ETH-USD").split(",")]

# --- Schwellenwert fuer Kursalarm (in %) ---
PRICE_CHANGE_THRESHOLD = float(os.getenv("PRICE_CHANGE_THRESHOLD", "3.0"))

# --- KI-Einstellungen ---
AI_MODEL = "qwen/qwen3.8-27b"
AI_LANGUAGE = os.getenv("AI_LANGUAGE", "Deutsch")

# --- RSS-Feeds (keine API Keys noetig) ---
RSS_FEEDS = {
    "Weisses Haus":      "https://www.whitehouse.gov/feed/",
    "SEC Filings":       "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&dateb=&owner=include&count=10&search_text=&output=atom",
    "Reuters Business":  "https://feeds.reuters.com/reuters/businessNews",
    "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss",
    "CNBC Top News":     "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "MarketWatch":       "https://feeds.marketwatch.com/marketwatch/topstories/",
    "CoinDesk Krypto":   "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "ECB Pressemitteilungen": "https://www.ecb.europa.eu/rss/press.html",
}

# --- Zeitintervalle (in Sekunden) ---
INTERVAL_NEWS_SCAN       = 300   # Alle 5 Minuten: News scannen
INTERVAL_PRICE_CHECK     = 180   # Alle 3 Minuten: Kurse pruefen
INTERVAL_MORNING_BRIEF   = "07:00"  # Jeden Morgen um 7 Uhr
INTERVAL_EVENING_BRIEF   = "20:00"  # Jeden Abend um 20 Uhr

