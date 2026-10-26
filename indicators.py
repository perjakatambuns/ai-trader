import math
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def get_pivot_points(df: pd.DataFrame) -> Dict[str, float]:
    """Calculates Standard Floor Pivot Points from the most recent completed candle"""
    if len(df) < 2:
        return {"pivot": 0.0, "r1": 0.0, "s1": 0.0, "r2": 0.0, "s2": 0.0}
    last = df.iloc[-2]
    h, l, c = float(last['high']), float(last['low']), float(last['close'])
    pivot = (h + l + c) / 3.0
    r1 = (2 * pivot) - l
    s1 = (2 * pivot) - h
    r2 = pivot + (h - l)
    s2 = pivot - (h - l)
    return {
        "pivot": round(pivot, 5),
        "r1": round(r1, 5),
        "s1": round(s1, 5),
        "r2": round(r2, 5),
        "s2": round(s2, 5)
    }

def get_market_sessions() -> Dict[str, Any]:
    """
    Computes current market session status and clocks in WIB (UTC+7) and UTC.
    London: 14:00 - 18:00 WIB (priority)
    New York: 19:00 - 23:00 WIB (priority)
    Tokyo/Asian: 07:00 - 14:00 WIB
    """
    utc_now = datetime.now(timezone.utc)
    wib_now = utc_now + timedelta(hours=7)
    hour_wib = wib_now.hour + (wib_now.minute / 60.0)

    is_tokyo = (7.0 <= hour_wib < 14.0)
    is_london = (14.0 <= hour_wib < 18.0)
    is_new_york = (19.0 <= hour_wib < 23.0)
    is_overlap = (19.0 <= hour_wib < 21.0) # London - NY overlap

    active_sessions = []
    if is_tokyo: active_sessions.append("Asian (Tokyo)")
    if is_london: active_sessions.append("London (Active)")
    if is_new_york: active_sessions.append("New York (Active)")
    if not active_sessions:
        active_sessions.append("Inter-Session / Quiet Market")

    return {
        "wib_time": wib_now.strftime("%H:%M:%S WIB"),
        "utc_time": utc_now.strftime("%H:%M:%S UTC"),
        "active_sessions": active_sessions,
        "is_priority_trading_hours": (is_london or is_new_york),
        "is_london": is_london,
        "is_new_york": is_new_york,
        "is_tokyo": is_tokyo,
        "is_overlap": is_overlap,
        "description": "High liquidity session" if (is_london or is_new_york) else "Lower volatility session"
    }

def analyze_timeframe(df: pd.DataFrame, timeframe_name: str) -> Dict[str, Any]:
    if df is None or len(df) < 15:
        return {"timeframe": timeframe_name, "error": "Insufficient data"}

    close = df['close']
    ema20 = calculate_ema(close, 20)
    ema50 = calculate_ema(close, 50)
    ema200 = calculate_ema(close, 200) if len(df) >= 200 else calculate_ema(close, len(df))
    rsi = calculate_rsi(close, 14)
    atr = calculate_atr(df, 14)

    curr_close = float(close.iloc[-1])
    curr_ema20 = float(ema20.iloc[-1])
    curr_ema50 = float(ema50.iloc[-1])
    curr_ema200 = float(ema200.iloc[-1])
    curr_rsi = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50.0
    curr_atr = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else (curr_close * 0.001)

    # Trend determination
    if curr_close > curr_ema200 and curr_ema20 > curr_ema50:
        trend = "Strong Bullish"
    elif curr_close > curr_ema200:
        trend = "Bullish"
    elif curr_close < curr_ema200 and curr_ema20 < curr_ema50:
        trend = "Strong Bearish"
    elif curr_close < curr_ema200:
        trend = "Bearish"
    else:
        trend = "Consolidating / Neutral"

    # Support / Resistance swing levels
    pivots = get_pivot_points(df)

    # RSI condition
    rsi_status = "Neutral"
    if curr_rsi <= 32:
        rsi_status = "Oversold (Bullish Reversal Potential)"
    elif curr_rsi >= 68:
        rsi_status = "Overbought (Bearish Pullback Potential)"

    return {
        "timeframe": timeframe_name,
        "current_price": round(curr_close, 5),
        "trend": trend,
        "ema20": round(curr_ema20, 5),
        "ema50": round(curr_ema50, 5),
        "ema200": round(curr_ema200, 5),
        "rsi": round(curr_rsi, 2),
        "rsi_status": rsi_status,
        "atr": round(curr_atr, 5),
        "pivots": pivots,
        "high": round(float(df['high'].max()), 5),
        "low": round(float(df['low'].min()), 5)
    }

_DXY_CACHE: Dict[str, Any] = {}
_DXY_CACHE_TIME: float = 0.0
_DXY_TTL: float = 60.0

def get_dollar_index_data(base_symbol: str = "XAUUSD") -> Dict[str, Any]:
    """
    Fetches real-time Dollar Index (DXY / DX-Y.NYB) and evaluates its macro momentum
    and correlation effect on the trading pair. Uses 60s in-memory cache to ensure instant speed.
    """
    global _DXY_CACHE, _DXY_CACHE_TIME
    now_ts = time.time()
    sym_key = base_symbol.upper()

    if _DXY_CACHE and (now_ts - _DXY_CACHE_TIME < _DXY_TTL):
        base_cached = dict(_DXY_CACHE)
        # Update symbol-specific impact note if needed
        dxy_price = base_cached.get("price", 101.95)
        dxy_change_pct = base_cached.get("change_pct", 0.05)
        trend = base_cached.get("trend", "Neutral")
    else:
        dxy_price = 101.95
        dxy_change_pct = 0.05
        trend = "Neutral"

        try:
            import yfinance as yf
            ticker = yf.Ticker("DX-Y.NYB")
            hist = ticker.history(period="5d", interval="1h")
            if hist is not None and len(hist) >= 5:
                close_series = hist['Close']
                dxy_price = round(float(close_series.iloc[-1]), 3)
                prev_close = float(close_series.iloc[-24]) if len(close_series) >= 24 else float(close_series.iloc[0])
                dxy_change_pct = round(((dxy_price - prev_close) / prev_close) * 100, 2)

                ema20 = float(calculate_ema(close_series, 20).iloc[-1])
                ema50 = float(calculate_ema(close_series, 50).iloc[-1]) if len(close_series) >= 50 else ema20

                if dxy_price > ema20 and dxy_change_pct > 0.1:
                    trend = "Strong Bullish"
                elif dxy_price > ema20:
                    trend = "Bullish / Penguatan"
                elif dxy_price < ema20 and dxy_change_pct < -0.1:
                    trend = "Strong Bearish"
                elif dxy_price < ema20:
                    trend = "Bearish / Pelemahan"
                else:
                    trend = "Sideways / Netral"
                
                _DXY_CACHE = {
                    "price": dxy_price,
                    "change_pct": dxy_change_pct,
                    "trend": trend
                }
                _DXY_CACHE_TIME = now_ts
        except Exception as e:
            print(f"[Indicators] DXY fetch notice: {e}")

    # Correlation impact note
    sym = base_symbol.upper()
    if "XAU" in sym or "GOLD" in sym:
        if "Bullish" in trend:
            impact_note = f"DXY menguat ({dxy_price}, {dxy_change_pct:+0.2f}%): Memberikan tekanan jual (bearish pressure) pada Emas/Gold."
        elif "Bearish" in trend:
            impact_note = f"DXY melemah ({dxy_price}, {dxy_change_pct:+0.2f}%): Membuka ruang rally bullish signifikan untuk Emas/Gold."
        else:
            impact_note = f"DXY bergerak netral ({dxy_price}): Sentimen inflasi & S/R teknikal menjadi penggerak utama."
    elif "EUR" in sym or "GBP" in sym or "AUD" in sym:
        if "Bullish" in trend:
            impact_note = f"DXY menguat ({dxy_price}, {dxy_change_pct:+0.2f}%): Koreksi turun pada mata uang mayor."
        else:
            impact_note = f"DXY melemah ({dxy_price}, {dxy_change_pct:+0.2f}%): Dorongan apresiasi bagi mata uang mayor."
    elif "JPY" in sym:
        if "Bullish" in trend:
            impact_note = f"DXY menguat ({dxy_price}): Mendorong kenaikan pair USDJPY."
        else:
            impact_note = f"DXY melemah ({dxy_price}): Memicu penguatan Yen / penurunan USDJPY."
    else:
        impact_note = f"Index Dollar saat ini berada di level {dxy_price} ({dxy_change_pct:+0.2f}%)."

    return {
        "price": dxy_price,
        "change_pct": dxy_change_pct,
        "trend": trend,
        "impact_note": impact_note,
        "formatted": f"DXY {dxy_price} ({dxy_change_pct:+0.2f}%)"
    }

def compute_quantitative_matrix(candles_d1: pd.DataFrame, candles_h1: pd.DataFrame, candles_m30: pd.DataFrame, candles_m5: pd.DataFrame, base_symbol: str = "XAUUSD") -> Dict[str, Any]:
    """
    Computes complete multi-timeframe quantitative matrix (D1, H1, M30, M5) + Dollar Index (DXY)
    """
    d1_metrics = analyze_timeframe(candles_d1, "D1")
    h1_metrics = analyze_timeframe(candles_h1, "H1")
    m30_metrics = analyze_timeframe(candles_m30, "M30")
    m5_metrics = analyze_timeframe(candles_m5, "M5")
    sessions = get_market_sessions()
    dxy = get_dollar_index_data(base_symbol)

    return {
        "sessions": sessions,
        "dxy": dxy,
        "d1": d1_metrics,
        "h1": h1_metrics,
        "m30": m30_metrics,
        "m5": m5_metrics,
        "macro_bias": d1_metrics.get("trend", "Neutral"),
        "setup_bias": h1_metrics.get("trend", "Neutral"),
        "trigger_bias": m5_metrics.get("trend", "Neutral")
    }
