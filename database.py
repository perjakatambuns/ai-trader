import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import get_database_url

Base = declarative_base()

def get_engine():
    db_url = get_database_url()
    try:
        if db_url.startswith("sqlite"):
            engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False}
            )
        else:
            # Remote MySQL Engine with pre-ping, auto-recycle, and network timeout
            engine = create_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_recycle=1800,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 10}
            )
        # Test connection
        with engine.connect() as conn:
            pass
        print(f"[Database] Successfully connected to {db_url.split('@')[-1] if '@' in db_url else 'SQLite'}")
        return engine
    except Exception as e:
        print(f"[Database] Could not connect to remote database ({e}). Falling back to local SQLite.")
        fallback_url = "sqlite:///./ai_trade.db"
        return create_engine(fallback_url, connect_args={"check_same_thread": False})

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
