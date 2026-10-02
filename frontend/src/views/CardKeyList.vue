<template>
  <div class="card-key-page">
    <div class="page-heading">
      <div><h2>卡密管理</h2><span>按项目统一领取，避免遗漏和重复使用</span></div>
      <div class="heading-actions"><el-button v-if="canManage" @click="platformVisible = true">平台管理</el-button><el-button v-if="canManage" type="primary" @click="openProject()">＋新建项目</el-button></div>
    </div>
    <el-card shadow="never" class="project-card">
      <div class="toolbar">
        <el-select v-model="selectedId" filterable placeholder="选择项目" style="width:280px" @change="reloadKeys">
          <el-option v-for="project in projects" :key="project.id" :label="`${project.name}${project.is_active ? '' : '（已结束）'}`" :value="project.id" />
        </el-select>
        <el-tag v-if="selected" type="success">可领取 {{ selected.available }}</el-tag>
        <el-tag v-if="selected" type="info">已领取 {{ selected.claimed }}</el-tag>
        <el-tag v-if="selected">已消耗 {{ selected.consumed }}</el-tag>
        <el-tag v-if="selected?.target_platform" type="warning">邮箱平台：{{ selected.target_platform }}</el-tag>
        <span class="project-description" :title="selected?.description">{{ selected?.description }}</span>
        <el-button v-if="canManage && selected" :disabled="!selected.is_active" @click="openImport">批量导入</el-button>
        <el-button v-if="canManage && selected" @click="openProject(selected)">编辑项目</el-button><el-button v-if="canManage && selected" type="danger" plain @click="deleteProject">删除项目</el-button>
      </div>
      <el-alert v-if="selected && !selected.is_active" title="项目已结束，停止新领取，已领取卡密仍可确认消耗" type="warning" :closable="false" />
      <el-empty v-if="!selected" :description="canManage ? '先新建项目，选择协助成员并导入卡密' : '暂无分配给你的项目'" :image-size="70" />
      <div v-if="selected" class="claim-bar">
        <div><strong>当前项目</strong><span>{{ selected.name }}</span><small>协助成员：{{ memberLabel(selected.members) }}</small></div>
        <div class="project-metrics"><template v-if="selected.target_platform"><el-tag size="small" type="success">检测正常可领 {{ selected.email_normal_available }}</el-tag><el-tag size="small">可领总数 {{ selected.email_available }}</el-tag><el-tag size="small" type="info">领取中 {{ selected.email_claimed }}</el-tag><el-tag size="small">注册完成 {{ selected.emails_completed }}</el-tag></template><el-popover placement="bottom" width="360" trigger="click"><template #reference><el-button link type="primary">成员完成量</el-button></template><div v-for="stat in selected.member_stats" :key="stat.username" class="member-stat"><span>{{ stat.username }}</span><span>卡密已消耗 {{ stat.consumed }} · 待消耗 {{ stat.claimed }} · 注册 {{ stat.emails_completed }}</span></div></el-popover></div>
        <el-button type="primary" :disabled="!selected.can_claim || !selected.available || !!pendingKey" :loading="claiming" @click="claim">领取下一份</el-button>
      </div>
      <div v-if="pendingKey" class="pending-key">
        <strong>我的待消耗</strong><code>{{ pendingKey.content }}</code>
        <el-button size="small" @click="copy(pendingKey.content)">复制</el-button>
        <el-button size="small" type="primary" :loading="consuming" @click="consume(pendingKey)">确认已消耗</el-button>
        <el-button size="small" :disabled="consuming" @click="release(pendingKey)">归还未使用</el-button>
        <el-button size="small" type="danger" plain :disabled="consuming" @click="invalid(pendingKey)">报告无效</el-button>
      </div>
      <div v-if="selected" class="email-claim-bar">
        <div><strong>注册邮箱</strong><span v-if="selected.target_platform">{{ selected.target_platform }}</span><span v-else class="email-platform-empty">未设置目标平台</span><small>{{ pendingEmail ? '注册完成后标记平台并释放' : selected.target_platform ? '领取未注册该平台的闲置邮箱' : '请先设置目标平台，才能领取对应邮箱' }}</small></div>
        <div v-if="!pendingEmail"><el-button v-if="selected.target_platform" type="primary" plain :disabled="!selected.can_claim" :loading="claimingEmail" @click="claimEmailAction">领取邮箱</el-button><el-button v-else-if="canManage" type="primary" plain @click="openProject(selected)">设置目标平台</el-button><el-tag v-else type="info">等待管理员设置</el-tag></div>
        <div v-else class="email-actions"><code>{{ pendingEmail.email }}</code><el-button size="small" @click="copy(pendingEmail.email)">复制邮箱</el-button><el-button v-if="pendingEmail.password" size="small" @click="copy(pendingEmail.password)">复制密码</el-button><el-button v-if="pendingEmail.recovery_email" size="small" @click="copy(pendingEmail.recovery_email)">辅助邮箱</el-button><el-button v-if="totp" size="small" type="success" @click="copy(totp.code)">验证码 {{ totp.code }}（{{ totp.remaining }}s）</el-button><el-button v-else-if="pendingEmail.totp_secret" size="small" @click="copy(pendingEmail.totp_secret)">复制 2FA 密钥</el-button><el-button size="small" type="primary" @click="completeEmailAction">注册完成</el-button><el-button size="small" type="warning" @click="releaseEmailAction">归还</el-button></div>
      </div>
      <div v-if="selected" class="record-filters">
        <strong>{{ canManage ? '卡密记录' : '我的领取记录' }}</strong>
        <el-select v-model="filters.status" clearable placeholder="全部状态" style="width:125px" @change="reloadKeys"><el-option label="可领取" value="available" v-if="canManage" /><el-option label="待消耗" value="claimed" /><el-option label="已消耗" value="consumed" /><el-option label="无效售后" value="invalid" /></el-select>
        <el-checkbox v-if="canManage" v-model="filters.mine" @change="reloadKeys">只看我的</el-checkbox>
        <el-input v-model="filters.keyword" clearable placeholder="搜索卡密 / 链接" style="width:220px" @keyup.enter="reloadKeys" @clear="reloadKeys" /><el-button link type="primary" @click="reloadKeys">搜索</el-button><el-button link type="primary" @click="load">刷新</el-button>
      </div>
      <el-table v-if="selected" v-loading="loading" :data="keys" size="small" empty-text="暂无记录，领取后在这里找回">
        <el-table-column label="卡密 / 链接" min-width="420"><template #default="{ row }"><code v-if="row.content">{{ row.content }}</code><span v-else class="muted">领取后可见</span></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag><div v-if="row.remark" class="key-remark" :title="row.remark">{{ row.remark }}</div></template></el-table-column>
        <el-table-column label="领取人" prop="claimed_by" width="130" />
        <el-table-column label="领取时间" width="180"><template #default="{ row }">{{ formatDate(row.claimed_at) }}</template></el-table-column>
        <el-table-column label="消耗时间" width="180"><template #default="{ row }">{{ formatDate(row.consumed_at) }}</template></el-table-column>
        <el-table-column label="操作" width="235" fixed="right"><template #default="{ row }"><span v-if="row.id === pendingKey?.id" class="muted">上方操作</span><template v-else><el-button v-if="row.content" link type="primary" @click="copy(row.content)">复制</el-button><el-button v-if="canManage && row.status === 'available'" link type="danger" @click="invalid(row)">标记无效</el-button><template v-if="row.status === 'claimed' && (row.claimed_by === username || canManage)"><el-button :disabled="consuming" link type="primary" @click="consume(row)">确认消耗</el-button><el-button :disabled="consuming" link type="warning" @click="release(row)">归还</el-button></template></template><el-button v-if="canManage || row.claimed_by === username" link @click="editKeyRemark(row)">备注</el-button><el-button v-if="row.history?.length" link @click="historyRow = row">记录</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-if="total" class="pagination" v-model:current-page="filters.page" :page-size="filters.page_size" :total="total" layout="total, prev, pager, next" @current-change="loadKeys" />
    </el-card>
    <el-dialog :model-value="!!historyRow" title="卡密流转记录" width="min(800px, 94vw)" @close="historyRow = null">
      <el-table :data="historyRow?.history || []" size="small"><el-table-column label="操作" width="85"><template #default="{ row }">{{ { claim: '领取', release: '归还', consume: '消耗', invalid: '无效售后', remark: '更新备注' }[row.action] }}</template></el-table-column><el-table-column prop="username" label="操作人" /><el-table-column label="时间" width="190"><template #default="{ row }">{{ formatDate(row.time) }}</template></el-table-column><el-table-column prop="remark" label="备注" min-width="180" /></el-table>
    </el-dialog>
    <CardKeyWorkReport v-if="canManage && selected" :project-id="selected.id" :project-name="selected.name" />
    <el-dialog v-model="projectVisible" :title="editing ? '编辑项目' : '新建项目'" width="min(600px, 94vw)">
      <el-form label-width="90px"><el-form-item label="项目名称" required><el-input v-model="projectForm.name" /></el-form-item><el-form-item label="项目备注"><el-input v-model="projectForm.description" type="textarea" :rows="3" placeholder="任务说明、上游联系方式、采购批次与售后说明" /></el-form-item><el-form-item label="目标平台"><el-select v-model="projectForm.target_platform" filterable clearable placeholder="选择目标平台" style="width:100%"><el-option v-for="platform in activePlatforms" :key="platform.id" :label="platform.name" :value="platform.name" /></el-select><div class="form-hint">没有合适的平台？关闭此窗口后点击“平台管理”创建。</div></el-form-item><el-form-item label="协助成员" required><el-select v-model="projectForm.members" multiple filterable style="width:100%" @change="normalizeMembers"><el-option label="全员" value="__all__" /><el-option v-for="member in members" :key="member.username" :label="member.real_name ? `${member.username}（${member.real_name}）` : member.username" :value="member.username" /></el-select></el-form-item><el-form-item label="项目状态"><el-switch v-model="projectForm.is_active" active-text="进行中" inactive-text="已结束" /></el-form-item></el-form>
      <template #footer><el-button @click="projectVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProject">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="platformVisible" title="平台管理" width="min(620px, 94vw)">
      <div class="platform-create"><el-input v-model="platformDraft.name" placeholder="例如 TikTok" @keyup.enter="savePlatform" /><el-button type="primary" :loading="platformSaving" @click="savePlatform">{{ platformDraft.id ? '保存修改' : '新增平台' }}</el-button><el-button v-if="platformDraft.id" @click="resetPlatformDraft">取消编辑</el-button></div>
      <el-table :data="platforms" size="small" empty-text="还没有平台配置"><el-table-column prop="name" label="平台" /><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column label="操作" width="180"><template #default="{ row }"><el-button link type="primary" @click="editPlatform(row)">编辑</el-button><el-button link :type="row.is_active ? 'warning' : 'success'" @click="togglePlatform(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template></el-table-column></el-table>
      <template #footer><el-button @click="platformVisible=false">关闭</el-button></template>
    </el-dialog>
    <el-dialog v-model="completeVisible" title="注册完成并创建运营账号" width="min(520px, 94vw)"><el-form label-width="100px"><el-form-item label="注册邮箱"><span>{{ pendingEmail?.email }}</span></el-form-item><el-form-item label="平台账号" required><el-input v-model="completeForm.account" placeholder="填写刚注册的平台用户名" /></el-form-item><el-form-item label="账号密码"><el-input v-model="completeForm.password" type="password" show-password /></el-form-item><el-form-item label="账号 2FA"><el-input v-model="completeForm.totp_secret" placeholder="没有可留空" /></el-form-item><p class="form-hint">确认后自动创建运营账号、关联当前邮箱、添加平台标签并释放邮箱。</p></el-form><template #footer><el-button @click="completeVisible=false">取消</el-button><el-button type="primary" :loading="completing" @click="submitCompleteEmail">确认完成</el-button></template></el-dialog>
    <el-dialog v-model="importVisible" title="批量导入卡密" width="min(620px, 94vw)"><p>导入项目：<strong>{{ importTarget.name }}</strong></p><p class="hint">一行一份，支持字符串或链接；重复内容会自动跳过。</p><el-input v-model="importText" type="textarea" :rows="12" placeholder="每行粘贴一份卡密或链接" /><template #footer><el-button @click="importVisible=false">取消</el-button><el-button type="primary" :loading="importing" @click="saveImport">导入</el-button></template></el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import CardKeyWorkReport from '@/components/CardKeyWorkReport.vue'
import { updateCardKeyRemark } from '@/api/card_keys'
import { getCardKeyProjects, getCardKeyMembers, createCardKeyProject, updateCardKeyProject, deleteCardKeyProject, importCardKeys, getCardKeys, claimCardKey, consumeCardKey, releaseCardKey, markCardKeyInvalid, getClaimedEmail, getClaimedEmailTotp, claimEmail, releaseEmail, completeEmail, getCardKeyPlatforms, createCardKeyPlatform, updateCardKeyPlatform } from '@/api/card_keys'
const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('card_key:manage'))
const username = computed(() => auth.user?.username)
const projects = ref([]); const members = ref([]); const keys = ref([]); const selectedId = ref(null); const loading = ref(false); const claiming = ref(false); const saving = ref(false); const importing = ref(false); const projectVisible = ref(false); const importVisible = ref(false); const editing = ref(false); const importText = ref('')
const projectForm = reactive({ id: null, name: '', description: '', target_platform: '', members: [], is_active: true }); const selected = computed(() => projects.value.find(x => x.id === selectedId.value))
const filters = reactive({ page: 1, page_size: 30, status: '', mine: false, keyword: '' })
const total = ref(0)
const pendingKey = ref(null)
const pendingEmail = ref(null)
const totp = ref(null)
let totpTimer = null
const claimingEmail = ref(false)
const platforms = ref([]); const platformVisible = ref(false); const platformSaving = ref(false); const platformDraft = reactive({ id: null, name: '' })
const completeVisible = ref(false); const completing = ref(false); const completeForm = reactive({ account: '', password: '', totp_secret: '' })
const completeTarget = reactive({ id: null, platform: '' })
const activePlatforms = computed(() => platforms.value.filter(platform => platform.is_active))
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
  pendingEmail.value = null
  historyRow.value = null
  filters.page = 1
}
const load = async () => {
  const version = ++projectRequestVersion
  try {
    const [result, platformResult] = await Promise.all([getCardKeyProjects(), getCardKeyPlatforms()])
    if (version !== projectRequestVersion) return
    projects.value = result
    platforms.value = platformResult
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
  if (!selectedId.value) { keys.value = []; total.value = 0; pendingKey.value = null; pendingEmail.value = null; loading.value = false; return }
  loading.value = true
  try {
    const [result, pending, email] = await Promise.all([
      getCardKeys(selectedId.value, filters),
      getCardKeys(selectedId.value, { mine: true, status: 'claimed', page_size: 1 }),
      selected.value?.target_platform ? getClaimedEmail(selectedId.value) : Promise.resolve(null)
    ])
    if (version !== requestVersion) return
    keys.value = result.items
    total.value = result.total
    pendingKey.value = pending.items[0] || null
    pendingEmail.value = email
    await refreshTotp()
  } catch (error) {
    if (version === requestVersion) {
      keys.value = []
      total.value = 0
      pendingKey.value = null
      pendingEmail.value = null
      historyRow.value = null
    }
    throw error
  } finally { if (version === requestVersion) loading.value = false }
}
const refreshTotp = async () => {
  const projectId = selectedId.value
  const emailId = pendingEmail.value?.id
  totp.value = null
  if (!projectId || !pendingEmail.value?.totp_secret) return
  try { const result = await getClaimedEmailTotp(projectId); if (selectedId.value === projectId && pendingEmail.value?.id === emailId) totp.value = { ...result, expiresAt: Date.now() + result.remaining * 1000 } }
  catch { if (selectedId.value === projectId && pendingEmail.value?.id === emailId) totp.value = null }
}
const reloadKeys = () => { filters.page = 1; keys.value = []; total.value = 0; pendingKey.value = null; pendingEmail.value = null; totp.value = null; loadKeys() }
const openProject = (row) => { editing.value = !!row; Object.assign(projectForm, row ? { ...row, members: [...row.members] } : { id: null, name: '', description: '', target_platform: '', members: [], is_active: true }); projectVisible.value = true }
const normalizeMembers = (values) => { if (values.includes('__all__')) projectForm.members = ['__all__'] }
const memberLabel = (values) => values.includes('__all__') ? '全员' : values.join('、')
const saveProject = async () => { if (!projectForm.name.trim() || !projectForm.members.length) return ElMessage.warning('请填写项目名称并选择协助成员'); saving.value = true; try { const data = { name: projectForm.name, description: projectForm.description, target_platform: projectForm.target_platform, members: projectForm.members, is_active: projectForm.is_active }; const result = editing.value ? await updateCardKeyProject(projectForm.id, data) : await createCardKeyProject(data); projectVisible.value = false; await load(); selectedId.value = result.id; await loadKeys() } finally { saving.value = false } }
const deleteProject = async () => { if (!selected.value) return; try { await ElMessageBox.confirm(`确认删除项目“${selected.value.name}”？项目卡密记录也会删除，已有完成记录的项目不能删除。`, '删除项目', { type: 'warning', confirmButtonText: '确认删除' }) } catch { return }; await deleteCardKeyProject(selected.value.id); selectedId.value = null; await load(); ElMessage.success('项目已删除') }
const claimEmailAction = async () => {
  const projectId = selectedId.value
  claimingEmail.value = true
  try { const email = await claimEmail(projectId); if (selectedId.value === projectId) { pendingEmail.value = email; await refreshTotp() }; ElMessage.success('已锁定邮箱，请注册完成后释放') }
  finally { claimingEmail.value = false }
}
const resetPlatformDraft = () => Object.assign(platformDraft, { id: null, name: '' })
const editPlatform = (row) => Object.assign(platformDraft, { id: row.id, name: row.name })
const savePlatform = async () => {
  if (!platformDraft.name.trim()) return ElMessage.warning('请填写平台名称')
  platformSaving.value = true
  try { const data = { name: platformDraft.name, is_active: true }; if (platformDraft.id) await updateCardKeyPlatform(platformDraft.id, data); else await createCardKeyPlatform(data); await load(); resetPlatformDraft(); ElMessage.success('平台已保存') }
  finally { platformSaving.value = false }
}
const togglePlatform = async (row) => { await updateCardKeyPlatform(row.id, { name: row.name, is_active: !row.is_active }); await load(); ElMessage.success(row.is_active ? '平台已停用' : '平台已启用') }
const releaseEmailAction = async () => {
  const projectId = selectedId.value
  try { await ElMessageBox.confirm('确认尚未注册该平台？已注册请使用“注册完成”，避免重复分配。', '归还邮箱', { type: 'warning' }) } catch { return }
  await releaseEmail(projectId); await load(); ElMessage.success('邮箱已归还，未添加平台标签')
}
const completeEmailAction = async () => {
  const projectId = selectedId.value
  const platform = selected.value.target_platform
  if (!['tiktok', 'youtube', 'instagram', 'facebook'].includes(platform.toLowerCase())) {
    try { await ElMessageBox.confirm('确认已注册完成？将添加平台标签并释放邮箱。', '注册完成', { type: 'warning' }) } catch { return }
    await completeEmail(projectId, { platform }); await load(); ElMessage.success('已标记注册完成并释放邮箱'); return
  }
  if (!auth.hasPermission('op_account:create')) return ElMessage.warning('请联系管理员授予创建运营账号权限')
  Object.assign(completeTarget, { id: projectId, platform })
  Object.assign(completeForm, { account: '', password: '', totp_secret: '' }); completeVisible.value = true
}
const submitCompleteEmail = async () => { if (!completeForm.account.trim()) return ElMessage.warning('请填写平台账号'); completing.value = true; try { const result = await completeEmail(completeTarget.id, { platform: completeTarget.platform, ...completeForm }); completeVisible.value = false; await load(); ElMessage.success(`已创建运营账号 ${result.op_account}，邮箱已关联并释放`) } finally { completing.value = false } }
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
const invalid = async (row) => { let value; try { ({ value } = await ElMessageBox.prompt('填写无效原因或上游售后信息', '标记卡密无效', { inputPlaceholder: '例如：兑换失败，已提交供应商售后', inputValidator: value => value?.trim() ? true : '请填写原因', confirmButtonText: '确认标记' })) } catch { return }; await markCardKeyInvalid(selectedId.value, row.id, value); await load(); ElMessage.success('已标记无效') }
const editKeyRemark = async (row) => {
  let value
  try { ({ value } = await ElMessageBox.prompt('记录供应商售后进度、补发情况或其他备注；修改历史会保留。', '卡密备注', { inputValue: row.remark || '', inputType: 'textarea', inputValidator: value => (value || '').length <= 2000 || '备注最多 2000 字' })) } catch { return }
  await updateCardKeyRemark(selectedId.value, row.id, value || ''); await load(); ElMessage.success('备注已保存')
}
const formatDate = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'; const statusLabel = value => ({ available: '可领取', claimed: '已领取', consumed: '已消耗', invalid: '无效售后' }[value] || value); const statusType = value => ({ available: 'success', claimed: 'warning', consumed: 'info', invalid: 'danger' }[value] || '')
onMounted(async () => {
  totpTimer = window.setInterval(() => {
    if (!pendingEmail.value) { totp.value = null; return }
    if (!totp.value) return
    totp.value.remaining = Math.max(0, Math.ceil((totp.value.expiresAt - Date.now()) / 1000))
    if (!totp.value.remaining) refreshTotp()
  }, 1000)
  await load()
  if (canManage.value) members.value = await getCardKeyMembers()
})
onBeforeUnmount(() => { if (totpTimer) window.clearInterval(totpTimer) })
</script>

<style scoped>
.email-claim-bar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:12px; margin:12px 0; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; }
.email-claim-bar span,.email-claim-bar small { margin-left:10px; color:#64748b; }
.email-claim-bar .email-platform-empty { color:#e6a23c; }
.email-actions { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
.email-actions .el-button { margin-left:0; }
.project-metrics { display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-left:auto; }
.member-stat { display:flex; justify-content:space-between; gap:18px; padding:5px 0; border-bottom:1px solid #ebeef5; color:#606266; font-size:13px; }
.key-remark { max-width:90px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#909399; font-size:12px; }
.heading-actions { display:flex; gap:8px; }
.platform-create { display:flex; gap:8px; margin-bottom:14px; }
.platform-create .el-input { flex:1; }
.form-hint { color:#909399; font-size:12px; line-height:1.5; margin-top:5px; }
.card-key-page { max-width: 1500px; margin: 0 auto; }.page-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }.page-heading h2 { margin:0 0 6px; color:#1f2937; }.page-heading span,.hint,.muted { color:#909399; font-size:13px; }.project-card,.project-list-card { margin-bottom:16px; }.toolbar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:14px; }.project-description { color:#909399; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }.claim-bar { display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-top:1px solid #ebeef5; border-bottom:1px solid #ebeef5; margin-bottom:10px; }.claim-bar span,.claim-bar small { margin-left:12px; color:#606266; }.claim-bar small { color:#909399; } code { color:#303133; word-break:break-all; white-space:pre-wrap; }
.pending-key { display:flex; align-items:center; gap:10px; padding:10px 12px; margin:10px 0; border:1px solid #d9ecff; background:#ecf5ff; border-radius:6px; }.pending-key code { flex:1; min-width:0; }.record-filters { display:flex; align-items:center; gap:12px; margin:12px 0; }.pagination { justify-content:flex-end; margin-top:12px; } @media(max-width:768px) { .claim-bar { align-items:flex-start; gap:8px; }.claim-bar small { display:block; margin:5px 0; }.pending-key { flex-wrap:wrap; }.pending-key code { flex-basis:75%; }.page-heading { gap:10px; }.project-description { flex-basis:100%; } }
</style>
