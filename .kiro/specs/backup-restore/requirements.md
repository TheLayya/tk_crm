# Requirements Document

## Introduction

本功能为 tiktok-monitor 系统新增备份导入/恢复能力。管理员可以上传一个由系统导出的备份 `.zip` 文件，系统解压该文件并用其中的 SQLite 数据库文件完整替换当前数据库，实现全量恢复。恢复操作会覆盖所有现有数据，恢复完成后需要重启或重新加载应用才能使新数据库生效。

系统已有备份导出功能（`backup_service.py`），生成 `monitor_backup_YYYYMMDD_HHMMSS.zip`，内含 `monitor.db`。本功能是其对应的恢复入口。

## Glossary

- **Restore_Service**: 负责接收备份文件、验证内容、替换数据库的后端服务模块
- **Backup_File**: 由系统导出功能生成的 `.zip` 压缩包，内含 `monitor.db` 文件
- **Restore_Operation**: 将 Backup_File 中的数据库文件替换当前运行数据库的完整流程
- **Admin**: 拥有 `settings:edit` 权限的系统管理员用户
- **Database_Path**: 由 `settings.DATABASE_URL` 决定的当前 SQLite 数据库文件路径（默认 `./data/monitor.db`）
- **Restore_Lock**: 防止并发恢复操作的互斥锁
- **Settings_Page**: 前端 `Settings.vue` 中的系统设置页面，已包含"数据备份"区块

---

## Requirements

### Requirement 1: 备份文件上传与验证

**User Story:** As an Admin, I want to upload a backup ZIP file to the system, so that I can initiate a database restore from a previously exported snapshot.

#### Acceptance Criteria

1. THE Restore_Service SHALL expose a POST API endpoint `/api/backup/restore` that accepts a multipart file upload.
2. WHEN the restore endpoint is called, THE Restore_Service SHALL require the caller to have the `settings:edit` permission.
3. WHEN a file is uploaded, THE Restore_Service SHALL verify that the uploaded file has a `.zip` extension; IF the file does not have a `.zip` extension, THEN THE Restore_Service SHALL return HTTP 400 with a descriptive error message.
4. WHEN a `.zip` file is uploaded, THE Restore_Service SHALL verify that the archive contains a file named `monitor.db`; IF `monitor.db` is not present in the archive, THEN THE Restore_Service SHALL return HTTP 422 with a descriptive error message.
5. WHEN the uploaded file cannot be read as a valid ZIP archive, THE Restore_Service SHALL return HTTP 422 with a descriptive error message.

---

### Requirement 2: 恢复前自动备份

**User Story:** As an Admin, I want the system to automatically back up the current database before performing a restore, so that I have a safety copy to recover from in case the restore was triggered by mistake.

#### Acceptance Criteria

1. WHEN all validations pass and before replacing the database, THE Restore_Service SHALL call `BackupService.run_backup()` to create a full backup of the current database.
2. IF the pre-restore backup fails, THEN THE Restore_Service SHALL log a warning message containing the failure reason and SHALL continue with the Restore_Operation without aborting.
3. WHEN the Restore_Operation completes successfully, THE Restore_Service SHALL include a `pre_restore_backup` field in the response containing the backup filename and file size in bytes; IF the pre-restore backup failed, THEN the `pre_restore_backup` field SHALL be `null`.
4. WHERE Telegram or email notification is configured, THE Restore_Service SHALL include the `pre_restore_backup` information in the restore completion notification sent to the Admin.

---

### Requirement 3: 数据库完整替换

**User Story:** As an Admin, I want the restore operation to completely replace the current database with the backup copy, so that the system state is fully restored to the snapshot point.

#### Acceptance Criteria

1. WHEN all validations pass, THE Restore_Service SHALL extract `monitor.db` from the uploaded ZIP archive to a temporary location.
2. WHEN the extracted database file is ready, THE Restore_Service SHALL replace the file at Database_Path with the extracted `monitor.db` using an atomic file operation (copy then replace).
3. THE Restore_Service SHALL NOT perform incremental or partial merges; the Restore_Operation SHALL overwrite all existing data in the current database.
4. IF the file replacement operation fails (e.g., permission error, disk full), THEN THE Restore_Service SHALL log the error with a descriptive message and return HTTP 500 without leaving the database in a partially replaced state.
5. WHEN the Restore_Operation completes successfully, THE Restore_Service SHALL log the completion with the source filename and timestamp.

---

### Requirement 4: 并发保护

**User Story:** As an Admin, I want the system to prevent simultaneous restore operations, so that database integrity is not compromised by concurrent writes.

#### Acceptance Criteria

1. THE Restore_Service SHALL use a Restore_Lock to prevent concurrent Restore_Operations.
2. IF a Restore_Operation is already in progress when a new restore request arrives, THEN THE Restore_Service SHALL return HTTP 409 with a message indicating a restore is already running.
3. WHILE a Restore_Operation is in progress, THE Restore_Service SHALL also reject any concurrent backup trigger requests with HTTP 409.

---

### Requirement 5: 临时文件清理

**User Story:** As an Admin, I want the system to clean up all temporary files after a restore attempt, so that disk space is not wasted regardless of whether the restore succeeded or failed.

#### Acceptance Criteria

1. WHEN a Restore_Operation completes (success or failure), THE Restore_Service SHALL delete all temporary files and directories created during the operation.
2. IF an exception occurs at any stage of the Restore_Operation, THE Restore_Service SHALL still execute the cleanup in a `finally` block.

---

### Requirement 6: 恢复后重启提示

**User Story:** As an Admin, I want to be informed that a restart is required after a successful restore, so that I know to reload the application for the new database to take effect.

#### Acceptance Criteria

1. WHEN the Restore_Operation completes successfully, THE Restore_Service SHALL return a JSON response containing the source filename, completion timestamp, a `restart_required` field set to `true`, and a `pre_restore_backup` field containing the auto-backup filename and file size in bytes (or `null` if the pre-restore backup failed).
2. WHEN the restore API returns a success response, THE Settings_Page SHALL display a prominent warning message informing the Admin that a system restart or page reload is required for the restored data to take effect.

---

### Requirement 7: 前端恢复操作界面

**User Story:** As an Admin, I want a restore section in the settings page, so that I can upload a backup file and trigger a restore through the web UI without using command-line tools.

#### Acceptance Criteria

1. THE Settings_Page SHALL display a "备份恢复"（Restore）section within the existing "数据备份" area, containing a file upload control that accepts only `.zip` files.
2. WHEN the Admin selects a file and clicks the restore button, THE Settings_Page SHALL show a confirmation dialog warning that the operation will overwrite all current data and cannot be undone.
3. WHEN the Admin confirms the restore, THE Settings_Page SHALL show a loading state on the restore button and disable the button to prevent duplicate submissions.
4. WHEN the restore API returns a success response, THE Settings_Page SHALL display a success message including the restored filename and a warning that a restart is required.
5. WHEN the restore API returns an error response, THE Settings_Page SHALL display the error message returned by the API.
6. WHEN the restore is in progress, THE Settings_Page SHALL disable the "立即备份" button to prevent concurrent operations.
