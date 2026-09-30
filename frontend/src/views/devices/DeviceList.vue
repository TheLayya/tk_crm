<template>
  <div class="device-list">
    <div class="page-toolbar">
      <div>
        <div class="page-title">终端资产</div>
        <div class="page-subtitle">{{ resultSummary }}</div>
      </div>
      <el-button v-if="hasFilters" size="small" @click="resetFilters">清空筛选</el-button>
    </div>

    <!-- 搜索/筛选操作栏 -->
    <el-card class="filter-card">
      <el-row :gutter="8">
        <el-col :xs="12" :sm="6">
          <el-input
            v-model="query.keyword"
            placeholder="搜索设备名称"
            clearable
            @change="applyFilters"
            @clear="applyFilters"
            @keyup.enter="applyFilters"
          />
        </el-col>
        <el-col :xs="12" :sm="4">
          <el-select
            v-model="query.device_type"
            placeholder="类型"
            clearable
            @change="applyFilters"
            @clear="applyFilters"
          >
            <el-option label="💻 电脑" value="pc" />
            <el-option label="📱 手机" value="phone" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="5" v-if="isSuperAdmin">
          <el-select
            v-model="query.owner_id"
            placeholder="所属人"
            clearable
            filterable
            @change="applyFilters"
            @clear="applyFilters"
          >
            <el-option
              v-for="m in members"
              :key="m.id"
              :label="m.real_name || m.username"
              :value="m.id"
            />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="9" style="text-align: right">
          <el-button
            v-if="authStore.hasPermission('device:manage')"
            type="primary"
            size="small"
            @click="showCreateDialog"
          >新增设备</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 桌面端：表格 -->
    <el-card class="desktop-table">
      <el-table
        :data="devices"
        v-loading="loading"
        :empty-text="emptyDescription"
        element-loading-text="正在加载设备"
        stripe
      >
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="device_type" label="类型" width="100">
          <template #default="{ row }">
            {{ row.device_type === 'pc' ? '💻 电脑' : '📱 手机' }}
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="所属人" width="110" />
        <el-table-column prop="node_ip" label="绑定节点" min-width="150">
          <template #default="{ row }">
            <span v-if="row.node_ip">{{ row.node_ip }}</span>
            <span v-else style="color: #909399;">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column label="绑定账号" min-width="400">
          <template #default="{ row }">
            <LinkedAccountCards :accounts="row.accounts || []" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button v-if="authStore.hasPermission('device:manage')" type="success" link @click="openRelations(row)">关联</el-button>
            <el-button type="primary" link @click="$router.push(`/devices/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-if="total > 0"
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="loadDevices"
        @size-change="handleSizeChange"
      />
    </el-card>

    <!-- 移动端：卡片列表 -->
    <div
      class="mobile-cards"
      v-loading="loading && devices.length > 0"
      element-loading-text="正在加载设备"
    >
      <el-skeleton v-if="loading && devices.length === 0" :rows="6" animated />
      <template v-else>
        <div
          v-for="d in devices"
          :key="d.id"
          class="device-card"
          @click="$router.push(`/devices/${d.id}`)"
        >
          <div class="card-top">
            <span class="card-name">{{ d.device_type === 'pc' ? '💻' : '📱' }} {{ d.name }}</span>
          </div>
          <div class="card-meta">
            <span>所属: {{ d.owner_name || '-' }}</span>
            <span>节点: {{ d.node_ip || '未绑定' }}</span>
          </div>
          <LinkedAccountCards :accounts="d.accounts || []" />
        </div>
      </template>
      <el-empty v-if="!loading && devices.length === 0" :description="emptyDescription" />
    </div>

    <!-- 新增设备对话框 -->
    <el-dialog v-model="createVisible" title="新增设备" width="500px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" placeholder="如: 01电脑" maxlength="100" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="createForm.device_type">
            <el-radio value="pc">💻 电脑</el-radio>
            <el-radio value="phone">📱 手机</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="isSuperAdmin" label="所属人">
          <el-select v-model="createForm.owner_id" placeholder="请选择" style="width:100%" filterable>
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
            v-model="createForm.node_id"
            placeholder="可选，绑定后该节点不可被其他设备使用"
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
          <el-input v-model="createForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createLoading" @click="handleCreate">确认创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="relationVisible" title="关联账号与代理节点" width="520px">
      <el-alert title="一个手机终端可绑定多个运营账号和多个代理节点，清空后保存即可解除。" type="info" :closable="false" style="margin-bottom:16px" />
      <el-form label-width="90px">
        <el-form-item label="终端"><strong>{{ relationRow?.name }}</strong></el-form-item>
        <el-form-item label="运营账号"><el-select v-model="relationForm.account_ids" multiple collapse-tags collapse-tags-tooltip clearable filterable style="width:100%"><el-option v-for="a in relationAccounts" :key="a.id" :label="`${a.platform} / ${a.account}`" :value="a.id" /></el-select></el-form-item>
        <el-form-item label="代理节点"><el-select v-model="relationForm.node_ids" multiple clearable filterable collapse-tags style="width:100%"><el-option v-for="n in relationNodes" :key="n.id" :label="`${n.ip}:${n.port}`" :value="n.id" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="relationVisible=false">取消</el-button><el-button type="primary" :loading="relationSaving" @click="saveRelations">保存关联</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { getDevices, createDevice, getBindableNodes, updateDeviceRelations } from '@/api/devices'
import { listOpAccounts } from '@/api/op_accounts'
import { getProxyNodes } from '@/api/proxy_nodes'
import { getMembers } from '@/api/team'
import LinkedAccountCards from '@/components/LinkedAccountCards.vue'

const authStore = useAuthStore()
const isSuperAdmin = computed(() => !!authStore.user?.is_super_admin)

/** 列表状态 */
const devices = ref([])
const total = ref(0)
const loading = ref(false)

/** 筛选查询参数 */
const query = reactive({ page: 1, page_size: 20, keyword: '', device_type: '', owner_id: '' })
const hasFilters = computed(() => Boolean(query.keyword || query.device_type || query.owner_id))
const emptyDescription = computed(() => (hasFilters.value ? '没有匹配的设备' : '暂无设备'))
const selectedOwnerName = computed(
  () => members.value.find((m) => m.id === query.owner_id)?.real_name
    || members.value.find((m) => m.id === query.owner_id)?.username
    || ''
)
const resultSummary = computed(() => {
  if (loading.value && total.value === 0) return '正在加载设备数据'
  const parts = []
  if (query.keyword) parts.push(`关键词: ${query.keyword}`)
  if (query.device_type) parts.push(`类型: ${query.device_type === 'pc' ? '电脑' : '手机'}`)
  if (selectedOwnerName.value) parts.push(`所属人: ${selectedOwnerName.value}`)
  return parts.length ? `共 ${total.value} 台设备，已按 ${parts.join('、')} 筛选` : `共 ${total.value} 台设备`
})

/** 新增对话框 */
const createVisible = ref(false)
const createLoading = ref(false)
const createForm = reactive({ name: '', device_type: 'pc', owner_id: '', node_id: null, remark: '' })
const members = ref([])
const bindableNodes = ref([])
const nodesLoading = ref(false)
const relationVisible = ref(false)
const relationSaving = ref(false)
const relationRow = ref(null)
const relationAccounts = ref([])
const relationNodes = ref([])
const relationForm = reactive({ account_ids: [], node_ids: [] })

async function openRelations(row) {
  relationRow.value = row
  relationForm.account_ids = (row.accounts || (row.account_id ? [{ id: row.account_id }] : [])).map((a) => a.id)
  relationForm.node_ids = row.node_ids || (row.node_id ? [row.node_id] : [])
  relationVisible.value = true
  const [accountsRes, nodesRes] = await Promise.all([
    listOpAccounts({ skip: 0, limit: 200 }),
    getProxyNodes({ skip: 0, limit: 500 })
  ])
  relationAccounts.value = accountsRes.items || []
  relationNodes.value = nodesRes.items || []
}

async function saveRelations() {
  relationSaving.value = true
  try {
    await updateDeviceRelations(relationRow.value.id, relationForm)
    ElMessage.success('关联已更新')
    relationVisible.value = false
    await loadDevices()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '关联保存失败')
  } finally { relationSaving.value = false }
}

// 请求序号守卫：快速筛选/翻页/搜索时丢弃过期响应
let listRequestSeq = 0
let nodesRequestSeq = 0

/** 加载设备列表 */
async function loadDevices() {
  const seq = ++listRequestSeq
  loading.value = true
  try {
    const params = { skip: (query.page - 1) * query.page_size, limit: query.page_size }
    if (query.keyword) params.keyword = query.keyword
    if (query.device_type) params.device_type = query.device_type
    if (isSuperAdmin.value && query.owner_id) params.owner_id = query.owner_id
    const res = await getDevices(params)
    if (seq !== listRequestSeq) return
    devices.value = res.items || []
    total.value = res.total || 0
  } catch {
    if (seq !== listRequestSeq) return
    // 失败清空旧结果，避免上一轮筛选/分页数据残留在新查询下
    devices.value = []
    total.value = 0
    ElMessage.error('加载设备列表失败')
  } finally {
    if (seq === listRequestSeq) {
      loading.value = false
    }
  }
}

function applyFilters() {
  query.page = 1
  loadDevices()
}

function resetFilters() {
  query.keyword = ''
  query.device_type = ''
  query.owner_id = ''
  applyFilters()
}

function handleSizeChange() {
  query.page = 1
  loadDevices()
}

/** 加载成员列表（仅超管筛选/分配使用） */
async function loadMembers() {
  try {
    const res = await getMembers({ page: 1, size: 500 })
    members.value = res.items || []
  } catch {
    members.value = []
  }
}

/** 可绑定节点远程搜索（序号守卫防乱序） */
async function searchNodes(q = '') {
  const seq = ++nodesRequestSeq
  nodesLoading.value = true
  try {
    const res = await getBindableNodes({ q })
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

/** 打开新增对话框 */
function showCreateDialog() {
  createForm.name = ''
  createForm.device_type = 'pc'
  createForm.owner_id = ''
  createForm.node_id = null
  createForm.remark = ''
  createVisible.value = true
  searchNodes('')
}

/** 确认创建设备 */
async function handleCreate() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请输入设备名称')
    return
  }
  createLoading.value = true
  try {
    const payload = {
      name: createForm.name.trim(),
      device_type: createForm.device_type,
      // clearable 清空可能赋值 undefined → 归一化为 null（不绑定）
      node_id: createForm.node_id === undefined ? null : createForm.node_id,
      remark: createForm.remark || null
    }
    if (isSuperAdmin.value) {
      if (!createForm.owner_id) {
        ElMessage.warning('请选择所属人')
        createLoading.value = false
        return
      }
      payload.owner_id = createForm.owner_id
    }
    await createDevice(payload)
    ElMessage.success('设备创建成功')
    createVisible.value = false
    loadDevices()
  } catch (err) {
    // 透出服务端业务错误（如 409 节点已被占用）
    ElMessage.error(err?.response?.data?.detail || '设备创建失败')
  } finally {
    createLoading.value = false
  }
}

function formatTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN') : '-'
}

onMounted(() => {
  loadDevices()
  if (isSuperAdmin.value) loadMembers()
})
</script>

<style scoped>
.page-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.page-subtitle {
  margin-top: 4px;
  color: #909399;
  font-size: 13px;
}

.filter-card {
  margin-bottom: 12px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.mobile-cards {
  display: none;
}

@media (max-width: 767px) {
  .page-toolbar {
    padding: 0 12px;
  }

  .page-title {
    display: none;
  }

  .page-subtitle {
    font-size: 12px;
  }

  .filter-card :deep(.el-card__body) {
    padding: 12px;
  }

  .filter-card :deep(.el-col) {
    margin-bottom: 8px;
  }

  .desktop-table {
    display: none;
  }

  .mobile-cards {
    display: block;
  }

  .device-card {
    background: var(--ios-card-bg, #fff);
    border-radius: 20px;
    box-shadow: var(--ios-shadow, 0 4px 16px rgba(0, 0, 0, 0.06));
    padding: 14px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: transform 0.15s;
    -webkit-tap-highlight-color: transparent;
  }

  .device-card:active {
    transform: scale(0.98);
  }

  .card-name {
    font-size: 15px;
    font-weight: 600;
  }

  .card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 12px;
    color: #909399;
    margin-top: 6px;
  }
}
</style>
