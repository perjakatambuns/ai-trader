import os
import json
from pathlib import Path
from typing import Dict, Any

CONFIG_FILE_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "auth": {
        "username": "admin",
        "password": "password123",
        "jwt_secret": "ai-trade-secret-token-key-2026-secure-trading",
        "jwt_algorithm": "HS256",
        "token_expire_minutes": 1440
    },
    "database": {
        "type": "sqlite",
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "ai_trade",
        "url": os.getenv("DATABASE_URL", "sqlite:///./ai_trade.db")
    },
    "app_settings": {
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "llm_api_key": os.getenv("OPENAI_API_KEY", ""),
        "llm_base_url": os.getenv("LLM_BASE_URL", ""),
        "mt5_account": os.getenv("MT5_ACCOUNT", "12345678"),
        "mt5_password": os.getenv("MT5_PASSWORD", "demo_password"),
        "mt5_server": os.getenv("MT5_SERVER", "HFMarkets-Demo"),
        "default_spread_pips": 1.4,
        "max_risk_percentage": 1.0,
        "news_config": {
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
        }
    }
}

def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with default if keys missing
            for key in DEFAULT_CONFIG:
                if key not in data:
                    data[key] = DEFAULT_CONFIG[key]
            return data
    except Exception as e:
        print(f"[Config] Error loading config: {e}. Using defaults.")
        return DEFAULT_CONFIG

def save_config(config_data: Dict[str, Any]) -> bool:
    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"[Config] Error saving config: {e}")
        return False

def update_password(new_password: str) -> bool:
    conf = load_config()
    conf["auth"]["password"] = new_password
    return save_config(conf)

def get_auth_config() -> Dict[str, Any]:
    return load_config().get("auth", DEFAULT_CONFIG["auth"])

def get_database_url() -> str:
    # Environment variable has top priority
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    conf = load_config()
    db_conf = conf.get("database", {})
    db_type = db_conf.get("type", "sqlite").lower()

    if db_type == "mysql":
        host = db_conf.get("host", "localhost")
        port = db_conf.get("port", 3306)
        user = db_conf.get("user", "root")
        password = db_conf.get("password", "")
        database = db_conf.get("database", "ai_trade")
        # Ensure password URL encoded if contains special chars
        from urllib.parse import quote_plus
        safe_pass = quote_plus(str(password))
        return f"mysql+pymysql://{user}:{safe_pass}@{host}:{port}/{database}?charset=utf8mb4"

    return db_conf.get("url", "sqlite:///./ai_trade.db")
