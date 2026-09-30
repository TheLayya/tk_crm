<template>
  <div class="device-detail">
    <el-page-header @back="$router.push('/devices')" :content="detailTitle" />

    <el-card style="margin-top: 16px">
      <el-skeleton v-if="loading" :rows="4" animated />
      <template v-else>
        <!-- 基本信息 -->
          <el-empty v-if="loadError" :description="loadError">
            <el-button type="primary" @click="retryDetail">重新加载</el-button>
          </el-empty>

          <el-descriptions :column="2" border v-if="device.id" class="desktop-desc">
            <el-descriptions-item label="名称">{{ device.name }}</el-descriptions-item>
            <el-descriptions-item label="类型">
              {{ device.device_type === 'pc' ? '💻 电脑' : '📱 手机' }}
            </el-descriptions-item>
            <el-descriptions-item label="所属人">{{ device.owner_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="绑定节点">
              {{ device.node_ip || '未绑定' }}
            </el-descriptions-item>
            <el-descriptions-item label="备注">{{ device.remark || '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(device.created_at) }}</el-descriptions-item>
          </el-descriptions>

          <!-- 移动端字段列表 -->
          <div class="mobile-fields" v-if="device.id">
            <div class="field-row"><span class="field-label">名称</span><span class="field-val">{{ device.name }}</span></div>
            <div class="field-row"><span class="field-label">类型</span><span class="field-val">{{ device.device_type === 'pc' ? '💻 电脑' : '📱 手机' }}</span></div>
            <div class="field-row"><span class="field-label">所属人</span><span class="field-val">{{ device.owner_name || '-' }}</span></div>
            <div class="field-row"><span class="field-label">绑定节点</span><span class="field-val">{{ device.node_ip || '未绑定' }}</span></div>
            <div class="field-row"><span class="field-label">备注</span><span class="field-val">{{ device.remark || '-' }}</span></div>
            <div class="field-row"><span class="field-label">创建时间</span><span class="field-val">{{ formatTime(device.created_at) }}</span></div>
          </div>

          <!-- 操作按钮（有管理权限可见） -->
          <div style="margin-top: 16px" v-if="authStore.hasPermission('device:manage') && device.id">
            <el-button type="primary" @click="showEditDialog">编辑</el-button>
            <el-popconfirm title="确定删除此设备？（历史轨迹保留）" @confirm="handleDelete">
              <template #reference>
                <el-button type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>

          <el-empty v-if="!loadError && !device.id" description="设备不存在或已删除">
            <el-button type="primary" @click="$router.push('/devices')">返回列表</el-button>
          </el-empty>
      </template>
    </el-card>

    <el-card class="history-card" style="margin-top: 16px">
      <template #header>历史轨迹</template>
          <el-skeleton v-if="logsLoading" :rows="5" animated />
          <el-empty v-else-if="logsError" :description="logsError">
            <el-button type="primary" @click="retryLogs">重新加载</el-button>
          </el-empty>
          <template v-else-if="logs.length">
            <el-timeline style="padding-left: 4px;">
              <el-timeline-item
                v-for="log in logs"
                :key="log.id"
                :timestamp="formatTime(log.created_at)"
                :type="log.action === 'CREATE' ? 'success' : log.action === 'DELETE' ? 'danger' : 'primary'"
              >
                <div class="log-line">
                  <span class="log-actor">{{ log.username }}</span>
                  <span class="log-action">{{ actionLabel(log.action) }}</span>
                </div>
                <div v-if="log.changes" class="log-changes">
                  <div
                    v-for="(change, field) in displayableChanges(log.changes)"
                    :key="field"
                    class="log-change-item"
                  >
                    {{ fieldLabel(field) }}: {{ formatChange(change.old) }} → {{ formatChange(change.new) }}
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-pagination
              v-if="logsTotal > logQuery.limit"
              v-model:current-page="logQuery.page"
              :page-size="logQuery.limit"
              :total="logsTotal"
              layout="prev, pager, next"
              style="justify-content: flex-end; margin-top: 12px;"
              @current-change="loadLogs"
            />
          </template>
          <el-empty v-else description="暂无历史轨迹" />
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editVisible" title="编辑设备" width="500px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="editForm.device_type">
            <el-radio value="pc">💻 电脑</el-radio>
            <el-radio value="phone">📱 手机</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="isSuperAdmin" label="所属人">
          <el-select v-model="editForm.owner_id" placeholder="请选择" style="width:100%" filterable>
            <el-option
              v-for="m in members"
              :key="m.id"
              :label="m.real_name || m.username"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定节点">
          <el-select
            v-model="editForm.node_id"
            placeholder="可选；清空表示解绑"
            style="width:100%"
            clearable
            filterable
            remote
            :remote-method="searchNodes"
            :loading="nodesLoading"
          >
            <el-option
              v-for="n in bindableNodes"
              :key="n.id"
              :label="`${n.ip}:${n.port} (${n.protocol})`"
              :value="n.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { getDevice, updateDevice, deleteDevice, getDeviceLogs, getBindableNodes } from '@/api/devices'
import { getMembers } from '@/api/team'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isSuperAdmin = computed(() => !!authStore.user?.is_super_admin)

const device = ref({})
const logs = ref([])
const logsTotal = ref(0)
const logQuery = ref({ page: 1, limit: 50 })
const loading = ref(true)
const loadError = ref('')
const logsLoading = ref(true)
const logsError = ref('')
const editVisible = ref(false)
const editLoading = ref(false)
const editForm = ref({ name: '', device_type: 'pc', owner_id: null, node_id: null, remark: '' })
const members = ref([])
const bindableNodes = ref([])
const nodesLoading = ref(false)

// 请求序号守卫：晚发起的请求覆盖早发起的结果
let deviceRequestSeq = 0
let logsRequestSeq = 0
let nodesRequestSeq = 0

// 日志可展示字段白名单（服务端只记录业务字段；此处兜底防未知/敏感字段直出）
const DISPLAYABLE_LOG_FIELDS = ['name', 'device_type', 'owner_id', 'node_id', 'node_ids', 'relations', 'remark', 'is_deleted']
const FIELD_LABELS = {
  name: '名称', device_type: '类型', owner_id: '所属人',
  node_id: '绑定节点', node_ids: '绑定节点', relations: '关联关系', remark: '备注', is_deleted: '删除状态'
}

const detailTitle = computed(() => (device.value.id ? `设备详情: ${device.value.name}` : '设备详情'))

onMounted(() => {
  loadDevice(true)
  loadLogs(true)
})

// 路由参数变化（同组件复用）时重载
watch(
  () => route.params.id,
  () => {
    loadDevice(true)
    loadLogs(true)
  }
)

/** 加载设备详情 */
async function loadDevice(reset = false) {
  const seq = ++deviceRequestSeq
  if (reset) {
    loading.value = true
    loadError.value = ''
    device.value = {}
  }

  try {
    const res = await getDevice(route.params.id)
    if (seq !== deviceRequestSeq) return // 过期响应丢弃
    device.value = res || {}
    loadError.value = ''
  } catch (err) {
    if (seq !== deviceRequestSeq) return
    // 403/404（删除或所有权变化）：清空旧数据，避免过期信息残留
    device.value = {}
    loadError.value = err?.response?.status === 404 ? '设备不存在或已删除' : '加载设备详情失败'
    ElMessage.error(err?.response?.data?.detail || '加载设备详情失败')
  } finally {
    if (seq === deviceRequestSeq) {
      loading.value = false
    }
  }
}

/** 加载操作日志（分页）。参数为数字时视为页码切换；true 表示重置。 */
async function loadLogs(reset = false) {
  const seq = ++logsRequestSeq
  if (typeof reset === 'number') {
    logQuery.value.page = reset
  } else if (reset === true) {
    logQuery.value.page = 1
    logsError.value = ''
    logs.value = []
    logsTotal.value = 0
  }
  logsLoading.value = true

  try {
    const params = {
      skip: (logQuery.value.page - 1) * logQuery.value.limit,
      limit: logQuery.value.limit
    }
    const res = await getDeviceLogs(route.params.id, params)
    if (seq !== logsRequestSeq) return
    logs.value = res.items || []
    logsTotal.value = res.total || 0
    logsError.value = ''
  } catch (err) {
    if (seq !== logsRequestSeq) return
    logs.value = []
    logsTotal.value = 0
    logsError.value = '加载操作日志失败'
    ElMessage.error(err?.response?.data?.detail || '加载操作日志失败')
  } finally {
    if (seq === logsRequestSeq) {
      logsLoading.value = false
    }
  }
}

function retryDetail() {
  loadDevice(true)
  loadLogs(true)
}

function retryLogs() {
  loadLogs(true)
}

function formatTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN') : '-'
}

function actionLabel(action) {
  return { CREATE: '创建', UPDATE: '更新', DELETE: '删除' }[action] || action
}

function formatChange(value) {
  if (value === null || value === undefined || value === '') return '空'
  if (typeof value === 'object') {
    try { return JSON.stringify(value, null, 2) } catch { return String(value) }
  }
  return String(value)
}

/** 仅渲染白名单字段，防敏感/未知字段直出 */
function displayableChanges(changes) {
  const out = {}
  for (const field of DISPLAYABLE_LOG_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(changes, field)) {
      out[field] = changes[field]
    }
  }
  return out
}

function fieldLabel(field) {
  return FIELD_LABELS[field] || field
}

/** 删除设备（软删除） */
async function handleDelete() {
  try {
    await deleteDevice(device.value.id)
    ElMessage.success('删除成功（历史轨迹保留）')
    router.push('/devices')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

/** 打开编辑对话框并填充当前值 */
async function showEditDialog() {
  editForm.value = {
    name: device.value.name || '',
    device_type: device.value.device_type || 'pc',
    owner_id: device.value.owner_id ?? null,
    node_id: device.value.node_id ?? null,
    remark: device.value.remark || ''
  }
  if (isSuperAdmin.value) {
    try {
      const res = await getMembers({ page: 1, size: 500 })
      members.value = res.items || []
    } catch {
      members.value = []
    }
  }
  searchNodes('')
  editVisible.value = true
}

/** 可绑定节点远程搜索（编辑时放行自身已绑定节点；序号守卫防乱序） */
async function searchNodes(q = '') {
  const seq = ++nodesRequestSeq
  nodesLoading.value = true
  try {
    const res = await getBindableNodes({ q, exclude_device_id: device.value.id })
    if (seq !== nodesRequestSeq) return
    bindableNodes.value = res.items || []
  } catch {
    if (seq !== nodesRequestSeq) return
    bindableNodes.value = []
  } finally {
    if (seq === nodesRequestSeq) {
      nodesLoading.value = false
    }
  }
}

/** 保存编辑 */
async function handleEdit() {
  if (!editForm.value.name || !editForm.value.name.trim()) {
    ElMessage.warning('请输入设备名称')
    return
  }
  editLoading.value = true
  try {
    const payload = {
      name: editForm.value.name.trim(),
      device_type: editForm.value.device_type,
      remark: editForm.value.remark
    }
    // node_id 仅在变化时提交；Element Plus clearable 清空会赋值 undefined → 归一化为 null（解绑）
    const originalNodeId = device.value.node_id ?? null
    const desiredNodeId = editForm.value.node_id === undefined ? null : editForm.value.node_id
    if (desiredNodeId !== originalNodeId) {
      payload.node_id = desiredNodeId // null = 解绑
    }
    if (isSuperAdmin.value) {
      payload.owner_id = editForm.value.owner_id
    }
    await updateDevice(device.value.id, payload)
    ElMessage.success('编辑成功')
    editVisible.value = false
    loadDevice()
    loadLogs(true)
  } catch (err) {
    // 透出服务端业务错误（如 409 节点占用），而非笼统"编辑失败"
    ElMessage.error(err?.response?.data?.detail || '编辑失败')
  } finally {
    editLoading.value = false
  }
}
</script>

<style scoped>
.mobile-fields {
  display: none;
}

.log-line {
  display: flex;
  gap: 8px;
  align-items: center;
}

.log-actor {
  font-weight: 600;
}

.log-action {
  color: #909399;
  font-size: 12px;
}

.log-changes {
  margin-top: 4px;
}

.log-change-item {
  font-size: 12px;
  color: #606266;
  font-family: monospace;
}

@media (max-width: 767px) {
  .desktop-desc {
    display: none;
  }

  .mobile-fields {
    display: block;
  }

  .field-row {
    display: flex;
    padding: 10px 0;
    border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
    font-size: 14px;
  }

  .field-label {
    flex-shrink: 0;
    width: 80px;
    color: #909399;
    font-size: 13px;
  }

  .field-val {
    flex: 1;
    word-break: break-all;
  }
}
</style>
