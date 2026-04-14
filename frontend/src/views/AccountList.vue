<template>
  <div class="account-list">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>账号列表</span>
          <div class="header-actions">
            <el-button type="primary" @click="handleCreate">
              <el-icon><Plus /></el-icon>
              添加账号
            </el-button>
            <el-button @click="showBatchAddDialog">
              <el-icon><DocumentAdd /></el-icon>
              批量添加
            </el-button>
            <el-button @click="showImportDialog">
              <el-icon><Upload /></el-icon>
              导入
            </el-button>
            <el-button @click="handleExport">
              <el-icon><Download /></el-icon>
              导出
            </el-button>
          </div>
        </div>
      </template>

      <!-- Filters -->
      <div class="filters">
        <el-select v-model="filters.project_id" placeholder="选择项目" clearable @change="loadAccounts">
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="搜索用户名/昵称"
          clearable
          @clear="loadAccounts"
          @keyup.enter="loadAccounts"
          style="width: 250px"
        >
          <template #append>
            <el-button :icon="Search" @click="loadAccounts" />
          </template>
        </el-input>
        <el-select v-model="filters.is_active" placeholder="状态" clearable @change="loadAccounts">
          <el-option label="已激活" :value="true" />
          <el-option label="已禁用" :value="false" />
        </el-select>
      </div>

      <!-- Batch Actions Toolbar -->
      <div class="batch-toolbar" v-if="selectedIds.length > 0">
        <span>已选择 {{ selectedIds.length }} 项</span>
        <el-button size="small" @click="batchCheck">批量检查</el-button>
        <el-button size="small" @click="batchEnable">批量启用</el-button>
        <el-button size="small" @click="batchDisable">批量禁用</el-button>
        <el-button size="small" @click="showBatchMoveDialog">批量移动</el-button>
        <el-button size="small" type="danger" @click="batchDelete">批量删除</el-button>
      </div>

      <!-- Table -->
      <el-table
        :data="accounts"
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        
        <el-table-column label="账号信息" min-width="300">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 12px;">
              <el-avatar :src="row.avatar_url" :size="50" v-if="row.avatar_url">
                <template #error>
                  <el-icon><User /></el-icon>
                </template>
              </el-avatar>
              <el-avatar :size="50" v-else>
                <el-icon><User /></el-icon>
              </el-avatar>
              <div style="flex: 1; min-width: 0;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                  <span style="font-weight: 500; font-size: 14px;">@{{ row.username }}</span>
                  <span v-if="row.nickname" style="color: #606266; font-size: 13px;">{{ row.nickname }}</span>
                </div>
                <div style="font-size: 12px; color: #909399; margin-bottom: 2px;">
                  <span v-if="row.tiktok_id">ID: {{ row.tiktok_id }}</span>
                  <span v-if="row.tiktok_id && row.sec_uid"> | </span>
                  <span v-if="row.sec_uid">UID: {{ row.sec_uid.substring(0, 20) }}...</span>
                </div>
                <div v-if="row.bio" style="font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                  <el-tooltip :content="row.bio" placement="top" v-if="row.bio.length > 40">
                    <span>{{ row.bio.substring(0, 40) }}...</span>
                  </el-tooltip>
                  <span v-else>{{ row.bio }}</span>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="project_name" label="所属项目" width="120" />
        
        <el-table-column label="粉丝数" min-width="200">
          <template #default="{ row }">
            <div class="stat-with-chart">
              <div class="stat-info">
                <span class="stat-value">{{ formatNumber(row.follower_count) }}</span>
              </div>
              <div :ref="el => setChartRef('follower_count_' + row.id, el)" class="mini-chart"></div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column label="关注数" min-width="200">
          <template #default="{ row }">
            <div class="stat-with-chart">
              <div class="stat-info">
                <span class="stat-value">{{ formatNumber(row.following_count) }}</span>
              </div>
              <div :ref="el => setChartRef('following_count_' + row.id, el)" class="mini-chart"></div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column label="点赞数" min-width="200">
          <template #default="{ row }">
            <div class="stat-with-chart">
              <div class="stat-info">
                <span class="stat-value">{{ formatNumber(row.like_count) }}</span>
              </div>
              <div :ref="el => setChartRef('like_count_' + row.id, el)" class="mini-chart"></div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column label="视频数" min-width="160">
          <template #default="{ row }">
            <div class="stat-with-chart">
              <div class="stat-info">
                <span class="stat-value">{{ row.video_count || 0 }}</span>
              </div>
              <div :ref="el => setChartRef('video_count_' + row.id, el)" class="mini-chart-small"></div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column label="国家/地区" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.region">{{ row.region }}</span>
            <span v-else style="color: #909399;">-</span>
          </template>
        </el-table-column>
        
        <el-table-column label="注册时间" width="110" align="center">
          <template #default="{ row }">
            <span v-if="row.account_created_at" style="font-size: 12px;">
              {{ formatShortDate(row.account_created_at) }}
            </span>
            <span v-else style="color: #909399;">-</span>
          </template>
        </el-table-column>
        
        <el-table-column label="代理" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.use_proxy" type="success" size="small">启用</el-tag>
            <el-tag v-else type="info" size="small">关闭</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="视频监控" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.enable_video_monitoring" type="success" size="small">启用</el-tag>
            <el-tag v-else type="info" size="small">关闭</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '激活' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="last_checked_at" label="最后检查" width="180">
          <template #default="{ row }">
            {{ formatDate(row.last_checked_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row)">详情</el-button>
            <el-button link type="primary" @click="handleCheck(row)">立即检查</el-button>
            <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.limit"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadAccounts"
          @size-change="loadAccounts"
        />
      </div>
    </el-card>

    <!-- Batch Add Dialog -->
    <BatchAddDialog
      v-model="batchAddVisible"
      :projects="projects"
      @success="loadAccounts"
    />

    <!-- Import Dialog -->
    <ImportDialog
      v-model="importVisible"
      :projects="projects"
      @success="loadAccounts"
    />

    <!-- Export Dialog -->
    <ExportDialog
      v-model="exportVisible"
      :projects="projects"
      :current-project-id="filters.project_id"
    />

    <!-- Batch Move Dialog -->
    <el-dialog v-model="batchMoveVisible" title="批量移动" width="400px">
      <el-form>
        <el-form-item label="目标项目">
          <el-select v-model="targetProjectId" placeholder="选择目标项目">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchMoveVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmBatchMove">确定</el-button>
      </template>
    </el-dialog>

    <!-- Account Dialog -->
    <AccountDialog
      v-model="accountDialogVisible"
      :projects="projects"
      :account="editingAccount"
      @success="loadAccounts"
    />
    
    <!-- 批量检查进度对话框 -->
    <el-dialog
      v-model="progressDialog.visible"
      title="批量检查进度"
      width="500px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="progressDialog.completed"
    >
      <div class="progress-content">
        <el-progress
          :percentage="progressDialog.percentage"
          :status="progressDialog.status"
          :stroke-width="20"
        />
        <div class="progress-info">
          <p>总数: {{ progressDialog.total }}</p>
          <p>成功: <span style="color: #67C23A">{{ progressDialog.success }}</span></p>
          <p>失败: <span style="color: #F56C6C">{{ progressDialog.failed }}</span></p>
          <p>进行中: <span style="color: #409EFF">{{ progressDialog.processing }}</span></p>
        </div>
        <div v-if="progressDialog.currentAccount" class="current-account">
          <el-text type="info">正在检查: {{ progressDialog.currentAccount }}</el-text>
        </div>
      </div>
      <template #footer v-if="progressDialog.completed">
        <el-button type="primary" @click="progressDialog.visible = false">
          关闭
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, DocumentAdd, Upload, Download, Search, User } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getAccounts, deleteAccount, triggerCheck, batchAction } from '@/api/accounts'
import { getProjects } from '@/api/projects'
import { getAccountTrend } from '@/api/history'
import BatchAddDialog from '@/components/BatchAddDialog.vue'
import ImportDialog from '@/components/ImportDialog.vue'
import ExportDialog from '@/components/ExportDialog.vue'
import AccountDialog from '@/components/AccountDialog.vue'

const router = useRouter()
const route = useRoute()

const accounts = ref([])
const projects = ref([])
const loading = ref(false)
const selectedIds = ref([])

// 批量检查进度对话框
const progressDialog = ref({
  visible: false,
  total: 0,
  success: 0,
  failed: 0,
  processing: 0,
  percentage: 0,
  status: '',
  completed: false,
  currentAccount: ''
})

const filters = ref({
  project_id: null,
  keyword: '',
  is_active: null
})

const pagination = ref({
  page: 1,
  limit: 50,
  total: 0
})

const batchAddVisible = ref(false)
const importVisible = ref(false)
const exportVisible = ref(false)
const batchMoveVisible = ref(false)
const targetProjectId = ref(null)
const accountDialogVisible = ref(false)
const editingAccount = ref(null)

// Chart refs and instances
const chartRefs = ref({})
const chartInstances = ref({})

const formatNumber = (num) => {
  if (num == null) return '-'
  return num.toLocaleString()
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  // 后端返回 UTC 时间，加 Z 后缀让浏览器正确转换为本地时间
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleString('zh-CN')
}

const formatShortDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  const date = new Date(s)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

const loadProjects = async () => {
  try {
    projects.value = await getProjects()
  } catch (error) {
    console.error('Failed to load projects:', error)
  }
}

const loadAccounts = async (renderCharts = true) => {
  loading.value = true
  try {
    const params = {
      skip: (pagination.value.page - 1) * pagination.value.limit,
      limit: pagination.value.limit
    }
    
    if (filters.value.project_id) params.project_id = filters.value.project_id
    if (filters.value.keyword) params.keyword = filters.value.keyword
    if (filters.value.is_active !== null) params.is_active = filters.value.is_active

    const data = await getAccounts(params)
    accounts.value = data.items || data
    pagination.value.total = data.total ?? data.length
    
    // Render charts only when explicitly requested (not during polling)
    if (renderCharts) {
      await nextTick()
      renderAllCharts()
    }
  } catch (error) {
    console.error('Failed to load accounts:', error)
  } finally {
    loading.value = false
  }
}

const handleSelectionChange = (selection) => {
  selectedIds.value = selection.map(item => item.id)
}

const handleCreate = () => {
  editingAccount.value = null
  accountDialogVisible.value = true
}

const handleEdit = (row) => {
  editingAccount.value = row
  accountDialogVisible.value = true
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除账号"${row.username}"吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await deleteAccount(row.id)
    ElMessage.success('账号删除成功')
    loadAccounts()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to delete account:', error)
    }
  }
}

const handleCheck = async (row) => {
  try {
    await triggerCheck(row.id)
    ElMessage.success('检查任务已触发')
    setTimeout(() => loadAccounts(false), 2000) // 不重新渲染图表
  } catch (error) {
    console.error('Failed to trigger check:', error)
  }
}

const viewDetail = (row) => {
  router.push(`/accounts/${row.id}`)
}

const showBatchAddDialog = () => {
  batchAddVisible.value = true
}

const showImportDialog = () => {
  importVisible.value = true
}

const handleExport = () => {
  exportVisible.value = true
}

const batchEnable = async () => {
  try {
    await batchAction({
      action: 'enable',
      account_ids: selectedIds.value
    })
    ElMessage.success('批量启用成功')
    loadAccounts()
  } catch (error) {
    console.error('Failed to batch enable:', error)
  }
}

const batchCheck = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要立即检查选中的 ${selectedIds.value.length} 个账号吗？`,
      '批量检查',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info'
      }
    )
    
    // 初始化进度对话框
    progressDialog.value = {
      visible: true,
      total: selectedIds.value.length,
      success: 0,
      failed: 0,
      processing: 0,
      percentage: 0,
      status: '',
      completed: false,
      currentAccount: ''
    }
    
    // 获取账号名称映射
    const accountMap = {}
    accounts.value.forEach(acc => {
      accountMap[acc.id] = acc.username
    })
    
    // 带重试的检查函数
    const triggerCheckWithRetry = async (accountId, maxRetries = 3) => {
      progressDialog.value.processing++
      progressDialog.value.currentAccount = accountMap[accountId] || `账号${accountId}`
      
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
          await triggerCheck(accountId)
          progressDialog.value.processing--
          progressDialog.value.success++
          progressDialog.value.percentage = Math.round(
            ((progressDialog.value.success + progressDialog.value.failed) / progressDialog.value.total) * 100
          )
          return { success: true, accountId }
        } catch (error) {
          console.warn(`检查账号 ${accountId} 失败 (尝试 ${attempt}/${maxRetries}):`, error.message)
          
          // 如果不是最后一次尝试，等待后重试
          if (attempt < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, 2000 * attempt)) // 递增延迟
          } else {
            console.error(`账号 ${accountId} 检查失败，已重试 ${maxRetries} 次`)
            progressDialog.value.processing--
            progressDialog.value.failed++
            progressDialog.value.percentage = Math.round(
              ((progressDialog.value.success + progressDialog.value.failed) / progressDialog.value.total) * 100
            )
            return { success: false, accountId, error: error.message }
          }
        }
      }
    }
    
    // 分批触发检查（每批10个，避免同时发送太多请求）
    const batchSize = 10
    const results = []
    
    for (let i = 0; i < selectedIds.value.length; i += batchSize) {
      const batch = selectedIds.value.slice(i, i + batchSize)
      const batchPromises = batch.map(accountId => triggerCheckWithRetry(accountId))
      const batchResults = await Promise.all(batchPromises)
      results.push(...batchResults)
      
      // 批次之间稍微延迟，避免压垮后端
      if (i + batchSize < selectedIds.value.length) {
        await new Promise(resolve => setTimeout(resolve, 500))
      }
    }
    
    // 统计结果
    const successCount = results.filter(r => r.success).length
    const failCount = results.filter(r => !r.success).length
    
    // 标记完成
    progressDialog.value.completed = true
    progressDialog.value.currentAccount = ''
    progressDialog.value.status = failCount > 0 ? 'warning' : 'success'
    
    if (failCount > 0) {
      ElMessage.warning(`已触发 ${successCount} 个账号检查，${failCount} 个失败`)
    } else {
      ElMessage.success(`已触发 ${successCount} 个账号的检查，数据将自动更新`)
    }
    
    // 启动轮询，每2秒刷新一次数据，持续30秒
    // 注意：轮询时不重新渲染图表，避免大量API请求
    let pollCount = 0
    const maxPolls = 15 // 30秒
    const pollInterval = setInterval(() => {
      pollCount++
      loadAccounts(false) // false = 不渲染图表
      
      if (pollCount >= maxPolls) {
        clearInterval(pollInterval)
      }
    }, 2000)
    
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to batch check:', error)
    }
  }
}

const batchDisable = async () => {
  try {
    await batchAction({
      action: 'disable',
      account_ids: selectedIds.value
    })
    ElMessage.success('批量禁用成功')
    loadAccounts()
  } catch (error) {
    console.error('Failed to batch disable:', error)
  }
}

const batchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedIds.value.length} 个账号吗？`,
      '批量删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await batchAction({
      action: 'delete',
      account_ids: selectedIds.value
    })
    ElMessage.success('批量删除成功')
    loadAccounts()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to batch delete:', error)
    }
  }
}

const showBatchMoveDialog = () => {
  targetProjectId.value = null
  batchMoveVisible.value = true
}

const confirmBatchMove = async () => {
  if (!targetProjectId.value) {
    ElMessage.warning('请选择目标项目')
    return
  }

  try {
    await batchAction({
      action: 'move',
      account_ids: selectedIds.value,
      target_project_id: targetProjectId.value
    })
    ElMessage.success('批量移动成功')
    batchMoveVisible.value = false
    loadAccounts()
  } catch (error) {
    console.error('Failed to batch move:', error)
  }
}

// Chart functions
const setChartRef = (id, el) => {
  if (el) {
    chartRefs.value[id] = el
  }
}

const renderAllCharts = async () => {
  for (const account of accounts.value) {
    await renderMiniChart(account, 'follower_count')
    await renderMiniChart(account, 'following_count')
    await renderMiniChart(account, 'like_count')
    await renderMiniChart(account, 'video_count')
  }
}

const renderMiniChart = async (account, metric) => {
  const chartKey = `${metric}_${account.id}`
  const chartEl = chartRefs.value[chartKey]
  if (!chartEl) return
  
  try {
    // Get 7-day trend data
    const data = await getAccountTrend(account.id)
    
    if (!data.data_points || data.data_points.length === 0) {
      return
    }
    
    // Dispose old chart
    if (chartInstances.value[chartKey]) {
      chartInstances.value[chartKey].dispose()
    }
    
    // Create new chart
    const chart = echarts.init(chartEl)
    chartInstances.value[chartKey] = chart
    
    // Set colors based on metric
    const colors = {
      follower_count: { line: '#409EFF', area1: 'rgba(64, 158, 255, 0.3)', area2: 'rgba(64, 158, 255, 0.05)' },
      following_count: { line: '#E6A23C', area1: 'rgba(230, 162, 60, 0.3)', area2: 'rgba(230, 162, 60, 0.05)' },
      like_count: { line: '#F56C6C', area1: 'rgba(245, 108, 108, 0.3)', area2: 'rgba(245, 108, 108, 0.05)' },
      video_count: { line: '#67C23A', area1: 'rgba(103, 194, 58, 0.3)', area2: 'rgba(103, 194, 58, 0.05)' }
    }
    
    const color = colors[metric]
    
    const option = {
      grid: {
        left: 5,
        right: 5,
        top: 5,
        bottom: 5
      },
      xAxis: {
        type: 'category',
        show: false,
        data: data.data_points.map(p => p.checked_at)
      },
      yAxis: {
        type: 'value',
        show: false
      },
      series: [
        {
          type: 'line',
          data: data.data_points.map(p => p[metric]),
          smooth: true,
          symbol: 'none',
          lineStyle: {
            width: 2,
            color: color.line
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: color.area1 },
                { offset: 1, color: color.area2 }
              ]
            }
          }
        }
      ]
    }
    
    chart.setOption(option)
  } catch (error) {
    console.error(`Failed to render ${metric} chart:`, error)
  }
}

onMounted(() => {
  // Load project_id from query if present
  if (route.query.project_id) {
    filters.value.project_id = parseInt(route.query.project_id)
  }
  
  loadProjects()
  loadAccounts()
})
</script>

<style scoped>
.account-list {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background-color: #f0f2f5;
  border-radius: 4px;
  margin-bottom: 10px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.stat-with-chart {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-value {
  font-size: 14px;
  font-weight: 500;
}

.mini-chart {
  width: 170px;
  height: 40px;
}

.mini-chart-small {
  width: 130px;
  height: 35px;
}

.progress-content {
  padding: 20px 0;
}

.progress-info {
  margin-top: 20px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.progress-info p {
  margin: 0;
  font-size: 14px;
  color: #606266;
}

.current-account {
  margin-top: 15px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
  text-align: center;
}
</style>
