<template>
  <div class="member-manage">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>团队成员 <small class="member-count">{{ total }} 人</small></span>
          <slot name="management-actions" />
          <el-button v-permission="'team:member:create'" type="primary" :icon="Plus" @click="openCreate">
            新增成员
          </el-button>
        </div>
      </template>

      <!-- 搜索栏：桌面端完整版 -->
      <el-form v-if="!isMobile" inline class="search-form" @submit.prevent>
        <el-form-item label="部门">
          <el-select v-model="filters.dept_id" clearable filterable placeholder="全部部门" aria-label="筛选部门" style="width:200px" @change="applyFilters">
            <el-option v-for="d in deptOptions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="filters.username" clearable placeholder="搜索用户名" aria-label="搜索用户名" @clear="applyFilters" @keyup.enter="applyFilters" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.is_active" clearable placeholder="全部" aria-label="筛选成员状态" style="width:100px" @change="applyFilters">
            <el-option label="启用" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="applyFilters">搜索</el-button>
        </el-form-item>
      </el-form>

      <!-- 搜索栏：移动端简化版 -->
      <el-form v-if="isMobile" inline class="search-form" @submit.prevent>
        <el-form-item>
          <el-input v-model="filters.username" clearable placeholder="搜索用户名" aria-label="搜索用户名" @clear="applyFilters" @keyup.enter="applyFilters" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="applyFilters">搜索</el-button>
        </el-form-item>
      </el-form>

      <div v-if="isMobile && (activeFilterTags.length || hasTableQuery)" class="member-query-summary">
        <el-tag v-for="tag in activeFilterTags" :key="tag.key" closable size="small" @close="clearFilter(tag.key)">{{ tag.label }}</el-tag>
        <el-tag v-if="hasTableQuery" size="small" type="info">已应用表格筛选或排序</el-tag>
        <el-button size="small" @click="resetAllQueries">清除全部</el-button>
      </div>

      <!-- 桌面端表格 -->
      <crm-table table-id="team-members" remote :query="tableQuery" :extra-query-active="activeFilterTags.length > 0" @query-reset="resetFilters" @query-change="handleTableQuery" v-if="!isMobile" :data="members" v-loading="loading" stripe>
        <template #query-summary><el-tag v-for="tag in activeFilterTags" :key="tag.key" closable size="small" @close="clearFilter(tag.key)">{{ tag.label }}</el-tag></template>
        <el-table-column column-key="username" filter-type="text" prop="username" label="用户名" />
        <el-table-column column-key="real_name" filter-type="text" prop="real_name" label="姓名" />
        <el-table-column column-key="department_name" prop="department_name" filter-type="text" label="部门">
          <template #default="{ row }">{{ departmentLabel(row.department_id, row.department_name) }}</template>
        </el-table-column>
        <el-table-column column-key="roles" prop="roles" filter-type="text" label="角色">
          <template #default="{ row }">
            <el-tag v-for="r in row.roles" :key="r.id" size="small" style="margin-right:4px">{{ r.name }}</el-tag>
            <span v-if="!row.roles?.length" class="member-unassigned">未分配角色</span>
          </template>
        </el-table-column>
        <el-table-column column-key="is_active" prop="is_active" filter-type="enum" :filter-options="[{ label: '启用', value: true }, { label: '禁用', value: false }]" label="状态">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column column-key="actions" table-tools-disabled label="操作" width="350" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'team:member:edit'" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-permission="'team:log:view'" link type="primary" size="small" @click="emit('view-logs', row.username)">操作记录</el-button>
            <el-button v-permission="'team:member:edit'" link :type="row.is_active ? 'warning' : 'success'" size="small" @click="toggleActive(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button v-permission="'team:member:edit'" link type="info" size="small" @click="handleUnlock(row)" title="解除登录锁定">
              <el-icon><Unlock /></el-icon> 解锁
            </el-button>
            <el-button v-permission="'team:member:reset_password'" link type="primary" size="small" @click="openResetPassword(row)">
              <el-icon><Lock /></el-icon> 重置密码
            </el-button>
            <el-button v-permission="'team:member:delete'" link type="danger" size="small" @click="openDelete(row)">
              <el-icon><Delete /></el-icon> 删除
            </el-button>
          </template>
        </el-table-column>
      </crm-table>

      <!-- 移动端卡片列表 -->
      <div v-if="isMobile" class="ios-card-list" v-loading="loading">
        <div v-for="row in members" :key="row.id" class="ios-card">
          <div class="ios-card-row">
            <span class="member-username">{{ row.username }}</span>
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </div>
          <div v-if="row.real_name" class="ios-card-row">
            <span class="ios-card-row-label">姓名</span>
            <span class="ios-card-row-value">{{ row.real_name }}</span>
          </div>
          <div class="ios-card-row">
            <span class="ios-card-row-label">部门</span>
            <span class="ios-card-row-value">{{ departmentLabel(row.department_id, row.department_name) }}</span>
          </div>
          <div class="ios-card-row">
            <span class="ios-card-row-label">角色</span>
            <span class="ios-card-row-value">
              <el-tag v-for="r in row.roles" :key="r.id" size="small" style="margin-right:4px">{{ r.name }}</el-tag>
              <span v-if="!row.roles?.length" class="member-unassigned">未分配角色</span>
            </span>
          </div>
          <div class="ios-card-actions ios-card-actions-wrap">
            <el-button v-permission="'team:member:edit'" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-permission="'team:log:view'" size="small" @click="emit('view-logs', row.username)">操作记录</el-button>
            <el-button v-permission="'team:member:edit'" size="small" :type="row.is_active ? 'warning' : 'success'" @click="toggleActive(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button v-permission="'team:member:edit'" size="small" type="info" @click="handleUnlock(row)">解锁</el-button>
            <el-button v-permission="'team:member:reset_password'" size="small" @click="openResetPassword(row)">重置密码</el-button>
            <el-button v-permission="'team:member:delete'" size="small" type="danger" @click="openDelete(row)">删除</el-button>
          </div>
        </div>
        <div v-if="!members.length && !loading" style="text-align:center;color:#999;padding:32px 0">暂无数据</div>
      </div>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        class="pagination"
        @current-change="loadMembers"
      />
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="memberDialogVisible" :title="editId ? '编辑成员' : '新增成员'" width="500px">
      <el-form ref="memberFormRef" :model="memberForm" :rules="memberRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="memberForm.username" :disabled="!!editId" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="memberForm.real_name" />
        </el-form-item>
        <el-form-item v-if="!editId" label="密码" prop="password">
          <el-input v-model="memberForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="部门">
          <el-select v-model="memberForm.department_id" clearable filterable placeholder="请选择部门" style="width:100%">
            <el-option v-for="d in deptOptions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="memberForm.role_ids" multiple filterable placeholder="请选择角色" style="width:100%" popper-class="member-role-options">
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id">
              <div class="role-option__heading"><span>{{ r.name }}</span><small>{{ roleScopeLabel(r.data_scope) }}</small></div>
              <div v-if="r.description" class="role-option__description">{{ r.description }}</div>
            </el-option>
          </el-select>
          <p class="member-role-hint">角色决定可用功能与数据范围；可分配多个角色。</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleMemberSubmit">{{ editId ? '保存成员' : '创建成员' }}</el-button>
      </template>
    </el-dialog>

    <!-- 二次确认弹窗（删除/重置密码） -->
    <el-dialog v-model="confirmDialogVisible" :title="confirmAction === 'delete' ? '确认删除成员' : '确认重置密码'" width="420px">
      <p>{{ confirmAction === 'delete' ? `即将删除成员「${confirmTarget?.username}」，此操作不可撤销。` : `即将重置「${confirmTarget?.username}」的密码。` }}</p>
      <el-form v-if="confirmAction === 'reset'" label-width="80px" style="margin-top:12px">
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password placeholder="至少8位" />
        </el-form-item>
      </el-form>
      <p style="margin-top:12px;color:#606266;font-size:13px">请输入您的登录密码以确认操作：</p>
      <el-input v-model="confirmPassword" type="password" show-password placeholder="请输入当前登录密码" style="margin-top:8px" />
      <template #footer>
        <el-button @click="confirmDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="confirmLoading" @click="handleConfirmAction">确认执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { useTableQuery } from '@/composables/useTableQuery'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Lock, Unlock, Delete } from '@element-plus/icons-vue'
import { getMembers, createMember, updateMember, deleteMember, resetMemberPassword, getRoles, getDeptTree, unlockMember } from '@/api/team'
import { verifyPassword } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const emit = defineEmits(['view-logs'])
const authStore = useAuthStore()

// 响应式断点
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const onResize = () => { windowWidth.value = window.innerWidth }

const { tableQuery, queryParams } = useTableQuery('team-members')
const handleTableQuery = (nextQuery) => { tableQuery.value = nextQuery; page.value = 1; loadMembers() }

const members = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ dept_id: null, username: '', is_active: null })
const appliedFilters = ref({ ...filters.value })

const roles = ref([])
const deptOptions = ref([])
const departmentLabel = (id, fallback) => deptOptions.value.find(dept => dept.id === id)?.name || fallback || '未分配部门'
const roleScopeLabel = scope => ({ all: '全部数据', dept: '本部门数据', self: '本人数据' }[scope] || '数据范围未设置')
const activeFilterTags = computed(() => [
  ...(appliedFilters.value.dept_id ? [{ key: 'dept_id', label: `部门：${departmentLabel(appliedFilters.value.dept_id, '已选部门')}` }] : []),
  ...(appliedFilters.value.username ? [{ key: 'username', label: `用户名：${appliedFilters.value.username}` }] : []),
  ...(typeof appliedFilters.value.is_active === 'boolean' ? [{ key: 'is_active', label: `状态：${appliedFilters.value.is_active ? '启用' : '禁用'}` }] : []),
])
const hasTableQuery = computed(() => Boolean(tableQuery.value.sortBy || Object.keys(tableQuery.value.filters || {}).length))
const applyFilters = () => {
  filters.value.username = filters.value.username.trim()
  appliedFilters.value = { dept_id: filters.value.dept_id || null, username: filters.value.username, is_active: typeof filters.value.is_active === 'boolean' ? filters.value.is_active : null }
  page.value = 1
  loadMembers()
}
const clearFilter = key => {
  const value = key === 'username' ? '' : null
  filters.value[key] = value
  appliedFilters.value = { ...appliedFilters.value, [key]: value }
  page.value = 1
  loadMembers()
}
// CrmTable emits query-change immediately after query-reset; keep that as the single request.
const resetFilters = () => { filters.value = { dept_id: null, username: '', is_active: null }; appliedFilters.value = { ...filters.value } }
const resetAllQueries = () => { resetFilters(); handleTableQuery({ sortBy: null, sortOrder: null, filters: {} }) }

// Member dialog
const memberDialogVisible = ref(false)
const editId = ref(null)
const submitting = ref(false)
const memberFormRef = ref(null)
const memberForm = ref({ username: '', real_name: '', password: '', department_id: null, role_ids: [] })
const memberRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码长度不得少于8个字符', trigger: 'blur' }
  ]
}

// Confirm dialog
const confirmDialogVisible = ref(false)
const confirmAction = ref('')
const confirmTarget = ref(null)
const confirmPassword = ref('')
const confirmLoading = ref(false)
const newPassword = ref('')

const flattenDepts = (nodes, result = [], path = []) => {
  for (const n of nodes) {
    const names = [...path, n.name]
    result.push({ id: n.id, name: names.join(' / ') })
    if (n.children?.length) flattenDepts(n.children, result, names)
  }
  return result
}

let memberRequestSequence = 0
const loadMembers = async () => {
  const sequence = ++memberRequestSequence
  loading.value = true
  try {
    const params = { ...queryParams.value, page: page.value, size: pageSize.value }
    if (appliedFilters.value.dept_id) params.dept_id = appliedFilters.value.dept_id
    if (appliedFilters.value.username) params.username = appliedFilters.value.username
    if (typeof appliedFilters.value.is_active === 'boolean') params.is_active = appliedFilters.value.is_active
    const data = await getMembers(params)
    if (sequence !== memberRequestSequence) return
    members.value = data.items
    total.value = data.total
  } catch {
    if (sequence === memberRequestSequence) ElMessage.error('加载成员列表失败')
  } finally {
    if (sequence === memberRequestSequence) loading.value = false
  }
}

const openCreate = () => {
  editId.value = null
  memberForm.value = { username: '', real_name: '', password: '', department_id: null, role_ids: [] }
  memberDialogVisible.value = true
}

const openEdit = (row) => {
  editId.value = row.id
  memberForm.value = {
    username: row.username,
    real_name: row.real_name || '',
    department_id: row.department_id || null,
    role_ids: row.roles?.map(r => r.id) || []
  }
  memberDialogVisible.value = true
}

const handleMemberSubmit = async () => {
  const valid = await memberFormRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editId.value) {
      await updateMember(editId.value, memberForm.value)
      ElMessage.success('更新成功')
    } else {
      await createMember(memberForm.value)
      ElMessage.success('创建成功')
    }
    memberDialogVisible.value = false
    await loadMembers()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

const toggleActive = async (row) => {
  try {
    await updateMember(row.id, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '已禁用' : '已启用')
    await loadMembers()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  }
}

const handleUnlock = async (row) => {
  try {
    await unlockMember(row.id)
    ElMessage.success(`已解除 ${row.username} 的登录锁定`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '解锁失败')
  }
}

const openDelete = (row) => {
  confirmAction.value = 'delete'
  confirmTarget.value = row
  confirmPassword.value = ''
  confirmDialogVisible.value = true
}

const openResetPassword = (row) => {
  confirmAction.value = 'reset'
  confirmTarget.value = row
  confirmPassword.value = ''
  newPassword.value = ''
  confirmDialogVisible.value = true
}

const handleConfirmAction = async () => {
  if (!confirmPassword.value) {
    ElMessage.warning('请输入当前登录密码')
    return
  }
  if (confirmAction.value === 'reset' && newPassword.value.length < 8) {
    ElMessage.warning('新密码长度不得少于8个字符')
    return
  }
  confirmLoading.value = true
  try {
    const { operation_token } = await verifyPassword(confirmPassword.value)
    if (confirmAction.value === 'delete') {
      await deleteMember(confirmTarget.value.id, operation_token)
      ElMessage.success('删除成功')
    } else {
      await resetMemberPassword(confirmTarget.value.id, newPassword.value, operation_token)
      ElMessage.success('密码重置成功')
    }
    confirmDialogVisible.value = false
    await loadMembers()
  } catch (err) {
    const status = err?.response?.status
    if (status === 401) {
      ElMessage.error('密码验证失败，请重新输入')
    } else {
      ElMessage.error(err?.response?.data?.detail || '操作失败')
    }
  } finally {
    confirmLoading.value = false
  }
}

const refresh = async () => {
  await Promise.all([
    authStore.hasPermission('team:dept:view') ? getDeptTree().then(tree => { deptOptions.value = flattenDepts(tree) }).catch(() => {}) : Promise.resolve(),
    authStore.hasPermission('team:role:view') ? getRoles().then(roleList => { roles.value = roleList }).catch(() => {}) : Promise.resolve(),
    loadMembers()
  ])
}
defineExpose({ refresh })
onMounted(() => {
  window.addEventListener('resize', onResize)
  refresh()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.member-count { color: #909399; font-size: 12px; font-weight: normal; }
.member-unassigned { color: var(--el-text-color-secondary); font-size: 12px; }
.member-query-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.member-role-hint { width: 100%; margin: 4px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
.role-option__heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.role-option__heading small, .role-option__description { color: var(--el-text-color-secondary); font-size: 12px; }
.role-option__description { line-height: 1.5; white-space: normal; overflow-wrap: anywhere; }
:global(.member-role-options .el-select-dropdown__item) { height: auto; min-height: 34px; padding-top: 6px; padding-bottom: 6px; line-height: 1.6; }
.card-header { flex-wrap: wrap; gap: 8px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.search-form {
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.member-username {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

@media (max-width: 768px) {
  .member-manage {
    padding: 0;
  }

  .member-manage :deep(.el-card__body) {
    padding: 12px;
  }
}

.ios-card-actions-wrap {
  flex-wrap: wrap;
}

.ios-card-actions-wrap .el-button {
  flex: unset !important;
  min-width: unset !important;
}
</style>
