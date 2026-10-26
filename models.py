from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, JSON, Enum
from database import Base, engine

class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    llm_provider = Column(String(50), default="openai") # 'openai', 'claude'
    llm_api_key = Column(Text, default="")
    llm_base_url = Column(String(255), default="")
    llm_model = Column(String(100), default="gpt-4o")
    mt5_account = Column(String(100), default="")
    mt5_password = Column(String(255), default="")
    mt5_server = Column(String(100), default="HFMarkets-Demo")
    mt5_path = Column(String(255), default="")
    default_spread_pips = Column(Float, default=1.4)
    max_risk_percentage = Column(Float, default=1.0)
    news_config = Column(JSON, default=lambda: {
        "forex_factory": True,
        "financialjuice": True,
        "forex_live": True,
        "yahoo_finance": True,
        "google_news": True,
        "msn_money": True,
        "finnhub_active": False,
        "finnhub_api_key": "",
        "newsapi_active": False,
        "newsapi_api_key": ""
    })
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TradingSymbol(Base):
    __tablename__ = "trading_symbols"

    id = Column(Integer, primary_key=True, index=True)
    mt5_symbol = Column(String(50), unique=True, nullable=False)
    base_symbol = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    pip_size = Column(Float, default=0.0001)

class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String(50), nullable=False)
    account_balance = Column(Float, nullable=False, default=1000.0)
    action = Column(String(20), nullable=False) # 'BUY_LIMIT', 'SELL_LIMIT', 'WAIT'
    entry_price = Column(Float, default=0.0)
    stop_loss = Column(Float, default=0.0)
    take_profit = Column(Float, default=0.0)
    calculated_lot = Column(Float, default=0.01)
    risk_percentage = Column(Float, default=1.0)
    confidence_score = Column(Integer, default=80)
    risk_reward_ratio = Column(String(20), default="1:2.0")
    ai_summary = Column(Text, default="")
    news_summary = Column(Text, default="")
    seasonality_note = Column(Text, default="")
    execution_status = Column(String(20), default="PENDING_USER") # 'PENDING_USER', 'EXECUTED', 'REJECTED', 'EXPIRED'
    mt5_ticket_id = Column(String(100), nullable=True)

# ----------------- SQLite Caching Models for Static Historical Data ----------------- #

class SeasonalityHistoryCache(Base):
    """
    Stores 1-year historical seasonality bias per symbol and calendar date.
    Static data: Never changes for a given calendar day.
    """
    __tablename__ = "seasonality_cache"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), index=True, nullable=False)
    calendar_date = Column(String(20), index=True, nullable=False) # e.g. "2026-10-20"
    date_reference = Column(String(20)) # e.g. "2025-10-20"
    seasonal_bias = Column(String(255))
    avg_change_pct = Column(Float, default=0.0)
    note = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)

class EconomicCalendarCache(Base):
    """
    Stores Forex Factory weekly economic calendar events in SQLite.
    Static data: Weekly schedule is preserved, refreshed every 4 hours.
    """
    __tablename__ = "economic_calendar_cache"

    id = Column(Integer, primary_key=True, index=True)
    week_key = Column(String(50), unique=True, index=True, nullable=False) # e.g. "2026-W42"
    events_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

class MarketCandleCache(Base):
    """
    Stores historical closed candle bars per symbol and timeframe.
    Only the latest open candle changes in realtime; past closed candles are read from SQLite.
    """
    __tablename__ = "market_candle_cache"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), index=True, nullable=False)
    timeframe = Column(String(10), index=True, nullable=False) # D1, H1, M30, M5
    candles_json = Column(Text, nullable=False) # JSON list of OHLCV bars
    last_candle_time = Column(String(50))
    updated_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Auto-migration: check if columns exist in app_settings
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE app_settings ADD COLUMN llm_base_url VARCHAR(255) DEFAULT ''"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE app_settings ADD COLUMN mt5_path VARCHAR(255) DEFAULT ''"))
            conn.commit()
        except Exception:
            pass

    # Seed default symbols if empty
    from database import SessionLocal
    db = SessionLocal()
    try:
        count = db.query(TradingSymbol).count()
        if count == 0:
            default_symbols = [
                TradingSymbol(mt5_symbol="XAUUSDc", base_symbol="XAUUSD", display_name="Gold (Cent Account)", is_active=True, pip_size=0.01),
                TradingSymbol(mt5_symbol="EURUSDc", base_symbol="EURUSD", display_name="EUR/USD (Cent Account)", is_active=True, pip_size=0.0001),
                TradingSymbol(mt5_symbol="USDJPYc", base_symbol="USDJPY", display_name="USD/JPY (Cent Account)", is_active=True, pip_size=0.01),
                TradingSymbol(mt5_symbol="GBPUSDc", base_symbol="GBPUSD", display_name="GBP/USD (Cent Account)", is_active=True, pip_size=0.0001),
                TradingSymbol(mt5_symbol="XAUUSD", base_symbol="XAUUSD", display_name="Gold (Standard)", is_active=True, pip_size=0.01),
                TradingSymbol(mt5_symbol="EURUSD", base_symbol="EURUSD", display_name="EUR/USD (Standard)", is_active=True, pip_size=0.0001),
            ]
            db.add_all(default_symbols)
            db.commit()
            print("[Database] Seeded default trading symbols.")
            
        settings = db.query(AppSettings).first()
        from config import load_config
        conf = load_config()
        app_conf = conf.get("app_settings", {})
        if not settings:
            new_settings = AppSettings(
                llm_provider=app_conf.get("llm_provider", "openai"),
                llm_model=app_conf.get("llm_model", "gpt-4o"),
                llm_api_key=app_conf.get("llm_api_key", ""),
                llm_base_url=app_conf.get("llm_base_url", ""),
                mt5_account=app_conf.get("mt5_account", ""),
                mt5_password=app_conf.get("mt5_password", ""),
                mt5_server=app_conf.get("mt5_server", "HFMarkets-Demo"),
                mt5_path=app_conf.get("mt5_path", ""),
                default_spread_pips=app_conf.get("default_spread_pips", 1.4),
                max_risk_percentage=app_conf.get("max_risk_percentage", 1.0)
            )
            if "news_config" in app_conf:
                new_settings.news_config = app_conf["news_config"]
            db.add(new_settings)
            db.commit()
            print("[Database] Initialized settings from config.json.")
        else:
            changed = False
            if not settings.llm_api_key and app_conf.get("llm_api_key"):
                settings.llm_api_key = app_conf.get("llm_api_key")
                changed = True
            if not getattr(settings, "llm_base_url", "") and app_conf.get("llm_base_url"):
                settings.llm_base_url = app_conf.get("llm_base_url")
                changed = True
            if not getattr(settings, "mt5_path", "") and app_conf.get("mt5_path"):
                settings.mt5_path = app_conf.get("mt5_path")
                changed = True
            if not settings.mt5_password and app_conf.get("mt5_password"):
                settings.mt5_password = app_conf.get("mt5_password")
                changed = True
            if changed:
                db.commit()
                print("[Database] Restored credentials from config.json into database.")
    finally:
        db.close()
