import os
import json
import concurrent.futures
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import load_config, save_config, update_password, get_auth_config
from auth import verify_password, create_access_token, get_current_user
from database import get_db
from models import init_db, AppSettings, TradingSymbol, AnalysisHistory
from mt5_service import mt5_service
from indicators import compute_quantitative_matrix, get_market_sessions
from news_service import news_service
from risk_engine import risk_engine
from llm_service import llm_service

app = FastAPI(title="AI Trading Copilot - HFM MT5", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def auto_expire_pending_orders_loop():
    """
    Background worker: checks every 60 seconds if any AI pending order has remained
    un-triggered for > 6 hours. If so, automatically removes/cancels it in MT5.
    """
    await asyncio.sleep(10) # Initial startup buffer
    while True:
        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                mt5_service.check_and_expire_pending_orders(db_session=db, max_age_hours=6.0)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[AutoExpire Worker] Error in check loop: {e}")
        await asyncio.sleep(60)

# Initialize database schema and seeds on startup
@app.on_event("startup")
async def on_startup():
    init_db()
    # Connect MT5 on startup with configured credentials
    conf = load_config()
    st = conf.get("app_settings", {})
    mt5_service.connect(
        account=st.get("mt5_account"),
        password=st.get("mt5_password"),
        server=st.get("mt5_server")
    )
    # Launch background auto-expire loop for orders > 6 hours
    asyncio.create_task(auto_expire_pending_orders_loop())

# ----------------- Auth Models & Endpoints ----------------- #

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@app.post("/api/auth/login")
def login(req: LoginRequest):
    auth_conf = get_auth_config()
    expected_user = auth_conf.get("username", "admin")
    stored_pass = auth_conf.get("password", "password123")
    
    if req.username != expected_user or not verify_password(req.password, stored_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau Password salah."
        )
    
    token = create_access_token({"sub": req.username})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "username": req.username
    }

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"authenticated": True, "username": user["username"]}

@app.post("/api/auth/change-password")
def change_pass(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    auth_conf = get_auth_config()
    stored_pass = auth_conf.get("password", "password123")
    
    if not verify_password(req.current_password, stored_pass):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password saat ini tidak cocok."
        )
    
    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password baru minimal 6 karakter."
        )
    
    success = update_password(req.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gagal menyimpan password baru ke config."
        )
    
    return {"success": True, "message": "Password berhasil diperbarui di config.json."}

# ----------------- System Status Endpoints ----------------- #

@app.get("/api/status")
def get_system_status(db: Session = Depends(get_db)):
    settings = db.query(AppSettings).first()
    acc_id = settings.mt5_account if settings else None
    acc_pwd = settings.mt5_password if settings else None
    acc_srv = settings.mt5_server if settings else None
    acc_path = getattr(settings, "mt5_path", None) if settings else None
    
    account_info = mt5_service.get_account_info(account=acc_id, password=acc_pwd, server=acc_srv, path=acc_path)
    sessions = get_market_sessions()
    from indicators import get_dollar_index_data
    dxy = get_dollar_index_data("XAUUSD")
    
    return {
        "mt5": account_info,
        "sessions": sessions,
        "dxy": dxy,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/mt5/account")
def get_mt5_account_direct(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    settings = db.query(AppSettings).first()
    acc_id = settings.mt5_account if settings else None
    acc_pwd = settings.mt5_password if settings else None
    acc_srv = settings.mt5_server if settings else None
    acc_path = getattr(settings, "mt5_path", None) if settings else None
    
    account_info = mt5_service.get_account_info(account=acc_id, password=acc_pwd, server=acc_srv, path=acc_path)
    return {"success": account_info.get("connected", False), "account": account_info}

@app.post("/api/mt5/reconnect")
def reconnect_mt5_direct(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    settings = db.query(AppSettings).first()
    acc_id = settings.mt5_account if settings else None
    acc_pwd = settings.mt5_password if settings else None
    acc_srv = settings.mt5_server if settings else None
    acc_path = getattr(settings, "mt5_path", None) if settings else None
    
    res = mt5_service.connect(account=acc_id, password=acc_pwd, server=acc_srv, path=acc_path)
    return res

# ----------------- Symbols Endpoints ----------------- #

class SymbolCreateRequest(BaseModel):
    mt5_symbol: str
    base_symbol: str
    display_name: str
    pip_size: float = 0.0001
    is_active: bool = True

class SymbolUpdateRequest(BaseModel):
    base_symbol: str
    display_name: str
    pip_size: float
    is_active: bool

@app.get("/api/symbols")
def get_symbols(db: Session = Depends(get_db)):
    symbols = db.query(TradingSymbol).order_by(TradingSymbol.is_active.desc(), TradingSymbol.id.asc()).all()
    return symbols

@app.post("/api/symbols")
def create_symbol(req: SymbolCreateRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    existing = db.query(TradingSymbol).filter(TradingSymbol.mt5_symbol == req.mt5_symbol.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Simbol MT5 ini sudah terdaftar.")
    
    sym = TradingSymbol(
        mt5_symbol=req.mt5_symbol.strip(),
        base_symbol=req.base_symbol.strip().upper(),
        display_name=req.display_name.strip(),
        pip_size=req.pip_size,
        is_active=req.is_active
    )
    db.add(sym)
    db.commit()
    db.refresh(sym)
    return sym

@app.patch("/api/symbols/{symbol_id}/toggle")
def toggle_symbol(symbol_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    sym = db.query(TradingSymbol).filter(TradingSymbol.id == symbol_id).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Simbol tidak ditemukan.")
    sym.is_active = not sym.is_active
    db.commit()
    return {"success": True, "id": sym.id, "is_active": sym.is_active}

@app.delete("/api/symbols/{symbol_id}")
def delete_symbol(symbol_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    sym = db.query(TradingSymbol).filter(TradingSymbol.id == symbol_id).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Simbol tidak ditemukan.")
    db.delete(sym)
    db.commit()
    return {"success": True, "message": "Simbol berhasil dihapus."}

# ----------------- Analysis Room Endpoint ----------------- #

class AnalyzeRequest(BaseModel):
    mt5_symbol: Optional[str] = None
    symbol: Optional[str] = None

@app.post("/api/analyze")
def run_analysis(req: AnalyzeRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    target_symbol = (req.mt5_symbol or req.symbol or "").strip()
    if not target_symbol:
        raise HTTPException(status_code=400, detail="Pilih atau masukkan simbol trading terlebih dahulu.")

    # 1. Lookup symbol in whitelist (support base and mt5 symbol)
    sym = db.query(TradingSymbol).filter(
        (TradingSymbol.mt5_symbol == target_symbol) | (TradingSymbol.base_symbol == target_symbol)
    ).first()

    if not sym:
        # Auto-create active symbol so user is never blocked
        base = target_symbol.rstrip("cm.").upper()
        if not base:
            base = target_symbol.upper()
        pip = 0.01 if ("JPY" in base or "XAU" in base) else 0.0001
        sym = TradingSymbol(mt5_symbol=target_symbol, base_symbol=base, display_name=target_symbol, is_active=True, pip_size=pip)
        db.add(sym)
        db.commit()
        db.refresh(sym)
    elif not sym.is_active:
        sym.is_active = True
        db.commit()
        db.refresh(sym)
    
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings()
        db.add(settings)
        db.commit()

    # 2. Get MT5 Account Info for precise lot sizing
    acc_info = mt5_service.get_account_info(
        account=settings.mt5_account,
        password=settings.mt5_password,
        server=settings.mt5_server
    )
    account_balance = acc_info.get("balance", 600.0)
    account_currency = acc_info.get("currency", "USC")
    broker_symbol_info = mt5_service.get_symbol_info(sym.mt5_symbol)

    # 3. Pull Multi-Timeframe Candles (D1, H1, M30, M5), Seasonality, & News fully parallelized
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_d1 = executor.submit(mt5_service.get_candles, sym.mt5_symbol, sym.base_symbol, "D1", 100)
        f_h1 = executor.submit(mt5_service.get_candles, sym.mt5_symbol, sym.base_symbol, "H1", 100)
        f_m30 = executor.submit(mt5_service.get_candles, sym.mt5_symbol, sym.base_symbol, "M30", 100)
        f_m5 = executor.submit(mt5_service.get_candles, sym.mt5_symbol, sym.base_symbol, "M5", 100)
        f_seasonality = executor.submit(mt5_service.get_seasonality_candles, sym.base_symbol, 100)
        f_news = executor.submit(news_service.get_aggregated_news, sym.base_symbol, settings.news_config)

        try:
            candles_d1 = f_d1.result(timeout=6.0)
        except Exception as e:
            print(f"[Analysis] D1 candles timeout/fallback: {e}")
            candles_d1 = mt5_service._generate_synthetic_candles(sym.base_symbol, 100, "D1")

        try:
            candles_h1 = f_h1.result(timeout=6.0)
        except Exception as e:
            print(f"[Analysis] H1 candles timeout/fallback: {e}")
            candles_h1 = mt5_service._generate_synthetic_candles(sym.base_symbol, 100, "H1")

        try:
            candles_m30 = f_m30.result(timeout=6.0)
        except Exception as e:
            print(f"[Analysis] M30 candles timeout/fallback: {e}")
            candles_m30 = mt5_service._generate_synthetic_candles(sym.base_symbol, 100, "M30")

        try:
            candles_m5 = f_m5.result(timeout=6.0)
        except Exception as e:
            print(f"[Analysis] M5 candles timeout/fallback: {e}")
            candles_m5 = mt5_service._generate_synthetic_candles(sym.base_symbol, 100, "M5")

        try:
            seasonality = f_seasonality.result(timeout=6.0)
        except Exception as e:
            print(f"[Analysis] Seasonality timeout/fallback: {e}")
            seasonality = {"seasonal_bias": "Neutral", "avg_change_pct": 0.0, "note": "Historical data steady"}

        try:
            news_data = f_news.result(timeout=6.0)
        except Exception as e:
            print(f"[Analysis] News timeout/fallback: {e}")
            news_data = {"calendar_status": "Normal market conditions", "has_imminent_high_impact": False, "imminent_events": [], "headlines": [], "headlines_summary": "- Steady market."}

    # 4. Compute Quantitative Matrix (EMA, RSI, S/R, Sessions, DXY)
    matrix = compute_quantitative_matrix(candles_d1, candles_h1, candles_m30, candles_m5, base_symbol=sym.base_symbol)

    # 5. Call LLM (OpenAI / Claude / Quantitative AI) with custom base_url support
    effective_api_key = settings.llm_api_key
    if not effective_api_key:
        conf = load_config()
        effective_api_key = conf.get("app_settings", {}).get("llm_api_key", "") or os.getenv("OPENAI_API_KEY", "")
        if effective_api_key:
            settings.llm_api_key = effective_api_key
            try:
                db.commit()
            except Exception:
                pass

    effective_base_url = getattr(settings, "llm_base_url", "")
    if not effective_base_url:
        conf = load_config()
        effective_base_url = conf.get("app_settings", {}).get("llm_base_url", "")

    app_settings_dict = {
        "llm_provider": settings.llm_provider,
        "llm_api_key": effective_api_key,
        "llm_base_url": effective_base_url,
        "llm_model": settings.llm_model
    }
    ai_result = llm_service.generate_trading_analysis(
        symbol=sym.mt5_symbol,
        base_symbol=sym.base_symbol,
        pip_size=sym.pip_size,
        quantitative_matrix=matrix,
        news_data=news_data,
        seasonality_data=seasonality,
        app_settings=app_settings_dict
    )

    action = ai_result.get("action", "WAIT")
    entry_price = ai_result.get("entry_price", matrix.get("m5", {}).get("current_price", 0.0))
    stop_loss = ai_result.get("stop_loss", 0.0)
    take_profit = ai_result.get("take_profit", 0.0)

    # 6. Apply HFM Spread Buffer (1.4 pips) if action is BUY/SELL
    if action in ["BUY_LIMIT", "SELL_LIMIT"] and stop_loss > 0:
        spread_adjusted = risk_engine.apply_spread_buffer(
            action=action,
            entry_price=entry_price,
            support_or_sl=stop_loss,
            resistance_or_tp=take_profit,
            pip_size=sym.pip_size,
            spread_pips=settings.default_spread_pips or 1.4
        )
        entry_price = spread_adjusted["entry_price"]
        stop_loss = spread_adjusted["stop_loss"]
        take_profit = spread_adjusted["take_profit"]

    # 7. Compute Anti-Margin Call Lot Size (Strict min 0.01 lot, calibrated for USC Cent balance)
    risk_pct = settings.max_risk_percentage or 1.0
    lot_calc = risk_engine.calculate_lot_size(
        account_balance=account_balance,
        risk_pct=risk_pct,
        entry_price=entry_price,
        stop_loss=stop_loss,
        symbol=sym.mt5_symbol,
        pip_size=sym.pip_size,
        account_currency=account_currency,
        broker_symbol_info=broker_symbol_info
    )

    # 9. Save log into analysis_history (status PENDING_USER)
    history_entry = AnalysisHistory(
        symbol=sym.mt5_symbol,
        account_balance=account_balance,
        action=action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        calculated_lot=lot_calc["calculated_lot"],
        risk_percentage=risk_pct,
        confidence_score=ai_result.get("confidence_score", 85),
        risk_reward_ratio=ai_result.get("risk_reward_ratio", "1:2.0"),
        ai_summary=ai_result.get("analysis_summary", ""),
        news_summary=news_data.get("headlines_summary", ""),
        seasonality_note=ai_result.get("seasonality_note", seasonality.get("note", "")),
        execution_status="PENDING_USER"
    )
    db.add(history_entry)
    db.commit()
    db.refresh(history_entry)

    wib_tz = timezone(timedelta(hours=7))
    ts = history_entry.timestamp
    if ts.tzinfo is None:
        ts_utc = ts.replace(tzinfo=timezone.utc)
    else:
        ts_utc = ts.astimezone(timezone.utc)
    ts_wib = ts_utc.astimezone(wib_tz)

    return {
        "history_id": history_entry.id,
        "symbol": sym.mt5_symbol,
        "display_name": sym.display_name,
        "action": action,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward_ratio": ai_result.get("risk_reward_ratio", "1:2.0"),
        "confidence_score": ai_result.get("confidence_score", 85),
        "lot_calculation": lot_calc,
        "analysis_summary": ai_result.get("analysis_summary", ""),
        "news_summary": news_data.get("headlines_summary", ""),
        "calendar_status": news_data.get("calendar_status", ""),
        "matrix": matrix,
        "timestamp": ts_utc.isoformat(),
        "time_gmt": ts_utc.strftime("%d/%m/%Y %H:%M:%S GMT"),
        "time_wib": ts_wib.strftime("%d/%m/%Y %H:%M:%S GMT+7")
    }

# ----------------- Order Execution Endpoints ----------------- #

class OrderExecuteRequest(BaseModel):
    history_id: int

@app.post("/api/order/execute")
def execute_order(req: OrderExecuteRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    item = db.query(AnalysisHistory).filter(AnalysisHistory.id == req.history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Riwayat analisa tidak ditemukan.")
    
    if item.execution_status == "EXECUTED":
        raise HTTPException(status_code=400, detail="Order ini sudah pernah dieksekusi sebelumnya.")

    if item.action == "WAIT":
        raise HTTPException(status_code=400, detail="Rekomendasi saat ini adalah WAIT. Tidak dapat memasang order.")

    # Send to MT5
    send_result = mt5_service.send_order(
        symbol=item.symbol,
        action=item.action,
        lot=item.calculated_lot,
        entry_price=item.entry_price,
        sl=item.stop_loss,
        tp=item.take_profit,
        comment="AI-Copilot"
    )

    if send_result.get("success"):
        item.execution_status = "EXECUTED"
        item.mt5_ticket_id = send_result.get("ticket")
        db.commit()
        return {
            "success": True,
            "ticket": send_result.get("ticket"),
            "message": send_result.get("message")
        }
    else:
        raise HTTPException(status_code=500, detail=send_result.get("message", "Gagal mengirim order ke MT5"))

@app.post("/api/order/reject")
def reject_order(req: OrderExecuteRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    item = db.query(AnalysisHistory).filter(AnalysisHistory.id == req.history_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Riwayat analisa tidak ditemukan.")
    item.execution_status = "REJECTED"
    db.commit()
    return {"success": True, "message": "Rekomendasi diabaikan."}

class CloseOrderRequest(BaseModel):
    ticket: str
    action_type: Optional[str] = "auto" # "close_position", "cancel_order", or "auto"

@app.post("/api/order/close")
def close_or_cancel_order(req: CloseOrderRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """
    Manual close or cancel endpoint for orders/positions from the Web UI.
    """
    ticket = str(req.ticket).strip()
    if not ticket:
        raise HTTPException(status_code=400, detail="Nomor tiket tidak boleh kosong.")

    if req.action_type == "cancel_order":
        res = mt5_service.cancel_pending_order(ticket, reason="Manual Cancel dari Web")
    elif req.action_type == "close_position":
        res = mt5_service.close_position(ticket)
    else:
        res = mt5_service.close_or_cancel_trade(ticket)

    # If successfully cancelled or closed, update DB status
    if res.get("success"):
        item = db.query(AnalysisHistory).filter(AnalysisHistory.mt5_ticket_id == ticket).first()
        if item:
            msg_lower = res.get("message", "").lower()
            if "batal" in msg_lower or "cancel" in msg_lower:
                item.execution_status = "CANCELLED"
            elif "tutup" in msg_lower or "close" in msg_lower:
                item.execution_status = "CLOSED_MANUAL"
            db.commit()
        return res
    else:
        raise HTTPException(status_code=400, detail=res.get("message", "Gagal memproses order di MT5."))

# ----------------- History & Journal Endpoint ----------------- #

@app.get("/api/history")
def get_history(limit: int = 50, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    records = db.query(AnalysisHistory).order_by(AnalysisHistory.timestamp.desc()).limit(limit).all()
    res = []
    wib_tz = timezone(timedelta(hours=7))
    for r in records:
        ts = r.timestamp
        if ts:
            if ts.tzinfo is None:
                ts_utc = ts.replace(tzinfo=timezone.utc)
            else:
                ts_utc = ts.astimezone(timezone.utc)
            gmt_str = ts_utc.strftime("%d/%m/%Y %H:%M:%S GMT")
            ts_wib = ts_utc.astimezone(wib_tz)
            wib_str = ts_wib.strftime("%d/%m/%Y %H:%M:%S GMT+7")
            iso_str = ts_utc.isoformat()
        else:
            gmt_str = "-"
            wib_str = "-"
            iso_str = ""

        res.append({
            "id": r.id,
            "timestamp": iso_str,
            "time_gmt": gmt_str,
            "time_wib": wib_str,
            "symbol": r.symbol,
            "account_balance": r.account_balance,
            "action": r.action,
            "entry_price": r.entry_price,
            "stop_loss": r.stop_loss,
            "take_profit": r.take_profit,
            "calculated_lot": r.calculated_lot,
            "risk_percentage": r.risk_percentage,
            "confidence_score": r.confidence_score,
            "risk_reward_ratio": r.risk_reward_ratio,
            "ai_summary": r.ai_summary,
            "news_summary": r.news_summary,
            "seasonality_note": r.seasonality_note,
            "execution_status": r.execution_status,
            "mt5_ticket_id": r.mt5_ticket_id
        })
    return res

@app.get("/api/trading/performance")
def get_trading_performance(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """
    Matches executed orders placed from this AI Copilot with MT5 trade deals/positions,
    calculates win rate, net profit/loss, and returns the trading history.
    """
    # 1. Fetch executed AI orders from AnalysisHistory
    executed_records = db.query(AnalysisHistory).filter(
        AnalysisHistory.execution_status == "EXECUTED"
    ).order_by(AnalysisHistory.timestamp.desc()).all()

    # Also include any records with non-empty mt5_ticket_id
    if not executed_records:
        executed_records = db.query(AnalysisHistory).filter(
            AnalysisHistory.mt5_ticket_id.isnot(None),
            AnalysisHistory.mt5_ticket_id != ""
        ).order_by(AnalysisHistory.timestamp.desc()).all()

    db_items = []
    for r in executed_records:
        db_items.append({
            "id": r.id,
            "ticket": r.mt5_ticket_id,
            "symbol": r.symbol,
            "action": r.action,
            "lot": r.calculated_lot,
            "entry_price": r.entry_price,
            "sl": r.stop_loss,
            "tp": r.take_profit,
            "timestamp": r.timestamp,
            "ai_summary": r.ai_summary
        })

    # 2. Get MT5 history and calculate matched performance stats
    res = mt5_service.get_trading_history_and_stats(db_items)
    return res

# ----------------- Settings Endpoints ----------------- #

class SettingsUpdateRequest(BaseModel):
    llm_provider: str
    llm_model: str
    llm_api_key: Optional[str] = ""
    llm_base_url: Optional[str] = ""
    mt5_account: Optional[str] = ""
    mt5_password: Optional[str] = ""
    mt5_server: Optional[str] = "HFMarkets-Demo"
    mt5_path: Optional[str] = ""
    default_spread_pips: float = 1.4
    max_risk_percentage: float = 1.0
    news_config: Dict[str, Any]
    db_config: Optional[Dict[str, Any]] = None

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)

    conf = load_config()
    db_conf = conf.get("database", {})
    app_conf = conf.get("app_settings", {})

    # Bi-directional sync: if DB empty but config.json has key, restore into DB
    if not settings.llm_api_key and app_conf.get("llm_api_key"):
        settings.llm_api_key = app_conf.get("llm_api_key")
        db.commit()
    elif settings.llm_api_key and not app_conf.get("llm_api_key"):
        conf["app_settings"]["llm_api_key"] = settings.llm_api_key
        save_config(conf)

    effective_key = settings.llm_api_key or app_conf.get("llm_api_key", "")
    if effective_key:
        masked_key = "********" + (effective_key[-4:] if len(effective_key) > 4 else "")
    else:
        masked_key = ""

    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_api_key_masked": masked_key,
        "has_llm_api_key": bool(effective_key),
        "llm_base_url": getattr(settings, "llm_base_url", "") or app_conf.get("llm_base_url", ""),
        "mt5_account": settings.mt5_account,
        "mt5_password_masked": "********" if settings.mt5_password else "",
        "mt5_server": settings.mt5_server,
        "mt5_path": getattr(settings, "mt5_path", "") or app_conf.get("mt5_path", ""),
        "default_spread_pips": settings.default_spread_pips,
        "max_risk_percentage": settings.max_risk_percentage,
        "news_config": settings.news_config,
        "database": {
            "type": db_conf.get("type", "sqlite"),
            "host": db_conf.get("host", "localhost"),
            "port": db_conf.get("port", 3306),
            "user": db_conf.get("user", "root"),
            "password_masked": "********" if db_conf.get("password") else "",
            "database": db_conf.get("database", "ai_trade")
        }
    }

@app.post("/api/settings")
def save_app_settings(req: SettingsUpdateRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings()
        db.add(settings)

    conf = load_config()
    settings.llm_provider = req.llm_provider
    settings.llm_model = req.llm_model
    if hasattr(settings, "llm_base_url"):
        settings.llm_base_url = (req.llm_base_url or "").strip()

    # Bulletproof API key preservation:
    # Only update if user explicitly provided a new unmasked key.
    # Empty string or masked string (contains '*') will NEVER wipe the saved key.
    new_llm_key = (req.llm_api_key or "").strip()
    if new_llm_key and "*" not in new_llm_key:
        if new_llm_key.lower() in ["clear", "delete", "hapus"]:
            settings.llm_api_key = ""
            conf["app_settings"]["llm_api_key"] = ""
        else:
            settings.llm_api_key = new_llm_key
            conf["app_settings"]["llm_api_key"] = new_llm_key
    elif not settings.llm_api_key and conf.get("app_settings", {}).get("llm_api_key"):
        # Restore if DB was empty
        settings.llm_api_key = conf["app_settings"]["llm_api_key"]
    elif settings.llm_api_key:
        conf["app_settings"]["llm_api_key"] = settings.llm_api_key

    if req.mt5_account is not None:
        settings.mt5_account = req.mt5_account.strip()

    # Preserve MT5 password if masked or untouched
    new_mt5_pass = (req.mt5_password or "").strip()
    if new_mt5_pass and "*" not in new_mt5_pass:
        settings.mt5_password = new_mt5_pass
        conf["app_settings"]["mt5_password"] = new_mt5_pass
    elif not settings.mt5_password and conf.get("app_settings", {}).get("mt5_password"):
        settings.mt5_password = conf["app_settings"]["mt5_password"]
    elif settings.mt5_password:
        conf["app_settings"]["mt5_password"] = settings.mt5_password

    if req.mt5_server is not None:
        settings.mt5_server = req.mt5_server.strip()
    if hasattr(settings, "mt5_path"):
        settings.mt5_path = (req.mt5_path or "").strip()

    settings.default_spread_pips = req.default_spread_pips
    settings.max_risk_percentage = req.max_risk_percentage
    settings.news_config = req.news_config
    db.commit()

    # Sync back to config.json
    conf["app_settings"]["llm_provider"] = settings.llm_provider
    conf["app_settings"]["llm_model"] = settings.llm_model
    conf["app_settings"]["llm_base_url"] = getattr(settings, "llm_base_url", "")
    conf["app_settings"]["mt5_account"] = settings.mt5_account
    conf["app_settings"]["mt5_server"] = settings.mt5_server
    conf["app_settings"]["mt5_path"] = getattr(settings, "mt5_path", "")
    conf["app_settings"]["default_spread_pips"] = settings.default_spread_pips
    conf["app_settings"]["max_risk_percentage"] = settings.max_risk_percentage
    conf["app_settings"]["news_config"] = settings.news_config

    if req.db_config:
        dbc = req.db_config
        conf["database"]["type"] = dbc.get("type", "sqlite")
        conf["database"]["host"] = dbc.get("host", "localhost")
        conf["database"]["port"] = int(dbc.get("port", 3306))
        conf["database"]["user"] = dbc.get("user", "root")
        db_pwd = (dbc.get("password") or "").strip()
        if db_pwd and "*" not in db_pwd:
            conf["database"]["password"] = db_pwd
        conf["database"]["database"] = dbc.get("database", "ai_trade")

    save_config(conf)

    # Reconnect MT5
    mt5_service.connect(
        account=settings.mt5_account,
        password=settings.mt5_password,
        server=settings.mt5_server,
        path=getattr(settings, "mt5_path", "")
    )

    return {"success": True, "message": "Pengaturan berhasil disimpan."}

class TestDBRequest(BaseModel):
    type: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: Optional[str] = ""
    database: str = "ai_trade"

@app.post("/api/settings/test-db")
def test_db_conn(req: TestDBRequest, user: dict = Depends(get_current_user)):
    if req.type == "sqlite":
        return {"success": True, "message": "SQLite lokal siap digunakan."}
    try:
        from urllib.parse import quote_plus
        from sqlalchemy import create_engine, text
        pwd = req.password or ""
        if pwd == "********":
            # load from current config
            conf = load_config()
            pwd = conf.get("database", {}).get("password", "")
        safe_pass = quote_plus(str(pwd))
        test_url = f"mysql+pymysql://{req.user}:{safe_pass}@{req.host}:{req.port}/{req.database}?charset=utf8mb4"
        test_engine = create_engine(test_url, connect_args={"connect_timeout": 5})
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"success": True, "message": f"Koneksi ke Remote MySQL ({req.host}:{req.port}/{req.database}) berhasil!"}
    except Exception as e:
        return {"success": False, "message": f"Gagal terhubung ke Remote MySQL: {str(e)}"}

class TestMT5Request(BaseModel):
    account: Optional[str] = ""
    password: Optional[str] = ""
    server: Optional[str] = ""
    path: Optional[str] = ""

@app.post("/api/settings/test-mt5")
def test_mt5_conn(req: TestMT5Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    account = (req.account or "").strip()
    password = (req.password or "").strip()
    server = (req.server or "").strip()
    path = (req.path or "").strip()

    # Fallback to saved credentials if masked or omitted
    if not password or "*" in password:
        settings = db.query(AppSettings).first()
        if settings and settings.mt5_password:
            password = settings.mt5_password
        else:
            conf = load_config()
            password = conf.get("app_settings", {}).get("mt5_password", "")

    if not account:
        settings = db.query(AppSettings).first()
        if settings and settings.mt5_account:
            account = settings.mt5_account
            server = server or settings.mt5_server

    res = mt5_service.connect(account=account, password=password, server=server, path=path)
    return res

class TestLLMRequest(BaseModel):
    provider: str
    api_key: Optional[str] = ""
    model: str
    base_url: Optional[str] = ""

@app.post("/api/settings/test-llm")
def test_llm_conn(req: TestLLMRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    api_key = (req.api_key or "").strip()
    # If masked or omitted, resolve real key from DB or config.json
    if not api_key or "*" in api_key:
        settings = db.query(AppSettings).first()
        if settings and settings.llm_api_key:
            api_key = settings.llm_api_key
        else:
            conf = load_config()
            api_key = conf.get("app_settings", {}).get("llm_api_key", "") or os.getenv("OPENAI_API_KEY", "")

    base_url = (req.base_url or "").strip()
    if not base_url:
        settings = db.query(AppSettings).first()
        if settings and getattr(settings, "llm_base_url", ""):
            base_url = settings.llm_base_url
        else:
            conf = load_config()
            base_url = conf.get("app_settings", {}).get("llm_base_url", "")

    res = llm_service.test_connection(provider=req.provider, api_key=api_key, model=req.model, base_url=base_url)
    return res

# ----------------- Static Frontend ----------------- #

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.mount("/static", NoCacheStaticFiles(directory=static_dir), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        resp = FileResponse(index_file)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return {"message": "AI Trading Copilot API Running. Frontend static file pending."}
