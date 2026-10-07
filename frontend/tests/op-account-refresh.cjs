// Run with: node frontend/tests/op-account-refresh.cjs (no extra dependencies).
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, '../src/views/OpAccountList.vue'), 'utf8')
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*? from ['"][^'"]+['"]\r?\n/gm, '')
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const row = (time = null, followers = 100) => ({ id: 101, platform: 'tiktok', account: 'fixture', collect_status: 'success', video_source: 'op', video_collected_at: time, follower_count: followers })
const list = account => ({ items: [account], total: 1 })

function setup(overrides = {}) {
  const state = { rows: [row()], mounted: [], unmounted: [], timers: new Map(), requests: [], messages: [] }
  let timerId = 0
  const sandbox = {
    console,
    ref: value => ({ value }), reactive: value => value,
    computed: getter => ({ get value() { return getter() } }),
    onMounted: callback => state.mounted.push(callback),
    onUnmounted: callback => state.unmounted.push(callback),
    useRouter: () => ({}), useRoute: () => ({ query: {} }),
    useAuthStore: () => ({ hasPermission: () => false }),
    useTableQuery: () => ({ tableQuery: { value: { sortBy: null, sortOrder: null, filters: {} } }, queryParams: { value: {} } }),
    localStorage: { getItem: () => null, setItem: () => {} },
    document: { hidden: false },
    window: { innerWidth: 390, addEventListener: () => {}, removeEventListener: () => {} },
    setInterval: (callback, delay) => { const id = ++timerId; state.timers.set(id, { callback, delay }); return id },
    clearInterval: id => state.timers.delete(id),
    ElMessage: { info: message => state.messages.push(message), success: () => {}, warning: () => {} },
    listOpAccounts: async params => { state.requests.push(params); return { items: state.rows.map(account => ({ ...account })), total: state.rows.length } },
    triggerCollect: async () => ({ task_id: 'fixture-task' }),
    getCollectTask: async () => ({ total: 1, completed: 1, success: 1, failed: 0, status: 'completed' }),
    module: { exports: {} },
    ...overrides,
  }
  vm.runInNewContext(script + '\nmodule.exports = { accounts, loading, detailDialog, filters, collectTask, loadAccounts, watchCollectTask, startCollect, videoComponentKey, isCollecting, collectStatusLabel, collectStatusHint }', sandbox)
  return { state, sandbox, view: sandbox.module.exports, timer: delay => [...state.timers.values()].find(timer => timer.delay === delay)?.callback }
}

async function main() {
  // An already open empty video component must remount after a completed task.
  const fixture = setup()
  const { view, state, sandbox, timer } = fixture
  await state.mounted[0]()
  view.detailDialog.value = { visible: true, row: view.accounts.value[0] }
  const oldKey = view.videoComponentKey(view.detailDialog.value.row)
  await view.startCollect([101])
  assert(view.isCollecting(101))
  assert.equal(view.collectStatusLabel('success', view.isCollecting(101)), '采集中')
  assert.equal(view.collectStatusHint(view.accounts.value[0]), '正在采集账号基础信息和视频')
  state.rows = [row('2026-10-06T04:00:00', 125)]
  await timer(2000)()
  assert(view.collectTask.done)
  assert(!view.isCollecting(101))
  assert.notEqual(view.videoComponentKey(view.detailDialog.value.row), oldKey)
  assert.equal(view.detailDialog.value.row.follower_count, 125)
  assert.strictEqual(view.detailDialog.value.row, view.accounts.value[0])
  assert(source.includes(':key="videoComponentKey(row)"'))
  assert(source.includes(':key="videoComponentKey(detailDialog.row)"'))

  // Scheduler changes refresh silently while the page is visible.
  const refresh = timer(30000)
  sandbox.document.hidden = true
  refresh()
  assert.equal(state.requests.length, 2)
  sandbox.document.hidden = false
  const pending = deferred()
  sandbox.listOpAccounts = async params => { state.requests.push(params); return pending.promise }
  refresh()
  assert.equal(view.loading.value, false, 'Automatic refresh must not show the table spinner')
  refresh()
  assert.equal(state.requests.length, 3, 'An in-flight automatic request must not overlap the next tick')
  pending.resolve(list(row('2026-10-06T05:00:00', 130)))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(view.detailDialog.value.row.follower_count, 130)
  state.unmounted[0]()
  assert.equal(state.timers.size, 0)
  refresh()
  assert.equal(state.requests.length, 3, 'Disposed page must not make new requests')

  // A slow old filter response must not replace the newest rows or dialog.
  const old = deferred(), newer = deferred()
  const racing = setup({ listOpAccounts: params => params.keyword === 'new' ? newer.promise : old.promise })
  const first = racing.view.loadAccounts()
  racing.view.filters.keyword = 'new'
  const second = racing.view.loadAccounts()
  newer.resolve(list(row('2026-10-06T06:00:00', 200)))
  await second
  old.resolve(list(row(null, 1)))
  await first
  assert.equal(racing.view.accounts.value[0].follower_count, 200)

  // Unmount during the first request must not create a late refresh timer.
  const delayed = deferred()
  const unmounting = setup({ listOpAccounts: () => delayed.promise })
  const mounting = unmounting.state.mounted[0]()
  unmounting.state.unmounted[0]()
  delayed.resolve(list(row()))
  await mounting
  assert.equal(unmounting.state.timers.size, 0)
  assert.equal(unmounting.view.accounts.value.length, 0)
  console.log('Operator refresh: completed/import task feedback, video keys, dialog sync, silent scheduler refresh, races and cleanup passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
