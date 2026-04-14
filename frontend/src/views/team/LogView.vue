<template>
  <div class="log-view">
    <el-card>
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <!-- 登录日志 -->
        <el-tab-pane label="登录日志" name="login">
          <el-form inline class="search-form">
            <el-form-item label="用户名">
              <el-input v-model="loginFilters.username" clearable placeholder="搜索用户名" />
            </el-form-item>
            <el-form-item label="时间范围">
              <el-date-picker
                v-model="loginFilters.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-form-item label="结果">
              <el-select v-model="loginFilters.result" clearable placeholder="全部" style="width:100px">
                <el-option label="成功" value="success" />
                <el-option label="失败" value="failed" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadLoginLogs">搜索</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="loginLogs" v-loading="loginLoading" stripe>
            <el-table-column prop="username" label="用户名" width="120" />
            <el-table-column prop="ip_address" label="IP地址" width="140" />
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.result === 'success' ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="失败原因" />
            <el-table-column prop="created_at" label="时间" width="180">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="loginPage"
            v-model:page-size="loginPageSize"
            :total="loginTotal"
            layout="total, prev, pager, next"
            class="pagination"
            @current-change="loadLoginLogs"
          />
        </el-tab-pane>

        <!-- 操作日志 -->
        <el-tab-pane label="操作日志" name="operation">
          <el-form inline class="search-form">
            <el-form-item label="操作人">
              <el-input v-model="opFilters.username" clearable placeholder="搜索操作人" />
            </el-form-item>
            <el-form-item label="时间范围">
              <el-date-picker
                v-model="opFilters.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-form-item label="模块">
              <el-input v-model="opFilters.module" clearable placeholder="模块名称" style="width:120px" />
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="opFilters.action" clearable placeholder="全部" style="width:110px">
                <el-option label="CREATE" value="CREATE" />
                <el-option label="UPDATE" value="UPDATE" />
                <el-option label="DELETE" value="DELETE" />
                <el-option label="EXPORT" value="EXPORT" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadOpLogs">搜索</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="opLogs" v-loading="opLoading" stripe>
            <el-table-column prop="username" label="操作人" width="120" />
            <el-table-column prop="module" label="模块" width="120" />
            <el-table-column prop="action" label="类型" width="90" />
            <el-table-column prop="summary" label="内容摘要" />
            <el-table-column prop="ip_address" label="IP地址" width="140" />
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.result === 'success' ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="180">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="opPage"
            v-model:page-size="opPageSize"
            :total="opTotal"
            layout="total, prev, pager, next"
            class="pagination"
            @current-change="loadOpLogs"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getLoginLogs, getOperationLogs } from '@/api/team'

const activeTab = ref('login')

// Login logs
const loginLogs = ref([])
const loginLoading = ref(false)
const loginTotal = ref(0)
const loginPage = ref(1)
const loginPageSize = ref(20)
const loginFilters = ref({ username: '', dateRange: null, result: '' })

// Operation logs
const opLogs = ref([])
const opLoading = ref(false)
const opTotal = ref(0)
const opPage = ref(1)
const opPageSize = ref(20)
const opFilters = ref({ username: '', dateRange: null, module: '', action: '' })

const formatTime = (t) => {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

const buildDateParams = (dateRange) => {
  if (!dateRange || !dateRange[0]) return {}
  return { start_date: dateRange[0], end_date: dateRange[1] }
}

const loadLoginLogs = async () => {
  loginLoading.value = true
  try {
    const params = { page: loginPage.value, size: loginPageSize.value }
    if (loginFilters.value.username) params.username = loginFilters.value.username
    if (loginFilters.value.result) params.result = loginFilters.value.result
    Object.assign(params, buildDateParams(loginFilters.value.dateRange))
    const data = await getLoginLogs(params)
    loginLogs.value = data.items
    loginTotal.value = data.total
  } catch {
    ElMessage.error('加载登录日志失败')
  } finally {
    loginLoading.value = false
  }
}

const loadOpLogs = async () => {
  opLoading.value = true
  try {
    const params = { page: opPage.value, size: opPageSize.value }
    if (opFilters.value.username) params.username = opFilters.value.username
    if (opFilters.value.module) params.module = opFilters.value.module
    if (opFilters.value.action) params.action = opFilters.value.action
    Object.assign(params, buildDateParams(opFilters.value.dateRange))
    const data = await getOperationLogs(params)
    opLogs.value = data.items
    opTotal.value = data.total
  } catch {
    ElMessage.error('加载操作日志失败')
  } finally {
    opLoading.value = false
  }
}

const handleTabChange = (tab) => {
  if (tab === 'login') loadLoginLogs()
  else loadOpLogs()
}

onMounted(loadLoginLogs)
</script>

<style scoped>
.search-form {
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
