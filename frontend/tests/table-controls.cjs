// Run against Vite: node frontend/tests/table-controls.cjs. Every API is isolated.
const assert = require('node:assert/strict')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const deadline = setTimeout(() => { console.error('Table controls exceeded 90 seconds'); process.exit(2) }, 90000)
const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'

async function main() {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
  const context = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  const errors = [], requests = [], unexpected = []
  const email = { id: 1, email: 'alpha@example.invalid', password: 'fixture-copy-value', country: 'US', platform_tags: ['TikTok'], management_status: '闲置', gmail_check_status: '正常', current_relation_count: 0, purchase_channel: 'alpha', purchase_price: 2, sale_price: 10, gmail_checked_at: '2026-10-07T12:00:00', device_name: 'phone', node_ip: '127.0.0.1' }
  const account = { id: 1, username: 'monitor-fixture', account: 'operator-fixture', nickname: 'fixture', platform: 'tiktok', status: '正常', follower_count: 2, following_count: 3, like_count: 10, video_count: 1, is_active: true, enable_video_monitoring: true, platform_tags: [], accounts: [], latest_check_status: 'success', followers_change: 1, yesterday_video_count: 1, yesterday_video_plays: [10] }
  const member = { id: 1, username: 'member-fixture', real_name: 'Fixture', department_name: 'QA', roles: [], is_active: true }
  const reportItems = Array.from({ length: 21 }, (_, index) => ({ username: `member-${String(index).padStart(2, '0')}`, kind: 'card_key', reference: `record-${index}`, time: `2026-10-${String(index + 1).padStart(2, '0')}T12:00:00Z` }))
  await context.addInitScript(() => {
    localStorage.setItem('token', 'table-controls-isolated')
    if (!localStorage.getItem('user')) localStorage.setItem('user', JSON.stringify({ username: 'table-controls', is_super_admin: true }))
    localStorage.setItem('permissions', JSON.stringify(['*']))
    window.__copies = []
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => window.__copies.push(text) } })
  })
  await context.route('**/api/**', async route => {
    const requestUrl = new URL(route.request().url()), endpoint = requestUrl.pathname
    if (!endpoint.startsWith('/api/')) return route.continue()
    requests.push(requestUrl)
    const responses = {
      '/api/settings/public': { site_name: 'Table controls' }, '/api/updates/check': { current_version: '1.1.16', has_update: false }, '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] }, '/api/work-items/summary': { overdue: 0, pending: 0, due_soon: 0 },
      '/api/emails/platforms': [{ id: 1, name: 'TikTok', is_active: true }], '/api/emails': { items: [email], total: 1 }, '/api/emails/1/relations': [], '/api/emails/1/asset-history': [],
      '/api/projects': [{ id: 1, name: 'fixture-project', account_count: 1 }], '/api/proxies': [], '/api/accounts': { items: [account], total: 1 }, '/api/accounts/1': account,
      '/api/accounts/1/trends': { data_points: [] }, '/api/accounts/1/history': [{ id: 1, checked_at: '2026-10-07T12:00:00', follower_count: 2, check_status: 'success' }], '/api/accounts/1/videos': { items: [{ id: 1, video_id: '1', title: 'fixture-video', published_at: '2026-10-07T12:00:00', play_count: 2 }], total: 1 },
      '/api/op-accounts': { items: [account], total: 1 }, '/api/proxy-nodes': { items: [{ id: 1, ip: '127.0.0.1', port: 80, protocol: 'http', country: 'US', status: 'idle', devices: [], accounts: [] }], total: 1 }, '/api/devices': { items: [{ id: 1, name: 'fixture-device', device_type: 'phone', owner_name: 'Fixture', accounts: [], node_ip: '127.0.0.1' }], total: 1 },
      '/api/work-items/categories': ['其他'], '/api/work-items/members': [member], '/api/work-items': { items: [{ id: 1, category: '其他', title: 'fixture-memo', content: 'fixture body', reminder_users: [], is_done: false }], total: 1 },
      '/api/team/member': { items: [member], total: 1 }, '/api/team/dept/tree': [], '/api/team/role': [{ id: 1, name: 'fixture-role', permissions: [], data_scope: 'all' }],
      '/api/card-keys': [{ id: 1, name: 'fixture-card-project', is_active: true, members: [], member_stats: [], can_claim: true, target_platform: null, available: 1, claimed: 0, consumed: 0 }], '/api/card-keys/members': [member], '/api/card-keys/platforms': [{ id: 1, name: 'Zulu', is_active: true }, { id: 2, name: 'Alpha', is_active: false }], '/api/card-keys/1/keys': { items: [], total: 0 }, '/api/card-keys/1/work-report': { members: [{ username: 'fixture-member', keys_consumed: 2, emails_completed: 1 }], items: reportItems },
    }
    if (!(endpoint in responses)) { unexpected.push(endpoint); return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API ' + endpoint } }) }
    return route.fulfill({ json: responses[endpoint] })
  })
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  page.on('pageerror', error => errors.push(error.message))
  const table = id => page.locator(`.crm-table-wrapper[data-table-id="${id}"]`)
  const visit = async (route, id) => { await page.goto(url + route, { waitUntil: 'commit' }); await table(id).locator('.el-table__header-wrapper').waitFor(); console.log('table ready:', id) }
  const latestEmail = () => requests.filter(request => request.pathname === '/api/emails').at(-1)
  const closePopovers = async () => { await page.keyboard.press('Escape'); await page.locator('.page-heading').first().click({ force: true }) }
  const openFilter = async label => { await closePopovers(); await table('emails').getByRole('button', { name: label + '筛选', exact: true }).click(); const panels = page.locator('.crm-table-filter-panel:visible'); await panels.last().waitFor(); return panels.last() }
  const submit = async panel => { const before = requests.filter(request => request.pathname === '/api/emails').length; await panel.getByRole('button', { name: '查询', exact: true }).click(); await page.waitForFunction(() => document.querySelector('.crm-table-filter-button.is-active')); await page.waitForTimeout(50); assert(requests.filter(request => request.pathname === '/api/emails').length > before) }
  try {
    await visit('/emails', 'emails')
    let panel = await openFilter('邮箱'); await panel.getByPlaceholder('包含文字').fill('alpha'); await submit(panel)
    assert.equal(JSON.parse(latestEmail().searchParams.get('table_filters')).email.value, 'alpha')
    panel = await openFilter('当前关联'); await panel.getByPlaceholder('最小值').fill('0'); await panel.getByPlaceholder('最大值').fill('2'); await submit(panel)
    assert.equal(JSON.parse(latestEmail().searchParams.get('table_filters')).current_relation_count.min, '0')
    panel = await openFilter('采购 / 出售'); await panel.locator('.el-select').click(); await page.getByRole('option', { name: '采购金额', exact: true }).click(); await panel.getByPlaceholder('最小值').fill('0'); await submit(panel)
    assert.equal(JSON.parse(latestEmail().searchParams.get('table_filters')).purchase_price.min, '0')
    panel = await openFilter('最后检测'); await panel.getByPlaceholder('开始日期').fill('2026-10-07'); await panel.getByPlaceholder('结束日期').fill('2026-10-07'); await panel.getByPlaceholder('结束日期').press('Tab'); await submit(panel)
    assert.equal(JSON.parse(latestEmail().searchParams.get('table_filters')).gmail_checked_at.max, '2026-10-07')
    panel = await openFilter('使用状态'); await panel.locator('.el-select').click(); await page.getByRole('option', { name: '闲置', exact: true }).click(); await panel.getByRole('button', { name: '查询', exact: true }).click(); await page.waitForTimeout(100)
    assert.deepEqual(JSON.parse(latestEmail().searchParams.get('table_filters')).management_status.value, ['闲置'])
    await closePopovers(); console.log('remote filters passed')
    await page.reload({ waitUntil: 'commit' }); await table('emails').getByRole('button', { name: '邮箱筛选', exact: true }).waitFor(); assert.equal(JSON.parse(latestEmail().searchParams.get('table_filters')).email.value, 'alpha')
    const countryHeader = table('emails').locator('th').filter({ has: page.getByRole('button', { name: '国家筛选', exact: true }) })
    await countryHeader.locator('.sort-caret.ascending').dispatchEvent('click'); await page.waitForTimeout(150); assert.equal(latestEmail().searchParams.get('sort_order'), 'asc')
    await countryHeader.locator('.sort-caret.descending').dispatchEvent('click'); await page.waitForTimeout(150); assert.equal(latestEmail().searchParams.get('sort_order'), 'desc')
    const count = requests.length; await page.waitForTimeout(100); assert(requests.length - count < 3, 'Sort synchronization flooded requests')
    await table('emails').getByRole('button', { name: '重置查询', exact: true }).click(); await page.waitForTimeout(80); assert.equal(latestEmail().searchParams.get('sort_by'), null)
    await table('emails').locator('th').filter({ has: page.getByRole('button', { name: '最后检测筛选', exact: true }) }).locator('.sort-caret.ascending').dispatchEvent('click'); await page.waitForTimeout(100)
    const selection = table('emails').locator('.el-table__body-wrapper tr').first().locator('.el-checkbox')
    await selection.click(); assert((await page.locator('.page-heading').innerText()).includes('检测选中 1'))
    await table('emails').getByRole('button', { name: '列设置', exact: true }).click(); console.log('settings clicked')
    const dialog = page.getByRole('dialog', { name: '列设置', exact: true }); await dialog.waitFor(); console.log('settings ready')
    const countryRow = dialog.locator('.crm-table-settings-row').filter({ hasText: /^⋮⋮国家/ })
    await countryRow.locator('.el-checkbox__label').click(); await dialog.getByRole('button', { name: '使用状态上移', exact: true }).click(); await dialog.getByRole('button', { name: '完成', exact: true }).click()
    assert.equal(await table('emails').getByRole('button', { name: '国家筛选', exact: true }).count(), 0)
    assert((await table('emails').locator('th').filter({ has: page.getByRole('button', { name: '最后检测筛选', exact: true }) }).getAttribute('class')).includes('ascending'), 'Layout changes must restore the active sort caret')
    const emailHeader = table('emails').locator('th').filter({ has: page.getByRole('button', { name: '邮箱筛选', exact: true }) }); await emailHeader.scrollIntoViewIfNeeded(); const beforeWidth = await emailHeader.boundingBox()
    await emailHeader.dispatchEvent('mousemove', { clientX: beforeWidth.x + beforeWidth.width - 2, clientY: beforeWidth.y + beforeWidth.height / 2 }); await emailHeader.dispatchEvent('mousedown', { clientX: beforeWidth.x + beforeWidth.width - 2, clientY: beforeWidth.y + beforeWidth.height / 2, button: 0 }); await page.mouse.move(beforeWidth.x + beforeWidth.width + 35, beforeWidth.y + beforeWidth.height / 2, { steps: 4 }); await page.mouse.up()
    await page.waitForTimeout(100)
    const storedLayout = await page.evaluate(() => JSON.parse(localStorage.getItem('tk-crm:table-layout:table-controls:emails')))
    assert(storedLayout.hidden.includes('country')); assert(storedLayout.order.indexOf('management_status') < storedLayout.order.indexOf('current_relation_count')); assert(storedLayout.widths.email >= 250, 'Column drag width must persist: ' + JSON.stringify(storedLayout.widths))
    await page.screenshot({ path: '.orchestration/table-email-layout.png', fullPage: true })
    await page.locator('.email-copy-actions').first().getByRole('button', { name: '复制邮箱', exact: true }).click(); assert.deepEqual(await page.evaluate(() => window.__copies), [email.email])
    await page.locator('.email-name').first().click(); await page.locator('.email-expanded').waitFor(); await page.locator('.email-name').first().click()
    await page.reload({ waitUntil: 'domcontentloaded' }); await table('emails').locator('.el-table').waitFor(); assert.equal(await table('emails').getByRole('button', { name: '国家筛选', exact: true }).count(), 0)
    await page.evaluate(() => localStorage.setItem('user', JSON.stringify({ username: 'other-user', is_super_admin: true }))); await page.reload({ waitUntil: 'domcontentloaded' }); await table('emails').getByRole('button', { name: '国家筛选', exact: true }).waitFor()
    console.log('column layout, copy, expand, reload and isolation passed')
    for (const [route, id] of [['/monitor', 'monitor-accounts'], ['/op-accounts', 'op-accounts'], ['/work-items', 'work-items'], ['/proxy-nodes', 'proxy-nodes'], ['/devices', 'devices'], ['/team/manage', 'team-members'], ['/accounts/1', 'account-detail-history']]) await visit(route, id)
    await visit('/card-keys', 'card-key-records')
    await table('card-key-work-report-items').evaluate(element => { element.closest('details').open = true })
    const report = table('card-key-work-report-items'); await report.locator('th').filter({ hasText: '成员' }).locator('.sort-caret.descending').click({ force: true })
    assert((await report.locator('.el-table__body tr').first().innerText()).includes('member-20'), 'Local sort must operate before page slicing')
    await report.getByRole('button', { name: '成员筛选', exact: true }).click(); const reportPanel = page.locator('.crm-table-filter-panel:visible').last(); await reportPanel.getByPlaceholder('包含文字').fill('member-20'); await reportPanel.getByRole('button', { name: '查询', exact: true }).click()
    assert.equal(await report.locator('.el-table__body tr').count(), 1, 'Local filter must search rows beyond the first original page')
    console.log('representative routes and local full-data sort passed')
    assert.deepEqual(errors, [], 'Page render errors')
    assert.deepEqual(unexpected, [], 'Unexpected APIs were contacted')
    console.log('Table controls browser acceptance passed')
  } finally {
    const closing = browser.close(); await Promise.race([closing, new Promise(resolve => setTimeout(resolve, 2000))]); clearTimeout(deadline)
  }
}

main().then(() => process.exit(0)).catch(error => { console.error(error); clearTimeout(deadline); process.exit(1) })
