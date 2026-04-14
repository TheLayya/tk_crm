<template>
  <div class="project-list">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>项目管理</span>
          <el-button type="primary" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            新建项目
          </el-button>
        </div>
      </template>

      <el-table :data="projects" v-loading="loading">
        <el-table-column prop="name" label="项目名称" />
        <el-table-column prop="description" label="描述" />
        <el-table-column prop="created_by" label="创建人" width="120">
          <template #default="{ row }">{{ row.created_by || '-' }}</template>
        </el-table-column>
        <el-table-column prop="account_count" label="账号数量" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="viewAccounts(row)">查看账号</el-button>
            <el-button link type="warning" @click="handleMembers(row)">协作成员</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入项目名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入项目描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- Members Dialog -->
    <el-dialog v-model="membersDialogVisible" title="协作成员管理" width="480px">
      <div class="members-tip">
        被添加的成员可查看该项目及其下的监控账号。
      </div>
      <el-select
        v-model="memberUsernames"
        multiple
        filterable
        placeholder="选择协作成员（用户名）"
        style="width: 100%; margin-top: 12px"
      >
        <el-option
          v-for="u in allMembers"
          :key="u.username"
          :label="`${u.real_name ? u.real_name + ' (' + u.username + ')' : u.username}`"
          :value="u.username"
        />
      </el-select>
      <template #footer>
        <el-button @click="membersDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMembersSubmit" :loading="membersSubmitting">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getProjects, createProject, updateProject, deleteProject, getProjectMembers, setProjectMembers } from '@/api/projects'
import { getMembers } from '@/api/team'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const projects = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const editingId = ref(null)

const form = ref({ name: '', description: '' })
const rules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { max: 100, message: '项目名称不能超过100个字符', trigger: 'blur' }
  ]
}
const dialogTitle = computed(() => editingId.value ? '编辑项目' : '新建项目')

// Members
const membersDialogVisible = ref(false)
const membersSubmitting = ref(false)
const memberUsernames = ref([])
const allMembers = ref([])
const currentMembersProjectId = ref(null)

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleString('zh-CN')
}

const loadProjects = async () => {
  loading.value = true
  try {
    projects.value = await getProjects()
  } catch (error) {
    console.error('Failed to load projects:', error)
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  editingId.value = null
  form.value = { name: '', description: '' }
  dialogVisible.value = true
}

const handleEdit = (row) => {
  editingId.value = row.id
  form.value = { name: row.name, description: row.description || '' }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value) {
      await updateProject(editingId.value, form.value)
      ElMessage.success('项目更新成功')
    } else {
      await createProject(form.value)
      ElMessage.success('项目创建成功')
    }
    dialogVisible.value = false
    loadProjects()
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除项目"${row.name}"吗？${row.account_count > 0 ? '该项目下还有账号，无法删除。' : ''}`,
      '删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await deleteProject(row.id)
    ElMessage.success('项目删除成功')
    loadProjects()
  } catch (error) {
    if (error !== 'cancel') console.error('Failed to delete project:', error)
  }
}

const handleMembers = async (row) => {
  currentMembersProjectId.value = row.id
  memberUsernames.value = await getProjectMembers(row.id).catch(() => [])
  // 加载可选成员列表（有权限才拉）
  if (authStore.hasPermission('team:member:view')) {
    const data = await getMembers({ size: 200 }).catch(() => ({ items: [] }))
    allMembers.value = (data.items || []).filter(u => u.username !== row.created_by)
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

const viewAccounts = (row) => {
  router.push({ path: '/accounts', query: { project_id: row.id } })
}

onMounted(() => {
  loadProjects()
})
</script>

<style scoped>
.project-list { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.members-tip { font-size: 13px; color: #909399; }
</style>
