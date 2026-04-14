<template>
  <el-dialog
    v-model="visible"
    title="导入账号"
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

      <el-form-item label="选择文件" required>
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          accept=".csv,.xlsx,.xls"
          drag
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            拖拽文件到此处或<em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              支持 CSV 和 Excel 文件，文件需包含用户名列
            </div>
          </template>
        </el-upload>
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
      <el-button type="primary" @click="handleSubmit" :loading="uploading">
        {{ results ? '关闭' : '开始导入' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { importFile } from '@/api/accounts'

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
const uploadRef = ref(null)
const uploading = ref(false)
const results = ref(null)
const selectedFile = ref(null)

const form = ref({
  project_id: null
})

const statusText = (status) => {
  const map = {
    success: '成功',
    duplicate: '重复',
    failed: '失败'
  }
  return map[status] || status
}

const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

const handleExceed = () => {
  ElMessage.warning('只能上传一个文件')
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

  if (!selectedFile.value) {
    ElMessage.warning('请选择要导入的文件')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('project_id', form.value.project_id)

    const result = await importFile(formData)
    results.value = result

    if (result.success > 0) {
      ElMessage.success(`成功导入 ${result.success} 个账号`)
      emit('success')
    }
  } catch (error) {
    console.error('Failed to import file:', error)
  } finally {
    uploading.value = false
  }
}

const handleClose = () => {
  visible.value = false
  // Reset form after dialog closes
  setTimeout(() => {
    form.value = {
      project_id: null
    }
    selectedFile.value = null
    results.value = null
    uploadRef.value?.clearFiles()
  }, 300)
}
</script>

<style scoped>
.results {
  margin-top: 20px;
}

.result-summary {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.el-icon--upload {
  font-size: 67px;
  color: #c0c4cc;
  margin: 40px 0 16px;
}
</style>
