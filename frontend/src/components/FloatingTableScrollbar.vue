<template>
  <div v-show="visible" class="floating-table-scrollbar" :style="position" :class="{ 'floating-table-scrollbar--mobile': isMobile }">
    <div ref="scrollbar" class="floating-table-scrollbar__track" @scroll="handleScroll">
      <div class="floating-table-scrollbar__content" :style="{ width: contentWidth + 'px' }"></div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

const visible = ref(false)
const position = ref({})
const contentWidth = ref(0)
const scrollbar = ref(null)
const isMobile = ref(window.innerWidth <= 768)
let target = null
let syncing = false
let scanTimer = null
let observer = null

const update = () => {
  isMobile.value = window.innerWidth <= 768
  const candidates = [...document.querySelectorAll('.main-content .el-table__body-wrapper .el-scrollbar__wrap')]
    .filter(el => el.scrollWidth > el.clientWidth + 2)
    .filter(el => {
      const rect = el.closest('.el-table')?.getBoundingClientRect()
      const main = el.closest('.main-content')?.getBoundingClientRect()
      const bottom = Math.min(window.innerHeight - (isMobile.value ? 65 : 8), main?.bottom ?? window.innerHeight)
      return rect && rect.width > 0 && rect.bottom > bottom && rect.top < bottom - 40
    })
  const nextTarget = candidates[0] || null
  if (nextTarget !== target) {
    if (target) target.removeEventListener('scroll', handleTargetScroll)
    target = nextTarget
    if (target) target.addEventListener('scroll', handleTargetScroll, { passive: true })
  }
  if (!target) {
    visible.value = false
    return
  }
  const rect = target.getBoundingClientRect()
  const main = target.closest('.main-content').getBoundingClientRect()
  const left = Math.max(0, rect.left, main.left)
  const right = Math.min(window.innerWidth, rect.right, main.right)
  position.value = { left: left + 'px', width: Math.max(0, right - left) + 'px' }
  contentWidth.value = target.scrollWidth + Math.max(0, right - left) - target.clientWidth
  visible.value = true
  if (scrollbar.value && !syncing) scrollbar.value.scrollLeft = target.scrollLeft
}

const handleTargetScroll = () => {
  if (!scrollbar.value || syncing) return
  syncing = true
  scrollbar.value.scrollLeft = target?.scrollLeft || 0
  syncing = false
}

const handleScroll = () => {
  if (!target || syncing) return
  syncing = true
  target.scrollLeft = scrollbar.value?.scrollLeft || 0
  syncing = false
}

const scheduleUpdate = () => {
  clearTimeout(scanTimer)
  scanTimer = setTimeout(() => nextTick(update), 80)
}

onMounted(() => {
  window.addEventListener('scroll', scheduleUpdate, { passive: true, capture: true })
  window.addEventListener('resize', scheduleUpdate, { passive: true })
  observer = new MutationObserver(scheduleUpdate)
  const main = document.querySelector('.main-content')
  if (main) observer.observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] })
  update()
})

onUnmounted(() => {
  clearTimeout(scanTimer)
  window.removeEventListener('scroll', scheduleUpdate, true)
  window.removeEventListener('resize', scheduleUpdate)
  observer?.disconnect()
  target?.removeEventListener('scroll', handleTargetScroll)
})
</script>

<style scoped>
.floating-table-scrollbar { position: fixed; z-index: 100; bottom: 8px; height: 18px; pointer-events: none; }
.floating-table-scrollbar__track { height: 18px; overflow-x: auto; overflow-y: hidden; pointer-events: auto; border-radius: 9px; background: rgba(144, 147, 153, 0.16); box-shadow: 0 1px 5px rgba(0, 0, 0, 0.12); }
.floating-table-scrollbar__track::-webkit-scrollbar { height: 14px; }
.floating-table-scrollbar__track::-webkit-scrollbar-track { background: transparent; }
.floating-table-scrollbar__track::-webkit-scrollbar-thumb { background: rgba(96, 98, 102, 0.58); border-radius: 7px; border: 3px solid transparent; background-clip: content-box; }
.floating-table-scrollbar__content { height: 1px; }
.floating-table-scrollbar--mobile { bottom: calc(49px + env(safe-area-inset-bottom) + 8px); }
</style>
