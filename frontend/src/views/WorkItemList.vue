<template>
  <div class="work-item-page">
    <div class="page-heading">
      <div>
        <h2>备忘管理</h2>
        <span>团队共享的一张备忘清单，内容、任务和到期事项都放在这里</span>
      </div>
      <div class="heading-actions">
        <el-button v-if="authStore.hasPermission('settings:edit')" @click="openCategorySettings">大类设置</el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">＋新增备忘</el-button>
      </div>
    </div>

    <el-card class="table-card" shadow="never">
      <div class="toolbar">
        <el-input v-model="filters.keyword" clearable placeholder="搜索标题或内容" @keyup.enter="load" @clear="load" />
        <el-select v-model="filters.category" clearable style="width:130px" placeholder="大类" @change="load">
          <el-option v-for="category in categories" :key="category" :label="category" :value="category" />
        </el-select>
        <el-select v-model="filters.status" style="width:130px" @change="load">
          <el-option label="待处理" value="pending" /><el-option label="已完成" value="done" /><el-option label="全部" value="all" />
        </el-select>
        <el-checkbox v-model="filters.mine" @change="load">只看提醒我的</el-checkbox>
        <el-button type="primary" plain @click="load">搜索</el-button>
        <span class="remind-overdue" v-if="summary.overdue">我的逾期 {{ summary.overdue }}</span>
        <span class="remind-soon" v-if="summary.due_soon">7天内到期 {{ summary.due_soon }}</span>
      </div>

      <el-table ref="tableRef" v-loading="loading" :data="items" row-key="id" size="small" empty-text="暂无备忘">
        <el-table-column type="expand" width="42">
          <template #default="{ row }">
            <div class="item-content">{{ row.content || '没有填写内容' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="大类" width="110"><template #default="{ row }"><el-tag size="small" effect="plain">{{ row.category }}</el-tag></template></el-table-column>
        <el-table-column label="备忘" min-width="300">
          <template #default="{ row }">
            <button class="item-title" :class="{ done: row.is_done }" @click="tableRef.toggleRowExpansion(row)">{{ row.title }}</button>
            <div class="item-preview">{{ row.content || '无内容' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="提醒成员" min-width="160">
          <template #default="{ row }">{{ row.reminder_users?.includes('__all__') ? '全员' : row.reminder_users?.join('、') || '—' }}</template>
        </el-table-column>
        <el-table-column label="提醒时间" width="180">
          <template #default="{ row }"><span :class="remindClass(row)">{{ formatDate(row.remind_at) }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.is_done ? 'info' : remindType(row)" size="small">{{ row.is_done ? '已完成' : remindLabel(row) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canManage" link type="primary" @click="toggleDone(row)">{{ row.is_done ? '恢复' : '完成' }}</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="categoryVisible" title="大类设置" width="min(440px, 94vw)">
      <p class="category-hint">每行一个大类，保留“其他”。已使用的大类不能直接删除。</p>
      <el-input v-model="categoryText" type="textarea" :rows="8" />
      <template #footer><el-button @click="categoryVisible = false">取消</el-button><el-button type="primary" :loading="categorySaving" @click="saveCategories">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑备忘' : '新增备忘'" width="min(620px, 94vw)">
      <el-form label-width="90px">
        <el-form-item label="标题" required><el-input v-model="form.title" maxlength="200" show-word-limit placeholder="例如：演示 VPS 续费" /></el-form-item>
        <el-form-item label="大类" required><el-select v-model="form.category" style="width:100%"><el-option v-for="category in categories" :key="category" :label="category" :value="category" /></el-select></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="7" placeholder="SSH 信息、采购渠道、任务说明……直接写在这里" /></el-form-item>
        <el-form-item label="提醒成员"><el-select v-model="form.reminder_users" multiple filterable clearable style="width:100%" placeholder="选择成员或全员，可不填" @change="normalizeReminderUsers">
          <el-option label="全员" value="__all__" />
          <el-option v-for="member in members" :key="member.username" :label="member.real_name ? `${member.real_name}（${member.username}）` : member.username" :value="member.username" />
        </el-select></el-form-item>
        <el-form-item label="提醒时间"><el-date-picker v-model="form.remind_at" type="datetime" clearable style="width:100%" placeholder="可不填" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createWorkItem, deleteWorkItem, getReminderMembers, getWorkItemCategories, getWorkItemSummary, getWorkItems, updateWorkItem, updateWorkItemCategories } from '@/api/work_items'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('work_item:manage'))
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(false)
const items = ref([])
const tableRef = ref(null)
const members = ref([])
const categories = ref([])
const categoryVisible = ref(false)
const categoryText = ref('')
const categorySaving = ref(false)
const openCategorySettings = () => { categoryText.value = categories.value.join('\n'); categoryVisible.value = true }
const saveCategories = async () => {
  categorySaving.value = true
  try {
    categories.value = await updateWorkItemCategories(categoryText.value.split('\n').map(name => name.trim()).filter(Boolean))
    categoryVisible.value = false
    if (!categories.value.includes(filters.category)) filters.category = ''
    ElMessage.success('大类已更新')
    await load()
  } finally { categorySaving.value = false }
}
const summary = reactive({ overdue: 0, due_soon: 0, pending: 0 })
const filters = reactive({ keyword: '', category: '', status: 'pending', mine: false })
const form = reactive({ id: null, title: '', category: '其他', content: '', reminder_users: [], remind_at: null, is_done: false })

const load = async () => {
  loading.value = true
  try {
    const [result, stats] = await Promise.all([getWorkItems(filters), getWorkItemSummary()])
    items.value = result.items || []
    Object.assign(summary, stats)
  } finally { loading.value = false }
}
const loadMembers = async () => {
  members.value = await getReminderMembers()
}
const loadCategories = async () => { categories.value = await getWorkItemCategories() }
const resetForm = () => Object.assign(form, { id: null, title: '', category: '其他', content: '', reminder_users: [], remind_at: null, is_done: false })
const normalizeReminderUsers = (values) => {
  if (values.includes('__all__')) form.reminder_users = ['__all__']
}
const openCreate = () => { editing.value = false; resetForm(); dialogVisible.value = true }
const openEdit = (row) => { editing.value = true; Object.assign(form, { ...row, category: row.category || '其他', remind_at: row.remind_at ? new Date(row.remind_at) : null, reminder_users: [...(row.reminder_users || [])] }); dialogVisible.value = true }
const save = async () => {
  if (!form.title.trim()) return ElMessage.warning('请填写标题')
  saving.value = true
  try {
    const data = { title: form.title, category: form.category, content: form.content, reminder_users: form.reminder_users, remind_at: form.remind_at ? new Date(form.remind_at).toISOString() : null, is_done: form.is_done }
    if (editing.value) await updateWorkItem(form.id, data); else await createWorkItem(data)
    ElMessage.success('已保存'); dialogVisible.value = false; await load()
  } finally { saving.value = false }
}
const toggleDone = async (row) => { await updateWorkItem(row.id, { ...row, is_done: !row.is_done }); await load() }
const remove = async (row) => { await ElMessageBox.confirm('确定删除这条备忘吗？', '提示', { type: 'warning' }); await deleteWorkItem(row.id); await load() }
const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
const remindState = (row) => {
  if (!row.remind_at || row.is_done) return 'normal'
  const time = new Date(row.remind_at).getTime() - Date.now()
  return time < 0 ? 'overdue' : time <= 7 * 86400000 ? 'soon' : 'normal'
}
const remindLabel = (row) => ({ overdue: '已逾期', soon: '即将到期', normal: '待处理' }[remindState(row)])
const remindType = (row) => ({ overdue: 'danger', soon: 'warning', normal: '' }[remindState(row)])
const remindClass = (row) => `remind-${remindState(row)}`

onMounted(() => { load(); loadMembers(); loadCategories() })
</script>

<style scoped>
.work-item-page { max-width: 1500px; margin: 0 auto; }
.page-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-heading h2 { margin:0 0 6px; color:#1f2937; }
.page-heading span { color:#909399; font-size:13px; }
.toolbar { display:flex; gap:10px; align-items:center; margin-bottom:14px; }.toolbar .el-input { width:300px; }
.item-title { font:inherit; font-weight:600; color:#303133; padding:0; border:0; background:none; text-align:left; cursor:pointer; }.item-title:hover { color:var(--el-color-primary); }.item-title.done { color:#a8abb2; text-decoration:line-through; }.item-preview { margin-top:4px; color:#909399; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:620px; }
.item-content { white-space:pre-wrap; padding:10px 28px; color:#606266; line-height:1.7; background:#fafafa; border-radius:4px; }
.category-hint { margin:0 0 10px; color:#909399; font-size:13px; }
.remind-overdue { color:#f56c6c; }.remind-soon { color:#e6a23c; }
@media (max-width:768px) { .toolbar { flex-wrap:wrap; }.toolbar .el-input { width:100%; } }
</style>
