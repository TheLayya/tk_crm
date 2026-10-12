<template>
  <span class="email-totp" aria-label="2FA 验证码">
    <template v-if="currentCode">
      <span>当前验证码 <code>{{ currentCode }}</code></span>
      <span class="email-totp-time">{{ remaining }} 秒后更新</span>
      <el-button link type="primary" @click="copyCode">复制验证码</el-button>
    </template>
    <span v-else>{{ loading ? '正在获取验证码…' : error || '正在更新验证码…' }}</span>
    <el-button v-if="error" link type="primary" :loading="loading" @click="refresh">重试</el-button>
  </span>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { getEmailTotp } from '@/api/emails'

const props = defineProps({ emailId: { type: Number, required: true } })
const emit = defineEmits(['copy'])
const code = ref(''), error = ref(''), loading = ref(false)
const expiresAt = ref(0), now = ref(performance.now())
const remaining = computed(() => Math.max(0, Math.ceil((expiresAt.value - now.value) / 1000)))
const currentCode = computed(() => remaining.value > 0 ? code.value : '')
let active = true, timer

const refresh = async () => {
  if (!active || loading.value) return
  code.value = ''
  error.value = ''
  loading.value = true
  const started = performance.now()
  try {
    const result = await getEmailTotp(props.emailId)
    if (!active) return
    // Deduct request time so a delayed response cannot extend the code's lifetime.
    const validFor = result.valid_for ?? Math.max(0, result.remaining - 1)
    expiresAt.value = started + validFor * 1000
    now.value = performance.now()
    if (!/^\d{6}$/.test(result.code) || !Number.isFinite(validFor) || validFor <= 0 || validFor > 30) {
      error.value = '验证码返回异常，请重试'
      return
    }
    if (!remaining.value) return
    code.value = result.code
  } catch (err) {
    if (active) error.value = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : '验证码获取失败，请重试'
  } finally { if (active) loading.value = false }
}

const copyCode = () => {
  now.value = performance.now()
  if (currentCode.value) emit('copy', currentCode.value)
  else refresh()
}

onMounted(() => {
  refresh()
  timer = window.setInterval(() => {
    now.value = performance.now()
    if (!remaining.value && !loading.value && !error.value) refresh()
  }, 250)
})
onBeforeUnmount(() => { active = false; window.clearInterval(timer); code.value = '' })
</script>

<style scoped>
.email-totp { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.email-totp code { color: #15803d; font-size: 20px; font-weight: 600; letter-spacing: 2px; }
.email-totp-time { color: #909399; font-size: 12px; }
</style>
