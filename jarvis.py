import os
import sys
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# ============================================================
# jarvis.py - Haupt-Orchestrator (Der eigentliche Jarvis)
# ============================================================
import logging
import time
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import (
    PRICE_CHANGE_THRESHOLD, WATCHLIST_STOCKS,
    INTERVAL_NEWS_SCAN, INTERVAL_PRICE_CHECK,
    INTERVAL_MORNING_BRIEF, INTERVAL_EVENING_BRIEF,
)
from data_fetcher import (
    get_all_prices, get_finnhub_news, get_newsapi_headlines,
    get_rss_articles, get_earnings_calendar, get_ticker_news_finnhub,
)
from ai_analyst import (
    filter_news_relevance, analyze_news, analyze_price_move,
    generate_morning_briefing,
)
from notifier import (
    send_alert, send_price_alert,
    send_morning_briefing, send_evening_briefing, send_discord,
)

# --- Logging einrichten ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("jarvis.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("JARVIS")
console = Console()

# Gespeicherte Preise fuer Vergleich
_last_prices: dict = {}


# ============================================================
# TASK 1: NEWS SCANNER (laeuft alle 5 Minuten)
# ============================================================
def scan_news():
    """
    Holt alle neuen News aus allen Quellen,
    filtert sie mit KI und sendet Alarme bei relevanten Nachrichten.
    """
    console.print(f"[cyan]🔍 News-Scan startet... [{datetime.now().strftime('%H:%M:%S')}][/cyan]")

    all_articles = []

    # Finnhub News (mehrere Kategorien)
    all_articles += get_finnhub_news(category="general", limit=15)
    all_articles += get_finnhub_news(category="crypto",  limit=10)
    all_articles += get_finnhub_news(category="merger",  limit=5)

    # NewsAPI
    all_articles += get_newsapi_headlines(query="federal reserve interest rates stocks")
    all_articles += get_newsapi_headlines(query="cryptocurrency bitcoin market")

    # RSS-Feeds (Weisses Haus, SEC, Reuters, etc.)
    all_articles += get_rss_articles()

    console.print(f"  📰 {len(all_articles)} neue Artikel gefunden")

    alarm_count = 0
    for article in all_articles:
        title   = article.get("title", "")
        summary = article.get("summary", "")
        source  = article.get("source", "")
        url     = article.get("url", "")

        if not title or len(title) < 10:
            continue

        # KI-Relevanzfilter
        result = filter_news_relevance(title, summary, source)
        relevanz = result.get("relevanz", "IGNORIEREN")
        tickers  = result.get("betroffene_ticker", [])

        if relevanz == "IGNORIEREN" or relevanz == "NIEDRIG":
            continue

        # KI-Analyse erstellen
        ticker_str = ", ".join(tickers) if tickers else "Markt allgemein"
        analysis = analyze_news(title, summary, source, ticker=ticker_str)

        # Alarm senden
        send_alert(
            ticker=ticker_str,
            title=title,
            summary=analysis,
            source=f"{source}: {url}",
            urgency=relevanz,
        )
        alarm_count += 1

        # Kurzpause damit Telegram nicht überflutet wird
        time.sleep(1.5)

    if alarm_count > 0:
        console.print(f"  [bold green]✅ {alarm_count} Alarme gesendet[/bold green]")
    else:
        console.print(f"  [dim]✅ Keine relevanten Alarme[/dim]")


# ============================================================
# TASK 2: KURSALARM (laeuft alle 3 Minuten)
# ============================================================
def check_prices():
    """
    Prueft alle Kurse in der Watchlist.
    Sendet Alarm wenn ein Kurs mehr als PRICE_CHANGE_THRESHOLD % bewegt hat.
    """
    prices = get_all_prices()
    if not prices:
        return

    # Tabelle im Terminal anzeigen
    table = Table(title=f"📊 Watchlist [{datetime.now().strftime('%H:%M')}]")
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Preis",  style="white")
    table.add_column("% Tag",  style="white")
    table.add_column("Alarm",  style="white")

    for p in prices:
        ticker     = p.get("ticker", "")
        price      = p.get("price", 0)
        change_pct = p.get("change_pct", 0)

        # Farbe je nach Bewegung
        color = "green" if change_pct > 0 else "red" if change_pct < 0 else "white"
        sign  = "+" if change_pct > 0 else ""
        alarm = ""

        # Alarm wenn Schwellenwert ueberschritten
        if abs(change_pct) >= PRICE_CHANGE_THRESHOLD:
            alarm = "🚨"
            # Erklaerung von KI holen
            news = get_ticker_news_finnhub(ticker, days=1)
            reason = analyze_price_move(ticker, price, change_pct, news)
            send_price_alert(ticker, price, change_pct, reason)

        table.add_row(
            ticker,
            f"",
            f"[{color}]{sign}{change_pct:.2f}%[/{color}]",
            alarm,
        )
        _last_prices[ticker] = price

    console.print(table)


# ============================================================
# TASK 3: MORGEN-BRIEFING (jeden Morgen um 7:00 Uhr)
# ============================================================
def morning_briefing():
    """
    Erstellt und sendet das taegliche Morgen-Briefing.
    Enthaelt: Marktueberblick, Top-News, bevorstehende Earnings.
    """
    console.print("[yellow]☀️ Erstelle Morgen-Briefing...[/yellow]")

    prices   = get_all_prices()
    news     = get_finnhub_news(limit=20) + get_rss_articles("Reuters Business")
    earnings = get_earnings_calendar()

    briefing = generate_morning_briefing(prices, news, earnings)
    send_morning_briefing(briefing)
    console.print("[green]✅ Morgen-Briefing gesendet[/green]")


# ============================================================
# TASK 4: ABEND-BRIEFING (jeden Abend um 20:00 Uhr)
# ============================================================
def evening_briefing():
    """Abend-Zusammenfassung des Handelstages."""
    console.print("[yellow]🌙 Erstelle Abend-Briefing...[/yellow]")

    prices   = get_all_prices()
    news     = get_finnhub_news(limit=30) + get_rss_articles()
    earnings = get_earnings_calendar()

    briefing = generate_morning_briefing(prices, news, earnings)
    send_evening_briefing(briefing)
    console.print("[green]✅ Abend-Briefing gesendet[/green]")


# ============================================================
# HAUPTPROGRAMM
# ============================================================
def main():
    console.print(Panel.fit(
        "[bold cyan]💼 FINANCIAL JARVIS[/bold cyan]\n"
        "[dim]Dein persoenlicher KI-Finanzanalyst[/dim]\n"
        f"[dim]Watchlist: {', '.join(WATCHLIST_STOCKS)}[/dim]",
        border_style="cyan",
    ))

    # Sofortiger Start-Check
    console.print("[yellow]🚀 Starte initialen Check...[/yellow]")
    check_prices()
    scan_news()
    send_discord("🟢 <b>Financial Jarvis ist jetzt aktiv!**\nDu wirst ab jetzt bei wichtigen Marktereignissen sofort benachrichtigt.")

    # APScheduler einrichten
    scheduler = BlockingScheduler(timezone="Europe/Berlin")

    # News-Scan alle 5 Minuten
    scheduler.add_job(scan_news, "interval", seconds=INTERVAL_NEWS_SCAN, id="news_scan")

    # Kurs-Check alle 3 Minuten
    scheduler.add_job(check_prices, "interval", seconds=INTERVAL_PRICE_CHECK, id="price_check")

    # Morgen-Briefing (07:00)
    h, m = INTERVAL_MORNING_BRIEF.split(":")
    scheduler.add_job(morning_briefing, "cron", hour=int(h), minute=int(m), id="morning_brief")

    # Abend-Briefing (20:00)
    h, m = INTERVAL_EVENING_BRIEF.split(":")
    scheduler.add_job(evening_briefing, "cron", hour=int(h), minute=int(m), id="evening_brief")

    console.print(f"[green]✅ Scheduler gestartet![/green]")
    console.print(f"  📰 News-Scan: alle {INTERVAL_NEWS_SCAN//60} Minuten")
    console.print(f"  📊 Kurs-Check: alle {INTERVAL_PRICE_CHECK//60} Minuten")
    console.print(f"  ☀️ Morgen-Briefing: {INTERVAL_MORNING_BRIEF} Uhr")
    console.print(f"  🌙 Abend-Briefing: {INTERVAL_EVENING_BRIEF} Uhr")
    console.print("[dim]Druecke Strg+C zum Beenden[/dim]\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[yellow]⚠️ Jarvis wird beendet...[/yellow]")
        send_discord("🔴 <b>Financial Jarvis wurde beendet.**")


if __name__ == "__main__":
    main()

