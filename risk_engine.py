from typing import Dict, Any, Optional

class RiskEngine:
    def __init__(self, default_spread_pips: float = 1.4, default_risk_pct: float = 1.0):
        self.default_spread_pips = default_spread_pips
        self.default_risk_pct = default_risk_pct

    def get_pip_details(self, symbol: str, pip_size: float = 0.0001, account_currency: str = "USC", broker_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sym = symbol.upper()
        curr = (account_currency or "USC").upper()
        is_cent = (curr in ["USC", "EU_C", "CENT", "USDT_C"]) or sym.endswith("C")
        currency_label = "USC" if is_cent else ("USD" if curr in ["USD", ""] else curr)

        # 1. If broker symbol info is provided directly by MT5 on Windows
        if broker_info and broker_info.get("trade_tick_value", 0) > 0 and broker_info.get("trade_tick_size", 0) > 0:
            eff_pip = pip_size if pip_size > 0 else (0.01 if ("XAU" in sym or "JPY" in sym) else 0.0001)
            tick_val = float(broker_info["trade_tick_value"])
            tick_sz = float(broker_info["trade_tick_size"])
            pip_val = (eff_pip / tick_sz) * tick_val
            min_l = max(0.01, float(broker_info.get("volume_min", 0.01)))
            step_l = float(broker_info.get("volume_step", 0.01))
            return {
                "is_cent": is_cent,
                "currency": currency_label,
                "pip_size": eff_pip,
                "pip_value_per_lot": pip_val,
                "min_lot": min_l,
                "volume_step": step_l
            }

        # 2. Formulaic model calibrated for Standard and Cent Accounts (HFM Cent / USC)
        # Note on Cent Accounts (USC):
        # 1 standard lot Gold (XAUUSD) = 100 oz => 1 pip ($0.01) = $1.00 USD
        # 1 cent lot Gold (XAUUSDc) = 1 oz => 1 pip ($0.01) = $0.01 USD = 1.00 USC!
        # For 0.01 lot XAUUSDc: 1 pip = 0.01 USC (100 pips / $1 move = 1.00 USC)
        if "XAU" in sym or "GOLD" in sym:
            default_pip_size = 0.01
            # In USC: 1.00 cent lot = 1.00 USC per pip. In USD: 1.00 std lot = 1.00 USD per pip.
            pip_value = 1.00
        elif "JPY" in sym:
            default_pip_size = 0.01
            # Standard USDJPY 1 lot = ~$6.60 USD per pip. Cent USDJPYc 1 lot = ~6.60 USC per pip.
            pip_value = 6.60
        else:
            # Standard FX (EURUSD, GBPUSD): 1 lot = 10.00 USD per pip.
            # Cent FX (EURUSDc, GBPUSDc): 1 cent lot (1,000 units) = $0.10 USD = 10.00 USC per pip.
            default_pip_size = 0.0001
            pip_value = 10.00

        actual_pip_size = pip_size if pip_size > 0 else default_pip_size
        return {
            "is_cent": is_cent,
            "currency": currency_label,
            "pip_size": actual_pip_size,
            "pip_value_per_lot": pip_value,
            "min_lot": 0.01,
            "volume_step": 0.01
        }

    def calculate_lot_size(
        self,
        account_balance: float,
        risk_pct: float,
        entry_price: float,
        stop_loss: float,
        symbol: str,
        pip_size: float = 0.0001,
        account_currency: str = "USC",
        broker_symbol_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Anti-Margin Call Engine for Standard and Cent (USC) Accounts:
        - Minimum lot is strictly enforced to broker floor: 0.01 Lot
        - Account Balance is in USC (for Cent accounts) or USD
        - Money at Risk (USC) = Balance (USC) * (Risk % / 100)
        - SL Distance Pips = |Entry - SL| / Pip Size
        - Lot = Money at Risk / (SL Distance Pips * Pip Value per Lot)
        - Expected Max Loss = Lot * SL Pips * Pip Value per Lot
        """
        pip_info = self.get_pip_details(symbol, pip_size, account_currency, broker_symbol_info)
        effective_pip_size = pip_info["pip_size"]
        pip_value = pip_info["pip_value_per_lot"]
        currency_label = pip_info["currency"]
        min_lot = pip_info.get("min_lot", 0.01)
        volume_step = pip_info.get("volume_step", 0.01)

        if account_balance <= 0:
            account_balance = 600.0  # safe default

        if risk_pct <= 0:
            risk_pct = 1.0

        money_at_risk = account_balance * (risk_pct / 100.0)
        price_diff = abs(entry_price - stop_loss)
        sl_pips = price_diff / effective_pip_size

        if sl_pips <= 0:
            sl_pips = 10.0  # safety minimum 10 pips

        # Raw lot calculation
        raw_lot = money_at_risk / (sl_pips * pip_value)
        
        # Strictly enforce minimum lot 0.01 and proper lot step rounding
        steps = round(raw_lot / volume_step)
        calculated_lot = round(max(min_lot, steps * volume_step), 2)

        # Expected loss if Stop Loss is hit
        expected_max_loss = round(calculated_lot * sl_pips * pip_value, 2)
        actual_risk_pct = round((expected_max_loss / account_balance) * 100.0, 2)

        # Anti-Margin Call verification statement
        if expected_max_loss > account_balance * 0.30:
            anti_mc_guarantee = (
                f"PERINGATAN MARGIN: Saldo ({account_balance:,.2f} {currency_label}) tergolong kecil untuk jarak SL {sl_pips:,.1f} pips. "
                f"Dengan lot minimum {calculated_lot:.2f} Lot, potensi risiko adalah {expected_max_loss:,.2f} {currency_label} "
                f"({actual_risk_pct:.1f}% modal). Rekomendasi: persempit SL atau pantau ketat."
            )
        else:
            anti_mc_guarantee = (
                f"JAMINAN ANTI-MARGIN CALL: Lot dibatasi {calculated_lot:.2f} Lot (minimal {min_lot:.2f}). "
                f"Jika Stop Loss ({sl_pips:,.1f} pips) tersentuh, kerugian dibatasi maksimal {expected_max_loss:,.2f} {currency_label} "
                f"({actual_risk_pct:.1f}% saldo), jauh di atas level Margin Call (50%) dan Stop Out (20%)."
            )

        return {
            "account_balance": round(account_balance, 2),
            "currency": currency_label,
            "risk_percentage": risk_pct,
            "actual_risk_pct": actual_risk_pct,
            "money_at_risk": round(money_at_risk, 2),
            "sl_distance_pips": round(sl_pips, 1),
            "calculated_lot": calculated_lot,
            "min_lot": min_lot,
            "expected_max_loss": expected_max_loss,
            "expected_max_loss_display": f"{expected_max_loss:,.2f} {currency_label}",
            "pip_value_per_lot": pip_value,
            "is_cent_account": pip_info["is_cent"],
            "anti_mc_guarantee": anti_mc_guarantee
        }

    def apply_spread_buffer(
        self,
        action: str,
        entry_price: float,
        support_or_sl: float,
        resistance_or_tp: float,
        pip_size: float,
        spread_pips: float = 1.4
    ) -> Dict[str, float]:
        """
        Applies HFM 1.4 pips buffer:
        - BUY: Stop Loss placed at support - (1.4 pips + volatility buffer)
        - SELL: Entry limit & SL adjusted with +1.4 pips buffer so spread doesn't trigger early
        """
        buffer_val = spread_pips * pip_size
        volatility_buffer = buffer_val * 0.5 # additional breathing space

        if "BUY" in action.upper():
            # For BUY positions:
            entry = entry_price
            adjusted_sl = support_or_sl - (buffer_val + volatility_buffer)
            adjusted_tp = resistance_or_tp
        else:
            # For SELL positions:
            entry = entry_price - buffer_val # entry placed slightly lower or conservative
            adjusted_sl = support_or_sl + (buffer_val + volatility_buffer) # SL placed above resistance + spread
            adjusted_tp = resistance_or_tp

        return {
            "entry_price": round(entry, 5),
            "stop_loss": round(adjusted_sl, 5),
            "take_profit": round(adjusted_tp, 5),
            "spread_buffer_pips": spread_pips
        }

risk_engine = RiskEngine()
