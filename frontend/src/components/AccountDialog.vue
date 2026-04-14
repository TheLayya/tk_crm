<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑账号' : '添加账号'"
    width="600px"
    @close="handleClose"
  >
    <el-form
      :model="form"
      :rules="rules"
      ref="formRef"
      label-width="120px"
    >
      <el-form-item label="所属项目" prop="project_id">
        <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" placeholder="TikTok用户名（@后面的部分）" />
      </el-form-item>

      <el-form-item label="昵称" prop="nickname">
        <el-input v-model="form.nickname" placeholder="可选" />
      </el-form-item>

      <el-form-item label="TikTok ID" prop="tiktok_id">
        <el-input v-model="form.tiktok_id" placeholder="可选" />
      </el-form-item>

      <el-form-item label="Sec UID" prop="sec_uid">
        <el-input v-model="form.sec_uid" placeholder="可选" />
      </el-form-item>

      <el-form-item label="监控间隔" prop="monitor_interval">
        <el-input-number
          v-model="form.monitor_interval"
          :min="5"
          :max="1440"
          :step="5"
        />
        <span style="margin-left: 10px; color: #909399; font-size: 12px;">分钟</span>
      </el-form-item>

      <el-form-item label="使用代理" prop="use_proxy">
        <el-switch v-model="form.use_proxy" />
      </el-form-item>

      <el-form-item label="选择代理" prop="proxy_id" v-if="form.use_proxy">
        <el-select v-model="form.proxy_id" placeholder="选择代理" clearable style="width: 100%">
          <el-option
            v-for="proxy in proxies"
            :key="proxy.id"
            :label="proxy.username ? `${proxy.username}@${proxy.host}:${proxy.port}` : `${proxy.host}:${proxy.port}`"
            :value="proxy.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="启用视频监控" prop="enable_video_monitoring">
        <el-switch v-model="form.enable_video_monitoring" />
      </el-form-item>

      <el-form-item label="启用状态" prop="is_active">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { createAccount, updateAccount } from '@/api/accounts'
import { getProxies } from '@/api/proxies'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  projects: {
    type: Array,
    default: () => []
  },
  account: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const isEdit = computed(() => !!props.account)

const formRef = ref(null)
const submitting = ref(false)
const proxies = ref([])

const form = ref({
  project_id: null,
  username: '',
  nickname: '',
  tiktok_id: '',
  sec_uid: '',
  monitor_interval: 60,  // 60 minutes = 1 hour
  use_proxy: true,
  proxy_id: null,
  enable_video_monitoring: true,
  is_active: true
})

const rules = {
  project_id: [
    { required: true, message: '请选择所属项目', trigger: 'change' }
  ],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  monitor_interval: [
    { required: true, message: '请输入监控间隔', trigger: 'blur' },
    { type: 'number', min: 5, max: 1440, message: '间隔必须在 5-1440 分钟之间', trigger: 'blur' }
  ]
}

const loadProxies = async () => {
  try {
    const data = await getProxies()
    proxies.value = data.filter(p => p.is_active)
  } catch (error) {
    console.error('Failed to load proxies:', error)
  }
}

const resetForm = () => {
  form.value = {
    project_id: null,
    username: '',
    nickname: '',
    tiktok_id: '',
    sec_uid: '',
    monitor_interval: 60,
    use_proxy: true,
    proxy_id: null,
    enable_video_monitoring: true,
    is_active: true
  }
  formRef.value?.clearValidate()
}

const handleClose = () => {
  visible.value = false
  resetForm()
}

const handleSubmit = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    // Convert minutes to seconds for backend
    const payload = {
      ...form.value,
      monitor_interval: form.value.monitor_interval * 60
    }

    // Remove empty optional fields
    if (!payload.nickname) delete payload.nickname
    if (!payload.tiktok_id) delete payload.tiktok_id
    if (!payload.sec_uid) delete payload.sec_uid
    if (!payload.use_proxy || !payload.proxy_id) delete payload.proxy_id

    if (isEdit.value) {
      await updateAccount(props.account.id, payload)
      ElMessage.success('账号更新成功')
    } else {
      await createAccount(payload)
      ElMessage.success('账号创建成功')
    }

    emit('success')
    handleClose()
  } catch (error) {
    console.error('Failed to submit account:', error)
    ElMessage.error(isEdit.value ? '账号更新失败' : '账号创建失败')
  } finally {
    submitting.value = false
  }
}

watch(() => props.modelValue, (val) => {
  if (val) {
    loadProxies()
    if (props.account) {
      // Edit mode: populate form with account data
      form.value = {
        project_id: props.account.project_id,
        username: props.account.username,
        nickname: props.account.nickname || '',
        tiktok_id: props.account.tiktok_id || '',
        sec_uid: props.account.sec_uid || '',
        monitor_interval: Math.round(props.account.monitor_interval / 60),  // Convert seconds to minutes
        use_proxy: props.account.use_proxy,
        proxy_id: props.account.proxy_id,
        enable_video_monitoring: props.account.enable_video_monitoring,
        is_active: props.account.is_active
      }
    } else {
      resetForm()
    }
  }
})
</script>
