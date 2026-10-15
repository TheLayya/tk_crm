// Run against Vite: node frontend/tests/card-key-batches.cjs. All API traffic is mocked.
const assert = require('node:assert/strict')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')
const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'

async function fixture(browser, manager = true, viewport = { width: 1366, height: 900 }) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' })
  await context.addInitScript(manager => {
    localStorage.setItem('token', 'isolated-card-key-batches')
    localStorage.setItem('user', JSON.stringify({ username: 'batch.member' }))
    localStorage.setItem('permissions', JSON.stringify(manager ? ['card_key:view', 'card_key:manage'] : ['card_key:view']))
    window.__copies = []
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => window.__copies.push(text) } })
  }, manager)
  const state = { batches: [
    { id: 0, project_id: 1, name: '历史未分批', status: 'active', remark: '', created_by: '', total: 1 },
    { id: 10, project_id: 1, batch_no: 'B-10', name: '供应商 A', status: 'active', remark: 'A 批次使用要求', created_by: 'admin' },
    { id: 11, project_id: 1, batch_no: 'B-11', name: '异常批次', status: 'paused', remark: '等上游处理', pause_reason: '部分兑换异常', created_by: 'admin' },
    { id: 20, project_id: 2, batch_no: 'B-20', name: '项目二批次', status: 'active', remark: '仅项目二', created_by: 'admin' },
  ], keys: [
    { id: 1, project_id: 1, batch_id: 0, content: 'legacy-key', status: 'available' },
    { id: 2, project_id: 1, batch_id: 10, content: 'a-key', status: 'available' },
    { id: 3, project_id: 1, batch_id: 11, content: 'paused-key', status: 'available' },
    { id: 4, project_id: 2, batch_id: 20, content: 'project-two-key', status: 'available' },
  ].map(key => ({ ...key, history: [] })), requests: [], errors: [], unexpected: [], conflict: false, deferKeys: false, held: [], imports: [] }
  const summary = batch => {
    const keys = state.keys.filter(key => key.project_id === batch.project_id && key.batch_id === batch.id)
    return { ...batch, total: keys.length, available: keys.filter(key => key.status === 'available').length, claimed: keys.filter(key => key.status === 'claimed').length, consumed: keys.filter(key => key.status === 'consumed').length, invalid: keys.filter(key => key.status === 'invalid').length }
  }
  const serialize = key => {
    const batch = state.batches.find(batch => batch.project_id === key.project_id && batch.id === key.batch_id)
    return { ...key, batch_name: batch?.name, batch_status: batch?.status, batch_remark: batch?.remark, batch_pause_reason: batch?.pause_reason }
  }
  const projects = () => [1, 2].map(id => ({ id, name: id === 1 ? '批次测试项目' : '项目二', is_active: true, members: ['__all__'], member_stats: [], can_claim: true, available: state.keys.filter(key => key.project_id === id && key.status === 'available' && state.batches.some(batch => batch.project_id === id && batch.id === key.batch_id && batch.status === 'active')).length, claimed: state.keys.filter(key => key.project_id === id && key.status === 'claimed').length, consumed: state.keys.filter(key => key.project_id === id && key.status === 'consumed').length }))
  await context.route('**/api/**', async route => {
    const request = route.request(), parsed = new URL(request.url()), endpoint = parsed.pathname, method = request.method()
    if (!endpoint.startsWith('/api/')) return route.continue()
    state.requests.push({ endpoint, method, query: Object.fromEntries(parsed.searchParams), body: request.postData() ? request.postDataJSON() : null })
    const respond = json => route.fulfill({ json })
    const match = endpoint.match(/^\/api\/card-keys\/(\d+)\/(batches|keys|import|claim)(?:\/(\d+))?(?:\/(consume|release|invalid))?$/)
    if (endpoint === '/api/card-keys' && method === 'GET') return respond(projects())
    if (match) {
      const [, projectRaw, kind, idRaw, action] = match, projectId = Number(projectRaw), id = Number(idRaw)
      if (kind === 'batches' && method === 'GET') return respond(state.batches.filter(batch => batch.project_id === projectId && (parsed.searchParams.get('include_archived') === 'true' || batch.status !== 'archived')).map(summary))
      if (kind === 'batches' && method === 'PUT') {
        const batch = state.batches.find(batch => batch.project_id === projectId && batch.id === id)
        Object.assign(batch, request.postDataJSON())
        return respond(summary(batch))
      }
      if (kind === 'batches' && method === 'DELETE') {
        if (state.conflict) return route.fulfill({ status: 409, json: { detail: '批次正在流转，请刷新后重试' } })
        const batch = state.batches.find(batch => batch.project_id === projectId && batch.id === id)
        const keys = state.keys.filter(key => key.project_id === projectId && key.batch_id === id)
        if (keys.some(key => key.history.length)) { batch.status = 'archived'; return respond({ deleted: false, archived: true }) }
        state.keys = state.keys.filter(key => key.project_id !== projectId || key.batch_id !== id)
        state.batches = state.batches.filter(item => item !== batch)
        return respond({ deleted: true, deleted_keys: keys.length })
      }
      if (kind === 'keys' && method === 'GET') {
        let keys = state.keys.filter(key => key.project_id === projectId)
        if (!manager) keys = keys.filter(key => key.claimed_by === 'batch.member')
        if (parsed.searchParams.has('batch_id')) keys = keys.filter(key => key.batch_id === Number(parsed.searchParams.get('batch_id')))
        if (parsed.searchParams.get('mine') === 'true') keys = keys.filter(key => key.claimed_by === 'batch.member')
        if (parsed.searchParams.get('status')) keys = keys.filter(key => key.status === parsed.searchParams.get('status'))
        const data = { items: keys.map(serialize), total: keys.length }
        if (state.deferKeys && projectId === 1) return new Promise(resolve => state.held.push(async () => { await respond(data); resolve() }))
        return respond(data)
      }
      if (kind === 'import' && method === 'POST') {
        const body = request.postDataJSON(); state.imports.push({ projectId, body })
        const batch = { id: 12, project_id: projectId, name: body.batch_name || '自动生成批次', remark: body.remark, status: 'active', batch_no: 'B-12', created_by: 'batch.member' }
        state.batches.push(batch)
        state.keys.push({ id: 5, project_id: projectId, batch_id: 12, content: body.content, status: 'available', history: [] })
        return respond({ added: 1, duplicates: 0, batch: summary(batch) })
      }
      if (kind === 'claim' && method === 'POST') {
        const batchId = parsed.searchParams.has('batch_id') ? Number(parsed.searchParams.get('batch_id')) : undefined
        const key = state.keys.find(key => key.project_id === projectId && key.status === 'available' && (batchId === undefined || key.batch_id === batchId) && state.batches.some(batch => batch.project_id === projectId && batch.id === key.batch_id && batch.status === 'active'))
        assert(key, 'Claim must target an available active batch')
        Object.assign(key, { status: 'claimed', claimed_by: 'batch.member', claimed_at: '2026-10-15T02:00:00Z' }); key.history.push({ action: 'claim', username: 'batch.member' })
        return respond(serialize(key))
      }
      if (kind === 'keys' && method === 'POST' && action) {
        const key = state.keys.find(key => key.project_id === projectId && key.id === id)
        key.status = { consume: 'consumed', release: 'available', invalid: 'invalid' }[action]
        key.history.push({ action, username: 'batch.member' })
        return respond(serialize(key))
      }
    }
    if (/^\/api\/card-keys\/\d+\/work-report$/.test(endpoint) && method === 'GET') return respond({ members: [], items: [] })
    const responses = { '/api/card-keys/platforms': [], '/api/card-keys/members': [], '/api/settings/public': { site_name: '卡密批次验收' }, '/api/updates/check': { current_version: '1.1.21', has_update: false }, '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] }, '/api/work-items/summary': {} }
    if (method === 'GET' && Object.hasOwn(responses, endpoint)) return respond(responses[endpoint])
    state.unexpected.push(`${method} ${endpoint}`)
    return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API' } })
  })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', error => state.errors.push(error.message))
  await page.goto(url + '/card-keys')
  try { await page.locator('[data-table-id="card-key-records"]').waitFor(); await page.waitForFunction(() => !document.querySelector('.batch-bar .el-loading-mask')) }
  catch (error) { console.error({ requests: state.requests, unexpected: state.unexpected, errors: state.errors, body: await page.locator('body').innerText() }); throw error }
  const choose = async (name, option) => { await page.locator('.el-select').filter({ has: page.getByRole('combobox', { name, exact: true }) }).locator('.el-select__wrapper').click(); await page.getByRole('option', { name: option, exact: true }).click() }
  const manage = async () => { await page.getByRole('button', { name: '批次管理', exact: true }).click(); const dialog = page.getByRole('dialog', { name: '批次管理 · 批次测试项目', exact: true }); await dialog.waitFor(); return dialog }
  const row = (dialog, name) => dialog.locator('.el-table__body-wrapper tr.el-table__row').filter({ has: page.getByText(name, { exact: true }) })
  const verify = () => { assert.deepEqual(state.errors, [], 'Runtime errors'); assert.deepEqual(state.unexpected, [], 'Unexpected API calls') }
  return { context, page, state, choose, manage, row, verify }
}

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  try {
    const f = await fixture(browser)
    try {
      const { page, state } = f
      await page.getByRole('button', { name: '批量导入', exact: true }).click()
      const importing = page.getByRole('dialog', { name: '批量导入卡密', exact: true })
      await importing.getByPlaceholder('例如 10月15日 · 供应商 A；留空自动生成').fill('10月15日新采购')
      await importing.getByPlaceholder('供应商、采购日期、有效期、使用要求或售后联系方式').fill('供应商 B；有效期 30 天')
      await importing.getByPlaceholder('每行粘贴一份卡密或链接').fill('imported-key')
      await importing.getByRole('button', { name: '导入并建立批次', exact: true }).click()
      await importing.waitFor({ state: 'hidden' })
      await page.locator('.batch-note').getByText('批次备注：供应商 B；有效期 30 天', { exact: true }).waitFor()
      assert.deepEqual(state.imports, [{ projectId: 1, body: { content: 'imported-key', batch_name: '10月15日新采购', remark: '供应商 B；有效期 30 天' } }])
      await page.getByRole('button', { name: '领取所选批次', exact: true }).click()
      await page.locator('.pending-key code').getByText('imported-key', { exact: true }).waitFor()
      assert.equal(state.requests.filter(request => request.endpoint.endsWith('/claim')).at(-1).query.batch_id, '12')
      let manager = await f.manage()
      await f.row(manager, '10月15日新采购').getByRole('button', { name: '暂停', exact: true }).click()
      let prompt = page.getByRole('dialog', { name: '暂停批次', exact: true })
      await prompt.getByRole('textbox').fill('上游正在排查')
      await prompt.getByRole('button', { name: '暂停领取', exact: true }).click()
      await f.row(manager, '10月15日新采购').getByText('已暂停', { exact: true }).waitFor()
      await manager.getByRole('button', { name: '关闭', exact: true }).click()
      await page.locator('.pending-batch-warning').getByText(/上游正在排查/).waitFor()
      assert(await page.getByRole('button', { name: '领取所选批次', exact: true }).isDisabled())
      await f.choose('领取批次', '供应商 A · 可领 1')
      await page.locator('.batch-note').getByText('批次备注：A 批次使用要求', { exact: true }).waitFor()
      await page.locator('.pending-key code').getByText('imported-key', { exact: true }).waitFor()
      assert(await page.getByRole('button', { name: '领取所选批次', exact: true }).isDisabled(), 'Pending key survives a different batch filter')
      await page.locator('.pending-key').getByRole('button', { name: '复制', exact: true }).click()
      assert.equal(await page.evaluate(() => window.__copies.at(-1)), 'imported-key')
      await page.locator('.pending-key').getByRole('button', { name: '确认已消耗', exact: true }).click()
      prompt = page.getByRole('dialog', { name: '确认消耗', exact: true })
      await prompt.getByRole('button', { name: '确定', exact: true }).click()
      await page.locator('.pending-key').waitFor({ state: 'hidden' })
      assert.equal(state.keys.find(key => key.id === 5).status, 'consumed', 'Paused batch keeps pending transitions')

      manager = await f.manage()
      await f.row(manager, '异常批次').getByRole('button', { name: '恢复', exact: true }).click()
      await page.getByRole('dialog', { name: '恢复批次', exact: true }).getByRole('button', { name: '恢复领取', exact: true }).click()
      await f.row(manager, '异常批次').getByText('正常', { exact: true }).waitFor()
      assert.equal(state.batches.find(batch => batch.id === 11).pause_reason, '')
      await f.row(manager, '供应商 A').getByRole('button', { name: '编辑', exact: true }).click()
      const editing = page.getByRole('dialog', { name: '编辑批次', exact: true })
      await editing.locator('.el-form-item').filter({ hasText: '批次备注' }).getByRole('textbox').fill('备注已修订')
      await editing.getByRole('button', { name: '保存', exact: true }).click()
      await editing.waitFor({ state: 'hidden' })
      await f.row(manager, '供应商 A').getByText('备注已修订', { exact: true }).waitFor()
      state.conflict = true
      await f.row(manager, '供应商 A').getByRole('button', { name: '删除', exact: true }).click()
      prompt = page.getByRole('dialog', { name: '删除批次', exact: true })
      assert((await prompt.innerText()).includes('保留全部卡密和历史'))
      await prompt.getByRole('button', { name: '确认删除 / 归档', exact: true }).click()
      await manager.locator('.batch-error').getByText('批次正在流转，请刷新后重试', { exact: true }).waitFor()
      assert(await f.row(manager, '供应商 A').isVisible(), 'A conflict retains the batch and dialog')
      state.conflict = false
      await f.row(manager, '供应商 A').getByRole('button', { name: '删除', exact: true }).click()
      await page.getByRole('dialog', { name: '删除批次', exact: true }).getByRole('button', { name: '确认删除 / 归档', exact: true }).click()
      await f.row(manager, '供应商 A').waitFor({ state: 'hidden' })
      assert(!state.keys.some(key => key.id === 2), 'Unused batch removes its inventory')
      await f.row(manager, '10月15日新采购').getByRole('button', { name: '删除', exact: true }).click()
      await page.getByRole('dialog', { name: '删除批次', exact: true }).getByRole('button', { name: '确认删除 / 归档', exact: true }).click()
      await f.row(manager, '10月15日新采购').waitFor({ state: 'hidden' })
      assert.equal(state.keys.find(key => key.id === 5).status, 'consumed', 'Archive preserves history')
      await manager.getByText('显示归档批次', { exact: true }).click()
      const archived = f.row(manager, '10月15日新采购')
      await archived.getByText('已归档', { exact: true }).waitFor()
      assert.equal(await archived.getByRole('button', { name: '恢复', exact: true }).count(), 0)
      await archived.getByRole('button', { name: '查看', exact: true }).click()
      await page.locator('[data-table-id="card-key-records"] code').getByText('imported-key', { exact: true }).waitFor()
      assert(await page.getByRole('button', { name: '领取所选批次', exact: true }).isDisabled())
      await f.choose('领取批次', '历史未分批 · 可领 1')
      await page.locator('[data-table-id="card-key-records"] code').getByText('legacy-key', { exact: true }).waitFor()
      assert.equal(state.requests.filter(request => request.endpoint.endsWith('/keys') && request.query.batch_id).at(-1).query.batch_id, '0')

      manager = await f.manage()
      await f.row(manager, '异常批次').getByRole('button', { name: '暂停', exact: true }).click()
      prompt = page.getByRole('dialog', { name: '暂停批次', exact: true })
      await prompt.getByRole('textbox').fill('部分兑换异常')
      await prompt.getByRole('button', { name: '暂停领取', exact: true }).click()
      await f.row(manager, '异常批次').getByText('已暂停', { exact: true }).waitFor()
      await manager.getByRole('button', { name: '关闭', exact: true }).click()

      state.deferKeys = true
      await f.choose('领取批次', '异常批次 · 已暂停')
      await page.waitForFunction(() => document.querySelector('.batch-bar .el-select__placeholder')?.textContent.includes('异常批次'))
      await f.choose('选择项目', '项目二')
      await page.locator('[data-table-id="card-key-records"] code').getByText('project-two-key', { exact: true }).waitFor()
      state.deferKeys = false
      await Promise.all(state.held.splice(0).map(release => release()))
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      assert.equal(await page.locator('[data-table-id="card-key-records"] code').innerText(), 'project-two-key', 'Late project one requests do not replace project two')
      assert.equal(await page.locator('.batch-select .el-select__placeholder').innerText(), '自动选择正常批次', 'Project switching resets the previous batch')
      const projectTwoQueries = state.requests.filter(request => request.endpoint === '/api/card-keys/2/keys')
      assert(projectTwoQueries.every(request => !Object.hasOwn(request.query, 'batch_id')), 'A batch ID must never leak between projects')
      await f.choose('选择项目', '批次测试项目')
      await page.locator('[data-table-id="card-key-records"] code').first().waitFor()
      await page.locator('.main-content').evaluate(element => { element.scrollTop = 0 })
      await page.screenshot({ path: '.orchestration/card-key-batches-1366.png', fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
      f.verify()
    } finally { await f.context.close() }

    const viewer = await fixture(browser, false, { width: 390, height: 844 })
    try {
      const { page } = viewer
      assert.equal(await page.getByRole('button', { name: '批次管理', exact: true }).count(), 0)
      assert.equal(await page.getByRole('button', { name: '批量导入', exact: true }).count(), 0)
      await viewer.choose('领取批次', '异常批次 · 已暂停')
      await page.locator('.batch-bar .el-alert').getByText(/部分兑换异常/).waitFor()
      assert(await page.getByRole('button', { name: '领取所选批次', exact: true }).isDisabled())
      const box = await page.locator('.batch-bar').boundingBox()
      assert(box.x >= 0 && box.x + box.width <= 391, 'Batch controls fit a phone viewport')
      assert.equal(await page.locator('[data-table-id="card-key-records"] code').count(), 0, 'Members never receive unclaimed key contents')
      await page.locator('.main-content').evaluate(element => { element.scrollTop = 0 })
      await page.screenshot({ path: '.orchestration/card-key-batches-390.png', fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
      viewer.verify()
    } finally { await viewer.context.close() }
  } finally { await close() }
  console.log('Card key batches: import metadata, selected-batch claim, pause and pending transitions, remarks, delete conflict, physical delete, archive/history, legacy filter, project race isolation, permissions and mobile layout passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
