<template>
  <section class="association-overview" v-loading="loading">
    <div v-if="error" class="association-error">{{ error }} <el-button link @click="load">重试</el-button></div>
    <template v-else-if="overview">
      <div class="association-heading"><strong>关联概览</strong><el-button link size="small" @click="load">刷新</el-button><span>已记录累计：<template v-for="kind in kinds" :key="kind.key">{{ kind.label }} {{ overview.counts[kind.key] || 0 }}　</template></span><span v-if="overview.historical_accounts_now_banned" class="association-danger">历史关联账号当前封禁 {{ overview.historical_accounts_now_banned }} 个</span></div>
      <div class="association-current"><b>当前关联</b><div v-for="(item, index) in overview.current" :key="index" class="association-chain"><strong>{{ item.account }}</strong><el-tag v-if="item.status === '封禁'" type="danger" size="small">当前封禁</el-tag><span>→ {{ item.device?.name || '未关联终端' }}</span><span>→ {{ item.nodes.map(node => node.name).join(' / ') || '未关联节点' }}</span><small>{{ item.source }}</small></div><span v-if="!overview.current.length">暂无可见账号关联</span></div>
      <details class="association-history"><summary>查看已记录历史关联（{{ overview.history.length }}）</summary>
        <div class="association-history-list"><div v-for="entry in overview.history" :key="entry.kind + ':' + entry.id" class="association-entry"><span>{{ labels[entry.kind] }}</span><strong>{{ entry.name }}</strong><el-tag :type="entry.current ? 'success' : 'info'" size="small">{{ entry.current ? '当前关联' : '历史关联' }}</el-tag><el-tag v-if="entry.status === '封禁'" type="danger" size="small">当前封禁</el-tag><span>首次记录 {{ time(entry.first_recorded_at) }} · 最近记录 {{ time(entry.last_recorded_at) }}</span></div><span v-if="!overview.history.length">暂无已记录历史关联</span></div>
      </details>
      <details v-if="overview.ban_snapshots.length" class="association-history"><summary class="association-danger">封禁登记时的关联快照（{{ overview.ban_snapshots.length }}）</summary><div v-for="(item, index) in overview.ban_snapshots" :key="index" class="association-entry"><time>{{ time(item.recorded_at) }}</time><strong>{{ item.account }}</strong><span>{{ item.device }} → {{ item.nodes.join(' / ') || '未关联节点' }}</span></div></details>
      <div class="association-note">{{ overview.note }}</div>
    </template>
  </section>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import request from '@/api/request'
const props = defineProps({ kind: { type: String, required: true }, resourceId: { type: Number, required: true } })
const overview = ref(null)
const loading = ref(false)
const error = ref('')
const labels = { account: '账号', device: '终端', node: '节点' }
const kinds = computed(() => Object.entries(labels).filter(([key]) => key !== props.kind).map(([key, label]) => ({ key, label })))
const time = (value) => value ? new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z').toLocaleString('zh-CN') : '无历史时间记录'
let sequence = 0
async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const prefix = { account: 'op-accounts', device: 'devices', node: 'proxy-nodes' }[props.kind]
    const data = await request.get('/' + prefix + '/' + props.resourceId + '/association-history')
    if (current === sequence) overview.value = data
  } catch { if (current === sequence) error.value = '关联概览加载失败' }
  finally { if (current === sequence) loading.value = false }
}
watch(() => [props.kind, props.resourceId], load, { immediate: true })
</script>
<style scoped>
.association-overview { min-width: 0; padding: 6px 0; font-size: 12px; border-top: 1px solid #edf0f5; }
.association-heading, .association-chain, .association-entry { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; line-height: 24px; }
.association-heading > span, .association-note, .association-chain small { color: #909399; font-size: 11px; }
.association-current { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; }
.association-current > b { line-height: 24px; font-weight: 500; color: #909399; }
.association-history { margin-top: 4px; }
.association-history summary { cursor: pointer; color: #606266; line-height: 24px; }
.association-history-list { max-height: 160px; overflow: auto; }
.association-entry { padding: 2px 0; border-bottom: 1px solid #edf0f5; }
.association-note { line-height: 18px; margin-top: 3px; }
.association-danger { color: #e5484d !important; }
.association-error { color: #909399; }
</style>
