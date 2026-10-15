// Run against Vite: node frontend/tests/email-batch-status.cjs. All API traffic is mocked.
const assert = require('node:assert/strict')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')

const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
const emails = [
  { id: 1, email: 'batch-status-one@gmail.com', management_status: '闲置', gmail_check_status: '正常', gmail_check_raw_status: 'live', gmail_checked_at: '2026-10-15T02:00:00Z' },
  { id: 2, email: 'batch-status-two@example.invalid', management_status: '使用中', gmail_check_status: null },
].map(row => ({ ...row, platform_tags: [], current_relation_count: 0, sellers: [] }))

async function fixture(browser, permissions, viewport = { width: 1366, height: 900 }) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' })
  await context.addInitScript(permissions => {
    localStorage.setItem('token', 'isolated-email-batch-status-fixture')
    localStorage.setItem('user', JSON.stringify({ username: 'batch-status-test' }))
    localStorage.setItem('permissions', JSON.stringify(permissions))
  }, permissions)
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  const state = { rows: structuredClone(emails), attempts: [], checks: [], lists: 0, errors: [], unexpected: [], mode: 'success', defer: false, release: null }
  page.on('pageerror', error => state.errors.push(error.message))
  await context.route('**/api/**', async route => {
    const request = route.request(), endpoint = new URL(request.url()).pathname
    if (!endpoint.startsWith('/api/')) return route.continue()
    if (endpoint === '/api/emails/batch-status') {
      assert.equal(request.method(), 'POST')
      const body = request.postDataJSON()
      state.attempts.push(body)
      const respond = async () => {
        if (state.mode === 'conflict') return route.fulfill({ status: 409, json: { detail: '所选邮箱的状态已变化，请刷新后重新选择' } })
        assert.equal(Object.keys(body).length, 2, 'A batch updates exactly one status field')
        for (const row of state.rows) if (body.email_ids.includes(row.id)) {
          if (Object.hasOwn(body, 'management_status')) row.management_status = body.management_status
          else Object.assign(row, { gmail_check_status: body.gmail_check_status, gmail_check_raw_status: body.gmail_check_status ? '手动标记' : null, gmail_checked_at: null })
        }
        return route.fulfill({ json: { updated: body.email_ids.length, email_ids: body.email_ids } })
      }
      if (state.defer) return new Promise(resolve => { state.release = async () => { await respond(); resolve() } })
      return respond()
    }
    if (endpoint === '/api/emails/check') {
      assert.equal(request.method(), 'POST')
      state.checks.push(request.postDataJSON())
      return route.fulfill({ json: { checked: request.postDataJSON().account_ids.length } })
    }
    if (endpoint === '/api/emails') {
      assert.equal(request.method(), 'GET')
      state.lists += 1
      return route.fulfill({ json: { items: state.rows, total: state.rows.length } })
    }
    const responses = {
      '/api/settings/public': { site_name: '邮箱批量状态验收' }, '/api/updates/check': { current_version: '1.1.21', has_update: false },
      '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] }, '/api/work-items/summary': {}, '/api/emails/platforms': [],
      '/api/emails/1/relations': [], '/api/emails/1/asset-history': [],
    }
    if (request.method() !== 'GET' || !(endpoint in responses)) {
      state.unexpected.push(`${request.method()} ${endpoint}`)
      return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API ' + endpoint } })
    }
    return route.fulfill({ json: responses[endpoint] })
  })
  await page.goto(url + '/emails')
  const table = page.locator('.crm-table-wrapper[data-table-id="emails"]')
  await table.locator('.el-table__body-wrapper .email-name').first().waitFor()
  const selectAll = () => table.locator('.el-table__header-wrapper .el-checkbox').first().click()
  const open = async kind => {
    const title = kind === 'management' ? '批量修改使用状态' : '批量修改检测状态'
    await page.getByRole('button', { name: title, exact: true }).click()
    const dialog = page.getByRole('dialog', { name: title, exact: true })
    await dialog.waitFor()
    return dialog
  }
  const choose = async (dialog, value) => {
    await dialog.locator('.el-select').click()
    await page.getByRole('option', { name: value, exact: true }).click()
  }
  const verify = () => { assert.deepEqual(state.errors, [], 'Batch-status runtime errors'); assert.deepEqual(state.unexpected, [], 'Unexpected API calls') }
  return { context, page, state, table, selectAll, open, choose, verify }
}

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  try {
    const manager = await fixture(browser, ['email:view', 'email:manage'])
    try {
      const { page, state, table } = manager
      for (const name of ['批量修改使用状态', '批量修改检测状态']) assert(await page.getByRole('button', { name, exact: true }).isDisabled(), 'Selection is required')
      await manager.selectAll()
      let dialog = await manager.open('management')
      const submit = dialog.getByRole('button', { name: '确认修改', exact: true })
      await submit.click()
      await page.locator('.el-message').getByText('请选择目标状态', { exact: true }).waitFor()
      assert.equal(state.attempts.length, 0, 'An empty target must not issue a request')
      await dialog.locator('.el-select').click()
      for (const name of ['闲置', '使用中', '锁定', '废弃']) await page.getByRole('option', { name, exact: true }).waitFor()
      assert.equal(await page.getByRole('option', { name: '已出售', exact: true }).count(), 0, 'Sales retain their transaction workflow')
      await page.getByRole('option', { name: '锁定', exact: true }).click()
      await dialog.locator('summary').click()
      for (const email of emails) await dialog.getByText(email.email, { exact: true }).waitFor()
      await page.getByRole('button', { name: '清空选择', exact: true }).evaluate(button => button.click())
      assert((await dialog.innerText()).includes('本次修改 2 个邮箱的使用状态'), 'Dialog retains its selection snapshot')
      state.defer = true
      const request = page.waitForRequest('**/api/emails/batch-status')
      await submit.click(); await request
      assert(await submit.isDisabled())
      assert(await dialog.getByRole('button', { name: '取消', exact: true }).isDisabled())
      assert.equal(await dialog.locator('.el-dialog__headerbtn').count(), 0, 'Pending request hides close control')
      await submit.evaluate(button => { button.click(); button.click() })
      await page.keyboard.press('Escape')
      assert(await dialog.isVisible(), 'Pending request locks dialog close')
      assert.equal(state.attempts.length, 1, 'Double clicks issue one atomic request')
      assert.deepEqual(state.attempts[0], { email_ids: [1, 2], management_status: '锁定' })
      const before = state.lists
      await state.release(); state.defer = false
      await dialog.waitFor({ state: 'hidden' })
      await page.waitForFunction(() => document.querySelector('.batch-actions')?.textContent.includes('已选 0 个邮箱'))
      await table.locator('.el-table__body-wrapper .el-tag').filter({ hasText: /^锁定$/ }).first().waitFor()
      assert.equal(state.lists, before + 1, 'Success refreshes the list once')
      assert.equal(await table.locator('.el-table__body-wrapper .el-checkbox.is-checked').count(), 0)
      assert.equal(state.checks.length, 0, 'Management change does not invoke Gmail checks')

      await manager.selectAll()
      dialog = await manager.open('check')
      assert((await dialog.innerText()).includes('手动标记检测状态，不会发起 Gmail 检测'))
      await dialog.locator('.el-select').click()
      for (const name of ['正常', '封禁', '验证', '未注册', '检测失败', '未检测（清空标记）']) await page.getByRole('option', { name, exact: true }).waitFor()
      await page.getByRole('option', { name: '验证', exact: true }).click()
      const retrySubmit = dialog.getByRole('button', { name: '确认修改', exact: true })
      state.mode = 'conflict'
      await retrySubmit.click()
      await dialog.locator('.batch-status-error').getByText('所选邮箱的状态已变化，请刷新后重新选择', { exact: true }).waitFor()
      assert(await dialog.isVisible())
      assert.equal(await dialog.locator('.el-select__placeholder').innerText(), '验证', 'Conflict preserves target for retry')
      assert((await dialog.innerText()).includes('本次修改 2 个邮箱的检测状态'))
      assert.equal(state.checks.length, 0, 'Manual status never invokes the detection API')
      state.mode = 'success'
      await retrySubmit.click()
      await dialog.waitFor({ state: 'hidden' })
      assert.equal(state.attempts.length, 3)
      assert.deepEqual(state.attempts.slice(1), [{ email_ids: [1, 2], gmail_check_status: '验证' }, { email_ids: [1, 2], gmail_check_status: '验证' }])
      await table.locator('.el-table__body-wrapper .manual-check-tag').first().waitFor()
      assert.equal(await table.locator('.manual-check-tag').first().getAttribute('title'), '人工标记状态，未实际检测')
      await table.locator('.email-name').first().click()
      await table.locator('.manual-check-note').first().getByText('（人工标记，未实际检测）', { exact: true }).waitFor()
      await table.locator('.email-name').first().click()
      assert.equal(state.checks.length, 0)
      await manager.selectAll()
      dialog = await manager.open('check')
      await manager.choose(dialog, '未检测（清空标记）')
      await dialog.getByRole('button', { name: '确认修改', exact: true }).click()
      await dialog.waitFor({ state: 'hidden' })
      assert.deepEqual(state.attempts.at(-1), { email_ids: [1, 2], gmail_check_status: null })
      await table.locator('.el-table__body-wrapper .el-tag').filter({ hasText: /^未检测$/ }).first().waitFor()
      assert.equal(await table.locator('.el-table__body-wrapper .manual-check-tag').count(), 0)
      manager.verify()
    } finally { await manager.context.close() }

    const viewer = await fixture(browser, ['email:view', 'email:check'])
    try {
      const { page, state, table } = viewer
      for (const name of ['批量修改使用状态', '批量修改检测状态']) assert.equal(await page.getByRole('button', { name, exact: true }).count(), 0, 'Manage permission is required')
      const check = table.locator('.el-table__body-wrapper tr.el-table__row').first().getByRole('button', { name: '检测', exact: true })
      await check.click()
      const confirm = page.getByRole('dialog', { name: '邮箱状态检测', exact: true })
      await confirm.waitFor()
      await confirm.getByRole('button', { name: '确定', exact: true }).click()
      await page.getByText('检测完成', { exact: true }).waitFor()
      assert.deepEqual(state.checks, [{ account_ids: [1], consent: true }], 'The original Gmail check remains functional')
      assert.deepEqual(state.attempts, [])
      await table.locator('.el-table__body-wrapper tr.el-table__row').first().locator('.el-checkbox').click()
      await page.getByRole('button', { name: '检测选中 1', exact: true }).waitFor()
      viewer.verify()
    } finally { await viewer.context.close() }

    const mobile = await fixture(browser, ['email:view', 'email:manage'], { width: 390, height: 844 })
    try {
      await mobile.selectAll()
      const bounds = await mobile.page.locator('.batch-actions').evaluate(element => {
        const outer = element.getBoundingClientRect()
        return { width: innerWidth, outer: { left: outer.left, right: outer.right }, buttons: [...element.querySelectorAll('button')].map(button => { const box = button.getBoundingClientRect(); return { left: box.left, right: box.right, top: box.top } }) }
      })
      assert(bounds.outer.left >= 0 && bounds.outer.right <= bounds.width + 1)
      assert(bounds.buttons.every(button => button.left >= 0 && button.right <= bounds.width + 1), 'Mobile batch controls wrap within the viewport')
      assert(new Set(bounds.buttons.map(button => button.top)).size > 1, 'Mobile actions wrap to multiple rows')
      const dialog = await mobile.open('check')
      const box = await dialog.boundingBox()
      assert(box.x >= 0 && box.x + box.width <= 391, 'Batch dialog fits a phone viewport')
      mobile.verify()
    } finally { await mobile.context.close() }
  } finally { await close() }
  console.log('Email batch status: permissions, target validation, one-field requests, immutable selection, loading locks, conflict retry, manual/clear metadata, refresh/selection reset, existing Gmail check and mobile wrapping passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
