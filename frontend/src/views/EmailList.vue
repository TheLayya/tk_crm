<template>
  <div class="email-page">
    <div class="page-heading">
      <div>
        <h2>邮箱管理</h2>
        <span>可复用邮箱资源 · 当前关联和累计关联分开查看</span>
      </div>
      <div class="heading-actions">
        <el-button v-if="canCheck && selected.length" :loading="checking" @click="checkSelected">检测选中 {{ selected.length }}</el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">新增邮箱</el-button>
        <el-button v-if="canImport" @click="importVisible = true">批量导入</el-button>
      </div>
    </div>

    <el-card class="filter-card" shadow="never">
      <div class="filters">
        <el-select v-model="filters.platform" clearable filterable placeholder="已注册平台标签" @change="page = 1; load()"><el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.name" /></el-select>
        <el-input v-model="filters.keyword" clearable placeholder="搜索邮箱/辅助邮箱" @keyup.enter="load" @clear="load" />
        <el-select v-model="filters.management_status" clearable placeholder="使用状态" @change="load">
          <el-option v-for="status in statuses" :key="status" :label="status" :value="status" />
        </el-select>
        <el-button type="primary" plain @click="load">搜索</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table ref="tableRef" v-loading="loading" :data="items" row-key="id" stripe @expand-change="handleExpand" @selection-change="selected = $event">
        <el-table-column type="selection" width="40" />
        <el-table-column type="expand" width="42">
          <template #default="{ row }">
            <div class="email-expanded">
              <div class="detail-grid">
                <span><b>邮箱密码</b><el-button link @click="row.showPassword = !row.showPassword">{{ row.showPassword ? row.password : mask(row.password) }}</el-button></span>
                <span><b>辅助邮箱</b>{{ row.recovery_email || '—' }}</span>
                <span><b>2FA</b><el-button link @click="row.showTotp = !row.showTotp">{{ row.showTotp ? row.totp_secret : mask(row.totp_secret) }}</el-button></span>
                <span><b>注册</b>{{ row.account_created_at || row.account_created_year || '—' }}</span>
                <span><b>检测</b>{{ row.gmail_check_status || '未检测' }}</span>
                <span><b>添加人</b>{{ row.registrant || '—' }}</span>
                <span><b>使用人</b>{{ row.operator || '—' }}</span>
                <span><b>采购</b>{{ row.purchase_channel || '—' }} · {{ money(row.purchase_price) }} · {{ row.purchase_date || '—' }}</span>
                <span><b>出售</b>{{ row.sale_customer || '—' }} · {{ money(row.sale_price) }} · {{ row.sale_date || '—' }}</span>
                <span><b>出售人</b>{{ row.sellers?.join(' / ') || '—' }}</span>
                <span><b>手机</b>{{ row.device_name || '未绑定' }}</span>
                <span><b>节点</b>{{ row.node_ip || '未绑定' }}</span>
              </div>
              <details v-if="row.assetHistory?.length"><summary>手机 / 节点关联轨迹（{{ row.assetHistory.length }}）</summary><div v-for="entry in row.assetHistory" :key="entry.id" class="relation-item"><b>{{ entry.kind }} · {{ entry.name }}</b><el-tag size="small" :type="entry.unbound_at ? 'info' : 'success'">{{ entry.unbound_at ? '历史关联' : '当前关联' }}</el-tag><span>{{ formatDate(entry.bound_at) }}{{ entry.unbound_at ? ` → ${formatDate(entry.unbound_at)}` : '' }}</span><span>{{ entry.operator }}</span></div></details>
              <div class="relation-heading">
                <b>关联轨迹</b><span>累计 {{ row.relations?.length || 0 }} 次</span>
                <el-button v-if="canLink" size="small" type="primary" plain @click="openBind(row)">关联账号</el-button>
              </div>
              <el-empty v-if="!row.relations?.length" description="暂无关联记录" :image-size="42" />
              <div v-else class="relation-list">
                <div v-for="relation in row.relations" :key="relation.id" class="relation-item">
                  <span class="relation-main">{{ relation.platform?.toUpperCase() }} · {{ relation.account }}</span>
                  <el-tag size="small" :type="relation.unbound_at ? 'info' : 'success'">{{ relation.unbound_at ? '已解绑' : '当前关联' }}</el-tag>
                  <span class="relation-time">{{ formatDate(relation.bound_at) }}{{ relation.unbound_at ? ` → ${formatDate(relation.unbound_at)}` : '' }}</span>
                  <span class="relation-time">{{ relation.operator }}{{ relation.unbound_by ? ` / 解绑：${relation.unbound_by}` : '' }}</span>
                  <el-button v-if="canLink && !relation.unbound_at" link type="danger" @click="unbind(row, relation)">解绑</el-button>
                </div>
              </div>
              <div v-if="row.remark" class="remark">备注：{{ row.remark }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="250">
          <template #default="{ row }"><el-button class="email-name" link @click="tableRef.toggleRowExpansion(row)">{{ row.email }}</el-button></template>
        </el-table-column>
        <el-table-column prop="country" label="国家" width="110" />
        <el-table-column label="平台注册 / 领取" min-width="190"><template #default="{ row }"><el-tag v-for="tag in row.platform_tags" :key="tag" size="small" style="margin:2px">{{ tag }}</el-tag><span v-if="!row.platform_tags?.length">未标记</span><div v-if="row.claimed_by" class="remark">{{ row.claimed_by }} 正在注册 {{ row.claimed_platform }}</div></template></el-table-column>
        <el-table-column label="检测状态" width="120">
          <template #default="{ row }"><el-tag size="small" :type="checkTag(row.gmail_check_status)">{{ row.gmail_check_status || '未检测' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="当前关联" width="110" align="center">
          <template #default="{ row }"><span class="count">{{ row.current_relation_count }}</span> 个账号</template>
        </el-table-column>
        <el-table-column label="使用状态" width="110">
          <template #default="{ row }"><el-tag size="small" :type="statusTag(row.management_status)">{{ row.management_status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="最后检测" width="165"><template #default="{ row }">{{ formatDate(row.gmail_checked_at) }}</template></el-table-column>
        <el-table-column prop="device_name" label="绑定手机" width="110" />
        <el-table-column prop="node_ip" label="绑定节点" width="170" />
        <el-table-column label="采购 / 出售" width="180"><template #default="{ row }"><div>{{ row.purchase_channel || '未登记采购' }} · {{ money(row.purchase_price) }}</div><div>{{ row.sale_customer || '未登记出售' }} · {{ money(row.sale_price) }}</div></template></el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canCheck && row.email.endsWith('@gmail.com')" :disabled="checking" link type="primary" @click="check(row)">检测</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage && !row.current_relation_count" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager"><span>共 {{ total }} 条</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" layout="prev, pager, next" :total="total" @current-change="load" /></div>
    </el-card>

    <el-dialog v-model="formVisible" :title="editing ? '编辑邮箱' : '新增邮箱'" width="760px" top="5vh">
      <el-form label-width="100px">
        <el-form-item label="邮箱" required><el-input v-model="form.email" :disabled="editing" /></el-form-item>
        <el-form-item label="邮箱密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="辅助邮箱"><el-input v-model="form.recovery_email" /></el-form-item>
        <el-form-item label="2FA 密钥"><el-input v-model="form.totp_secret" type="password" show-password /></el-form-item>
        <el-form-item label="注册时间"><el-input v-model="form.account_created_at" placeholder="YYYY-MM-DD 或 YYYY-MM-DD HH:mm:ss，也可只填年份" /></el-form-item>
        <el-form-item label="国家"><el-input v-model="form.country" /></el-form-item>
        <el-form-item label="使用状态"><el-select v-model="form.management_status"><el-option v-for="status in statuses" :key="status" :label="status" :value="status" /></el-select></el-form-item>
        <el-form-item label="已注册平台"><el-select v-model="form.platform_tags" multiple filterable placeholder="选择已注册的平台" style="width:100%"><el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.name" /></el-select></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="绑定手机"><el-select v-model="form.device_id" filterable clearable @visible-change="loadAssetOptions"><el-option v-for="device in devices" :key="device.id" :label="device.name" :value="device.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="绑定节点"><el-select v-model="form.node_id" filterable clearable @visible-change="loadAssetOptions"><el-option v-for="node in nodes" :key="node.id" :label="`${node.ip}:${node.port}`" :value="node.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购渠道" :required="!editing"><el-input v-model="form.purchase_channel" placeholder="例如：供应商、自注册" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购成本" :required="!editing"><el-input-number v-model="form.purchase_price" :min="0" :precision="2" placeholder="免费来源请填 0" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购日期"><el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <template v-if="form.management_status === '已出售'">
            <el-col :span="12"><el-form-item label="出售客户" required><el-input v-model="form.sale_customer" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="出售金额" required><el-input-number v-model="form.sale_price" :min="0" :precision="2" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="出售日期" required><el-date-picker v-model="form.sale_date" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="出售人" required><SellerSelector v-model="form.sellers" /></el-form-item></el-col>
          </template>
          <el-col :span="12"><el-form-item label="使用人"><SellerSelector v-model="form.operator" :multiple="false" placeholder="选择使用人" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="formVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="批量导入邮箱" width="620px">
      <el-upload :auto-upload="false" :show-file-list="false" accept=".txt" :on-change="readImportFile"><el-button size="small">读取 TXT 文件</el-button></el-upload>
      <el-input v-model="importText" type="textarea" :rows="8" placeholder="邮箱|邮箱密码|辅助邮箱|2FA|注册时间|国家&#10;同时支持 |、----、: 分隔；注册时间可只填年份" />
      <el-row :gutter="12" class="import-trade-fields">
        <el-col :span="12"><el-form-item label="采购渠道" required><el-input v-model="importPurchaseChannel" placeholder="例如：供应商" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="采购成本（每个）" required><el-input-number v-model="importPurchasePrice" :min="0" :precision="2" placeholder="单个邮箱成本" controls-position="right" style="width:100%" /></el-form-item></el-col>
      </el-row>
      <div class="import-tip">采购渠道和单个邮箱成本必填，会应用到整批邮箱；免费来源请明确填写 0。每行自动识别 |、---- 或 :，支持四项或六项，注册时间可只填年份。导入后可自动进行邮箱状态检测。</div>
      <div v-if="importResult" class="import-result">成功 {{ importResult.success }} · 重复 {{ importResult.duplicates }} · 失败 {{ importResult.failed }}{{ checkingImport ? ' · 正在检测新 Gmail…' : (importCheckResult ? ` · 已检测 ${importCheckResult.checked} 个` : '') }}</div>
      <div v-for="result in importResult?.rows?.filter(row => row._result === 'failed') || []" :key="result.line" class="import-result">第 {{ result.line }} 行：{{ result._reason }}</div>
      <template #footer><el-button @click="importVisible = false">取消</el-button><el-button type="primary" :loading="importing" @click="importData">导入</el-button></template>
    </el-dialog>

    <el-dialog v-model="bindVisible" title="关联运营账号" width="520px">
      <el-select v-model="bindAccountId" filterable remote clearable placeholder="搜索运营账号" :remote-method="searchAccounts" style="width:100%">
        <el-option v-for="account in accountOptions" :key="account.id" :label="account.label" :value="account.id" />
      </el-select>
      <el-input v-model="bindRemark" placeholder="关联备注（可选）" style="margin-top:14px" />
      <template #footer><el-button @click="bindVisible = false">取消</el-button><el-button type="primary" :loading="binding" @click="bind">确认关联</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listEmails, createEmail, updateEmail, deleteEmail, importEmails, checkEmails, getEmailRelations, getEmailAccountOptions, bindEmailAccount, unbindEmailAccount, getEmailPlatforms } from '@/api/emails'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'
import { getDevices } from '@/api/devices'
import { getProxyNodes } from '@/api/proxy_nodes'
import SellerSelector from '@/components/SellerSelector.vue'

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('email:manage'))
const canImport = computed(() => auth.hasPermission('email:import'))
const canCheck = computed(() => auth.hasPermission('email:check'))
const canLink = computed(() => canManage.value && auth.hasPermission('op_account:edit') && auth.hasPermission('op_account:view'))
const selected = ref([])
const checking = ref(false)
const tableRef = ref(null)
const statuses = ['闲置', '使用中', '锁定', '已出售', '废弃']
const platforms = ref([])
const devices = ref([])
const nodes = ref([])
const tradeDefaults = () => ({ device_id: null, node_id: null, purchase_channel: '', purchase_price: null, purchase_date: null, sale_customer: '', sale_price: null, sale_date: null, sellers: [], operator: '' })
const money = (value) => value == null ? '—' : `¥${Number(value).toFixed(2)}`
const loadAssetOptions = async (visible) => {
  if (!visible) return
  if (auth.hasPermission('device:view')) devices.value = (await getDevices({ limit: 200, device_type: 'phone' })).items
  if (auth.hasPermission('proxy_node:view')) nodes.value = (await getProxyNodes({ limit: 500 })).items.filter(node => ['idle', 'active'].includes(node.status))
}
const filters = reactive({ keyword: '', management_status: '', platform: '' })
const items = ref([]); const total = ref(0); const page = ref(1); const pageSize = ref(50); const loading = ref(false)
const formVisible = ref(false); const editing = ref(false); const saving = ref(false)
const form = reactive({ email: '', password: '', recovery_email: '', totp_secret: '', account_created_at: '', account_created_year: null, country: '', management_status: '闲置', platform_tags: [], remark: '' })
const importVisible = ref(false); const importText = ref(''); const importPurchaseChannel = ref(''); const importPurchasePrice = ref(null); const importResult = ref(null); const importing = ref(false); const checkingImport = ref(false); const importCheckResult = ref(null)
const bindVisible = ref(false); const binding = ref(false); const bindEmail = ref(null); const bindAccountId = ref(null); const bindRemark = ref(''); const accountOptions = ref([])

const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
const mask = (value) => value ? '••••••' : '—'
const statusTag = (value) => ({ '使用中': 'success', '已出售': 'warning', '锁定': 'warning', '废弃': 'danger' }[value] || 'info')
const checkTag = (value) => ({ 正常: 'success', 封禁: 'danger', 验证: 'warning', 未注册: 'info' }[value] || 'info')
const load = async () => { loading.value = true; try { const data = await listEmails({ ...filters, skip: (page.value - 1) * pageSize.value, limit: pageSize.value }); items.value = data.items; total.value = data.total } finally { loading.value = false } }
const handleExpand = async (row, expanded) => { if (expanded.some(item => item.id === row.id)) { row.relations = await getEmailRelations(row.id); row.assetHistory = await request.get(`/emails/${row.id}/asset-history`) } }
const resetForm = () => Object.assign(form, { email: '', password: '', recovery_email: '', totp_secret: '', account_created_at: '', account_created_year: null, country: '', management_status: '闲置', platform_tags: [], remark: '' })
const openCreate = () => { editing.value = false; resetForm(); Object.assign(form, tradeDefaults()); formVisible.value = true }
const openEdit = (row) => { editing.value = true; resetForm(); Object.assign(form, tradeDefaults(), row, { password: '', totp_secret: '', account_created_at: row.account_created_at || String(row.account_created_year || '') }); formVisible.value = true }
const save = async () => {
  if (!editing.value && !form.purchase_channel?.trim()) return ElMessage.warning('请填写采购渠道')
  if (!editing.value && (form.purchase_price == null || !Number.isFinite(form.purchase_price) || form.purchase_price < 0)) return ElMessage.warning('请填写有效的采购成本，免费来源请填 0')
  if (form.management_status === '已出售') {
    if (!form.sale_customer?.trim()) return ElMessage.warning('请填写出售客户')
    if (form.sale_price == null || !Number.isFinite(form.sale_price) || form.sale_price < 0) return ElMessage.warning('请填写有效的出售金额')
    if (!form.sale_date) return ElMessage.warning('请填写出售日期')
    if (!form.sellers?.length) return ElMessage.warning('请填写出售人')
  }
  saving.value = true
  try {
    const data = Object.fromEntries(['email', 'password', 'recovery_email', 'totp_secret', 'country', 'management_status', 'platform_tags', 'remark'].map(field => [field, form[field]]))
    for (const field of Object.keys(tradeDefaults())) data[field] = form[field] ?? null
    data.device_id = form.device_id || null
    data.node_id = form.node_id || null
    if (editing.value) { if (!data.password) delete data.password; if (!data.totp_secret) delete data.totp_secret }
    const registered = String(form.account_created_at || '').trim()
    data.account_created_at = /^\d{4}$/.test(registered) || !registered ? null : registered
    data.account_created_year = /^\d{4}$/.test(registered) ? Number(registered) : null
    if (editing.value) await updateEmail(form.id, data); else await createEmail(data)
    ElMessage.success('已保存'); formVisible.value = false; await load()
  } finally { saving.value = false }
}
const importData = async () => {
  if (!importText.value.trim()) return ElMessage.warning('请输入邮箱内容')
  if (!importPurchaseChannel.value.trim()) return ElMessage.warning('请填写采购渠道')
  if (importPurchasePrice.value == null || importPurchasePrice.value < 0) return ElMessage.warning('请填写采购成本')
  importing.value = true
  importCheckResult.value = null
  try {
    importResult.value = await importEmails(importText.value, { purchase_channel: importPurchaseChannel.value.trim(), purchase_price: importPurchasePrice.value })
    const ids = (importResult.value.rows || []).filter(row => row._result === 'success' && row._id && row.email?.toLowerCase().endsWith('@gmail.com')).map(row => row._id)
    if (ids.length && canCheck.value) {
      checkingImport.value = true
      let checked = 0
      for (let index = 0; index < ids.length; index += 50) {
        const result = await checkEmails(ids.slice(index, index + 50))
        checked += result.checked || ids.slice(index, index + 50).length
      }
      importCheckResult.value = { checked }
      ElMessage.success(`导入完成，已自动检测 ${checked} 个 Gmail`)
    } else {
      ElMessage.success(ids.length ? '导入完成' : '导入完成，没有可检测的 Gmail')
    }
    await load()
  } catch (error) {
    if (importResult.value?.success) ElMessage.warning('邮箱已导入，但自动检测失败，可稍后手动检测')
    throw error
  } finally { importing.value = false; checkingImport.value = false }
}
const readImportFile = async (file) => { importText.value = await file.raw.text(); importResult.value = null }
const checkSelected = () => checkRows(selected.value)
const check = (row) => checkRows([row])
const checkRows = async (rows) => {
  if (rows.length > 50 || rows.some(row => !row.email.endsWith('@gmail.com'))) return ElMessage.warning('每次请选择 1-50 个 Gmail 邮箱')
  try { await ElMessageBox.confirm('检测仅用于判断邮箱状态，不会发送密码或 2FA。结果来自第三方探测，不代表邮箱一定可以登录。是否继续？', '邮箱状态检测', { type: 'warning' }) } catch { return }
  checking.value = true
  try { await checkEmails(rows.map(row => row.id)); ElMessage.success('检测完成'); await load() }
  finally { checking.value = false }
}
const remove = async (row) => { await ElMessageBox.confirm(`确认删除 ${row.email}？`, '删除邮箱', { type: 'warning' }); await deleteEmail(row.id); ElMessage.success('已删除'); await load() }
const openBind = async (row) => { bindEmail.value = row; bindAccountId.value = null; bindRemark.value = ''; accountOptions.value = await getEmailAccountOptions(); bindVisible.value = true }
const searchAccounts = async (keyword) => { accountOptions.value = await getEmailAccountOptions(keyword) }
const bind = async () => { if (!bindAccountId.value) return ElMessage.warning('请选择运营账号'); binding.value = true; try { await bindEmailAccount(bindEmail.value.id, { op_account_id: bindAccountId.value, remark: bindRemark.value }); bindEmail.value.relations = await getEmailRelations(bindEmail.value.id); bindVisible.value = false; await load(); ElMessage.success('已关联') } finally { binding.value = false } }
const unbind = async (row, relation) => { await ElMessageBox.confirm(`确认解绑 ${relation.account}？历史记录会保留。`, '解除关联', { type: 'warning' }); await unbindEmailAccount(row.id, relation.id); row.relations = await getEmailRelations(row.id); await load(); ElMessage.success('已解绑') }
onMounted(async () => { platforms.value = await getEmailPlatforms(); await load() })
</script>

<style scoped>
.email-page { padding: 12px 16px 28px; }
.page-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
.page-heading h2 { margin:0 0 5px; color:#1f2937; font-size:22px; }
.page-heading span, .import-tip { color:#909399; font-size:13px; }
.heading-actions { display:flex; gap:8px; }
.filter-card, .table-card { margin-bottom:14px; border-radius:10px; }
.filters { display:flex; gap:10px; max-width:760px; }
.filters .el-input { width:340px; } .filters .el-select { width:140px; }
.count { color:#409eff; font-weight:700; }
.email-name { font-weight:600; font-size:12px; }
.email-expanded { padding:12px 22px 16px 52px; background:#f8fafc; }
.detail-grid { display:grid; grid-template-columns:repeat(3, minmax(180px, 1fr)); gap:8px 26px; padding-bottom:12px; border-bottom:1px solid #ebeef5; }
.detail-grid b { display:inline-block; width:72px; color:#909399; font-weight:400; }
.relation-heading { display:flex; align-items:center; gap:10px; padding:12px 0 8px; color:#606266; }
.relation-heading span { color:#909399; font-size:12px; } .relation-heading .el-button { margin-left:auto; }
.relation-list { display:flex; flex-direction:column; gap:6px; }
.relation-item { display:flex; align-items:center; gap:10px; min-height:28px; padding:5px 8px; background:#fff; border:1px solid #ebeef5; border-radius:5px; }
.relation-main { min-width:250px; font-weight:500; } .relation-time { color:#909399; font-size:12px; }
.remark { margin-top:10px; color:#909399; font-size:12px; }
.pager { display:flex; justify-content:flex-end; align-items:center; gap:20px; padding-top:14px; color:#909399; font-size:13px; }
.import-tip { margin-top:10px; line-height:1.6; } .import-result { margin-top:10px; color:#606266; }
@media (max-width:768px) { .email-page { padding:8px; } .page-heading { align-items:flex-start; gap:10px; } .page-heading h2 { font-size:18px; } .filters { flex-wrap:wrap; } .filters .el-input { width:100%; } .filters .el-select { width:140px; } .detail-grid { grid-template-columns:1fr; } .email-expanded { padding:10px; } .relation-item { flex-wrap:wrap; } .relation-main { min-width:0; } }
</style>
