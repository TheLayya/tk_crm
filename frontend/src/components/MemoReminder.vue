<template>
  <el-badge :value="due.length" :hidden="!due.length" :max="99">
    <el-button link aria-label="备忘提醒" title="备忘提醒" @click="router.push('/work-items')"><el-icon :size="19"><Bell /></el-icon></el-button>
  </el-badge>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import { getWorkItemSummary } from '@/api/work_items'

const router = useRouter()
const due = ref([])
const notified = new Set()
let timer
let stopped = false
const refresh = async () => {
  try {
    const summary = await getWorkItemSummary()
    if (stopped) return
    due.value = summary.due || []
    for (const item of due.value) {
      if (notified.has(item.id)) continue
      notified.add(item.id)
      ElNotification({ title: '备忘到期提醒', message: item.title, type: 'warning', onClick: () => router.push('/work-items') })
    }
  } catch (_) {}
}
onMounted(() => { refresh(); timer = window.setInterval(refresh, 60000) })
onUnmounted(() => { stopped = true; window.clearInterval(timer) })
</script>
