<template>
  <div class="settings">
    <el-card>
      <template #header>
        <div class="settings-header">
          <span>系统设置</span>
          <div class="settings-actions">
            <el-button @click="loadSettings" :disabled="loading || submitting">重新加载</el-button>
            <el-button type="primary" @click="handleSubmit" :loading="submitting" :disabled="loading">保存设置</el-button>
          </div>
        </div>
      </template>

      <el-form
        :model="form"
        :rules="rules"
        ref="formRef"
        label-width="160px"
        v-loading="loading"
        class="settings-form"
      >
        <div class="settings-grid">
        <div class="settings-column">
        <section class="settings-section">
        <h3>监控调度</h3>

        <el-form-item label="默认监控间隔" prop="default_interval">
          <el-input-number
            v-model="form.default_interval"
            :min="5"
            :max="1440"
            :step="5"
          />
          <span class="hint">分钟（监控账号与运营账号周期采集；保存后同步已有监控账号）</span>
        </el-form-item>

        <el-form-item label="最大并发检查数" prop="max_concurrent_checks">
          <el-input-number
            v-model="form.max_concurrent_checks"
            :min="1"
            :max="50"
          />
          <span class="hint">同时执行的检查任务数量上限</span>
        </el-form-item>

        <el-form-item label="请求超时时间" prop="request_timeout">
          <el-input-number
            v-model="form.request_timeout"
            :min="10"
            :max="120"
          />
          <span class="hint">秒（单次请求的超时时间）</span>
        </el-form-item>

        <el-form-item label="默认监控视频数" prop="default_video_count">
          <el-input-number
            v-model="form.default_video_count"
            :min="5"
            :max="100"
            :step="5"
          />
          <span class="hint">个（每次检查时获取的最新视频数量）</span>
        </el-form-item>

        </section>
        <section class="settings-section">
        <h3>界面设置</h3>

        <el-form-item label="网站名称" prop="site_name">
          <el-input
            v-model="form.site_name"
            placeholder="请输入网站名称"
            maxlength="50"
            show-word-limit
          />
          <span class="hint">显示在浏览器标签和侧边栏顶部</span>
        </el-form-item>

        <el-form-item label="登录屏幕文字" prop="login_screen_text">
          <el-input v-model="form.login_screen_text" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="数据连接团队，协作创造价值" />
          <span class="hint">显示在登录场景的三面屏幕上；留空隐藏文字。仅支持纯文本，保存后刷新登录页生效。</span>
        </el-form-item>

        <el-form-item label="网站Logo" prop="logo_image">
          <div class="logo-upload">
            <el-upload
              class="logo-uploader"
              :show-file-list="false"
              :before-upload="handleLogoUpload"
              accept="image/*"
            >
              <img v-if="form.logo_image" :src="form.logo_image" class="logo-preview" />
              <el-icon v-else class="logo-uploader-icon"><Plus /></el-icon>
            </el-upload>
            <div class="logo-actions">
              <el-button v-if="form.logo_image" size="small" @click="clearLogo">
                清除Logo
              </el-button>
              <span class="hint">建议尺寸：200x50px，支持PNG/JPG格式</span>
            </div>
          </div>
        </el-form-item>

        </section>
        <section class="settings-section restore-section">
        <h3>备份恢复</h3>
        <p class="section-note">恢复会覆盖现有数据，请确认备份文件来源和恢复范围。</p>

        <el-form-item label="选择备份文件">
          <el-upload
            accept=".zip"
            :auto-upload="false"
            :limit="1"
            :on-change="(file) => { restoreFile = file }"
            :on-remove="() => { restoreFile = null }"
            :file-list="restoreFile ? [restoreFile] : []"
          >
            <el-button size="small">选择 .zip 文件</el-button>
          </el-upload>
        </el-form-item>

        <el-form-item label="恢复数据库">
          <el-button
            type="danger"
            :loading="restoreLoading"
            :disabled="restoreLoading || backupLoading || !restoreFile"
            @click="handleRestore"
          >
            恢复数据库
          </el-button>
        </el-form-item>

        <el-form-item v-if="restoreResult">
          <el-alert
            type="success"
            :closable="false"
            show-icon
            :title="`恢复成功：${restoreResult.filename}`"
          />
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="需要重启应用才能使恢复的数据生效，请刷新页面或重启服务。"
            style="margin-top: 8px"
          />
          <div v-if="restoreResult.pre_restore_backup" class="hint" style="margin-top: 8px">
            恢复前自动备份：{{ restoreResult.pre_restore_backup.filename }}（{{ (restoreResult.pre_restore_backup.file_size / 1024).toFixed(1) }} KB）
          </div>
        </el-form-item>

        <el-form-item v-if="restoreError">
          <el-alert
            type="error"
            :closable="false"
            show-icon
            :title="restoreError"
          />
        </el-form-item>

        </section>
        </div>
        <div class="settings-column">
        <section class="settings-section">
        <h3>数据备份</h3>

        <el-form-item label="启用自动备份">
          <el-switch v-model="form.backup_enabled" />
        </el-form-item>

        <el-form-item label="备份间隔（小时）">
          <el-input-number
            v-model="form.backup_interval_hours"
            :min="1" :max="168"
            :disabled="!form.backup_enabled"
          />
          <span class="hint">1–168 小时（最长7天）</span>
        </el-form-item>

        <details class="notification-settings" :open="form.telegram_enabled">
        <summary>Telegram 通知 <span>{{ form.telegram_enabled ? '已启用' : '未启用' }}</span></summary>
        <el-form-item label="启用 Telegram 通知">
          <el-switch v-model="form.telegram_enabled" :disabled="!form.backup_enabled" />
        </el-form-item>

        <el-form-item label="Telegram Bot Token">
          <el-input
            v-model="form.telegram_bot_token"
            placeholder="Telegram Bot Token（留空保持不变）"
            :disabled="!form.backup_enabled || !form.telegram_enabled"
            show-password
          />
        </el-form-item>

        <el-form-item label="Telegram Chat ID">
          <el-input
            v-model="form.telegram_chat_id"
            placeholder="请输入 Chat ID"
            :disabled="!form.backup_enabled || !form.telegram_enabled"
          />
        </el-form-item>

        </details>
        <details class="notification-settings" :open="form.email_enabled">
        <summary>邮件通知 <span>{{ form.email_enabled ? '已启用' : '未启用' }}</span></summary>
        <el-form-item label="启用邮件通知">
          <el-switch v-model="form.email_enabled" :disabled="!form.backup_enabled" />
        </el-form-item>

        <el-form-item label="SMTP 服务器">
          <el-input
            v-model="form.smtp_host"
            placeholder="例如 smtp.gmail.com"
            :disabled="!form.backup_enabled || !form.email_enabled"
          />
        </el-form-item>

        <el-form-item label="SMTP 端口">
          <el-input-number
            v-model="form.smtp_port"
            :min="1" :max="65535"
            :disabled="!form.backup_enabled || !form.email_enabled"
          />
        </el-form-item>

        <el-form-item label="SMTP 用户名">
          <el-input
            v-model="form.smtp_username"
            placeholder="SMTP 登录用户名"
            :disabled="!form.backup_enabled || !form.email_enabled"
          />
        </el-form-item>

        <el-form-item label="SMTP 密码">
          <el-input
            v-model="form.smtp_password"
            placeholder="SMTP 登录密码（留空保持不变）"
            show-password
            :disabled="!form.backup_enabled || !form.email_enabled"
          />
        </el-form-item>

        <el-form-item label="发件人地址">
          <el-input
            v-model="form.smtp_sender"
            placeholder="例如 noreply@example.com"
            :disabled="!form.backup_enabled || !form.email_enabled"
          />
        </el-form-item>

        <el-form-item label="收件人地址">
          <el-input
            v-model="form.email_recipient"
            placeholder="备份文件接收邮箱"
            :disabled="!form.backup_enabled || !form.email_enabled"
          />
        </el-form-item>

        <el-form-item label="使用 STARTTLS">
          <el-switch v-model="form.smtp_use_tls" :disabled="!form.backup_enabled || !form.email_enabled" />
        </el-form-item>

        </details>
        <el-form-item label="立即备份">
          <el-button
            type="warning"
            :loading="backupLoading"
            :disabled="!form.backup_enabled || restoreLoading"
            @click="handleTriggerBackup"
          >
            立即备份
          </el-button>
          <span v-if="backupResult" class="hint" style="color: #67c23a">
            ✓ 备份成功，文件已开始下载
          </span>
          <span v-if="backupError" class="hint" style="color: #f56c6c">
            ✗ {{ backupError }}
          </span>
        </el-form-item>

        </section>

        </div>
        </div>

        <div class="settings-footer">
          <span>修改后统一保存；立即备份与恢复为独立操作。</span>
          <el-button type="primary" @click="handleSubmit" :loading="submitting" :disabled="loading">
            保存设置
          </el-button>
        </div>

        <el-alert
          title="提示"
          type="info"
          :closable="false"
          show-icon
        >
          <p>设置更改后将在下一个调度周期生效。</p>
          <p>监控间隔会同步应用到已有账号；账号单独编辑后也会继续遵循下一次全局设置。</p>
        </el-alert>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getSettings, updateSettings } from '@/api/settings'
import { triggerBackup, restoreBackup } from '@/api/backup'

const loading = ref(false)
const submitting = ref(false)
const formRef = ref(null)

const form = ref({
  default_interval: 60,  // 60 minutes = 1 hour (matches backend default 3600s)
  max_concurrent_checks: 5,
  request_timeout: 30,
  default_video_count: 20,
  site_name: 'TikTok Monitor',
  logo_image: '',
  login_screen_text: '数据连接团队，协作创造价值',
  backup_enabled: false,
  backup_interval_hours: 24,
  telegram_enabled: false,
  telegram_bot_token: '',
  telegram_chat_id: '',
  email_enabled: false,
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  smtp_sender: '',
  email_recipient: '',
  smtp_use_tls: true
})

const backupLoading = ref(false)
const backupResult = ref(null)
const backupError = ref(null)

const restoreFile = ref(null)
const restoreLoading = ref(false)
const restoreResult = ref(null)
const restoreError = ref(null)

const rules = {
  default_interval: [
    { required: true, message: '请输入默认监控间隔', trigger: 'blur' },
    { type: 'number', min: 5, max: 1440, message: '间隔必须在 5-1440 分钟之间', trigger: 'blur' }
  ],
  max_concurrent_checks: [
    { required: true, message: '请输入最大并发数', trigger: 'blur' },
    { type: 'number', min: 1, max: 50, message: '并发数必须在 1-50 之间', trigger: 'blur' }
  ],
  request_timeout: [
    { required: true, message: '请输入请求超时时间', trigger: 'blur' },
    { type: 'number', min: 10, max: 120, message: '超时时间必须在 10-120 秒之间', trigger: 'blur' }
  ],
  default_video_count: [
    { required: true, message: '请输入默认监控视频数', trigger: 'blur' },
    { type: 'number', min: 5, max: 100, message: '视频数必须在 5-100 之间', trigger: 'blur' }
  ],
  site_name: [
    { required: true, message: '请输入网站名称', trigger: 'blur' },
    { min: 1, max: 50, message: '网站名称长度必须在 1-50 字符之间', trigger: 'blur' }
  ]
}

const loadSettings = async () => {
  loading.value = true
  try {
    const data = await getSettings()
    // Convert seconds to minutes for display
    form.value = {
      default_interval: Math.round(data.default_interval / 60),
      max_concurrent_checks: data.max_concurrent_checks,
      request_timeout: data.request_timeout,
      default_video_count: data.default_video_count || 20,
      site_name: data.site_name || 'TikTok Monitor',
      logo_image: data.logo_image || '',
      login_screen_text: data.login_screen_text ?? '数据连接团队，协作创造价值',
      backup_enabled: data.backup_enabled || false,
      backup_interval_hours: data.backup_interval_hours || 24,
      telegram_enabled: data.telegram_enabled || false,
      telegram_bot_token: data.telegram_bot_token || '',
      telegram_chat_id: data.telegram_chat_id || '',
      email_enabled: data.email_enabled || false,
      smtp_host: data.smtp_host || '',
      smtp_port: data.smtp_port || 587,
      smtp_username: data.smtp_username || '',
      smtp_password: data.smtp_password || '',
      smtp_sender: data.smtp_sender || '',
      email_recipient: data.email_recipient || '',
      smtp_use_tls: data.smtp_use_tls !== undefined ? data.smtp_use_tls : true
    }
  } catch (error) {
    console.error('Failed to load settings:', error)
    ElMessage.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

const handleLogoUpload = (file) => {
  // 验证文件类型
  const isImage = file.type.startsWith('image/')
  if (!isImage) {
    ElMessage.error('只能上传图片文件！')
    return false
  }

  // 验证文件大小（限制2MB）
  const isLt2M = file.size / 1024 / 1024 < 2
  if (!isLt2M) {
    ElMessage.error('图片大小不能超过 2MB！')
    return false
  }

  // 读取文件并转换为base64
  const reader = new FileReader()
  reader.onload = (e) => {
    form.value.logo_image = e.target.result
  }
  reader.readAsDataURL(file)

  return false // 阻止自动上传
}

const clearLogo = () => {
  form.value.logo_image = ''
}

const handleSubmit = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    // Convert minutes to seconds for backend
    const payload = {
      default_interval: form.value.default_interval * 60,
      max_concurrent_checks: form.value.max_concurrent_checks,
      request_timeout: form.value.request_timeout,
      default_video_count: form.value.default_video_count,
      site_name: form.value.site_name,
      logo_image: form.value.logo_image,
      login_screen_text: form.value.login_screen_text,
      backup_enabled: form.value.backup_enabled,
      backup_interval_hours: form.value.backup_interval_hours,
      telegram_enabled: form.value.telegram_enabled,
      telegram_bot_token: form.value.telegram_bot_token,
      telegram_chat_id: form.value.telegram_chat_id,
      email_enabled: form.value.email_enabled,
      smtp_host: form.value.smtp_host,
      smtp_port: form.value.smtp_port,
      smtp_username: form.value.smtp_username,
      smtp_password: form.value.smtp_password,
      smtp_sender: form.value.smtp_sender,
      email_recipient: form.value.email_recipient,
      smtp_use_tls: form.value.smtp_use_tls
    }
    await updateSettings(payload)
    window.dispatchEvent(new CustomEvent('site-settings-updated', {
      detail: { site_name: form.value.site_name, logo_image: form.value.logo_image }
    }))
    ElMessage.success('设置保存成功')
  } catch (error) {
    console.error('Failed to update settings:', error)
    ElMessage.error('设置保存失败')
  } finally {
    submitting.value = false
  }
}

const handleRestore = async () => {
  try {
    await ElMessageBox.confirm(
      '此操作将用备份文件完整替换当前数据库，所有现有数据将被覆盖且无法撤销。确定要继续吗？',
      '警告：数据库恢复',
      {
        confirmButtonText: '确认恢复',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      }
    )
  } catch {
    return // user cancelled
  }

  restoreLoading.value = true
  restoreResult.value = null
  restoreError.value = null

  try {
    const data = await restoreBackup(restoreFile.value.raw)
    restoreResult.value = data
    restoreFile.value = null
  } catch (error) {
    restoreError.value = error.response?.data?.detail || '恢复失败，请查看日志'
  } finally {
    restoreLoading.value = false
  }
}

const handleTriggerBackup = async () => {
  backupLoading.value = true
  backupResult.value = null
  backupError.value = null
  try {
    await triggerBackup()
    backupResult.value = { filename: '下载已开始', file_size: 0 }
  } catch (error) {
    // blob error responses need special handling
    const detail = error.response?.data
    if (detail instanceof Blob) {
      const text = await detail.text()
      try {
        backupError.value = JSON.parse(text)?.detail || '备份失败，请查看日志'
      } catch {
        backupError.value = '备份失败，请查看日志'
      }
    } else {
      backupError.value = detail?.detail || '备份失败，请查看日志'
    }
  } finally {
    backupLoading.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings {
  padding: 0;
}

.settings-header, .settings-actions, .settings-footer { display: flex; align-items: center; gap: 8px; }
.settings-header { justify-content: space-between; flex-wrap: wrap; }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; }
.settings-column { display: grid; gap: 16px; min-width: 0; }
.settings-section { padding: 16px; border: 1px solid #e9edf3; border-radius: 8px; min-width: 0; }
.settings-section h3 { font-size: 14px; margin: 0 0 16px; color: #303133; }
.settings-form :deep(.el-form-item) { margin-bottom: 14px; }
.settings-form :deep(.el-form-item:last-child) { margin-bottom: 0; }
.settings-form :deep(.el-form-item__content) { gap: 4px 8px; min-width: 0; }
.settings-form :deep(.el-input-number) { width: 148px; }
.settings-footer { margin-top: 16px; justify-content: space-between; flex-wrap: wrap; padding: 12px 0 0; border-top: 1px solid #edf0f5; }
.settings-footer > span, .section-note { color: #909399; font-size: 12px; }
.section-note { margin: -6px 0 14px; line-height: 18px; }
.notification-settings { border-top: 1px solid #edf0f5; margin-bottom: 14px; }
.notification-settings summary { cursor: pointer; padding: 10px 0; font-size: 13px; color: #606266; }
.notification-settings summary span { margin-left: 8px; font-size: 12px; color: #909399; }
@media (max-width: 1100px) {
  .settings-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 600px) {
  .settings-section { padding: 12px; }
  .settings-form :deep(.el-form-item) { display: block; }
  .settings-form :deep(.el-form-item__label) { width: auto !important; justify-content: flex-start; height: auto; line-height: 26px; }
  .settings-form :deep(.el-form-item__content) { margin-left: 0 !important; }
  .logo-upload { flex-wrap: wrap; }
}

.hint {
  margin-left: 0;
  font-size: 12px;
  color: #909399;
}

.el-alert {
  margin-top: 20px;
}

.el-alert p {
  margin: 5px 0;
}

.logo-upload {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.logo-uploader {
  border: 1px dashed #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: border-color 0.3s;
}

.logo-uploader:hover {
  border-color: #409eff;
}

.logo-uploader-icon {
  font-size: 28px;
  color: #8c939d;
  width: 140px;
  height: 70px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-preview {
  width: 140px;
  height: 70px;
  object-fit: contain;
  display: block;
}

.logo-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
