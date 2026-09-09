"""
dashboard.py – Financial Jarvis Web-Dashboard
Laeuft parallel zum Discord-Bot auf Port 5000
Automatische Aktualisierung alle 60 Sekunden
"""
from flask import Flask, render_template_string, jsonify
import threading
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Financial Jarvis Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0f0f1a; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
        
        header {
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #00d4aa;
        }
        header h1 { color: #00d4aa; font-size: 1.8em; }
        header span { color: #888; font-size: 0.9em; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            padding: 25px;
        }
        
        .card {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #333355;
            transition: transform 0.2s;
        }
        .card:hover { transform: translateY(-3px); }
        .card h2 {
            color: #00d4aa;
            font-size: 1em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
            border-bottom: 1px solid #333355;
            padding-bottom: 8px;
        }
        
        .stock-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #222244;
        }
        .stock-item:last-child { border-bottom: none; }
        .stock-ticker { font-weight: bold; color: #fff; min-width: 80px; }
        .stock-price { color: #aaa; }
        .stock-change { font-weight: bold; min-width: 70px; text-align: right; }
        .positive { color: #00d4aa; }
        .negative { color: #ff4757; }
        
        .fg-bar-container {
            background: linear-gradient(to right, #00d4aa, #ffd700, #ff4757);
            height: 12px;
            border-radius: 6px;
            margin: 15px 0;
            position: relative;
        }
        .fg-marker {
            position: absolute;
            top: -4px;
            width: 20px;
            height: 20px;
            background: white;
            border-radius: 50%;
            transform: translateX(-50%);
            border: 3px solid #0f0f1a;
        }
        .fg-score { font-size: 2.5em; font-weight: bold; text-align: center; margin: 10px 0; }
        .fg-label { text-align: center; font-size: 1.1em; }
        
        .news-item {
            padding: 10px 0;
            border-bottom: 1px solid #222244;
            font-size: 0.9em;
            line-height: 1.4;
        }
        .news-item:last-child { border-bottom: none; }
        .news-source { color: #00d4aa; font-size: 0.8em; margin-bottom: 3px; }
        
        .stat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        .stat-box {
            background: #1a1a2e;
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }
        .stat-value { font-size: 1.4em; font-weight: bold; color: #00d4aa; }
        .stat-label { font-size: 0.8em; color: #888; margin-top: 4px; }
        
        .refresh-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #16213e;
            border-top: 1px solid #333355;
            padding: 8px 30px;
            display: flex;
            justify-content: space-between;
            font-size: 0.85em;
            color: #666;
        }
        .live-dot {
            width: 8px; height: 8px;
            background: #00d4aa;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        
        #last-update { color: #00d4aa; }
        
        .winner { background: rgba(0, 212, 170, 0.1); border-radius: 6px; padding: 2px 6px; }
        .loser { background: rgba(255, 71, 87, 0.1); border-radius: 6px; padding: 2px 6px; }
    </style>
</head>
<body>
    <header>
        <h1>🤖 Financial Jarvis Dashboard</h1>
        <span><span class="live-dot"></span>Live • Aktualisierung alle 60 Sekunden</span>
    </header>
    
    <div class="grid" id="main-grid">
        <!-- Wird dynamisch befuellt -->
        <div class="card"><h2>Laden...</h2></div>
    </div>
    
    <div class="refresh-bar">
        <span><span class="live-dot"></span>Jarvis laeuft</span>
        <span>Letzte Aktualisierung: <span id="last-update">--</span></span>
        <span>Naechste in: <span id="countdown">60</span>s</span>
    </div>

    <script>
        let countdown = 60;

        async function loadData() {
            try {
                const resp = await fetch('/api/data');
                const data = await resp.json();
                renderDashboard(data);
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString('de-CH');
                countdown = 60;
            } catch (e) {
                console.error('Ladefehler:', e);
            }
        }

        function renderDashboard(data) {
            const grid = document.getElementById('main-grid');
            grid.innerHTML = '';

            // Fear & Greed
            const fg = data.fear_greed || { score: 50, label: 'Neutral' };
            const fgColor = fg.score <= 30 ? '#00d4aa' : fg.score >= 70 ? '#ff4757' : '#ffd700';
            grid.innerHTML += `
                <div class="card">
                    <h2>😱 Fear &amp; Greed Index</h2>
                    <div class="fg-score" style="color:${fgColor}">${fg.score}</div>
                    <div class="fg-bar-container">
                        <div class="fg-marker" style="left:${fg.score}%"></div>
                    </div>
                    <div class="fg-label" style="color:${fgColor}">${fg.label}</div>
                </div>`;

            // Markt-Statistiken
            const prices = data.prices || [];
            const winners = prices.filter(p => p.change_pct > 0).length;
            const losers = prices.filter(p => p.change_pct < 0).length;
            const bigWinner = prices.sort((a,b) => b.change_pct - a.change_pct)[0];
            const bigLoser = [...prices].sort((a,b) => a.change_pct - b.change_pct)[0];
            grid.innerHTML += `
                <div class="card">
                    <h2>📊 Markt-Ueberblick</h2>
                    <div class="stat-grid">
                        <div class="stat-box">
                            <div class="stat-value positive">${winners}</div>
                            <div class="stat-label">Im Plus</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value negative">${losers}</div>
                            <div class="stat-label">Im Minus</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value positive">${bigWinner ? bigWinner.ticker : '-'}</div>
                            <div class="stat-label">Bester: ${bigWinner ? '+'+bigWinner.change_pct.toFixed(1)+'%' : ''}</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value negative">${bigLoser ? bigLoser.ticker : '-'}</div>
                            <div class="stat-label">Schlechtester: ${bigLoser ? bigLoser.change_pct.toFixed(1)+'%' : ''}</div>
                        </div>
                    </div>
                </div>`;

            // Alle Kurse
            const sortedPrices = [...(data.prices||[])].sort((a,b) => b.change_pct - a.change_pct);
            let priceHTML = '<div class="card" style="grid-column: span 2"><h2>💹 Live-Kurse (alle Titel)</h2>';
            priceHTML += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:5px">';
            for (const p of sortedPrices) {
                const cls = p.change_pct >= 0 ? 'positive' : 'negative';
                const sign = p.change_pct >= 0 ? '+' : '';
                priceHTML += `<div class="stock-item">
                    <span class="stock-ticker">${p.ticker}</span>
                    <span class="stock-price">$${p.price.toLocaleString('de-CH', {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
                    <span class="stock-change ${cls}">${sign}${p.change_pct.toFixed(2)}%</span>
                </div>`;
            }
            priceHTML += '</div></div>';
            grid.innerHTML += priceHTML;

            // News
            const news = data.news || [];
            let newsHTML = '<div class="card"><h2>📰 Aktuelle News</h2>';
            for (const n of news.slice(0,8)) {
                newsHTML += `<div class="news-item">
                    <div class="news-source">${n.source || 'News'}</div>
                    ${n.title}
                </div>`;
            }
            newsHTML += '</div>';
            grid.innerHTML += newsHTML;
        }

        // Countdown
        setInterval(() => {
            countdown--;
            document.getElementById('countdown').textContent = countdown;
            if (countdown <= 0) loadData();
        }, 1000);

        // Initial laden
        loadData();
    </script>
</body>
</html>
"""


def get_dashboard_data():
    """Holt alle Daten fuer das Dashboard"""
    result = {"prices": [], "fear_greed": {}, "news": [], "updated": datetime.now().isoformat()}

    try:
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from data_fetcher import get_all_prices, get_rss_articles

        prices = get_all_prices()
        result["prices"] = [p for p in prices if p]

        articles = get_rss_articles()[:10]
        result["news"] = [{"title": a.get("title", "")[:120],
                           "source": a.get("source", "")} for a in articles]

        try:
            import requests
            r = requests.get(
                "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=8
            )
            if r.status_code == 200:
                d = r.json()
                score = round(d.get("fear_and_greed", {}).get("score", 50))
                if score <= 20:    label = "😱 Extreme Angst"
                elif score <= 40:  label = "😨 Angst"
                elif score <= 60:  label = "😐 Neutral"
                elif score <= 80:  label = "😄 Gier"
                else:              label = "🤑 Extreme Gier"
                result["fear_greed"] = {"score": score, "label": label}
        except Exception:
            result["fear_greed"] = {"score": 50, "label": "😐 Neutral"}

    except Exception as e:
        result["error"] = str(e)

    return result


@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/data')
def api_data():
    data = get_dashboard_data()
    return jsonify(data)


def run_dashboard(port: int = 5000):
    """Startet das Dashboard in einem separaten Thread"""
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    print(f"Dashboard startet auf http://0.0.0.0:5000")
    run_dashboard()
