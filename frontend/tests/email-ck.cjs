// Run against an isolated Vite server. All API data and clipboard contents are synthetic.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')

const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
const artifactDir = process.env.TKCRM_EMAIL_CK_ARTIFACT_DIR || path.resolve(__dirname, '../../outputs/email-ck-qa')
const ck = JSON.stringify([
  { domain: '.google.com', path: '/', name: 'OSID', value: 'fixture-osid==' },
  { domain: '.google.com', path: '/', name: 'SID', value: 'fixture-sid%2F' },
  { domain: '.google.com', path: '/', secure: true, name: '__Secure-1PSIDTS', value: 'fixture-timestamp' },
  { domain: '.google.com', path: '/', secure: true, name: '__Secure-1PSID', value: 'fixture-primary' },
  { domain: '.google.com', path: '/', name: 'SAPISID', value: 'fixture-unrelated' },
])
const combo = 'fixture-primary::fixture-sid%2F::fixture-osid==::fixture-timestamp'
const missing = '__Secure-1PSID=fixture-incomplete; SID=fixture-sid'
const draft = 'Cookie: OSID=draft-osid==; __Secure-1PSID=draft-primary; SID=draft-sid%2F'
const draftCombo = 'draft-primary::draft-sid%2F::draft-osid=='
const initialEmails = [
  { id: 1, email: 'ck-one@example.invalid', ck, remark: 'Existing note must remain separate', password: 'fixture-password' },
  { id: 2, email: 'ck-empty@example.invalid', ck: null, remark: '' },
  { id: 3, email: 'ck-incomplete@example.invalid', ck: missing, remark: '' },
].map(row => ({ ...row, management_status: '闲置', current_relation_count: 0, platform_tags: [], sellers: [], purchase_channel: 'fixture-source', purchase_price: 0 }))

async function fixture(browser, permissions, viewport = { width: 1366, height: 900 }) {
  const context = await browser.newContext({ viewport, timezoneId: 'Asia/Shanghai' })
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  await page.addInitScript(permissions => {
    localStorage.setItem('token', 'isolated-email-ck-fixture')
    localStorage.setItem('user', JSON.stringify({ username: 'ck-test' }))
    localStorage.setItem('permissions', JSON.stringify(permissions))
    window.__copies = []
    window.__clipboardMode = 'available'
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => {
      if (window.__clipboardMode !== 'available') throw new Error('fixture clipboard unavailable')
      window.__copies.push(text)
    } } })
    document.execCommand = action => {
      if (action !== 'copy' || window.__clipboardMode === 'failure') return false
      const active = document.activeElement
      assertSyntheticTextarea(active)
      window.__copies.push(active.value)
      return true
    }
    function assertSyntheticTextarea(element) {
      if (!element || element.tagName !== 'TEXTAREA' || !element.hasAttribute('readonly')) throw new Error('Clipboard fallback must select a temporary readonly textarea')
    }
  }, permissions)
  const state = { emails: structuredClone(initialEmails), mutations: [], unexpected: [], errors: [], saveMode: 'success', lists: 0 }
  page.on('pageerror', error => state.errors.push(error.message))
  await page.route('**/api/**', async route => {
    const request = route.request(), endpoint = new URL(request.url()).pathname, method = request.method()
    if (!endpoint.startsWith('/api/')) return route.continue()
    if (endpoint === '/api/emails' && method === 'GET') {
      state.lists += 1
      return route.fulfill({ json: { total: state.emails.length, items: state.emails } })
    }
    if ((endpoint === '/api/emails' && method === 'POST') || (/^\/api\/emails\/\d+$/.test(endpoint) && method === 'PUT')) {
      const body = request.postDataJSON()
      state.mutations.push({ endpoint, method, body })
      if (state.saveMode === 'failure') return route.fulfill({ status: 422, json: { detail: '合成保存失败，请重试' } })
      let row
      if (method === 'POST') {
        row = { ...body, id: 4, current_relation_count: 0 }
        state.emails.push(row)
      } else {
        row = state.emails.find(row => row.id === Number(endpoint.split('/').at(-1)))
        Object.assign(row, body)
      }
      return route.fulfill({ json: row })
    }
    if (/^\/api\/emails\/\d+\/(relations|asset-history)$/.test(endpoint)) return route.fulfill({ json: [] })
    const responses = {
      '/api/settings/public': { site_name: 'CK 验收' },
      '/api/updates/check': { current_version: '1.1.23', has_update: false },
      '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] },
      '/api/work-items/summary': {}, '/api/emails/platforms': [],
      '/api/team/member': { items: [{ id: 1, username: 'ck-test', real_name: 'CK 测试', is_active: true }], total: 1 },
    }
    if (!(endpoint in responses)) {
      state.unexpected.push(endpoint)
      return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API ' + endpoint } })
    }
    return route.fulfill({ json: responses[endpoint] })
  })
  await page.goto(url + '/emails')
  const table = page.locator('.crm-table-wrapper[data-table-id="emails"]')
  await table.locator('.email-ck-cell').first().waitFor()
  const flow = page.getByRole('dialog', { name: '提取 Flow 加号', exact: true })
  const editor = page.getByRole('dialog', { name: '编辑邮箱', exact: true })
  const creator = page.getByRole('dialog', { name: '新增邮箱', exact: true })
  const result = flow.getByRole('textbox', { name: 'Flow 加号', exact: true })
  const field = (dialog, label) => dialog.locator('.el-form-item').filter({ has: page.getByText(label, { exact: true }) }).locator('input, textarea').first()
  const openEdit = async (index = 0) => {
    await table.locator('.el-table__body-wrapper tbody tr').nth(index).getByRole('button', { name: '编辑', exact: true }).click()
    await editor.waitFor()
  }
  const closeFlow = async () => { await page.keyboard.press('Escape'); await flow.waitFor({ state: 'hidden' }) }
  const copy = async (container, label, expected) => {
    const before = await page.evaluate(() => window.__copies.length)
    await container.getByRole('button', { name: label, exact: true }).click()
    await page.waitForFunction(count => window.__copies.length === count + 1, before)
    assert.equal(await page.evaluate(() => window.__copies.at(-1)), expected)
  }
  const check = () => {
    assert.deepEqual(state.errors, [], 'CK runtime errors')
    assert.deepEqual(state.unexpected, [], 'Unexpected API requests')
  }
  return { context, page, state, table, flow, result, editor, creator, field, openEdit, closeFlow, copy, check }
}

async function screenshot(page, name) {
  fs.mkdirSync(artifactDir, { recursive: true })
  await page.screenshot({ path: path.join(artifactDir, name + '.png'), fullPage: true, style: '.el-message { visibility: hidden !important }' })
}

async function assertWithinViewport(locator, width, label) {
  const bounds = await locator.boundingBox()
  assert(bounds && bounds.x >= -1 && bounds.x + bounds.width <= width + 1, label + ' must fit the viewport')
}

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  let primaryError
  try {
    const viewer = await fixture(browser, ['email:view'])
    try {
      const { page, state, table, flow, result } = viewer
      assert.equal(await page.getByRole('button', { name: '新增邮箱', exact: true }).count(), 0)
      assert.equal(await page.getByRole('button', { name: '编辑', exact: true }).count(), 0)
      const cells = table.locator('.email-ck-cell')
      assert.equal(await cells.count(), 3)
      assert((await cells.nth(0).innerText()).includes('已保存'))
      assert((await cells.nth(1).innerText()).includes('未填写'))
      assert(!(await table.innerText()).includes('fixture-primary'), 'Stored CK must be masked in the table')
      assert.equal(await cells.nth(1).getByRole('button', { name: '取加号', exact: true }).count(), 0, 'Empty CK has no extraction action')
      await viewer.copy(cells.first(), '复制 CK', ck)
      await cells.first().getByRole('button', { name: '取加号', exact: true }).click()
      await flow.waitFor()
      assert.equal(await result.inputValue(), combo, 'Cookie order and exact values must be retained')
      assert.notEqual(await result.getAttribute('readonly'), null)
      assert((await flow.innerText()).includes('__Secure-1PSIDTS'), 'Optional timestamp must have an explanatory message')
      const before = await page.evaluate(() => window.__copies.length)
      await page.evaluate(() => { window.__clipboardMode = 'failure' })
      await flow.getByRole('button', { name: '复制加号', exact: true }).click()
      await page.getByText(/复制失败/).last().waitFor()
      assert.equal(await page.evaluate(() => window.__copies.length), before)
      assert.equal(await result.inputValue(), combo, 'Clipboard failure must retain the manual-copy result')
      assert.equal(await page.locator('textarea[readonly]').count(), 1, 'Clipboard fallback must remove its temporary secret textarea')
      await page.evaluate(() => { window.__clipboardMode = 'available' })
      await viewer.copy(flow, '复制加号', combo)
      await screenshot(page, 'desktop')
      await viewer.closeFlow()

      await cells.nth(2).getByRole('button', { name: '取加号', exact: true }).click()
      await flow.waitFor()
      assert.equal(await result.count(), 0, 'Invalid extraction must not show a stale successful result')
      assert((await flow.locator('.el-alert--error').innerText()).includes('OSID'))
      assert(!(await flow.innerText()).includes('fixture-incomplete'), 'Extraction errors must not echo sensitive values')
      assert(!(await flow.innerText()).includes(combo))
      const invalidCopy = flow.getByRole('button', { name: '复制加号', exact: true })
      assert(await invalidCopy.count() === 0 || await invalidCopy.isDisabled(), 'Invalid extraction cannot be copied')
      await viewer.closeFlow()
      await cells.first().getByRole('button', { name: '取加号', exact: true }).click()
      await flow.waitFor()
      assert.equal(await result.inputValue(), combo)
      assert.equal(await flow.locator('.el-alert--error').count(), 0, 'A new successful extraction clears the previous error')
      await viewer.closeFlow()

      await page.locator('.email-name').first().click()
      const details = page.locator('.email-ck-detail')
      await details.waitFor()
      assert(!(await details.innerText()).includes('fixture-primary'), 'Expanded CK starts masked')
      await details.getByRole('button', { name: /^显示(?: CK)?$/ }).click()
      assert((await details.innerText()).includes(ck), 'Show CK reveals the original stored text')
      await details.getByRole('button', { name: /^隐藏(?: CK)?$/ }).click()
      assert(!(await details.innerText()).includes('fixture-primary'))
      await viewer.copy(details, '复制 CK', ck)
      assert.deepEqual(state.mutations, [], 'Read-only extraction must never mutate the mailbox')
      viewer.check()
    } finally { await viewer.context.close() }

    const manager = await fixture(browser, ['email:view', 'email:manage'])
    try {
      const { page, state, table, flow, result, editor, creator, field } = manager
      await manager.openEdit()
      const input = editor.getByRole('textbox', { name: 'CK (Cookie)', exact: true })
      assert.equal(await input.inputValue(), ck, 'Editing must prefill the original CK')
      assert.equal(await field(editor, '备注').inputValue(), initialEmails[0].remark)
      await input.fill(draft)
      await editor.getByRole('button', { name: '取加号', exact: true }).click()
      await flow.waitFor()
      assert.equal(await result.inputValue(), draftCombo, 'Form extraction must use the current unsaved CK')
      assert.equal(state.mutations.length, 0, 'Form extraction must not save the mailbox')
      await manager.closeFlow()
      assert.equal(await input.inputValue(), draft)
      await input.fill(missing)
      await editor.getByRole('button', { name: '取加号', exact: true }).click()
      await flow.waitFor()
      assert.equal(await result.count(), 0)
      assert((await flow.locator('.el-alert--error').innerText()).includes('OSID'))
      await manager.closeFlow()
      const preserved = '\n  ' + ck + '\n'
      await input.fill(preserved)
      state.saveMode = 'failure'
      await editor.getByRole('button', { name: '保存', exact: true }).click()
      await page.getByText('合成保存失败，请重试', { exact: true }).waitFor()
      assert(await editor.isVisible(), 'A failed save must keep the editor open')
      assert.equal(await input.inputValue(), preserved, 'A failed save must retain CK input')
      state.saveMode = 'success'
      await editor.getByRole('button', { name: '保存', exact: true }).click()
      await editor.waitFor({ state: 'hidden' })
      assert.equal(state.mutations.at(-1).body.ck, preserved, 'CK must be sent without trimming or reformatting')
      assert.equal(state.mutations.at(-1).body.remark, initialEmails[0].remark, 'Saving CK must preserve notes')
      assert(!('password' in state.mutations.at(-1).body), 'CK editing must preserve the existing password')
      await manager.copy(table.locator('.email-ck-cell').first(), '复制 CK', preserved)
      await manager.openEdit()
      assert.equal(await input.inputValue(), preserved)
      await input.fill('')
      await editor.getByRole('button', { name: '保存', exact: true }).click()
      await editor.waitFor({ state: 'hidden' })
      assert.equal(state.mutations.at(-1).body.ck, '', 'An explicit empty CK must be submitted to clear the field')
      await table.locator('.email-ck-cell').first().getByText('未填写', { exact: true }).waitFor()

      await page.getByRole('button', { name: '新增邮箱', exact: true }).click()
      await creator.waitFor()
      assert.equal(await creator.getByRole('textbox', { name: 'CK (Cookie)', exact: true }).inputValue(), '', 'New mailbox must not inherit the last edited CK')
      await field(creator, '邮箱').fill('ck-created@example.invalid')
      await field(creator, '采购渠道').fill('fixture-source')
      await field(creator, '采购成本').fill('0')
      await field(creator, '采购成本').press('Tab')
      await creator.getByRole('button', { name: '保存', exact: true }).click()
      await creator.waitFor({ state: 'hidden' })
      assert.equal(state.mutations.at(-1).method, 'POST')
      assert.equal(state.mutations.at(-1).body.ck, '', 'CK remains optional on create')
      assert.equal(state.mutations.at(-1).body.remark, '')
      manager.check()
    } finally { await manager.context.close() }

    const mobile = await fixture(browser, ['email:view'], { width: 360, height: 800 })
    try {
      const { page, table, flow, result } = mobile
      await page.locator('.email-name').first().click()
      const details = page.locator('.email-ck-detail')
      await details.waitFor()
      await details.getByRole('button', { name: '取加号', exact: true }).click()
      await flow.waitFor()
      assert.equal(await result.inputValue(), combo)
      await assertWithinViewport(flow, 360, 'Mobile extraction dialog')
      await assertWithinViewport(result, 360, 'Mobile extraction result')
      await assertWithinViewport(flow.getByRole('button', { name: '复制加号', exact: true }), 360, 'Mobile copy action')
      assert(await flow.evaluate(node => node.scrollWidth <= node.clientWidth + 1), 'Mobile dialog must not overflow horizontally')
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile page must not overflow horizontally')
      await mobile.copy(flow, '复制加号', combo)
      await screenshot(page, 'mobile')
      await mobile.closeFlow()
      assert.equal(await table.locator('.email-ck-cell').count(), 3)
      mobile.check()
    } finally { await mobile.context.close() }
  } catch (error) { primaryError = error; throw error }
  finally {
    try { await close() }
    catch (error) { if (!primaryError) throw error; console.error('Additional browser cleanup failure:', error.message) }
  }
  console.log('Email CK: masked column/details, exact copy, Flow extraction/reset, optional timestamp, clipboard retry, form drafts, save failure/retry, CK clear/create, view permissions, and 360px layout passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
