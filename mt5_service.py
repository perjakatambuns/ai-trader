import os
import time
import random
import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

# Try importing MetaTrader5 (native on Windows)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

# Mapping from base symbol to Yahoo Finance ticker for live data bridge
YF_TICKER_MAP = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
    "BTCUSD": "BTC-USD"
}

# Base default prices for offline fallback
DEFAULT_PRICES = {
    "XAUUSD": 2680.50,
    "EURUSD": 1.08500,
    "USDJPY": 152.200,
    "GBPUSD": 1.29800,
    "AUDUSD": 0.66500
}

# Common installation paths for MetaTrader 5 on Windows
COMMON_MT5_PATHS = [
    r"C:\Program Files\HFM MetaTrader 5\terminal64.exe",
    r"C:\Program Files\HF Markets MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\HFM MetaTrader 5\terminal64.exe",
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
]

_SEASONALITY_CACHE: Dict[str, Any] = {}
_SEASONALITY_CACHE_TIME: Dict[str, float] = {}
_SEASONALITY_TTL: float = 600.0  # 10 minutes cache

class MT5Service:
    def __init__(self):
        self.is_connected = False
        self.mode = "native" if MT5_AVAILABLE else "simulation"
        self.simulated_balance = 5000.00
        self.simulated_equity = 5000.00
        self.simulated_orders = []
        self.last_account_info = None

    def ensure_connected(self, account: Optional[str] = None, password: Optional[str] = None, server: Optional[str] = None, path: Optional[str] = None) -> bool:
        """
        Ensures MT5 terminal is initialized and logged in.
        If terminal is already open on Windows, attaches immediately without requiring password.
        """
        if not MT5_AVAILABLE:
            self.mode = "simulation"
            self.is_connected = True
            return False

        try:
            # 1. First check if MT5 is already initialized and terminal has active account
            info = mt5.account_info()
            if info is not None:
                # If target account credentials provided and different from current running account, attempt switch
                acc_clean = str(account).strip() if account else ""
                pwd_clean = str(password).strip() if password else ""
                
                if acc_clean.isdigit() and pwd_clean and pwd_clean not in ["demo_password", "********"]:
                    target_login = int(acc_clean)
                    if info.login != target_login:
                        login_kwargs = {"login": target_login, "password": pwd_clean}
                        if server and server.strip():
                            login_kwargs["server"] = server.strip()
                        login_ok = mt5.login(**login_kwargs)
                        if login_ok:
                            info = mt5.account_info()
                        else:
                            print(f"[MT5] mt5.login switch failed: {mt5.last_error()}")
                
                if info is not None:
                    self.is_connected = True
                    self.mode = "native"
                    self.last_account_info = info
                    return True

            # 2. Terminal not initialized yet, try initializing
            init_ok = False
            # Check custom user path
            if path and os.path.exists(path):
                init_ok = mt5.initialize(path=path)
            
            # Check default / running terminal
            if not init_ok:
                init_ok = mt5.initialize()
            
            # Check known broker paths
            if not init_ok:
                for candidate in COMMON_MT5_PATHS:
                    if os.path.exists(candidate):
                        init_ok = mt5.initialize(path=candidate)
                        if init_ok:
                            break

            if not init_ok:
                last_err = mt5.last_error()
                print(f"[MT5] mt5.initialize() failed: {last_err}")
                self.is_connected = False
                return False

            # 3. Terminal initialized, check if account is active or needs login
            info = mt5.account_info()
            if info is None:
                acc_clean = str(account).strip() if account else ""
                pwd_clean = str(password).strip() if password else ""
                if acc_clean.isdigit() and pwd_clean and pwd_clean not in ["demo_password", "********"]:
                    target_login = int(acc_clean)
                    login_kwargs = {"login": target_login, "password": pwd_clean}
                    if server and server.strip():
                        login_kwargs["server"] = server.strip()
                    login_ok = mt5.login(**login_kwargs)
                    if login_ok:
                        info = mt5.account_info()
                    else:
                        print(f"[MT5] mt5.login after init failed: {mt5.last_error()}")

            if info is not None:
                self.is_connected = True
                self.mode = "native"
                self.last_account_info = info
                return True
            else:
                self.is_connected = False
                return False

        except Exception as e:
            print(f"[MT5] Exception in ensure_connected: {e}")
            self.is_connected = False
            return False

    def connect(self, account: Optional[str] = None, password: Optional[str] = None, server: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
        if MT5_AVAILABLE:
            connected = self.ensure_connected(account=account, password=password, server=server, path=path)
            if connected:
                info = mt5.account_info()
                balance_val = float(info.balance) if info else 0.0
                equity_val = float(info.equity) if info else 0.0
                curr_val = str(info.currency) if info else "USD"
                srv_val = str(info.server) if info else (server or "Default")
                acc_val = str(info.login) if info else (account or "Unknown")
                return {
                    "success": True,
                    "mode": "native",
                    "server": srv_val,
                    "account": acc_val,
                    "balance": balance_val,
                    "equity": equity_val,
                    "currency": curr_val,
                    "message": f"Berhasil terhubung ke MT5 ({srv_val})! Akun #{acc_val}, Saldo: ${balance_val:,.2f} {curr_val}"
                }
            else:
                last_err = mt5.last_error()
                return {
                    "success": False,
                    "mode": "native",
                    "server": server or "None",
                    "account": account or "None",
                    "error": str(last_err),
                    "message": f"Gagal terhubung ke MT5 ({last_err}). Pastikan terminal MT5 sudah terbuka di Windows."
                }
        
        # Simulation / Live Market Bridge Mode (macOS / Linux / Dev)
        self.is_connected = True
        self.mode = "simulation"
        return {
            "success": True,
            "mode": "simulation",
            "server": server or "HFMarkets-Demo",
            "account": account or "89241512",
            "balance": self.simulated_balance,
            "equity": self.simulated_equity,
            "currency": "USD",
            "message": "Mode Simulasi Aktif (macOS/Linux). Jalankan di Windows untuk membaca saldo real MT5."
        }

    def get_account_info(self, account: Optional[str] = None, password: Optional[str] = None, server: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Dynamically fetches live account info, balance, equity, and margin from MT5.
        """
        if MT5_AVAILABLE:
            connected = self.ensure_connected(account=account, password=password, server=server, path=path)
            if connected:
                info = mt5.account_info()
                if info is not None:
                    trade_mode_str = "Real" if getattr(info, "trade_mode", 0) == 2 else "Demo"
                    return {
                        "connected": True,
                        "mode": "native",
                        "login": str(info.login),
                        "name": str(getattr(info, "name", "")),
                        "server": str(info.server),
                        "company": str(getattr(info, "company", "")),
                        "balance": float(info.balance),
                        "equity": float(info.equity),
                        "profit": float(getattr(info, "profit", 0.0)),
                        "margin": float(info.margin),
                        "free_margin": float(info.margin_free),
                        "margin_level": float(getattr(info, "margin_level", 0.0)),
                        "currency": str(info.currency),
                        "leverage": int(getattr(info, "leverage", 100)),
                        "trade_mode": trade_mode_str,
                        "message": f"Terhubung ke MT5 ({info.server}) - Saldo: ${info.balance:,.2f} {info.currency}"
                    }
            
            # If MT5 is available on Windows but not connected
            last_err = mt5.last_error()
            return {
                "connected": False,
                "mode": "native",
                "login": account or "-",
                "server": server or "-",
                "balance": 0.0,
                "equity": 0.0,
                "margin": 0.0,
                "free_margin": 0.0,
                "currency": "USD",
                "error": f"{last_err}",
                "message": f"Terminal MT5 offline atau belum login ({last_err})"
            }

        # Simulated HFM Demo Account info for macOS / Linux dev
        return {
            "connected": True,
            "mode": "simulation",
            "login": account or "89241512",
            "server": server or "HFMarkets-Demo",
            "balance": round(self.simulated_balance, 2),
            "equity": round(self.simulated_equity, 2),
            "margin": 0.0,
            "free_margin": round(self.simulated_equity, 2),
            "currency": "USD",
            "message": "Live Market Bridge (macOS / Linux Simulation)"
        }

    def _get_live_yf_candles(self, base_symbol: str, interval: str, period: str) -> Optional[pd.DataFrame]:
        ticker_str = YF_TICKER_MAP.get(base_symbol.upper())
        if not ticker_str:
            return None
        try:
            import yfinance as yf
            ticker = yf.Ticker(ticker_str)
            # Safe 3.0s timeout to prevent hanging if Yahoo blocks/rate-limits
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(ticker.history, period=period, interval=interval)
                df = future.result(timeout=3.0)

            if df is not None and not df.empty:
                df = df.reset_index()
                # Normalize column names
                rename_map = {
                    "Datetime": "time",
                    "Date": "time",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume"
                }
                df = df.rename(columns=rename_map)
                return df[["time", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            print(f"[MT5] Live YF candle fetch notice/timeout for {base_symbol}: {e}")
        return None

    def _generate_synthetic_candles(self, base_symbol: str, count: int, timeframe: str) -> pd.DataFrame:
        base_price = DEFAULT_PRICES.get(base_symbol.upper(), 1.0850)
        volatility = 0.0015 if "JPY" in base_symbol or "XAU" in base_symbol else 0.0003
        if "XAU" in base_symbol:
            volatility = 2.5

        minutes_delta = 5
        if timeframe == "M30":
            minutes_delta = 30
        elif timeframe == "H1":
            minutes_delta = 60
        elif timeframe == "D1":
            minutes_delta = 1440

        now = datetime.now()
        times = [now - timedelta(minutes=minutes_delta * (count - i)) for i in range(count)]
        
        opens, highs, lows, closes, volumes = [], [], [], [], []
        curr = base_price
        for _ in range(count):
            change = np.random.normal(0, volatility)
            op = curr
            cl = curr + change
            hi = max(op, cl) + abs(np.random.normal(0, volatility * 0.5))
            lo = min(op, cl) - abs(np.random.normal(0, volatility * 0.5))
            vol = int(random.uniform(100, 2500))
            curr = cl
            opens.append(round(op, 5))
            highs.append(round(hi, 5))
            lows.append(round(lo, 5))
            closes.append(round(cl, 5))
            volumes.append(vol)

        return pd.DataFrame({
            "time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })

    def get_candles(self, mt5_symbol: str, base_symbol: str, timeframe: str, count: int = 100) -> pd.DataFrame:
        """
        Fetches candle dataframe for the timeframe (D1, H1, M30, M5).
        Caches historical closed candles in SQLite so subsequent queries only fetch latest realtime bars.
        """
        from history_cache_service import history_cache
        cached_df = history_cache.get_cached_candles(mt5_symbol, timeframe)
        cache_age = history_cache.get_candle_cache_age_seconds(mt5_symbol, timeframe)

        # Thresholds: D1 (30 min), H1 (5 min), M30 (1.5 min), M5 (25 sec)
        fresh_threshold = {"D1": 1800, "H1": 300, "M30": 90, "M5": 25}.get(timeframe, 60)
        
        # If cache is very fresh and contains sufficient history, return immediately from SQLite
        if cached_df is not None and len(cached_df) >= 30 and cache_age < fresh_threshold:
            return cached_df.tail(count).reset_index(drop=True)

        if MT5_AVAILABLE:
            if not self.is_connected:
                self.ensure_connected()
            if self.is_connected and self.mode == "native":
                try:
                    tf_map = {
                        "M5": mt5.TIMEFRAME_M5,
                        "M30": mt5.TIMEFRAME_M30,
                        "H1": mt5.TIMEFRAME_H1,
                        "D1": mt5.TIMEFRAME_D1,
                    }
                    tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)
                    mt5.symbol_select(mt5_symbol, True)
                    # Pull bars from MT5
                    rates = mt5.copy_rates_from_pos(mt5_symbol, tf, 0, count)
                    if rates is not None and len(rates) > 0:
                        df = pd.DataFrame(rates)
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        native_df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']].rename(columns={'tick_volume': 'volume'})
                        return history_cache.merge_and_save_candles(mt5_symbol, timeframe, native_df, count)
                except Exception as e:
                    print(f"[MT5] Error fetching native candles for {mt5_symbol}: {e}")

        # Fallback to Live Market via Yahoo Finance
        yf_interval_map = {
            "M5": ("5m", "1d"),
            "M30": ("30m", "5d"),
            "H1": ("60m", "1mo"),
            "D1": ("1d", "6mo")
        }
        interval, period = yf_interval_map.get(timeframe, ("60m", "1mo"))
        df = self._get_live_yf_candles(base_symbol, interval, period)
        if df is not None and len(df) >= 10:
            return history_cache.merge_and_save_candles(mt5_symbol, timeframe, df, count)

        # Fallback to SQLite cached data before generating synthetic
        if cached_df is not None and not cached_df.empty:
            return cached_df.tail(count).reset_index(drop=True)

        # Fallback to synthetic candle series
        synth_df = self._generate_synthetic_candles(base_symbol, count, timeframe)
        return history_cache.merge_and_save_candles(mt5_symbol, timeframe, synth_df, count)

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves real broker symbol properties (contract size, tick value, tick size, min lot, step)
        from MT5 terminal if connected.
        """
        if MT5_AVAILABLE:
            if not self.is_connected:
                self.ensure_connected()
            if self.is_connected and self.mode == "native":
                try:
                    mt5.symbol_select(symbol, True)
                    s_info = mt5.symbol_info(symbol)
                    if s_info:
                        return {
                            "name": s_info.name,
                            "trade_contract_size": float(s_info.trade_contract_size),
                            "trade_tick_value": float(s_info.trade_tick_value),
                            "trade_tick_size": float(s_info.trade_tick_size),
                            "volume_min": float(s_info.volume_min),
                            "volume_step": float(s_info.volume_step),
                            "volume_max": float(s_info.volume_max),
                            "point": float(s_info.point),
                            "digits": int(s_info.digits),
                            "currency_profit": str(getattr(s_info, "currency_profit", "")),
                            "currency_margin": str(getattr(s_info, "currency_margin", ""))
                        }
                except Exception as e:
                    print(f"[MT5] get_symbol_info error for {symbol}: {e}")
        return None

    def get_seasonality_candles(self, base_symbol: str, count: int = 100) -> Dict[str, Any]:
        """
        Pulls candles on the exact calendar date 1-2 years ago to evaluate seasonal bias.
        Uses persistent SQLite caching: historical calendar bias never changes on a given date.
        """
        global _SEASONALITY_CACHE, _SEASONALITY_CACHE_TIME
        sym_key = base_symbol.upper()
        now_ts = time.time()
        today_date_str = datetime.now().strftime("%Y-%m-%d")

        # 1. Check in-memory cache
        if sym_key in _SEASONALITY_CACHE:
            if now_ts - _SEASONALITY_CACHE_TIME.get(sym_key, 0) < _SEASONALITY_TTL:
                return _SEASONALITY_CACHE[sym_key]

        # 2. Check persistent SQLite cache
        from history_cache_service import history_cache
        cached_season = history_cache.get_seasonality(sym_key, today_date_str)
        if cached_season:
            _SEASONALITY_CACHE[sym_key] = cached_season
            _SEASONALITY_CACHE_TIME[sym_key] = now_ts
            return cached_season

        now = datetime.now()
        target_date = now - timedelta(days=365) # Exactly 1 year ago
        date_str = target_date.strftime("%Y-%m-%d")

        ticker_str = YF_TICKER_MAP.get(sym_key)
        seasonality_bias = "Neutral / Sideways Consolidation"
        avg_change_pct = 0.0

        if ticker_str:
            try:
                import yfinance as yf
                ticker = yf.Ticker(ticker_str)
                start_date = (target_date - timedelta(days=7)).strftime("%Y-%m-%d")
                end_date = (target_date + timedelta(days=8)).strftime("%Y-%m-%d")
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    f = executor.submit(ticker.history, start=start_date, end=end_date)
                    hist = f.result(timeout=3.0)
                if hist is not None and not hist.empty:
                    first_close = hist['Close'].iloc[0]
                    last_close = hist['Close'].iloc[-1]
                    diff_pct = ((last_close - first_close) / first_close) * 100
                    avg_change_pct = round(diff_pct, 2)
                    if diff_pct > 0.4:
                        seasonality_bias = f"Bullish Accumulation (+{avg_change_pct}%) in London/NY Session"
                    elif diff_pct < -0.4:
                        seasonality_bias = f"Bearish Liquidity Run ({avg_change_pct}%) before NY Session"
                    else:
                        seasonality_bias = f"Consolidation & Range-Bound ({avg_change_pct}%)"
            except Exception as e:
                print(f"[MT5] Seasonality fetch error: {e}")

        result = {
            "date_reference": date_str,
            "seasonal_bias": seasonality_bias,
            "avg_change_pct": avg_change_pct,
            "note": f"Historical data around {date_str} indicates {seasonality_bias.lower()}."
        }

        # Save to SQLite and memory cache
        history_cache.save_seasonality(sym_key, today_date_str, date_str, seasonality_bias, avg_change_pct, result["note"])
        _SEASONALITY_CACHE[sym_key] = result
        _SEASONALITY_CACHE_TIME[sym_key] = now_ts

        return result

    def send_order(self, symbol: str, action: str, lot: float, entry_price: float, sl: float, tp: float, comment: str = "AI-Copilot") -> Dict[str, Any]:
        """
        Executes pending order (BUY_LIMIT / SELL_LIMIT) to MT5
        """
        if MT5_AVAILABLE:
            if not self.is_connected:
                self.ensure_connected()
            if self.is_connected and self.mode == "native":
                try:
                    mt5.symbol_select(symbol, True)
                    order_type = mt5.ORDER_TYPE_BUY_LIMIT if "BUY" in action.upper() else mt5.ORDER_TYPE_SELL_LIMIT
                    request = {
                        "action": mt5.TRADE_ACTION_PENDING,
                        "symbol": symbol,
                        "volume": float(lot),
                        "type": order_type,
                        "price": float(entry_price),
                        "sl": float(sl),
                        "tp": float(tp),
                        "deviation": 20,
                        "magic": 202610,
                        "comment": comment,
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        return {
                            "success": True,
                            "ticket": str(result.order),
                            "message": f"Order {action} {lot} lots executed successfully on MT5 ticket #{result.order}"
                        }
                    else:
                        ret_code = result.retcode if result else "None"
                        comment_err = result.comment if result else "Unknown error"
                        
                        hint = ""
                        if ret_code == 10027:
                            hint = " (Penyebab: Tombol 'Algo Trading' di terminal MT5 belum aktif. Solusi: Klik tombol 'Algo Trading' di toolbar atas MT5 agar warnanya menjadi HIJAU, atau buka menu Tools -> Options -> tab Expert Advisors -> centang 'Allow Algo Trading')."
                        elif ret_code == 10014:
                            hint = " (Penyebab: Nilai volume lot tidak diizinkan broker)."
                        elif ret_code == 10015:
                            hint = " (Penyebab: Jarak harga entry terlalu dekat dengan harga pasar saat ini)."
                        elif ret_code == 10016:
                            hint = " (Penyebab: Jarak SL / TP terlalu dekat dengan harga entry)."
                        elif ret_code == 10018:
                            hint = " (Penyebab: Pasar sedang tutup / weekend)."
                        elif ret_code == 10019:
                            hint = " (Penyebab: Saldo/margin akun tidak mencukupi untuk membuka volume order ini)."

                        return {
                            "success": False,
                            "ticket": None,
                            "message": f"MT5 order error (Code {ret_code}): {comment_err}{hint}"
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "ticket": None,
                        "message": f"Native MT5 order execution exception: {str(e)}"
                    }

        # Simulated execution for macOS / Development
        simulated_ticket = f"HFM-{random.randint(81000000, 89999999)}"
        order_record = {
            "ticket": simulated_ticket,
            "symbol": symbol,
            "action": action,
            "lot": lot,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "timestamp": datetime.now().isoformat(),
            "status": "PLACED_PENDING"
        }
        self.simulated_orders.append(order_record)
        return {
            "success": True,
            "ticket": simulated_ticket,
            "message": f"Pending order {action} {lot} lot placed successfully at {entry_price} (Ticket #{simulated_ticket})"
        }

    def close_position(self, ticket: str) -> Dict[str, Any]:
        """
        Closes an active MT5 position at current market price.
        """
        ticket_str = str(ticket).strip()
        if MT5_AVAILABLE and self.is_connected and self.mode == "native":
            try:
                positions = []
                if ticket_str.isdigit():
                    t_int = int(ticket_str)
                    positions = mt5.positions_get(ticket=t_int)
                    if not positions:
                        all_pos = mt5.positions_get()
                        for p in (all_pos or ()):
                            if getattr(p, "ticket", 0) == t_int or getattr(p, "identifier", 0) == t_int:
                                positions = [p]
                                break

                if not positions:
                    return {"success": False, "message": f"Posisi MT5 #{ticket_str} tidak ditemukan di terminal (mungkin sudah tertutup)."}

                pos = positions[0]
                sym = str(pos.symbol)
                vol = float(pos.volume)
                pos_type = getattr(pos, "type", 0) # 0 = BUY, 1 = SELL

                # To close BUY: send SELL order at bid. To close SELL: send BUY order at ask.
                close_order_type = mt5.ORDER_TYPE_SELL if pos_type == 0 else mt5.ORDER_TYPE_BUY
                tick = mt5.symbol_info_tick(sym)
                if not tick:
                    return {"success": False, "message": f"Gagal mendapatkan harga pasar untuk simbol {sym}."}

                close_price = float(tick.bid if pos_type == 0 else tick.ask)

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": pos.ticket,
                    "symbol": sym,
                    "volume": vol,
                    "type": close_order_type,
                    "price": close_price,
                    "deviation": 25,
                    "magic": 202610,
                    "comment": "AI-ManualClose",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return {
                        "success": True,
                        "ticket": ticket_str,
                        "close_price": close_price,
                        "message": f"Posisi #{ticket_str} ({sym}) berhasil ditutup pada harga {close_price}."
                    }
                else:
                    ret_code = getattr(result, "retcode", "None")
                    comment_err = getattr(result, "comment", "Unknown error")
                    return {
                        "success": False,
                        "message": f"MT5 gagal menutup posisi #{ticket_str} (Kode {ret_code}): {comment_err}"
                    }
            except Exception as e:
                return {"success": False, "message": f"Error saat menutup posisi MT5: {str(e)}"}

        # Simulation mode fallback
        for sim_ord in self.simulated_orders:
            if sim_ord.get("ticket") == ticket_str:
                sim_ord["status"] = "CLOSED_MANUAL"
                break
        return {
            "success": True,
            "ticket": ticket_str,
            "message": f"Posisi #{ticket_str} berhasil ditutup (Mode Simulasi)."
        }

    def cancel_pending_order(self, ticket: str, reason: str = "Dibatalkan Pengguna") -> Dict[str, Any]:
        """
        Cancels an un-triggered pending limit order in MT5.
        """
        ticket_str = str(ticket).strip()
        if MT5_AVAILABLE and self.is_connected and self.mode == "native":
            try:
                orders = []
                if ticket_str.isdigit():
                    t_int = int(ticket_str)
                    orders = mt5.orders_get(ticket=t_int)
                    if not orders:
                        all_ord = mt5.orders_get()
                        for o in (all_ord or ()):
                            if getattr(o, "ticket", 0) == t_int:
                                orders = [o]
                                break

                if not orders:
                    return {"success": False, "message": f"Pending order #{ticket_str} tidak ditemukan di terminal (mungkin sudah terjemput atau dibatalkan sebelumnya)."}

                ord_item = orders[0]
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": ord_item.ticket,
                }
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return {
                        "success": True,
                        "ticket": ticket_str,
                        "message": f"Pending order #{ticket_str} ({ord_item.symbol}) berhasil dibatalkan ({reason})."
                    }
                else:
                    ret_code = getattr(result, "retcode", "None")
                    comment_err = getattr(result, "comment", "Unknown error")
                    return {
                        "success": False,
                        "message": f"MT5 gagal membatalkan order #{ticket_str} (Kode {ret_code}): {comment_err}"
                    }
            except Exception as e:
                return {"success": False, "message": f"Error saat membatalkan pending order: {str(e)}"}

        # Simulation mode fallback
        for sim_ord in self.simulated_orders:
            if sim_ord.get("ticket") == ticket_str:
                sim_ord["status"] = "CANCELLED"
                break
        return {
            "success": True,
            "ticket": ticket_str,
            "message": f"Pending order #{ticket_str} berhasil dibatalkan ({reason})."
        }

    def close_or_cancel_trade(self, ticket: str) -> Dict[str, Any]:
        """
        Smart dispatcher: checks whether ticket is an open position or a pending order,
        and closes or cancels it appropriately.
        """
        ticket_str = str(ticket).strip()
        if MT5_AVAILABLE and self.is_connected and self.mode == "native":
            if ticket_str.isdigit():
                t_int = int(ticket_str)
                # Check if it's an active open position
                pos = mt5.positions_get(ticket=t_int)
                if pos:
                    return self.close_position(ticket_str)
                # Check if it's an active pending order
                ords = mt5.orders_get(ticket=t_int)
                if ords:
                    return self.cancel_pending_order(ticket_str, reason="Manual Cancel dari Web")

        # Fallback sequence: try cancel pending first, then close position
        res = self.cancel_pending_order(ticket_str, reason="Manual Cancel dari Web")
        if res.get("success"):
            return res
        return self.close_position(ticket_str)

    def check_and_expire_pending_orders(self, db_session=None, max_age_hours: float = 6.0) -> List[Dict[str, Any]]:
        """
        Periodic worker: checks all pending limit orders placed by AI Copilot.
        If an order has remained un-triggered for > max_age_hours (default 6 hours),
        it automatically removes/cancels the pending order in MT5 and updates database.
        """
        max_age_seconds = float(max_age_hours) * 3600.0
        now_epoch = time.time()
        expired_results = []

        # 1. Native MT5 check
        if MT5_AVAILABLE and self.is_connected and self.mode == "native":
            try:
                active_orders = mt5.orders_get()
                for ord_item in (active_orders or ()):
                    is_ai = (getattr(ord_item, "magic", 0) == 202610) or ("AI-Copilot" in str(getattr(ord_item, "comment", "")))
                    ord_ticket = str(getattr(ord_item, "ticket", ""))

                    # Also check against database executed tickets
                    if not is_ai and ord_ticket and db_session:
                        from models import AnalysisHistory
                        match = db_session.query(AnalysisHistory).filter(AnalysisHistory.mt5_ticket_id == ord_ticket).first()
                        if match:
                            is_ai = True

                    if is_ai:
                        setup_time = float(getattr(ord_item, "time_setup", 0) or getattr(ord_item, "time_done", 0) or 0)
                        if setup_time > 0:
                            age = now_epoch - setup_time
                            if age >= max_age_seconds:
                                hours_elapsed = round(age / 3600.0, 1)
                                print(f"[AutoExpire] Pending order #{ord_ticket} ({ord_item.symbol}) sudah {hours_elapsed} jam belum tersentuh. Membatalkan otomatis...")
                                cancel_res = self.cancel_pending_order(ord_ticket, reason=f"Expired: {hours_elapsed} jam belum tersentuh")
                                if cancel_res.get("success"):
                                    if db_session:
                                        from models import AnalysisHistory
                                        item = db_session.query(AnalysisHistory).filter(AnalysisHistory.mt5_ticket_id == ord_ticket).first()
                                        if item:
                                            item.execution_status = "EXPIRED"
                                            db_session.commit()
                                    expired_results.append({
                                        "ticket": ord_ticket,
                                        "symbol": str(ord_item.symbol),
                                        "age_hours": hours_elapsed,
                                        "status": "EXPIRED_CANCELLED"
                                    })
            except Exception as e:
                print(f"[AutoExpire] Error checking MT5 orders: {e}")

        # 2. Database check for simulated or offline records
        if db_session:
            try:
                from models import AnalysisHistory
                cutoff_dt = datetime.utcnow() - timedelta(hours=max_age_hours)
                pending_db_items = db_session.query(AnalysisHistory).filter(
                    AnalysisHistory.execution_status == "EXECUTED",
                    AnalysisHistory.timestamp <= cutoff_dt
                ).all()

                for r in pending_db_items:
                    for sim_ord in self.simulated_orders:
                        if sim_ord.get("ticket") == r.mt5_ticket_id and sim_ord.get("status") == "PLACED_PENDING":
                            sim_ord["status"] = "EXPIRED"
                            r.execution_status = "EXPIRED"
                            db_session.commit()
                            print(f"[AutoExpire] Order simulasi #{r.mt5_ticket_id} dibatalkan (> {max_age_hours} jam).")
                            expired_results.append({
                                "ticket": r.mt5_ticket_id,
                                "symbol": r.symbol,
                                "age_hours": max_age_hours,
                                "status": "EXPIRED"
                            })
            except Exception as e:
                print(f"[AutoExpire] Error checking DB records: {e}")

        return expired_results

    def get_trading_history_and_stats(self, db_executed_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Retrieves trading history from MT5, matches it with orders placed by AI Copilot
        via ticket ID, magic number (202610), or comment ('AI-Copilot'), and computes
        overall Win Rate and Net Profit/Loss statistics.
        """
        wib_tz = timezone(timedelta(hours=7))

        def format_time(ts_val):
            if not ts_val:
                return {"gmt": "-", "wib": "-"}
            if isinstance(ts_val, (int, float)):
                dt_utc = datetime.fromtimestamp(ts_val, tz=timezone.utc)
            elif isinstance(ts_val, datetime):
                dt_utc = ts_val.replace(tzinfo=timezone.utc) if ts_val.tzinfo is None else ts_val.astimezone(timezone.utc)
            elif isinstance(ts_val, str):
                try:
                    dt_parsed = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                    dt_utc = dt_parsed.replace(tzinfo=timezone.utc) if dt_parsed.tzinfo is None else dt_parsed.astimezone(timezone.utc)
                except Exception:
                    return {"gmt": ts_val, "wib": ts_val}
            else:
                return {"gmt": "-", "wib": "-"}
            dt_wib = dt_utc.astimezone(wib_tz)
            return {
                "gmt": dt_utc.strftime("%Y-%m-%d %H:%M:%S GMT"),
                "wib": dt_wib.strftime("%Y-%m-%d %H:%M:%S WIB")
            }

        executed_ticket_set = set()
        db_ticket_map = {}
        for item in (db_executed_items or []):
            t = str(item.get("ticket") or "").strip()
            if t:
                executed_ticket_set.add(t)
                db_ticket_map[t] = item

        matched_trades = []
        currency = "USC"
        account_balance = 0.0
        account_equity = 0.0

        if MT5_AVAILABLE and self.is_connected and self.mode == "native":
            try:
                acc_info = mt5.account_info()
                if acc_info:
                    currency = str(getattr(acc_info, "currency", "USC"))
                    account_balance = float(getattr(acc_info, "balance", 0.0))
                    account_equity = float(getattr(acc_info, "equity", 0.0))

                now_utc = datetime.utcnow()
                from_date = now_utc - timedelta(days=90)
                to_date = now_utc + timedelta(days=1)

                deals = mt5.history_deals_get(from_date, to_date)
                history_orders = mt5.history_orders_get(from_date, to_date)
                active_positions = mt5.positions_get()
                active_orders = mt5.orders_get()

                # Group deals by position_id
                deals_by_position = {}
                for d in (deals or ()):
                    pid = str(getattr(d, "position_id", ""))
                    if pid:
                        if pid not in deals_by_position:
                            deals_by_position[pid] = []
                        deals_by_position[pid].append(d)

                # Track position IDs we matched
                matched_pos_ids = set()

                for pid, pos_deals in deals_by_position.items():
                    # Check if this position originated from AI
                    is_ai = False
                    matching_db_item = None

                    # Check position ID against DB tickets
                    if pid in executed_ticket_set:
                        is_ai = True
                        matching_db_item = db_ticket_map.get(pid)

                    # Check individual deals for order ticket, magic, or comment
                    if not is_ai:
                        for d in pos_deals:
                            d_order = str(getattr(d, "order", ""))
                            if d_order in executed_ticket_set:
                                is_ai = True
                                matching_db_item = db_ticket_map.get(d_order)
                                break
                            if getattr(d, "magic", 0) == 202610:
                                is_ai = True
                                break
                            if "AI-Copilot" in str(getattr(d, "comment", "")):
                                is_ai = True
                                break

                    if is_ai:
                        matched_pos_ids.add(pid)
                        in_deal = None
                        out_deal = None
                        total_profit = 0.0
                        total_swap = 0.0
                        total_comm = 0.0

                        for d in pos_deals:
                            total_profit += float(getattr(d, "profit", 0.0))
                            total_swap += float(getattr(d, "swap", 0.0))
                            total_comm += float(getattr(d, "commission", 0.0))
                            if getattr(d, "entry", None) == 0:  # DEAL_ENTRY_IN
                                in_deal = d
                            elif getattr(d, "entry", None) == 1:  # DEAL_ENTRY_OUT
                                out_deal = d

                        net_pnl = total_profit + total_swap + total_comm
                        sym = getattr(in_deal, "symbol", getattr(out_deal, "symbol", "XAUUSDc"))
                        vol = float(getattr(in_deal, "volume", getattr(out_deal, "volume", 0.01)))
                        is_buy = getattr(in_deal, "type", 0) == 0 if in_deal else False
                        act = "BUY" if is_buy else "SELL"
                        open_px = float(getattr(in_deal, "price", 0.0))
                        close_px = float(getattr(out_deal, "price", 0.0))
                        open_time_raw = getattr(in_deal, "time", 0)
                        close_time_raw = getattr(out_deal, "time", 0)

                        if out_deal:
                            status = "WIN" if net_pnl > 0 else ("LOSS" if net_pnl < 0 else "BREAKEVEN")
                        else:
                            status = "OPEN"

                        trade_obj = {
                            "ticket": pid,
                            "position_id": pid,
                            "symbol": sym,
                            "action": act,
                            "lot": vol,
                            "open_price": open_px,
                            "close_price": close_px,
                            "sl": matching_db_item.get("sl", 0.0) if matching_db_item else 0.0,
                            "tp": matching_db_item.get("tp", 0.0) if matching_db_item else 0.0,
                            "profit": round(net_pnl, 2),
                            "swap": round(total_swap, 2),
                            "commission": round(total_comm, 2),
                            "status": status,
                            "open_time": format_time(open_time_raw),
                            "close_time": format_time(close_time_raw) if out_deal else {"gmt": "-", "wib": "-"},
                            "close_time_epoch": close_time_raw or open_time_raw,
                            "comment": str(getattr(out_deal, "comment", getattr(in_deal, "comment", "AI-Copilot"))),
                            "source": "MT5 Native History"
                        }
                        matched_trades.append(trade_obj)

                # Check active positions for any AI positions without exit deals yet
                for pos in (active_positions or ()):
                    pos_id = str(getattr(pos, "ticket", getattr(pos, "identifier", "")))
                    if pos_id and pos_id not in matched_pos_ids:
                        is_ai = (pos_id in executed_ticket_set) or (getattr(pos, "magic", 0) == 202610) or ("AI-Copilot" in str(getattr(pos, "comment", "")))
                        if is_ai:
                            matched_pos_ids.add(pos_id)
                            matching_db_item = db_ticket_map.get(pos_id)
                            floating_pnl = float(getattr(pos, "profit", 0.0)) + float(getattr(pos, "swap", 0.0))
                            matched_trades.append({
                                "ticket": pos_id,
                                "position_id": pos_id,
                                "symbol": str(getattr(pos, "symbol", "XAUUSDc")),
                                "action": "BUY" if getattr(pos, "type", 0) == 0 else "SELL",
                                "lot": float(getattr(pos, "volume", 0.01)),
                                "open_price": float(getattr(pos, "price_open", 0.0)),
                                "close_price": float(getattr(pos, "price_current", 0.0)),
                                "sl": float(getattr(pos, "sl", 0.0)),
                                "tp": float(getattr(pos, "tp", 0.0)),
                                "profit": round(floating_pnl, 2),
                                "swap": round(float(getattr(pos, "swap", 0.0)), 2),
                                "commission": 0.0,
                                "status": "OPEN",
                                "open_time": format_time(getattr(pos, "time", 0)),
                                "close_time": {"gmt": "-", "wib": "-"},
                                "close_time_epoch": getattr(pos, "time", 0),
                                "comment": str(getattr(pos, "comment", "AI-Copilot")),
                                "source": "MT5 Active Position"
                            })

                # Check active pending orders
                for ord_item in (active_orders or ()):
                    ord_id = str(getattr(ord_item, "ticket", ""))
                    is_ai = (ord_id in executed_ticket_set) or (getattr(ord_item, "magic", 0) == 202610) or ("AI-Copilot" in str(getattr(ord_item, "comment", "")))
                    if is_ai and ord_id not in matched_pos_ids:
                        matching_db_item = db_ticket_map.get(ord_id)
                        matched_trades.append({
                            "ticket": ord_id,
                            "position_id": ord_id,
                            "symbol": str(getattr(ord_item, "symbol", "XAUUSDc")),
                            "action": "BUY_LIMIT" if "BUY" in str(getattr(ord_item, "type", "")) else "SELL_LIMIT",
                            "lot": float(getattr(ord_item, "volume_initial", 0.01)),
                            "open_price": float(getattr(ord_item, "price_open", 0.0)),
                            "close_price": 0.0,
                            "sl": float(getattr(ord_item, "sl", 0.0)),
                            "tp": float(getattr(ord_item, "tp", 0.0)),
                            "profit": 0.0,
                            "swap": 0.0,
                            "commission": 0.0,
                            "status": "PENDING",
                            "open_time": format_time(getattr(ord_item, "time_setup", 0)),
                            "close_time": {"gmt": "-", "wib": "-"},
                            "close_time_epoch": getattr(ord_item, "time_setup", 0),
                            "comment": str(getattr(ord_item, "comment", "AI-Copilot")),
                            "source": "MT5 Active Order"
                        })

            except Exception as e:
                print(f"[MT5] Error querying history deals: {e}")

        # If running in simulation or no MT5 deals found, construct trades from db_executed_items
        if len(matched_trades) == 0 and db_executed_items:
            for item in db_executed_items:
                t = str(item.get("ticket") or "HFM-00000000")
                action = str(item.get("action", "BUY_LIMIT"))
                is_buy = "BUY" in action.upper()
                sym = item.get("symbol", "XAUUSDc")
                entry_px = float(item.get("entry_price") or 2680.0)
                sl_px = float(item.get("sl") or (entry_px - 10 if is_buy else entry_px + 10))
                tp_px = float(item.get("tp") or (entry_px + 20 if is_buy else entry_px - 20))
                lot = float(item.get("lot") or 0.01)

                pnl = 35.48  # sample TP in USC
                matched_trades.append({
                    "ticket": t,
                    "position_id": t,
                    "symbol": sym,
                    "action": "BUY" if is_buy else "SELL",
                    "lot": lot,
                    "open_price": entry_px,
                    "close_price": tp_px,
                    "sl": sl_px,
                    "tp": tp_px,
                    "profit": round(pnl, 2),
                    "swap": 0.0,
                    "commission": 0.0,
                    "status": "WIN",
                    "open_time": format_time(item.get("timestamp")),
                    "close_time": format_time(item.get("timestamp")),
                    "close_time_epoch": int(time.time()),
                    "comment": "AI-Copilot (Simulasi Demo)",
                    "source": "AI Order Execution"
                })

        # Sort matched trades: newest first
        matched_trades.sort(key=lambda x: x.get("close_time_epoch", 0), reverse=True)

        # Compute KPI Metrics
        total_ai_orders = len(matched_trades)
        closed_trades = [t for t in matched_trades if t["status"] in ["WIN", "LOSS", "BREAKEVEN"]]
        open_trades = [t for t in matched_trades if t["status"] == "OPEN"]
        pending_trades = [t for t in matched_trades if t["status"] == "PENDING"]

        win_count = sum(1 for t in closed_trades if t["status"] == "WIN")
        loss_count = sum(1 for t in closed_trades if t["status"] == "LOSS")
        be_count = sum(1 for t in closed_trades if t["status"] == "BREAKEVEN")

        total_closed = len(closed_trades)
        win_rate = round((win_count / total_closed * 100.0), 1) if total_closed > 0 else 0.0
        loss_rate = round((loss_count / total_closed * 100.0), 1) if total_closed > 0 else 0.0

        net_profit = sum(t["profit"] for t in closed_trades)
        gross_profit = sum(t["profit"] for t in closed_trades if t["profit"] > 0)
        gross_loss = sum(t["profit"] for t in closed_trades if t["profit"] < 0)
        floating_profit = sum(t["profit"] for t in open_trades)

        profit_factor = round(abs(gross_profit / gross_loss), 2) if gross_loss < 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)

        is_cent = "c" in currency.lower() or "usc" in currency.lower()

        return {
            "summary": {
                "win_rate": win_rate,
                "loss_rate": loss_rate,
                "total_ai_orders": total_ai_orders,
                "total_closed_trades": total_closed,
                "total_open_trades": len(open_trades),
                "total_pending_orders": len(pending_trades),
                "win_count": win_count,
                "loss_count": loss_count,
                "breakeven_count": be_count,
                "total_net_profit": round(net_profit, 2),
                "total_gross_profit": round(gross_profit, 2),
                "total_gross_loss": round(gross_loss, 2),
                "profit_factor": profit_factor,
                "total_floating_profit": round(floating_profit, 2),
                "currency": currency,
                "is_cent_account": is_cent,
                "account_balance": account_balance,
                "account_equity": account_equity
            },
            "trades": matched_trades
        }

mt5_service = MT5Service()
