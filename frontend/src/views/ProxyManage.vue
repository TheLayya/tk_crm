<template>
  <div class="proxy-manage">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>代理管理</span>
          <div>
            <el-button 
              v-if="selectedProxies.length > 0" 
              type="success" 
              @click="handleBatchEnable"
            >
              <el-icon><Check /></el-icon>
              批量启用 ({{ selectedProxies.length }})
            </el-button>
            <el-button 
              v-if="selectedProxies.length > 0" 
              type="warning" 
              @click="handleBatchDisable"
            >
              <el-icon><Close /></el-icon>
              批量禁用 ({{ selectedProxies.length }})
            </el-button>
            <el-button 
              v-if="selectedProxies.length > 0" 
              type="danger" 
              @click="handleBatchDelete"
            >
              <el-icon><Delete /></el-icon>
              批量删除 ({{ selectedProxies.length }})
            </el-button>
            <el-button type="success" @click="handleBatchCreate">
              <el-icon><Upload /></el-icon>
              批量导入
            </el-button>
            <el-button type="primary" @click="handleCreate">
              <el-icon><Plus /></el-icon>
              添加代理
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="proxies" v-loading="loading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="proxy_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.proxy_type?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="host" label="IP" width="150" />
        <el-table-column prop="port" label="端口" width="100" />
        <el-table-column prop="username" label="用户名" width="120">
          <template #default="{ row }">
            {{ row.username || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="密码" width="150">
          <template #default="{ row }">
            <div v-if="row.password" style="display: flex; align-items: center; gap: 8px;">
              <span>{{ visiblePasswords[row.id] ? row.password : '******' }}</span>
              <el-icon 
                style="cursor: pointer; color: #409eff;" 
                @click="togglePasswordVisibility(row.id)"
              >
                <View v-if="!visiblePasswords[row.id]" />
                <Hide v-else />
              </el-icon>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_test_result" label="测试结果" width="100">
          <template #default="{ row }">
            <el-tag
              v-if="row.last_test_result"
              :type="row.last_test_result === 'success' ? 'success' : 'danger'"
              size="small"
            >
              {{ row.last_test_result === 'success' ? '成功' : '失败' }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_test_at" label="最后测试" width="180">
          <template #default="{ row }">
            {{ formatDate(row.last_test_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleTest(row)" :loading="testingIds.includes(row.id)">
              测试
            </el-button>
            <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="500px"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="代理类型" prop="proxy_type">
          <el-select v-model="form.proxy_type" placeholder="选择代理类型">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>

        <el-form-item label="IP地址" prop="host">
          <el-input v-model="form.host" placeholder="例如: 127.0.0.1" />
        </el-form-item>

        <el-form-item label="端口" prop="port">
          <el-input-number v-model="form.port" :min="1" :max="65535" placeholder="端口号" />
        </el-form-item>

        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="可选" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="可选" show-password />
        </el-form-item>

        <el-form-item label="启用状态" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- Batch Import Dialog -->
    <el-dialog
      v-model="batchDialogVisible"
      title="批量导入代理"
      width="600px"
    >
      <el-alert
        title="格式说明"
        type="info"
        :closable="false"
        style="margin-bottom: 15px"
      >
        <p>每行一个代理，支持以下格式：</p>
        <ul style="margin: 5px 0; padding-left: 20px;">
          <li><code>ip:port</code> - 例如: 192.168.1.1:8080</li>
          <li><code>ip:port:username:password</code> - 例如: 192.168.1.1:8080:user:pass</li>
        </ul>
      </el-alert>

      <el-form :model="batchForm" label-width="100px">
        <el-form-item label="代理类型">
          <el-select v-model="batchForm.proxy_type">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>

        <el-form-item label="代理列表">
          <el-input
            v-model="batchForm.proxies_text"
            type="textarea"
            :rows="10"
            placeholder="请输入代理列表，每行一个&#10;例如：&#10;192.168.1.1:8080:user1:pass1&#10;192.168.1.2:8080&#10;192.168.1.3:1080:user3:pass3"
          />
        </el-form-item>

        <el-form-item label="启用状态">
          <el-switch v-model="batchForm.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBatchSubmit" :loading="batchSubmitting">
          导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, View, Hide, Delete, Check, Close } from '@element-plus/icons-vue'
import { getProxies, createProxy, updateProxy, deleteProxy, testProxy, batchCreateProxies } from '@/api/proxies'

const proxies = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const batchDialogVisible = ref(false)
const submitting = ref(false)
const batchSubmitting = ref(false)
const testingIds = ref([])
const formRef = ref(null)
const editingId = ref(null)
const visiblePasswords = ref({}) // 记录哪些密码是可见的
const selectedProxies = ref([]) // 选中的代理列表

const form = ref({
  proxy_type: 'http',
  host: '',
  port: null,
  username: '',
  password: '',
  is_active: true
})

const batchForm = ref({
  proxies_text: '',
  proxy_type: 'socks5',
  is_active: true
})

const rules = {
  proxy_type: [
    { required: true, message: '请选择代理类型', trigger: 'change' }
  ],
  host: [
    { required: true, message: '请输入IP地址', trigger: 'blur' }
  ],
  port: [
    { required: true, message: '请输入端口号', trigger: 'blur' },
    { type: 'number', message: '端口号必须是数字', trigger: 'blur' }
  ]
}

const dialogTitle = computed(() => {
  return editingId.value ? '编辑代理' : '添加代理'
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleString('zh-CN')
}

const togglePasswordVisibility = (proxyId) => {
  visiblePasswords.value[proxyId] = !visiblePasswords.value[proxyId]
}

const handleSelectionChange = (selection) => {
  selectedProxies.value = selection
}

const handleBatchEnable = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要启用选中的 ${selectedProxies.value.length} 个代理吗？`,
      '批量启用',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    let successCount = 0
    let failCount = 0
    
    for (const proxy of selectedProxies.value) {
      try {
        await updateProxy(proxy.id, { is_active: true })
        successCount++
      } catch (error) {
        console.error(`Failed to enable proxy ${proxy.id}:`, error)
        failCount++
      }
    }
    
    if (successCount > 0) {
      ElMessage.success(`成功启用 ${successCount} 个代理${failCount > 0 ? `，失败 ${failCount} 个` : ''}`)
      loadProxies()
    } else {
      ElMessage.error('批量启用失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to batch enable proxies:', error)
    }
  }
}

const handleBatchDisable = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要禁用选中的 ${selectedProxies.value.length} 个代理吗？`,
      '批量禁用',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    let successCount = 0
    let failCount = 0
    
    for (const proxy of selectedProxies.value) {
      try {
        await updateProxy(proxy.id, { is_active: false })
        successCount++
      } catch (error) {
        console.error(`Failed to disable proxy ${proxy.id}:`, error)
        failCount++
      }
    }
    
    if (successCount > 0) {
      ElMessage.success(`成功禁用 ${successCount} 个代理${failCount > 0 ? `，失败 ${failCount} 个` : ''}`)
      loadProxies()
    } else {
      ElMessage.error('批量禁用失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to batch disable proxies:', error)
    }
  }
}

const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedProxies.value.length} 个代理吗？此操作不可恢复！`,
      '批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    let successCount = 0
    let failCount = 0
    
    for (const proxy of selectedProxies.value) {
      try {
        await deleteProxy(proxy.id)
        successCount++
      } catch (error) {
        console.error(`Failed to delete proxy ${proxy.id}:`, error)
        failCount++
      }
    }
    
    if (successCount > 0) {
      ElMessage.success(`成功删除 ${successCount} 个代理${failCount > 0 ? `，失败 ${failCount} 个` : ''}`)
      loadProxies()
    } else {
      ElMessage.error('批量删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to batch delete proxies:', error)
    }
  }
}

const loadProxies = async () => {
  loading.value = true
  try {
    proxies.value = await getProxies()
  } catch (error) {
    console.error('Failed to load proxies:', error)
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  editingId.value = null
  form.value = {
    proxy_type: 'http',
    host: '',
    port: null,
    username: '',
    password: '',
    is_active: true
  }
  dialogVisible.value = true
}

const handleBatchCreate = () => {
  batchForm.value = {
    proxies_text: '',
    proxy_type: 'socks5',
    is_active: true
  }
  batchDialogVisible.value = true
}

const handleEdit = (row) => {
  editingId.value = row.id
  form.value = {
    proxy_type: row.proxy_type,
    host: row.host,
    port: row.port,
    username: row.username || '',
    password: '', // Don't populate password for security
    is_active: row.is_active
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const data = { ...form.value }
    // Remove empty username/password
    if (!data.username) delete data.username
    if (!data.password) delete data.password

    if (editingId.value) {
      await updateProxy(editingId.value, data)
      ElMessage.success('代理更新成功')
    } else {
      await createProxy(data)
      ElMessage.success('代理创建成功')
    }
    dialogVisible.value = false
    loadProxies()
  } catch (error) {
    console.error('Failed to submit proxy:', error)
  } finally {
    submitting.value = false
  }
}

const handleBatchSubmit = async () => {
  if (!batchForm.value.proxies_text.trim()) {
    ElMessage.warning('请输入代理列表')
    return
  }

  batchSubmitting.value = true
  try {
    const result = await batchCreateProxies(batchForm.value)
    
    let message = `成功导入 ${result.success_count} 个代理`
    if (result.fail_count > 0) {
      message += `，失败 ${result.fail_count} 个`
    }
    
    if (result.errors.length > 0) {
      ElMessageBox.alert(
        result.errors.join('\n'),
        '导入结果',
        {
          confirmButtonText: '确定',
          type: result.success_count > 0 ? 'warning' : 'error'
        }
      )
    } else {
      ElMessage.success(message)
    }
    
    if (result.success_count > 0) {
      batchDialogVisible.value = false
      loadProxies()
    }
  } catch (error) {
    console.error('Failed to batch create proxies:', error)
    ElMessage.error('批量导入失败')
  } finally {
    batchSubmitting.value = false
  }
}

const handleDelete = async (row) => {
  const displayName = row.username 
    ? `${row.username}@${row.host}:${row.port}` 
    : `${row.host}:${row.port}`
  
  try {
    await ElMessageBox.confirm(
      `确定要删除代理"${displayName}"吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await deleteProxy(row.id)
    ElMessage.success('代理删除成功')
    loadProxies()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to delete proxy:', error)
    }
  }
}

const handleTest = async (row) => {
  testingIds.value.push(row.id)
  try {
    const result = await testProxy(row.id)
    if (result.success) {
      ElMessage.success(`代理测试成功 (响应时间: ${result.response_time}ms)`)
    } else {
      ElMessage.error(`代理测试失败: ${result.error}`)
    }
    loadProxies()
  } catch (error) {
    console.error('Failed to test proxy:', error)
  } finally {
    testingIds.value = testingIds.value.filter(id => id !== row.id)
  }
}

onMounted(() => {
  loadProxies()
})
</script>

<style scoped>
.proxy-manage {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header > div {
  display: flex;
  gap: 10px;
}

code {
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}
</style>
