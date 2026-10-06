// Run with: node frontend/tests/update-recovery.cjs (no extra dependencies).
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const frontend = path.resolve(__dirname, '..')
const target = '1.1.13'
const jobKey = 'tk-crm:update-job'
const networkError = (status) => status ? { response: { status, data: { detail: 'gateway' } } } : new Error('disconnected')
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

function setup(overrides = {}) {
  const state = { now: 1000000, reloaded: 0, applied: 0, messages: [], timers: new Map(), storage: new Map(), mounted: [], unmounted: [] }
  let timerId = 0
  const api = {
    checkUpdate: async () => ({ current_version: '1.1.12', latest_version: target, has_update: true, configured: true, changes: [] }),
    applyUpdate: async () => { state.applied += 1; return { status: 'running', latest_version: target } },
    getUpdateStatus: async () => ({ status: 'running', latest_version: target }),
    getUpdateVersion: async () => ({ current_version: target }),
    getUpdateHistory: async () => ({ items: [] }),
    getPublicSettings: async () => ({}),
    ...overrides,
  }
  const sandbox = {
    ...api,
    console,
    Date: class extends Date { static now() { return state.now } },
    AbortController,
    ref: value => ({ value }),
    computed: getter => ({ get value() { return getter() } }),
    onMounted: callback => state.mounted.push(callback),
    onUnmounted: callback => state.unmounted.push(callback),
    watch: () => {},
    useRoute: () => ({ path: '/monitor', matched: [] }),
    useRouter: () => ({ push: () => {} }),
    useAuthStore: () => ({ user: {}, hasPermission: () => true }),
    ElMessage: { error: message => state.messages.push(message), success: () => {} },
    ElMessageBox: { confirm: async () => {} },
    localStorage: {
      getItem: key => state.storage.get(key) ?? null,
      setItem: (key, value) => state.storage.set(key, value),
      removeItem: key => state.storage.delete(key),
    },
    fetch: async () => ({ ok: true, headers: { get: () => 'text/html' }, text: async () => '<div id="app"></div>' }),
    document: {},
    window: {
      innerWidth: 1366,
      addEventListener: () => {}, removeEventListener: () => {},
      setTimeout: (callback, delay) => { const id = ++timerId; state.timers.set(id, { callback, delay }); return id },
      clearTimeout: id => state.timers.delete(id),
      setInterval: (callback, delay) => { const id = ++timerId; state.timers.set(id, { callback, delay }); return id },
      clearInterval: id => state.timers.delete(id),
      location: { href: 'http://fixture/monitor', reload: () => { state.reloaded += 1 } },
    },
    module: { exports: {} },
  }
  const source = fs.readFileSync(path.join(frontend, 'src/components/Layout.vue'), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1]
  vm.runInNewContext(source.replace(/^import .*\r?\n/gm, '') + '\nmodule.exports = { updateInfo, updateChecking, handleApplyUpdate, checkUpdateSilently, beginUpdatePolling, pollUpdate, resumeUpdate, stopUpdatePolling }', sandbox)
  const layout = sandbox.module.exports
  layout.updateInfo.value = { current_version: '1.1.12', latest_version: target, has_update: true, configured: true }
  return { layout, state, sandbox }
}

function checkInterceptor() {
  const { state, sandbox } = setup()
  let rejectResponse
  const request = () => Promise.resolve({})
  request.interceptors = { request: { use: () => {} }, response: { use: (_, reject) => { rejectResponse = reject } } }
  sandbox.axios = { create: () => request }
  sandbox.router = { currentRoute: { value: { path: '/monitor' } }, replace: () => assert.fail('restart must not redirect to login') }
  sandbox.testAuth = { refreshAccessToken: async () => { throw networkError(503) }, _clearState: () => assert.fail('restart must not clear auth') }
  let source = fs.readFileSync(path.join(frontend, 'src/api/request.js'), 'utf8').replace(/^import .*\r?\n/gm, '').replace('export default request', '')
  source = source.replaceAll("await import('@/stores/auth')", '({ useAuthStore: () => testAuth })')
  vm.runInNewContext(source, sandbox)
  return { state, sandbox, rejectResponse }
}

async function main() {
  const stale = setup({ getUpdateStatus: async () => ({ status: 'completed', latest_version: '1.1.12' }) })
  stale.layout.beginUpdatePolling({ targetVersion: target, startedAt: stale.state.now })
  await stale.layout.pollUpdate()
  assert.equal(stale.state.reloaded, 0, 'a prior completed version cannot complete this job')
  assert(stale.state.storage.has(jobKey))
  assert.equal(stale.state.timers.size, 1)
  await stale.layout.checkUpdateSilently()
  assert.equal(stale.layout.updateInfo.value.updating, true, 'background checks cannot erase the job')

  let statusCount = 0
  const lost = setup({
    applyUpdate: async () => { lost.state.applied += 1; throw networkError() },
    getUpdateStatus: async () => {
      statusCount += 1
      if (statusCount === 1) throw networkError(503)
      if (statusCount === 2) return { status: 'failed', latest_version: target, message: 'prior failure' }
      if (statusCount === 3) return { status: 'running', latest_version: target }
      return { status: 'failed', latest_version: target, message: 'this failure' }
    },
  })
  await lost.layout.handleApplyUpdate()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(lost.state.applied, 1)
  assert(lost.state.storage.has(jobKey))
  await lost.layout.handleApplyUpdate()
  assert.equal(lost.state.applied, 1, 'an unresolved POST must never be replayed')
  await lost.layout.pollUpdate()
  assert(lost.state.storage.has(jobKey), 'old failed state cannot resolve an unconfirmed POST')
  await lost.layout.pollUpdate()
  await lost.layout.pollUpdate()
  assert(!lost.state.storage.has(jobKey))
  assert(lost.state.messages.includes('更新失败：this failure'))

  for (const status of [409, 500, 501]) {
    const rejected = setup({ applyUpdate: async () => { rejected.state.applied += 1; throw networkError(status) } })
    await rejected.layout.handleApplyUpdate()
    assert(rejected.state.storage.has(jobKey), `HTTP ${status} can leave a server task running`)
    assert.equal(rejected.layout.updateInfo.value.update_waiting, true)
    await rejected.layout.handleApplyUpdate()
    assert.equal(rejected.state.applied, 1, 'ambiguous HTTP apply errors cannot be resubmitted')
  }
  for (const status of [400, 401, 403, 404, 422]) {
    const denied = setup({ applyUpdate: async () => { throw networkError(status) } })
    await denied.layout.handleApplyUpdate()
    assert(!denied.state.storage.has(jobKey), `definitive HTTP ${status} rejection clears the job`)
  }

  const slowStatus = deferred()
  const slow = setup({ getUpdateStatus: () => slowStatus.promise })
  slow.layout.beginUpdatePolling({ targetVersion: target, startedAt: slow.state.now })
  const pending = slow.layout.pollUpdate()
  assert.equal(slow.state.timers.size, 0, 'no interval accumulates while status is in flight')
  slowStatus.resolve({ status: 'running', latest_version: target })
  await pending
  assert.equal(slow.state.timers.size, 1)
  for (const cleanup of slow.state.unmounted) cleanup()
  assert.equal(slow.state.timers.size, 0, 'unmount clears polling timers')

  const completed = setup({ getUpdateStatus: async () => ({ status: 'completed', latest_version: target }) })
  completed.layout.beginUpdatePolling({ targetVersion: target, startedAt: completed.state.now })
  completed.sandbox.getUpdateVersion = async () => ({ current_version: '1.1.12' })
  await completed.layout.pollUpdate()
  assert.equal(completed.state.reloaded, 0, 'the backend must run the target version')
  completed.sandbox.getUpdateVersion = async () => ({ current_version: target })
  completed.sandbox.fetch = async () => ({ ok: false })
  await completed.layout.pollUpdate()
  assert.equal(completed.state.reloaded, 0, 'frontend downtime must not trigger reload')
  completed.sandbox.fetch = async () => ({ ok: true, headers: { get: () => 'text/html' }, text: async () => '<div id="app"></div>' })
  await completed.layout.pollUpdate()
  assert.equal(completed.state.reloaded, 1)
  assert(!completed.state.storage.has(jobKey))

  const timeout = setup()
  timeout.layout.beginUpdatePolling({ targetVersion: target, startedAt: timeout.state.now })
  timeout.state.now += 10 * 60 * 1000
  await timeout.layout.pollUpdate()
  assert.equal(timeout.layout.updateInfo.value.update_waiting, true)
  assert(timeout.state.storage.has(jobKey), 'timeout keeps submission locked until a terminal state')
  assert.equal(timeout.state.timers.size, 0, 'timeout stops automatic polling')
  await timeout.layout.handleApplyUpdate()
  assert.equal(timeout.state.applied, 0)
  const read = deferred()
  let reads = 0
  timeout.sandbox.getUpdateStatus = () => { reads += 1; return read.promise }
  const retry = timeout.layout.resumeUpdate(true)
  await timeout.layout.resumeUpdate(true)
  assert.equal(reads, 1, 'manual double click cannot overlap status requests')
  read.resolve({ status: 'running', latest_version: target })
  await retry
  assert.equal(timeout.state.applied, 0, 'manual retry only queries status')
  assert(timeout.state.storage.has(jobKey))

  const resumed = setup()
  resumed.state.storage.set(jobKey, JSON.stringify({ targetVersion: target, startedAt: resumed.state.now, confirmed: true }))
  await resumed.layout.resumeUpdate()
  assert.equal(resumed.layout.updateInfo.value.updating, true, 'reload resumes the saved job')
  assert.equal(resumed.state.timers.size, 1)
  resumed.sandbox.getUpdateStatus = async () => { throw networkError(500) }
  await resumed.layout.pollUpdate()
  assert(resumed.state.storage.has(jobKey), 'unexpected status errors cannot unlock an in-flight job')
  assert.equal(resumed.layout.updateInfo.value.update_waiting, true)
  const loggedOut = setup({ getUpdateStatus: () => slowStatus.promise })
  for (const cleanup of loggedOut.state.unmounted) cleanup()
  await loggedOut.layout.resumeUpdate()
  assert.equal(loggedOut.state.timers.size, 0, 'disposed layout cannot restart polling')

  const interceptor = checkInterceptor()
  interceptor.state.storage.set(jobKey, JSON.stringify({ targetVersion: target, startedAt: interceptor.state.now }))
  for (const status of [undefined, 502, 503, 504]) {
    await assert.rejects(interceptor.rejectResponse({ ...networkError(status), config: { url: '/work-items/summary' } }))
  }
  assert.equal(interceptor.state.messages.length, 0, 'expected restart errors from all requests stay quiet')
  await assert.rejects(interceptor.rejectResponse({ ...networkError(401), config: { url: '/settings', headers: {} } }))
  assert.equal(interceptor.state.messages.length, 0, 'transient refresh failure during restart preserves login')
  interceptor.state.now += 10 * 60 * 1000
  await assert.rejects(interceptor.rejectResponse({ ...networkError(503), config: { url: '/settings' } }))
  assert.equal(interceptor.state.messages.length, 1, 'outside the expected window a network error is visible')
  console.log('Update recovery: target matching, lost POST, stale failed, no overlapping polls, cleanup, timeout lock, read-only retry, resume, and restart errors passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
