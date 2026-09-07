# ============================================================
# dashboard.py - Interaktives Terminal-Dashboard
# Starte mit: python dashboard.py
# ============================================================
import sys
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.layout import Layout
from rich.live import Live
from rich.text import Text

from data_fetcher import (
    get_all_prices, get_finnhub_news, get_rss_articles,
    get_earnings_calendar, get_company_financials,
)
from ai_analyst import analyze_news, analyze_earnings_report

console = Console()


def build_price_table(prices):
    table = Table(title="📊 Markt-Watchlist", border_style="cyan", show_header=True)
    table.add_column("Ticker",  style="bold white", width=10)
    table.add_column("Preis",   style="white",      width=12, justify="right")
    table.add_column("% Tag",   style="white",      width=10, justify="right")
    table.add_column("Volumen", style="dim",         width=14, justify="right")
    table.add_column("Quelle",  style="dim",         width=14)

    for p in prices:
        if not p:
            continue
        chg = p.get("change_pct", 0)
        color = "green" if chg > 0 else "red" if chg < 0 else "white"
        sign  = "+" if chg > 0 else ""
        vol   = p.get("volume", 0)
        vol_str = f"{vol:,}" if vol else "-"

        table.add_row(
            p.get("ticker", ""),
            f"",
            f"[{color}]{sign}{chg:.2f}%[/{color}]",
            vol_str,
            p.get("source", ""),
        )
    return table


def build_news_table(articles, max_rows=8):
    table = Table(title="📰 Aktuelle News", border_style="yellow", show_header=True)
    table.add_column("Zeit",   style="dim",   width=7)
    table.add_column("Quelle", style="cyan",  width=18)
    table.add_column("Schlagzeile", style="white", width=60)

    for a in articles[:max_rows]:
        table.add_row(
            a.get("time", "")[-5:] or "--:--",
            a.get("source", "")[:18],
            a.get("title", "")[:60],
        )
    return table


def interactive_menu():
    """Interaktives Menue fuer manuelle Analysen."""
    while True:
        console.print("\n[bold cyan]═══ JARVIS ANALYSE-MENUE ═══[/bold cyan]")
        console.print("[1] 📊 Aktuelle Kurse anzeigen")
        console.print("[2] 📰 Neueste Nachrichten")
        console.print("[3] 🤖 KI-Analyse einer Nachricht")
        console.print("[4] 🏢 Fundamentaldaten einer Aktie")
        console.print("[5] 📅 Bevorstehende Earnings")
        console.print("[6] 🌐 RSS-Feeds lesen")
        console.print("[0] ❌ Beenden")

        choice = input("\nWaehle eine Option: ").strip()

        if choice == "1":
            console.print("\n[dim]Lade Kurse...[/dim]")
            prices = get_all_prices()
            console.print(build_price_table(prices))

        elif choice == "2":
            console.print("\n[dim]Lade News...[/dim]")
            news = get_finnhub_news(limit=15)
            console.print(build_news_table(news, max_rows=15))

        elif choice == "3":
            console.print("\n[bold]KI-News-Analyse[/bold]")
            title   = input("Titel der Nachricht: ")
            summary = input("Kurze Beschreibung: ")
            source  = input("Quelle (z.B. Reuters): ")
            console.print("\n[dim]KI analysiert...[/dim]")
            analysis = analyze_news(title, summary, source)
            console.print(Panel(analysis, title="🤖 Jarvis Analyse", border_style="green"))

        elif choice == "4":
            ticker = input("Ticker eingeben (z.B. AAPL): ").upper()
            console.print(f"\n[dim]Lade Fundamentaldaten fuer {ticker}...[/dim]")
            data = get_company_financials(ticker)
            if data:
                table = Table(title=f"📈 {ticker} Fundamentaldaten")
                table.add_column("Kennzahl", style="cyan")
                table.add_column("Wert",     style="white")
                metrics = {
                    "KGV (P/E Ratio)":    data.get("pe_ratio"),
                    "EPS (Gewinn/Aktie)": data.get("eps"),
                    "Marktkapital. (Mrd)":data.get("market_cap"),
                    "52-Wochen-Hoch":     data.get("52w_high"),
                    "52-Wochen-Tief":     data.get("52w_low"),
                    "Eigenkapitalrendite":data.get("roe"),
                }
                for k, v in metrics.items():
                    table.add_row(k, str(round(v, 2)) if v else "N/A")
                console.print(table)
            else:
                console.print("[red]Keine Daten gefunden. Bitte Finnhub API-Key pruefen.[/red]")

        elif choice == "5":
            console.print("\n[dim]Lade Earnings-Kalender...[/dim]")
            earnings = get_earnings_calendar()
            if earnings:
                table = Table(title="📅 Bevorstehende Quartalszahlen")
                table.add_column("Datum",  style="cyan")
                table.add_column("Ticker", style="bold white")
                table.add_column("Uhrzeit",style="dim")
                for e in earnings:
                    table.add_row(
                        e.get("date", ""),
                        e.get("symbol", ""),
                        e.get("hour", "N/A"),
                    )
                console.print(table)
            else:
                console.print("[dim]Keine Earnings in den naechsten 7 Tagen fuer deine Watchlist.[/dim]")

        elif choice == "6":
            console.print("\n[dim]Lese RSS-Feeds...[/dim]")
            articles = get_rss_articles()
            console.print(build_news_table(articles, max_rows=20))

        elif choice == "0":
            console.print("[yellow]Auf Wiedersehen![/yellow]")
            sys.exit(0)
        else:
            console.print("[red]Ungueltige Eingabe.[/red]")


if __name__ == "__main__":
    console.print(Panel.fit(
        "[bold cyan]💼 FINANCIAL JARVIS - DASHBOARD[/bold cyan]\n"
        "[dim]Interaktives Analyse-Terminal[/dim]",
        border_style="cyan",
    ))
    interactive_menu()
