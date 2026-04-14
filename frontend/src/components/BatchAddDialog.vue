<template>
  <el-dialog
    v-model="visible"
    title="批量添加账号"
    width="600px"
    @close="handleClose"
  >
    <el-form :model="form" ref="formRef" label-width="100px">
      <el-form-item label="选择项目" prop="project_id" required>
        <el-select v-model="form.project_id" placeholder="请选择项目">
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
      </el-form-item>
      
      <el-form-item label="用户名列表" prop="usernames" required>
        <el-input
          v-model="form.usernames"
          type="textarea"
          :rows="10"
          placeholder="每行一个 TikTok 用户名，例如：&#10;username1&#10;username2&#10;&#10;注意：此处只填用户名，代理请在「代理管理」页面添加"
        />
        <div class="hint">每行输入一个 TikTok 用户名，系统会自动去除空行和首尾空格</div>
      </el-form-item>

      <el-form-item label="监控间隔" prop="monitor_interval">
        <el-input-number
          v-model="form.monitor_interval"
          :min="5"
          :max="1440"
          placeholder="留空使用系统默认值"
        />
        <span class="hint" style="margin-left: 10px">分钟（留空使用系统默认值）</span>
      </el-form-item>
    </el-form>

    <!-- Results Display -->
    <div v-if="results" class="results">
      <el-divider />
      <h4>导入结果</h4>
      <div class="result-summary">
        <el-tag type="success">成功: {{ results.success }}</el-tag>
        <el-tag type="warning">重复: {{ results.duplicates }}</el-tag>
        <el-tag type="danger">失败: {{ results.failed }}</el-tag>
        <el-tag type="info">总计: {{ results.total }}</el-tag>
      </div>

      <el-table :data="results.results" max-height="300" style="margin-top: 10px">
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="row.status === 'success' ? 'success' : row.status === 'duplicate' ? 'warning' : 'danger'"
              size="small"
            >
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" />
      </el-table>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        {{ results ? '关闭' : '开始导入' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { batchImportAccounts } from '@/api/accounts'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  projects: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const formRef = ref(null)
const submitting = ref(false)
const results = ref(null)

const form = ref({
  project_id: null,
  usernames: '',
  monitor_interval: null
})

const statusText = (status) => {
  const map = {
    success: '成功',
    duplicate: '重复',
    failed: '失败'
  }
  return map[status] || status
}

const handleSubmit = async () => {
  if (results.value) {
    handleClose()
    return
  }

  if (!form.value.project_id) {
    ElMessage.warning('请选择项目')
    return
  }

  if (!form.value.usernames.trim()) {
    ElMessage.warning('请输入用户名列表')
    return
  }

  submitting.value = true
  try {
    const data = {
      project_id: form.value.project_id,
      usernames: form.value.usernames,
      monitor_interval: form.value.monitor_interval ? form.value.monitor_interval * 60 : null
    }

    const result = await batchImportAccounts(data)
    results.value = result
    
    if (result.success > 0) {
      ElMessage.success(`成功导入 ${result.success} 个账号`)
      emit('success')
    }
  } catch (error) {
    console.error('Failed to batch import:', error)
  } finally {
    submitting.value = false
  }
}

const handleClose = () => {
  visible.value = false
  // Reset form after dialog closes
  setTimeout(() => {
    form.value = {
      project_id: null,
      usernames: '',
      monitor_interval: null
    }
    results.value = null
  }, 300)
}
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.results {
  margin-top: 20px;
}

.result-summary {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}
</style>
