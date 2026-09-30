<template>
  <section class="inline-videos" v-loading="loading">
    <div class="video-heading">
      <strong>视频信息 <span v-if="!error">（已记录 {{ total }} 条）</span></strong>
      <el-button size="small" :disabled="loading" @click="loadVideos">刷新视频数据</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-else>
      <div v-if="videos.length" class="video-cards" tabindex="0" aria-label="视频卡片列表，可左右滚动">
        <article v-for="video in videos" :key="video.id" class="video-card">
          <el-image v-if="video.cover_url" :src="video.cover_url" fit="cover" class="video-cover" :preview-src-list="[video.cover_url]" preview-teleported>
            <template #error><span class="cover-placeholder">封面失效</span></template>
          </el-image>
          <span v-else class="cover-placeholder">暂无封面</span>
          <time class="video-date" :title="'北京时间 ' + formatPublishedAt(video.published_at)">{{ formatPublishedAt(video.published_at).split(' ')[0] }}</time>
          <div class="video-overlay">
            <div class="video-metrics">
              <span v-for="metric in metrics" :key="metric.key" :title="metric.label + '：' + formatNumber(video[metric.key])">{{ metric.label }} <strong>{{ formatNumber(video[metric.key]) }}</strong></span>
            </div>
            <el-tooltip :content="(video.title || '无标题') + ' · ID：' + video.video_id" placement="top">
              <div class="video-title" tabindex="0">{{ video.title || '无标题' }}</div>
            </el-tooltip>
          </div>
        </article>
      </div>
      <div v-else class="video-empty">暂无已采集视频；请启用视频监控后检查账号。</div>
      <el-pagination v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total" layout="total, prev, pager, next" small @current-change="loadVideos" />
    </template>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { getAccountVideos } from '@/api/videos'

const props = defineProps({ accountId: { type: Number, required: true } })
const videos = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const error = ref('')
const metrics = [
  { key: 'play_count', label: '播放' },
  { key: 'like_count', label: '点赞' },
  { key: 'comment_count', label: '评论' },
  { key: 'share_count', label: '分享' }
]
const formatNumber = (value) => (value ?? 0).toLocaleString('zh-CN')
const formatPublishedAt = (value) => {
  if (!value) return '-'
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : value + 'Z'
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
let requestVersion = 0
const loadVideos = async () => {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const response = await getAccountVideos(props.accountId, { skip: (page.value - 1) * pageSize, limit: pageSize })
    if (version !== requestVersion) return
    videos.value = response.items || []
    total.value = response.total ?? 0
  } catch (failure) {
    if (version !== requestVersion) return
    error.value = '视频数据加载失败，请点击刷新重试。'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
watch(() => props.accountId, () => {
  page.value = 1
  videos.value = []
  total.value = 0
  loadVideos()
}, { immediate: true })
</script>

<style scoped>
.inline-videos { margin-bottom: 10px; min-width: 0; }
.video-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 6px; }
.video-heading span { color: #909399; font-size: 12px; font-weight: 400; }
.video-cards { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 6px; scrollbar-width: thin; }
.video-card { position: relative; flex: 0 0 130px; width: 130px; height: 180px; overflow: hidden; border-radius: 7px; background: #283140; color: #fff; }
.video-cover, .cover-placeholder { width: 100%; height: 100%; }
.cover-placeholder { display: flex; align-items: center; justify-content: center; color: #cbd5e1; font-size: 12px; }
.video-date { position: absolute; top: 5px; left: 5px; padding: 2px 5px; border-radius: 4px; background: rgba(0, 0, 0, .62); font-size: 11px; line-height: 18px; pointer-events: none; }
.video-overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 18px 6px 6px; background: linear-gradient(transparent, rgba(0, 0, 0, .88)); }
.video-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2px 4px; font-size: 11px; line-height: 18px; }
.video-metrics > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.video-metrics strong { font-weight: 600; font-variant-numeric: tabular-nums; }
.video-title { margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; line-height: 18px; }
.video-title:focus-visible { outline: 2px solid #fff; }
.video-empty { padding: 12px 0; font-size: 13px; color: #909399; }
.el-pagination { justify-content: flex-end; margin-top: 4px; }
</style>
