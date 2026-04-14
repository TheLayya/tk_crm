<template>
  <div class="login-container">
    <el-card class="login-card">
      <div class="login-header">
        <img v-if="siteSettings.logo_image" :src="siteSettings.logo_image" class="login-logo" />
        <h2>{{ siteSettings.site_name }}</h2>
        <p>请登录以继续</p>
      </div>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @keyup.enter="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-alert
          v-if="errorMsg"
          :title="errorMsg"
          type="error"
          show-icon
          :closable="false"
          class="login-error"
        />
        <el-button
          type="primary"
          :loading="loading"
          class="login-btn"
          @click="handleLogin"
        >
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { getPublicSettings } from '@/api/settings'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const siteSettings = ref({ site_name: 'TikTok Monitor', logo_image: '' })

const form = ref({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

onMounted(async () => {
  try {
    const data = await getPublicSettings()
    siteSettings.value = { site_name: data.site_name || 'TikTok Monitor', logo_image: data.logo_image || '' }
    document.title = siteSettings.value.site_name
  } catch {}
})

const handleLogin = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''
  try {
    await authStore.login(form.value.username, form.value.password)
    router.push('/')
  } catch (err) {
    const status = err?.response?.status
    if (status === 401) {
      errorMsg.value = '用户名或密码错误'
    } else if (status === 403) {
      errorMsg.value = '账号已禁用，请联系管理员'
    } else if (status === 429) {
      errorMsg.value = '登录失败次数过多，账号已锁定，请稍后再试'
    } else {
      errorMsg.value = err?.response?.data?.detail || '登录失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #304156 0%, #409eff 100%);
}

.login-card {
  width: 400px;
  border-radius: 8px;
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-header h2 {
  margin: 0 0 8px;
  font-size: 24px;
  color: #303133;
}

.login-logo {
  max-width: 120px;
  max-height: 60px;
  object-fit: contain;
  margin-bottom: 12px;
  display: block;
  margin-left: auto;
  margin-right: auto;
}

.login-header p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.login-error {
  margin-bottom: 16px;
}

.login-btn {
  width: 100%;
  margin-top: 8px;
}
</style>
