<script>
import { computed, defineComponent, Fragment, h, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElButton, ElCheckbox, ElDatePicker, ElDialog, ElIcon, ElInput, ElMessage, ElOption, ElPopover, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { Filter, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { layoutStorageKey, normalizeColumnProps, normalizeLayout, normalizeQuery, queryRows, readLayout, readQuery, saveLayout, saveQuery, stripColumnMetadata, textValue } from '@/utils/tableState'

const columnNodes = nodes => (Array.isArray(nodes) ? nodes : [nodes]).flatMap(node => {
  if (!node || typeof node !== 'object') return []
  if (node.type === Fragment) return columnNodes(node.children || [])
  return node.type === ElTableColumn || node.type?.name === 'ElTableColumn' ? [node] : []
})
const unique = values => [...new Set(values)]
const inferType = prop => /(_at|_date)$/.test(prop || '') || prop === 'time' ? 'date' : /(count|price|amount|latency|port|change|year)$/.test(prop || '') ? 'number' : 'text'
const flag = value => value === true || value === ''

export default defineComponent({
  name: 'CrmTable', inheritAttrs: false,
  props: { tableId: { type: String, required: true }, data: { type: Array, default: () => [] }, remote: Boolean, query: { type: Object, default: null }, page: { type: Number, default: null }, pageSize: { type: Number, default: null }, legacyColumnConfig: { type: String, default: '' } },
  emits: ['query-change', 'total-change'],
  setup(props, { attrs, slots, emit, expose }) {
    const auth = useAuthStore()
    const username = computed(() => auth.user?.username || 'anonymous')
    const table = ref(null), container = ref(null), settingsOpen = ref(false)
    const localQuery = ref(readQuery(props.tableId, username.value)), layout = ref(readLayout(props.tableId, username.value))
    const drafts = reactive({}), sortFields = reactive({})
    let columns = [], fields = {}, lastTotal = null, lastSignature = '', syncingSort = false, layoutPending = false, legacy = null
    const hasSavedLayout = () => { try { return Boolean(localStorage.getItem(layoutStorageKey(props.tableId, username.value))) } catch { return false } }
    const readLegacy = () => { try { const saved = props.legacyColumnConfig && !hasSavedLayout() ? JSON.parse(localStorage.getItem(props.legacyColumnConfig) || 'null') : null; return Array.isArray(saved) ? saved : null } catch { return null } }
    legacy = readLegacy()
    const currentQuery = computed(() => normalizeQuery(props.remote ? props.query : localQuery.value))
    const locked = column => ['selection', 'expand', 'index'].includes(column.meta.type) || column.key === 'actions'
    const visible = column => locked(column) || (layout.value.order.includes(column.key) ? !layout.value.hidden.includes(column.key) : legacy && column.meta.legacyColumnGroup ? legacy.includes(column.meta.legacyColumnGroup) : !flag(column.meta.defaultHidden))
    const ordered = () => {
      const business = columns.filter(column => !locked(column)), keys = unique([...layout.value.order, ...business.map(column => column.key)])
      return [...columns.filter(column => locked(column) && column.key !== 'actions'), ...keys.map(key => business.find(column => column.key === key)).filter(Boolean), ...columns.filter(column => column.key === 'actions')]
    }
    const synchronizeSort = () => {
      if (!table.value) return
      const states = table.value.store?.states
      const query = currentQuery.value
      const requested = query.sortBy && fields[query.sortBy] ? query : { sortBy: null, sortOrder: null }
      const liveColumn = requested.sortBy ? states?.columns?.value?.find(column => column.property === requested.sortBy) : null
      if ((states?.sortProp?.value || null) === requested.sortBy && (states?.sortOrder?.value || null) === requested.sortOrder && (!requested.sortBy || liveColumn?.order === requested.sortOrder)) return
      syncingSort = true
      if (requested.sortBy) table.value.sort(requested.sortBy, requested.sortOrder)
      else table.value.clearSort()
      syncingSort = false
    }
    const scheduleLayout = () => { if (layoutPending) return; layoutPending = true; nextTick(() => { layoutPending = false; table.value?.doLayout(); synchronizeSort() }) }
    const changeQuery = value => { const query = normalizeQuery(value); if (!props.remote) { localQuery.value = query; saveQuery(props.tableId, username.value, query) } emit('query-change', query); scheduleLayout() }
    const removeFilter = field => { const filters = { ...currentQuery.value.filters }; delete filters[field]; changeQuery({ ...currentQuery.value, filters }) }
    const materializedLayout = () => ({ order: unique([...ordered().filter(column => !locked(column)).map(column => column.key), ...layout.value.order]), hidden: unique([...layout.value.hidden.filter(key => !columns.some(column => column.key === key)), ...columns.filter(column => !locked(column) && !visible(column)).map(column => column.key)]), widths: { ...layout.value.widths } })
    const persistLayout = value => { layout.value = saveLayout(props.tableId, username.value, value); legacy = null; scheduleLayout() }
    const showColumn = (key, show) => { const next = materializedLayout(); next.hidden = next.hidden.filter(hidden => hidden !== key); if (!show) next.hidden.push(key); persistLayout(next) }
    const moveColumn = (key, target) => { const next = materializedLayout(), from = next.order.indexOf(key), to = next.order.indexOf(target); if (from < 0 || to < 0 || from === to) return; next.order.splice(from, 1); next.order.splice(to, 0, key); persistLayout(next) }
    const columnFields = column => Array.isArray(column.meta.tableFields) && column.meta.tableFields.length ? column.meta.tableFields.map(field => ({ ...field, type: field.type || inferType(field.prop) })) : column.meta.prop ? [{ prop: column.meta.prop, label: column.meta.label, type: column.meta.filterType || inferType(column.meta.prop), options: column.meta.filterOptions }] : []
    const openFilter = column => {
      const choices = columnFields(column), field = choices.find(item => currentQuery.value.filters[item.prop])?.prop || sortFields[column.key] || choices[0]?.prop, condition = currentQuery.value.filters[field]
      drafts[column.key] = { field, value: condition?.value ?? '', min: condition?.min ?? '', max: condition?.max ?? '', dates: condition ? [condition.min || condition.value || '', condition.max || condition.value || ''] : null }
    }
    const selectedField = column => columnFields(column).find(field => field.prop === drafts[column.key]?.field) || columnFields(column)[0]
    const applyFilter = column => {
      const field = selectedField(column), draft = drafts[column.key]
      if (!field || !draft) return
      const condition = field.type === 'number' ? { type: 'number', min: draft.min, max: draft.max } : field.type === 'date' ? { type: 'date', min: draft.dates?.[0], max: draft.dates?.[1] } : { type: field.type, value: draft.value }
      const normalized = normalizeQuery({ ...currentQuery.value, filters: { ...currentQuery.value.filters, [field.prop]: condition } })
      const entered = field.type === 'number' ? draft.min !== '' || draft.max !== '' : field.type === 'date' ? Boolean(draft.dates?.length) : Array.isArray(draft.value) ? draft.value.length > 0 : draft.value !== ''
      if (entered && !normalized.filters[field.prop]) return ElMessage.warning('请填写有效条件，最小值或开始日期应不大于最大值或结束日期')
      changeQuery(normalized)
    }
    const sortField = (column, order) => { const field = selectedField(column); if (!field) return; sortFields[column.key] = field.prop; changeQuery({ ...currentQuery.value, sortBy: field.prop, sortOrder: order }) }
    const enumOptions = (column, field) => {
      if (Array.isArray(field?.options)) return field.options
      if (Array.isArray(column.meta.filterOptions)) return column.meta.filterOptions
      const values = unique(props.data.flatMap(row => Array.isArray(row[field.prop]) ? row[field.prop] : [row[field.prop]]).filter(value => value === null || ['string', 'number', 'boolean'].includes(typeof value)))
      return values.map(value => ({ value, label: value === null ? '未填写' : typeof value === 'boolean' ? value ? '是' : '否' : String(value) }))
    }
    const filterPanel = column => {
      const draft = drafts[column.key] || { field: columnFields(column)[0]?.prop, value: '', min: '', max: '', dates: null }, field = selectedField(column)
      if (!field) return []
      const update = (key, value) => { if (!drafts[column.key]) drafts[column.key] = draft; drafts[column.key][key] = value }, choices = columnFields(column)
      const input = field.type === 'enum' ? h(ElSelect, { modelValue: Array.isArray(draft.value) ? draft.value : draft.value === '' ? [] : [draft.value], multiple: true, clearable: true, filterable: true, placeholder: '选择值', 'onUpdate:modelValue': value => update('value', value) }, () => enumOptions(column, field).map(option => h(ElOption, { key: JSON.stringify(option.value), ...option })))
        : field.type === 'number' ? h('div', { class: 'crm-table-range' }, [h(ElInput, { modelValue: draft.min, type: 'number', placeholder: '最小值', 'onUpdate:modelValue': value => update('min', value) }), h('span', '至'), h(ElInput, { modelValue: draft.max, type: 'number', placeholder: '最大值', 'onUpdate:modelValue': value => update('max', value) })])
          : field.type === 'date' ? h(ElDatePicker, { modelValue: draft.dates, type: 'daterange', valueFormat: 'YYYY-MM-DD', startPlaceholder: '开始日期', endPlaceholder: '结束日期', 'onUpdate:modelValue': value => update('dates', value) })
            : h(ElInput, { modelValue: draft.value, clearable: true, placeholder: '包含文字', 'onUpdate:modelValue': value => update('value', value), onKeyup: event => { if (event.key === 'Enter') applyFilter(column) } })
      return h('div', { class: 'crm-table-filter-panel' }, [choices.length > 1 ? h(ElSelect, { modelValue: draft.field, 'onUpdate:modelValue': value => { drafts[column.key] = { field: value, value: '', min: '', max: '', dates: null }; sortFields[column.key] = value } }, () => choices.map(choice => h(ElOption, { label: choice.label || choice.prop, value: choice.prop, key: choice.prop }))) : null, input,
        h('div', { class: 'crm-table-filter-actions' }, [h(ElButton, { size: 'small', type: 'primary', onClick: () => applyFilter(column) }, () => '查询'), h(ElButton, { size: 'small', onClick: () => { removeFilter(field.prop); openFilter(column) } }, () => '清空')]),
        choices.length > 1 ? h('div', { class: 'crm-table-filter-actions' }, [h(ElButton, { size: 'small', onClick: () => sortField(column, 'ascending') }, () => '按此字段升序'), h(ElButton, { size: 'small', onClick: () => sortField(column, 'descending') }, () => '按此字段降序')]) : null])
    }
    const renderColumn = (column, signature) => {
      const meta = column.meta, native = stripColumnMetadata(meta), choices = columnFields(column), business = !locked(column), queryable = business && !meta.tableToolsDisabled && choices.length > 0, query = currentQuery.value
      const selectedSort = choices.find(field => field.prop === query.sortBy)?.prop || sortFields[column.key] || meta.prop
      if (business) delete native.fixed
      if (column.key === 'actions') native.fixed = 'right'
      if (meta.type === 'selection' || meta.type === 'expand') native.fixed = 'left'
      if (layout.value.widths[column.key]) native.width = layout.value.widths[column.key]
      native.key = column.key + ':' + signature; native.columnKey = column.key
      if (queryable) { native.sortable = 'custom'; native.prop = selectedSort }
      const original = column.node.children && typeof column.node.children === 'object' && !Array.isArray(column.node.children) ? column.node.children : {}
      const originalSlots = Object.fromEntries(Object.entries(original).filter(([key, value]) => !key.startsWith('_') && typeof value === 'function').map(([key, render]) => [key, (...args) => { const result = render(...args); return Array.isArray(result) ? result : result ? [result] : [] }]))
      const renderedSlots = queryable ? { ...originalSlots, header: scope => [h('span', { class: 'crm-table-header' }, [h('span', { class: 'crm-table-header-label' }, originalSlots.header ? originalSlots.header(scope) : meta.label),
        h(ElPopover, { trigger: 'click', placement: 'bottom-start', width: 320, onShow: () => openFilter(column) }, { reference: () => [h('button', { type: 'button', class: ['crm-table-filter-button', choices.some(field => query.filters[field.prop]) && 'is-active'], 'aria-label': `${meta.label || column.key}筛选`, title: '筛选', onClick: event => event.stopPropagation() }, [h(ElIcon, null, () => h(Filter))])], default: () => filterPanel(column) })]) ] } : originalSlots
      return h(column.node.type, native, renderedSlots)
    }
    const settingsDialog = () => h(ElDialog, { modelValue: settingsOpen.value, 'onUpdate:modelValue': value => { settingsOpen.value = value }, title: '列设置', width: 'min(600px, 94vw)', class: 'crm-table-settings', appendToBody: true }, {
      default: () => [h('p', { class: 'crm-table-settings-hint' }, '勾选显示列；拖动或使用箭头调整顺序。选择、展开和操作列固定。'), ...ordered().map((column, index, list) => {
        const movable = !locked(column)
        return h('div', { key: column.key, class: ['crm-table-settings-row', !movable && 'is-locked'], draggable: movable, onDragstart: event => { event.dataTransfer?.setData('text/plain', column.key) }, onDragover: event => { if (movable) event.preventDefault() }, onDrop: event => { event.preventDefault(); if (movable) moveColumn(event.dataTransfer?.getData('text/plain'), column.key) } }, [h('span', { class: 'crm-table-drag-handle', 'aria-hidden': true }, movable ? '⋮⋮' : '·'),
          h(ElCheckbox, { modelValue: visible(column), disabled: !movable, 'onUpdate:modelValue': value => showColumn(column.key, value) }, () => column.meta.label || ({ selection: '选择', expand: '展开', index: '序号' }[column.meta.type]) || column.key),
          h('div', { class: 'crm-table-column-moves' }, [h(ElButton, { size: 'small', disabled: !movable || !list[index - 1] || locked(list[index - 1]), 'aria-label': `${column.meta.label || column.key}上移`, onClick: () => moveColumn(column.key, list[index - 1]?.key) }, () => '↑'), h(ElButton, { size: 'small', disabled: !movable || !list[index + 1] || locked(list[index + 1]), 'aria-label': `${column.meta.label || column.key}下移`, onClick: () => moveColumn(column.key, list[index + 1]?.key) }, () => '↓')])])
      })],
      footer: () => [h(ElButton, { onClick: () => { persistLayout({ order: [], hidden: [], widths: {} }); layout.value = normalizeLayout(null); settingsOpen.value = false } }, () => '恢复默认布局'), h(ElButton, { type: 'primary', onClick: () => { settingsOpen.value = false } }, () => '完成')],
    })
    watch(() => [props.tableId, username.value], () => { localQuery.value = readQuery(props.tableId, username.value); layout.value = readLayout(props.tableId, username.value); legacy = readLegacy(); lastTotal = null; scheduleLayout() })
    watch(() => JSON.stringify(currentQuery.value), scheduleLayout)
    onMounted(scheduleLayout)
    const exposed = { get $el() { return table.value?.$el || container.value } }
    for (const method of ['toggleRowExpansion', 'toggleRowSelection', 'clearSelection', 'getSelectionRows', 'doLayout', 'sort', 'clearSort']) exposed[method] = (...args) => table.value?.[method]?.(...args)
    expose(exposed)
    return () => {
      columns = columnNodes(slots.default?.() || []).map((node, index) => { const meta = normalizeColumnProps(node.props || {}); return { node, meta, key: meta.columnKey || meta.prop || `column-${index}` } })
      fields = Object.fromEntries(columns.filter(column => !locked(column) && !column.meta.tableToolsDisabled).flatMap(column => columnFields(column).map(field => [field.prop, field])))
      const query = currentQuery.value, allRows = props.remote ? props.data : queryRows(props.data, query, fields)
      if (lastTotal !== allRows.length) { lastTotal = allRows.length; nextTick(() => emit('total-change', allRows.length)) }
      const rows = !props.remote && props.page !== null && props.pageSize !== null ? allRows.slice((Math.max(1, props.page) - 1) * props.pageSize, Math.max(1, props.page) * props.pageSize) : allRows
      const displayed = ordered().filter(visible), signature = displayed.map(column => column.key).join('|'), filters = Object.entries(query.filters)
      if (signature !== lastSignature) { lastSignature = signature; scheduleLayout() }
      return h('div', { ref: container, class: 'crm-table-wrapper', 'data-table-id': props.tableId }, [h('div', { class: 'crm-table-toolbar' }, [
        h('div', { class: 'crm-table-active-filters' }, [query.sortBy ? h(ElTag, { closable: true, size: 'small', onClose: () => changeQuery({ ...query, sortBy: null, sortOrder: null }) }, () => `${fields[query.sortBy]?.label || query.sortBy} ${query.sortOrder === 'descending' ? '降序' : '升序'}`) : null, ...filters.map(([field, condition]) => h(ElTag, { key: field, closable: true, size: 'small', onClose: () => removeFilter(field) }, () => `${fields[field]?.label || field}：${condition.value !== undefined ? textValue(condition.value) || '未填写' : `${condition.min ?? '不限'} 至 ${condition.max ?? '不限'}`}`))]),
        h(ElButton, { size: 'small', disabled: !query.sortBy && !filters.length, onClick: () => changeQuery(null) }, () => '重置查询'), h(ElButton, { size: 'small', icon: Setting, onClick: () => { settingsOpen.value = true } }, () => '列设置')]),
        h(ElTable, { ...attrs, ref: table, data: rows, border: attrs.border ?? true, onSortChange: event => { attrs.onSortChange?.(event); if (!syncingSort) changeQuery({ ...currentQuery.value, sortBy: event.order ? event.prop : null, sortOrder: event.order }) }, onHeaderDragend: (width, oldWidth, column, event) => { attrs.onHeaderDragend?.(width, oldWidth, column, event); const next = materializedLayout(); next.widths[column.columnKey || column.property] = width; persistLayout(next) } }, { ...slots, default: () => displayed.map(column => renderColumn(column, signature)) }), settingsDialog()])
    }
  },
})
</script>

<style>
.crm-table-wrapper { width: 100%; min-width: 0; }
.crm-table-toolbar { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.crm-table-active-filters { display: flex; flex: 1; flex-wrap: wrap; gap: 6px; min-width: 0; }
.crm-table-header { display: inline-flex; align-items: center; gap: 4px; max-width: calc(100% - 24px); vertical-align: middle; }
.crm-table-header-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.crm-table-wrapper .el-table th .cell { white-space: nowrap; }
.crm-table-filter-button { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 3px; color: #909399; background: transparent; cursor: pointer; }
.crm-table-filter-button:hover, .crm-table-filter-button.is-active { color: #409eff; background: #ecf5ff; }
.crm-table-filter-panel { display: flex; flex-direction: column; gap: 12px; }
.crm-table-filter-panel .el-select, .crm-table-filter-panel .el-date-editor { width: 100%; box-sizing: border-box; }
.crm-table-range { display: flex; align-items: center; gap: 8px; }
.crm-table-filter-actions { display: flex; justify-content: flex-end; gap: 8px; }
.crm-table-filter-actions .el-button + .el-button { margin-left: 0; }
.crm-table-settings-hint { margin-top: 0; color: #909399; font-size: 12px; }
.crm-table-settings .el-dialog__body { max-height: 55vh; overflow: auto; }
.crm-table-settings-row { display: flex; align-items: center; gap: 10px; min-height: 42px; padding: 4px 0; border-bottom: 1px solid #ebeef5; }
.crm-table-settings-row .el-checkbox { margin-right: 0; min-width: 0; }
.crm-table-drag-handle { width: 16px; flex-shrink: 0; color: #909399; cursor: grab; }
.crm-table-settings-row.is-locked .crm-table-drag-handle { cursor: default; }
.crm-table-column-moves { display: flex; gap: 4px; margin-left: auto; }
.crm-table-column-moves .el-button + .el-button { margin-left: 0; }
</style>
