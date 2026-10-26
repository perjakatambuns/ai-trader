-- Database Schema for AI Trading Copilot
-- Target Database: MySQL 8.0+

CREATE DATABASE IF NOT EXISTS ai_trade CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_trade;

-- 1. Tabel app_settings (Konfigurasi Global)
CREATE TABLE IF NOT EXISTS app_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    llm_provider ENUM('openai', 'claude') NOT NULL DEFAULT 'openai',
    llm_api_key VARCHAR(255) DEFAULT '',
    llm_base_url VARCHAR(255) DEFAULT '',
    llm_model VARCHAR(100) DEFAULT 'gpt-4o',
    mt5_account VARCHAR(100) DEFAULT '',
    mt5_password VARCHAR(255) DEFAULT '',
    mt5_server VARCHAR(100) DEFAULT 'HFMarkets-Demo',
    default_spread_pips DECIMAL(5, 2) DEFAULT 1.40,
    max_risk_percentage DECIMAL(5, 2) DEFAULT 1.00,
    news_config JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 2. Tabel trading_symbols (Daftar Simbol yang Dipantau)
CREATE TABLE IF NOT EXISTS trading_symbols (
    id INT PRIMARY KEY AUTO_INCREMENT,
    mt5_symbol VARCHAR(50) NOT NULL UNIQUE,
    base_symbol VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    pip_size DECIMAL(10, 5) DEFAULT 0.0001
);

-- 3. Tabel analysis_history (Riwayat Analisa & Eksekusi)
CREATE TABLE IF NOT EXISTS analysis_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(50) NOT NULL,
    account_balance DECIMAL(15, 2) NOT NULL,
    action VARCHAR(20) NOT NULL, -- BUY_LIMIT, SELL_LIMIT, WAIT
    entry_price DECIMAL(15, 5) DEFAULT 0.0,
    stop_loss DECIMAL(15, 5) DEFAULT 0.0,
    take_profit DECIMAL(15, 5) DEFAULT 0.0,
    calculated_lot DECIMAL(10, 2) DEFAULT 0.01,
    risk_percentage DECIMAL(5, 2) DEFAULT 1.00,
    confidence_score INT DEFAULT 80,
    risk_reward_ratio VARCHAR(20) DEFAULT '1:2.0',
    ai_summary TEXT,
    news_summary TEXT,
    seasonality_note TEXT,
    execution_status ENUM('PENDING_USER', 'EXECUTED', 'REJECTED', 'EXPIRED') DEFAULT 'PENDING_USER',
    mt5_ticket_id VARCHAR(100) NULL
);

-- Initial default symbols
INSERT INTO trading_symbols (mt5_symbol, base_symbol, display_name, is_active, pip_size) VALUES
('XAUUSDc', 'XAUUSD', 'Gold (Cent Account)', 1, 0.01),
('EURUSDc', 'EURUSD', 'EUR/USD (Cent Account)', 1, 0.0001),
('USDJPYc', 'USDJPY', 'USD/JPY (Cent Account)', 1, 0.01),
('GBPUSDc', 'GBPUSD', 'GBP/USD (Cent Account)', 1, 0.0001),
('XAUUSD', 'XAUUSD', 'Gold (Standard)', 1, 0.01),
('EURUSD', 'EURUSD', 'EUR/USD (Standard)', 1, 0.0001)
ON DUPLICATE KEY UPDATE display_name=VALUES(display_name);
