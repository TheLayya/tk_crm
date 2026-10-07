import { computed, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { normalizeQuery, readQuery, saveQuery } from '@/utils/tableState'

export function useTableQuery(tableId) {
  const auth = useAuthStore()
  const username = computed(() => auth.user?.username || 'anonymous')
  const tableQuery = ref(readQuery(tableId, username.value))
  watch(username, () => { tableQuery.value = readQuery(tableId, username.value) })
  watch(tableQuery, value => saveQuery(tableId, username.value, value), { deep: true, flush: 'sync' })
  const queryParams = computed(() => {
    const query = normalizeQuery(tableQuery.value)
    const params = {}
    if (query.sortBy && query.sortOrder) {
      params.sort_by = query.sortBy
      params.sort_order = query.sortOrder === 'descending' ? 'desc' : 'asc'
    }
    if (Object.keys(query.filters).length) params.table_filters = JSON.stringify(query.filters)
    return params
  })
  const resetTableQuery = () => { tableQuery.value = normalizeQuery(null) }
  return { tableQuery, queryParams, resetTableQuery }
}
