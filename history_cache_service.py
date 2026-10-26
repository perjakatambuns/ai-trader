import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
from database import SessionLocal
from models import SeasonalityHistoryCache, EconomicCalendarCache, MarketCandleCache

class HistoryCacheService:
    """
    Manages persistent SQLite caching for non-changing historical market data:
    1. Seasonality Analysis (Historical calendar data 1-2 years ago)
    2. Weekly Economic Calendar (Forex Factory)
    3. Multi-timeframe Closed Candles (D1, H1, M30, M5)
    """

    # ----------------- 1. Seasonality Cache ----------------- #

    def get_seasonality(self, symbol: str, calendar_date: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rec = db.query(SeasonalityHistoryCache).filter(
                SeasonalityHistoryCache.symbol == symbol.upper(),
                SeasonalityHistoryCache.calendar_date == calendar_date
            ).first()
            if rec:
                return {
                    "date_reference": rec.date_reference,
                    "seasonal_bias": rec.seasonal_bias,
                    "avg_change_pct": rec.avg_change_pct,
                    "note": rec.note,
                    "from_cache": True
                }
        except Exception as e:
            print(f"[HistoryCache] Error reading seasonality cache: {e}")
        finally:
            db.close()
        return None

    def save_seasonality(self, symbol: str, calendar_date: str, date_reference: str, seasonal_bias: str, avg_change_pct: float, note: str):
        db = SessionLocal()
        try:
            sym_key = symbol.upper()
            rec = db.query(SeasonalityHistoryCache).filter(
                SeasonalityHistoryCache.symbol == sym_key,
                SeasonalityHistoryCache.calendar_date == calendar_date
            ).first()
            if not rec:
                rec = SeasonalityHistoryCache(
                    symbol=sym_key,
                    calendar_date=calendar_date,
                    date_reference=date_reference,
                    seasonal_bias=seasonal_bias,
                    avg_change_pct=avg_change_pct,
                    note=note,
                    updated_at=datetime.utcnow()
                )
                db.add(rec)
            else:
                rec.date_reference = date_reference
                rec.seasonal_bias = seasonal_bias
                rec.avg_change_pct = avg_change_pct
                rec.note = note
                rec.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[HistoryCache] Error saving seasonality cache: {e}")
        finally:
            db.close()

    # ----------------- 2. Economic Calendar Cache ----------------- #

    def get_economic_calendar(self, week_key: str, max_age_hours: float = 4.0) -> Optional[List[Dict[str, Any]]]:
        db = SessionLocal()
        try:
            rec = db.query(EconomicCalendarCache).filter(
                EconomicCalendarCache.week_key == week_key
            ).first()
            if rec:
                age_hours = (datetime.utcnow() - rec.updated_at).total_seconds() / 3600.0
                if age_hours <= max_age_hours:
                    data = json.loads(rec.events_json)
                    return data
        except Exception as e:
            print(f"[HistoryCache] Error reading calendar cache: {e}")
        finally:
            db.close()
        return None

    def save_economic_calendar(self, week_key: str, events: List[Dict[str, Any]]):
        db = SessionLocal()
        try:
            rec = db.query(EconomicCalendarCache).filter(
                EconomicCalendarCache.week_key == week_key
            ).first()
            json_str = json.dumps(events)
            if not rec:
                rec = EconomicCalendarCache(
                    week_key=week_key,
                    events_json=json_str,
                    updated_at=datetime.utcnow()
                )
                db.add(rec)
            else:
                rec.events_json = json_str
                rec.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[HistoryCache] Error saving calendar cache: {e}")
        finally:
            db.close()

    # ----------------- 3. Market Candles Cache & Incremental Merge ----------------- #

    def get_cached_candles(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        db = SessionLocal()
        try:
            rec = db.query(MarketCandleCache).filter(
                MarketCandleCache.symbol == symbol.upper(),
                MarketCandleCache.timeframe == timeframe.upper()
            ).first()
            if rec and rec.candles_json:
                data = json.loads(rec.candles_json)
                if data:
                    df = pd.DataFrame(data)
                    df['time'] = pd.to_datetime(df['time'])
                    return df
        except Exception as e:
            print(f"[HistoryCache] Error reading candle cache: {e}")
        finally:
            db.close()
        return None

    def get_candle_cache_age_seconds(self, symbol: str, timeframe: str) -> float:
        db = SessionLocal()
        try:
            rec = db.query(MarketCandleCache).filter(
                MarketCandleCache.symbol == symbol.upper(),
                MarketCandleCache.timeframe == timeframe.upper()
            ).first()
            if rec and rec.updated_at:
                return (datetime.utcnow() - rec.updated_at).total_seconds()
        except Exception:
            pass
        finally:
            db.close()
        return 999999.0

    def merge_and_save_candles(self, symbol: str, timeframe: str, realtime_df: pd.DataFrame, max_count: int = 100) -> pd.DataFrame:
        """
        Merges newly fetched realtime bars with historical closed bars from SQLite.
        Drops duplicate timestamps and preserves full history.
        """
        if realtime_df is None or realtime_df.empty:
            cached = self.get_cached_candles(symbol, timeframe)
            if cached is not None and not cached.empty:
                return cached.tail(max_count)
            return pd.DataFrame()

        # Clean realtime_df
        realtime_df = realtime_df.copy()
        realtime_df['time'] = pd.to_datetime(realtime_df['time'])

        cached_df = self.get_cached_candles(symbol, timeframe)
        if cached_df is not None and not cached_df.empty:
            # Combine historical closed bars with latest realtime bars
            combined = pd.concat([cached_df, realtime_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['time'], keep='last')
            combined = combined.sort_values(by='time').tail(max_count).reset_index(drop=True)
        else:
            combined = realtime_df.sort_values(by='time').tail(max_count).reset_index(drop=True)

        # Save merged dataframe back to SQLite
        db = SessionLocal()
        try:
            sym_key = symbol.upper()
            tf_key = timeframe.upper()
            rec = db.query(MarketCandleCache).filter(
                MarketCandleCache.symbol == sym_key,
                MarketCandleCache.timeframe == tf_key
            ).first()

            # Format time as ISO string for JSON serialization
            save_df = combined.copy()
            save_df['time'] = save_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
            json_records = save_df.to_dict(orient='records')
            json_str = json.dumps(json_records)
            last_time = str(save_df['time'].iloc[-1]) if not save_df.empty else ""

            if not rec:
                rec = MarketCandleCache(
                    symbol=sym_key,
                    timeframe=tf_key,
                    candles_json=json_str,
                    last_candle_time=last_time,
                    updated_at=datetime.utcnow()
                )
                db.add(rec)
            else:
                rec.candles_json = json_str
                rec.last_candle_time = last_time
                rec.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[HistoryCache] Error saving candle cache for {symbol} {timeframe}: {e}")
        finally:
            db.close()

        return combined

history_cache = HistoryCacheService()
