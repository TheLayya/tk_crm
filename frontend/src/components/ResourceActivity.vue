<template>
  <section class="resource-activity" v-loading="loading">
    <div class="activity-heading"><strong>最近轨迹</strong><span>{{ total }} 条</span></div>
    <div v-if="error" class="activity-empty">{{ error }}</div>
    <div v-else-if="!logs.length" class="activity-empty">暂无已记录轨迹</div>
    <div v-else class="activity-list">
      <div v-for="log in logs" :key="log.id" class="activity-row">
        <time>{{ formatTime(log.created_at) }}</time>
        <span class="activity-actor" :title="log.username">{{ log.username }}</span>
        <div class="activity-detail">
          <strong>{{ summary(log) }}</strong>
          <div v-for="(detail, index) in log.details || []" :key="index" class="activity-change">{{ detail }}</div>
        </div>
        <span v-if="log.result" :class="log.result === 'failed' ? 'activity-failed' : 'activity-success'">{{ log.result === 'failed' ? '失败' : '成功' }}</span>
      </div>
    </div>
    <el-pagination v-if="total > 5" :current-page="page" :page-size="5" :total="total" layout="prev, pager, next" small @current-change="$emit('page-change', $event)" />
    <div v-if="note" class="activity-note">{{ note }}</div>
  </section>
</template>

<script setup>
defineProps({ logs: { type: Array, default: () => [] }, total: { type: Number, default: 0 }, page: { type: Number, default: 1 }, loading: Boolean, error: String, note: String })
defineEmits(['page-change'])
const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
const summary = (log) => log.summary || ({ CREATE: '新增终端', UPDATE: '更新终端', DELETE: '删除终端' }[log.action] || '终端操作')
</script>

<style scoped>
.resource-activity { min-width: 0; font-size: 12px; }
.activity-heading { display: flex; align-items: center; gap: 8px; line-height: 24px; }
.activity-heading > span, .activity-note { color: #909399; font-size: 11px; }
.activity-list { max-height: 190px; overflow: auto; }
.activity-row { display: flex; align-items: flex-start; gap: 10px; padding: 5px 0; line-height: 20px; border-bottom: 1px solid #edf0f5; }
.activity-row time { flex: 0 0 85px; color: #909399; font-variant-numeric: tabular-nums; }
.activity-actor { flex: 0 0 65px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.activity-detail { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.activity-detail strong { font-weight: 500; color: #303133; }
.activity-change { color: #737d8c; font-size: 11px; }
.activity-success { color: #169b62; }
.activity-failed { color: #e5484d; }
.activity-empty { padding: 12px 0; color: #909399; }
.activity-note { margin-top: 4px; }
.el-pagination { justify-content: flex-end; margin-top: 4px; }
</style>
