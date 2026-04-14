# Requirements Document

## Introduction

本功能为 tiktok-monitor 系统新增数据备份与通知能力。系统需要能够周期性地自动备份 SQLite 数据库文件，并通过 Telegram Bot 将备份文件发送到指定 Chat；同时支持可选的邮件发送方式。管理员可在系统设置页面配置备份相关参数（Bot Token、Chat ID、备份周期、邮件信息等），并可随时手动触发一次备份。

## Glossary

- **Backup_Service**: 负责执行数据库备份、压缩及分发的后端服务模块
- **Scheduler**: 已有的 APScheduler 异步调度器，负责注册和触发定时任务
- **Backup_Job**: 由 Scheduler 注册的周期性备份定时任务
- **Telegram_Notifier**: 负责通过 Telegram Bot API 发送备份文件的组件
- **Email_Notifier**: 负责通过 SMTP 发送备份文件的可选组件
- **MonitorSettings**: 系统唯一的设置记录（id=1），存储所有系统配置，包括备份配置
- **Backup_File**: 由 Backup_Service 生成的 SQLite 数据库压缩副本（.zip 格式）
- **Admin**: 拥有 `settings:edit` 权限的系统管理员用户
- **Chat_ID**: Telegram 中目标会话（用户、群组或频道）的唯一标识符
- **Bot_Token**: Telegram Bot 的身份认证令牌

---

## Requirements

### Requirement 1: 数据库备份文件生成

**User Story:** As an Admin, I want the system to create a compressed copy of the SQLite database, so that I have a recoverable snapshot of all monitoring data.

#### Acceptance Criteria

1. WHEN a backup is triggered, THE Backup_Service SHALL copy the SQLite database file to a temporary location using SQLite online backup API or file copy.
2. WHEN a backup is triggered, THE Backup_Service SHALL compress the database copy into a ZIP archive named with the format `monitor_backup_YYYYMMDD_HHMMSS.zip`.
3. WHEN the backup file is successfully created, THE Backup_Service SHALL record the backup timestamp and file size in the application log.
4. IF the database file does not exist or is inaccessible during backup, THEN THE Backup_Service SHALL log the error with a descriptive message and abort the backup without raising an unhandled exception.
5. WHEN a backup completes (success or failure), THE Backup_Service SHALL delete any temporary files created during the backup process.

---

### Requirement 2: 周期性自动备份

**User Story:** As an Admin, I want the system to automatically back up the database on a configurable schedule, so that backups happen without manual intervention.

#### Acceptance Criteria

1. WHEN the application starts, THE Scheduler SHALL register the Backup_Job using the backup interval stored in MonitorSettings.
2. WHEN the backup interval setting is updated via the settings API, THE Scheduler SHALL reschedule the Backup_Job to use the new interval within the same request lifecycle.
3. WHILE the backup feature is enabled in MonitorSettings, THE Scheduler SHALL execute the Backup_Job at every configured interval.
4. WHEN the backup feature is disabled in MonitorSettings, THE Scheduler SHALL remove the Backup_Job from the schedule.
5. THE Backup_Job SHALL support interval values between 1 hour and 168 hours (7 days) inclusive.

---

### Requirement 3: Telegram Bot 发送备份文件

**User Story:** As an Admin, I want backup files to be sent to a Telegram chat automatically, so that I can receive and store backups remotely without accessing the server.

#### Acceptance Criteria

1. WHEN a backup file is successfully created and Telegram notification is enabled in MonitorSettings, THE Telegram_Notifier SHALL send the Backup_File as a document to the configured Chat_ID using the configured Bot_Token.
2. WHEN sending the Telegram document, THE Telegram_Notifier SHALL include a caption containing the backup timestamp and file size in human-readable format.
3. IF the Telegram API returns an error response (non-2xx HTTP status), THEN THE Telegram_Notifier SHALL log the error including the HTTP status code and response body, and SHALL NOT retry automatically.
4. IF the Bot_Token or Chat_ID is empty or not configured in MonitorSettings, THEN THE Telegram_Notifier SHALL skip the Telegram notification and log a warning message.
5. THE Telegram_Notifier SHALL complete the send operation within 60 seconds; IF the operation exceeds 60 seconds, THEN THE Telegram_Notifier SHALL cancel the request and log a timeout error.

---

### Requirement 4: 邮件发送备份（可选）

**User Story:** As an Admin, I want the option to receive backup files via email, so that I have an alternative delivery channel independent of Telegram.

#### Acceptance Criteria

1. WHERE email notification is enabled in MonitorSettings, THE Email_Notifier SHALL send the Backup_File as an attachment to the configured recipient email address via SMTP.
2. WHERE email notification is enabled, THE Email_Notifier SHALL use the SMTP host, port, username, password, sender address, and recipient address stored in MonitorSettings.
3. WHERE email notification is enabled and TLS is configured, THE Email_Notifier SHALL establish the SMTP connection using STARTTLS.
4. IF the SMTP connection fails or the email send operation returns an error, THEN THE Email_Notifier SHALL log the error with the SMTP host and error message, and SHALL NOT block the completion of the backup workflow.
5. IF any required email configuration field (SMTP host, recipient address) is empty when email notification is enabled, THEN THE Email_Notifier SHALL skip the email send and log a warning message.

---

### Requirement 5: 手动触发备份

**User Story:** As an Admin, I want to manually trigger a backup at any time, so that I can create an on-demand snapshot before making significant changes.

#### Acceptance Criteria

1. THE Backup_Service SHALL expose a POST API endpoint `/api/backup/trigger` that initiates an immediate backup when called.
2. WHEN the manual trigger endpoint is called, THE Backup_Service SHALL require the caller to have the `settings:edit` permission.
3. WHEN a manual backup is triggered, THE Backup_Service SHALL execute the same backup, compression, and notification workflow as the scheduled Backup_Job.
4. WHEN the manual backup completes successfully, THE Backup_Service SHALL return a JSON response containing the backup filename, file size in bytes, and completion timestamp.
5. IF a backup is already in progress when the manual trigger endpoint is called, THEN THE Backup_Service SHALL return HTTP 409 with a message indicating a backup is already running.

---

### Requirement 6: 备份配置管理

**User Story:** As an Admin, I want to configure all backup-related settings in the system settings page, so that I can manage backup behavior without modifying server configuration files.

#### Acceptance Criteria

1. THE MonitorSettings model SHALL store the following backup configuration fields: `backup_enabled` (boolean), `backup_interval_hours` (integer), `telegram_enabled` (boolean), `telegram_bot_token` (string), `telegram_chat_id` (string), `email_enabled` (boolean), `smtp_host` (string), `smtp_port` (integer), `smtp_username` (string), `smtp_password` (string), `smtp_sender` (string), `email_recipient` (string), `smtp_use_tls` (boolean).
2. WHEN the settings API returns MonitorSettings, THE Settings_API SHALL include all backup configuration fields in the response.
3. WHEN the settings update API receives new backup configuration values, THE Settings_API SHALL validate that `backup_interval_hours` is between 1 and 168 inclusive; IF the value is out of range, THEN THE Settings_API SHALL return HTTP 422 with a descriptive error message.
4. WHEN the settings update API receives a new `backup_interval_hours` or `backup_enabled` value, THE Settings_API SHALL trigger a reschedule of the Backup_Job after persisting the change.
5. THE Settings_API SHALL NOT return `smtp_password` or `telegram_bot_token` in plaintext in the GET settings response; THE Settings_API SHALL mask these fields by returning a fixed placeholder string `"********"` when the value is set, or an empty string when not set.

---

### Requirement 7: 前端备份配置界面

**User Story:** As an Admin, I want a dedicated backup configuration section in the system settings page, so that I can view and update all backup settings through the web UI.

#### Acceptance Criteria

1. THE Settings_Page SHALL display a "数据备份" section containing controls for all backup configuration fields defined in Requirement 6.1.
2. WHEN the Admin toggles `backup_enabled` to off, THE Settings_Page SHALL disable (but not hide) all other backup-related input fields.
3. WHEN the Admin toggles `telegram_enabled` to off, THE Settings_Page SHALL disable (but not hide) the Telegram Bot Token and Chat ID input fields.
4. WHEN the Admin toggles `email_enabled` to off, THE Settings_Page SHALL disable (but not hide) all SMTP configuration input fields.
5. THE Settings_Page SHALL display a "立即备份" button that calls the manual trigger endpoint defined in Requirement 5.1; WHEN the button is clicked, THE Settings_Page SHALL show a loading state and display a success or error message upon completion.
6. WHEN the settings form is submitted, THE Settings_Page SHALL send the updated backup configuration fields together with the existing settings fields in a single PUT request.
