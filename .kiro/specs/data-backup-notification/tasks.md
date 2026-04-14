# Implementation Plan: Data Backup & Notification

## Overview

Incrementally implement the data backup and notification feature for tiktok-monitor. The plan starts with the database schema, then builds the core backup service, notifiers, API endpoint, scheduler integration, settings extension, and finally the frontend UI.

## Tasks

- [x] 1. Add backup configuration fields to the database schema
  - Create an Alembic migration that adds all 13 backup fields to the `monitor_settings` table with the default values specified in the design
  - _Requirements: 6.1_

- [x] 2. Extend Pydantic schemas and SQLAlchemy model for backup settings
  - [x] 2.1 Add backup fields to `MonitorSettings` SQLAlchemy model (`backend/app/models/monitor.py`)
    - Add all 13 columns matching the migration
    - _Requirements: 6.1_
  - [x] 2.2 Extend `SettingsUpdate` and `SettingsResponse` schemas (`backend/app/schemas/settings.py`)
    - All fields `Optional` in `SettingsUpdate`
    - `telegram_bot_token` and `smtp_password` masked in `SettingsResponse` (return `"********"` when set, `""` when empty)
    - _Requirements: 6.2, 6.5_
  - [ ]* 2.3 Write property test for sensitive field masking
    - **Property 9: 敏感字段脱敏**
    - **Validates: Requirements 6.5**
    - Use `@given(st.text(min_size=1))` to verify that any non-empty token/password is always returned as `"********"` and empty values return `""`
  - [ ]* 2.4 Write property test for settings response field completeness
    - **Property 8: 设置响应包含所有备份配置字段**
    - **Validates: Requirements 6.2**
    - Use `@given(settings_strategy())` to verify all 13 backup fields are present in every `SettingsResponse`

- [x] 3. Implement `BackupService` with file generation logic (`backend/app/services/backup_service.py`)
  - [x] 3.1 Implement `BackupResult` dataclass and `generate_backup_filename` method
    - Format: `monitor_backup_YYYYMMDD_HHMMSS.zip`
    - _Requirements: 1.2_
  - [ ]* 3.2 Write property test for backup filename format
    - **Property 1: 备份文件名格式**
    - **Validates: Requirements 1.2**
    - Use `@given(st.datetimes())` to verify the filename always matches the expected pattern
  - [x] 3.3 Implement `run_backup` core flow: copy DB to temp dir, compress to ZIP, log timestamp and size, clean up temp files
    - Use `asyncio.Lock` to prevent concurrent backups
    - Handle missing/inaccessible DB file: log ERROR and abort without raising
    - Handle ZIP failure: log ERROR, clean up, abort
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [ ]* 3.4 Write property test for temporary file cleanup
    - **Property 2: 备份完成后无临时文件残留**
    - **Validates: Requirements 1.5**
    - Use `@given(st.booleans())` to simulate success/failure paths and assert no temp files remain after `run_backup` completes

- [x] 4. Implement `TelegramNotifier` (`send_telegram` function in `backup_service.py`)
  - [x] 4.1 Implement `send_telegram` using `httpx` async client
    - Send file via `sendDocument` API, 60-second timeout
    - Log ERROR on non-2xx; log WARNING and skip when token/chat_id empty; do not raise exceptions
    - _Requirements: 3.1, 3.3, 3.4, 3.5_
  - [ ]* 4.2 Write property test for Telegram caption content
    - **Property 4: Telegram 通知 caption 包含必要信息**
    - **Validates: Requirements 3.2**
    - Use `@given(st.datetimes(), st.integers(min_value=0))` to verify caption always contains timestamp and file size representations

- [x] 5. Implement `EmailNotifier` (`send_email` function in `backup_service.py`)
  - [x] 5.1 Implement `send_email` using `smtplib` with STARTTLS support
    - Use all SMTP config fields from `MonitorSettings`
    - Log ERROR on SMTP failure; log WARNING and skip when host/recipient empty; do not raise exceptions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ]* 5.2 Write property test for SMTP config passthrough
    - **Property 6: SMTP 配置完整传递**
    - **Validates: Requirements 4.2**
    - Use `@given(smtp_config_strategy())` to verify all config values are passed exactly to the SMTP connection
  - [ ]* 5.3 Write property test for email failure not blocking backup
    - **Property 5: 邮件通知失败不阻断备份流程**
    - **Validates: Requirements 4.4**
    - Use `@given(st.sampled_from([...smtp_errors...]))` to verify `run_backup` returns a valid `BackupResult` regardless of SMTP error type

- [x] 6. Checkpoint — Ensure all backend service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Backup API endpoint (`backend/app/api/backup.py`)
  - [x] 7.1 Create `BackupTriggerResponse` Pydantic schema and `POST /backup/trigger` router
    - Require `settings:edit` permission via `require_permission` dependency
    - Return HTTP 409 if `BackupService.is_running()` is True
    - Return `filename`, `file_size`, `completed_at` on success
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [ ]* 7.2 Write property test for trigger response field completeness
    - **Property 7: 手动触发响应包含完整字段**
    - **Validates: Requirements 5.4**
    - Use `@given(backup_result_strategy())` to verify the response always contains all three required fields with correct types
  - [x] 7.3 Register the backup router in `backend/app/main.py`
    - Include `backup.router` with the `/api` prefix alongside existing routers
    - _Requirements: 5.1_

- [x] 8. Integrate scheduler for automatic backups
  - [x] 8.1 Implement `register_backup_job` and `reschedule_backup_job` in `backup_service.py`
    - Read `backup_enabled` and `backup_interval_hours` from `MonitorSettings`
    - Add/replace/remove APScheduler job with id `"scheduled_backup"` accordingly
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 8.2 Call `register_backup_job` during application startup in `backend/app/main.py`
    - _Requirements: 2.1_
  - [x] 8.3 Update `update_settings` in `backend/app/api/settings.py` to call `reschedule_backup_job` when `backup_enabled` or `backup_interval_hours` changes
    - _Requirements: 2.2, 6.4_

- [x] 9. Add `backup_interval_hours` range validation to the Settings API
  - In `backend/app/api/settings.py` (or the `SettingsUpdate` schema), validate that `backup_interval_hours` is between 1 and 168 inclusive; return HTTP 422 with a descriptive message if out of range
  - _Requirements: 2.5, 6.3_
  - [ ]* 9.1 Write property test for interval range validation
    - **Property 3: 备份间隔验证**
    - **Validates: Requirements 2.5, 6.3**
    - Use `@given(st.integers())` to verify values outside [1, 168] always return HTTP 422 and values inside always succeed

- [x] 10. Checkpoint — Ensure all backend API and scheduler tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement frontend backup configuration section (`frontend/src/views/Settings.vue`)
  - [x] 11.1 Add "数据备份" section with controls for all 13 backup configuration fields
    - Render all fields defined in Requirement 6.1 inside the existing settings form
    - _Requirements: 7.1_
  - [x] 11.2 Implement conditional disabling logic for dependent fields
    - Disable (not hide) all backup fields when `backup_enabled` is off
    - Disable Telegram token and chat ID fields when `telegram_enabled` is off
    - Disable all SMTP fields when `email_enabled` is off
    - _Requirements: 7.2, 7.3, 7.4_
  - [x] 11.3 Add "立即备份" button with loading state and result feedback
    - Call `POST /api/backup/trigger` on click
    - Show loading indicator while request is in flight
    - Display success message (filename, size) or error message on completion
    - _Requirements: 7.5_
  - [x] 11.4 Ensure the settings form PUT request includes all backup fields
    - Merge backup fields into the existing form submission payload
    - _Requirements: 7.6_

- [x] 12. Add backup API client function (`frontend/src/api/`)
  - Create `frontend/src/api/backup.js` with a `triggerBackup()` function that calls `POST /api/backup/trigger`
  - _Requirements: 5.1, 7.5_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use [Hypothesis](https://hypothesis.readthedocs.io/) and must be annotated with `# Feature: data-backup-notification, Property {N}: {property_text}`
- Each property test must run a minimum of 100 iterations
- Sensitive fields (`telegram_bot_token`, `smtp_password`) must never be returned in plaintext from any API response
- Backup temp files live under `/tmp/tiktok_monitor_backup_{uuid}/` and must be cleaned up regardless of outcome
