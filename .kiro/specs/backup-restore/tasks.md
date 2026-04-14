# Implementation Plan: backup-restore

## Overview

在现有 `backup_service.py` 和 `backup.py` 基础上，新增 `RestoreService`、自定义异常类、`POST /api/backup/restore` 端点，并在前端 `backup.js` 和 `Settings.vue` 中添加恢复操作界面。

## Tasks

- [x] 1. Define custom exception classes
  - Add six exception classes to `backend/app/services/backup_service.py`:
    `RestoreInProgressError`, `BackupInProgressError`, `InvalidFileTypeError`,
    `InvalidZipError`, `MissingDatabaseError`, `RestoreIOError`
  - Each inherits from `Exception` with no extra fields
  - _Requirements: 1.3, 1.4, 1.5, 3.4, 4.1, 4.2_

- [x] 2. Implement RestoreService and run_restore core flow
  - Add `RestoreResult` dataclass and `RestoreService` class to `backend/app/services/backup_service.py`
  - `RestoreResult` fields: `filename: str`, `completed_at: datetime`, `restart_required: bool`, `pre_restore_backup: Optional[BackupResult]`
  - `RestoreService._lock` is an independent `asyncio.Lock`, mutually exclusive with `BackupService._lock`
  - `is_running()` returns `self._lock.locked()`
  - `run_restore(file_content, original_filename, db)` executes in order:
    1. If `_lock` is locked, raise `RestoreInProgressError`
    2. After acquiring lock, check `backup_service.is_running()`, raise `BackupInProgressError` if True
    3. Validate `original_filename.lower().endswith('.zip')`, else raise `InvalidFileTypeError`
    4. Try `zipfile.ZipFile(io.BytesIO(file_content))`, raise `InvalidZipError` on failure
    5. Check `'monitor.db' in zf.namelist()`, else raise `MissingDatabaseError`
    6. Call `backup_service.run_backup(db)`, log WARNING on failure and continue
    7. Create temp dir `/tmp/tiktok_monitor_restore_{uuid4().hex}/`, extract `monitor.db`
    8. Resolve `db_path` from `settings.DATABASE_URL`, use `shutil.copy2` to replace
    9. If `copy2` raises, log ERROR and raise `RestoreIOError`
    10. Log completion (source filename + timestamp)
    11. `finally` block: cleanup temp dir with `shutil.rmtree(ignore_errors=True)`
    12. Return `RestoreResult`
  - Add `restore_service = RestoreService()` singleton at module end
  - _Requirements: 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 5.1, 5.2, 6.1_

- [x] 3. Add concurrency mutex check to backup trigger endpoint
  - Modify `backend/app/api/backup.py`, import `restore_service`
  - After existing `backup_service.is_running()` check, add `restore_service.is_running()` check
  - If restore is running, return HTTP 409 with detail `"恢复正在进行中，请稍后再试"`
  - _Requirements: 4.3_

- [x] 4. Implement POST /api/backup/restore endpoint
  - In `backend/app/api/backup.py` add:
    - Import `UploadFile`, `File`, `restore_service`, all custom exception classes
    - Add `PreRestoreBackupInfo` and `RestoreResponse` Pydantic models
    - Implement `POST /restore` route accepting `UploadFile`, with `get_db` and `require_permission("settings:edit")` dependencies
    - Read `file.filename` and `await file.read()`, call `restore_service.run_restore()`
    - Map each exception to the correct HTTP status code and detail message per design doc
    - Return `RestoreResponse` on success
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 3.4, 4.1, 4.2, 6.1_

- [x] 5. Backend Checkpoint
  - Ensure all backend code has no errors, ask the user if questions arise.

- [x] 6. Add restoreBackup frontend API function
  - Add `restoreBackup(file)` function to `frontend/src/api/backup.js`
  - Build `FormData`, `append('file', file)`
  - Use `request` to POST to `/backup/restore` with `Content-Type: multipart/form-data`, `timeout: 60000`
  - _Requirements: 7.1_

- [x] 7. Frontend Settings.vue restore section
  - [x] 7.1 Add reactive state and imports
    - Import `restoreBackup` and `ElMessageBox` in `<script setup>`
    - Add four refs: `restoreFile`, `restoreLoading`, `restoreResult`, `restoreError`
    - _Requirements: 7.3_
  - [x] 7.2 Extend backup button disabled condition
    - Change `:disabled="!form.backup_enabled"` to `:disabled="!form.backup_enabled || restoreLoading"`
    - _Requirements: 7.6_
  - [x] 7.3 Add restore template section
    - After the backup trigger `el-form-item`, before `<el-divider />`, insert:
      - `<el-divider content-position="left">备份恢复</el-divider>`
      - `el-form-item` label="选择备份文件": `el-upload` with `accept=".zip"`, `auto-upload=false`, `limit=1`
      - `el-form-item` label="恢复数据库": restore button with `:loading="restoreLoading"`, `:disabled="restoreLoading || backupLoading || !restoreFile"`, `@click="handleRestore"`
      - Success: `el-alert type="success"` with filename + `el-alert type="warning"` for restart notice
      - Error: `el-alert type="error"` with `restoreError`
    - _Requirements: 7.1, 7.4, 7.5_
  - [x] 7.4 Implement handleRestore function
    - Call `ElMessageBox.confirm` with warning that operation overwrites all data and cannot be undone
    - On confirm: set `restoreLoading=true`, clear `restoreResult` and `restoreError`
    - Call `restoreBackup(restoreFile.value.raw)`, on success assign `restoreResult`, clear `restoreFile`
    - On failure: extract error from `error.response?.data?.detail`, assign to `restoreError`
    - In `finally`: reset `restoreLoading=false`
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [x] 8. Final Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `RestoreService._lock` and `BackupService._lock` are independent; mutual exclusion is achieved via `is_running()` cross-checks
- `shutil.copy2` is near-atomic on the same filesystem; if it fails, the original database file remains unchanged
- Temp files always cleaned up in `finally` block regardless of outcome
