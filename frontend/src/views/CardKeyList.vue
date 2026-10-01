<template>
  <div class="card-key-page">
    <div class="page-heading">
      <div><h2>卡密管理</h2><span>按项目统一领取，避免遗漏和重复使用</span></div>
      <el-button v-if="canManage" type="primary" @click="openProject()">＋新建项目</el-button>
    </div>
    <el-card shadow="never" class="project-card">
      <div class="toolbar">
        <el-select v-model="selectedId" filterable placeholder="选择项目" style="width:280px" @change="reloadKeys">
          <el-option v-for="project in projects" :key="project.id" :label="`${project.name}${project.is_active ? '' : '（已结束）'}`" :value="project.id" />
        </el-select>
        <el-tag v-if="selected" type="success">可领取 {{ selected.available }}</el-tag>
        <el-tag v-if="selected" type="info">已领取 {{ selected.claimed }}</el-tag>
        <el-tag v-if="selected">已消耗 {{ selected.consumed }}</el-tag>
        <span class="project-description" :title="selected?.description">{{ selected?.description }}</span>
        <el-button v-if="canManage && selected" :disabled="!selected.is_active" @click="openImport">批量导入</el-button>
        <el-button v-if="canManage && selected" @click="openProject(selected)">编辑项目</el-button>
      </div>
      <el-alert v-if="selected && !selected.is_active" title="项目已结束，停止新领取，已领取卡密仍可确认消耗" type="warning" :closable="false" />
      <el-empty v-if="!selected" :description="canManage ? '先新建项目，选择协助成员并导入卡密' : '暂无分配给你的项目'" :image-size="70" />
      <div v-if="selected" class="claim-bar">
        <div><strong>当前项目</strong><span>{{ selected.name }}</span><small>协助成员：{{ memberLabel(selected.members) }}</small></div>
        <el-button type="primary" :disabled="!selected.can_claim || !selected.available || !!pendingKey" :loading="claiming" @click="claim">领取下一份</el-button>
      </div>
      <div v-if="pendingKey" class="pending-key">
        <strong>我的待消耗</strong><code>{{ pendingKey.content }}</code>
        <el-button size="small" @click="copy(pendingKey.content)">复制</el-button>
        <el-button size="small" type="primary" :loading="consuming" @click="consume(pendingKey)">确认已消耗</el-button>
        <el-button size="small" :disabled="consuming" @click="release(pendingKey)">归还未使用</el-button>
      </div>
      <div v-if="selected" class="record-filters">
        <strong>{{ canManage ? '卡密记录' : '我的领取记录' }}</strong>
        <el-select v-model="filters.status" clearable placeholder="全部状态" style="width:125px" @change="reloadKeys"><el-option label="可领取" value="available" v-if="canManage" /><el-option label="待消耗" value="claimed" /><el-option label="已消耗" value="consumed" /></el-select>
        <el-checkbox v-if="canManage" v-model="filters.mine" @change="reloadKeys">只看我的</el-checkbox>
        <el-button link type="primary" @click="load">刷新</el-button>
      </div>
      <el-table v-if="selected" v-loading="loading" :data="keys" size="small" empty-text="暂无记录，领取后在这里找回">
        <el-table-column label="卡密 / 链接" min-width="420"><template #default="{ row }"><code v-if="row.content">{{ row.content }}</code><span v-else class="muted">领取后可见</span></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="领取人" prop="claimed_by" width="130" />
        <el-table-column label="领取时间" width="180"><template #default="{ row }">{{ formatDate(row.claimed_at) }}</template></el-table-column>
        <el-table-column label="消耗时间" width="180"><template #default="{ row }">{{ formatDate(row.consumed_at) }}</template></el-table-column>
        <el-table-column label="操作" width="235" fixed="right"><template #default="{ row }"><el-button v-if="row.content" link type="primary" @click="copy(row.content)">复制</el-button><template v-if="row.status === 'claimed' && (row.claimed_by === username || canManage)"><el-button :disabled="consuming" link type="primary" @click="consume(row)">确认消耗</el-button><el-button :disabled="consuming" link type="warning" @click="release(row)">归还</el-button></template><el-button v-if="row.history?.length" link @click="historyRow = row">记录</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-if="total" class="pagination" v-model:current-page="filters.page" :page-size="filters.page_size" :total="total" layout="total, prev, pager, next" @current-change="loadKeys" />
    </el-card>
    <el-dialog :model-value="!!historyRow" title="卡密流转记录" width="min(520px, 94vw)" @close="historyRow = null">
      <el-table :data="historyRow?.history || []" size="small"><el-table-column label="操作" width="85"><template #default="{ row }">{{ { claim: '领取', release: '归还', consume: '消耗' }[row.action] }}</template></el-table-column><el-table-column prop="username" label="操作人" /><el-table-column label="时间" width="190"><template #default="{ row }">{{ formatDate(row.time) }}</template></el-table-column></el-table>
    </el-dialog>
    <el-dialog v-model="projectVisible" :title="editing ? '编辑项目' : '新建项目'" width="min(600px, 94vw)">
      <el-form label-width="90px"><el-form-item label="项目名称" required><el-input v-model="projectForm.name" /></el-form-item><el-form-item label="任务说明"><el-input v-model="projectForm.description" type="textarea" :rows="3" /></el-form-item><el-form-item label="协助成员" required><el-select v-model="projectForm.members" multiple filterable style="width:100%" @change="normalizeMembers"><el-option label="全员" value="__all__" /><el-option v-for="member in members" :key="member.username" :label="member.real_name ? `${member.username}（${member.real_name}）` : member.username" :value="member.username" /></el-select></el-form-item><el-form-item label="项目状态"><el-switch v-model="projectForm.is_active" active-text="进行中" inactive-text="已结束" /></el-form-item></el-form>
      <template #footer><el-button @click="projectVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProject">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="importVisible" title="批量导入卡密" width="min(620px, 94vw)"><p>导入项目：<strong>{{ importTarget.name }}</strong></p><p class="hint">一行一份，支持字符串或链接；重复内容会自动跳过。</p><el-input v-model="importText" type="textarea" :rows="12" placeholder="每行粘贴一份卡密或链接" /><template #footer><el-button @click="importVisible=false">取消</el-button><el-button type="primary" :loading="importing" @click="saveImport">导入</el-button></template></el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getCardKeyProjects, getCardKeyMembers, createCardKeyProject, updateCardKeyProject, importCardKeys, getCardKeys, claimCardKey, consumeCardKey, releaseCardKey } from '@/api/card_keys'
const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('card_key:manage'))
const username = computed(() => auth.user?.username)
const projects = ref([]); const members = ref([]); const keys = ref([]); const selectedId = ref(null); const loading = ref(false); const claiming = ref(false); const saving = ref(false); const importing = ref(false); const projectVisible = ref(false); const importVisible = ref(false); const editing = ref(false); const importText = ref('')
const projectForm = reactive({ id: null, name: '', description: '', members: [], is_active: true }); const selected = computed(() => projects.value.find(x => x.id === selectedId.value))
const filters = reactive({ page: 1, page_size: 30, status: '', mine: false })
const total = ref(0)
const pendingKey = ref(null)
const consuming = ref(false)
const historyRow = ref(null)
const importTarget = reactive({ id: null, name: '' })
let requestVersion = 0
let projectRequestVersion = 0
const clearData = () => {
  requestVersion++
  loading.value = false
  projects.value = []
  selectedId.value = null
  keys.value = []
  total.value = 0
  pendingKey.value = null
  historyRow.value = null
  filters.page = 1
}
const load = async () => {
  const version = ++projectRequestVersion
  try {
    const result = await getCardKeyProjects()
    if (version !== projectRequestVersion) return
    projects.value = result
    if (!projects.value.some(project => project.id === selectedId.value)) {
      selectedId.value = projects.value[0]?.id || null
      filters.page = 1
      keys.value = []
      total.value = 0
      pendingKey.value = null
      historyRow.value = null
    }
    await loadKeys()
  } catch (error) {
    if (version === projectRequestVersion) clearData()
    throw error
  }
}
const loadKeys = async () => {
  const version = ++requestVersion
  if (!selectedId.value) { keys.value = []; total.value = 0; pendingKey.value = null; loading.value = false; return }
  loading.value = true
  try {
    const [result, pending] = await Promise.all([
      getCardKeys(selectedId.value, filters),
      getCardKeys(selectedId.value, { mine: true, status: 'claimed', page_size: 1 })
    ])
    if (version !== requestVersion) return
    keys.value = result.items
    total.value = result.total
    pendingKey.value = pending.items[0] || null
  } catch (error) {
    if (version === requestVersion) {
      keys.value = []
      total.value = 0
      pendingKey.value = null
      historyRow.value = null
    }
    throw error
  } finally { if (version === requestVersion) loading.value = false }
}
const reloadKeys = () => { filters.page = 1; keys.value = []; total.value = 0; pendingKey.value = null; loadKeys() }
const openProject = (row) => { editing.value = !!row; Object.assign(projectForm, row ? { ...row, members: [...row.members] } : { id: null, name: '', description: '', members: [], is_active: true }); projectVisible.value = true }
const normalizeMembers = (values) => { if (values.includes('__all__')) projectForm.members = ['__all__'] }
const memberLabel = (values) => values.includes('__all__') ? '全员' : values.join('、')
const saveProject = async () => { if (!projectForm.name.trim() || !projectForm.members.length) return ElMessage.warning('请填写项目名称并选择协助成员'); saving.value = true; try { const data = { name: projectForm.name, description: projectForm.description, members: projectForm.members, is_active: projectForm.is_active }; const result = editing.value ? await updateCardKeyProject(projectForm.id, data) : await createCardKeyProject(data); projectVisible.value = false; await load(); selectedId.value = result.id; await loadKeys() } finally { saving.value = false } }
const openImport = () => { if (!selected.value) return; Object.assign(importTarget, { id: selected.value.id, name: selected.value.name }); importText.value = ''; importVisible.value = true }
const saveImport = async () => { if (!importText.value.trim()) return ElMessage.warning('请粘贴卡密内容'); importing.value = true; try { const result = await importCardKeys(importTarget.id, importText.value); ElMessage.success(`导入 ${result.added} 份，跳过重复 ${result.duplicates} 份`); importVisible.value = false; await load() } finally { importing.value = false } }
const claim = async () => {
  const projectId = selectedId.value
  claiming.value = true
  try {
    const key = await claimCardKey(projectId)
    if (selectedId.value === projectId) pendingKey.value = key
    await load()
    ElMessage.success('已领取并锁定，复制后使用，完成再确认消耗')
  } finally { claiming.value = false }
}
const copy = async (content) => {
  try { await navigator.clipboard.writeText(content); ElMessage.success('已复制') }
  catch { ElMessage.warning('浏览器不支持复制，请选择卡密手动复制') }
}
const consume = async (row) => {
  const projectId = selectedId.value
  try { await ElMessageBox.confirm('确认这份卡密已经使用？确认后不会重新分配。', '确认消耗', { type: 'warning' }) }
  catch { return }
  consuming.value = true
  try { await consumeCardKey(projectId, row.id); await load(); ElMessage.success('已确认消耗') }
  finally { consuming.value = false }
}
const release = async (row) => {
  const projectId = selectedId.value
  try { await ElMessageBox.confirm('请确认卡密尚未使用，也未提交给其他服务。归还后其他成员可以立即领取；已经使用或不确定是否使用时，请勿归还。', '归还未使用卡密', { type: 'warning', confirmButtonText: '确认未使用并归还' }) }
  catch { return }
  consuming.value = true
  try { await releaseCardKey(projectId, row.id); await load(); ElMessage.success('已归还，卡密重新可领取') }
  finally { consuming.value = false }
}
const formatDate = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'; const statusLabel = value => ({ available: '可领取', claimed: '已领取', consumed: '已消耗' }[value] || value); const statusType = value => ({ available: 'success', claimed: 'warning', consumed: 'info' }[value] || '')
onMounted(async () => { await load(); if (canManage.value) members.value = await getCardKeyMembers() })
</script>

<style scoped>
.card-key-page { max-width: 1500px; margin: 0 auto; }.page-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }.page-heading h2 { margin:0 0 6px; color:#1f2937; }.page-heading span,.hint,.muted { color:#909399; font-size:13px; }.project-card,.project-list-card { margin-bottom:16px; }.toolbar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:14px; }.project-description { color:#909399; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.claim-bar { display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-top:1px solid #ebeef5; border-bottom:1px solid #ebeef5; margin-bottom:10px; }.claim-bar span,.claim-bar small { margin-left:12px; color:#606266; }.claim-bar small { color:#909399; } code { color:#303133; word-break:break-all; white-space:pre-wrap; }
.pending-key { display:flex; align-items:center; gap:10px; padding:10px 12px; margin:10px 0; border:1px solid #d9ecff; background:#ecf5ff; border-radius:6px; }.pending-key code { flex:1; min-width:0; }.record-filters { display:flex; align-items:center; gap:12px; margin:12px 0; }.pagination { justify-content:flex-end; margin-top:12px; } @media(max-width:768px) { .claim-bar { align-items:flex-start; gap:8px; }.claim-bar small { display:block; margin:5px 0; }.pending-key { flex-wrap:wrap; }.pending-key code { flex-basis:75%; }.page-heading { gap:10px; }.project-description { flex-basis:100%; } }
</style>
