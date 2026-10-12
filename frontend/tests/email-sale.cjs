// Run against Vite: node frontend/tests/email-sale.cjs. All API traffic is mocked.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')

const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
const today = '2026-10-12'
const initialEmails = [
  { id: 1, email: 'sale-one@example.invalid', password: 'password-one-<&>', recovery_email: 'recovery@example.invalid', totp_secret: 'JBSWY3DPEHPK3PXP', purchase_channel: 'internal-supplier', purchase_price: 2, remark: 'internal-remark' },
  { id: 2, email: 'sale-two@example.invalid', password: 'password-two', recovery_email: null, totp_secret: null, purchase_channel: 'internal-supplier', purchase_price: 2, remark: 'internal-remark' },
].map(row => ({ ...row, management_status: '闲置', current_relation_count: 0, platform_tags: [], sellers: [] }))
const delivery = initialEmails.map(row => [row.email, row.password, row.recovery_email || '', row.totp_secret || ''].join('----')).join('\n')

async function fixture(browser, permissions) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, timezoneId: 'Asia/Shanghai' })
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  // 01:30 in China is still yesterday in UTC; this catches UTC date defaults.
  await page.clock.install({ time: new Date('2026-10-11T17:30:00Z') })
  await page.addInitScript(permissions => {
    localStorage.setItem('token', 'isolated-email-sale-fixture')
    localStorage.setItem('user', JSON.stringify({ username: 'sale-test' }))
    localStorage.setItem('permissions', JSON.stringify(permissions))
    window.__copies = []
    window.__clipboardMode = 'available'
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => {
      if (window.__clipboardMode !== 'available') throw new Error('clipboard denied')
      window.__copies.push(text)
    } } })
    document.execCommand = action => {
      if (action !== 'copy' || window.__clipboardMode === 'failure') return false
      window.__copies.push(document.querySelector('textarea[readonly]').value)
      return true
    }
  }, permissions)
  const state = { emails: structuredClone(initialEmails), attempts: [], lists: [], unexpected: [], errors: [], memberRequests: 0, mode: 'success', defer: false, release: null }
  page.on('pageerror', error => state.errors.push(error.message))
  await page.route('**/api/**', async route => {
    const request = route.request(), requestUrl = new URL(request.url()), endpoint = requestUrl.pathname
    if (!endpoint.startsWith('/api/')) return route.continue()
    if (endpoint === '/api/emails/batch-sale') {
      assert.equal(request.method(), 'POST')
      const body = request.postDataJSON()
      state.attempts.push(body)
      const respond = async () => {
        if (state.mode === 'conflict') return route.fulfill({ status: 409, json: { detail: '所选邮箱包含已出售邮箱，请刷新后重新选择' } })
        for (const row of state.emails) if (body.email_ids.includes(row.id)) Object.assign(row, body, { management_status: '已出售' })
        return route.fulfill({ json: { updated: body.email_ids.length, email_ids: body.email_ids } })
      }
      if (state.defer) return new Promise(resolve => { state.release = async () => { await respond(); resolve() } })
      return respond()
    }
    if (endpoint === '/api/emails') {
      state.lists.push(requestUrl)
      const status = requestUrl.searchParams.get('management_status')
      const rows = state.emails.filter(row => !status || row.management_status === status)
      return route.fulfill({ json: { total: rows.length, items: rows } })
    }
    if (endpoint === '/api/team/member') state.memberRequests += 1
    const responses = {
      '/api/settings/public': { site_name: '批量售出验收' },
      '/api/updates/check': { current_version: '1.1.17', has_update: false },
      '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] },
      '/api/work-items/summary': {}, '/api/emails/platforms': [],
      '/api/team/member': { items: [{ id: 1, username: 'sale-test', real_name: '售卖测试', is_active: true }], total: 1 },
    }
    if (!(endpoint in responses)) {
      state.unexpected.push(endpoint)
      return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API ' + endpoint } })
    }
    return route.fulfill({ json: responses[endpoint] })
  })
  await page.goto(url + '/emails')
  const table = page.locator('.crm-table-wrapper[data-table-id="emails"]')
  await table.locator('.el-table__body-wrapper tbody tr').first().waitFor()
  const dialog = page.getByRole('dialog', { name: '批量售出邮箱', exact: true })
  const field = label => dialog.locator('.el-form-item').filter({ has: page.getByText(label, { exact: true }) }).locator('input').first()
  const selectAll = () => table.locator('.el-table__header-wrapper .el-checkbox').first().click()
  const openSale = async () => { await page.getByRole('button', { name: '批量售出', exact: true }).click(); await dialog.waitFor() }
  const check = () => { assert.deepEqual(state.errors, [], 'Email sale runtime errors'); assert.deepEqual(state.unexpected, [], 'Unexpected APIs') }
  return { context, page, state, table, dialog, field, selectAll, openSale, check }
}

async function screenshot(page, suffix) {
  const artifact = process.env.TKCRM_EMAIL_SALE_ARTIFACT
  if (!artifact) return
  const parsed = path.parse(artifact), target = suffix ? path.join(parsed.dir, parsed.name + '-' + suffix + (parsed.ext || '.png')) : artifact
  fs.mkdirSync(path.dirname(target), { recursive: true })
  await page.screenshot({ path: target, fullPage: true, style: '.el-message { visibility: hidden !important }' })
}

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  try {
    const sale = await fixture(browser, ['email:view', 'email:manage'])
    try {
      const { page, state, table, dialog, field } = sale
      assert(await page.getByRole('button', { name: '批量售出', exact: true }).isDisabled(), 'Sale requires a selection')
      assert(await page.getByRole('button', { name: '复制选中资料', exact: true }).isDisabled(), 'Batch copy requires a selection')
      await page.locator('.el-pagination__sizes .el-select').click()
      for (const size of [50, 100, 200, 500]) assert.equal(await page.locator('li').filter({ hasText: `${size}/page` }).count(), 1)
      const resized = page.waitForRequest(request => new URL(request.url()).pathname === '/api/emails' && new URL(request.url()).searchParams.get('limit') === '500')
      await page.getByText('500/page', { exact: true }).click()
      await resized
      // Sell from the idle filter, so the saved rows disappear without closing the receipt.
      const idleRequest = page.waitForRequest(request => new URL(request.url()).pathname === '/api/emails' && new URL(request.url()).searchParams.get('management_status') === '闲置')
      await page.locator('.filters .el-select').last().click()
      await page.locator('.el-select-dropdown__item:visible').filter({ hasText: '闲置' }).first().click()
      await idleRequest
      await sale.selectAll()
      await page.getByRole('button', { name: '复制选中资料', exact: true }).click()
      await page.waitForFunction(() => window.__copies.length === 1)
      assert.deepEqual(await page.evaluate(() => window.__copies), [delivery])
      // Preserve the individual credential format while adding batch delivery format.
      await page.locator('.email-copy-actions').first().getByRole('button', { name: '复制资料', exact: true }).click()
      await page.waitForFunction(() => window.__copies.length === 2)
      assert.equal(await page.evaluate(() => window.__copies.at(-1)), '邮箱：sale-one@example.invalid\n邮箱密码：password-one-<&>\n辅助邮箱：recovery@example.invalid\n2FA 密钥：JBSWY3DPEHPK3PXP')
      await sale.openSale()
      assert.equal(await field('出售日期').inputValue(), today, 'Sale date must use the China local day')
      assert.equal(await field('出售人').inputValue(), 'sale-test')
      assert.notEqual(await field('出售人').getAttribute('readonly'), null)
      assert.equal(state.memberRequests, 0, 'Own sale must not require member-list permission')
      const submit = dialog.getByRole('button', { name: '确认售出并复制资料', exact: true })
      await submit.click()
      await page.getByText('请填写出售客户', { exact: true }).waitFor()
      await field('出售客户').fill('  客户甲  ')
      await submit.click()
      await page.getByText('请填写有效的出售金额', { exact: true }).waitFor()
      await field('出售单价（每个）').fill('8')
      await field('出售单价（每个）').press('Tab')
      await dialog.getByText('2 个 × ¥8.00，合计 ¥16.00', { exact: true }).waitFor()
      await field('出售日期').fill('')
      await field('出售日期').press('Tab')
      await submit.click()
      await page.getByText('请填写出售日期', { exact: true }).waitFor()
      assert.equal(state.attempts.length, 0, 'Incomplete sale must never issue a mutation')
      await field('出售日期').fill(today)
      await field('出售日期').press('Tab')
      await screenshot(page)
      // Change the live selection behind the modal; the saved batch must stay intact.
      await page.getByRole('button', { name: '清空选择', exact: true }).evaluate(button => button.click())
      assert((await dialog.innerText()).includes('本次售出 2 个邮箱'))
      state.defer = true
      const request = page.waitForRequest('**/api/emails/batch-sale')
      await submit.click()
      await request
      assert(await submit.isDisabled(), 'Pending sale must disable duplicate submits')
      assert(await dialog.getByRole('button', { name: '取消', exact: true }).isDisabled())
      await submit.evaluate(button => { button.click(); button.click() })
      await page.keyboard.press('Escape')
      assert(await dialog.isVisible(), 'A pending sale must retain its dialog')
      assert.equal(state.attempts.length, 1)
      assert.deepEqual(state.attempts[0], { email_ids: [1, 2], sale_customer: '客户甲', sale_price: 8, sale_date: today, sellers: ['sale-test'] })
      await state.release()
      await dialog.getByText('成功售出 2 个邮箱', { exact: true }).waitFor()
      const receipt = dialog.locator('.delivery-text textarea')
      assert.equal(await receipt.inputValue(), delivery)
      assert.notEqual(await receipt.getAttribute('readonly'), null)
      await page.waitForFunction(() => window.__copies.length === 3)
      assert.equal(await page.evaluate(() => window.__copies.at(-1)), delivery)
      // The active filter hides sold rows; the delivery receipt must remain available.
      await page.waitForFunction(() => document.querySelectorAll('.email-table .el-table__body-wrapper tbody tr').length === 0 || document.querySelector('.email-table .el-table__empty-text'))
      assert(await dialog.isVisible(), 'Filtering out sold rows must preserve the delivery receipt')
      for (const internal of ['客户甲', 'sale-test', today, 'internal-supplier', 'internal-remark']) assert(!delivery.includes(internal), 'Customer delivery leaked a trade field: ' + internal)
      await screenshot(page, 'receipt')
      await dialog.getByRole('button', { name: '复制交付资料', exact: true }).click()
      await page.waitForFunction(() => window.__copies.length === 4)
      assert.equal(await page.evaluate(() => window.__copies.at(-1)), delivery)
      await dialog.getByRole('button', { name: '完成', exact: true }).click()
      await dialog.waitFor({ state: 'hidden' })
      sale.check()
    } finally { await sale.context.close() }

    const retry = await fixture(browser, ['email:view', 'email:manage'])
    try {
      const { page, state, dialog, field } = retry
      await retry.selectAll(); await retry.openSale()
      await field('出售客户').fill('客户乙')
      await field('出售单价（每个）').fill('8'); await field('出售单价（每个）').press('Tab')
      await page.keyboard.press('Escape')
      state.mode = 'conflict'
      await dialog.getByRole('button', { name: '确认售出并复制资料', exact: true }).click()
      await page.getByText('所选邮箱包含已出售邮箱，请刷新后重新选择', { exact: true }).waitFor()
      assert(await dialog.isVisible())
      assert.equal(await field('出售客户').inputValue(), '客户乙')
      assert.equal(Number(await field('出售单价（每个）').inputValue()), 8)
      assert.equal(await field('出售日期').inputValue(), today)
      assert.deepEqual(await page.evaluate(() => window.__copies), [], 'Failed sale must not copy delivery credentials')
      assert.equal(state.attempts.length, 1)
      state.mode = 'success'
      await page.evaluate(() => { window.__clipboardMode = 'failure' })
      await dialog.getByRole('button', { name: '确认售出并复制资料', exact: true }).click()
      await dialog.getByText('成功售出 2 个邮箱', { exact: true }).waitFor()
      await page.getByText('售出已保存，复制失败，请手动复制下方交付资料或重试', { exact: true }).waitFor()
      assert.equal(await dialog.locator('.delivery-text textarea').inputValue(), delivery, 'Clipboard failure must leave a manual delivery copy')
      assert.deepEqual(await page.evaluate(() => window.__copies), [])
      assert.equal(await page.locator('textarea[readonly]').count(), 1, 'Fallback must remove its temporary textarea')
      await page.evaluate(() => { window.__clipboardMode = 'available' })
      await dialog.getByRole('button', { name: '复制交付资料', exact: true }).click()
      await page.waitForFunction(() => window.__copies.length === 1)
      assert.deepEqual(await page.evaluate(() => window.__copies), [delivery])
      assert.equal(state.attempts.length, 2, 'Copy retry must never repeat the sale mutation')
      retry.check()
    } finally { await retry.context.close() }

    const viewer = await fixture(browser, ['email:view'])
    try {
      const { page, state } = viewer
      assert.equal(await page.getByRole('button', { name: '批量售出', exact: true }).count(), 0)
      assert(await page.getByRole('button', { name: '复制选中资料', exact: true }).isDisabled())
      await viewer.selectAll()
      await page.getByRole('button', { name: '复制选中资料', exact: true }).click()
      await page.waitForFunction(() => window.__copies.length === 1)
      assert.deepEqual(await page.evaluate(() => window.__copies), [delivery])
      assert.equal(state.memberRequests, 0)
      assert.deepEqual(state.attempts, [])
      viewer.check()
    } finally { await viewer.context.close() }
  } finally { await close() }
  console.log('Email batch sale: validation, local date/user defaults, batch copy, page sizes, immutable selection, atomic request, receipt, conflict/clipboard retries, and view permissions passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
