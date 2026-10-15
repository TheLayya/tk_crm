// Run against Vite: node frontend/tests/card-key-workspace.cjs. All API traffic is mocked.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')

const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5194'
const artifactDir = path.resolve(process.env.TKCRM_UI_ARTIFACT_DIR || path.join(__dirname, '../../.orchestration/card-key-workspace-20261015'))

const longContent = 'https://example.invalid/claim?' + Array.from({ length: 18 }, (_, index) => `token${index + 1}=abcdefghijklmnopqrstuvwxyz0123456789`).join('&')
const keys = Array.from({ length: 30 }, (_, index) => ({
  id: index + 1,
  project_id: 1,
  batch_id: 10,
  batch_no: 'B-20261015-01',
  batch_name: '10月供应商 A',
  batch_status: 'active',
  batch_remark: '团队内部验收批次',
  content: index === 0 ? longContent : `TEAM-CARD-${String(index + 1).padStart(2, '0')}-ABCDEFGHIJKLMN`,
  status: 'available',
  claimed_by: null,
  claimed_at: null,
  consumed_at: null,
  history: [],
  remark: index === 0 ? '长链接样本' : '',
}))
const members = Array.from({ length: 20 }, (_, index) => ({
  username: `member-${String(index + 1).padStart(2, '0')}`,
  keys_consumed: index + 1,
  emails_completed: index % 4,
}))
const reportItems = Array.from({ length: 60 }, (_, index) => ({
  kind: index % 2 ? '平台注册' : '卡密消耗',
  record_id: index + 1,
  username: members[index % members.length].username,
  time: `2026-10-${String((index % 15) + 1).padStart(2, '0')}T02:00:00Z`,
  reference: `${index % 2 ? 'TikTok' : '卡密'} · 明细-${String(index + 1).padStart(2, '0')}`,
}))

async function settledBounds(page, selector) {
  await page.locator(selector).waitFor({ state: 'visible' })
  return page.evaluate(async selector => {
    const target = document.querySelector(selector)
    if (!target) throw new Error('Missing viewport measurement target: ' + selector)
    // Product layout reacts to both tab changes and ResizeObserver; measure only after both settle.
    window.dispatchEvent(new Event('resize'))
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    return new Promise((resolve, reject) => {
      let previous = ''
      let stableFrames = 0
      let lastResize = performance.now()
      const started = performance.now()
      const observer = new ResizeObserver(() => { lastResize = performance.now(); stableFrames = 0 })
      observer.observe(target)
      const root = target.closest('.project-card')
      if (root) observer.observe(root)
      const inspect = () => {
        const bounds = target.getBoundingClientRect()
        const signature = [bounds.x, bounds.y, bounds.width, bounds.height].map(value => Math.round(value * 100)).join('|')
        stableFrames = signature === previous ? stableFrames + 1 : 0
        previous = signature
        if (stableFrames >= 3 && performance.now() - lastResize >= 100) {
          observer.disconnect()
          resolve({ x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, bottom: bounds.bottom, viewportHeight: innerHeight })
        } else if (performance.now() - started > 3000) {
          observer.disconnect()
          reject(new Error('Viewport table did not settle: ' + selector))
        } else requestAnimationFrame(inspect)
      }
      requestAnimationFrame(inspect)
    })
  }, selector)
}

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })
  const state = { requests: [], errors: [], unexpected: [] }
  await context.addInitScript(() => {
    localStorage.setItem('token', 'isolated-card-key-workspace')
    localStorage.setItem('user', JSON.stringify({ username: 'workspace-admin', is_super_admin: true }))
    localStorage.setItem('permissions', JSON.stringify(['card_key:view', 'card_key:manage']))
    window.__copies = []
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => window.__copies.push(text) } })
  })

  const project = {
    id: 1, name: '卡密工作台验收', description: '批次记录与成员工作量', target_platform: '',
    members: ['__all__'], total: keys.length, available: keys.length, claimed: 0, consumed: 0,
    is_active: true, can_claim: true, member_stats: [], emails_completed: 0,
  }
  const batch = {
    id: 10, project_id: 1, batch_no: 'B-20261015-01', name: '10月供应商 A', remark: '团队内部验收批次',
    status: 'active', pause_reason: '', total: keys.length, available: keys.length, claimed: 0, consumed: 0, invalid: 0,
  }
  const respond = json => ({ status: 200, contentType: 'application/json', body: JSON.stringify(json) })
  await context.route('**/api/**', async route => {
    const request = route.request()
    const parsed = new URL(request.url())
    const endpoint = parsed.pathname
    const method = request.method()
    if (!endpoint.startsWith('/api/')) return route.continue()
    state.requests.push({ endpoint, method, query: Object.fromEntries(parsed.searchParams) })
    if (endpoint === '/api/card-keys' && method === 'GET') return route.fulfill(respond([project]))
    if (endpoint === '/api/card-keys/members' && method === 'GET') return route.fulfill(respond(members.map(row => ({ ...row, real_name: row.username }))))
    if (endpoint === '/api/card-keys/platforms' && method === 'GET') return route.fulfill(respond([]))
    const keysMatch = endpoint.match(/^\/api\/card-keys\/(\d+)\/(keys|batches|work-report)$/)
    if (keysMatch && Number(keysMatch[1]) === 1 && method === 'GET') {
      const kind = keysMatch[2]
      if (kind === 'keys') {
        const page = Number(parsed.searchParams.get('page') || 1)
        const pageSize = Number(parsed.searchParams.get('page_size') || 30)
        const batchId = parsed.searchParams.get('batch_id')
        let rows = batchId ? keys.filter(row => row.batch_id === Number(batchId)) : keys
        if (parsed.searchParams.get('mine') === 'true') rows = rows.filter(row => row.claimed_by === 'workspace-admin')
        if (parsed.searchParams.get('status')) rows = rows.filter(row => row.status === parsed.searchParams.get('status'))
        return route.fulfill(respond({ items: rows.slice((page - 1) * pageSize, page * pageSize), total: rows.length }))
      }
      if (kind === 'batches') return route.fulfill(respond([batch]))
      return route.fulfill(respond({ members, items: reportItems }))
    }
    const common = {
      '/api/settings/public': { site_name: 'TkCRM 卡密工作台' },
      '/api/updates/check': { current_version: '1.1.22', has_update: false },
      '/api/updates/status': { status: 'idle' },
      '/api/updates/history': { items: [] },
      '/api/work-items/summary': { overdue: 0, pending: 0, due_soon: 0 },
    }
    if (method === 'GET' && Object.hasOwn(common, endpoint)) return route.fulfill(respond(common[endpoint]))
    state.unexpected.push(`${method} ${endpoint}`)
    return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: `Unexpected isolated API: ${method} ${endpoint}` }) })
  })

  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', error => state.errors.push(error.message))
  try {
    await page.goto(url + '/card-keys', { waitUntil: 'domcontentloaded' })
    const records = page.locator('[data-table-id="card-key-records"]')
    await records.waitFor()
    await page.waitForFunction(() => !document.querySelector('[data-table-id="card-key-records"] .el-loading-mask'))
    assert.equal(await records.locator('.el-table__body-wrapper tr.el-table__row').count(), 30, 'all 30 records are available at the default page size')

    const recordTable = records.locator('.el-table')
    const recordBounds = await settledBounds(page, '[data-table-id="card-key-records"] .el-table')
    assert(recordBounds && recordBounds.height <= 500, `record list must stay bounded: ${JSON.stringify(recordBounds)}`)
    assert(recordBounds.bottom <= recordBounds.viewportHeight - 50, `record footer stays visible above the viewport bottom: ${JSON.stringify(recordBounds)}`)
    const firstRow = records.locator('.el-table__body-wrapper tr.el-table__row').first()
    const rowBounds = await firstRow.boundingBox()
    assert(rowBounds && rowBounds.height > 0 && rowBounds.height <= 72, `record row height must remain compact: ${JSON.stringify(rowBounds)}`)
    console.log(`Record bounds: table=${recordBounds.height}px row=${rowBounds.height}px long-value=${longContent.length} characters`)

    const preview = firstRow.getByRole('button', { name: '查看完整卡密', exact: true })
    await preview.waitFor()
    const previewStyle = await preview.locator('code').evaluate(element => ({ text: element.textContent, whiteSpace: getComputedStyle(element).whiteSpace, overflow: getComputedStyle(element).overflow, textOverflow: getComputedStyle(element).textOverflow }))
    assert.equal(previewStyle.text, longContent, 'long card key keeps the original value in the preview DOM')
    assert.equal(previewStyle.whiteSpace, 'nowrap', 'long card key is one line')
    assert.equal(previewStyle.overflow, 'hidden', 'long card key is clipped instead of expanding the table')
    assert.equal(previewStyle.textOverflow, 'ellipsis', 'long card key uses an ellipsis')
    await preview.click()
    const fullDialog = page.getByRole('dialog', { name: '完整卡密 / 链接', exact: true })
    await fullDialog.waitFor()
    assert.equal(await fullDialog.locator('.full-key-content').innerText(), longContent, 'full card-key dialog shows the complete original value')
    await fullDialog.getByRole('button', { name: '复制完整内容', exact: true }).click()
    assert.equal(await page.evaluate(() => window.__copies.at(-1)), longContent, 'full card-key copy preserves the exact original value')
    await fullDialog.locator('.el-dialog__headerbtn').click()
    await fullDialog.waitFor({ state: 'hidden' })

    const pageSize = page.locator('.pagination .el-select__wrapper')
    await pageSize.click()
    const sizeResponse = page.waitForResponse(response => response.url().includes('/api/card-keys/1/keys?') && new URL(response.url()).searchParams.get('page_size') === '50' && new URL(response.url()).searchParams.get('mine') !== 'true')
    await page.getByRole('option', { name: /50.*(条|page)/ }).click()
    await sizeResponse
    const sizeRequest = state.requests.filter(item => item.endpoint === '/api/card-keys/1/keys' && item.query.mine !== 'true').at(-1)
    assert.equal(sizeRequest.query.page_size, '50', 'record page size sends the selected value to the API')
    assert((await page.locator('.pagination .el-select__placeholder').innerText()).includes('50'), 'selected page size remains visible')

    const recordsTab = page.getByRole('tab', { name: '卡密记录', exact: true })
    const workloadTab = page.getByRole('tab', { name: '成员工作量', exact: true })
    await workloadTab.click()
    const report = page.locator('section.work-report[aria-label="成员工作量统计"]')
    await report.waitFor()
    await page.waitForFunction(() => !document.querySelector('section.work-report .el-loading-mask'))
    assert.equal(await records.isVisible(), false, 'record workspace is hidden while workload is selected')
    const reportRequest = state.requests.filter(item => item.endpoint === '/api/card-keys/1/work-report').at(-1)
    assert(reportRequest.query.date_from && reportRequest.query.date_to, 'default report request has a Beijing date range')
    assert.equal(reportRequest.query.date_from, reportRequest.query.date_to, 'default workload range covers one Beijing day')
    assert.equal(await report.locator('.report-summary > div').filter({ hasText: '参与成员' }).locator('strong').innerText(), '20', 'summary shows all participating members')
    assert.equal(await report.locator('[data-table-id="card-key-work-report-members"] .el-table__body-wrapper tr.el-table__row').count(), 20, 'member summary renders all 20 members')
    const memberBounds = await settledBounds(page, '[data-table-id="card-key-work-report-members"] .el-table')
    assert(memberBounds.bottom <= memberBounds.viewportHeight, `member table stays inside the viewport: ${JSON.stringify(memberBounds)}`)
    await report.getByRole('tab', { name: '完成明细', exact: true }).click()
    assert.equal(await report.locator('[data-table-id="card-key-work-report-items"] .el-table__body-wrapper tr.el-table__row').count(), 10, 'detail table paginates 60 records at ten rows')
    const detailBounds = await settledBounds(page, '[data-table-id="card-key-work-report-items"] .el-table')
    assert(detailBounds.bottom <= detailBounds.viewportHeight - 50, `detail footer stays visible above the viewport bottom: ${JSON.stringify(detailBounds)}`)
    assert(memberBounds && memberBounds.height <= 350, `member summary must stay bounded: ${JSON.stringify(memberBounds)}`)
    assert(detailBounds && detailBounds.height <= 430, `detail list must stay bounded: ${JSON.stringify(detailBounds)}`)
    console.log(`Workload bounds: members=${memberBounds.height}px details=${detailBounds.height}px`)
    await report.getByRole('tab', { name: '成员汇总', exact: true }).click()
    await report.getByRole('button', { name: '查看成员明细：member-01', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.detail-head .el-select__placeholder')?.textContent.includes('member-01'))
    assert.equal(await report.locator('[data-table-id="card-key-work-report-items"] .el-table__body-wrapper tr.el-table__row').count(), 3, 'member summary action filters the detail list')
    assert.equal(await report.getByRole('button', { name: '导出该成员明细 CSV', exact: true }).count(), 1, 'filtered export identifies the selected member scope')
    await report.getByRole('button', { name: '近 7 天', exact: true }).click()
    await page.waitForFunction(() => document.querySelectorAll('[data-table-id="card-key-work-report-items"] .el-table__body-wrapper tr.el-table__row').length >= 1 && document.querySelectorAll('section.work-report .el-loading-mask').length === 0)
    const sevenDayRequest = state.requests.filter(item => item.endpoint === '/api/card-keys/1/work-report').at(-1)
    assert(sevenDayRequest.query.date_from && sevenDayRequest.query.date_to, 'preset report request has a date range')
    assert.equal(Date.parse(sevenDayRequest.query.date_to) - Date.parse(sevenDayRequest.query.date_from), 6 * 86400000, 'seven-day preset includes today and six preceding Beijing dates')
    await report.getByRole('button', { name: '全部时间', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('section.work-report .report-hint')?.textContent.includes('全部历史') && !document.querySelector('section.work-report .el-loading-mask'))
    const allTimeRequest = state.requests.filter(item => item.endpoint === '/api/card-keys/1/work-report').at(-1)
    assert(!allTimeRequest.query.date_from && !allTimeRequest.query.date_to, 'all-time report omits date limits')
    fs.mkdirSync(artifactDir, { recursive: true })
    await page.waitForTimeout(250) // Wait for the Element Plus tab underline transition before capturing evidence.
    await page.screenshot({ path: path.join(artifactDir, 'workload-details-1366.png'), fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
    await report.getByRole('tab', { name: '成员汇总', exact: true }).click()
    await page.waitForTimeout(250)
    await page.screenshot({ path: path.join(artifactDir, 'workload-members-1366.png'), fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
    await recordsTab.click()
    await records.waitFor()
    assert.equal(await report.isVisible(), false, 'workload workspace is hidden after returning to records')
    assert.equal(await records.isVisible(), true, 'records workspace returns without losing the selected page size')
    await page.waitForTimeout(250)
    await page.screenshot({ path: path.join(artifactDir, 'records-1366.png'), fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(100)
    const mobileBounds = await page.locator('.main-content').boundingBox()
    assert(mobileBounds && mobileBounds.width <= 390, 'mobile workspace fits the viewport width')
    const overflow = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }))
    assert(overflow.document <= overflow.viewport + 1 && overflow.body <= overflow.viewport + 1, `mobile card-key workspace overflows: ${JSON.stringify(overflow)}`)
    await page.screenshot({ path: path.join(artifactDir, 'records-390.png'), fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
    await workloadTab.click()
    await report.waitFor()
    await page.waitForFunction(() => !document.querySelector('section.work-report .el-loading-mask'))
    const mobileReportOverflow = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }))
    assert(mobileReportOverflow.document <= mobileReportOverflow.viewport + 1 && mobileReportOverflow.body <= mobileReportOverflow.viewport + 1, `mobile workload overflows: ${JSON.stringify(mobileReportOverflow)}`)
    await page.screenshot({ path: path.join(artifactDir, 'workload-members-390.png'), fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
    assert.deepEqual(state.errors, [], 'runtime page errors')
    assert.deepEqual(state.unexpected, [], `unexpected API calls: ${state.unexpected.join(', ')}`)
    console.log(`PASS card-key workspace: 30 records, long-value copy, bounded tables, page size, 20 members/60 details, tabs and mobile layout; screenshots=${artifactDir}`)
  } finally {
    await context.close()
    await close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
