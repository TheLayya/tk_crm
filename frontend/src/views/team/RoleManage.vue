<template>
  <div class="role-manage">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>角色管理</span>
          <el-button v-permission="'team:role:create'" type="primary" :icon="Plus" @click="openCreate">
            新增角色
          </el-button>
        </div>
      </template>

      <el-table :data="roles" v-loading="loading" stripe>
        <el-table-column prop="name" label="角色名称" />
        <el-table-column prop="description" label="描述" />
        <el-table-column label="权限数量">
          <template #default="{ row }">{{ row.permissions?.length || 0 }} 项</template>
        </el-table-column>
        <el-table-column label="数据范围" width="120">
          <template #default="{ row }">
            <el-tag :type="row.data_scope === 'all' ? 'success' : row.data_scope === 'dept' ? 'primary' : 'warning'" size="small">
              {{ row.data_scope === 'all' ? '全部数据' : row.data_scope === 'dept' ? '本部门数据' : '本人数据' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button v-permission="'team:role:edit'" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-permission="'team:role:delete'" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editId ? '编辑角色' : '新增角色'" width="700px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="数据范围">
          <el-radio-group v-model="form.data_scope">
            <el-radio value="all">全部数据（可查看所有账号）</el-radio>
            <el-radio value="dept">本部门数据（可查看同部门成员的账号）</el-radio>
            <el-radio value="self">本人数据（只能查看注册人或使用人为自己的账号）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="权限">
          <div class="permission-matrix">
            <div v-for="group in permissionGroups" :key="group.module" class="perm-group">
              <div class="perm-group-title">{{ group.label }}</div>
              <div class="perm-items">
                <el-checkbox
                  v-for="p in group.perms"
                  :key="p.value"
                  v-model="selectedPerms"
                  :label="p.value"
                >
                  {{ p.label }}
                </el-checkbox>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getRoles, createRole, updateRole, deleteRole } from '@/api/team'

const roles = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editId = ref(null)
const submitting = ref(false)
const formRef = ref(null)
const selectedPerms = ref([])

const form = ref({ name: '', description: '', data_scope: 'all' })
const rules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }]
}

const permissionGroups = [
  {
    module: 'monitor', label: '监控管理',
    perms: [
      { value: 'monitor:view', label: '查看' },
      { value: 'monitor:check', label: '账号检查' },
      { value: 'monitor:proxy', label: '代理管理' }
    ]
  },
  {
    module: 'op_account', label: '运营账号',
    perms: [
      { value: 'op_account:view', label: '查看' },
      { value: 'op_account:create', label: '新增' },
      { value: 'op_account:edit', label: '编辑' },
      { value: 'op_account:delete', label: '删除' },
      { value: 'op_account:import', label: '导入' },
      { value: 'op_account:export', label: '导出' },
      { value: 'op_account:collect', label: '采集' }
    ]
  },
  {
    module: 'settings', label: '系统设置',
    perms: [
      { value: 'settings:view', label: '查看' },
      { value: 'settings:edit', label: '编辑' }
    ]
  },
  {
    module: 'team_dept', label: '部门管理',
    perms: [
      { value: 'team:dept:view', label: '查看' },
      { value: 'team:dept:create', label: '新增' },
      { value: 'team:dept:edit', label: '编辑' },
      { value: 'team:dept:delete', label: '删除' }
    ]
  },
  {
    module: 'team_member', label: '成员管理',
    perms: [
      { value: 'team:member:view', label: '查看' },
      { value: 'team:member:create', label: '新增' },
      { value: 'team:member:edit', label: '编辑' },
      { value: 'team:member:delete', label: '删除' },
      { value: 'team:member:reset_password', label: '重置密码' }
    ]
  },
  {
    module: 'team_role', label: '角色管理',
    perms: [
      { value: 'team:role:view', label: '查看' },
      { value: 'team:role:create', label: '新增' },
      { value: 'team:role:edit', label: '编辑' },
      { value: 'team:role:delete', label: '删除' }
    ]
  },
  {
    module: 'team_log', label: '日志查看',
    perms: [
      { value: 'team:log:view', label: '查看' }
    ]
  }
]

const loadRoles = async () => {
  loading.value = true
  try {
    roles.value = await getRoles()
  } catch {
    ElMessage.error('加载角色列表失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editId.value = null
  form.value = { name: '', description: '', data_scope: 'all' }
  selectedPerms.value = []
  dialogVisible.value = true
}

const openEdit = (row) => {
  editId.value = row.id
  form.value = { name: row.name, description: row.description || '', data_scope: row.data_scope || 'all' }
  selectedPerms.value = [...(row.permissions || [])]
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload = { ...form.value, permissions: selectedPerms.value }
    if (editId.value) {
      await updateRole(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createRole(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadRoles()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除角色「${row.name}」？`, '提示', { type: 'warning' })
    await deleteRole(row.id)
    ElMessage.success('删除成功')
    await loadRoles()
  } catch (err) {
    if (err === 'cancel') return
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

onMounted(loadRoles)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.permission-matrix {
  width: 100%;
}

.perm-group {
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.perm-group-title {
  background: #f5f7fa;
  padding: 6px 12px;
  font-weight: 600;
  font-size: 13px;
  color: #606266;
}

.perm-items {
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
