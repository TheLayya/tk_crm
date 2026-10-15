import { onBeforeUnmount, onMounted, reactive } from 'vue'

// Keep table footers reachable while short screens retain a usable scroll area.
export function useViewportTableHeight(root, tables) {
  const heights = reactive(Object.fromEntries(tables.map(table => [table.id, table.max])))
  let frame = 0
  let observer
  const refresh = () => {
    if (frame) cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      frame = 0
      const element = root.value?.$el || root.value
      for (const table of tables) {
        const target = element?.querySelector(`[data-table-id="${table.id}"] .el-table`)
        if (!target?.getClientRects().length) continue
        const top = target.getBoundingClientRect().top
        heights[table.id] = Math.max(140, Math.min(table.max, Math.floor(window.innerHeight - top - table.bottom)))
      }
    })
  }
  onMounted(() => {
    observer = new ResizeObserver(refresh)
    const element = root.value?.$el || root.value
    if (element) observer.observe(element)
    window.addEventListener('resize', refresh)
    refresh()
  })
  onBeforeUnmount(() => {
    observer?.disconnect()
    window.removeEventListener('resize', refresh)
    if (frame) cancelAnimationFrame(frame)
  })
  return { heights, refresh }
}
