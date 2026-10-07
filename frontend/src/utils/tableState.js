// State and complete-data querying shared by every CRM table; no Vue dependency.
const kinds = new Set(['text', 'number', 'date', 'enum'])
const has = (value, key) => Object.prototype.hasOwnProperty.call(value, key)
const object = value => value && typeof value === 'object' && !Array.isArray(value)
const empty = value => value === undefined || value === ''
const validField = key => typeof key === 'string' && key.length > 0 && !['__proto__', 'constructor', 'prototype'].includes(key)

export function normalizeQuery(value) {
  const query = object(value) ? value : {}
  const sortOrder = ['ascending', 'asc'].includes(query.sortOrder) ? 'ascending'
    : ['descending', 'desc'].includes(query.sortOrder) ? 'descending' : null
  const filters = {}
  for (const [field, filter] of Object.entries(object(query.filters) ? query.filters : {})) {
    if (!validField(field) || !object(filter) || !kinds.has(filter.type)) continue
    const normalized = { type: filter.type }
    if (filter.type === 'text') {
      if (typeof filter.value !== 'string' || !filter.value.trim()) continue
      normalized.value = filter.value
    } else if (filter.type === 'enum') {
      const choices = Array.isArray(filter.value) ? filter.value : [filter.value]
      const values = choices.filter(item => !empty(item) && (item === null || ['string', 'number', 'boolean'].includes(typeof item)))
      if (!values.length) continue
      normalized.value = Array.isArray(filter.value) ? [...new Set(values)] : values[0]
    } else {
      // An exact value takes precedence over stale range controls.
      const keys = has(filter, 'value') && !empty(filter.value) && filter.value !== null ? ['value'] : ['min', 'max']
      for (const key of keys) {
        if (!has(filter, key) || empty(filter[key]) || filter[key] === null) continue
        const converted = filter.type === 'number' ? number(filter[key]) : date(filter[key])
        if (converted !== null) normalized[key] = filter[key]
      }
      if (!['value', 'min', 'max'].some(key => has(normalized, key))) continue
      if (has(normalized, 'min') && has(normalized, 'max')) {
        const convert = filter.type === 'number' ? number : date
        if (convert(normalized.min) > convert(normalized.max)) continue
      }
    }
    filters[field] = normalized
  }
  return { sortBy: validField(query.sortBy) && sortOrder ? query.sortBy : null, sortOrder: validField(query.sortBy) ? sortOrder : null, filters }
}

const number = value => {
  if (value === null || empty(value) || typeof value === 'boolean' || object(value) || Array.isArray(value) || (typeof value === 'string' && !value.trim())) return null
  const result = Number(value)
  return Number.isFinite(result) ? result : null
}
const dateOnly = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
const date = value => {
  if (value === null || empty(value) || typeof value === 'boolean') return null
  if (typeof value !== 'string' && !(value instanceof Date)) return null
  const iso = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value.replace(' ', 'T') + 'Z' : value
  const result = new Date(iso).getTime()
  if (!Number.isFinite(result)) return null
  return dateOnly(value) && new Date(result).toISOString().slice(0, 10) !== value ? null : result
}

export function textValue(value) {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(textValue).join(' ')
  if (object(value)) return Object.values(value).map(textValue).join(' ')
  return String(value)
}

const metadata = value => typeof value === 'string' ? { type: value } : value || { type: 'text' }
const scalar = (value, kind) => {
  if (value === null || value === undefined) return null
  if (kind === 'number') return number(value)
  if (kind === 'date') return date(value)
  if (typeof value === 'boolean' || typeof value === 'number') return value
  return textValue(value).toLocaleLowerCase()
}
const compare = (left, right) => typeof left === 'number' && typeof right === 'number'
  ? left - right : typeof left === 'boolean' && typeof right === 'boolean'
    ? Number(left) - Number(right) : String(left).localeCompare(String(right), undefined, { numeric: false })
const matches = (raw, condition, fieldType) => {
  if (condition.type === 'text') return raw !== null && raw !== undefined && textValue(raw).toLocaleLowerCase().includes(condition.value.toLocaleLowerCase())
  if (condition.type === 'enum') {
    const selected = Array.isArray(condition.value) ? condition.value : [condition.value]
    return (Array.isArray(raw) ? raw : [raw]).some(value => selected.some(choice => scalar(value, fieldType) === scalar(choice, fieldType)))
  }
  const kind = condition.type
  const actual = scalar(raw, kind)
  if (actual === null) return false
  return ['value', 'min', 'max'].every(key => {
    if (!has(condition, key)) return true
    const bound = scalar(condition[key], kind)
    if (kind === 'date' && dateOnly(condition[key]) && (key === 'value' || key === 'max')) {
      return actual < bound + 86400000 && (key !== 'value' || actual >= bound)
    }
    return key === 'value' ? actual === bound : key === 'min' ? actual >= bound : actual <= bound
  })
}

// Always filter/sort the complete collection before optionally selecting a page.
export function queryRows(data, value, fields = {}, pagination) {
  const query = normalizeQuery(value)
  let rows = (Array.isArray(data) ? data : []).map((row, index) => ({ row, index }))
  rows = rows.filter(({ row }) => Object.entries(query.filters).every(([field, filter]) => !has(fields, field) || matches(row[field], filter, metadata(fields[field]).type)))
  if (query.sortBy && has(fields, query.sortBy)) {
    const kind = metadata(fields[query.sortBy]).type
    const direction = query.sortOrder === 'descending' ? -1 : 1
    rows.sort((left, right) => {
      const a = scalar(left.row[query.sortBy], kind), b = scalar(right.row[query.sortBy], kind)
      if (a === null || b === null) return a === b ? left.index - right.index : a === null ? 1 : -1
      return direction * compare(a, b) || left.index - right.index
    })
  }
  const result = rows.map(item => item.row)
  if (!pagination) return result
  const page = Math.max(1, Math.trunc(Number(pagination.page) || 1))
  const size = Math.max(1, Math.trunc(Number(pagination.pageSize) || result.length || 1))
  return result.slice((page - 1) * size, page * size)
}

const aliases = {
  columnKey: 'column-key', filterType: 'filter-type', filterOptions: 'filter-options', tableFields: 'table-fields',
  defaultHidden: 'default-hidden', legacyColumnGroup: 'legacy-column-group', tableToolsDisabled: 'table-tools-disabled',
}
const flags = new Set(['defaultHidden', 'tableToolsDisabled'])
export function normalizeColumnProps(attrs = {}) {
  const result = { ...attrs }
  for (const [name, alias] of Object.entries(aliases)) {
    const value = has(attrs, name) ? attrs[name] : attrs[alias]
    delete result[alias]
    if (value !== undefined) result[name] = flags.has(name) ? value !== false && value !== 'false' && value !== null : value
  }
  return result
}

export function stripColumnMetadata(attrs = {}) {
  const result = { ...attrs }
  for (const [name, alias] of Object.entries(aliases)) {
    if (name !== 'columnKey') { delete result[name]; delete result[alias] }
  }
  return result
}

export function normalizeLayout(value) {
  const layout = object(value) ? value : {}
  const keys = value => [...new Set((Array.isArray(value) ? value : []).filter(validField))]
  const widths = {}
  for (const [key, value] of Object.entries(object(layout.widths) ? layout.widths : {})) {
    const width = Number(value)
    if (validField(key) && Number.isFinite(width) && width >= 24 && width <= 2000) widths[key] = Math.round(width)
  }
  return { order: keys(layout.order), hidden: keys(layout.hidden), widths }
}

const storageKey = (kind, tableId, user) => `tk-crm:table-${kind}:${encodeURIComponent(String(user || 'anonymous'))}:${encodeURIComponent(String(tableId))}`
export const queryStorageKey = (tableId, user) => storageKey('query', tableId, user)
export const layoutStorageKey = (tableId, user) => storageKey('layout', tableId, user)
const read = (storage, key, normalize) => { try { return normalize(JSON.parse(storage?.getItem(key) || 'null')) } catch { return normalize(null) } }
const save = (storage, key, value, normalize) => { const result = normalize(value); try { storage?.setItem(key, JSON.stringify(result)) } catch { /* Storage can be denied by the browser. */ } return result }
const browserStorage = name => { try { return globalThis[name] } catch { return undefined } }
export const readQuery = (tableId, user, storage = browserStorage('sessionStorage')) => read(storage, queryStorageKey(tableId, user), normalizeQuery)
export const saveQuery = (tableId, user, value, storage = browserStorage('sessionStorage')) => save(storage, queryStorageKey(tableId, user), value, normalizeQuery)
export const readLayout = (tableId, user, storage = browserStorage('localStorage')) => read(storage, layoutStorageKey(tableId, user), normalizeLayout)
export const saveLayout = (tableId, user, value, storage = browserStorage('localStorage')) => save(storage, layoutStorageKey(tableId, user), value, normalizeLayout)
