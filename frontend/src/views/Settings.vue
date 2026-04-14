<template>
  <div class="settings">
    <el-card>
      <template #header>
        <span>系统设置</span>
      </template>

      <el-form
        :model="form"
        :rules="rules"
        ref="formRef"
        label-width="180px"
        v-loading="loading"
        style="max-width: 600px"
      >
        <el-divider content-position="left">监控调度设置</el-divider>

        <el-form-item label="默认监控间隔" prop="default_interval">
          <el-input-number
            v-model="form.default_interval"
            :min="5"
            :max="1440"
            :step="5"
          />
          <span class="hint">分钟（新建账号时的默认值）</span>
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

        <el-divider content-position="left">界面设置</el-divider>

        <el-form-item label="网站名称" prop="site_name">
          <el-input
            v-model="form.site_name"
            placeholder="请输入网站名称"
            maxlength="50"
            show-word-limit
          />
          <span class="hint">显示在浏览器标签和侧边栏顶部</span>
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

        <el-divider content-position="left">数据备份</el-divider>

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

        <el-form-item label="启用 Telegram 通知">
          <el-switch v-model="form.telegram_enabled" :disabled="!form.backup_enabled" />
        </el-form-item>

        <el-form-item label="Telegram Bot Token">
          <el-input
            v-model="form.telegram_bot_token"
            placeholder="请输入 Bot Token"
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

        <el-divider content-position="left">备份恢复</el-divider>

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

        <el-divider />

        <el-form-item>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            保存设置
          </el-button>
          <el-button @click="loadSettings">
            重置
          </el-button>
        </el-form-item>

        <el-alert
          title="提示"
          type="info"
          :closable="false"
          show-icon
        >
          <p>设置更改后将在下一个调度周期生效。</p>
          <p>已创建的账号不会自动更新监控间隔，需要手动编辑。</p>
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
    ElMessage.success('设置保存成功，刷新页面生效')
    
    // 更新页面标题
    document.title = form.value.site_name
    
    // 刷新页面以应用新的logo和站名
    setTimeout(() => {
      window.location.reload()
    }, 1000)
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
  padding: 20px;
}

.hint {
  margin-left: 10px;
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
  width: 200px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-preview {
  width: 200px;
  height: 100px;
  object-fit: contain;
  display: block;
}

.logo-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
