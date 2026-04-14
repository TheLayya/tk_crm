<template>
  <el-dialog
    v-model="visible"
    title="导出账号"
    width="500px"
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

      <el-form-item label="导出格式" prop="format" required>
        <el-radio-group v-model="form.format">
          <el-radio value="csv">CSV</el-radio>
          <el-radio value="excel">Excel (XLSX)</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-alert
        title="导出说明"
        type="info"
        :closable="false"
        show-icon
      >
        <p>导出文件将包含以下字段：</p>
        <ul>
          <li>用户名</li>
          <li>昵称</li>
          <li>粉丝数</li>
          <li>最后检查时间</li>
          <li>激活状态</li>
        </ul>
      </el-alert>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon>
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { exportAccounts } from '@/api/accounts'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  projects: {
    type: Array,
    default: () => []
  },
  currentProjectId: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const formRef = ref(null)
const exporting = ref(false)

const form = ref({
  project_id: null,
  format: 'csv'
})

// Set default project when dialog opens
watch(visible, (val) => {
  if (val && props.currentProjectId) {
    form.value.project_id = props.currentProjectId
  }
})

const handleExport = async () => {
  if (!form.value.project_id) {
    ElMessage.warning('请选择项目')
    return
  }

  exporting.value = true
  try {
    const params = {
      project_id: form.value.project_id,
      format: form.value.format
    }

    const blob = await exportAccounts(params)
    
    // Create download link
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    
    // Generate filename with project name and date
    const project = props.projects.find(p => p.id === form.value.project_id)
    const projectName = project ? project.name : 'accounts'
    const date = new Date().toISOString().split('T')[0]
    const extension = form.value.format === 'csv' ? 'csv' : 'xlsx'
    link.download = `${projectName}_${date}.${extension}`
    
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    ElMessage.success('导出成功')
    handleClose()
  } catch (error) {
    console.error('Failed to export accounts:', error)
  } finally {
    exporting.value = false
  }
}

const handleClose = () => {
  visible.value = false
  // Reset form after dialog closes
  setTimeout(() => {
    form.value = {
      project_id: null,
      format: 'csv'
    }
  }, 300)
}
</script>

<style scoped>
.el-alert ul {
  margin: 10px 0 0 0;
  padding-left: 20px;
}

.el-alert li {
  margin: 5px 0;
}
</style>
