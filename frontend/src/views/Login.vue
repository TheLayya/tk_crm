<template>
  <div class="login-container">
    <section class="login-visual" aria-hidden="true">
      <div ref="contentRef" class="scene-content">
        <div class="scene-full">
          <div class="scene-hue animated" />
          <img class="scene-background" src="/login/room.jpg" alt="" />
          <img class="scene-boy" src="/login/people.png" alt="" />
          <div v-if="screenText" class="scene-screen">
            <div v-for="side in ['left', 'back', 'right']" :key="side" class="screen-face" :class="`screen-face--${side}`">
              <div class="screen-track"><span>{{ screenText }}　·　</span><span aria-hidden="true">{{ screenText }}　·　</span></div>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="login-panel">
      <div class="login-card">
        <div class="login-header">
          <div class="brand-mark"><img v-if="siteSettings.logo_image" :src="siteSettings.logo_image" class="login-logo" /><span v-else>✦</span></div>
          <div class="login-eyebrow">WELCOME BACK</div>
          <h2>{{ siteSettings.site_name }}</h2>
          <p>登录以继续管理您的业务资产</p>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="handleLogin">
          <el-form-item label="用户名" prop="username"><el-input v-model="form.username" placeholder="请输入用户名" :prefix-icon="User" autocomplete="username" /></el-form-item>
          <el-form-item label="密码" prop="password"><el-input v-model="form.password" type="password" placeholder="请输入密码" :prefix-icon="Lock" show-password autocomplete="current-password" /></el-form-item>
          <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" class="login-error" />
          <el-button type="primary" :loading="loading" class="login-btn" @click="handleLogin"><span>进入工作台</span><span class="login-arrow">→</span></el-button>
        </el-form>
        <div class="login-footnote"><span class="status-dot" /> 团队专属工作台 · 授权访问</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
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
const contentRef = ref(null)
const screenText = ref('数据连接团队，协作创造价值')
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const adjustContentSize = () => {
  if (!contentRef.value) return
  const scale = window.innerWidth <= 760
    ? Math.max(window.innerWidth / 1000, window.innerHeight / 562)
    : Math.min((window.innerWidth - 64) / 1000, (window.innerHeight - 48) / 562)
  contentRef.value.style.transform = `scale(${scale})`
}

onMounted(async () => {
  await nextTick()
  adjustContentSize()
  window.addEventListener('resize', adjustContentSize)
  try {
    const data = await getPublicSettings()
    screenText.value = (data.login_screen_text ?? '数据连接团队，协作创造价值').replace(/\s+/g, ' ').trim()
    siteSettings.value = { site_name: data.site_name || 'TikTok Monitor', logo_image: data.logo_image || '' }
    document.title = siteSettings.value.site_name
  } catch {}
})
onBeforeUnmount(() => window.removeEventListener('resize', adjustContentSize))

const handleLogin = async () => {
  if (loading.value) return
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
    if (status === 401) errorMsg.value = '用户名或密码错误'
    else if (status === 403) errorMsg.value = '账号已禁用，请联系管理员'
    else if (status === 429) errorMsg.value = '登录失败次数过多，账号已锁定，请稍后再试'
    else errorMsg.value = err?.response?.data?.detail || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container { min-height: 100svh; position: relative; display: grid; place-items: center; overflow: hidden; background: #101014; color: #fff; }
.login-visual { position: absolute; inset: 0; display: grid; place-items: center; overflow: hidden; pointer-events: none; }
.scene-content { position: relative; width: 1000px; height: 562px; transform-origin: center; }
.scene-full { position: relative; width: 1000px; height: 562px; overflow: hidden; border-radius: 28px; isolation: isolate; background: #000; }
.scene-background, .scene-boy { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; }
.scene-background { z-index: 0; }
.scene-boy { z-index: 4; }
.scene-hue { position: absolute; inset: 0; z-index: 5; pointer-events: none; background: #e87ac5; mix-blend-mode: color; opacity: .62; animation: scene-color 24s ease-in-out infinite; }
.scene-screen { position: absolute; inset: 0; z-index: 2; }
.screen-face { position: absolute; left: 0; top: 0; height: 100px; overflow: hidden; transform-origin: 0 0; color: rgba(255,255,255,.58); font: 300 38px/100px Arial, sans-serif; white-space: nowrap; }
.screen-face--back { width: 450px; transform: translate(275px, 250px); }
.screen-face--left { width: 275px; transform: matrix3d(2.35, 1.572727273, 0, .004909090909, 0, 2.35, 0, 0, 0, 0, 1, 0, 0, 155, 0, 1); }
.screen-face--right { width: 275px; transform: matrix3d(-1.088974855, -.669245648, 0, -.002088974855, 0, 1, 0, 0, 0, 0, 1, 0, 725, 250, 0, 1); }
.screen-track { display: flex; width: max-content; animation: screen-scroll 34s linear infinite; }
.screen-face--back .screen-track { margin-left: -275px; }
.screen-face--right .screen-track { margin-left: -725px; }
.screen-track span { flex-shrink: 0; min-width: 1000px; padding-right: 48px; box-sizing: border-box; }
.login-panel { position: relative; z-index: 10; width: min(1440px, 100%); box-sizing: border-box; padding: 56px; pointer-events: none; }
.login-card { pointer-events: auto; width: 340px; box-sizing: border-box; padding: 32px; border: 1px solid rgba(255,255,255,.2); border-radius: 22px; background: linear-gradient(145deg, rgba(23,17,32,.67), rgba(17,17,28,.4)); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); box-shadow: 0 24px 72px rgba(0,0,0,.4), inset 0 1px rgba(255,255,255,.08); }
.login-header { margin-bottom: 26px; text-align: left; }
.brand-mark { height: 40px; width: 40px; display: grid; place-items: center; margin-bottom: 22px; border-radius: 12px; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.18); color: #efb7e4; font-size: 22px; }
.login-logo { max-width: 32px; max-height: 32px; object-fit: contain; }
.login-eyebrow { font-size: 10px; letter-spacing: .24em; color: #e6afd9; }
.login-header h2 { margin: 10px 0; font-size: 27px; font-weight: 600; color: #fff; overflow-wrap: anywhere; }
.login-header p { margin: 0; color: rgba(255,255,255,.66); font-size: 12px; line-height: 1.7; }
.login-card :deep(.el-form-item) { margin-bottom: 22px; }
.login-card :deep(.el-form-item__label) { font-size: 12px; color: #eee4f0; }
.login-card :deep(.el-input__wrapper) { min-height: 42px; border-radius: 9px; background: rgba(255,255,255,.07); box-shadow: 0 0 0 1px rgba(255,255,255,.2) inset; }
.login-card :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px #e6a8db inset, 0 0 0 3px rgba(230,168,219,.12); }
.login-card :deep(.el-input__inner) { color: #fff; }
.login-card :deep(.el-input__inner::placeholder) { color: #b8abbf; }
.login-card :deep(.el-input__icon) { color: #d1bfd7; }
.login-error { margin-bottom: 16px; }
.login-btn { width: 100%; height: 44px; border: 1px solid rgba(255,255,255,.3); border-radius: 9px; color: #27172f; background: linear-gradient(110deg, #efd6ed, #c9b9ef); font-weight: 600; box-shadow: 0 6px 24px rgba(210,137,203,.15); }
.login-btn:hover, .login-btn:focus-visible { color: #27172f; background: #f8e8fa; border-color: #fff; }
.login-arrow { margin-left: 12px; }
.login-footnote { margin-top: 22px; font-size: 10px; color: #c4b4cc; }
.status-dot { display: inline-block; width: 5px; height: 5px; margin-right: 6px; border-radius: 50%; background: #dcbce9; }
@keyframes screen-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes scene-color { 0%, 100% { background: #e87ac5; } 50% { background: #739ee8; } }
@media (max-width: 760px) { .login-panel { padding: 28px; display: flex; justify-content: center; }.login-card { width: min(340px,100%); background: rgba(19,16,29,.66); }.scene-full { border-radius: 0; } }
@media (max-height: 620px) { .login-panel { padding-top: 24px; padding-bottom: 24px; }.login-header { margin-bottom: 16px; }.brand-mark { margin-bottom: 12px; } }
@media (prefers-reduced-motion: reduce) { .scene-hue, .screen-track { animation: none; } }
</style>
