import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# 确保数据目录存在（SQLite 场景）
if settings.DATABASE_URL.startswith("sqlite"):
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

# 增加连接池大小以支持高并发检查（支持并发50+）
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=60,  # 基础连接池大小（支持并发50+）
    max_overflow=40,  # 溢出连接数（总共可达100个连接）
    pool_timeout=120,  # 超时时间（秒）
    pool_pre_ping=True,  # 连接前检查连接是否有效
    pool_recycle=3600  # 每小时回收连接，避免连接过期
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
