<template>
  <div class="dept-manage">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>部门管理</span>
          <el-button v-permission="'team:dept:create'" type="primary" :icon="Plus" @click="openCreate(null)">
            新增顶级部门
          </el-button>
        </div>
      </template>

      <el-tree
        :data="treeData"
        :props="{ label: 'name', children: 'children' }"
        node-key="id"
        default-expand-all
        class="dept-tree"
      >
        <template #default="{ node, data }">
          <div class="tree-node">
            <span>{{ node.label }}</span>
            <div class="tree-actions">
              <el-button v-permission="'team:dept:create'" link type="primary" size="small" @click.stop="openCreate(data)">
                新增子部门
              </el-button>
              <el-button v-permission="'team:dept:edit'" link type="primary" size="small" @click.stop="openEdit(data)">
                编辑
              </el-button>
              <el-button v-permission="'team:dept:delete'" link type="danger" size="small" @click.stop="handleDelete(data)">
                删除
              </el-button>
            </div>
          </div>
        </template>
      </el-tree>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="400px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="部门名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入部门名称" />
        </el-form-item>
        <el-form-item v-if="form.parent_id !== undefined" label="上级部门">
          <el-input :value="parentName" disabled />
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getDeptTree, createDept, updateDept, deleteDept } from '@/api/team'

// 响应式断点
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const onResize = () => { windowWidth.value = window.innerWidth }

const treeData = ref([])
const dialogVisible = ref(false)
const dialogTitle = ref('')
const submitting = ref(false)
const formRef = ref(null)
const editId = ref(null)
const parentName = ref('')

const form = ref({ name: '', parent_id: null })

const rules = {
  name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }]
}

const loadTree = async () => {
  try {
    const data = await getDeptTree()
    treeData.value = data
  } catch {
    ElMessage.error('加载部门树失败')
  }
}

const openCreate = (parent) => {
  editId.value = null
  form.value = { name: '', parent_id: parent?.id ?? null }
  parentName.value = parent?.name ?? '（顶级）'
  dialogTitle.value = parent ? `新增子部门（${parent.name}）` : '新增顶级部门'
  dialogVisible.value = true
}

const openEdit = (data) => {
  editId.value = data.id
  form.value = { name: data.name, parent_id: data.parent_id ?? null }
  dialogTitle.value = '编辑部门'
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editId.value) {
      await updateDept(editId.value, { name: form.value.name })
      ElMessage.success('更新成功')
    } else {
      await createDept(form.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadTree()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (data) => {
  try {
    await ElMessageBox.confirm(`确定删除部门「${data.name}」？`, '提示', { type: 'warning' })
    await deleteDept(data.id)
    ElMessage.success('删除成功')
    await loadTree()
  } catch (err) {
    if (err === 'cancel') return
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  loadTree()
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

.dept-tree {
  min-height: 200px;
}

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
}

.tree-actions {
  display: none;
}

.tree-node:hover .tree-actions {
  display: flex;
  gap: 4px;
}

@media (max-width: 768px) {
  .dept-manage {
    padding: 0;
  }

  .dept-manage :deep(.el-card__body) {
    padding: 12px;
  }

  .tree-actions {
    display: flex;
    gap: 4px;
  }
}
</style>
