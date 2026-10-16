<template>
  <el-dialog :model-value="modelValue" :title="title" width="min(800px, 94vw)" @update:model-value="$emit('update:modelValue', $event)" @closed="onClosed">
    <p v-if="targetLabel" class="history-target">{{ targetLabel }}</p>
    <div v-loading="loading" class="failure-history-content">
      <el-alert v-if="errorMessage" :title="errorMessage" type="error" :closable="false"><template #default><el-button link type="danger" @click="load">重试</el-button></template></el-alert>
      <el-empty v-else-if="!loading && !reports.length" description="暂无失败记录和售后凭证" :image-size="64" />
      <article v-for="report in reports" :key="report.id" class="failure-history-entry">
        <header><el-tag size="small" type="danger">{{ report.kind === 'card_key' ? '卡密无效' : '邮箱注册失败' }}</el-tag><strong>{{ report.username }}</strong><time>{{ formatDate(report.created_at) }}</time></header>
        <div class="history-context"><span v-if="report.project_name">{{ report.project_name }}</span><span v-if="report.batch_name" :title="report.batch_no || ''">批次：{{ report.batch_name }}{{ report.batch_no ? ' · ' + report.batch_no : '' }}</span><span v-if="report.platform">{{ report.platform }}</span><span>{{ report.image_count || report.images?.length || 0 }} 张截图</span></div>
        <p v-if="report.remark" class="history-remark">{{ report.remark }}</p>
        <div v-if="report.images?.length" class="history-images">
          <div v-for="(shot, index) in report.images" :key="shot.url" class="history-image">
            <el-image v-if="imageUrls[shot.url]" :src="imageUrls[shot.url]" :preview-src-list="[imageUrls[shot.url]]" preview-teleported fit="contain" :alt="shot.name || `截图 ${index + 1}`" />
            <el-button v-else :loading="imageLoading[shot.url]" @click="loadImage(shot)">查看截图 {{ index + 1 }}</el-button>
            <span :title="shot.name">{{ shot.name || `截图 ${index + 1}` }}</span><small v-if="imageErrors[shot.url]" class="history-image-error">{{ imageErrors[shot.url] }}</small>
          </div>
        </div>
      </article>
    </div>
    <template #footer><el-button @click="$emit('update:modelValue', false)">关闭</el-button></template>
  </el-dialog>
</template>

<script setup>
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { getFailureReports, getFailureScreenshot } from '@/api/failure_reports'

const props = defineProps({ modelValue: Boolean, source: Object, title: { type: String, default: '失败记录与售后凭证' }, targetLabel: { type: String, default: '' } })
defineEmits(['update:modelValue'])
const reports = ref([])
const loading = ref(false)
const errorMessage = ref('')
const imageUrls = reactive({})
const imageLoading = reactive({})
const imageErrors = reactive({})
let version = 0
const clear = () => { version++; reports.value = []; loading.value = false; errorMessage.value = ''; Object.values(imageUrls).forEach(url => URL.revokeObjectURL(url)); for (const state of [imageUrls, imageLoading, imageErrors]) for (const key of Object.keys(state)) delete state[key] }
const onClosed = () => { if (!props.modelValue) clear() }
const load = async () => {
  clear()
  if (!props.modelValue || !props.source) return
  const current = version
  const source = { ...props.source }
  loading.value = true
  try { const result = await getFailureReports(source); if (current === version && props.modelValue) reports.value = result }
  catch (error) { if (current === version) { const detail = error.response?.data?.detail; errorMessage.value = typeof detail === 'string' ? detail : '失败记录加载失败，请重试' } }
  finally { if (current === version) loading.value = false }
}
const loadImage = async shot => {
  if (imageLoading[shot.url] || imageUrls[shot.url]) return
  const current = version
  imageLoading[shot.url] = true
  delete imageErrors[shot.url]
  try { const blob = await getFailureScreenshot(shot.url); if (current === version && props.modelValue) imageUrls[shot.url] = URL.createObjectURL(blob) }
  catch { if (current === version) imageErrors[shot.url] = '图片加载失败，点击重试' }
  finally { if (current === version) imageLoading[shot.url] = false }
}
const formatDate = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
watch(() => [props.modelValue, props.source], () => { if (props.modelValue) load(); else clear() })
onBeforeUnmount(clear)
</script>

<style scoped>
.history-target { font-weight:600; color:#203047; overflow-wrap:anywhere; }
.failure-history-content { min-height:100px; max-height:65vh; overflow:auto; }
.failure-history-entry { padding:14px 0; border-bottom:1px solid #e2e8f0; }
.failure-history-entry:first-child { padding-top:0; }
.failure-history-entry header { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.failure-history-entry time,.history-context { color:#64748b; font-size:12px; }
.history-context { display:flex; flex-wrap:wrap; gap:12px; margin-top:7px; }
.history-remark { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.6; color:#334155; }
.history-images { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:10px; }
.history-image { min-width:0; display:flex; flex-direction:column; align-items:stretch; justify-content:center; gap:6px; padding:8px; border:1px solid #e2e8f0; border-radius:6px; }
.history-image .el-image { height:140px; width:100%; cursor:zoom-in; }
.history-image span { color:#64748b; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.history-image-error { color:#dc2626; font-size:12px; }
@media(max-width:600px) { .history-images { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
