// Run with: node frontend/tests/table-state.cjs (no browser or dependencies).
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

async function main() {
  const source = fs.readFileSync(path.join(__dirname, '../src/utils/tableState.js'), 'utf8')
  const state = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
  const { normalizeQuery, queryRows, normalizeColumnProps, stripColumnMetadata, readQuery, saveQuery, readLayout, saveLayout, queryStorageKey, layoutStorageKey } = state
  const fields = { amount: { type: 'number' }, time: { type: 'date' }, name: { type: 'text' }, tags: { type: 'enum' }, enabled: { type: 'enum' } }
  const rows = [
    { id: 1, amount: 10, time: '2026-10-07T23:59:59.999Z', name: 'Alpha', tags: ['a', 'b'], enabled: false },
    { id: 2, amount: 2, time: '2026-10-08T00:00:00Z', name: 'alpha', tags: ['b'], enabled: true },
    { id: 3, amount: 0, time: '2026-10-07T00:00:00', name: { name: 'Nested', values: ['Gamma'] }, tags: ['c'], enabled: false },
    { id: 4, amount: null, time: null, name: null, tags: [], enabled: null },
    { id: 5, amount: 2, time: '2026-10-06T09:00:00Z', name: 'Beta', tags: ['d'], enabled: true },
  ]
  const snapshot = JSON.stringify(rows)
  const query = (sortBy, sortOrder = 'ascending', filters = {}) => ({ sortBy, sortOrder, filters })
  const ids = value => value.map(row => row.id)
  const filter = (name, condition) => queryRows(rows, query(null, null, { [name]: condition }), fields)

  // Numeric values are compared numerically, equal values retain input order, and null stays last in either direction.
  assert.deepEqual(['amount', 'name'].map(field => ids(queryRows(rows, query(field), fields))), [[3, 2, 5, 1, 4], [1, 2, 5, 3, 4]])
  assert.deepEqual(['amount', 'time'].map(field => ids(queryRows(rows, query(field, 'descending'), fields))), [[1, 2, 5, 3, 4], [2, 1, 3, 5, 4]])
  // Date parsing treats backend naive timestamps as UTC, and a date-only max includes the final millisecond of the day.
  assert.deepEqual([{ type: 'date', min: '2026-10-07', max: '2026-10-07' }, { type: 'date', value: '2026-10-07' }].map(condition => ids(filter('time', condition))), [[1, 3], [1, 3]])
  // Zero/false/null are valid filter choices; enum arrays match any selected value inside row arrays.
  assert.deepEqual([
    ['amount', { type: 'number', value: 0 }], ['enabled', { type: 'enum', value: false }],
    ['tags', { type: 'enum', value: ['b', 'c'] }], ['enabled', { type: 'enum', value: [null] }],
  ].map(([field, condition]) => ids(filter(field, condition))), [[3], [1, 3], [1, 2, 3], [4]])
  // Nested text is searchable, unknown stale fields do not hide rows, and paging happens after complete-data filtering/sorting.
  assert.deepEqual([
    ids(filter('name', { type: 'text', value: 'GAMMA' })),
    ids(queryRows(rows, query('amount', 'ascending', { amount: { type: 'number', min: 2 }, removed: { type: 'text', value: 'stale' } }), fields, { page: 2, pageSize: 2 })),
    JSON.stringify(rows),
  ], [[3], [1], snapshot])
  // Query normalization rejects corrupt shapes, removes blank controls, keeps exact zero, and maps backend sort aliases.
  assert.deepEqual(normalizeQuery({ sortBy: 'amount', sortOrder: 'desc', filters: { amount: { type: 'number', value: 0, min: 1 }, blank: { type: 'text', value: ' ' }, invalid: { type: 'number', min: 'bad' } } }), { sortBy: 'amount', sortOrder: 'descending', filters: { amount: { type: 'number', value: 0 } } })
  assert.deepEqual(normalizeQuery({ filters: { time: { type: 'date', value: '2026-02-30' }, amount: { type: 'number', value: ' ' } } }).filters, {})
  const attrs = { 'column-key': 'amount', 'filter-type': 'number', 'default-hidden': '', 'table-tools-disabled': false, 'table-fields': [{ prop: 'amount', type: 'number' }], label: 'Amount', prop: 'amount' }
  assert.deepEqual([
    normalizeColumnProps(attrs), normalizeColumnProps({ ...attrs, filterType: 'enum' }).filterType, stripColumnMetadata(attrs),
  ], [{ columnKey: 'amount', filterType: 'number', defaultHidden: true, tableToolsDisabled: false, tableFields: attrs['table-fields'], label: 'Amount', prop: 'amount' }, 'enum', { 'column-key': 'amount', label: 'Amount', prop: 'amount' }])
  // Storage is isolated by user/table, normalized on both reads and writes, and resilient to corrupted or denied storage.
  const values = new Map()
  const storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  saveQuery('assets', 'alice', query('amount'), storage)
  assert.deepEqual([
    readQuery('assets', 'alice', storage).sortBy, readQuery('assets', 'bob', storage).sortBy,
    queryStorageKey('a:b', 'c') === queryStorageKey('b', 'c:a'), queryStorageKey('assets', 'alice') === layoutStorageKey('assets', 'alice'),
  ], ['amount', null, false, false])
  saveLayout('assets', 'alice', { order: ['amount', 'amount', null], hidden: ['name'], widths: { amount: 100.6, name: -1, invalid: 'bad' } }, storage)
  assert.deepEqual(readLayout('assets', 'alice', storage), { order: ['amount'], hidden: ['name'], widths: { amount: 101 } })
  values.set(queryStorageKey('assets', 'alice'), '{broken')
  assert.deepEqual(readQuery('assets', 'alice', storage), { sortBy: null, sortOrder: null, filters: {} })
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, get: () => { throw new Error('denied getter') } })
  assert.doesNotThrow(() => {
    saveQuery('assets', 'alice', query('amount'), { setItem: () => { throw new Error('denied') } })
    readQuery('assets', 'alice')
  })
  delete globalThis.sessionStorage
  console.log('Table state: typed stable sorting, nulls, date boundaries, array/object filters, full-data paging, metadata and isolated storage passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
