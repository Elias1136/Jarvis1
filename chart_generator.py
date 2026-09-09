"""
chart_generator.py – Erstellt Candlestick-Charts mit RSI und KI-Signalen
"""
import io
import matplotlib
matplotlib.use('Agg')  # Kein Display noetig (Server-Betrieb)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices: pd.Series):
    ema12 = prices.ewm(span=12).mean()
    ema26 = prices.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    return macd, signal


def generate_chart(ticker: str, period: str = "3mo") -> io.BytesIO | None:
    """
    Erstellt einen Chart mit:
    - Candlestick-Kerzen (gruen/rot)
    - 20/50-Tage gleitende Durchschnitte
    - RSI-Indikator
    - Automatische Kauf/Verkauf-Signale
    Gibt das Bild als BytesIO-Objekt zurueck (fuer Discord-Upload)
    """
    try:
        import yfinance as yf
        data = yf.Ticker(ticker).history(period=period)
        if data.empty or len(data) < 30:
            return None

        # Indikatoren berechnen
        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['RSI'] = calculate_rsi(data['Close'])
        data['MACD'], data['Signal'] = calculate_macd(data['Close'])

        # Kauf/Verkauf-Signale
        buy_signals = []
        sell_signals = []
        for i in range(1, len(data)):
            rsi = data['RSI'].iloc[i]
            prev_rsi = data['RSI'].iloc[i - 1]
            macd = data['MACD'].iloc[i]
            signal = data['Signal'].iloc[i]
            prev_macd = data['MACD'].iloc[i - 1]
            prev_signal = data['Signal'].iloc[i - 1]

            # Kaufsignal: RSI unter 35 oder MACD Crossover nach oben
            if (rsi < 35 and prev_rsi >= 35) or (macd > signal and prev_macd <= prev_signal and rsi < 60):
                buy_signals.append(i)
            # Verkaufssignal: RSI ueber 70 oder MACD Crossover nach unten
            elif (rsi > 70 and prev_rsi <= 70) or (macd < signal and prev_macd >= prev_signal and rsi > 40):
                sell_signals.append(i)

        # Chart zeichnen
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9),
                                        gridspec_kw={'height_ratios': [3, 1]},
                                        facecolor='#1a1a2e')
        fig.suptitle(f'{ticker} – Jarvis KI-Analyse ({period})',
                     color='white', fontsize=16, fontweight='bold', y=0.98)

        # --- Oberes Panel: Candlestick + Indikatoren ---
        ax1.set_facecolor('#16213e')
        dates = range(len(data))

        # Kerzen zeichnen
        for i in dates:
            o, h, l, c = data['Open'].iloc[i], data['High'].iloc[i], \
                          data['Low'].iloc[i], data['Close'].iloc[i]
            color = '#00d4aa' if c >= o else '#ff4757'
            ax1.plot([i, i], [l, h], color=color, linewidth=0.8)
            ax1.bar(i, abs(c - o), bottom=min(o, c), color=color,
                    width=0.6, alpha=0.9)

        # Gleitende Durchschnitte
        ax1.plot(dates, data['MA20'], color='#ffd700', linewidth=1.5,
                 label='MA20', alpha=0.8)
        ax1.plot(dates, data['MA50'], color='#ff6b6b', linewidth=1.5,
                 label='MA50', alpha=0.8)

        # Signale einzeichnen
        for idx in buy_signals:
            ax1.scatter(idx, data['Low'].iloc[idx] * 0.995,
                       color='#00ff88', marker='^', s=120, zorder=5)
            ax1.annotate('BUY', (idx, data['Low'].iloc[idx] * 0.992),
                        color='#00ff88', fontsize=7, ha='center', fontweight='bold')

        for idx in sell_signals:
            ax1.scatter(idx, data['High'].iloc[idx] * 1.005,
                       color='#ff4757', marker='v', s=120, zorder=5)
            ax1.annotate('SELL', (idx, data['High'].iloc[idx] * 1.008),
                        color='#ff4757', fontsize=7, ha='center', fontweight='bold')

        # X-Achse: Datum-Labels (alle 20 Tage)
        tick_positions = list(range(0, len(data), max(1, len(data) // 8)))
        tick_labels = [data.index[i].strftime('%d.%m') for i in tick_positions]
        ax1.set_xticks(tick_positions)
        ax1.set_xticklabels(tick_labels, color='#aaaaaa', fontsize=8)
        ax1.tick_params(colors='#aaaaaa')
        ax1.spines[:].set_color('#333355')
        ax1.grid(color='#222244', linestyle='--', linewidth=0.5, alpha=0.7)
        ax1.legend(loc='upper left', facecolor='#1a1a2e', edgecolor='#333355',
                  labelcolor='white', fontsize=9)

        # Aktueller Preis als Linie
        current_price = data['Close'].iloc[-1]
        ax1.axhline(y=current_price, color='#ffffff', linestyle=':', linewidth=1, alpha=0.5)
        ax1.text(len(data) - 1, current_price, f' ${current_price:.2f}',
                color='white', fontsize=9, va='center')

        # --- Unteres Panel: RSI ---
        ax2.set_facecolor('#16213e')
        ax2.plot(dates, data['RSI'], color='#a29bfe', linewidth=1.5, label='RSI(14)')
        ax2.axhline(70, color='#ff4757', linestyle='--', linewidth=1, alpha=0.7)
        ax2.axhline(30, color='#00d4aa', linestyle='--', linewidth=1, alpha=0.7)
        ax2.fill_between(dates, data['RSI'], 70,
                         where=data['RSI'] > 70, alpha=0.3, color='#ff4757')
        ax2.fill_between(dates, data['RSI'], 30,
                         where=data['RSI'] < 30, alpha=0.3, color='#00d4aa')
        ax2.set_ylim(0, 100)
        ax2.set_ylabel('RSI', color='#aaaaaa', fontsize=9)
        ax2.tick_params(colors='#aaaaaa')
        ax2.spines[:].set_color('#333355')
        ax2.grid(color='#222244', linestyle='--', linewidth=0.5, alpha=0.7)
        ax2.set_xticks(tick_positions)
        ax2.set_xticklabels(tick_labels, color='#aaaaaa', fontsize=8)

        # RSI-Wert aktuell anzeigen
        rsi_now = data['RSI'].iloc[-1]
        rsi_color = '#ff4757' if rsi_now > 70 else '#00d4aa' if rsi_now < 30 else '#a29bfe'
        ax2.text(len(data) - 1, rsi_now, f' {rsi_now:.0f}',
                color=rsi_color, fontsize=9, va='center', fontweight='bold')

        # Legende mit Signal-Erklaerung
        buy_patch = mpatches.Patch(color='#00ff88', label='▲ Kaufsignal (RSI<35 / MACD↑)')
        sell_patch = mpatches.Patch(color='#ff4757', label='▼ Verkaufssignal (RSI>70 / MACD↓)')
        fig.legend(handles=[buy_patch, sell_patch],
                  loc='lower center', ncol=2, facecolor='#1a1a2e',
                  edgecolor='#333355', labelcolor='white', fontsize=8,
                  bbox_to_anchor=(0.5, 0.01))

        plt.tight_layout(rect=[0, 0.05, 1, 0.96])

        # Als BytesIO speichern (fuer Discord)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                   facecolor='#1a1a2e', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as e:
        print(f"Chart-Fehler fuer {ticker}: {e}")
        return None


def generate_portfolio_chart(tickers: list, period: str = "1mo") -> io.BytesIO | None:
    """Erstellt einen Vergleichs-Chart fuer mehrere Aktien (prozentuale Veraenderung)"""
    try:
        import yfinance as yf
        fig, ax = plt.subplots(figsize=(14, 7), facecolor='#1a1a2e')
        ax.set_facecolor('#16213e')

        colors = ['#00d4aa', '#ffd700', '#ff6b6b', '#a29bfe', '#ff9ff3',
                  '#54a0ff', '#ff9f43', '#48dbfb', '#1dd1a1', '#ee5a24']

        valid_count = 0
        for i, ticker in enumerate(tickers[:10]):
            try:
                data = yf.Ticker(ticker).history(period=period)
                if data.empty or len(data) < 5:
                    continue
                normalized = (data['Close'] / data['Close'].iloc[0] - 1) * 100
                color = colors[i % len(colors)]
                ax.plot(range(len(normalized)), normalized,
                       label=ticker, color=color, linewidth=1.8)
                # Endwert beschriften
                ax.text(len(normalized) - 1, normalized.iloc[-1],
                       f' {ticker} ({normalized.iloc[-1]:+.1f}%)',
                       color=color, fontsize=8, va='center')
                valid_count += 1
            except Exception:
                pass

        if valid_count == 0:
            plt.close(fig)
            return None

        ax.axhline(0, color='white', linestyle='--', linewidth=1, alpha=0.4)
        ax.set_ylabel('Performance (%)', color='#aaaaaa')
        ax.tick_params(colors='#aaaaaa')
        ax.spines[:].set_color('#333355')
        ax.grid(color='#222244', linestyle='--', linewidth=0.5, alpha=0.7)
        fig.suptitle(f'Portfolio Performance ({period})',
                    color='white', fontsize=14, fontweight='bold')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=130, bbox_inches='tight',
                   facecolor='#1a1a2e', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as e:
        print(f"Portfolio-Chart Fehler: {e}")
        return None
