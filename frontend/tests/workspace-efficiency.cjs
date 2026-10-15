// Run against Vite: node frontend/tests/workspace-efficiency.cjs. All APIs use synthetic fixtures.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
const artifacts = path.resolve(__dirname, '../../.orchestration')
const username = 'workspace-efficiency'
const now = '2026-10-15T02:30:00Z'
const tsv = rows => rows.map(row => row.map(value => {
  const text = String(value ?? '')
  return /[\t\r\n"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}).join('\t')).join('\n')

const accounts = Array.from({ length: 8 }, (_, index) => ({
  id: index + 101, platform: index % 3 === 0 ? 'instagram' : 'tiktok', account: `team_creator_${String(index + 1).padStart(2, '0')}`,
  nickname: ['晨光工作室', '海岸日记', '城市观察', '咖啡时间', '山野记录', '生活手帐', '北方来信', '周末计划'][index],
  password: index === 0 ? 'fixture"password\twith-tab' : `fixture-password-${index + 1}`, totp_secret: 'JBSWY3DPEHPK3PXP',
  email: `team${index + 1}@example.invalid`, email_password: `fixture-email-${index + 1}`, recovery_email: `backup${index + 1}@example.invalid`,
  email_login_url: 'https://example.invalid/mail', phone: `1550000000${index + 1}`, phone_manage_url: 'https://example.invalid/phone',
  status: index === 4 ? '自用' : '正常', country: index % 2 ? '英国' : '美国', registrant: '成员甲', operator: index % 2 ? '成员乙' : '成员甲',
  follower_count: 1200 + index * 1800, following_count: 80 + index, like_count: 6800 + index * 3200, video_count: 15 + index,
  followers_change: index % 3 === 0 ? -8 : 20 + index * 7, yesterday_video_count: index % 3, yesterday_video_plays: index % 3 ? [1250 + index * 40] : [],
  collect_status: 'success', last_collected_at: now, created_at: now, updated_at: now, purchase_channel: '团队采购 A', purchase_price: 12,
  device_name: `工作手机 ${String(index + 1).padStart(2, '0')}`, node_ip: `192.0.2.${index + 10}:1080`, remark: '常规运营账号',
}))
const nodes = accounts.map((account, index) => ({
  id: index + 1, ip: index === 7 ? '2001:db8::18' : `192.0.2.${index + 10}`, port: 1080 + index,
  protocol: index % 2 ? 'http' : 'socks5', username: `fixture-user-${index + 1}`, password: index === 0 ? 'node"secret\tline\nnext' : `fixture-node-${index + 1}`,
  relay_ip: index % 2 ? `198.51.100.${index + 20}` : null, relay_port: index % 2 ? 8080 : null, relay_protocol: index % 2 ? 'http' : null,
  country: index % 2 ? '英国' : '美国', status: index === 5 ? 'disabled' : index % 2 ? 'active' : 'idle', expire_date: '2026-12-31',
  last_test_result: index === 5 ? 'failed' : 'success', last_test_latency: 85 + index * 12, last_test_at: now,
  purchase_channel: '线路采购 A', sale_customer: null, sellers: [], remark: '团队共享线路',
  devices: [{ id: index + 1, name: `工作手机 ${String(index + 1).padStart(2, '0')}` }], accounts: [account],
}))
const devices = accounts.map((account, index) => ({
  id: index + 1, name: `工作手机 ${String(index + 1).padStart(2, '0')}`, device_type: index === 6 ? 'pc' : 'phone',
  owner_id: index % 2 + 1, owner_name: index % 2 ? '成员乙' : '成员甲', node_ip: `${nodes[index].ip}:${nodes[index].port}`,
  accounts: [account], nodes: [nodes[index]], created_at: now, updated_at: now, remark: index === 0 ? '第一组\t备用"设备' : '日常运营终端',
}))
const emails = accounts.map((account, index) => ({
  id: index + 1, email: account.email, password: account.email_password, recovery_email: account.recovery_email,
  totp_secret: index % 2 ? null : 'JBSWY3DPEHPK3PXP', country: account.country, platform_tags: index % 2 ? ['TikTok'] : ['TikTok', 'Instagram'],
  platform_registrants: { TikTok: '成员甲' }, management_status: index % 2 ? '使用中' : '闲置', gmail_check_status: index === 5 ? '验证' : '正常',
  current_relation_count: 1, gmail_checked_at: now, device_name: devices[index].name, node_ip: devices[index].node_ip,
  purchase_channel: '团队采购 A', purchase_price: 2.5, purchase_date: '2026-10-01', sale_price: null, registrant: '成员甲', operator: '成员乙',
  remark: '资料完整，按需领取',
}))
const overview = { counts: { account: 1, device: 1, node: 1 }, current: [], history: [], ban_snapshots: [], note: '验收数据关联概览' }

async function main() {
  const started = Date.now()
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
  let deadline
  try {
    deadline = setTimeout(() => browser.close().catch(() => {}), 85000)
    const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })
    const errors = [], unexpected = [], requests = []
    await context.addInitScript(user => {
      localStorage.setItem('token', 'workspace-efficiency-isolated')
      if (!localStorage.getItem('user')) localStorage.setItem('user', JSON.stringify({ username: user, is_super_admin: true }))
      localStorage.setItem('permissions', JSON.stringify(['*']))
      window.__copies = []
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => window.__copies.push(text) } })
    }, username)
    const responses = {
      '/api/settings/public': { site_name: 'TkCRM 团队工作台' }, '/api/updates/check': { current_version: '1.1.18', has_update: false },
      '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] }, '/api/work-items/summary': { overdue: 0, pending: 3, due_soon: 1 },
      '/api/emails/platforms': [{ id: 1, name: 'TikTok', is_active: true }, { id: 2, name: 'Instagram', is_active: true }],
      '/api/emails': { items: emails, total: emails.length }, '/api/devices': { items: devices, total: devices.length },
      '/api/proxy-nodes': { items: nodes, total: nodes.length }, '/api/op-accounts': { items: accounts, total: accounts.length },
      '/api/op-accounts/filter-options': { country: ['美国', '英国'], registrant: ['成员甲'], operator: ['成员甲', '成员乙'], purchase_channel: ['团队采购 A'], sale_customer: [], device_name: devices.map(row => row.name), node_ip: nodes.map(row => row.ip) },
      '/api/team/member': { items: [{ id: 1, username: 'member-a', real_name: '成员甲' }, { id: 2, username: 'member-b', real_name: '成员乙' }], total: 2 },
    }
    for (const email of emails) {
      responses[`/api/emails/${email.id}/relations`] = [{ id: email.id, platform: accounts[email.id - 1].platform, account: accounts[email.id - 1].account, bound_at: now, operator: '成员甲' }]
      responses[`/api/emails/${email.id}/asset-history`] = []
      responses[`/api/emails/${email.id}/totp`] = { code: '123456', remaining: 30, valid_for: 30 }
    }
    for (const device of devices) {
      responses[`/api/devices/${device.id}`] = device
      responses[`/api/devices/${device.id}/logs`] = { items: [{ id: device.id, action: 'UPDATE', username: '成员甲', summary: '更新终端备注', created_at: now, changes: {} }], total: 1 }
      responses[`/api/devices/${device.id}/association-history`] = overview
    }
    await context.route('**/api/**', async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname
      if (!endpoint.startsWith('/api/')) return route.continue()
      requests.push(`${request.method()} ${endpoint}`)
      if (request.method() !== 'GET' || !Object.hasOwn(responses, endpoint)) {
        unexpected.push(`${request.method()} ${endpoint}`)
        return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API: ' + endpoint } })
      }
      return route.fulfill({ json: responses[endpoint] })
    })
    const page = await context.newPage()
    page.setDefaultTimeout(8000)
    page.on('pageerror', error => errors.push(error.message))
    const table = id => page.locator(`.crm-table-wrapper[data-table-id="${id}"]`)
    const rows = id => table(id).locator('.el-table__body-wrapper tr.el-table__row')
    const ready = async id => {
      try { await rows(id).last().waitFor() }
      catch (error) { console.error('Fixture diagnostics:', { id, errors, unexpected, requests, body: (await page.locator('body').innerText()).slice(0, 1800) }); throw error }
      await page.waitForFunction(tableId => !document.querySelector(`[data-table-id="${tableId}"] .el-loading-mask`), id)
      assert.equal(await rows(id).count(), 8, `${id}: multi-row fixture loaded`)
    }
    const visit = async (route, id) => { await page.goto(url + route, { waitUntil: 'domcontentloaded' }); await ready(id) }
    const selectAll = async id => {
      await table(id).locator('.el-table__header-wrapper .el-checkbox').first().click()
      await page.waitForFunction(tableId => document.querySelector(`[data-table-id="${tableId}"] .crm-table-selection-count`)?.textContent.includes('8'), id)
      assert.equal(await table(id).locator('.crm-row-selected').count(), 8, `${id}: header selected every displayed row`)
    }
    const expectCopy = async (action, expected) => {
      const before = await page.evaluate(() => window.__copies.length)
      await action()
      await page.waitForFunction(count => window.__copies.length === count + 1, before)
      assert.equal(await page.evaluate(() => window.__copies.at(-1)), expected)
    }
    const batchExpand = async (id, details) => {
      await table(id).getByRole('button', { name: '展开选中', exact: true }).click()
      await page.waitForFunction(({ tableId, selector }) => document.querySelectorAll(`[data-table-id="${tableId}"] ${selector}`).length === 8, { tableId: id, selector: details })
      await table(id).getByRole('button', { name: '收起详情', exact: true }).click()
      await page.waitForFunction(({ tableId, selector }) => document.querySelectorAll(`[data-table-id="${tableId}"] ${selector}`).length === 0, { tableId: id, selector: details })
    }
    fs.mkdirSync(artifacts, { recursive: true })
    const checkViewportOverflow = async label => {
      const bounds = await page.evaluate(() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth,
      }))
      assert(bounds.document <= bounds.viewport + 1 && bounds.body <= bounds.viewport + 1, `${label}: outer page overflows ${JSON.stringify(bounds)}`)
    }
    const screenshot = async (id, name) => {
      await checkViewportOverflow(`${id} at 1366px`)
      await table(id).scrollIntoViewIfNeeded()
      await page.evaluate(() => { document.querySelector('main')?.scrollTo(0, 0); window.scrollTo(0, 0) })
      await page.screenshot({ path: path.join(artifacts, `workspace-${name}-1366.png`), style: '.el-message, .el-popper { visibility: hidden !important; }' })
    }

    await visit('/proxy-nodes', 'proxy-nodes')
    await expectCopy(() => rows('proxy-nodes').first().getByRole('button', { name: '复制地址', exact: true }).click(), '192.0.2.10:1080')
    await expectCopy(() => rows('proxy-nodes').last().getByRole('button', { name: '复制地址', exact: true }).click(), '[2001:db8::18]:1087')
    await selectAll('proxy-nodes')
    await expectCopy(() => page.locator('.batch-toolbar').getByRole('button', { name: '复制地址', exact: true }).click(), nodes.map(row => `${row.ip.includes(':') ? `[${row.ip}]` : row.ip}:${row.port}`).join('\n'))
    await expectCopy(() => page.getByRole('button', { name: '复制连接资料', exact: true }).click(), tsv([['IP', '端口', '协议', '用户名', '密码', '中转 IP', '中转端口', '中转协议'], ...nodes.map(row => [row.ip, row.port, row.protocol, row.username, row.password, row.relay_ip, row.relay_port, row.relay_protocol])]))
    await screenshot('proxy-nodes', 'nodes')
    console.log('Nodes: single/batch addresses, IPv6 and original connection TSV passed')

    await visit('/devices', 'devices')
    await expectCopy(() => rows('devices').first().getByRole('button', { name: '复制名称', exact: true }).click(), devices[0].name)
    await selectAll('devices')
    await expectCopy(() => page.getByRole('button', { name: '复制资产概要', exact: true }).click(), tsv([['设备名称', '类型', '所属人', '绑定节点', '绑定账号', '备注'], ...devices.map(row => [row.name, row.device_type === 'phone' ? '手机' : '电脑', row.owner_name, row.node_ip, row.accounts.map(account => account.account).join(' / '), row.remark])]))
    await batchExpand('devices', '.device-inline-details')
    for (const device of devices) for (const suffix of ['', '/logs', '/association-history']) assert(requests.includes(`GET /api/devices/${device.id}${suffix}`), 'Batch expansion loaded device detail: ' + device.id + suffix)
    await screenshot('devices', 'devices')
    console.log('Devices: copy, header selection and batch expand/collapse passed')

    await visit('/emails', 'emails')
    await selectAll('emails')
    await expectCopy(() => page.getByRole('button', { name: '复制选中邮箱', exact: true }).click(), emails.map(row => row.email).join('\n'))
    await batchExpand('emails', '.email-expanded')
    for (const email of emails) for (const suffix of ['/relations', '/asset-history']) assert(requests.includes(`GET /api/emails/${email.id}${suffix}`), 'Batch expansion loaded email details: ' + email.id + suffix)
    const compactHeight = (await rows('emails').first().boundingBox()).height
    await table('emails').getByRole('button', { name: '标准', exact: true }).click()
    const standardHeight = (await rows('emails').first().boundingBox()).height
    assert(standardHeight > compactHeight, `Standard row height ${standardHeight} must exceed compact ${compactHeight}`)
    await page.reload({ waitUntil: 'domcontentloaded' }); await ready('emails')
    assert.equal(await table('emails').getByRole('button', { name: '标准', exact: true }).getAttribute('aria-pressed'), 'true', 'Same-user row density persisted after reload')
    await page.evaluate(() => localStorage.setItem('user', JSON.stringify({ username: 'workspace-other-user', is_super_admin: true })))
    await page.reload({ waitUntil: 'domcontentloaded' }); await ready('emails')
    assert.equal(await table('emails').getByRole('button', { name: '紧凑', exact: true }).getAttribute('aria-pressed'), 'true', 'Another user starts with independent compact density')
    await page.evaluate(user => localStorage.setItem('user', JSON.stringify({ username: user, is_super_admin: true })), username)
    await page.reload({ waitUntil: 'domcontentloaded' }); await ready('emails')
    assert.equal(await table('emails').getByRole('button', { name: '标准', exact: true }).getAttribute('aria-pressed'), 'true', 'Original user retained standard density')
    await table('emails').getByRole('button', { name: '紧凑', exact: true }).click()
    await selectAll('emails')
    await screenshot('emails', 'emails')
    console.log(`Emails: plain addresses, batch expansion and density ${compactHeight}/${standardHeight}px with reload/user isolation passed`)

    await visit('/op-accounts', 'op-accounts')
    await selectAll('op-accounts')
    const copySelected = page.getByRole('button', { name: '复制选中', exact: true })
    await expectCopy(async () => { await copySelected.click(); await page.getByRole('menuitem', { name: '账号列表（每行一个）', exact: true }).click() }, accounts.map(row => row.account).join('\n'))
    const credentialColumns = ['platform', 'account', 'password', 'totp_secret', 'email', 'email_password', 'recovery_email', 'email_login_url', 'phone', 'phone_manage_url']
    await expectCopy(async () => { await copySelected.click(); await page.getByRole('menuitem', { name: '完整登录资料（含列头，可粘贴表格）', exact: true }).click() }, tsv([['平台', '账号', '账号密码', '2FA密钥', '绑定邮箱', '邮箱密码', '辅助邮箱', '邮箱登录地址', '绑定手机', '手机管理链接'], ...accounts.map(row => credentialColumns.map(key => row[key]))]))
    await screenshot('op-accounts', 'accounts')
    for (const width of [1920, 390]) {
      await page.setViewportSize({ width, height: 900 })
      for (const [route, id] of [['/emails', 'emails'], ['/op-accounts', 'op-accounts'], ['/devices', 'devices'], ['/proxy-nodes', 'proxy-nodes']]) {
        await page.goto(url + route, { waitUntil: 'domcontentloaded' })
        if (width === 390 && ['devices', 'op-accounts'].includes(id)) {
          const selector = id === 'devices' ? '.mobile-cards .device-card' : '.op-account-list .ios-card'
          await page.locator(selector).last().waitFor()
          await page.waitForFunction(() => !document.querySelector('.main-content .el-loading-mask'))
          assert.equal(await page.locator(selector).count(), 8, `${id}: mobile fixture cards loaded`)
        } else await ready(id)
        await checkViewportOverflow(`${id} at ${width}px`)
        if (width === 390 && id === 'emails') {
          const emailBox = await rows('emails').first().locator('.email-name').boundingBox()
          const tableBox = await table('emails').locator('.el-table').boundingBox()
          assert(emailBox.x >= tableBox.x && emailBox.x + emailBox.width <= tableBox.x + tableBox.width + 1, 'First email address fits entirely inside the mobile table viewport')
          const unobstructed = await rows('emails').first().locator('.email-name').evaluate(element => {
            const bounds = element.getBoundingClientRect()
            return [.15, .5, .85].every(position => element.contains(document.elementFromPoint(bounds.left + bounds.width * position, bounds.top + bounds.height / 2)))
          })
          assert(unobstructed, 'Mobile action column must not overlay the email address')
          assert.equal(await rows('emails').first().locator('.el-table-fixed-column--right').evaluate(element => getComputedStyle(element).position), 'static', 'Mobile actions scroll with the table instead of covering data')
        }
        if (width === 390 && id === 'op-accounts') {
          const filters = page.locator('details.mobile-filter-details')
          assert.equal(await filters.evaluate(element => element.open), false, 'Mobile filters start collapsed')
          await filters.locator('summary').click()
          assert.equal(await filters.evaluate(element => element.open), true, 'Mobile filters expand on request')
          for (const label of ['绑定终端', '绑定节点']) {
            const filter = filters.locator('.el-select').filter({ has: page.getByText(label, { exact: true }) })
            await filter.waitFor()
            assert(await filter.isVisible(), `${label}: translated mobile filter is visible`)
          }
          await checkViewportOverflow('Expanded account filters at 390px')
          await filters.locator('summary').click()
        }
        if (width === 390 && ['emails', 'op-accounts'].includes(id)) {
          await page.evaluate(() => { document.querySelector('main')?.scrollTo(0, 0); window.scrollTo(0, 0) })
          await page.screenshot({ path: path.join(artifacts, `workspace-${id === 'op-accounts' ? 'accounts' : id}-390.png`), style: '.el-message, .el-popper { visibility: hidden !important; }' })
        }
      }
      console.log(`Responsive smoke: 4 routes at ${width}px have no document/body overflow`)
    }
    assert.deepEqual(errors, [], 'Page render errors')
    assert.deepEqual(unexpected, [], 'Unexpected APIs were contacted')
    console.log(`Workspace efficiency acceptance passed in ${((Date.now() - started) / 1000).toFixed(1)}s; ${requests.length} isolated GETs; 6 screenshots saved`)
  } finally {
    clearTimeout(deadline)
    await browser.close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
