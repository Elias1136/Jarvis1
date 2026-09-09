import os
import re
import json
import logging
import io
from datetime import datetime, timedelta

import pytz
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests

# Load env first so config picks it up
load_dotenv()

import config as _config_module
from config import (
    DISCORD_BOT_TOKEN, WATCHLIST_STOCKS, WATCHLIST_CRYPTO,
    PRICE_CHANGE_THRESHOLD, INTERVAL_PRICE_CHECK,
    GROQ_API_KEY, AI_MODEL, FINNHUB_API_KEY,
)
from data_fetcher import get_all_prices, get_company_financials, get_ticker_news_finnhub, get_rss_articles
from ai_analyst import analyze_price_move, chat_with_jarvis
from chart_generator import generate_chart, generate_portfolio_chart

# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("JARVIS")

# ============================================================
#  SCHWEIZER ZEITZONE
# ============================================================
SWISS_TZ = pytz.timezone("Europe/Zurich")

# ============================================================
#  BOT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ============================================================
#  PERSISTENTER ALERT-KANAL
# ============================================================
SETTINGS_FILE = "jarvis_settings.json"


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)


settings = load_settings()
ALERT_CHANNEL_ID = settings.get("alert_channel_id", None)
conversation_history = {}
_sent_today = set()        # Verhindert doppelte geplante Nachrichten
_sent_alerts_today = set() # Verhindert doppelte Preisalarme

# ============================================================
#  SEKTOR-ETFs
# ============================================================
SECTOR_ETFS = {
    "Technologie \U0001f4bb": "XLK", "Energie \u26fd": "XLE",
    "Banken \U0001f3e6": "XLF", "Gesundheit \U0001f3e5": "XLV",
    "Industrie \U0001f3ed": "XLI", "Konsum \U0001f6d2": "XLY",
    "Versorger \u26a1": "XLU", "Immobilien \U0001f3e0": "XLRE",
    "Rohstoffe \U0001faa8": "XLB",
}

# ============================================================
#  JARVIS PERSOENLICHKEIT
# ============================================================
SYSTEM_PROMPT = """Du bist Jarvis - der persoenliche KI-Finanzberater deines Masters.

Du bist ein Experte in ALLEM was mit Geld, Maerkten und Weltgeschehen zu tun hat:
- Aktien und ETFs (ALLE Maerkte weltweit, nicht nur die Watchlist!)
- Krypto (Bitcoin, Ethereum, alle Altcoins)
- Rohstoffe (Oel, Gold, Silber, Gas)
- Forex, Geopolitik, Notenbanken, Wirtschaftsdaten
- Unternehmensanalysen jeder beliebigen Firma

WICHTIGE REGELN:
1. Antworte IMMER auf Deutsch, max. 4 kurze Saetze
2. Antworte AUF JEDE FRAGE - auch wenn du keine Live-Daten hast, gib dein Wissen wieder
3. Wenn LIVE-MARKTDATEN im Kontext stehen, nutze diese echten Zahlen
4. Wenn KEINE Live-Daten vorhanden sind, antworte trotzdem mit deinem Wissen und weise kurz darauf hin
5. Sei direkt und gib klare Meinungen: kaufen / halten / verkaufen
6. Gelegentlich Humor erlaubt

Aktuelle Watchlist (automatisch ueberwacht): {watchlist}"""

# ============================================================
#  TICKER NAME MAP
# ============================================================
NAME_MAP = {
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD", "sol": "SOL-USD",
    "cardano": "ADA-USD", "ada": "ADA-USD",
    "ripple": "XRP-USD", "xrp": "XRP-USD",
    "apple": "AAPL", "aapl": "AAPL",
    "tesla": "TSLA", "tsla": "TSLA",
    "nvidia": "NVDA", "nvda": "NVDA",
    "microsoft": "MSFT", "msft": "MSFT",
    "amazon": "AMZN", "amzn": "AMZN",
    "google": "GOOGL", "alphabet": "GOOGL", "googl": "GOOGL",
    "meta": "META", "facebook": "META",
    "netflix": "NFLX", "nflx": "NFLX",
    "spy": "SPY", "s&p": "SPY", "sp500": "SPY",
    "oel": "CL=F", "oil": "CL=F", "erdoel": "CL=F",
    "gold": "GC=F", "silber": "SI=F",
    "eur": "EURUSD=X", "euro": "EURUSD=X",
    "nestle": "NESN.SW", "novartis": "NOVN.SW",
    "roche": "ROG.SW", "ubs": "UBSG.SW",
    "samsung": "005930.KS", "alibaba": "BABA",
    "berkshire": "BRK-B", "jp morgan": "JPM",
    "bank of america": "BAC", "goldman": "GS",
}

# Pfad zur .env Datei
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# ============================================================
#  WATCHLIST MANAGEMENT (Chat-basiert)
# ============================================================

def _reload_config_watchlists():
    """Reloads WATCHLIST_STOCKS and WATCHLIST_CRYPTO from .env into the running process."""
    load_dotenv(override=True)
    new_stocks = [t.strip() for t in os.getenv("WATCHLIST_STOCKS", "AAPL,NVDA,TSLA").split(",") if t.strip()]
    new_crypto = [t.strip() for t in os.getenv("WATCHLIST_CRYPTO", "BTC-USD,ETH-USD").split(",") if t.strip()]
    import config as cfg
    cfg.WATCHLIST_STOCKS.clear()
    cfg.WATCHLIST_STOCKS.extend(new_stocks)
    cfg.WATCHLIST_CRYPTO.clear()
    cfg.WATCHLIST_CRYPTO.extend(new_crypto)
    global WATCHLIST_STOCKS, WATCHLIST_CRYPTO
    WATCHLIST_STOCKS = cfg.WATCHLIST_STOCKS
    WATCHLIST_CRYPTO = cfg.WATCHLIST_CRYPTO


def _update_env_watchlist(key: str, tickers: list):
    """Writes the updated ticker list back to .env file."""
    value = ",".join(tickers)
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}\n")
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    else:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def _detect_watchlist_command(text: str):
    """
    Detects natural language watchlist add/remove commands.
    Returns ('add', ticker), ('remove', ticker), or (None, None).
    """
    add_patterns = [
        r"f[u\u00fc]ge\s+([A-Z0-9.\-]{1,10})\s+hinzu",
        r"add\s+([A-Z0-9.\-]{1,10})\s+(?:zur\s+)?watchlist",
        r"beobachte\s+([A-Z0-9.\-]{1,10})",
        r"watchlist\s+add\s+([A-Z0-9.\-]{1,10})",
        r"zur\s+watchlist\s+hinzuf[u\u00fc]gen[:\s]+([A-Z0-9.\-]{1,10})",
    ]
    for pattern in add_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return ("add", m.group(1).upper())

    remove_patterns = [
        r"entferne\s+([A-Z0-9.\-]{1,10})",
        r"remove\s+([A-Z0-9.\-]{1,10})",
        r"l[o\u00f6]sche\s+([A-Z0-9.\-]{1,10})",
        r"watchlist\s+remove\s+([A-Z0-9.\-]{1,10})",
        r"aus\s+(?:der\s+)?watchlist\s+(?:entfernen?|l[o\u00f6]schen?)[:\s]+([A-Z0-9.\-]{1,10})",
    ]
    for pattern in remove_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return ("remove", m.group(1).upper())

    return (None, None)


# ============================================================
#  EINZELKURS
# ============================================================

def fetch_any_ticker_price(ticker: str) -> dict | None:
    """Holt den Preis fuer JEDEN beliebigen Ticker von Yahoo Finance."""
    try:
        import yfinance as yf
        data = yf.Ticker(ticker)
        hist = data.history(period="2d")
        if hist.empty:
            return None
        price = hist["Close"].iloc[-1]
        chg = ((price - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2]) * 100 if len(hist) >= 2 else 0.0
        return {"ticker": ticker, "price": price, "change_pct": chg}
    except Exception:
        return None


# ============================================================
#  LIVE-KONTEXT FUER KI
# ============================================================

def get_live_context(text: str) -> str:
    text_lower = text.lower()
    found_tickers = []

    for name, ticker in NAME_MAP.items():
        if name in text_lower and ticker not in found_tickers:
            found_tickers.append(ticker)

    ticker_pattern = re.findall(r"\b([A-Z]{1,5}(?:-[A-Z]{2,4})?)\b", text)
    common_words = {
        "I", "A", "AI", "KI", "US", "EU", "CHF", "USD", "EUR", "ETF",
        "IPO", "CEO", "CFO", "GDP", "CPI", "NFP", "FED", "EZB", "SNB",
        "OK", "UND", "DER", "DIE", "DAS", "FUR", "VON", "BEI", "AUF",
    }
    for t in ticker_pattern:
        if t not in common_words and t not in found_tickers:
            found_tickers.append(t)

    for ticker in WATCHLIST_STOCKS + WATCHLIST_CRYPTO:
        base = ticker.replace("-USD", "").replace(".SW", "").replace(".KS", "")
        if base.lower() in text_lower and ticker not in found_tickers:
            found_tickers.append(ticker)

    market_words = [
        "markt", "boerse", "aktien", "krypto", "crypto", "alle", "portfolio",
        "overview", "ueberblick", "wie laufen", "was laeuft",
    ]
    if not found_tickers and any(w in text_lower for w in market_words):
        found_tickers = WATCHLIST_STOCKS + WATCHLIST_CRYPTO

    if not found_tickers:
        return ""

    price_info = []
    try:
        all_prices = get_all_prices()
        watchlist_prices = {p["ticker"]: p for p in all_prices if p}
        for ticker in found_tickers[:6]:
            if ticker in watchlist_prices:
                p = watchlist_prices[ticker]
                sign = "+" if p["change_pct"] > 0 else ""
                price_info.append(f"{ticker}: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}% heute)")
            else:
                p = fetch_any_ticker_price(ticker)
                if p:
                    sign = "+" if p["change_pct"] > 0 else ""
                    price_info.append(f"{ticker}: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}% heute)")
    except Exception:
        pass

    return "\n\n[LIVE-MARKTDATEN]\n" + "\n".join(price_info) if price_info else ""


# ============================================================
#  INSIDER TRADING
# ============================================================

def get_insider_trades(ticker: str) -> list:
    """
    Holt Insider-Transaktionen der letzten 7 Tage via Finnhub.
    Filtert Transaktionen > 100.000 USD.
    """
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    cutoff = (datetime.now(SWISS_TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        trades = []
        for t in r.json().get("data", []):
            tx_date = t.get("transactionDate", "")
            tx_type = t.get("transactionCode", "")
            shares = t.get("share", 0) or 0
            price_per_share = t.get("transactionPrice", 0) or 0
            amount = shares * price_per_share
            if tx_date >= cutoff and amount > 100_000:
                trades.append({
                    "name": t.get("name", "Unbekannt"),
                    "type": "KAUF" if tx_type in ("P", "A") else "VERKAUF",
                    "amount": amount,
                    "shares": shares,
                    "date": tx_date,
                })
        return trades
    except Exception as e:
        logger.warning(f"Insider-Trades Fehler ({ticker}): {e}")
        return []


# ============================================================
#  MARKTDATEN HILFSFUNKTIONEN
# ============================================================

def get_fear_greed_index() -> dict:
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            score = data.get("fear_and_greed", {}).get("score", 50)
            rating = data.get("fear_and_greed", {}).get("rating", "neutral")
            return {"score": round(score), "rating": rating}
    except Exception:
        pass
    return {"score": 50, "rating": "neutral"}


def get_fear_greed_emoji(score: int) -> str:
    if score <= 20: return "\U0001f631 Extreme Angst"
    if score <= 40: return "\U0001f628 Angst"
    if score <= 60: return "\U0001f610 Neutral"
    if score <= 80: return "\U0001f604 Gier"
    return "\U0001f911 Extreme Gier"


def get_upcoming_earnings(days_ahead: int = 2) -> list:
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    target = (datetime.now(SWISS_TZ) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    results = []
    for ticker in WATCHLIST_STOCKS:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/calendar/earnings",
                params={"from": target, "to": target, "symbol": ticker, "token": FINNHUB_API_KEY},
                timeout=10,
            )
            if r.status_code == 200:
                for item in r.json().get("earningsCalendar", []):
                    results.append({
                        "ticker": ticker,
                        "date": item.get("date", target),
                        "estimate_eps": item.get("epsEstimate", "N/A"),
                        "hour": item.get("hour", "N/A"),
                    })
        except Exception:
            pass
    return results


def get_upcoming_dividends() -> list:
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    results = []
    today = datetime.now(SWISS_TZ).strftime("%Y-%m-%d")
    future = (datetime.now(SWISS_TZ) + timedelta(days=30)).strftime("%Y-%m-%d")
    for ticker in WATCHLIST_STOCKS:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/stock/dividend2",
                params={"symbol": ticker, "token": FINNHUB_API_KEY},
                timeout=10,
            )
            if r.status_code == 200:
                for d in r.json().get("data", []):
                    ex_date = d.get("exDate", "")
                    if today <= ex_date <= future:
                        results.append({
                            "ticker": ticker,
                            "ex_date": ex_date,
                            "amount": d.get("amount", "N/A"),
                        })
        except Exception:
            pass
    return results


def get_economic_calendar() -> list:
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    try:
        today = datetime.now(SWISS_TZ).strftime("%Y-%m-%d")
        future = (datetime.now(SWISS_TZ) + timedelta(days=7)).strftime("%Y-%m-%d")
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/economic",
            params={"from": today, "to": future, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            return [e for e in r.json().get("economicCalendar", []) if e.get("impact", 0) == 3][:8]
    except Exception:
        pass
    return []


def get_sector_performance() -> list:
    results = []
    try:
        import yfinance as yf
        for sector_name, etf in SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period="1d")
                if not hist.empty:
                    chg = ((hist["Close"].iloc[-1] - hist["Open"].iloc[-1]) / hist["Open"].iloc[-1]) * 100
                    results.append({"sector": sector_name, "ticker": etf, "change_pct": chg})
            except Exception:
                pass
    except Exception:
        pass
    return sorted(results, key=lambda x: x["change_pct"], reverse=True)


def check_52_week_extremes() -> list:
    extremes = []
    try:
        import yfinance as yf
        for ticker in WATCHLIST_STOCKS:
            try:
                hist = yf.Ticker(ticker).history(period="1y")
                if len(hist) < 10:
                    continue
                current = hist["Close"].iloc[-1]
                high_52 = hist["High"].max()
                low_52 = hist["Low"].min()
                if ((current - high_52) / high_52) * 100 >= -3:
                    extremes.append({"ticker": ticker, "type": "HIGH", "price": current, "extreme": high_52})
                elif ((current - low_52) / low_52) * 100 <= 5:
                    extremes.append({"ticker": ticker, "type": "LOW", "price": current, "extreme": low_52})
            except Exception:
                pass
    except Exception:
        pass
    return extremes


# ============================================================
#  BRIEFINGS
# ============================================================

def generate_morning_briefing() -> str:
    try:
        fg = get_fear_greed_index()
        news = get_rss_articles()[:4]
        econ = get_economic_calendar()
        earnings = get_upcoming_earnings(days_ahead=2)
        date_str = datetime.now(SWISS_TZ).strftime("%A, %d. %B %Y")
        news_text = "\n".join([f"\u2022 {n['title'][:75]}" for n in news])
        econ_text = (
            "\n\U0001f4c5 **Wichtige Termine diese Woche:**\n"
            + "\n".join([f"\u2022 {e.get('event','')} ({e.get('country','')})" for e in econ[:4]])
        ) if econ else ""
        earnings_text = (
            "\n\U0001f4ca **Quartalszahlen in 2 Tagen:**\n"
            + "\n".join([f"\u2022 **{e['ticker']}** am {e['date']}" for e in earnings])
        ) if earnings else ""
        prompt = (
            f"Morgen-Analyse in 3 Saetzen fuer den heutigen Handelstag. "
            f"Fear&Greed: {fg['score']}. Top-News: {news_text[:300]}."
        )
        ai_outlook = chat_with_jarvis(prompt, WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        return (
            f"\u2600\ufe0f **GUTEN MORGEN | {date_str}**\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"\U0001f631 **Fear & Greed:** {fg['score']}/100 \u2013 {get_fear_greed_emoji(fg['score'])}\n"
            f"{econ_text}{earnings_text}\n\n"
            f"\U0001f4f0 **Aktuelle News:**\n{news_text}\n\n"
            f"\U0001f916 **Jarvis Ausblick:**\n{ai_outlook}"
        )
    except Exception as e:
        return f"Morgen-Briefing Fehler: {e}"


def generate_evening_briefing() -> str:
    try:
        prices = get_all_prices()
        fg = get_fear_greed_index()
        news = get_rss_articles()[:4]
        date_str = datetime.now(SWISS_TZ).strftime("%A, %d. %B %Y")
        price_lines = []
        for p in prices:
            if not p:
                continue
            sign = "+" if p["change_pct"] > 0 else ""
            icon = "\U0001f7e2" if p["change_pct"] > 0 else "\U0001f534"
            price_lines.append(f"{icon} **{p['ticker']}**: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}%)")
        prices_text = "\n".join(price_lines)
        news_text = "\n".join([f"\u2022 {n['title'][:75]}" for n in news])
        prompt = f"Abend-Zusammenfassung in 3 Saetzen. Fear&Greed: {fg['score']}. Kurse:\n{prices_text}"
        ai_summary = chat_with_jarvis(prompt, WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        return (
            f"\U0001f319 **ABEND-BRIEFING | {date_str}**\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"\U0001f4ca **Watchlist:**\n{prices_text}\n\n"
            f"\U0001f631 **Fear & Greed:** {fg['score']}/100 \u2013 {get_fear_greed_emoji(fg['score'])}\n\n"
            f"\U0001f916 **Tagesanalyse:**\n{ai_summary}\n\n\U0001f4f0 **Top-News:**\n{news_text}"
        )
    except Exception as e:
        return f"Abend-Briefing Fehler: {e}"


def generate_weekly_review() -> str:
    try:
        import yfinance as yf
        lines, winners, losers = [], [], []
        for ticker in WATCHLIST_STOCKS + WATCHLIST_CRYPTO:
            try:
                hist = yf.Ticker(ticker).history(period="5d")
                if len(hist) >= 2:
                    chg = ((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]) * 100
                    sign = "+" if chg > 0 else ""
                    icon = "🟢" if chg > 0 else "🔴"
                    lines.append(f"{icon} **{ticker}**: {sign}{chg:.2f}%")
                    (winners if chg > 0 else losers).append(f"{ticker}({sign}{chg:.1f}%)")
            except Exception:
                pass
        prompt = (
            "Wochenanalyse in 3 Saetzen. Gewinner: " + ", ".join(winners[:3]) + ". "
            "Verlierer: " + ", ".join(losers[:3]) + "."
        )
        ai_summary = chat_with_jarvis(prompt, WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        week = datetime.now(SWISS_TZ).strftime("KW%V %Y")
        return (
            f"\U0001f4c5 **WOCHEN-REVIEW | {week}**\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"\U0001f4ca **Performance:**\n" + "\n".join(lines)
            + f"\n\n\U0001f916 **Jarvis Wochenanalyse:**\n{ai_summary}"
        )
    except Exception as e:
        return f"Wochen-Review Fehler: {e}"


# ============================================================
#  HINTERGRUND-TASKS
# ============================================================

@tasks.loop(seconds=INTERVAL_PRICE_CHECK)
async def price_check_loop():
    if not ALERT_CHANNEL_ID:
        return
    channel = bot.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return
    for p in get_all_prices():
        if not p:
            continue
        ticker = p.get("ticker")
        price = p.get("price", 0)
        chg = p.get("change_pct", 0)
        alert_key = f"{ticker}_{datetime.now(SWISS_TZ).strftime('%Y%m%d%H')}"
        if abs(chg) >= PRICE_CHANGE_THRESHOLD and alert_key not in _sent_alerts_today:
            _sent_alerts_today.add(alert_key)
            reason = analyze_price_move(ticker, price, chg, get_ticker_news_finnhub(ticker, days=1))
            sign = "+" if chg > 0 else ""
            icon = "\U0001f680" if chg > 0 else "\U0001f4a5"
            await channel.send(
                f"{icon} **KURSALARM: {ticker}**\n"
                f"\U0001f4b0 ${price:,.2f}  |  \U0001f4ca {sign}{chg:.2f}%\n"
                f"\U0001f916 {reason}"
            )


@tasks.loop(minutes=30)
async def scheduled_tasks_loop():
    """Alle zeitgesteuerten Aufgaben - laeuft alle 30 Minuten (Schweizer Zeit)."""
    if not ALERT_CHANNEL_ID:
        return
    channel = bot.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return

    now = datetime.now(SWISS_TZ)
    is_weekday = now.weekday() < 5
    hour = now.hour
    date_key = now.strftime("%Y%m%d")

    # 08:00 Morgen-Briefing
    if is_weekday and hour == 8 and f"morning_{date_key}" not in _sent_today:
        _sent_today.add(f"morning_{date_key}")
        await channel.send(generate_morning_briefing())

        earnings = get_upcoming_earnings(days_ahead=2)
        if earnings:
            msg = "\U0001f4c5 **QUARTALSZAHLEN in 2 TAGEN!**\n" + "\n".join(
                [f"\U0001f3e2 **{e['ticker']}** am {e['date']}" for e in earnings]
            )
            await channel.send(msg)

        divs = get_upcoming_dividends()
        if divs:
            msg = "\U0001f4b0 **DIVIDENDEN-ALARM!**\n" + "\n".join(
                [f"\U0001f4b5 **{d['ticker']}**: Ex-Datum {d['ex_date']} | ${d['amount']}" for d in divs[:5]]
            )
            await channel.send(msg)

        extremes = check_52_week_extremes()
        if extremes:
            msg = "\U0001f4c8 **52-WOCHEN ALARM!**\n"
            for e in extremes:
                icon = "\U0001f3c6" if e["type"] == "HIGH" else "\u26a0\ufe0f"
                label = "HOCH" if e["type"] == "HIGH" else "TIEF"
                msg += f"{icon} **{e['ticker']}** nahe Jahres-{label}! ${e['price']:.2f}\n"
            await channel.send(msg)

        econ = get_economic_calendar()
        if econ:
            msg = "\U0001f30d **WIRTSCHAFTSKALENDER diese Woche:**\n" + "\n".join(
                [f"\U0001f4cc **{e.get('event','')}** | {e.get('country','')}" for e in econ[:6]]
            )
            await channel.send(msg)

        # Insider Trading
        insider_msgs = []
        for ticker in WATCHLIST_STOCKS:
            trades = get_insider_trades(ticker)
            for t in trades:
                amt_fmt = f"${t['amount']:,.0f}"
                icon = "\U0001f7e2" if t["type"] == "KAUF" else "\U0001f534"
                insider_msgs.append(
                    f"{icon} **{ticker}** - {t['name']} hat **{t['type']}** "
                    f"({t['shares']:,} Aktien / {amt_fmt}) am {t['date']}"
                )
        if insider_msgs:
            await channel.send(
                "\U0001f575\ufe0f **INSIDER-TRADING ALERT (letzte 7 Tage):**\n"
                + "\n".join(insider_msgs[:10])
            )

    # 09:00 Fear & Greed
    if is_weekday and hour == 9 and f"fg_{date_key}" not in _sent_today:
        _sent_today.add(f"fg_{date_key}")
        fg = get_fear_greed_index()
        bar = "\u2588" * int(fg["score"] / 5) + "\u2591" * (20 - int(fg["score"] / 5))
        await channel.send(
            f"\U0001f631 **FEAR & GREED INDEX**\n`[{bar}]` **{fg['score']}/100**\n"
            f"Stimmung: **{get_fear_greed_emoji(fg['score'])}**\n"
            f"*Unter 30 = Kaufgelegenheit | Ueber 70 = Vorsicht*"
        )

    # 21:00 Abend-Briefing
    if is_weekday and hour == 21 and f"evening_{date_key}" not in _sent_today:
        _sent_today.add(f"evening_{date_key}")
        await channel.send(generate_evening_briefing())

    # Freitag 19:00 Wochen-Review
    if now.weekday() == 4 and hour == 19 and f"weekly_{date_key}" not in _sent_today:
        _sent_today.add(f"weekly_{date_key}")
        await channel.send(generate_weekly_review())

    # Mitternacht: alte Keys entfernen
    if hour == 0:
        yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
        keys_to_remove = [k for k in list(_sent_today) if yesterday in k]
        for k in keys_to_remove:
            _sent_today.discard(k)


@price_check_loop.before_loop
@scheduled_tasks_loop.before_loop
async def before_loops():
    await bot.wait_until_ready()


# ============================================================
#  BOT EVENTS
# ============================================================

@bot.event
async def on_ready():
    global ALERT_CHANNEL_ID
    logger.info(f"Jarvis ist online als {bot.user}")
    s = load_settings()
    if s.get("alert_channel_id"):
        ALERT_CHANNEL_ID = s["alert_channel_id"]
        logger.info(f"Alert-Kanal wiederhergestellt: {ALERT_CHANNEL_ID}")
    price_check_loop.start()
    scheduled_tasks_loop.start()
    print(f"\n=== Jarvis online: {bot.user} | Alert-Kanal: {ALERT_CHANNEL_ID} ===")
    print(f"Schweizer Zeit: {datetime.now(SWISS_TZ).strftime('%H:%M %Z')}")
    print("Automatisch aktiv: 8h Morgen | 9h Fear&Greed | 21h Abend | Fr19h Woche")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # Watchlist-Management via Chat
    action, ticker = _detect_watchlist_command(message.content)
    if action and ticker:
        if action == "add":
            stocks = list(WATCHLIST_STOCKS)
            crypto = list(WATCHLIST_CRYPTO)
            crypto_bases = {
                "BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "SHIB", "MATIC", "DOT", "AVAX",
                "LTC", "LINK", "UNI", "ATOM", "ALGO",
            }
            is_crypto = ticker.endswith("-USD") or ticker in crypto_bases
            if is_crypto and not ticker.endswith("-USD") and len(ticker) <= 5:
                ticker = f"{ticker}-USD"
            target_list = crypto if is_crypto else stocks
            target_key = "WATCHLIST_CRYPTO" if is_crypto else "WATCHLIST_STOCKS"
            if ticker not in target_list:
                target_list.append(ticker)
                _update_env_watchlist(target_key, target_list)
                _reload_config_watchlists()
                icon = "\U0001fa99" if is_crypto else "\U0001f4c8"
                await message.channel.send(
                    f"\u2705 **{ticker}** wurde zur Watchlist hinzugefuegt! {icon}\n"
                    f"Aktuelle Watchlist: {', '.join(WATCHLIST_STOCKS)} | {', '.join(WATCHLIST_CRYPTO)}"
                )
            else:
                await message.channel.send(f"\u2139\ufe0f **{ticker}** ist bereits auf der Watchlist!")
            return

        elif action == "remove":
            removed = False
            for lst_copy, key in [
                (list(WATCHLIST_STOCKS), "WATCHLIST_STOCKS"),
                (list(WATCHLIST_CRYPTO), "WATCHLIST_CRYPTO"),
            ]:
                if ticker in lst_copy:
                    lst_copy.remove(ticker)
                    _update_env_watchlist(key, lst_copy)
                    removed = True
            if removed:
                _reload_config_watchlists()
                await message.channel.send(
                    f"\U0001f5d1\ufe0f **{ticker}** wurde von der Watchlist entfernt!\n"
                    f"Aktuelle Watchlist: {', '.join(WATCHLIST_STOCKS)} | {', '.join(WATCHLIST_CRYPTO)}"
                )
            else:
                await message.channel.send(f"\u274c **{ticker}** war nicht auf der Watchlist.")
            return

    # KI-Chat
    user_id = str(message.author.id)
    user_name = message.author.display_name
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    live_context = get_live_context(message.content)
    watchlist_str = ", ".join(WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
    system = SYSTEM_PROMPT.format(watchlist=watchlist_str)
    if live_context:
        system += live_context

    conversation_history[user_id].append({"role": "user", "content": f"{user_name}: {message.content}"})
    if len(conversation_history[user_id]) > 12:
        conversation_history[user_id] = conversation_history[user_id][-12:]

    async with message.channel.typing():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
            resp = client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "system", "content": system}] + conversation_history[user_id],
                temperature=0.75,
                max_tokens=450,
            )
            response = resp.choices[0].message.content.strip()
            conversation_history[user_id].append({"role": "assistant", "content": response})
        except Exception as e:
            response = f"Kurze Verbindungsstoerung - versuchs nochmal! \U0001f527 ({e})"

    await message.channel.send(response)


# ============================================================
#  BEFEHLE
# ============================================================

@bot.command(name="start_alerts")
async def start_alerts(ctx):
    global ALERT_CHANNEL_ID
    ALERT_CHANNEL_ID = ctx.channel.id
    save_settings({"alert_channel_id": ctx.channel.id})
    await ctx.send(
        "\u2705 **Jarvis Zentrale dauerhaft aktiviert!**\n"
        "*(Auch nach Neustart merke ich mir diesen Kanal!)*\n\n"
        "\u2600\ufe0f `8:00` Morgen-Briefing + Quartalszahlen + Dividenden + 52W-Alarme + Insider-Trading\n"
        "\U0001f631 `9:00` Fear & Greed Index\n"
        "\U0001f319 `21:00` Abend-Briefing\n"
        "\U0001f4c5 `Fr 19:00` Wochen-Review\n"
        "\U0001f6a8 Kursalarme bei starken Bewegungen\n\n"
        "Schreib mir einfach - ich antworte auf JEDE Frage!\n"
        f"\U0001f550 Schweizer Zeit aktiv: {datetime.now(SWISS_TZ).strftime('%H:%M %Z')}"
    )


@bot.command(name="morgen")
async def morning_cmd(ctx):
    async with ctx.typing():
        await ctx.send(generate_morning_briefing())


@bot.command(name="briefing")
async def evening_cmd(ctx):
    async with ctx.typing():
        await ctx.send(generate_evening_briefing())


@bot.command(name="woche")
async def weekly_cmd(ctx):
    async with ctx.typing():
        await ctx.send(generate_weekly_review())


@bot.command(name="sektoren")
async def sectors_cmd(ctx):
    async with ctx.typing():
        sectors = get_sector_performance()
        if not sectors:
            await ctx.send("Keine Sektordaten verfuegbar.")
            return
        lines = []
        for s in sectors:
            icon = "🟢" if s["change_pct"] > 0 else "🔴"
            sign = "+" if s["change_pct"] > 0 else ""
            lines.append(f"{icon} **{s['sector']}**: {sign}{s['change_pct']:.2f}%")
        await ctx.send("\U0001f3ed **SEKTOR-ANALYSE:**\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n" + "\n".join(lines))


@bot.command(name="angst")
async def fear_cmd(ctx):
    fg = get_fear_greed_index()
    bar = "\u2588" * int(fg["score"] / 5) + "\u2591" * (20 - int(fg["score"] / 5))
    await ctx.send(
        f"\U0001f631 **FEAR & GREED**\n`[{bar}]` **{fg['score']}/100**\n"
        f"{get_fear_greed_emoji(fg['score'])}"
    )


@bot.command(name="dividenden")
async def divs_cmd(ctx):
    async with ctx.typing():
        divs = get_upcoming_dividends()
        if not divs:
            await ctx.send("Keine Dividenden in den naechsten 30 Tagen.")
            return
        await ctx.send(
            "\U0001f4b0 **Dividenden:**\n"
            + "\n".join([f"\U0001f4b5 **{d['ticker']}** - Ex: {d['ex_date']} | ${d['amount']}" for d in divs])
        )


@bot.command(name="earnings")
async def earnings_cmd(ctx):
    async with ctx.typing():
        all_e = []
        for d in range(0, 8):
            all_e += get_upcoming_earnings(days_ahead=d)
        if not all_e:
            await ctx.send("Keine Quartalszahlen in den naechsten 7 Tagen.")
            return
        await ctx.send(
            "\U0001f4c5 **Quartalszahlen:**\n"
            + "\n".join([f"\U0001f3e2 **{e['ticker']}** - {e['date']}" for e in all_e])
        )


@bot.command(name="wirtschaft")
async def econ_cmd(ctx):
    async with ctx.typing():
        events = get_economic_calendar()
        if not events:
            await ctx.send("Keine wichtigen Termine diese Woche.")
            return
        await ctx.send(
            "\U0001f30d **WIRTSCHAFTSKALENDER:**\n"
            + "\n".join([f"\U0001f4cc **{e.get('event','')}** | {e.get('country','')}" for e in events])
        )


@bot.command(name="preise")
async def prices_cmd(ctx):
    async with ctx.typing():
        prices = get_all_prices()
        lines = []
        for p in prices:
            if not p:
                continue
            sign = "+" if p["change_pct"] > 0 else ""
            icon = "\U0001f7e2" if p["change_pct"] > 0 else "\U0001f534"
            lines.append(f"{icon} **{p['ticker']}**: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}%)")
        await ctx.send("\U0001f4b9 **Live-Kurse:**\n" + "\n".join(lines) if lines else "Keine Kurse.")


@bot.command(name="kurs")
async def single_price_cmd(ctx, ticker: str):
    """Holt den Kurs fuer JEDEN beliebigen Ticker."""
    ticker = ticker.upper()
    async with ctx.typing():
        p = fetch_any_ticker_price(ticker)
        if p:
            sign = "+" if p["change_pct"] > 0 else ""
            icon = "\U0001f7e2" if p["change_pct"] > 0 else "\U0001f534"
            await ctx.send(f"{icon} **{ticker}**: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}% heute)")
        else:
            await ctx.send(f"\u274c Konnte keinen Kurs fuer `{ticker}` finden. Stimmt das Kuerzel?")


@bot.command(name="analyze")
async def analyze_cmd(ctx, ticker: str):
    ticker = ticker.upper()
    async with ctx.typing():
        data = get_company_financials(ticker)
        news = get_ticker_news_finnhub(ticker, days=2)
        news_str = " | ".join([n["title"] for n in news[:3]]) if news else "keine News"
        pe = data.get("pe_ratio", "unbekannt") if data else "unbekannt"
        p = fetch_any_ticker_price(ticker)
        if p:
            chg_sign = "+" if p["change_pct"] > 0 else ""
            price_info = f"Aktueller Kurs: ${p['price']:,.2f} ({chg_sign}{p['change_pct']:.2f}%)"
        else:
            price_info = ""
        response = chat_with_jarvis(
            f"Analysiere {ticker} als Finanzberater. {price_info} KGV: {pe}. News: {news_str}. "
            f"Kaufen, halten oder verkaufen?",
            WATCHLIST_STOCKS + WATCHLIST_CRYPTO,
        )
        await ctx.send(f"\U0001f4ca **{ticker} - Analyse:**\n{response}")


@bot.command(name="insider")
async def insider_cmd(ctx, ticker: str):
    """Zeigt Insider-Transaktionen der letzten 7 Tage."""
    ticker = ticker.upper()
    async with ctx.typing():
        trades = get_insider_trades(ticker)
        if not trades:
            await ctx.send(
                f"\U0001f575\ufe0f Keine signifikanten Insider-Transaktionen fuer **{ticker}** in den letzten 7 Tagen."
            )
            return
        lines = []
        for t in trades[:8]:
            amt_fmt = f"${t['amount']:,.0f}"
            icon = "\U0001f7e2" if t["type"] == "KAUF" else "\U0001f534"
            lines.append(
                f"{icon} **{t['name']}** - {t['type']} | {t['shares']:,} Aktien | {amt_fmt} | {t['date']}"
            )
        await ctx.send(f"\U0001f575\ufe0f **INSIDER-TRADES {ticker} (letzte 7 Tage):**\n" + "\n".join(lines))


@bot.command(name="chart")
async def chart_cmd(ctx, ticker: str, period: str = "3mo"):
    """
    Erstellt einen Candlestick-Chart mit RSI und KI-Signalen.
    Verwendung: !chart TSLA [1mo|3mo|6mo|1y|2y]
    """
    ticker = ticker.upper()
    valid_periods = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
    if period not in valid_periods:
        await ctx.send(f"\u274c Ungueltige Period. Erlaubt: {', '.join(sorted(valid_periods))}")
        return
    async with ctx.typing():
        buf = generate_chart(ticker, period)
        if buf is None:
            await ctx.send(f"\u274c Konnte keinen Chart fuer `{ticker}` erstellen. Stimmt das Kuerzel?")
            return
        await ctx.send(
            f"\U0001f4ca **{ticker} - Chart ({period})**",
            file=discord.File(buf, filename=f"{ticker}_chart.png"),
        )


@bot.command(name="portfolio")
async def portfolio_cmd(ctx, period: str = "1mo"):
    """
    Erstellt einen Vergleichs-Performance-Chart aller Watchlist-Aktien.
    Verwendung: !portfolio [1mo|3mo|6mo|1y]
    """
    valid_periods = {"1mo", "3mo", "6mo", "1y"}
    if period not in valid_periods:
        await ctx.send(f"\u274c Ungueltige Period. Erlaubt: {', '.join(sorted(valid_periods))}")
        return
    async with ctx.typing():
        tickers = WATCHLIST_STOCKS[:10]
        buf = generate_portfolio_chart(tickers, period)
        if buf is None:
            await ctx.send("\u274c Konnte keinen Portfolio-Chart erstellen.")
            return
        await ctx.send(
            f"\U0001f4c8 **Portfolio Performance ({period})**\nVergleich: {', '.join(tickers)}",
            file=discord.File(buf, filename=f"portfolio_{period}.png"),
        )


@bot.command(name="watchlist")
async def watchlist_cmd(ctx):
    """Zeigt die aktuelle Watchlist."""
    await ctx.send(
        f"\U0001f4cb **Watchlist:**\n"
        f"\U0001f4c8 **Aktien:** {', '.join(WATCHLIST_STOCKS)}\n"
        f"\U0001fa99 **Krypto:** {', '.join(WATCHLIST_CRYPTO)}\n\n"
        f"_Tipp: Schreib 'fuege AAPL hinzu' oder 'entferne TSLA' um die Liste anzupassen!_"
    )


@bot.command(name="help")
async def help_cmd(ctx):
    await ctx.send(
        "**Jarvis - Dein Finanzberater** \U0001f916\n\n"
        "**Schreib mir einfach auf Deutsch** - ich antworte auf alles!\n"
        "Aktien, Krypto, Gold, Oel, Geopolitik, Notenbanken, Wirtschaft...\n"
        "*(Keine Ticker-Liste noetig - ich kenne alle Aktien weltweit!)*\n\n"
        "**Watchlist per Chat:**\n"
        "`fuege AAPL hinzu` / `add AAPL zur watchlist` / `beobachte TSLA`\n"
        "`entferne TSLA` / `remove NVDA` / `loesche BTC`\n\n"
        "**Automatisch (nach `!start_alerts`):**\n"
        "\u2600\ufe0f`8h` Morgen-Briefing + Insider-Trading | \U0001f631`9h` Fear&Greed\n"
        "\U0001f319`21h` Abend-Briefing | \U0001f4c5`Fr19h` Wochen-Review\n\n"
        "**Befehle:**\n"
        "`!kurs TSLA` - Kurs einer beliebigen Aktie\n"
        "`!preise` - Alle Watchlist-Kurse\n"
        "`!analyze NVDA` - KI-Analyse\n"
        "`!chart TSLA [3mo]` - Candlestick-Chart mit RSI\n"
        "`!portfolio [1mo]` - Portfolio Performance Chart\n"
        "`!insider AAPL` - Insider-Transaktionen\n"
        "`!morgen` `!briefing` `!woche` - Sofort-Briefings\n"
        "`!angst` `!sektoren` `!dividenden`\n"
        "`!earnings` `!wirtschaft` `!watchlist`\n"
        "`!start_alerts` - Alarm-Kanal aktivieren\n"
    )


# ============================================================
#  ENTRY POINT
# ============================================================

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN.startswith("DEIN"):
        print("FEHLER: Discord Bot Token fehlt in .env!")
    else:
        bot.run(DISCORD_BOT_TOKEN)
