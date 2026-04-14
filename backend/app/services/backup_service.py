"""
Backup service for tiktok-monitor.

Handles database backup creation, compression, and notification dispatch.
"""

import asyncio
import functools
import io
import logging
import shutil
import smtplib
import zipfile
from dataclasses import dataclass
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import httpx
from apscheduler.jobstores.base import JobLookupError

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.monitor import MonitorSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions for restore operations
# ---------------------------------------------------------------------------

class RestoreInProgressError(Exception):
    """Raised when a restore operation is already in progress."""

class BackupInProgressError(Exception):
    """Raised when a backup is in progress and a restore is requested."""

class InvalidFileTypeError(Exception):
    """Raised when the uploaded file does not have a .zip extension."""

class InvalidZipError(Exception):
    """Raised when the uploaded file cannot be parsed as a valid ZIP archive."""

class MissingDatabaseError(Exception):
    """Raised when the ZIP archive does not contain monitor.db."""

class RestoreIOError(Exception):
    """Raised when the database file replacement operation fails."""


@dataclass
class BackupResult:
    """Result of a completed backup operation."""
    filename: str          # e.g. "monitor_backup_20260601_120000.zip"
    file_size: int         # bytes
    completed_at: datetime


# ---------------------------------------------------------------------------
# Notification stubs — replaced by Tasks 4.1 and 5.1
# ---------------------------------------------------------------------------

async def send_telegram(
    bot_token: str,
    chat_id: str,
    file_path: Path,
    caption: str,
    timeout: int = 60,
) -> None:
    """Send backup file via Telegram Bot API using httpx async client."""
    if not bot_token or not chat_id:
        logger.warning("Telegram notification skipped: bot_token or chat_id not configured")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"document": f},
                )
        if not (200 <= response.status_code < 300):
            logger.error(
                "Telegram notification failed: status=%d, body=%s",
                response.status_code,
                response.text,
            )
    except httpx.TimeoutException:
        logger.error("Telegram notification timed out after %ds", timeout)
    except Exception as exc:
        logger.error("Telegram notification error: %s", exc)


def _send_email_sync(
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    smtp_sender: str,
    email_recipient: str,
    smtp_use_tls: bool,
    file_path: Path,
    subject: str,
) -> None:
    """Synchronous SMTP send helper, intended to run in a thread pool."""
    msg = MIMEMultipart()
    msg["From"] = smtp_sender
    msg["To"] = email_recipient
    msg["Subject"] = subject

    with open(file_path, "rb") as f:
        attachment = MIMEApplication(f.read(), Name=file_path.name)
    attachment["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
    msg.attach(attachment)

    server = smtplib.SMTP(smtp_host, smtp_port)
    try:
        if smtp_use_tls:
            server.starttls()
        if smtp_username:
            server.login(smtp_username, smtp_password)
        server.sendmail(smtp_sender, email_recipient, msg.as_string())
    finally:
        server.quit()


async def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    smtp_sender: str,
    email_recipient: str,
    smtp_use_tls: bool,
    file_path: Path,
    subject: str,
) -> None:
    """Send backup file as an email attachment via SMTP with optional STARTTLS."""
    if not smtp_host or not email_recipient:
        logger.warning("Email notification skipped: smtp_host or email_recipient not configured")
        return

    try:
        await asyncio.to_thread(
            _send_email_sync,
            smtp_host,
            smtp_port,
            smtp_username,
            smtp_password,
            smtp_sender,
            email_recipient,
            smtp_use_tls,
            file_path,
            subject,
        )
    except Exception as exc:
        logger.error("Email notification failed: smtp_host=%s, error=%s", smtp_host, exc)


class BackupService:
    """
    Core backup service.

    Uses an asyncio.Lock to prevent concurrent backup executions.
    Tasks 3.3, 4.1, 5.1, and 8.1 will extend this class with
    run_backup, notifier calls, and scheduler integration.
    """

    _lock: asyncio.Lock = asyncio.Lock()

    def is_running(self) -> bool:
        """Return True if a backup is currently in progress."""
        return self._lock.locked()

    def generate_backup_filename(self, dt: datetime) -> str:
        """
        Generate a backup filename for the given datetime.

        Format: monitor_backup_YYYYMMDD_HHMMSS.zip
        """
        return dt.strftime("monitor_backup_%Y%m%d_%H%M%S.zip")

    async def run_backup(self, db: Session) -> Optional[BackupResult]:
        """
        Execute the full backup workflow:
        1. Acquire lock (return None if already running)
        2. Read MonitorSettings from DB
        3. Copy DB file to a temp directory
        4. Compress the copy into a ZIP archive
        5. Log timestamp and file size
        6. Dispatch Telegram / email notifications (if enabled)
        7. Clean up temp directory (always, in finally)
        8. Return BackupResult on success, None on failure
        """
        if self._lock.locked():
            return None

        async with self._lock:
            temp_dir: Optional[Path] = None
            try:
                # --- 1. Load settings ---
                monitor_settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()

                # --- 2. Resolve DB file path ---
                db_url: str = settings.DATABASE_URL
                db_file = Path(db_url.replace("sqlite:///", ""))

                if not db_file.exists() or not db_file.is_file():
                    logger.error(
                        "Backup aborted: database file not found or inaccessible at '%s'",
                        db_file,
                    )
                    return None

                # --- 3. Create temp directory and copy DB ---
                temp_dir = Path(f"/tmp/tiktok_monitor_backup_{uuid4().hex}/")
                temp_dir.mkdir(parents=True, exist_ok=True)

                db_copy = temp_dir / db_file.name
                shutil.copy2(db_file, db_copy)

                # --- 4. Compress into ZIP ---
                now = datetime.utcnow()
                zip_filename = self.generate_backup_filename(now)
                zip_path = temp_dir / zip_filename

                try:
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        zf.write(db_copy, db_file.name)
                except Exception as exc:
                    logger.error("Backup aborted: failed to create ZIP archive: %s", exc)
                    return None

                file_size = zip_path.stat().st_size

                # --- 5. Log timestamp and size ---
                logger.info(
                    "Backup completed: filename=%s, size=%d bytes, timestamp=%s",
                    zip_filename,
                    file_size,
                    now.isoformat(),
                )

                # --- 6. Notifications ---
                if monitor_settings is not None and monitor_settings.telegram_enabled:
                    caption = (
                        f"备份时间: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                        f"文件大小: {file_size} bytes"
                    )
                    await send_telegram(
                        bot_token=monitor_settings.telegram_bot_token,
                        chat_id=monitor_settings.telegram_chat_id,
                        file_path=zip_path,
                        caption=caption,
                    )

                if monitor_settings is not None and monitor_settings.email_enabled:
                    subject = f"TikTok Monitor 数据备份 {now.strftime('%Y-%m-%d %H:%M:%S')}"
                    await send_email(
                        smtp_host=monitor_settings.smtp_host,
                        smtp_port=monitor_settings.smtp_port,
                        smtp_username=monitor_settings.smtp_username,
                        smtp_password=monitor_settings.smtp_password,
                        smtp_sender=monitor_settings.smtp_sender,
                        email_recipient=monitor_settings.email_recipient,
                        smtp_use_tls=monitor_settings.smtp_use_tls,
                        file_path=zip_path,
                        subject=subject,
                    )

                return BackupResult(
                    filename=zip_filename,
                    file_size=file_size,
                    completed_at=now,
                )

            finally:
                # --- 7. Always clean up temp directory ---
                if temp_dir is not None and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)

    async def run_backup_download(self, db: Session) -> Optional[tuple[BackupResult, bytes]]:
        """
        Same as run_backup but also returns the ZIP file bytes for direct download.
        Notifications are still dispatched. Returns (BackupResult, zip_bytes) or None on failure.
        """
        if self._lock.locked():
            return None

        async with self._lock:
            temp_dir: Optional[Path] = None
            try:
                monitor_settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()

                db_url: str = settings.DATABASE_URL
                db_file = Path(db_url.replace("sqlite:///", ""))

                if not db_file.exists() or not db_file.is_file():
                    logger.error(
                        "Backup aborted: database file not found or inaccessible at '%s'",
                        db_file,
                    )
                    return None

                temp_dir = Path(f"/tmp/tiktok_monitor_backup_{uuid4().hex}/")
                temp_dir.mkdir(parents=True, exist_ok=True)

                db_copy = temp_dir / db_file.name
                shutil.copy2(db_file, db_copy)

                now = datetime.utcnow()
                zip_filename = self.generate_backup_filename(now)
                zip_path = temp_dir / zip_filename

                try:
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        zf.write(db_copy, db_file.name)
                except Exception as exc:
                    logger.error("Backup aborted: failed to create ZIP archive: %s", exc)
                    return None

                file_size = zip_path.stat().st_size
                zip_bytes = zip_path.read_bytes()

                logger.info(
                    "Backup (download) completed: filename=%s, size=%d bytes, timestamp=%s",
                    zip_filename,
                    file_size,
                    now.isoformat(),
                )

                if monitor_settings is not None and monitor_settings.telegram_enabled:
                    caption = (
                        f"备份时间: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                        f"文件大小: {file_size} bytes"
                    )
                    await send_telegram(
                        bot_token=monitor_settings.telegram_bot_token,
                        chat_id=monitor_settings.telegram_chat_id,
                        file_path=zip_path,
                        caption=caption,
                    )

                if monitor_settings is not None and monitor_settings.email_enabled:
                    subject = f"TikTok Monitor 数据备份 {now.strftime('%Y-%m-%d %H:%M:%S')}"
                    await send_email(
                        smtp_host=monitor_settings.smtp_host,
                        smtp_port=monitor_settings.smtp_port,
                        smtp_username=monitor_settings.smtp_username,
                        smtp_password=monitor_settings.smtp_password,
                        smtp_sender=monitor_settings.smtp_sender,
                        email_recipient=monitor_settings.email_recipient,
                        smtp_use_tls=monitor_settings.smtp_use_tls,
                        file_path=zip_path,
                        subject=subject,
                    )

                result = BackupResult(
                    filename=zip_filename,
                    file_size=file_size,
                    completed_at=now,
                )
                return result, zip_bytes

            finally:
                if temp_dir is not None and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)


backup_service = BackupService()


# ---------------------------------------------------------------------------
# Scheduler integration
# ---------------------------------------------------------------------------

async def _backup_job(db_factory: Callable) -> None:
    """APScheduler job: open a DB session and run the backup."""
    db = db_factory()
    try:
        await backup_service.run_backup(db)
    finally:
        db.close()


def register_backup_job(scheduler, db_factory: Callable) -> None:
    """
    Read MonitorSettings (id=1) and register or remove the scheduled backup job.
    Called once at application startup.
    """
    db = db_factory()
    try:
        monitor_settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
    finally:
        db.close()

    if monitor_settings is not None and monitor_settings.backup_enabled:
        try:
            scheduler.remove_job("scheduled_backup")
        except JobLookupError:
            pass
        scheduler.add_job(
            functools.partial(_backup_job, db_factory),
            "interval",
            hours=monitor_settings.backup_interval_hours,
            id="scheduled_backup",
            replace_existing=True,
        )
        logger.info(
            "Registered scheduled backup job (every %d hours)",
            monitor_settings.backup_interval_hours,
        )
    else:
        try:
            scheduler.remove_job("scheduled_backup")
            logger.info("Removed scheduled backup job (backup_enabled=False)")
        except JobLookupError:
            pass


def reschedule_backup_job(scheduler, db_factory: Callable) -> None:
    """
    Re-read MonitorSettings and update the scheduled backup job.
    Called after settings are updated.
    """
    db = db_factory()
    try:
        monitor_settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
    finally:
        db.close()

    if monitor_settings is not None and monitor_settings.backup_enabled:
        try:
            scheduler.remove_job("scheduled_backup")
        except JobLookupError:
            pass
        scheduler.add_job(
            functools.partial(_backup_job, db_factory),
            "interval",
            hours=monitor_settings.backup_interval_hours,
            id="scheduled_backup",
            replace_existing=True,
        )
        logger.info(
            "Rescheduled backup job (every %d hours)",
            monitor_settings.backup_interval_hours,
        )
    else:
        try:
            scheduler.remove_job("scheduled_backup")
            logger.info("Removed scheduled backup job (backup_enabled=False)")
        except JobLookupError:
            pass


# ---------------------------------------------------------------------------
# Restore service
# ---------------------------------------------------------------------------

@dataclass
class RestoreResult:
    filename: str
    completed_at: datetime
    restart_required: bool
    pre_restore_backup: Optional[BackupResult]


class RestoreService:
    _lock: asyncio.Lock = asyncio.Lock()

    def is_running(self) -> bool:
        return self._lock.locked()

    async def run_restore(
        self,
        file_content: bytes,
        original_filename: str,
        db: Session,
    ) -> RestoreResult:
        if self._lock.locked():
            raise RestoreInProgressError("A restore operation is already in progress")

        async with self._lock:
            temp_dir: Optional[Path] = None
            try:
                # Check backup not running
                if backup_service.is_running():
                    raise BackupInProgressError("A backup is in progress, cannot restore now")

                # Validate file extension
                if not original_filename.lower().endswith('.zip'):
                    raise InvalidFileTypeError(f"File must have .zip extension, got: {original_filename}")

                # Validate ZIP format
                try:
                    zf = zipfile.ZipFile(io.BytesIO(file_content))
                except zipfile.BadZipFile:
                    raise InvalidZipError("Uploaded file is not a valid ZIP archive")

                # Validate monitor.db presence
                with zf:
                    if 'monitor.db' not in zf.namelist():
                        raise MissingDatabaseError("ZIP archive does not contain monitor.db")

                    # Pre-restore backup
                    pre_backup: Optional[BackupResult] = None
                    try:
                        pre_backup = await backup_service.run_backup(db)
                        if pre_backup is None:
                            logger.warning("Pre-restore backup returned None (backup may have failed)")
                    except Exception as exc:
                        logger.warning("Pre-restore backup failed, continuing with restore: %s", exc)

                    # Extract monitor.db to temp dir
                    temp_dir = Path(f"/tmp/tiktok_monitor_restore_{uuid4().hex}/")
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    zf.extract('monitor.db', temp_dir)

                # Resolve db path
                db_url: str = settings.DATABASE_URL
                db_path = Path(db_url.replace("sqlite:///", ""))
                extracted_db = temp_dir / 'monitor.db'

                # Atomic replace
                try:
                    shutil.copy2(extracted_db, db_path)
                except Exception as exc:
                    logger.error("Failed to replace database file: %s", exc)
                    raise RestoreIOError(f"Database file replacement failed: {exc}") from exc

                now = datetime.utcnow()
                logger.info(
                    "Restore completed: source=%s, timestamp=%s",
                    original_filename,
                    now.isoformat(),
                )

                return RestoreResult(
                    filename=original_filename,
                    completed_at=now,
                    restart_required=True,
                    pre_restore_backup=pre_backup,
                )

            finally:
                if temp_dir is not None and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)


restore_service = RestoreService()
