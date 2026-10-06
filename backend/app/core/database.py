import os
from collections.abc import Generator
from sqlite3 import Connection
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.pool import ConnectionPoolEntry
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
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: Connection, _connection_record: ConnectionPoolEntry) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
