# ============================================================
# ai_analyst.py - Das KI-Gehirn (OpenAI GPT-4o)
# ============================================================
import logging
from openai import OpenAI
from config import GROQ_API_KEY, AI_MODEL, AI_LANGUAGE

logger = logging.getLogger(__name__)
client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

# ============================================================
# SYSTEM-PROMPTS
# ============================================================

FILTER_SYSTEM_PROMPT = f"""Du bist ein hochspezialisierter Finanzanalyst-KI-Assistent.
Deine einzige Aufgabe ist es, eingehende Nachrichten auf ihre Marktrelevanz zu bewerten.

BEWERTUNGSREGELN:
- Antworte AUSSCHLIESSLICH im JSON-Format: {{"relevanz": "HOCH|MITTEL|NIEDRIG|IGNORIEREN", "begruendung": "...", "betroffene_ticker": ["AAPL", "BTC"]}}
- HOCH: Zentralbank-Entscheidungen, massive Kurseinbrueche (>5%), Kriegseskalation, CEO-Ruecktritte, Gewinnwarnungen, Regulierungsentscheide
- MITTEL: Quartalszahlen (gut/schlecht), neue Produktankuendigungen, M&A-Geruechte, politische Aussagen zu Wirtschaft
- NIEDRIG: Routine-Analysen, allgemeine Marktkommentare, unbedeutende Firmenmeldungen
- IGNORIEREN: Sportnachrichten, Klatsch, unrelated content, Werbung
- Antworte immer auf {AI_LANGUAGE}
"""

ANALYSIS_SYSTEM_PROMPT = f"""Du bist Jarvis, ein brillanter und praeziser KI-Finanzanalyst.
Du analysierst Finanznews und Marktdaten fuer deinen Nutzer.

DEIN STIL:
- Praezise, faktenbasiert, kein Blabla
- Maximal 4-5 Saetze pro Analyse
- Nenne immer konkrete Zahlen wenn vorhanden
- Beschreibe was es BEDEUTET, nicht nur was passiert ist
- Antworte auf {AI_LANGUAGE}
- Du gibst KEINE direkten Kaufempfehlungen (nur Analysen)

FORMAT DEINER ANTWORT:
- Was ist passiert? (1 Satz)
- Warum ist es relevant? (1-2 Saetze)
- Moegliche Marktauswirkung? (1-2 Saetze)
"""

BRIEFING_SYSTEM_PROMPT = f"""Du bist Jarvis, ein Wall-Street-erfahrener Finanzanalyst.
Erstelle ein praegnantes Markt-Briefing basierend auf den uebergebenen Daten.

STRUKTUR DES BRIEFINGS:
1. Gesamtstimmung der Maerkte (1 Satz mit Emoji)
2. Top-Gewinner & Verlierer aus der Watchlist
3. 3 wichtigste Ereignisse des Tages
4. Ausblick / Was heute noch wichtig wird

Halte es kurz, praezise, und informativ. Antworte auf {AI_LANGUAGE}.
"""


# ============================================================
# KI-FUNKTIONEN
# ============================================================

def filter_news_relevance(title: str, summary: str, source: str) -> dict:
    """
    Bewertet eine Nachricht auf Marktrelevanz.
    Gibt Dict zurueck mit: relevanz, begruendung, betroffene_ticker
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("gsk_DEIN"):
        logger.warning("Groq Key nicht gesetzt - alle News als MITTEL gewertet")
        return {"relevanz": "MITTEL", "begruendung": "KI nicht konfiguriert", "betroffene_ticker": []}

    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Titel: {title}\nQuelle: {source}\nZusammenfassung: {summary}"},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        import json
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f"KI-Filter Fehler: {e}")
        return {"relevanz": "NIEDRIG", "begruendung": str(e), "betroffene_ticker": []}


def analyze_news(title: str, summary: str, source: str, ticker: str = "") -> str:
    """
    Erstellt eine detaillierte KI-Analyse einer Nachricht.
    Gibt einen formatierten Analysetext zurueck.
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("gsk_DEIN"):
        return summary[:300] + "..."

    try:
        user_msg = f"Analysiere diese Finanznachricht:\n\nTitel: {title}\nQuelle: {source}"
        if ticker:
            user_msg += f"\nBetroffener Ticker: {ticker}"
        if summary:
            user_msg += f"\n\nDetails: {summary[:1000]}"

        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"KI-Analyse Fehler: {e}")
        return f"Analyse nicht verfuegbar: {e}"


def analyze_price_move(ticker: str, price: float, change_pct: float, recent_news: list) -> str:
    """
    Erklaert einen starken Kursbewegung mit Hilfe aktueller News.
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("gsk_DEIN"):
        return ""

    news_text = "\n".join([f"- {n.get('title', '')}" for n in recent_news[:5]])
    direction = "gestiegen" if change_pct > 0 else "gefallen"
    user_msg = (
        f"{ticker} ist heute um {abs(change_pct):.2f}% {direction} und steht bei .\n"
        f"Aktuelle News zu diesem Unternehmen:\n{news_text}\n\n"
        f"Erklaere in 2-3 Saetzen was den Kursausschlag verursacht haben koennte."
    )
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Kursanalyse Fehler: {e}")
        return ""


def generate_morning_briefing(prices: list, top_news: list, earnings: list) -> str:
    """
    Generiert das morgendliche Markt-Briefing.
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("gsk_DEIN"):
        return "KI-Briefing nicht verfuegbar (Groq Key fehlt)."

    # Daten aufbereiten
    price_summary = "\n".join([
        f"- {p['ticker']}:  ({'+' if p['change_pct'] > 0 else ''}{p['change_pct']:.2f}%)"
        for p in prices if p
    ])
    news_summary = "\n".join([f"- {n['title']} ({n['source']})" for n in top_news[:8]])
    earnings_text = "\n".join([
        f"- {e.get('symbol')} berichtet am {e.get('date', '?')}"
        for e in earnings[:5]
    ]) if earnings else "Keine relevanten Earnings heute."

    user_msg = (
        f"AKTUELLE KURSE (Watchlist):\n{price_summary}\n\n"
        f"TOP NACHRICHTEN:\n{news_summary}\n\n"
        f"BEVORSTEHENDE EARNINGS:\n{earnings_text}\n\n"
        f"Erstelle jetzt das Morgen-Briefing."
    )
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.5,
            max_tokens=600,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Briefing-Generierung Fehler: {e}")
        return f"Briefing nicht verfuegbar: {e}"


def analyze_earnings_report(ticker: str, report_text: str) -> str:
    """
    Analysiert einen Quartalsbericht und extrahiert die Kernaussagen.
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("gsk_DEIN"):
        return "Groq Key fehlt fuer Quartalsbericht-Analyse."

    user_msg = (
        f"Analysiere diesen Quartalsbericht von {ticker}:\n\n"
        f"{report_text[:3000]}\n\n"
        f"Beantworte: 1) War es besser/schlechter als erwartet? "
        f"2) Was waren die 3 wichtigsten Aussagen des Managements? "
        f"3) Wie wird der Markt wahrscheinlich reagieren?"
    )
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Earnings-Analyse Fehler: {e}")
        return str(e)

def chat_with_jarvis(user_message: str, watchlist: list) -> str:
    """Allgemeine Chat-Funktion fuer interaktive Discord-Nachrichten"""
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("gsk_DEIN"):
        return "Groq Key fehlt."
    
    system_prompt = (
        "Du bist Jarvis, ein brillanter, leicht sarkastischer Finanz-KI-Assistent. "
        "Du sprichst auf Deutsch. Du ueberwachst Aktien und analysierst Maerkte fuer deinen 'Master'. "
        "Du gibst keine direkten, bindenden Finanzberatungen, sondern fundierte Analysen, so dass die Entscheidung klar wird. "
        f"Die aktuelle Watchlist deines Masters ist: {', '.join(watchlist)}."
    )
    
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=600,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Ich habe gerade Verbindungsprobleme zu meinen Servern: {e}"

