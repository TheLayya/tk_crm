<template>
  <div ref="containerRef" class="linked-accounts" :class="{ 'linked-accounts--expanded': showAllAccounts }" @click.stop>
    <button
      v-for="account in visibleAccounts"
      :key="account.id"
      type="button"
      class="account-chip"
      :aria-label="`${navigateOnClick ? '查看详情' : '放大查看'}账号 ${accountName(account)}`"
      :aria-haspopup="navigateOnClick ? undefined : 'dialog'"
      :title="navigateOnClick ? '点击前往账号详情' : '点击放大'"
      @click.stop="openAccount(account)"
      :style="chipStyle"
    >
      <span class="account-identity">
        <el-avatar :size="16" :src="account.avatar_url || undefined" class="account-avatar">
          {{ accountName(account).slice(0, 1).toUpperCase() }}
        </el-avatar>
        <span class="account-name" :title="accountName(account)">{{ accountName(account) }}</span>
        <span v-if="account.nickname" class="account-nickname" :title="account.nickname">{{ account.nickname }}</span>
      </span>
      <span class="account-data-row">
        <span class="account-inline-stats" :title="inlineStats(account)">{{ inlineStats(account) }}</span>
        <span class="account-indicator" :class="deltaClass(account.followers_change)" :title="'粉丝变化（较上次采集）：' + formatDelta(account.followers_change)"><el-icon aria-hidden="true"><component :is="account.followers_change < 0 ? Bottom : Top" /></el-icon>{{ account.followers_change == null ? '—' : compactCount(Math.abs(account.followers_change)) }}</span>
        <span class="account-indicator" :title="'昨日更新（北京时间）：' + yesterdayLabel(account)"><el-icon aria-hidden="true"><Refresh /></el-icon>{{ account.yesterday_video_count == null ? '—' : account.yesterday_video_count }}</span>
        <span class="account-indicator account-indicator--traffic" :title="'昨日视频流量：' + yesterdayPlays(account)"><el-icon aria-hidden="true"><VideoPlay /></el-icon><span>{{ account.yesterday_video_count == null ? '—' : yesterdayPlays(account) }}</span></span>
      </span>
    </button>
    <button
      v-if="!showAllAccounts && accounts.length > visibleCount"
      type="button"
      class="account-more"
      :aria-label="`查看全部 ${accounts.length} 个账号`"
      :title="`共 ${accounts.length} 个账号，点击查看全部`"
      aria-haspopup="dialog"
      @click.stop="showAll = true"
    >+{{ accounts.length - visibleCount }}</button>
    <span v-if="!accounts.length" class="account-empty">{{ emptyText }}</span>

    <el-dialog
      v-model="showAll"
      :title="`全部关联账号（${accounts.length}）`"
      width="620px"
      style="max-width: calc(100vw - 32px)"
      append-to-body
      destroy-on-close
    >
      <div class="account-all-list">
        <button
          v-for="account in accounts"
          :key="account.id"
          type="button"
          class="account-all-item"
          :aria-label="`放大查看账号 ${accountName(account)}`"
          @click="openAccount(account)"
        >
          <el-avatar :size="32" :src="account.avatar_url || undefined" class="account-avatar">
            {{ accountName(account).slice(0, 1).toUpperCase() }}
          </el-avatar>
          <span class="account-all-info">
            <strong>{{ accountName(account) }}</strong>
            <span>{{ account.nickname || '暂无昵称' }}</span>
            <span>粉丝变化 <strong :class="deltaClass(account.followers_change)">{{ formatDelta(account.followers_change) }}</strong> · 昨日更新（北京时间） {{ yesterdayLabel(account) }}</span>
            <span>昨日视频流量 {{ yesterdayPlays(account) }}</span>
            <span class="account-all-metrics">
              <span v-for="metric in metrics" :key="metric.key">{{ metric.label }} {{ formatCount(account[metric.key]) }}</span>
            </span>
          </span>
        </button>
      </div>
    </el-dialog>

    <el-dialog
      v-model="expanded"
      title="账号概览"
      width="380px"
      style="max-width: calc(100vw - 32px)"
      append-to-body
      destroy-on-close
    >
      <div v-if="selectedAccount" class="account-expanded">
        <el-avatar :size="80" :src="selectedAccount.avatar_url || undefined" class="account-avatar">
          {{ accountName(selectedAccount).slice(0, 1).toUpperCase() }}
        </el-avatar>
        <h3>{{ accountName(selectedAccount) }}</h3>
        <p>{{ selectedAccount.nickname || '暂无昵称' }}</p>
        <p>粉丝变化 <strong :class="deltaClass(selectedAccount.followers_change)">{{ formatDelta(selectedAccount.followers_change) }}</strong></p>
        <p>昨日更新（北京时间） {{ yesterdayLabel(selectedAccount) }}</p>
        <p>昨日视频流量 {{ yesterdayPlays(selectedAccount) }}</p>
        <div class="account-metrics">
          <div v-for="metric in metrics" :key="metric.key" class="account-metric">
            <strong>{{ formatCount(selectedAccount[metric.key]) }}</strong>
            <span>{{ metric.label }}</span>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Top, Bottom, Refresh, VideoPlay } from '@element-plus/icons-vue'

const props = defineProps({
  accounts: { type: Array, default: () => [] },
  emptyText: { type: String, default: '未绑定' },
  showAllAccounts: { type: Boolean, default: false },
  navigateOnClick: { type: Boolean, default: false },
})
const emit = defineEmits(['account-click'])

const metrics = [
  { key: 'follower_count', label: '粉丝' },
  { key: 'following_count', label: '关注' },
  { key: 'like_count', label: '点赞' },
  { key: 'video_count', label: '视频' },
]
const selectedAccount = ref(null)
const expanded = ref(false)
const showAll = ref(false)
const containerRef = ref(null)
const containerWidth = ref(0)
const visibleCount = ref(0)
let resizeObserver
const accountName = (account) => account.account || account.username || `账号 #${account.id}`
const formatCount = (value) => value == null || value === '' ? '—' : Number(value).toLocaleString('zh-CN')
const compactNumber = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1, useGrouping: false })
const compactCount = (value) => value == null || value === '' ? '—' : compactNumber.format(Number(value))
const inlineStats = (account) => `粉${compactCount(account.follower_count)} 关${compactCount(account.following_count)} 赞${compactCount(account.like_count)} 视${compactCount(account.video_count)}`
const formatDelta = (value) => value == null ? '—' : value > 0 ? '+' + formatCount(value) : formatCount(value)
const deltaClass = (value) => value > 0 ? 'delta-up' : value < 0 ? 'delta-down' : ''
const yesterdayLabel = (account) => account.yesterday_video_count == null ? '待采集' : account.yesterday_video_count > 0 ? account.yesterday_video_count + '条' : '未更新'
const yesterdayPlays = (account) => account.yesterday_video_count == null ? '暂无可靠数据' : account.yesterday_video_count === 0 ? '—' : (account.yesterday_video_plays || []).join(' / ') || '暂无可靠数据'
const visibleAccounts = computed(() => props.showAllAccounts ? props.accounts : props.accounts.slice(0, visibleCount.value))
const chipStyle = computed(() => {
  if (props.showAllAccounts) return { width: '320px', flexBasis: '320px' }
  const count = visibleCount.value || 1
  const extra = props.accounts.length > count ? 34 : 0
  const width = Math.max(260, Math.floor((containerWidth.value - extra - (count - 1) * 4) / count))
  return { width: `${width}px`, flexBasis: `${width}px` }
})
function updateVisibleCount() {
  const total = props.accounts.length
  if (!total || !containerWidth.value) { visibleCount.value = total ? 1 : 0; return }
  for (let count = Math.min(3, total); count >= 1; count -= 1) {
    const extra = total > count ? 34 : 0
    if (count * 260 + (count - 1) * 4 + extra <= containerWidth.value) {
      visibleCount.value = count
      return
    }
  }
  visibleCount.value = 1
}

function openAccount(account) {
  if (props.navigateOnClick) {
    emit('account-click', account)
    return
  }
  showAll.value = false
  selectedAccount.value = account
  expanded.value = true
}
onMounted(async () => {
  await nextTick()
  resizeObserver = new ResizeObserver(([entry]) => {
    containerWidth.value = entry.contentRect.width
    updateVisibleCount()
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  updateVisibleCount()
})
watch(() => props.accounts.length, updateVisibleCount)
onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<style scoped>
.linked-accounts {
  position: relative;
  width: 100%;
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  min-height: 46px;
  min-width: 0;
  overflow: hidden;
}
.linked-accounts--expanded { flex-wrap: wrap; gap: 6px; align-items: flex-start; }
.account-chip {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  flex: 0 0 188px;
  width: 188px;
  max-width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 3px 6px;
  border: 1px solid #e1e6ef;
  border-radius: 4px;
  background: #f2f5ff;
  color: #303133;
  font: inherit;
  line-height: 20px;
  text-align: left;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.account-chip:hover, .account-more:hover, .account-all-item:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px #5d64f51a;
}
.account-chip:focus-visible, .account-more:focus-visible, .account-all-item:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.account-avatar { flex-shrink: 0; background: #e5e9f3; color: #626d85; }
.account-identity { display: flex; align-items: center; gap: 4px; min-width: 0; }
.account-nickname { flex: 1 1 0; min-width: 0; font-size: 11px; color: #737d8c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-name {
  flex: 0 1 auto;
  max-width: 70%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.account-name { font-size: 12px; }
.account-chip .account-avatar { font-size: 10px; }
.account-data-row { display: flex; align-items: center; gap: 7px; min-width: 0; font-size: 11px; color: #737d8c; line-height: 18px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.account-inline-stats {
  flex: 0 1 auto;
  min-width: 0;
  flex-shrink: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #737d8c;
  font-size: 11px;
  white-space: nowrap;
}
.account-indicator { display: inline-flex; align-items: center; gap: 2px; flex-shrink: 0; }
.account-indicator--traffic { min-width: 0; flex-shrink: 1; }
.account-indicator--traffic > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.delta-up { color: #169b62; }
.delta-down { color: #e5484d; }
.account-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
  gap: 18px 12px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #edf0f5;
  font-variant-numeric: tabular-nums;
}
.account-metric { display: flex; flex-direction: column; min-width: 0; gap: 1px; }
.account-metric strong { font-size: 22px; overflow-wrap: anywhere; }
.account-metric > span { color: #737d8c; font-size: 13px; }
.account-more {
  align-self: center;
  flex-shrink: 0;
  min-width: 26px;
  height: 22px;
  padding: 0 5px;
  border: 1px solid #e1e6ef;
  border-radius: 4px;
  background: #f2f5ff;
  color: var(--el-color-primary);
  font-size: 12px;
  cursor: pointer;
}
.account-all-list { display: flex; flex-direction: column; gap: 8px; max-height: 60vh; overflow-y: auto; }
.account-all-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid #e1e6ef;
  border-radius: 8px;
  background: #fafbff;
  text-align: left;
  font: inherit;
  cursor: pointer;
}
.account-all-info { display: flex; flex-direction: column; gap: 4px; min-width: 0; overflow-wrap: anywhere; }
.account-all-info > span { color: #737d8c; font-size: 12px; }
.account-all-metrics { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.account-empty { color: #909399; }
.account-expanded { display: flex; flex-direction: column; align-items: center; text-align: center; }
.account-expanded h3 { margin: 12px 0 4px; font-size: 20px; overflow-wrap: anywhere; }
.account-expanded p { margin: 0; color: #737d8c; overflow-wrap: anywhere; }
</style>
