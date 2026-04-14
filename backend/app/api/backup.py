"""
Backup API endpoints
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.auth_service import require_permission
from app.services.backup_service import (
    BackupInProgressError,
    InvalidFileTypeError,
    InvalidZipError,
    MissingDatabaseError,
    RestoreIOError,
    RestoreInProgressError,
    backup_service,
    restore_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["Backup"])


class BackupTriggerResponse(BaseModel):
    filename: str
    file_size: int  # bytes
    completed_at: datetime


class PreRestoreBackupInfo(BaseModel):
    filename: str
    file_size: int  # bytes


class RestoreResponse(BaseModel):
    filename: str
    completed_at: datetime
    restart_required: bool
    pre_restore_backup: Optional[PreRestoreBackupInfo]


@router.post("/trigger")
async def trigger_backup(
    db: Session = Depends(get_db),
    _=Depends(require_permission("settings:edit")),
):
    """
    手动触发备份，直接返回 ZIP 文件供浏览器下载。
    - 需要 settings:edit 权限
    - 若备份或恢复正在进行，返回 HTTP 409
    """
    if backup_service.is_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="备份正在进行中，请稍后再试",
        )

    if restore_service.is_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="恢复正在进行中，请稍后再试",
        )

    result = await backup_service.run_backup_download(db)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="备份失败，请查看日志",
        )

    backup_result, zip_bytes = result

    import io as _io
    return StreamingResponse(
        _io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{backup_result.filename}"',
            "Content-Length": str(backup_result.file_size),
        },
    )


@router.post("/restore", response_model=RestoreResponse)
async def restore_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_permission("settings:edit")),
):
    """
    上传备份文件并恢复数据库。
    - 需要 settings:edit 权限
    - 恢复前自动备份当前数据库
    - 成功返回 filename、completed_at、restart_required=True、pre_restore_backup
    """
    file_content = await file.read()
    original_filename = file.filename or "upload.zip"

    try:
        result = await restore_service.run_restore(file_content, original_filename, db)
    except RestoreInProgressError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="恢复正在进行中，请稍后再试")
    except BackupInProgressError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="备份正在进行中，请稍后再试")
    except InvalidFileTypeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件必须是 .zip 格式")
    except InvalidZipError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="上传的文件不是有效的 ZIP 压缩包")
    except MissingDatabaseError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ZIP 压缩包中不包含 monitor.db 文件")
    except RestoreIOError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库替换失败：{exc}")

    pre_backup_info = None
    if result.pre_restore_backup is not None:
        pre_backup_info = PreRestoreBackupInfo(
            filename=result.pre_restore_backup.filename,
            file_size=result.pre_restore_backup.file_size,
        )

    return RestoreResponse(
        filename=result.filename,
        completed_at=result.completed_at,
        restart_required=result.restart_required,
        pre_restore_backup=pre_backup_info,
    )
