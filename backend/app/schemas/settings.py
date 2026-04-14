from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


class SettingsUpdate(BaseModel):
    default_interval: Optional[int] = None
    max_concurrent_checks: Optional[int] = None
    request_timeout: Optional[int] = None
    default_video_count: Optional[int] = None
    site_name: Optional[str] = None
    logo_image: Optional[str] = None
    # Backup & notification fields
    backup_enabled: Optional[bool] = None
    backup_interval_hours: Optional[int] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_sender: Optional[str] = None
    email_recipient: Optional[str] = None
    smtp_use_tls: Optional[bool] = None


class SettingsResponse(BaseModel):
    id: int
    default_interval: int
    max_concurrent_checks: int
    request_timeout: int
    default_video_count: int
    site_name: str
    logo_image: Optional[str]
    updated_at: datetime
    # Backup & notification fields
    backup_enabled: bool
    backup_interval_hours: int
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_sender: str
    email_recipient: str
    smtp_use_tls: bool

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def mask_sensitive_fields(self) -> "SettingsResponse":
        self.telegram_bot_token = "********" if self.telegram_bot_token else ""
        self.smtp_password = "********" if self.smtp_password else ""
        return self
