import re
import time
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import feedparser
import httpx
from bs4 import BeautifulSoup

_NEWS_CACHE: Dict[str, Any] = {}
_NEWS_CACHE_TIME: Dict[str, float] = {}
_NEWS_CACHE_TTL: float = 90.0  # 90 seconds in-memory cache

class NewsService:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_forex_factory_calendar(self) -> Dict[str, Any]:
        """
        Fetches economic calendar from Forex Factory weekly JSON feed.
        Detects High Impact (Red Folder) events within +/- 30 minutes of current time.
        """
        high_impact_news = []
        has_imminent_high_impact = False
        imminent_events = []

        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        week_key = datetime.now(timezone.utc).strftime("%Y-W%U")
        data = None

        try:
            from history_cache_service import history_cache
            data = history_cache.get_economic_calendar(week_key, max_age_hours=4.0)
        except Exception as e:
            print(f"[NewsService] Calendar cache read error: {e}")

        if not data:
            try:
                with httpx.Client(timeout=5.0, headers=self.headers) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        try:
                            from history_cache_service import history_cache
                            history_cache.save_economic_calendar(week_key, data)
                        except Exception as e:
                            print(f"[NewsService] Calendar cache save error: {e}")
            except Exception as e:
                print(f"[NewsService] ForexFactory fetch error: {e}")

        if data:
            try:
                now_utc = datetime.now(timezone.utc)
                for item in data:
                    impact = str(item.get("impact", "")).lower()
                    title = item.get("title", "")
                    country = item.get("country", "")
                    date_str = item.get("date", "")
                    
                    is_red = ("high" in impact or "red" in impact)
                    if is_red:
                        high_impact_news.append({
                            "title": title,
                            "country": country,
                            "impact": "HIGH_IMPACT",
                            "date": date_str
                        })
                        # Parse time if possible to check if within 30 min window
                        try:
                            event_time = datetime.fromisoformat(date_str)
                            diff_min = abs((event_time - now_utc).total_seconds()) / 60.0
                            if diff_min <= 35:
                                has_imminent_high_impact = True
                                imminent_events.append(f"{country} - {title} ({round(diff_min)}m away)")
                        except Exception:
                            pass
            except Exception as e:
                print(f"[NewsService] ForexFactory parse error: {e}")

        return {
            "source": "Forex Factory",
            "has_imminent_high_impact": has_imminent_high_impact,
            "imminent_events": imminent_events,
            "high_impact_count": len(high_impact_news),
            "upcoming_events": high_impact_news[:5]
        }

    def fetch_forexlive_rss(self) -> List[Dict[str, str]]:
        url = "https://www.forexlive.com/feed/news"
        articles = []
        try:
            with httpx.Client(timeout=4.0, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:5]:
                        articles.append({
                            "title": entry.get("title", ""),
                            "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:160] + "...",
                            "link": entry.get("link", ""),
                            "source": "ForexLive"
                        })
        except Exception as e:
            print(f"[NewsService] ForexLive RSS error: {e}")
        return articles

    def fetch_google_news_rss(self, base_symbol: str) -> List[Dict[str, str]]:
        query_map = {
            "XAUUSD": "Gold+price+Fed+inflation",
            "EURUSD": "EURUSD+forex+ECB+Fed",
            "USDJPY": "USDJPY+forex+Bank+of+Japan",
            "GBPUSD": "GBPUSD+forex+Bank+of+England",
        }
        query = query_map.get(base_symbol.upper(), f"{base_symbol}+forex+market")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        articles = []
        try:
            with httpx.Client(timeout=4.0, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:4]:
                        articles.append({
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "source": "Google News"
                        })
        except Exception as e:
            print(f"[NewsService] Google News RSS error: {e}")
        return articles

    def fetch_yahoo_finance_news(self, base_symbol: str) -> List[Dict[str, str]]:
        articles = []
        try:
            import yfinance as yf
            from mt5_service import YF_TICKER_MAP
            ticker_str = YF_TICKER_MAP.get(base_symbol.upper())
            if ticker_str:
                ticker = yf.Ticker(ticker_str)
                news = ticker.news
                if news:
                    for n in news[:4]:
                        title = n.get("title") or (n.get("content", {}).get("title") if isinstance(n.get("content"), dict) else "")
                        if title:
                            articles.append({
                                "title": title,
                                "source": "Yahoo Finance"
                            })
        except Exception as e:
            print(f"[NewsService] Yahoo Finance news error: {e}")
        return articles

    def fetch_financialjuice_news(self) -> List[Dict[str, str]]:
        """
        Fetches breaking financial news & squawk headlines from FinancialJuice.com feed
        """
        url = "https://www.financialjuice.com/feed.ashx"
        articles = []
        try:
            with httpx.Client(timeout=6.0, headers=self.headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:6]:
                        title = entry.get("title", "")
                        if title.startswith("FinancialJuice: "):
                            title = title[len("FinancialJuice: "):]
                        articles.append({
                            "title": title,
                            "link": entry.get("link", ""),
                            "source": "FinancialJuice"
                        })
        except Exception as e:
            print(f"[NewsService] FinancialJuice fetch error: {e}")
        return articles

    def get_aggregated_news(self, base_symbol: str, news_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        global _NEWS_CACHE, _NEWS_CACHE_TIME
        sym_key = (base_symbol or "MARKET").upper()
        now_ts = time.time()

        # Check Cache
        if sym_key in _NEWS_CACHE:
            if now_ts - _NEWS_CACHE_TIME.get(sym_key, 0) < _NEWS_CACHE_TTL:
                return _NEWS_CACHE[sym_key]

        if news_config is None:
            news_config = {
                "forex_factory": True,
                "financialjuice": True,
                "forex_live": True,
                "yahoo_finance": True,
                "google_news": True,
                "msn_money": True
            }

        forex_factory_data = {"has_imminent_high_impact": False, "imminent_events": [], "upcoming_events": []}
        all_headlines = []

        # Run independent fetchers in parallel using ThreadPoolExecutor
        tasks = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            if news_config.get("forex_factory", True):
                tasks["ff"] = executor.submit(self.fetch_forex_factory_calendar)
            if news_config.get("financialjuice", True):
                tasks["fj"] = executor.submit(self.fetch_financialjuice_news)
            if news_config.get("forex_live", True):
                tasks["fl"] = executor.submit(self.fetch_forexlive_rss)
            if news_config.get("yahoo_finance", True):
                tasks["yf"] = executor.submit(self.fetch_yahoo_finance_news, base_symbol)
            if news_config.get("google_news", True):
                tasks["gn"] = executor.submit(self.fetch_google_news_rss, base_symbol)

            # Gather results with per-task safety timeout
            for key, future in tasks.items():
                try:
                    res = future.result(timeout=4.0)
                    if key == "ff" and isinstance(res, dict):
                        forex_factory_data = res
                    elif isinstance(res, list):
                        all_headlines.extend(res)
                except Exception as ex:
                    print(f"[NewsService] Worker '{key}' timeout or error: {ex}")

        # Build clean narrative summary
        imminent = forex_factory_data.get("imminent_events", [])
        if forex_factory_data.get("has_imminent_high_impact"):
            calendar_status = f"HIGH RISK: High impact economic news within 30 min ({', '.join(imminent)}). Trade pause recommended."
        else:
            calendar_status = "No high-impact economic calendar events in the immediate 30-minute window."

        headlines_text = "\n".join([f"- [{h.get('source', 'News')}] {h.get('title', '')}" for h in all_headlines[:8]])
        if not headlines_text:
            headlines_text = "- Steady macroeconomic conditions; no immediate breaking volatility triggers detected."

        result = {
            "calendar_status": calendar_status,
            "has_imminent_high_impact": forex_factory_data.get("has_imminent_high_impact", False),
            "imminent_events": imminent,
            "headlines": all_headlines[:10],
            "headlines_summary": headlines_text
        }

        # Cache result
        _NEWS_CACHE[sym_key] = result
        _NEWS_CACHE_TIME[sym_key] = now_ts

        return result

news_service = NewsService()
