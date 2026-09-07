# ============================================================
# data_fetcher.py - Alle Datenquellen (Kurse, News, RSS)
# ============================================================
import requests
import feedparser
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import (
    FINNHUB_API_KEY, NEWSAPI_KEY, ALPHAVANTAGE_KEY,
    WATCHLIST_STOCKS, WATCHLIST_CRYPTO, RSS_FEEDS
)

logger = logging.getLogger(__name__)

# Verhindert doppelte Alarme (speichert bereits gesendete News-IDs)
_seen_articles: set = set()


# ============================================================
# AKTIENKURSE
# ============================================================

def get_stock_price_alphavantage(ticker: str) -> Optional[Dict]:
    """Holt aktuellen Kurs + Veraenderung von Alpha Vantage (kostenlos)."""
    if not ALPHAVANTAGE_KEY or ALPHAVANTAGE_KEY.startswith("DEIN"):
        return _get_stock_price_fallback(ticker)

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker,
        "apikey": ALPHAVANTAGE_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json().get("Global Quote", {})
        if not data:
            return None
        return {
            "ticker":     ticker,
            "price":      float(data.get("05. price", 0)),
            "change_pct": float(data.get("10. change percent", "0%").replace("%", "")),
            "volume":     int(data.get("06. volume", 0)),
            "source":     "Alpha Vantage",
        }
    except Exception as e:
        logger.error(f"Alpha Vantage Fehler ({ticker}): {e}")
        return None


def _get_stock_price_fallback(ticker: str) -> Optional[Dict]:
    """Fallback: Yahoo Finance (kein API-Key noetig)."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev  = meta.get("previousClose", price)
        change_pct = ((price - prev) / prev * 100) if prev else 0
        return {
            "ticker":     ticker,
            "price":      price,
            "change_pct": change_pct,
            "volume":     meta.get("regularMarketVolume", 0),
            "source":     "Yahoo Finance",
        }
    except Exception as e:
        logger.error(f"Yahoo Finance Fallback Fehler ({ticker}): {e}")
        return None


def get_all_prices() -> List[Dict]:
    """Holt Kurse fuer alle Tickers in der Watchlist."""
    results = []
    all_tickers = WATCHLIST_STOCKS + WATCHLIST_CRYPTO
    for ticker in all_tickers:
        data = get_stock_price_alphavantage(ticker)
        if data:
            results.append(data)
    return results


# ============================================================
# NEWS VIA FINNHUB
# ============================================================

def get_finnhub_news(category: str = "general", limit: int = 20) -> List[Dict]:
    """
    Holt aktuelle Finanznews von Finnhub.
    category: 'general' | 'forex' | 'crypto' | 'merger'
    """
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        logger.warning("Finnhub API-Key nicht gesetzt - ueberspringe Finnhub")
        return []

    url = "https://finnhub.io/api/v1/news"
    params = {"category": category, "token": FINNHUB_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        articles = resp.json()[:limit]
        result = []
        for a in articles:
            article_id = str(a.get("id", a.get("url", "")))
            if article_id in _seen_articles:
                continue
            _seen_articles.add(article_id)
            result.append({
                "id":      article_id,
                "title":   a.get("headline", ""),
                "summary": a.get("summary", ""),
                "source":  a.get("source", "Finnhub"),
                "url":     a.get("url", ""),
                "time":    datetime.fromtimestamp(a.get("datetime", 0)).strftime("%H:%M"),
            })
        return result
    except Exception as e:
        logger.error(f"Finnhub Fehler: {e}")
        return []


def get_ticker_news_finnhub(ticker: str, days: int = 3) -> List[Dict]:
    """Holt News zu einem spezifischen Ticker (z.B. AAPL)."""
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = "https://finnhub.io/api/v1/company-news"
    params = {"symbol": ticker, "from": from_date, "to": today, "token": FINNHUB_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        articles = resp.json()[:10]
        return [{
            "title":   a.get("headline", ""),
            "summary": a.get("summary", ""),
            "source":  a.get("source", ""),
            "url":     a.get("url", ""),
        } for a in articles]
    except Exception as e:
        logger.error(f"Finnhub Ticker-News Fehler ({ticker}): {e}")
        return []


# ============================================================
# NEWS VIA NEWSAPI
# ============================================================

def get_newsapi_headlines(query: str = "stock market finance", language: str = "en") -> List[Dict]:
    """Holt aktuelle Schlagzeilen von NewsAPI."""
    if not NEWSAPI_KEY or NEWSAPI_KEY.startswith("DEIN"):
        logger.warning("NewsAPI Key nicht gesetzt - ueberspringe NewsAPI")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        articles = resp.json().get("articles", [])
        result = []
        for a in articles:
            article_id = a.get("url", "")
            if article_id in _seen_articles:
                continue
            _seen_articles.add(article_id)
            result.append({
                "id":      article_id,
                "title":   a.get("title", ""),
                "summary": a.get("description", ""),
                "source":  a.get("source", {}).get("name", "NewsAPI"),
                "url":     a.get("url", ""),
                "time":    a.get("publishedAt", "")[:16].replace("T", " "),
            })
        return result
    except Exception as e:
        logger.error(f"NewsAPI Fehler: {e}")
        return []


# ============================================================
# RSS-FEEDS (Weisses Haus, SEC, Reuters, etc.)
# ============================================================

def get_rss_articles(feed_name: str = None) -> List[Dict]:
    """
    Liest RSS-Feeds aus. Gibt alle oder einen bestimmten Feed zurueck.
    Kein API-Key noetig!
    """
    feeds_to_parse = {}
    if feed_name and feed_name in RSS_FEEDS:
        feeds_to_parse[feed_name] = RSS_FEEDS[feed_name]
    else:
        feeds_to_parse = RSS_FEEDS

    all_articles = []
    for name, url in feeds_to_parse.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                article_id = entry.get("link", entry.get("id", ""))
                if article_id in _seen_articles:
                    continue
                _seen_articles.add(article_id)

                summary = entry.get("summary", entry.get("description", ""))
                # HTML-Tags entfernen
                from bs4 import BeautifulSoup
                summary = BeautifulSoup(summary, "lxml").get_text()[:500]

                all_articles.append({
                    "id":      article_id,
                    "title":   entry.get("title", ""),
                    "summary": summary,
                    "source":  name,
                    "url":     article_id,
                    "time":    entry.get("published", "")[:16],
                })
        except Exception as e:
            logger.error(f"RSS-Feed Fehler ({name}): {e}")

    return all_articles


# ============================================================
# QUARTALSBERICHTE & FUNDAMENTALDATEN
# ============================================================

def get_earnings_calendar() -> List[Dict]:
    """Holt bevorstehende Earnings-Termine von Finnhub."""
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    end   = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    url   = "https://finnhub.io/api/v1/calendar/earnings"
    params = {"from": today, "to": end, "token": FINNHUB_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        earnings = resp.json().get("earningsCalendar", [])
        # Nur Tickers aus unserer Watchlist
        relevant = [e for e in earnings if e.get("symbol") in WATCHLIST_STOCKS]
        return relevant[:10]
    except Exception as e:
        logger.error(f"Earnings Calendar Fehler: {e}")
        return []


def get_company_financials(ticker: str) -> Optional[Dict]:
    """Holt grundlegende Finanzkennzahlen (KGV, Marktkapitalisierung etc.)."""
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("DEIN"):
        return None

    url = "https://finnhub.io/api/v1/stock/metric"
    params = {"symbol": ticker, "metric": "all", "token": FINNHUB_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        metrics = data.get("metric", {})
        return {
            "ticker":     ticker,
            "pe_ratio":   metrics.get("peNormalizedAnnual"),
            "eps":        metrics.get("epsNormalizedAnnual"),
            "market_cap": metrics.get("marketCapitalization"),
            "52w_high":   metrics.get("52WeekHigh"),
            "52w_low":    metrics.get("52WeekLow"),
            "revenue":    metrics.get("revenuePerShareAnnual"),
            "roe":        metrics.get("roeRfy"),
        }
    except Exception as e:
        logger.error(f"Fundamentaldaten Fehler ({ticker}): {e}")
        return None
