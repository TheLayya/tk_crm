import re
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/monitor.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # JWT 认证
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 敏感字段加密（AES-256-GCM，64位hex = 32字节）
    FIELD_ENCRYPTION_KEY: str = ""

    # 超级管理员
    SUPER_ADMIN_PASSWORD: str = "admin123456"

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.FIELD_ENCRYPTION_KEY:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", self.FIELD_ENCRYPTION_KEY):
                raise ValueError(
                    "FIELD_ENCRYPTION_KEY 格式不正确，必须为 64 位 hex 字符串（32 字节）"
                )
        else:
            raise ValueError(
                "FIELD_ENCRYPTION_KEY 未配置，系统拒绝启动。请在环境变量中设置 64 位 hex 字符串。"
            )


settings = Settings()
