import os
import json
import logging
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests

load_dotenv()

from config import (
    DISCORD_BOT_TOKEN, WATCHLIST_STOCKS, WATCHLIST_CRYPTO,
    PRICE_CHANGE_THRESHOLD, INTERVAL_PRICE_CHECK,
    GROQ_API_KEY, AI_MODEL, FINNHUB_API_KEY
)
from data_fetcher import get_all_prices, get_company_financials, get_ticker_news_finnhub, get_rss_articles
from ai_analyst import analyze_price_move, chat_with_jarvis

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('JARVIS')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ============================================================
#  PERSISTENTER ALERT-KANAL (wird gespeichert, nie vergessen)
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

SECTOR_ETFS = {
    "Technologie 💻": "XLK", "Energie ⛽": "XLE",
    "Banken 🏦": "XLF", "Gesundheit 🏥": "XLV",
    "Industrie 🏭": "XLI", "Konsum 🛒": "XLY",
    "Versorger ⚡": "XLU", "Immobilien 🏠": "XLRE",
    "Rohstoffe 🪨": "XLB",
}

# ============================================================
#  JARVIS PERSOENLICHKEIT – KOMPLETT OFFEN
# ============================================================
SYSTEM_PROMPT = """Du bist Jarvis – der persoenliche KI-Finanzberater und Weltmarkt-Analyst deines Masters.

Du bist ein Experte in ALLEM was mit Geld, Maerkten und Weltgeschehen zu tun hat:
✅ Aktien und ETFs (alle Maerkte weltweit, nicht nur die Watchlist!)
✅ Krypto (Bitcoin, Ethereum, Altcoins, DeFi, NFTs)
✅ Rohstoffe (Oel, Gold, Silber, Kupfer, Gas)
✅ Forex (EUR/USD, CHF, GBP, Yen usw.)
✅ Immobilien und REITs
✅ Derivate (Optionen, Futures – einfach erklaert)
✅ Geopolitik und deren Auswirkungen auf Maerkte
✅ Notenbanken (Fed, EZB, SNB) und Zinsentscheide
✅ Wirtschaftsdaten (Inflation, BIP, Arbeitslosigkeit)
✅ Unternehmensanalysen (jede Firma, die dein Master fragt)

Deine Persoenlichkeit:
- Redest wie ein smarter Freund, der zufaellig Milliardaer-Berater ist
- Direkt, ehrlich, kein Blabla – max. 4 kurze Saetze
- Klare Meinung: kaufen, halten oder verkaufen – mit Begruendung
- Warnst bei Risiken, ohne den Master zu bevormunden
- Antworten IMMER auf Deutsch
- Gelegentlich Humor oder Sarkasmus erlaubt

Aktuelle Watchlist (automatisch ueberwacht): {watchlist}

WICHTIG: Wenn LIVE-MARKTDATEN im Kontext stehen, nutze diese echten Zahlen!"""

NAME_MAP = {
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD", "sol": "SOL-USD",
    "apple": "AAPL", "aapl": "AAPL",
    "tesla": "TSLA", "tsla": "TSLA",
    "nvidia": "NVDA", "nvda": "NVDA",
    "microsoft": "MSFT", "msft": "MSFT",
    "amazon": "AMZN", "amzn": "AMZN",
    "google": "GOOGL", "googl": "GOOGL",
    "meta": "META", "facebook": "META",
    "spy": "SPY", "s&p": "SPY",
    "oel": "CL=F", "oil": "CL=F",
    "gold": "GC=F", "silber": "SI=F",
    "eur": "EURUSD=X", "dollar": "DX-Y.NYB",
    "nestle": "NESN.SW", "novartis": "NOVN.SW",
    "roche": "ROG.SW", "ubs": "UBSG.SW",
}

PRICE_KEYWORDS = [
    "preis", "kurs", "steht", "kostet", "wert", "price",
    "wie viel", "wieviel", "aktuell", "jetzt", "heute",
    "kaufen", "verkaufen", "einsteigen", "aussteigen",
    "analyse", "analysier", "schau", "check", "wo steht",
]


# ============================================================
#  HILFSFUNKTIONEN
# ============================================================

def get_live_context(text: str) -> str:
    text_lower = text.lower()
    has_price_question = any(kw in text_lower for kw in PRICE_KEYWORDS)
    found_tickers = []
    for name, ticker in NAME_MAP.items():
        if name in text_lower and ticker not in found_tickers:
            found_tickers.append(ticker)
    for ticker in WATCHLIST_STOCKS + WATCHLIST_CRYPTO:
        base = ticker.replace("-USD", "")
        if base.lower() in text_lower and ticker not in found_tickers:
            found_tickers.append(ticker)
    if not found_tickers and has_price_question:
        if any(w in text_lower for w in ["markt", "boerse", "aktien", "krypto", "alle", "portfolio"]):
            found_tickers = WATCHLIST_STOCKS + WATCHLIST_CRYPTO
    if not found_tickers:
        return ""
    try:
        all_prices = get_all_prices()
        price_info = []
        for p in all_prices:
            if p and p.get("ticker") in found_tickers:
                sign = "+" if p["change_pct"] > 0 else ""
                price_info.append(f"{p['ticker']}: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}% heute)")
        if price_info:
            return "\n\n[LIVE-MARKTDATEN]\n" + "\n".join(price_info)
    except Exception:
        pass
    return ""


def get_fear_greed_index() -> dict:
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
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
    if score <= 20: return "😱 Extreme Angst"
    if score <= 40: return "😨 Angst"
    if score <= 60: return "😐 Neutral"
    if score <= 80: return "😄 Gier"
    return "🤑 Extreme Gier"


def get_upcoming_earnings(days_ahead: int = 2) -> list:
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    target = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    results = []
    for ticker in WATCHLIST_STOCKS:
        try:
            r = requests.get("https://finnhub.io/api/v1/calendar/earnings",
                params={"from": target, "to": target, "symbol": ticker, "token": FINNHUB_API_KEY}, timeout=10)
            if r.status_code == 200:
                for item in r.json().get("earningsCalendar", []):
                    results.append({"ticker": ticker, "date": item.get("date", target),
                                    "estimate_eps": item.get("epsEstimate", "N/A"), "hour": item.get("hour", "N/A")})
        except Exception:
            pass
    return results


def get_upcoming_dividends() -> list:
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    results = []
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    for ticker in WATCHLIST_STOCKS:
        try:
            r = requests.get("https://finnhub.io/api/v1/stock/dividend2",
                params={"symbol": ticker, "token": FINNHUB_API_KEY}, timeout=10)
            if r.status_code == 200:
                for d in r.json().get("data", []):
                    ex_date = d.get("exDate", "")
                    if today <= ex_date <= future:
                        results.append({"ticker": ticker, "ex_date": ex_date,
                                        "amount": d.get("amount", "N/A"), "pay_date": d.get("payDate", "N/A")})
        except Exception:
            pass
    return results


def get_economic_calendar() -> list:
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        r = requests.get("https://finnhub.io/api/v1/calendar/economic",
            params={"from": today, "to": future, "token": FINNHUB_API_KEY}, timeout=10)
        if r.status_code == 200:
            events = r.json().get("economicCalendar", [])
            return [e for e in events if e.get("impact", 0) == 3][:8]
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
                    chg = ((hist['Close'].iloc[-1] - hist['Open'].iloc[-1]) / hist['Open'].iloc[-1]) * 100
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
                current = hist['Close'].iloc[-1]
                high_52 = hist['High'].max()
                low_52 = hist['Low'].min()
                if ((current - high_52) / high_52) * 100 >= -3:
                    extremes.append({"ticker": ticker, "type": "HIGH", "price": current, "extreme": high_52})
                elif ((current - low_52) / low_52) * 100 <= 5:
                    extremes.append({"ticker": ticker, "type": "LOW", "price": current, "extreme": low_52})
            except Exception:
                pass
    except Exception:
        pass
    return extremes


def generate_morning_briefing() -> str:
    try:
        fg = get_fear_greed_index()
        news = get_rss_articles()[:4]
        econ = get_economic_calendar()
        earnings = get_upcoming_earnings(days_ahead=2)
        date_str = datetime.now().strftime("%A, %d. %B %Y")
        news_text = "\n".join([f"• {n['title'][:75]}" for n in news])
        econ_text = ("\n📅 **Wichtige Termine diese Woche:**\n" +
                     "\n".join([f"• {e.get('event', '')} ({e.get('country', '')})" for e in econ[:4]])) if econ else ""
        earnings_text = ("\n📊 **Quartalszahlen in 2 Tagen:**\n" +
                         "\n".join([f"• **{e['ticker']}** am {e['date']}" for e in earnings])) if earnings else ""
        prompt = (f"Morgen-Analyse in 3 Saetzen. Fear&Greed: {fg['score']}. "
                  f"Top-News: {news_text[:300]}. Worauf achten heute?")
        ai_outlook = chat_with_jarvis(prompt, WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        return (f"☀️ **GUTEN MORGEN | {date_str}**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"😱 **Fear & Greed:** {fg['score']}/100 – {get_fear_greed_emoji(fg['score'])}\n"
                f"{econ_text}{earnings_text}\n\n"
                f"📰 **Aktuelle News:**\n{news_text}\n\n"
                f"🤖 **Jarvis Ausblick:**\n{ai_outlook}")
    except Exception as e:
        return f"Morgen-Briefing Fehler: {e}"


def generate_evening_briefing() -> str:
    try:
        prices = get_all_prices()
        fg = get_fear_greed_index()
        news = get_rss_articles()[:4]
        date_str = datetime.now().strftime("%A, %d. %B %Y")
        price_lines = []
        for p in prices:
            if not p:
                continue
            sign = "+" if p["change_pct"] > 0 else ""
            icon = "🟢" if p["change_pct"] > 0 else "🔴"
            price_lines.append(f"{icon} **{p['ticker']}**: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}%)")
        prices_text = "\n".join(price_lines)
        news_text = "\n".join([f"• {n['title'][:75]}" for n in news])
        prompt = f"Abend-Zusammenfassung in 3 Saetzen. Fear&Greed: {fg['score']}. Kurse:\n{prices_text}"
        ai_summary = chat_with_jarvis(prompt, WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        return (f"🌙 **ABEND-BRIEFING | {date_str}**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 **Watchlist:**\n{prices_text}\n\n"
                f"😱 **Fear & Greed:** {fg['score']}/100 – {get_fear_greed_emoji(fg['score'])}\n\n"
                f"🤖 **Tagesanalyse:**\n{ai_summary}\n\n"
                f"📰 **Top-News:**\n{news_text}")
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
                    chg = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                    sign = "+" if chg > 0 else ""
                    icon = "🟢" if chg > 0 else "🔴"
                    lines.append(f"{icon} **{ticker}**: {sign}{chg:.2f}%")
                    (winners if chg > 0 else losers).append(f"{ticker}({sign}{chg:.1f}%)")
            except Exception:
                pass
        prompt = (f"Wochenanalyse in 3 Saetzen. Gewinner: {', '.join(winners[:3])}. "
                  f"Verlierer: {', '.join(losers[:3])}. Was war das Thema der Woche?")
        ai_summary = chat_with_jarvis(prompt, WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        week = datetime.now().strftime("KW%V %Y")
        return (f"📅 **WOCHEN-REVIEW | {week}**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 **Performance:**\n" + "\n".join(lines) +
                f"\n\n🤖 **Jarvis Wochenanalyse:**\n{ai_summary}")
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
        ticker, price, chg = p.get("ticker"), p.get("price", 0), p.get("change_pct", 0)
        if abs(chg) >= PRICE_CHANGE_THRESHOLD:
            reason = analyze_price_move(ticker, price, chg, get_ticker_news_finnhub(ticker, days=1))
            sign = "+" if chg > 0 else ""
            icon = "🚀" if chg > 0 else "💥"
            await channel.send(f"{icon} **KURSALARM: {ticker}**\n💰 ${price:,.2f}  |  📊 {sign}{chg:.2f}%\n🤖 {reason}")


@tasks.loop(minutes=60)
async def scheduled_tasks_loop():
    """Alle zeitgesteuerten Aufgaben in einem Loop"""
    if not ALERT_CHANNEL_ID:
        return
    channel = bot.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return
    now = datetime.now()
    is_weekday = now.weekday() < 5

    # 8:00 Uhr – Morgen-Briefing + alle Daily Checks
    if is_weekday and now.hour == 8:
        await channel.send(generate_morning_briefing())
        # Quartalszahlen
        earnings = get_upcoming_earnings(days_ahead=2)
        if earnings:
            msg = "📅 **QUARTALSZAHLEN in 2 TAGEN!**\n" + "\n".join(
                [f"🏢 **{e['ticker']}** am {e['date']}" for e in earnings])
            await channel.send(msg)
        # Dividenden
        divs = get_upcoming_dividends()
        if divs:
            msg = "💰 **DIVIDENDEN-ALARM!**\n" + "\n".join(
                [f"💵 **{d['ticker']}**: Ex-Datum {d['ex_date']} | ${d['amount']}" for d in divs[:5]])
            await channel.send(msg)
        # 52-Wochen-Extreme
        extremes = check_52_week_extremes()
        if extremes:
            msg = "📈 **52-WOCHEN ALARM!**\n"
            for e in extremes:
                icon = "🏆" if e["type"] == "HIGH" else "⚠️"
                label = "HOCH" if e["type"] == "HIGH" else "TIEF"
                msg += f"{icon} **{e['ticker']}** nahe Jahres-{label}! ${e['price']:.2f}\n"
            await channel.send(msg)
        # Wirtschaftskalender
        econ = get_economic_calendar()
        if econ:
            msg = "🌍 **WIRTSCHAFTSKALENDER diese Woche:**\n" + "\n".join(
                [f"📌 **{e.get('event', '')}** | {e.get('country', '')}" for e in econ[:6]])
            await channel.send(msg)

    # 9:00 Uhr – Fear & Greed Index
    if is_weekday and now.hour == 9:
        fg = get_fear_greed_index()
        bar_filled = int(fg["score"] / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        await channel.send(
            f"😱 **FEAR & GREED INDEX**\n`[{bar}]` **{fg['score']}/100**\n"
            f"Stimmung: **{get_fear_greed_emoji(fg['score'])}**\n"
            f"*Unter 30 = Kaufgelegenheit | Ueber 70 = Vorsicht*")

    # 21:00 Uhr – Abend-Briefing
    if is_weekday and now.hour == 21:
        await channel.send(generate_evening_briefing())

    # Freitag 19:00 – Wochen-Review
    if now.weekday() == 4 and now.hour == 19:
        await channel.send(generate_weekly_review())


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
    logger.info(f'Jarvis ist online als {bot.user}')
    price_check_loop.start()
    scheduled_tasks_loop.start()
    # Gespeicherten Kanal laden
    s = load_settings()
    if s.get("alert_channel_id"):
        ALERT_CHANNEL_ID = s["alert_channel_id"]
        logger.info(f"Alert-Kanal wiederhergestellt: {ALERT_CHANNEL_ID}")
    print(f"\n=== Jarvis online: {bot.user} | Alert-Kanal: {ALERT_CHANNEL_ID} ===")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith('!'):
        await bot.process_commands(message)
        return

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
                temperature=0.75, max_tokens=450
            )
            response = resp.choices[0].message.content.strip()
            conversation_history[user_id].append({"role": "assistant", "content": response})
        except Exception as e:
            response = f"Kurze Verbindungsstoerung – versuchs nochmal! 🔧 ({e})"

    await message.channel.send(response)


# ============================================================
#  BEFEHLE
# ============================================================

@bot.command(name='start_alerts')
async def start_alerts(ctx):
    global ALERT_CHANNEL_ID
    ALERT_CHANNEL_ID = ctx.channel.id
    save_settings({"alert_channel_id": ctx.channel.id})
    await ctx.send(
        "✅ **Jarvis Zentrale dauerhaft aktiviert!**\n"
        "*(Auch nach einem Neustart merke ich mir diesen Kanal!)*\n\n"
        "☀️ `8:00` Morgen-Briefing + Quartalszahlen + Dividenden\n"
        "😱 `9:00` Fear & Greed Index\n"
        "🌙 `21:00` Abend-Briefing\n"
        "📅 `Fr 19:00` Wochen-Review\n"
        "🚨 Kursalarme bei starken Bewegungen"
    )

@bot.command(name='morgen')
async def morning_cmd(ctx):
    async with ctx.typing():
        await ctx.send(generate_morning_briefing())

@bot.command(name='briefing')
async def evening_cmd(ctx):
    async with ctx.typing():
        await ctx.send(generate_evening_briefing())

@bot.command(name='woche')
async def weekly_cmd(ctx):
    async with ctx.typing():
        await ctx.send(generate_weekly_review())

@bot.command(name='sektoren')
async def sectors_cmd(ctx):
    async with ctx.typing():
        sectors = get_sector_performance()
        if not sectors:
            await ctx.send("Keine Sektordaten verfuegbar.")
            return
        lines = []
        for s in sectors:
            sign = "+" if s["change_pct"] > 0 else ""
            icon = "🟢" if s["change_pct"] > 0 else "🔴"
            lines.append(f"{icon} **{s['sector']}**: {sign}{s['change_pct']:.2f}%")
        await ctx.send("🏭 **SEKTOR-ANALYSE:**\n━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines))

@bot.command(name='angst')
async def fear_cmd(ctx):
    fg = get_fear_greed_index()
    bar = "█" * int(fg["score"] / 5) + "░" * (20 - int(fg["score"] / 5))
    await ctx.send(f"😱 **FEAR & GREED**\n`[{bar}]` **{fg['score']}/100**\n{get_fear_greed_emoji(fg['score'])}")

@bot.command(name='dividenden')
async def divs_cmd(ctx):
    async with ctx.typing():
        divs = get_upcoming_dividends()
        if not divs:
            await ctx.send("Keine Dividenden in den naechsten 30 Tagen.")
            return
        msg = "💰 **Kommende Dividenden:**\n" + "\n".join(
            [f"💵 **{d['ticker']}** – Ex: {d['ex_date']} | ${d['amount']}" for d in divs])
        await ctx.send(msg)

@bot.command(name='earnings')
async def earnings_cmd(ctx):
    async with ctx.typing():
        all_e = []
        for d in range(0, 8):
            all_e += get_upcoming_earnings(days_ahead=d)
        if not all_e:
            await ctx.send("Keine Quartalszahlen in den naechsten 7 Tagen.")
            return
        msg = "📅 **Quartalszahlen:**\n" + "\n".join([f"🏢 **{e['ticker']}** – {e['date']}" for e in all_e])
        await ctx.send(msg)

@bot.command(name='wirtschaft')
async def econ_cmd(ctx):
    async with ctx.typing():
        events = get_economic_calendar()
        if not events:
            await ctx.send("Keine wichtigen Termine diese Woche.")
            return
        msg = "🌍 **WIRTSCHAFTSKALENDER:**\n" + "\n".join(
            [f"📌 **{e.get('event', '')}** | {e.get('country', '')}" for e in events])
        await ctx.send(msg)

@bot.command(name='preise')
async def prices_cmd(ctx):
    async with ctx.typing():
        prices = get_all_prices()
        lines = []
        for p in prices:
            if not p:
                continue
            sign = "+" if p['change_pct'] > 0 else ""
            icon = "🟢" if p['change_pct'] > 0 else "🔴"
            lines.append(f"{icon} **{p['ticker']}**: ${p['price']:,.2f} ({sign}{p['change_pct']:.2f}%)")
        await ctx.send("💹 **Live-Kurse:**\n" + "\n".join(lines) if lines else "Keine Kurse.")

@bot.command(name='analyze')
async def analyze_cmd(ctx, ticker: str):
    ticker = ticker.upper()
    async with ctx.typing():
        data = get_company_financials(ticker)
        news = get_ticker_news_finnhub(ticker, days=2)
        news_str = " | ".join([n['title'] for n in news[:3]]) if news else "keine News"
        pe = data.get('pe_ratio', 'unbekannt') if data else 'unbekannt'
        response = chat_with_jarvis(
            f"Analysiere {ticker}. KGV: {pe}. News: {news_str}. Kaufen, halten oder verkaufen?",
            WATCHLIST_STOCKS + WATCHLIST_CRYPTO)
        await ctx.send(f"📊 **{ticker} – Analyse:**\n{response}")

@bot.command(name='watchlist')
async def watchlist_cmd(ctx):
    await ctx.send(f"📋 **Watchlist:**\n📈 {', '.join(WATCHLIST_STOCKS)}\n🪙 {', '.join(WATCHLIST_CRYPTO)}")

@bot.command(name='help')
async def help_cmd(ctx):
    await ctx.send(
        "**Jarvis – Dein Finanzberater** 🤖\n\n"
        "Schreib mir einfach auf Deutsch – ich antworte zu allem:\n"
        "Aktien, Krypto, Gold, Oel, Geopolitik, Notenbanken...\n\n"
        "**Automatisch:**\n"
        "☀️`8h` Morgen | 😱`9h` Fear&Greed | 🌙`21h` Abend | 📅`Fr19h` Woche\n\n"
        "**Befehle:**\n"
        "`!morgen` `!briefing` `!woche` – Sofort-Briefings\n"
        "`!preise` `!angst` `!sektoren` – Marktdaten\n"
        "`!dividenden` `!earnings` `!wirtschaft`\n"
        "`!analyze TSLA` – KI-Analyse\n"
        "`!start_alerts` – Kanal festlegen (einmalig!)\n"
    )


if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN.startswith("DEIN"):
        print("FEHLER: Discord Bot Token fehlt!")
    else:
        bot.run(DISCORD_BOT_TOKEN)
