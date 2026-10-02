<template>
  <el-card shadow="never" class="work-report">
    <template #header><strong>成员工作量 · {{ projectName }}</strong></template>
    <div class="report-toolbar">
      <el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" @change="load" />
      <el-button :loading="loading" @click="load">刷新</el-button>
      <el-button :disabled="loading || !report.items.length" @click="exportReport">导出明细 CSV</el-button>
      <span>按北京时间统计；卡密消耗与平台注册分别计数，不相加、不自动结算分成。</span>
    </div>
    <el-table v-loading="loading" :data="report.members" size="small" empty-text="当前日期范围暂无完成记录">
      <el-table-column prop="username" label="成员" />
      <el-table-column prop="keys_consumed" label="卡密已消耗" />
      <el-table-column prop="emails_completed" label="平台注册完成" />
    </el-table>
    <details v-if="report.items.length">
      <summary>完成明细（{{ report.items.length }} 条）</summary>
      <el-table :data="pagedItems" size="small">
        <el-table-column prop="username" label="成员" width="120" />
        <el-table-column prop="kind" label="完成类型" width="120" />
        <el-table-column prop="reference" label="关联记录" min-width="240" />
        <el-table-column label="完成时间" width="190"><template #default="{ row }">{{ formatTime(row.time) }}</template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="10" :total="report.items.length" layout="total, prev, pager, next" />
    </details>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { getCardKeyWorkReport } from '@/api/card_keys'

const props = defineProps({ projectId: { type: Number, required: true }, projectName: { type: String, required: true } })
const range = ref(null)
const report = ref({ members: [], items: [] })
const page = ref(1)
const loading = ref(false)
let requestVersion = 0
const pagedItems = computed(() => report.value.items.slice((page.value - 1) * 10, page.value * 10))
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'
const load = async () => {
  const version = ++requestVersion
  loading.value = true
  report.value = { members: [], items: [] }
  page.value = 1
  try {
    const result = await getCardKeyWorkReport(props.projectId, { date_from: range.value?.[0], date_to: range.value?.[1] })
    if (version === requestVersion) report.value = result
  } finally { if (version === requestVersion) loading.value = false }
}
const exportReport = () => {
  const cell = value => `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"`
  const rows = [['项目', '成员', '完成类型', '关联记录', '完成时间（北京时间）'], ...report.value.items.map(item => [props.projectName, item.username, item.kind, item.reference, formatTime(item.time)])]
  const url = URL.createObjectURL(new Blob(['\ufeff' + rows.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `项目-${props.projectId}-成员完成明细.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}
watch(() => props.projectId, load, { immediate: true })
</script>

<style scoped>
.work-report { margin-top:16px; }
.report-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:12px; }
.report-toolbar span { color:#909399; font-size:12px; }
summary { cursor:pointer; padding:12px 0; color:#606266; }
</style>
