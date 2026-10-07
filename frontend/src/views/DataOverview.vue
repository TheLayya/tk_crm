<template>
  <div class="data-overview" v-loading="loading">
    <div class="overview-heading">
      <div><h2>数据总览</h2><p>当前用户可见范围内的资产快照；设备归属人与账号运营人分别展示。</p></div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-if="overview">
      <el-alert title="金额仅来自当前资产记录，不是历史收支流水，也不是净利润。未录入金额不代表零成本；设备采购、节点续费及其他费用尚不包含。修改或删除资产会改变这些金额。" type="info" :closable="false" show-icon />
      <div class="snapshot-note">快照时间：{{ time(overview.generated_at) }} · 状态及金额包含当前记录中的已售资产。</div>
      <div class="snapshot-grid">
      <el-card>
        <template #header><div class="card-header"><strong>资产与状态</strong><span class="muted">当前快照</span></div></template>
        <div class="asset-summary">
          <div><strong>手机 {{ overview.assets.devices.phone }} 台 · 电脑 {{ overview.assets.devices.pc }} 台</strong><p>共 {{ overview.assets.devices.total }} 台未删除终端</p></div>
          <div v-for="section in statusSections" :key="section.label">
            <strong>{{ section.label }} {{ section.total }}</strong>
            <div class="tag-list"><el-tag v-for="(count, name) in section.data" :key="name" type="info">{{ section.map ? section.map(name) : name }} {{ count }}</el-tag></div>
          </div>
        </div>
      </el-card>
        <el-card>
          <template #header><div class="card-header"><strong>待处理与数据质量</strong><span class="muted">当前快照</span></div></template>
          <div class="quality-grid"><div v-for="issue in issues" :key="issue.label" class="issue-row"><span>{{ issue.label }}</span><strong :class="{ warning: issue.value > 0 }">{{ issue.value }}</strong></div></div>
          <p class="muted">账号数据超过 7 天标为过期；节点测试失败指最近一次测试结果，不表示实时连通状态。</p>
        </el-card>
      </div>
      <section class="device-section">
        <div class="card-header device-toolbar">
          <div><strong>人员与终端关联</strong><span class="section-count">{{ deviceRows.length }} 台终端</span></div>
          <el-select v-model="owner" clearable placeholder="全部所属人" style="width: 380px; max-width: 100%"><el-option
            v-for="person in owners"
            :key="person.id"
            :label="`${person.name} · ${person.phone} 手机 · ${person.nodes} 节点 · ${person.accounts} 账号`"
            :value="person.id"
          /></el-select>
        </div>
        <div class="device-grid">
          <article v-for="device in pagedDeviceRows" :key="device.id" class="device-card">
            <div class="device-heading">
              <el-button link @click="router.push(`/devices/${device.id}`)"><el-icon><component :is="device.device_type === 'phone' ? Iphone : Monitor" /></el-icon>{{ device.name }}</el-button>
              <span class="device-owner" :title="device.owner">{{ device.owner }}</span>
              <span class="device-account-count">{{ device.accounts.length }} 账号</span>
            </div>
            <div class="device-nodes">
              <div v-for="node in device.nodes" :key="node.id" class="node-line"><el-icon><Connection /></el-icon><span>{{ node.name }}</span><span class="node-status">{{ nodeStatus(node.status) }}</span></div>
              <span v-if="!device.nodes.length" class="muted">未绑定有效节点</span>
            </div>
            <div class="device-accounts">
              <LinkedAccountCards :accounts="device.accounts" show-all-accounts empty-text="未绑定可见账号" />
            </div>
          </article>
        </div>
        <el-empty v-if="!deviceRows.length" description="暂无终端" :image-size="60" />
        <el-pagination
          v-if="deviceRows.length"
          v-model:current-page="devicePage"
          v-model:page-size="devicePageSize"
          :page-sizes="[12, 24, 48]"
          :total="deviceRows.length"
          layout="total, sizes, prev, pager, next"
          class="device-pagination"
        />
      </section>
      <div class="finance-toolbar">
        <strong>金额与分布</strong>
        <el-radio-group v-model="financePeriod" size="small" @change="changeFinancePeriod">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="day">今天</el-radio-button>
          <el-radio-button value="week">本周</el-radio-button>
          <el-radio-button value="month">本月</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker v-if="financePeriod === 'custom'" v-model="financeDates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" size="small" :clearable="false" style="max-width: 320px" @change="loadFinance" />
        <span class="muted">{{ financeRangeLabel }}</span>
      </div>
      <el-alert v-if="financeError" :title="financeError" type="error" :closable="false" />
      <div class="finance-grid" v-loading="financeLoading">
        <el-card class="finance-card">
          <template #header><strong>已录入金额分布</strong></template>
          <div class="money-summary"><div>采购金额<strong>{{ money(overview.finance.entered_cost) }}</strong></div><div>出售金额<strong>{{ money(overview.finance.entered_revenue) }}</strong></div></div>
          <div class="finance-assets">
            <div v-for="asset in overview.finance.by_asset" :key="asset.name" class="finance-asset">
              <div class="account-heading"><strong>{{ asset.name }}</strong><span class="muted">采购 {{ asset.cost_count }} 笔 · 出售 {{ asset.revenue_count }} 笔</span></div>
              <div class="finance-pair"><span>采购 <strong>{{ money(asset.cost) }}</strong></span><span>出售 <strong>{{ money(asset.revenue) }}</strong></span></div>
            </div>
          </div>
        </el-card>
        <el-card v-for="distribution in distributions" :key="distribution.label" class="finance-card">
          <template #header><strong>{{ distribution.label }}</strong></template>
          <crm-table :table-id="`overview-distribution-${distribution.key}`" :page="distribution.page" :page-size="distribution.pageSize" @total-change="distributionTotals[distribution.key] = $event" @query-change="distributionPages[distribution.key] = 1" :data="distribution.rows" size="small" empty-text="暂无记录"><el-table-column column-key="name" filter-type="text" prop="name" :label="distribution.column" /><el-table-column column-key="count" filter-type="number" prop="count" label="记录数" width="80" /><el-table-column column-key="amount" prop="amount" filter-type="number" label="已录入金额"><template #default="{ row }">{{ money(row.amount) }}</template></el-table-column></crm-table>
          <el-pagination v-if="(distributionTotals[distribution.key] || 0) > distribution.pageSize" :current-page="distribution.page" @current-change="distributionPages[distribution.key] = $event" :page-size="distribution.pageSize" :total="distributionTotals[distribution.key] || 0" layout="prev, pager, next" small class="distribution-pagination" />
        </el-card>
      </div>
      <p class="muted finance-note">采购按采购日期，出售按出售日期，范围包含起止日。缺少日期：采购 {{ overview.finance.missing_cost_dates }} 笔 / 出售 {{ overview.finance.missing_revenue_dates }} 笔（仅“全部”纳入）；节点尚无出售日期。不使用创建时间或修改时间代替业务日期。</p>
      <div class="orphan-grid">
        <el-card class="orphan-card">
          <template #header><div class="card-header"><strong>未绑定有效终端的账号（{{ overview.unbound_accounts.length }}）</strong><span class="muted">每页 {{ orphanPageSize }} 条</span></div></template>
          <LinkedAccountCards class="orphan-accounts" :accounts="pagedUnboundAccounts" show-all-accounts navigate-on-click empty-text="暂无未绑定账号" @account-click="openAccount" />
          <el-pagination v-if="overview.unbound_accounts.length > orphanPageSize" v-model:current-page="orphanPages.accounts" :page-size="orphanPageSize" :total="overview.unbound_accounts.length" layout="prev, pager, next" small class="orphan-pagination" />
        </el-card>
        <el-card class="orphan-card">
          <template #header><div class="card-header"><strong>未关联可见终端或账号的节点（{{ overview.unbound_nodes.length }}）</strong><span class="muted">每页 {{ orphanPageSize }} 条</span></div></template>
          <crm-table table-id="overview-unbound-nodes" :page="orphanPages.nodes" :page-size="orphanPageSize" @total-change="unboundNodeTotal = $event" @query-change="orphanPages.nodes = 1" :data="overview.unbound_nodes" size="small" empty-text="暂无未关联节点"><el-table-column column-key="name" prop="name" filter-type="text" label="节点" min-width="130"><template #default="{ row }"><el-button link type="primary" @click="openNode(row)">{{ row.name }}</el-button></template></el-table-column><el-table-column column-key="status" prop="status" filter-type="enum" :filter-options="[{ label: '闲置', value: 'idle' }, { label: '自用', value: 'active' }, { label: '已出售', value: 'sold' }, { label: '停用', value: 'disabled' }]" label="状态" width="80"><template #default="{ row }">{{ nodeStatus(row.status) }}</template></el-table-column><el-table-column column-key="expire_date" filter-type="date" prop="expire_date" label="到期日期" width="110" /></crm-table>
          <el-pagination v-if="unboundNodeTotal > orphanPageSize" v-model:current-page="orphanPages.nodes" :page-size="orphanPageSize" :total="unboundNodeTotal" layout="prev, pager, next" small class="orphan-pagination" />
        </el-card>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Iphone, Monitor, Connection } from '@element-plus/icons-vue'
import LinkedAccountCards from '@/components/LinkedAccountCards.vue'
import { getDataOverview } from '@/api/overview'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const overview = ref(null)
const owner = ref(null)
const devicePage = ref(1)
const devicePageSize = ref(12)
const financePeriod = ref('all')
const financeDates = ref([])
const financeLoading = ref(false)
const financeError = ref('')
let financeRequestId = 0
const financeRangeLabel = computed(() => {
  const finance = overview.value?.finance
  return finance?.date_from ? `${finance.date_from} 至 ${finance.date_to}` : '全部日期'
})
function financeParams() {
  if (financePeriod.value === 'all') return {}
  if (financeDates.value?.length !== 2) return null
  return { date_from: financeDates.value[0], date_to: financeDates.value[1] }
}
function changeFinancePeriod() {
  if (financePeriod.value === 'custom') {
    financeDates.value = []
    return
  }
  const today = new Date()
  const start = new Date(today)
  if (financePeriod.value === 'week') start.setDate(today.getDate() - (today.getDay() + 6) % 7)
  if (financePeriod.value === 'month') start.setDate(1)
  const format = value => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  financeDates.value = financePeriod.value === 'all' ? [] : [format(start), format(today)]
  loadFinance()
}
async function loadFinance() {
  const params = financeParams()
  if (!params) return
  const requestId = ++financeRequestId
  financeLoading.value = true
  financeError.value = ''
  try {
    const result = await getDataOverview(params)
    if (requestId === financeRequestId && overview.value) overview.value.finance = result.finance
  } catch (failure) {
    if (requestId === financeRequestId) financeError.value = failure?.response?.data?.detail || '金额加载失败，仍显示上次范围的数据，请重试'
  } finally {
    if (requestId === financeRequestId) financeLoading.value = false
  }
}
const money = value => `¥${Number(value).toFixed(2)}`
const count = value => value == null ? '未采集' : Number(value).toLocaleString()
const time = value => value ? new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`).toLocaleString() : '未采集'
const nodeStatus = value => ({ idle: '闲置', active: '自用', sold: '已出售', disabled: '停用' }[value] || value)
const owners = computed(() => {
  const people = new Map()
  for (const device of overview.value?.device_rows || []) {
    if (!people.has(device.owner_id)) {
      people.set(device.owner_id, {
        id: device.owner_id,
        name: device.owner,
        phone: 0,
        pc: 0,
        nodeIds: new Set(),
        accountIds: new Set()
      })
    }
    const person = people.get(device.owner_id)
    if (device.device_type === 'phone') person.phone++
    if (device.device_type === 'pc') person.pc++
    for (const node of device.nodes || []) person.nodeIds.add(node.id)
    for (const account of device.accounts || []) person.accountIds.add(account.id)
  }
  return [...people.values()].map(person => ({
    ...person,
    nodes: person.nodeIds.size,
    accounts: person.accountIds.size
  }))
})
const deviceRows = computed(() => (overview.value?.device_rows || []).filter(device => owner.value == null || device.owner_id === owner.value))
const pagedDeviceRows = computed(() => {
  const start = (devicePage.value - 1) * devicePageSize.value
  return deviceRows.value.slice(start, start + devicePageSize.value)
})
watch(owner, () => { devicePage.value = 1 })
watch(devicePageSize, () => { devicePage.value = 1 })
watch(() => overview.value?.finance?.cost_by_channel, () => { distributionPages.cost = 1 })
watch(() => overview.value?.finance?.revenue_by_customer, () => { distributionPages.revenue = 1 })
const statusSections = computed(() => {
  if (!overview.value) return []
  const assets = overview.value.assets
  return [
    { label: '运营账号', total: assets.accounts.total, data: assets.accounts.by_status },
    { label: '代理节点', total: assets.nodes.total, data: assets.nodes.by_status, map: nodeStatus },
    { label: '邮箱', total: assets.emails.total, data: assets.emails.by_status }
  ]
})
const orphanPageSize = 5
const orphanPages = reactive({ accounts: 1, nodes: 1 })
const unboundNodeTotal = ref(0)
const pagedUnboundAccounts = computed(() => overview.value?.unbound_accounts.slice((orphanPages.accounts - 1) * orphanPageSize, orphanPages.accounts * orphanPageSize) || [])
const openAccount = (account) => router.push({ path: '/op-accounts', query: { account_id: account.id, keyword: account.account } })
const openNode = (node) => router.push({ path: '/proxy-nodes', query: { node_id: node.id } })
const distributionPageSize = 5
const distributionPages = reactive({ cost: 1, revenue: 1 })
const distributionTotals = reactive({ cost: 0, revenue: 0 })
const distributions = computed(() => {
  const items = [
    { key: 'cost', label: '采购渠道分布', column: '渠道', rows: overview.value?.finance.cost_by_channel || [] },
    { key: 'revenue', label: '出售客户分布', column: '客户', rows: overview.value?.finance.revenue_by_customer || [] }
  ]
  return items.map(item => ({
    ...item,
    page: distributionPages[item.key],
    pageSize: distributionPageSize
  }))
})
const issues = computed(() => {
  const quality = overview.value?.quality || {}
  return [
    { label: '所属人缺失的终端', value: quality.unassigned_devices },
    { label: '未绑定有效节点的终端', value: quality.unbound_devices },
    { label: '未绑定有效终端的账号', value: quality.unbound_accounts },
    { label: '未填写运营人的账号', value: quality.unassigned_accounts },
    { label: '未采集账号数据', value: quality.uncollected_accounts },
    { label: '超过 7 天未采集', value: quality.stale_accounts },
    { label: '已过期节点', value: quality.expired_nodes },
    { label: '7 天内到期节点', value: quality.expiring_nodes },
    { label: '节点最近测试失败', value: quality.failed_nodes },
    { label: '缺少采购金额的记录', value: quality.missing_purchase_amount }
  ]
})
async function load() {
  loading.value = true
  error.value = ''
  try {
    overview.value = await getDataOverview(financeParams() || {})
    devicePage.value = 1
    orphanPages.accounts = 1
    orphanPages.nodes = 1
  } catch (failure) {
    overview.value = null
    error.value = failure?.response?.data?.detail || '总览加载失败，请重试'
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.data-overview { display: flex; flex-direction: column; gap: 14px; padding-bottom: 24px; }
.overview-heading, .card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.overview-heading h2 { margin: 0 0 6px; font-size: 22px; }
.overview-heading p, .muted, .snapshot-note { color: #909399; font-size: 12px; line-height: 1.7; }
.overview-heading p { margin: 0; }
.snapshot-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: stretch; }
.snapshot-grid > :deep(.el-card) { height: 100%; box-sizing: border-box; }
.snapshot-grid :deep(.el-card__header) { padding: 12px 16px; }
.snapshot-grid :deep(.el-card__body) { padding: 12px 16px; }
.asset-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 16px; }
.quality-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2px 18px; }
.quality-grid .issue-row { gap: 10px; font-size: 12px; }
.finance-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.finance-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: stretch; }
.finance-card { height: 100%; box-sizing: border-box; }
.finance-card :deep(.el-card__body) { display: flex; flex-direction: column; min-height: 220px; box-sizing: border-box; }
.distribution-pagination { justify-content: flex-end; margin-top: auto; padding-top: 10px; }
.finance-grid :deep(.el-card__header) { padding: 12px 16px; }
.finance-grid :deep(.el-card__body) { padding: 12px 16px; }
.finance-note { margin: 0; }
.orphan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: stretch; }
.orphan-card { height: 100%; box-sizing: border-box; }
.orphan-card :deep(.el-card__body) { display: flex; flex-direction: column; min-height: 220px; box-sizing: border-box; }
.orphan-pagination { justify-content: flex-end; margin-top: auto; padding-top: 10px; }
.orphan-accounts :deep(.account-chip) { width: 240px !important; flex-basis: 240px !important; max-width: 100%; }
.account-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.finance-pair { display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 12px; }
@media (max-width: 1100px) { .snapshot-grid, .finance-grid, .orphan-grid { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .quality-grid { grid-template-columns: 1fr; } }
.asset-summary p { color: #909399; font-size: 12px; }
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.device-section { min-width: 0; }
.device-toolbar { margin-bottom: 12px; }
.device-pagination { justify-content: flex-end; margin-top: 4px; }
.section-count { margin-left: 12px; color: #8b95a5; font-size: 12px; font-weight: 400; }
.device-grid { display: flex; flex-direction: column; gap: 8px; }
.device-card { display: grid; grid-template-columns: 170px 190px minmax(0, 1fr); align-items: stretch; min-width: 0; border: 1px solid #e2e7ee; border-radius: 8px; background: #fff; overflow: hidden; }
.device-heading { display: flex; flex-wrap: wrap; align-content: center; align-items: center; gap: 8px; min-width: 0; padding: 12px 14px; background: #f8fafc; }
.device-heading .el-button { flex-basis: 100%; justify-content: flex-start; padding: 0; height: auto; font-size: 14px; font-weight: 650; color: #25344a; min-width: 0; white-space: normal; text-align: left; }
.device-heading .el-button:hover { color: #5366bd; }
.device-heading .el-icon { color: #74839a; margin-right: 6px; flex-shrink: 0; }
.device-owner { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #606e80; font-size: 12px; }
.device-account-count { flex-shrink: 0; border-left: 1px solid #dce2eb; padding-left: 8px; color: #8b95a5; font-size: 11px; }
.device-nodes { display: flex; flex-direction: column; justify-content: center; min-width: 0; padding: 7px 10px; border-left: 1px solid #edf0f4; border-right: 1px solid #edf0f4; }
.node-line { display: flex; align-items: center; gap: 6px; min-width: 0; color: #64748b; font-size: 11px; }
.node-line > span:first-of-type { min-width: 0; overflow-wrap: anywhere; }
.node-line + .node-line { margin-top: 5px; }
.node-status { margin-left: auto; flex-shrink: 0; color: #8b95a5; font-size: 11px; }
.device-accounts { min-width: 0; padding: 6px 10px; }
.device-accounts :deep(.linked-accounts) { min-height: 44px; overflow-x: auto; }
.device-accounts :deep(.linked-accounts) { gap: 6px; }
.device-accounts :deep(.account-chip) { flex: 0 0 240px !important; width: 240px !important; max-width: 240px !important; }
.finance-assets { display: grid; gap: 8px; }
.finance-asset { border-radius: 6px; background: #f6f8fb; padding: 12px; }
.finance-pair { margin: 10px 0 0; }
.money-summary { display: flex; gap: 30px; margin-bottom: 16px; color: #606266; font-size: 13px; }
.money-summary strong { display: block; color: #303133; font-size: 22px; margin-top: 6px; }
.issue-row { display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; color: #606266; }
.warning { color: #e6a23c; }
@media (max-width: 1000px) { .device-card { grid-template-columns: 150px 170px minmax(0, 1fr); } .account-card { min-width: 200px; } .asset-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } .overview-grid { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .device-card { display: block; } .device-heading { border-bottom: 1px solid #edf0f4; } .device-nodes { border: 0; border-bottom: 1px solid #edf0f4; } .account-card { flex: 1 1 240px; } }
@media (max-width: 600px) { .data-overview { padding-bottom: 70px; } .card-header { flex-wrap: wrap; } .money-summary { gap: 20px; } }
</style>
