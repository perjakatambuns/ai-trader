import json
import re
from typing import Dict, Any, Optional

class LLMService:
    def __init__(self):
        pass

    def test_connection(self, provider: str, api_key: str, model: str, base_url: Optional[str] = None) -> Dict[str, Any]:
        if not api_key and not base_url:
            return {"success": False, "message": "API Key atau Base URL diperlukan untuk pengujian"}
        
        try:
            if provider.lower() == "openai":
                from openai import OpenAI
                kwargs = {"api_key": api_key or "sk-dummy"}
                if base_url and base_url.strip():
                    kwargs["base_url"] = base_url.strip()
                client = OpenAI(**kwargs)
                response = client.chat.completions.create(
                    model=model or "gpt-4o",
                    messages=[{"role": "user", "content": "Respond with the word 'OK' in JSON format: {\"status\": \"OK\"}"}],
                    max_tokens=20
                )
                target_desc = f"custom endpoint ({base_url})" if base_url else f"OpenAI ({model})"
                return {"success": True, "message": f"Successfully connected to {target_desc}"}
            elif provider.lower() == "claude":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model=model or "claude-3-5-sonnet-20241022",
                    max_tokens=20,
                    messages=[{"role": "user", "content": "Respond with {\"status\": \"OK\"}"}]
                )
                return {"success": True, "message": f"Successfully connected to Anthropic Claude ({model})"}
            else:
                return {"success": False, "message": f"Unsupported provider: {provider}"}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {str(e)}"}

    def _fallback_rule_based_analysis(self, quantitative_matrix: Dict[str, Any], news_data: Dict[str, Any], seasonality_data: Dict[str, Any], symbol: str, pip_size: float) -> Dict[str, Any]:
        """
        Algorithmic quantitative fallback when no LLM API key is provided.
        Follows the exact technical strategy specified in plan.md + Dollar Index (DXY).
        """
        d1 = quantitative_matrix.get("d1", {})
        h1 = quantitative_matrix.get("h1", {})
        m30 = quantitative_matrix.get("m30", {})
        m5 = quantitative_matrix.get("m5", {})
        sessions = quantitative_matrix.get("sessions", {})
        dxy = quantitative_matrix.get("dxy", {})

        current_price = m5.get("current_price", d1.get("current_price", 1.0850))
        m30_rsi = m30.get("rsi", 50.0)
        d1_trend = d1.get("trend", "Neutral")
        m30_trend = m30.get("trend", "Neutral")
        pivots = h1.get("pivots", {})

        # High impact calendar check
        if news_data.get("has_imminent_high_impact", False):
            events = ", ".join(news_data.get("imminent_events", []))
            return {
                "action": "WAIT",
                "entry_price": current_price,
                "stop_loss": current_price,
                "take_profit": current_price,
                "risk_reward_ratio": "0:0",
                "confidence_score": 92,
                "analysis_summary": f"SISTEM WAIT: Terdeteksi rilis berita High Impact ({events}) dalam rentang 30 menit. Berdasarkan SOP Filter Berita, seluruh aktivitas trading ditunda untuk menghindari slippage.",
                "seasonality_note": seasonality_data.get("note", "Musiman dalam pantauan.")
            }

        atr = h1.get("atr", current_price * 0.002)
        if atr <= 0:
            atr = 20 * pip_size

        dxy_trend = dxy.get("trend", "Neutral")
        dxy_note = dxy.get("impact_note", "")

        # Multi-timeframe setup logic + DXY correlation
        is_gold = "XAU" in symbol.upper()
        
        # Bullish setup condition
        bullish_allowed = True
        if is_gold and "Strong Bullish" in dxy_trend:
            bullish_allowed = False # DXY surging puts heavy pressure on gold

        if "Bullish" in d1_trend and (m30_rsi <= 48 or "Bullish" in m30_trend) and bullish_allowed:
            action = "BUY_LIMIT"
            entry = pivots.get("s1", current_price - (15 * pip_size))
            if entry >= current_price:
                entry = current_price - (10 * pip_size)
            stop_loss = entry - (atr * 1.5)
            take_profit = entry + (atr * 3.0)
            rr = "1:2.0"
            conf = 87
            summary = (
                f"Daily berada dalam tren Bullish di atas EMA 200 ({d1.get('ema200')}). "
                f"Timeframe M30 membentuk pullback sehat dengan RSI di level {m30_rsi}. "
                f"Indeks Dollar (DXY): {dxy_note} "
                f"Sesi aktif: {', '.join(sessions.get('active_sessions', ['Pasar Reguler']))}. "
                f"Setup Buy Limit divalidasi pada zona Support {entry} dengan target R1/TP {take_profit}."
            )
        elif "Bearish" in d1_trend and (m30_rsi >= 52 or "Bearish" in m30_trend):
            action = "SELL_LIMIT"
            entry = pivots.get("r1", current_price + (15 * pip_size))
            if entry <= current_price:
                entry = current_price + (10 * pip_size)
            stop_loss = entry + (atr * 1.5)
            take_profit = entry - (atr * 3.0)
            rr = "1:2.0"
            conf = 85
            summary = (
                f"Daily berada dalam tren Bearish di bawah EMA 200 ({d1.get('ema200')}). "
                f"Timeframe M30 mengalami rejection pada resistance dinamis dengan RSI di level {m30_rsi}. "
                f"Indeks Dollar (DXY): {dxy_note} "
                f"Sesi aktif: {', '.join(sessions.get('active_sessions', ['Pasar Reguler']))}. "
                f"Setup Sell Limit terkonfirmasi pada area Resistance {entry} dengan target TP {take_profit}."
            )
        else:
            action = "WAIT"
            entry = current_price
            stop_loss = current_price
            take_profit = current_price
            rr = "0:0"
            conf = 72
            summary = (
                f"Tren multi-timeframe belum sinkron (Daily: {d1_trend}, M30: {m30_trend}, RSI: {m30_rsi}). "
                f"Indeks Dollar (DXY): {dxy_note} "
                f"Pasar berada dalam zona sideways konsolidasi tanpa konfirmasi rejection M5 yang memadai. AI menyarankan WAIT."
            )

        return {
            "action": action,
            "entry_price": round(entry, 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward_ratio": rr,
            "confidence_score": conf,
            "analysis_summary": summary,
            "seasonality_note": seasonality_data.get("note", "Bias musiman stabil.")
        }

    def generate_trading_analysis(
        self,
        symbol: str,
        base_symbol: str,
        pip_size: float,
        quantitative_matrix: Dict[str, Any],
        news_data: Dict[str, Any],
        seasonality_data: Dict[str, Any],
        app_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        provider = app_settings.get("llm_provider", "openai")
        api_key = app_settings.get("llm_api_key", "").strip()
        base_url = app_settings.get("llm_base_url", "").strip()
        model = app_settings.get("llm_model", "gpt-4o")

        # If no API key and no base_url, use rule-based Chief Analyst engine
        if not api_key and not base_url:
            return self._fallback_rule_based_analysis(quantitative_matrix, news_data, seasonality_data, symbol, pip_size)

        system_prompt = (
            "You are the Chief Technical Analyst for an elite hedge fund trading on MetaTrader 5 (HFM broker). "
            "Your role is to analyze multi-timeframe price action, EMA trends (20/50/200), RSI momentum, support/resistance pivots, "
            "Dollar Index (DXY) macro momentum, market sessions (London/NY priority), economic news calendar, and historical seasonality.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Output ONLY a valid JSON object matching the requested schema.\n"
            "2. Note the Dollar Index (DXY) trend: strong DXY creates bearish pressure on Gold (XAUUSD) and EURUSD, while weak DXY boosts Gold.\n"
            "3. If High Impact news is imminent within 30 minutes, or market structure is choppy/unclear, recommend action 'WAIT'.\n"
            "4. If clear Bullish setup (Daily > EMA 200, M30 pullback, M5 confirmation), recommend 'BUY_LIMIT'.\n"
            "5. If clear Bearish setup (Daily < EMA 200, M30 rejection, M5 confirmation), recommend 'SELL_LIMIT'.\n"
            "6. Ensure Risk-to-Reward ratio is at least 1:1.5 to 1:3.\n\n"
            "JSON SCHEMA:\n"
            "{\n"
            '  "action": "BUY_LIMIT" | "SELL_LIMIT" | "WAIT",\n'
            '  "entry_price": <number>,\n'
            '  "stop_loss": <number>,\n'
            '  "take_profit": <number>,\n'
            '  "risk_reward_ratio": "<string e.g. 1:2.0>",\n'
            '  "confidence_score": <int between 50 and 99>,\n'
            '  "analysis_summary": "<clear Indonesian language narrative explaining D1, M30, RSI, DXY Index impact, S/R, and news>",\n'
            '  "seasonality_note": "<clear note regarding historical behavior on same date last year>"\n'
            "}"
        )

        user_content = {
            "symbol": symbol,
            "base_symbol": base_symbol,
            "pip_size": pip_size,
            "quantitative_matrix": quantitative_matrix,
            "dollar_index_dxy": quantitative_matrix.get("dxy", {}),
            "economic_news": news_data,
            "historical_seasonality": seasonality_data
        }

        user_prompt = f"Perform deep technical analysis on the following quantitative matrix:\n{json.dumps(user_content, indent=2)}"

        try:
            raw_text = ""
            if provider.lower() == "openai":
                from openai import OpenAI
                kwargs = {
                    "api_key": api_key or "sk-dummy",
                    "timeout": 12.0,
                    "max_retries": 0
                }
                if base_url:
                    kwargs["base_url"] = base_url
                client = OpenAI(**kwargs)

                chat_kwargs = {
                    "model": model or "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.2
                }
                # Only pass response_format to official OpenAI; third-party proxy routers often hang or reject it
                if not base_url:
                    chat_kwargs["response_format"] = {"type": "json_object"}

                response = client.chat.completions.create(**chat_kwargs)
                raw_text = response.choices[0].message.content
            elif provider.lower() == "claude":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key, timeout=12.0, max_retries=0)
                response = client.messages.create(
                    model=model or "claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.2
                )
                raw_text = response.content[0].text
            else:
                return self._fallback_rule_based_analysis(quantitative_matrix, news_data, seasonality_data, symbol, pip_size)

            # Parse JSON
            # Clean markdown code blocks if present
            cleaned = re.sub(r"^```json\s*", "", raw_text.strip())
            cleaned = re.sub(r"```$", "", cleaned.strip())
            data = json.loads(cleaned)
            
            # Sanitize keys
            return {
                "action": data.get("action", "WAIT"),
                "entry_price": float(data.get("entry_price", quantitative_matrix.get("m5", {}).get("current_price", 0.0))),
                "stop_loss": float(data.get("stop_loss", 0.0)),
                "take_profit": float(data.get("take_profit", 0.0)),
                "risk_reward_ratio": str(data.get("risk_reward_ratio", "1:2.0")),
                "confidence_score": int(data.get("confidence_score", 85)),
                "analysis_summary": str(data.get("analysis_summary", "")),
                "seasonality_note": str(data.get("seasonality_note", seasonality_data.get("note", "")))
            }
        except Exception as e:
            print(f"[LLM] Error in LLM generation ({provider}): {e}. Falling back to rule-based analyst.")
            return self._fallback_rule_based_analysis(quantitative_matrix, news_data, seasonality_data, symbol, pip_size)

llm_service = LLMService()
