<template>
  <div class="member-manage">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>成员管理</span>
          <el-button v-permission="'team:member:create'" type="primary" :icon="Plus" @click="openCreate">
            新增成员
          </el-button>
        </div>
      </template>

      <!-- 搜索栏：桌面端完整版 -->
      <el-form v-if="!isMobile" inline class="search-form">
        <el-form-item label="部门">
          <el-select v-model="filters.dept_id" clearable placeholder="全部部门" style="width:160px" @change="loadMembers">
            <el-option v-for="d in deptOptions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="filters.username" clearable placeholder="搜索用户名" @keyup.enter="loadMembers" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.is_active" clearable placeholder="全部" style="width:100px" @change="loadMembers">
            <el-option label="启用" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadMembers">搜索</el-button>
        </el-form-item>
      </el-form>

      <!-- 搜索栏：移动端简化版 -->
      <el-form v-if="isMobile" inline class="search-form">
        <el-form-item>
          <el-input v-model="filters.username" clearable placeholder="搜索用户名" @keyup.enter="loadMembers" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadMembers">搜索</el-button>
        </el-form-item>
      </el-form>

      <!-- 桌面端表格 -->
      <el-table v-if="!isMobile" :data="members" v-loading="loading" stripe>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="real_name" label="姓名" />
        <el-table-column prop="department_name" label="部门" />
        <el-table-column label="角色">
          <template #default="{ row }">
            <el-tag v-for="r in row.roles" :key="r.id" size="small" style="margin-right:4px">{{ r.name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260">
          <template #default="{ row }">
            <el-button v-permission="'team:member:edit'" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
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
      </el-table>

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
          <div v-if="row.department_name" class="ios-card-row">
            <span class="ios-card-row-label">部门</span>
            <span class="ios-card-row-value">{{ row.department_name }}</span>
          </div>
          <div v-if="row.roles?.length" class="ios-card-row">
            <span class="ios-card-row-label">角色</span>
            <span class="ios-card-row-value">
              <el-tag v-for="r in row.roles" :key="r.id" size="small" style="margin-right:4px">{{ r.name }}</el-tag>
            </span>
          </div>
          <div class="ios-card-actions">
            <el-button v-permission="'team:member:edit'" size="small" @click="openEdit(row)">编辑</el-button>
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
          <el-select v-model="memberForm.department_id" clearable placeholder="请选择部门" style="width:100%">
            <el-option v-for="d in deptOptions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="memberForm.role_ids" multiple placeholder="请选择角色" style="width:100%">
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleMemberSubmit">确定</el-button>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Lock, Unlock, Delete } from '@element-plus/icons-vue'
import { getMembers, createMember, updateMember, deleteMember, resetMemberPassword, getRoles, getDeptTree, unlockMember } from '@/api/team'
import { verifyPassword } from '@/api/auth'

// 响应式断点
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const onResize = () => { windowWidth.value = window.innerWidth }

const members = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ dept_id: null, username: '', is_active: null })

const roles = ref([])
const deptOptions = ref([])

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

const flattenDepts = (nodes, result = []) => {
  for (const n of nodes) {
    result.push({ id: n.id, name: n.name })
    if (n.children?.length) flattenDepts(n.children, result)
  }
  return result
}

const loadMembers = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: pageSize.value }
    if (filters.value.dept_id) params.dept_id = filters.value.dept_id
    if (filters.value.username) params.username = filters.value.username
    if (filters.value.is_active !== null && filters.value.is_active !== undefined) params.is_active = filters.value.is_active
    const data = await getMembers(params)
    members.value = data.items
    total.value = data.total
  } catch {
    ElMessage.error('加载成员列表失败')
  } finally {
    loading.value = false
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

onMounted(async () => {
  window.addEventListener('resize', onResize)
  const [tree, roleList] = await Promise.all([getDeptTree(), getRoles()])
  deptOptions.value = flattenDepts(tree)
  roles.value = roleList
  await loadMembers()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
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
</style>
