<template>
  <div class="monitor-manage">
    <el-tabs v-model="activeTab" type="border-card" @tab-change="onTabChange">
      <!-- 项目管理 -->
      <el-tab-pane label="项目管理" name="projects">
        <el-card shadow="never" :body-style="{ padding: '0' }">
          <template #header>
            <div class="card-header">
              <span>项目管理</span>
              <el-button type="primary" @click="handleCreateProject">
                <el-icon><Plus /></el-icon>
                新建项目
              </el-button>
            </div>
          </template>
          <el-table :data="projects" v-loading="projectLoading">
            <el-table-column prop="name" label="项目名称" />
            <el-table-column prop="description" label="描述" />
            <el-table-column prop="created_by" label="创建人" width="120">
              <template #default="{ row }">{{ row.created_by || '-' }}</template>
            </el-table-column>
            <el-table-column prop="account_count" label="账号数量" width="120" />
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="300" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="handleEditProject(row)">编辑</el-button>
                <el-button link type="primary" @click="viewProjectAccounts(row)">查看账号</el-button>
                <el-button link type="warning" @click="handleProjectMembers(row)">协作成员</el-button>
                <el-button link type="danger" @click="handleDeleteProject(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 账号列表 -->
      <el-tab-pane label="账号列表" name="accounts">
        <el-card shadow="never" :body-style="{ padding: '0' }">
          <template #header>
            <div class="card-header">
              <span>账号列表</span>
              <div class="header-actions">
                <el-button type="primary" @click="handleCreateAccount">
                  <el-icon><Plus /></el-icon>添加账号
                </el-button>
                <el-button @click="showBatchAddDialog">
                  <el-icon><DocumentAdd /></el-icon>批量添加
                </el-button>
                <el-button @click="showImportDialog">
                  <el-icon><Upload /></el-icon>导入
                </el-button>
                <el-button @click="handleExport">
                  <el-icon><Download /></el-icon>导出
                </el-button>
              </div>
            </div>
          </template>

          <div class="filters">
            <el-select v-model="accountFilters.project_id" placeholder="选择项目" clearable @change="loadAccounts">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-input
              v-model="accountFilters.keyword"
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
            <el-select v-model="accountFilters.is_active" placeholder="状态" clearable @change="loadAccounts">
              <el-option label="已激活" :value="true" />
              <el-option label="已禁用" :value="false" />
            </el-select>
          </div>

          <div class="batch-toolbar" v-if="selectedIds.length > 0">
            <span>已选择 {{ selectedIds.length }} 项</span>
            <el-button size="small" @click="batchCheck">批量检查</el-button>
            <el-button size="small" @click="batchEnable">批量启用</el-button>
            <el-button size="small" @click="batchDisable">批量禁用</el-button>
            <el-button size="small" @click="showBatchMoveDialog">批量移动</el-button>
            <el-button size="small" type="danger" @click="batchDelete">批量删除</el-button>
          </div>

          <el-table :data="accounts" v-loading="accountLoading" @selection-change="handleSelectionChange">
            <el-table-column type="selection" width="55" />
            <el-table-column label="账号信息" min-width="300">
              <template #default="{ row }">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <el-avatar :src="row.avatar_url" :size="50" v-if="row.avatar_url">
                    <template #error><el-icon><User /></el-icon></template>
                  </el-avatar>
                  <el-avatar :size="50" v-else><el-icon><User /></el-icon></el-avatar>
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
                  <span class="stat-value">{{ formatNumber(row.follower_count) }}</span>
                  <div :ref="el => setChartRef('follower_count_' + row.id, el)" class="mini-chart"></div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="关注数" min-width="200">
              <template #default="{ row }">
                <div class="stat-with-chart">
                  <span class="stat-value">{{ formatNumber(row.following_count) }}</span>
                  <div :ref="el => setChartRef('following_count_' + row.id, el)" class="mini-chart"></div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="点赞数" min-width="200">
              <template #default="{ row }">
                <div class="stat-with-chart">
                  <span class="stat-value">{{ formatNumber(row.like_count) }}</span>
                  <div :ref="el => setChartRef('like_count_' + row.id, el)" class="mini-chart"></div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="视频数" min-width="160">
              <template #default="{ row }">
                <div class="stat-with-chart">
                  <span class="stat-value">{{ row.video_count || 0 }}</span>
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
                <span v-if="row.account_created_at" style="font-size: 12px;">{{ formatShortDate(row.account_created_at) }}</span>
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
                <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '激活' : '禁用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_checked_at" label="最后检查" width="180">
              <template #default="{ row }">{{ formatDate(row.last_checked_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="250" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="viewAccountDetail(row)">详情</el-button>
                <el-button link type="primary" @click="handleCheckAccount(row)">立即检查</el-button>
                <el-button link type="primary" @click="handleEditAccount(row)">编辑</el-button>
                <el-button link type="danger" @click="handleDeleteAccount(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="accountPagination.page"
              v-model:page-size="accountPagination.limit"
              :total="accountPagination.total"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="loadAccounts"
              @size-change="loadAccounts"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- 代理管理 -->
      <el-tab-pane v-if="authStore.hasPermission('monitor:proxy')" label="代理管理" name="proxies">
        <el-card shadow="never" :body-style="{ padding: '0' }">
          <template #header>
            <div class="card-header">
              <span>代理管理</span>
              <div class="header-actions">
                <template v-if="selectedProxies.length > 0">
                  <el-button type="success" @click="handleBatchEnableProxy">
                    <el-icon><Check /></el-icon>批量启用 ({{ selectedProxies.length }})
                  </el-button>
                  <el-button type="warning" @click="handleBatchDisableProxy">
                    <el-icon><Close /></el-icon>批量禁用 ({{ selectedProxies.length }})
                  </el-button>
                  <el-button type="danger" @click="handleBatchDeleteProxy">
                    <el-icon><Delete /></el-icon>批量删除 ({{ selectedProxies.length }})
                  </el-button>
                </template>
                <el-button type="success" @click="handleBatchCreateProxy">
                  <el-icon><Upload /></el-icon>批量导入
                </el-button>
                <el-button type="primary" @click="handleCreateProxy">
                  <el-icon><Plus /></el-icon>添加代理
                </el-button>
              </div>
            </div>
          </template>

          <el-table :data="proxies" v-loading="proxyLoading" @selection-change="handleProxySelectionChange">
            <el-table-column type="selection" width="55" />
            <el-table-column prop="proxy_type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.proxy_type?.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="host" label="IP" width="150" />
            <el-table-column prop="port" label="端口" width="100" />
            <el-table-column prop="username" label="用户名" width="120">
              <template #default="{ row }">{{ row.username || '-' }}</template>
            </el-table-column>
            <el-table-column label="密码" width="150">
              <template #default="{ row }">
                <div v-if="row.password" style="display: flex; align-items: center; gap: 8px;">
                  <span>{{ visiblePasswords[row.id] ? row.password : '******' }}</span>
                  <el-icon style="cursor: pointer; color: #409eff;" @click="togglePasswordVisibility(row.id)">
                    <View v-if="!visiblePasswords[row.id]" /><Hide v-else />
                  </el-icon>
                </div>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_test_result" label="测试结果" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.last_test_result" :type="row.last_test_result === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.last_test_result === 'success' ? '成功' : '失败' }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="last_test_at" label="最后测试" width="180">
              <template #default="{ row }">{{ formatDate(row.last_test_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="handleTestProxy(row)" :loading="testingIds.includes(row.id)">测试</el-button>
                <el-button link type="primary" @click="handleEditProxy(row)">编辑</el-button>
                <el-button link type="danger" @click="handleDeleteProxy(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- ===== 项目弹窗 ===== -->
    <el-dialog v-model="projectDialogVisible" :title="projectDialogTitle" width="500px">
      <el-form :model="projectForm" :rules="projectRules" ref="projectFormRef" label-width="80px">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="projectForm.name" placeholder="请输入项目名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="projectForm.description" type="textarea" :rows="3" placeholder="请输入项目描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitProject" :loading="projectSubmitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- ===== 协作成员弹窗 ===== -->
    <el-dialog v-model="membersDialogVisible" title="协作成员管理" width="480px" append-to-body>
      <div style="font-size: 13px; color: #909399; margin-bottom: 12px;">
        被添加的成员可查看该项目及其下的监控账号。
      </div>
      <el-select
        v-model="memberUsernames"
        multiple
        filterable
        allow-create
        collapse-tags
        collapse-tags-tooltip
        placeholder="输入或选择用户名"
        style="width: 100%"
        popper-append-to-body
      >
        <el-option
          v-for="u in allTeamMembers"
          :key="u.username"
          :label="u.real_name ? `${u.real_name} (${u.username})` : u.username"
          :value="u.username"
        />
      </el-select>
      <div v-if="memberUsernames.length" style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px;">
        <el-tag
          v-for="name in memberUsernames"
          :key="name"
          closable
          @close="memberUsernames = memberUsernames.filter(n => n !== name)"
        >{{ name }}</el-tag>
      </div>
      <template #footer>
        <el-button @click="membersDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMembersSubmit" :loading="membersSubmitting">保存</el-button>
      </template>
    </el-dialog>

    <!-- ===== 账号相关弹窗 ===== -->
    <BatchAddDialog v-model="batchAddVisible" :projects="projects" @success="loadAccounts" />
    <ImportDialog v-model="importVisible" :projects="projects" @success="loadAccounts" />
    <ExportDialog v-model="exportVisible" :projects="projects" :current-project-id="accountFilters.project_id" />
    <AccountDialog v-model="accountDialogVisible" :projects="projects" :account="editingAccount" @success="loadAccounts" />

    <el-dialog v-model="batchMoveVisible" title="批量移动" width="400px">
      <el-form>
        <el-form-item label="目标项目">
          <el-select v-model="targetProjectId" placeholder="选择目标项目">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchMoveVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmBatchMove">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="progressDialog.visible" title="批量检查进度" width="500px"
      :close-on-click-modal="false" :close-on-press-escape="false" :show-close="progressDialog.completed">
      <div class="progress-content">
        <el-progress :percentage="progressDialog.percentage" :status="progressDialog.status" :stroke-width="20" />
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
        <el-button type="primary" @click="progressDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- ===== 代理弹窗 ===== -->
    <el-dialog v-model="proxyDialogVisible" :title="proxyDialogTitle" width="500px">
      <el-form :model="proxyForm" :rules="proxyRules" ref="proxyFormRef" label-width="100px">
        <el-form-item label="代理类型" prop="proxy_type">
          <el-select v-model="proxyForm.proxy_type" placeholder="选择代理类型">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>
        <el-form-item label="IP地址" prop="host">
          <el-input v-model="proxyForm.host" placeholder="例如: 127.0.0.1" />
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input-number v-model="proxyForm.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="proxyForm.username" placeholder="可选" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="proxyForm.password" type="password" placeholder="可选" show-password />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="proxyForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="proxyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitProxy" :loading="proxySubmitting">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchProxyDialogVisible" title="批量导入代理" width="600px">
      <el-alert title="格式说明" type="info" :closable="false" style="margin-bottom: 15px">
        <p>每行一个代理，支持以下格式：</p>
        <ul style="margin: 5px 0; padding-left: 20px;">
          <li><code>ip:port</code></li>
          <li><code>ip:port:username:password</code></li>
        </ul>
      </el-alert>
      <el-form :model="batchProxyForm" label-width="100px">
        <el-form-item label="代理类型">
          <el-select v-model="batchProxyForm.proxy_type">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>
        <el-form-item label="代理列表">
          <el-input v-model="batchProxyForm.proxies_text" type="textarea" :rows="10"
            placeholder="请输入代理列表，每行一个&#10;例如：&#10;192.168.1.1:8080:user1:pass1" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="batchProxyForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchProxyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBatchSubmitProxy" :loading="batchProxySubmitting">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, DocumentAdd, Upload, Download, Search, User, View, Hide, Delete, Check, Close } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getProjects, createProject, updateProject, deleteProject, getProjectMembers, setProjectMembers } from '@/api/projects'
import { getAccounts, deleteAccount, triggerCheck, batchAction } from '@/api/accounts'
import { getAccountTrend } from '@/api/history'
import { getProxies, createProxy, updateProxy, deleteProxy, testProxy, batchCreateProxies } from '@/api/proxies'
import { getMembers } from '@/api/team'
import { useAuthStore } from '@/stores/auth'
import BatchAddDialog from '@/components/BatchAddDialog.vue'
import ImportDialog from '@/components/ImportDialog.vue'
import ExportDialog from '@/components/ExportDialog.vue'
import AccountDialog from '@/components/AccountDialog.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeTab = ref('projects')

// ===== 工具函数 =====
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleString('zh-CN')
}
const formatShortDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
const formatNumber = (num) => {
  if (num == null) return '-'
  return num.toLocaleString()
}

// ===== 项目管理 =====
const projects = ref([])
const projectLoading = ref(false)
const projectDialogVisible = ref(false)
const projectSubmitting = ref(false)
const projectFormRef = ref(null)
const editingProjectId = ref(null)
const projectForm = ref({ name: '', description: '' })
const projectRules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { max: 100, message: '项目名称不能超过100个字符', trigger: 'blur' }
  ]
}
const projectDialogTitle = computed(() => editingProjectId.value ? '编辑项目' : '新建项目')

const loadProjects = async () => {
  projectLoading.value = true
  try {
    projects.value = await getProjects()
  } catch (e) {
    console.error(e)
  } finally {
    projectLoading.value = false
  }
}

const handleCreateProject = () => {
  editingProjectId.value = null
  projectForm.value = { name: '', description: '' }
  projectDialogVisible.value = true
}
const handleEditProject = (row) => {
  editingProjectId.value = row.id
  projectForm.value = { name: row.name, description: row.description || '' }
  projectDialogVisible.value = true
}
const handleSubmitProject = async () => {
  const valid = await projectFormRef.value.validate().catch(() => false)
  if (!valid) return
  projectSubmitting.value = true
  try {
    if (editingProjectId.value) {
      await updateProject(editingProjectId.value, projectForm.value)
      ElMessage.success('项目更新成功')
    } else {
      await createProject(projectForm.value)
      ElMessage.success('项目创建成功')
    }
    projectDialogVisible.value = false
    loadProjects()
  } finally {
    projectSubmitting.value = false
  }
}
const handleDeleteProject = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除项目"${row.name}"吗？`, '删除确认', { type: 'warning' })
    await deleteProject(row.id)
    ElMessage.success('项目删除成功')
    loadProjects()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}
const viewProjectAccounts = (row) => {
  accountFilters.value.project_id = row.id
  activeTab.value = 'accounts'
  loadAccounts()
}

// ===== 协作成员 =====
const membersDialogVisible = ref(false)
const membersSubmitting = ref(false)
const memberUsernames = ref([])
const allTeamMembers = ref([])
const currentMembersProjectId = ref(null)

const handleProjectMembers = async (row) => {
  currentMembersProjectId.value = row.id
  memberUsernames.value = await getProjectMembers(row.id).catch(() => [])
  if (authStore.hasPermission('team:member:view')) {
    const data = await getMembers({ size: 200 }).catch(() => ({ items: [] }))
    allTeamMembers.value = (data.items || []).filter(u => u.username !== row.created_by)
  } else {
    allTeamMembers.value = []
  }
  membersDialogVisible.value = true
}

const handleMembersSubmit = async () => {
  membersSubmitting.value = true
  try {
    await setProjectMembers(currentMembersProjectId.value, memberUsernames.value)
    ElMessage.success('协作成员已保存')
    membersDialogVisible.value = false
  } finally {
    membersSubmitting.value = false
  }
}

// ===== 账号列表 =====
const accounts = ref([])
const accountLoading = ref(false)
const selectedIds = ref([])
const accountFilters = ref({ project_id: null, keyword: '', is_active: null })
const accountPagination = ref({ page: 1, limit: 50, total: 0 })
const batchAddVisible = ref(false)
const importVisible = ref(false)
const exportVisible = ref(false)
const batchMoveVisible = ref(false)
const targetProjectId = ref(null)
const accountDialogVisible = ref(false)
const editingAccount = ref(null)
const progressDialog = ref({
  visible: false, total: 0, success: 0, failed: 0, processing: 0,
  percentage: 0, status: '', completed: false, currentAccount: ''
})

const loadAccounts = async (renderCharts = true) => {
  accountLoading.value = true
  try {
    const params = {
      skip: (accountPagination.value.page - 1) * accountPagination.value.limit,
      limit: accountPagination.value.limit
    }
    if (accountFilters.value.project_id) params.project_id = accountFilters.value.project_id
    if (accountFilters.value.keyword) params.keyword = accountFilters.value.keyword
    if (accountFilters.value.is_active !== null) params.is_active = accountFilters.value.is_active
    const data = await getAccounts(params)
    accounts.value = data.items || data
    accountPagination.value.total = data.total ?? data.length
    if (renderCharts) {
      await nextTick()
      renderAllCharts()
    }
  } catch (e) {
    console.error(e)
  } finally {
    accountLoading.value = false
  }
}

const handleSelectionChange = (sel) => { selectedIds.value = sel.map(i => i.id) }
const handleCreateAccount = () => { editingAccount.value = null; accountDialogVisible.value = true }
const handleEditAccount = (row) => { editingAccount.value = row; accountDialogVisible.value = true }
const viewAccountDetail = (row) => router.push(`/accounts/${row.id}`)
const showBatchAddDialog = () => { batchAddVisible.value = true }
const showImportDialog = () => { importVisible.value = true }
const handleExport = () => { exportVisible.value = true }
const showBatchMoveDialog = () => { targetProjectId.value = null; batchMoveVisible.value = true }

const handleDeleteAccount = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除账号"${row.username}"吗？`, '删除确认', { type: 'warning' })
    await deleteAccount(row.id)
    ElMessage.success('账号删除成功')
    loadAccounts()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}
const handleCheckAccount = async (row) => {
  try {
    await triggerCheck(row.id)
    ElMessage.success('检查任务已触发')
    setTimeout(() => loadAccounts(false), 2000)
  } catch (e) { console.error(e) }
}
const batchEnable = async () => {
  try {
    await batchAction({ action: 'enable', account_ids: selectedIds.value })
    ElMessage.success('批量启用成功')
    loadAccounts()
  } catch (e) { console.error(e) }
}
const batchDisable = async () => {
  try {
    await batchAction({ action: 'disable', account_ids: selectedIds.value })
    ElMessage.success('批量禁用成功')
    loadAccounts()
  } catch (e) { console.error(e) }
}
const batchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedIds.value.length} 个账号吗？`, '批量删除确认', { type: 'warning' })
    await batchAction({ action: 'delete', account_ids: selectedIds.value })
    ElMessage.success('批量删除成功')
    loadAccounts()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}
const confirmBatchMove = async () => {
  if (!targetProjectId.value) { ElMessage.warning('请选择目标项目'); return }
  try {
    await batchAction({ action: 'move', account_ids: selectedIds.value, target_project_id: targetProjectId.value })
    ElMessage.success('批量移动成功')
    batchMoveVisible.value = false
    loadAccounts()
  } catch (e) { console.error(e) }
}
const batchCheck = async () => {
  try {
    await ElMessageBox.confirm(`确定要立即检查选中的 ${selectedIds.value.length} 个账号吗？`, '批量检查', { type: 'info' })
    progressDialog.value = {
      visible: true, total: selectedIds.value.length, success: 0, failed: 0,
      processing: 0, percentage: 0, status: '', completed: false, currentAccount: ''
    }
    const accountMap = {}
    accounts.value.forEach(a => { accountMap[a.id] = a.username })
    const triggerWithRetry = async (id, maxRetries = 3) => {
      progressDialog.value.processing++
      progressDialog.value.currentAccount = accountMap[id] || `账号${id}`
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
          await triggerCheck(id)
          progressDialog.value.processing--
          progressDialog.value.success++
          progressDialog.value.percentage = Math.round(((progressDialog.value.success + progressDialog.value.failed) / progressDialog.value.total) * 100)
          return { success: true }
        } catch (e) {
          if (attempt < maxRetries) await new Promise(r => setTimeout(r, 2000 * attempt))
          else {
            progressDialog.value.processing--
            progressDialog.value.failed++
            progressDialog.value.percentage = Math.round(((progressDialog.value.success + progressDialog.value.failed) / progressDialog.value.total) * 100)
            return { success: false }
          }
        }
      }
    }
    const batchSize = 10
    const results = []
    for (let i = 0; i < selectedIds.value.length; i += batchSize) {
      const batch = selectedIds.value.slice(i, i + batchSize)
      results.push(...await Promise.all(batch.map(id => triggerWithRetry(id))))
      if (i + batchSize < selectedIds.value.length) await new Promise(r => setTimeout(r, 500))
    }
    const failCount = results.filter(r => !r.success).length
    progressDialog.value.completed = true
    progressDialog.value.currentAccount = ''
    progressDialog.value.status = failCount > 0 ? 'warning' : 'success'
    ElMessage[failCount > 0 ? 'warning' : 'success'](`已触发 ${results.length - failCount} 个账号检查${failCount > 0 ? `，${failCount} 个失败` : ''}`)
    let pollCount = 0
    const pollInterval = setInterval(() => {
      loadAccounts(false)
      if (++pollCount >= 15) clearInterval(pollInterval)
    }, 2000)
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

// ===== 图表 =====
const chartRefs = ref({})
const chartInstances = ref({})
const setChartRef = (id, el) => { if (el) chartRefs.value[id] = el }
const renderAllCharts = async () => {
  for (const account of accounts.value) {
    // 每个账号只请求一次 trend 数据，4个指标复用
    let trendData = null
    try {
      trendData = await getAccountTrend(account.id)
    } catch (e) { continue }
    if (!trendData?.data_points?.length) continue
    for (const metric of ['follower_count', 'following_count', 'like_count', 'video_count']) {
      renderMiniChartWithData(account, metric, trendData)
    }
  }
}
const renderMiniChart = async (account, metric) => {
  try {
    const data = await getAccountTrend(account.id)
    renderMiniChartWithData(account, metric, data)
  } catch (e) { console.error(e) }
}
const renderMiniChartWithData = (account, metric, data) => {
  const key = `${metric}_${account.id}`
  const el = chartRefs.value[key]
  if (!el || !data?.data_points?.length) return
  if (chartInstances.value[key]) chartInstances.value[key].dispose()
  const chart = echarts.init(el)
  chartInstances.value[key] = chart
  const colors = {
    follower_count: { line: '#409EFF', area1: 'rgba(64,158,255,0.3)', area2: 'rgba(64,158,255,0.05)' },
    following_count: { line: '#E6A23C', area1: 'rgba(230,162,60,0.3)', area2: 'rgba(230,162,60,0.05)' },
    like_count: { line: '#F56C6C', area1: 'rgba(245,108,108,0.3)', area2: 'rgba(245,108,108,0.05)' },
    video_count: { line: '#67C23A', area1: 'rgba(103,194,58,0.3)', area2: 'rgba(103,194,58,0.05)' }
  }
  const c = colors[metric]
  chart.setOption({
    grid: { left: 5, right: 5, top: 5, bottom: 5 },
    xAxis: { type: 'category', show: false, data: data.data_points.map(p => p.checked_at) },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'line', data: data.data_points.map(p => p[metric]),
      smooth: true, symbol: 'none',
      lineStyle: { width: 2, color: c.line },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: c.area1 }, { offset: 1, color: c.area2 }] } }
    }]
  })
}

// ===== 代理管理 =====
const proxies = ref([])
const proxyLoading = ref(false)
const proxyDialogVisible = ref(false)
const proxySubmitting = ref(false)
const batchProxyDialogVisible = ref(false)
const batchProxySubmitting = ref(false)
const proxyFormRef = ref(null)
const editingProxyId = ref(null)
const testingIds = ref([])
const visiblePasswords = ref({})
const selectedProxies = ref([])
const proxyForm = ref({ proxy_type: 'http', host: '', port: null, username: '', password: '', is_active: true })
const batchProxyForm = ref({ proxies_text: '', proxy_type: 'socks5', is_active: true })
const proxyRules = {
  proxy_type: [{ required: true, message: '请选择代理类型', trigger: 'change' }],
  host: [{ required: true, message: '请输入IP地址', trigger: 'blur' }],
  port: [{ required: true, message: '请输入端口号', trigger: 'blur' }]
}
const proxyDialogTitle = computed(() => editingProxyId.value ? '编辑代理' : '添加代理')

const loadProxies = async () => {
  proxyLoading.value = true
  try {
    proxies.value = await getProxies()
  } catch (e) { console.error(e) }
  finally { proxyLoading.value = false }
}
const handleProxySelectionChange = (sel) => { selectedProxies.value = sel }
const togglePasswordVisibility = (id) => { visiblePasswords.value[id] = !visiblePasswords.value[id] }
const handleCreateProxy = () => {
  editingProxyId.value = null
  proxyForm.value = { proxy_type: 'http', host: '', port: null, username: '', password: '', is_active: true }
  proxyDialogVisible.value = true
}
const handleEditProxy = (row) => {
  editingProxyId.value = row.id
  proxyForm.value = { proxy_type: row.proxy_type, host: row.host, port: row.port, username: row.username || '', password: '', is_active: row.is_active }
  proxyDialogVisible.value = true
}
const handleSubmitProxy = async () => {
  const valid = await proxyFormRef.value.validate().catch(() => false)
  if (!valid) return
  proxySubmitting.value = true
  try {
    const data = { ...proxyForm.value }
    if (!data.username) delete data.username
    if (!data.password) delete data.password
    if (editingProxyId.value) {
      await updateProxy(editingProxyId.value, data)
      ElMessage.success('代理更新成功')
    } else {
      await createProxy(data)
      ElMessage.success('代理创建成功')
    }
    proxyDialogVisible.value = false
    loadProxies()
  } finally { proxySubmitting.value = false }
}
const handleBatchCreateProxy = () => {
  batchProxyForm.value = { proxies_text: '', proxy_type: 'socks5', is_active: true }
  batchProxyDialogVisible.value = true
}
const handleBatchSubmitProxy = async () => {
  if (!batchProxyForm.value.proxies_text.trim()) { ElMessage.warning('请输入代理列表'); return }
  batchProxySubmitting.value = true
  try {
    const result = await batchCreateProxies(batchProxyForm.value)
    if (result.errors?.length > 0) {
      ElMessageBox.alert(result.errors.join('\n'), '导入结果', { type: result.success_count > 0 ? 'warning' : 'error' })
    } else {
      ElMessage.success(`成功导入 ${result.success_count} 个代理`)
    }
    if (result.success_count > 0) { batchProxyDialogVisible.value = false; loadProxies() }
  } finally { batchProxySubmitting.value = false }
}
const handleDeleteProxy = async (row) => {
  const name = row.username ? `${row.username}@${row.host}:${row.port}` : `${row.host}:${row.port}`
  try {
    await ElMessageBox.confirm(`确定要删除代理"${name}"吗？`, '删除确认', { type: 'warning' })
    await deleteProxy(row.id)
    ElMessage.success('代理删除成功')
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleTestProxy = async (row) => {
  testingIds.value.push(row.id)
  try {
    const result = await testProxy(row.id)
    if (result.success) ElMessage.success(`代理测试成功 (响应时间: ${result.response_time}ms)`)
    else ElMessage.error(`代理测试失败: ${result.error}`)
    loadProxies()
  } finally { testingIds.value = testingIds.value.filter(id => id !== row.id) }
}
const handleBatchEnableProxy = async () => {
  try {
    await ElMessageBox.confirm(`确定要启用选中的 ${selectedProxies.value.length} 个代理吗？`, '批量启用', { type: 'warning' })
    let ok = 0, fail = 0
    for (const p of selectedProxies.value) {
      try { await updateProxy(p.id, { is_active: true }); ok++ } catch { fail++ }
    }
    ElMessage.success(`成功启用 ${ok} 个代理${fail > 0 ? `，失败 ${fail} 个` : ''}`)
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleBatchDisableProxy = async () => {
  try {
    await ElMessageBox.confirm(`确定要禁用选中的 ${selectedProxies.value.length} 个代理吗？`, '批量禁用', { type: 'warning' })
    let ok = 0, fail = 0
    for (const p of selectedProxies.value) {
      try { await updateProxy(p.id, { is_active: false }); ok++ } catch { fail++ }
    }
    ElMessage.success(`成功禁用 ${ok} 个代理${fail > 0 ? `，失败 ${fail} 个` : ''}`)
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleBatchDeleteProxy = async () => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedProxies.value.length} 个代理吗？`, '批量删除', { type: 'warning' })
    let ok = 0, fail = 0
    for (const p of selectedProxies.value) {
      try { await deleteProxy(p.id); ok++ } catch { fail++ }
    }
    ElMessage.success(`成功删除 ${ok} 个代理${fail > 0 ? `，失败 ${fail} 个` : ''}`)
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}

// ===== Tab 切换时懒加载 =====
const onTabChange = (tab) => {
  if (tab === 'accounts') loadAccounts()
  else if (tab === 'proxies') loadProxies()
}

onMounted(() => {
  // 支持从其他页面跳转带 tab 参数
  if (route.query.tab) activeTab.value = route.query.tab
  if (route.query.project_id) accountFilters.value.project_id = parseInt(route.query.project_id)
  loadProjects()
  if (activeTab.value === 'accounts') loadAccounts()
  else if (activeTab.value === 'proxies') loadProxies()
})
</script>

<style scoped>
.monitor-manage {
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
  margin: 16px 0 10px;
  padding: 0 20px;
}
.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  background-color: #f0f2f5;
  margin-bottom: 10px;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  padding: 0 20px 16px;
}
.stat-with-chart {
  display: flex;
  flex-direction: column;
  gap: 4px;
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
code {
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}
</style>
