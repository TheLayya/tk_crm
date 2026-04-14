from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from app.core.database import engine, Base
from app.core.scheduler import start_scheduler, stop_scheduler, scheduler
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.config import settings
from app.models.team import User
from app.api import projects, accounts, history, proxies, videos, import_export, op_accounts, auth, team
from app.api import settings as settings_router
from app.api import backup as backup_router
from app.middleware.rate_limit import limiter
from app.middleware.operation_log import OperationLogMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import logging

logging.basicConfig(level=logging.INFO)


def create_super_admin(db: Session) -> None:
    """如果不存在超级管理员，则创建默认 admin 账号。"""
    exists = db.query(User).filter(User.is_super_admin == True).first()
    if not exists:
        admin = User(
            username="admin",
            password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
            is_super_admin=True,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        logging.info("超级管理员 admin 已创建")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建数据库表
    Base.metadata.create_all(bind=engine)
    # 初始化超级管理员
    db = SessionLocal()
    try:
        create_super_admin(db)
    finally:
        db.close()
    # 注册并启动定时监控任务
    from app.services.monitor_service import register_scheduler_jobs
    register_scheduler_jobs(scheduler, SessionLocal)
    start_scheduler()
    from app.services.backup_service import register_backup_job
    register_backup_job(scheduler, SessionLocal)
    yield
    stop_scheduler()


app = FastAPI(
    title="TikTok Monitor",
    version="1.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(OperationLogMiddleware)

# Register API routers
# Note: import_export must be registered before accounts to avoid route conflicts
# (export/import-file are more specific than {account_id})
app.include_router(projects.router, prefix="/api")
app.include_router(import_export.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(proxies.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(op_accounts.router, prefix="/api/op-accounts", tags=["op-accounts"])
app.include_router(auth.router, prefix="/api")
app.include_router(team.router, prefix="/api")
app.include_router(backup_router.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
