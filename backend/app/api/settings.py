"""
MonitorSettings CRUD API endpoints
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.scheduler import scheduler
from app.schemas.settings import SettingsUpdate, SettingsResponse
from app.models.monitor import MonitorSettings
from app.services.auth_service import require_permission
from app.services.backup_service import reschedule_backup_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


def get_or_create_settings(db: Session) -> MonitorSettings:
    """
    Get the singleton MonitorSettings record (id=1), creating it if it doesn't exist.
    
    **Validates: Requirements 6.1, 6.3**
    
    - Maintains unique MonitorSettings record (6.1)
    - Auto-creates default settings on init (6.3)
    """
    settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
    if not settings:
        # Create default settings
        settings = MonitorSettings(
            id=1,
            default_interval=14400,  # 4 hours in seconds
            max_concurrent_checks=5,
            request_timeout=30,
            default_video_count=20,
            site_name="TikTok Monitor",
            logo_image=None
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
        logger.info("Created default MonitorSettings")
    return settings


@router.get("/public", response_model=SettingsResponse)
def get_public_settings(db: Session = Depends(get_db)):
    """公开接口：返回站点名称和 logo，不需要登录。"""
    try:
        return get_or_create_settings(db)
    except Exception as e:
        logger.error(f"Failed to get public settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )


@router.get("", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db), _=Depends(require_permission("settings:view"))):
    """
    Get current monitor settings.
    
    **Validates: Requirements 6.1, 6.3, 6.4**
    
    - Returns the unique MonitorSettings record (6.1)
    - Auto-creates default settings if not exists (6.3)
    - Provides read interface for frontend display/edit (6.4)
    """
    try:
        settings = get_or_create_settings(db)
        return settings
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )


@router.put("", response_model=SettingsResponse)
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db), _=Depends(require_permission("settings:edit"))):
    """
    Update monitor settings.
    
    **Validates: Requirements 6.1, 6.2**
    
    - Updates the unique MonitorSettings record (6.1)
    - Persists changes and takes effect next cycle (6.2)
    """
    try:
        settings = get_or_create_settings(db)
        
        # Update only provided fields
        if data.default_interval is not None:
            if data.default_interval <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="default_interval must be positive"
                )
            settings.default_interval = data.default_interval
        
        if data.max_concurrent_checks is not None:
            if data.max_concurrent_checks <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="max_concurrent_checks must be positive"
                )
            settings.max_concurrent_checks = data.max_concurrent_checks
        
        if data.request_timeout is not None:
            if data.request_timeout <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="request_timeout must be positive"
                )
            settings.request_timeout = data.request_timeout
        
        if data.default_video_count is not None:
            if data.default_video_count <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="default_video_count must be positive"
                )
            settings.default_video_count = data.default_video_count
        
        if data.site_name is not None:
            settings.site_name = data.site_name
        
        # Allow clearing logo by passing empty string or None
        if data.logo_image is not None:
            settings.logo_image = data.logo_image if data.logo_image else None

        # Backup & notification fields
        if data.backup_enabled is not None:
            settings.backup_enabled = data.backup_enabled
        if data.backup_interval_hours is not None:
            if not (1 <= data.backup_interval_hours <= 168):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="backup_interval_hours must be between 1 and 168 (inclusive)"
                )
            settings.backup_interval_hours = data.backup_interval_hours
        if data.telegram_enabled is not None:
            settings.telegram_enabled = data.telegram_enabled
        if data.telegram_bot_token is not None:
            settings.telegram_bot_token = data.telegram_bot_token
        if data.telegram_chat_id is not None:
            settings.telegram_chat_id = data.telegram_chat_id
        if data.email_enabled is not None:
            settings.email_enabled = data.email_enabled
        if data.smtp_host is not None:
            settings.smtp_host = data.smtp_host
        if data.smtp_port is not None:
            settings.smtp_port = data.smtp_port
        if data.smtp_username is not None:
            settings.smtp_username = data.smtp_username
        if data.smtp_password is not None:
            settings.smtp_password = data.smtp_password
        if data.smtp_sender is not None:
            settings.smtp_sender = data.smtp_sender
        if data.email_recipient is not None:
            settings.email_recipient = data.email_recipient
        if data.smtp_use_tls is not None:
            settings.smtp_use_tls = data.smtp_use_tls

        db.commit()
        db.refresh(settings)

        # Reschedule backup job if backup scheduling fields changed
        if data.backup_enabled is not None or data.backup_interval_hours is not None:
            reschedule_backup_job(scheduler, SessionLocal)

        logger.info(f"Updated MonitorSettings: {settings.id}")
        return settings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )
