<template>
  <section ref="reportRoot" class="work-report" aria-label="成员工作量统计">
    <div class="report-heading"><div><h3>成员工作量</h3><span>{{ projectName }}</span></div><el-tag size="small" type="info">北京时间</el-tag></div>
    <div class="report-toolbar">
      <div class="report-presets" role="group" aria-label="工作量统计范围"><el-button size="small" :type="preset === 'today' ? 'primary' : ''" @click="setPreset('today')">今天</el-button><el-button size="small" :type="preset === '7d' ? 'primary' : ''" @click="setPreset('7d')">近 7 天</el-button><el-button size="small" :type="preset === 'all' ? 'primary' : ''" @click="setPreset('all')">全部时间</el-button></div>
      <el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" @change="onRangeChange" />
      <el-button :loading="loading" @click="load">刷新</el-button>
      <el-button :disabled="loading || !detailItems.length" @click="exportReport">{{ memberFilter ? '导出该成员明细 CSV' : '导出明细 CSV' }}</el-button>
    </div>
    <p class="report-hint">统计范围：{{ rangeLabel }}（北京时间）；卡密消耗与平台注册分别计数，不相加、不自动结算分成。</p>
    <el-alert v-if="errorMessage" class="report-error" type="error" :closable="false" :title="errorMessage"><template #default><el-button link type="danger" @click="load">重试</el-button></template></el-alert>
    <div class="report-summary" v-loading="loading"><div><span>卡密已消耗</span><strong>{{ keyCount }}</strong></div><div><span>平台注册完成</span><strong>{{ emailCount }}</strong></div><div><span>参与成员</span><strong>{{ report.members.length }}</strong></div></div>
    <el-tabs v-model="reportView" class="report-tabs" aria-label="工作量查看方式">
    <el-tab-pane label="成员汇总" name="members">
    <div class="report-section-head"><span class="muted">点击“看明细”核对成员记录</span></div>
    <crm-table table-id="card-key-work-report-members" v-loading="loading" :data="report.members" size="small" :max-height="tableHeights['card-key-work-report-members']" empty-text="当前日期范围暂无完成记录">
      <el-table-column column-key="username" filter-type="text" prop="username" label="成员" min-width="150" />
      <el-table-column column-key="keys_consumed" filter-type="number" prop="keys_consumed" label="卡密已消耗" width="140" />
      <el-table-column column-key="emails_completed" filter-type="number" prop="emails_completed" label="平台注册完成" width="150" />
      <el-table-column column-key="actions" table-tools-disabled label="操作" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" :aria-label="`查看成员明细：${row.username}`" @click="showMember(row.username)">看明细</el-button></template></el-table-column>
    </crm-table>
    </el-tab-pane>
    <el-tab-pane label="完成明细" name="details">
    <div class="report-section-head detail-head"><span class="muted">{{ detailItems.length }} 条</span><el-select v-model="memberFilter" clearable filterable size="small" aria-label="工作量明细成员" placeholder="全部成员" style="width:180px"><el-option v-for="member in report.members" :key="member.username" :label="member.username" :value="member.username" /></el-select></div>
      <crm-table table-id="card-key-work-report-items" :page="page" :page-size="10" @total-change="reportTotal = $event" @query-change="page = 1" :data="detailItems" size="small" :max-height="tableHeights['card-key-work-report-items']" empty-text="当前日期范围暂无完成明细">
        <el-table-column column-key="username" filter-type="text" prop="username" label="成员" width="120" />
        <el-table-column column-key="kind" filter-type="text" prop="kind" label="完成类型" width="120" />
        <el-table-column column-key="reference" filter-type="text" prop="reference" label="关联记录" min-width="240" show-overflow-tooltip />
        <el-table-column column-key="time" prop="time" filter-type="date" label="完成时间" width="190"><template #default="{ row }">{{ formatTime(row.time) }}</template></el-table-column>
      </crm-table>
      <el-pagination v-if="reportTotal" class="report-pagination" v-model:current-page="page" :page-size="10" :total="reportTotal" layout="total, prev, pager, next" />
    </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getCardKeyWorkReport } from '@/api/card_keys'
import { useViewportTableHeight } from '@/composables/useViewportTableHeight'

const props = defineProps({ projectId: { type: Number, required: true }, projectName: { type: String, required: true } })
const range = ref(null)
const preset = ref('today')
const memberFilter = ref('')
const reportView = ref('members')
const reportRoot = ref(null)
const { heights: tableHeights, refresh: refreshTableHeight } = useViewportTableHeight(reportRoot, [
  { id: 'card-key-work-report-members', max: 300, bottom: 24 },
  { id: 'card-key-work-report-items', max: 380, bottom: 64 },
])
watch(reportView, () => nextTick(refreshTableHeight))
const report = ref({ members: [], items: [] })
const page = ref(1)
const reportTotal = ref(0)
const loading = ref(false)
const errorMessage = ref('')
let requestVersion = 0
const beijingDate = (offset = 0) => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const today = new Date(Date.UTC(Number(parts.find(part => part.type === 'year').value), Number(parts.find(part => part.type === 'month').value) - 1, Number(parts.find(part => part.type === 'day').value)))
  today.setUTCDate(today.getUTCDate() + offset)
  return today.toISOString().slice(0, 10)
}
const setPreset = value => { preset.value = value; range.value = value === 'today' ? [beijingDate(), beijingDate()] : value === '7d' ? [beijingDate(-6), beijingDate()] : null; load() }
const onRangeChange = value => { preset.value = value?.[0] === beijingDate() && value?.[1] === beijingDate() ? 'today' : ''; load() }
const rangeLabel = computed(() => range.value ? `${range.value[0]} 至 ${range.value[1]}` : '全部历史')
const detailItems = computed(() => memberFilter.value ? report.value.items.filter(item => item.username === memberFilter.value) : report.value.items)
const showMember = username => { memberFilter.value = username; reportView.value = 'details' }
const keyCount = computed(() => report.value.members.reduce((sum, member) => sum + Number(member.keys_consumed || 0), 0))
const emailCount = computed(() => report.value.members.reduce((sum, member) => sum + Number(member.emails_completed || 0), 0))
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'
const load = async () => {
  const version = ++requestVersion
  const projectId = props.projectId
  loading.value = true
  errorMessage.value = ''
  report.value = { members: [], items: [] }
  page.value = 1
  try {
    const result = await getCardKeyWorkReport(projectId, { date_from: range.value?.[0], date_to: range.value?.[1] })
    if (version === requestVersion && projectId === props.projectId) {
      report.value = { members: result?.members || [], items: result?.items || [] }
      if (memberFilter.value && !report.value.members.some(member => member.username === memberFilter.value)) memberFilter.value = ''
    }
  } catch (error) {
    if (version === requestVersion && projectId === props.projectId) errorMessage.value = error.response?.data?.detail || '工作量加载失败，请重试'
  } finally { if (version === requestVersion) loading.value = false }
}
const exportReport = () => {
  const cell = value => `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"`
  const rows = [['项目', '成员', '完成类型', '关联记录', '完成时间（北京时间）'], ...detailItems.value.map(item => [props.projectName, item.username, item.kind, item.reference, formatTime(item.time)])]
  const url = URL.createObjectURL(new Blob(['\ufeff' + rows.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `项目-${props.projectId}-成员完成明细.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}
range.value = [beijingDate(), beijingDate()]
watch(() => props.projectId, () => { memberFilter.value = ''; reportView.value = 'members'; load() }, { immediate: true })
watch(memberFilter, () => { page.value = 1 })
onBeforeUnmount(() => { requestVersion++ })
</script>

<style scoped>
.work-report { padding-top:4px; min-width:0; }
.report-heading,.report-heading > div { display:flex; align-items:center; gap:10px; }
.report-heading { justify-content:space-between; margin-bottom:14px; }
.report-heading h3 { margin:0; color:#1f2937; font-size:16px; }
.report-heading span,.muted,.report-hint { color:#909399; font-size:12px; }
.report-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:12px; }
.report-presets { display:flex; gap:6px; }
.report-presets .el-button + .el-button { margin-left:0; }
.report-hint { margin:0 0 14px; line-height:1.6; }
.report-error { margin-bottom:12px; }
.report-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-bottom:18px; }
.report-summary > div { padding:12px 14px; border:1px solid #e2e8f0; border-radius:6px; background:#f8fafc; }
.report-summary span { display:block; color:#64748b; font-size:12px; }
.report-summary strong { display:block; margin-top:5px; color:#1f2937; font-size:24px; line-height:1.1; font-variant-numeric:tabular-nums; }
.report-section-head { display:flex; align-items:center; gap:10px; }
.report-section-head { justify-content:space-between; margin:14px 0 8px; }
.detail-head { margin-top:4px; }
.report-pagination { justify-content:flex-end; margin-top:10px; }
@media (max-width:768px) { .report-heading > div { align-items:flex-start; flex-direction:column; gap:4px; } .report-summary { gap:6px; } .report-summary > div { padding:10px; } .report-summary strong { font-size:22px; } .report-toolbar .el-date-editor { width:100%; } .detail-head { flex-wrap:wrap; } .detail-head .el-select { width:100% !important; } }
</style>
