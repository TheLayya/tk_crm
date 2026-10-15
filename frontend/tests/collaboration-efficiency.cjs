// Run against Vite: node frontend/tests/collaboration-efficiency.cjs. All APIs use local fixtures.
const assert = require('node:assert/strict')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
let browser
const deadline = setTimeout(async () => { console.error('Collaboration acceptance exceeded 85 seconds'); await browser?.close().catch(() => {}); process.exit(2) }, 85000)

async function main() {
  browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } })
  const requests = [], unexpected = [], errors = []
  const departments = [{ id: 1, name: '运营中心', parent_id: null, children: [{ id: 2, name: '海外业务', parent_id: 1, children: [{ id: 3, name: '内容组', parent_id: 2, children: [] }] }] }]
  const members = Array.from({ length: 61 }, (_, index) => ({ id: index + 1, username: index === 0 ? 'li.ming' : `member.${index}`, real_name: index === 0 ? '李明' : `团队成员${index}`, department_id: 3, department_name: '内容组', roles: index % 3 ? [{ id: 1, name: '运营成员' }] : [], is_active: index % 5 !== 4 }))
  const memos = [
    { id: 101, category: '采购与续费', title: '本周节点续费核对', content: '核对续费日期与供应商报价。\n完成后在表格登记。', reminder_users: ['li.ming', 'chen.yu'], remind_at: '2026-10-14T10:00:00Z', is_done: false, created_by: 'chen.yu', updated_at: '2026-10-14T09:00:00Z' },
    { id: 102, category: '团队任务', title: '交接本周账号资料', content: '整理待交接账号和关联邮箱，确认负责人。', reminder_users: ['__all__'], remind_at: '2026-10-16T10:00:00Z', is_done: false, created_by: 'li.ming', updated_at: '2026-10-14T10:00:00Z' },
    { id: 103, category: '团队任务', title: '已完成的资料复核', content: '已复核完成，保留交接记录。', reminder_users: ['li.ming'], remind_at: null, is_done: true, created_by: 'chen.yu', updated_at: '2026-10-13T10:00:00Z' },
  ]
  let dueItems = []
  let releaseOldMember, oldMemberSeen
  const oldMemberArrived = new Promise(resolve => { oldMemberSeen = resolve })
  const oldMemberGate = new Promise(resolve => { releaseOldMember = resolve })
  await context.addInitScript(() => {
    localStorage.setItem('token', 'collaboration-isolated')
    localStorage.setItem('user', JSON.stringify({ username: 'li.ming', real_name: '李明', is_super_admin: true }))
    localStorage.setItem('permissions', JSON.stringify(['*']))
    window.__copies = []
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => window.__copies.push(text) } })
  })
  await context.route('**/api/**', async route => {
    const request = route.request(), requestUrl = new URL(request.url()), endpoint = requestUrl.pathname
    if (!endpoint.startsWith('/api/')) return route.continue()
    requests.push({ url: requestUrl, method: request.method() })
    const fail = () => { unexpected.push(`${request.method()} ${endpoint}`); return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API' } }) }
    if (request.method() !== 'GET') return fail()
    if (endpoint === '/api/team/member') {
      const params = requestUrl.searchParams
      if (['old', 'new'].includes(params.get('username'))) {
        const keyword = params.get('username')
        if (keyword === 'old') { oldMemberSeen(); await oldMemberGate }
        return route.fulfill({ json: { items: [{ ...members[0], id: keyword === 'old' ? 990 : 991, username: `${keyword}.result`, real_name: keyword === 'old' ? '较早搜索结果' : '最新搜索结果' }], total: 1 } })
      }
      let found = members.filter(member => !params.get('username') || member.username.includes(params.get('username')))
      if (params.has('is_active')) found = found.filter(member => String(member.is_active) === params.get('is_active'))
      const page = Number(params.get('page') || 1), size = Number(params.get('size') || 20)
      return route.fulfill({ json: { items: found.slice((page - 1) * size, page * size), total: found.length } })
    }
    if (endpoint === '/api/work-items') {
      const params = requestUrl.searchParams
      let found = memos.filter(memo => params.get('status') === 'all' || memo.is_done === (params.get('status') === 'done'))
      if (params.get('keyword')) found = found.filter(memo => `${memo.title}${memo.content}`.includes(params.get('keyword')))
      if (params.get('category')) found = found.filter(memo => memo.category === params.get('category'))
      return route.fulfill({ json: { items: found, total: found.length } })
    }
    const responses = {
      '/api/settings/public': { site_name: '团队运营工作台' },
      '/api/updates/check': { current_version: '1.1.19', has_update: false },
      '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] },
      '/api/team/dept/tree': departments,
      '/api/team/role': [{ id: 1, name: '运营成员', description: '查看并维护本人负责的资料', data_scope: 'self', permissions: [] }],
      '/api/work-items/categories': ['采购与续费', '团队任务', '其他'],
      '/api/work-items/members': [{ username: 'li.ming', real_name: '李明' }, { username: 'chen.yu', real_name: '陈雨' }],
      '/api/work-items/summary': { overdue: 1, due_soon: 1, pending: 2, due: dueItems },
    }
    return Object.hasOwn(responses, endpoint) ? route.fulfill({ json: responses[endpoint] }) : fail()
  })
  const page = await context.newPage()
  page.setDefaultTimeout(7000)
  page.on('pageerror', error => errors.push(error.message))
  const table = id => page.locator(`.crm-table-wrapper[data-table-id="${id}"]`)
  const memberRequests = () => requests.filter(request => request.url.pathname === '/api/team/member')
  const latestMember = () => memberRequests().at(-1).url.searchParams
  const visit = async route => { await page.goto(url + route, { waitUntil: 'domcontentloaded' }); await page.locator('.main-content').waitFor() }
  const waitApi = endpoint => page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.status() === 200)
  const noBodyOverflow = async label => {
    const widths = await page.evaluate(() => ({ body: document.body.scrollWidth, document: document.documentElement.scrollWidth, viewport: innerWidth }))
    assert(widths.body <= widths.viewport + 1 && widths.document <= widths.viewport + 1, `${label} body overflow: ${JSON.stringify(widths)}`)
  }
  try {
    await visit('/team/manage')
    await table('team-members').getByText('未分配角色', { exact: true }).first().waitFor()
    assert.equal(await page.locator('.pagination .el-pagination__total').innerText(), '共 61 条')
    let response = waitApi('/api/team/member'); await page.locator('.pagination .el-pager li').filter({ hasText: /^2$/ }).click(); await response
    assert.equal(latestMember().get('page'), '2')
    await page.locator('.search-form .el-form-item').filter({ has: page.getByRole('combobox', { name: '筛选部门', exact: true }) }).locator('.el-select__wrapper').click()
    await page.getByRole('option', { name: '运营中心 / 海外业务 / 内容组', exact: true }).waitFor()
    response = waitApi('/api/team/member'); await page.getByRole('option', { name: '运营中心 / 海外业务 / 内容组', exact: true }).click(); await response
    assert.equal(latestMember().get('dept_id'), '3'); assert.equal(latestMember().get('page'), '1'); assert.equal(Number(latestMember().get('skip') || 0), 0)
    const username = page.getByRole('textbox', { name: '搜索用户名', exact: true })
    await username.fill('li.ming'); response = waitApi('/api/team/member'); await username.press('Enter'); await response
    assert.equal(latestMember().get('username'), 'li.ming')
    await username.hover(); response = waitApi('/api/team/member'); await username.locator('..').locator('.el-input__clear').click(); await response
    assert.equal(latestMember().get('username'), null)
    await table('team-members').locator('.crm-table-active-filters').getByText('部门：运营中心 / 海外业务 / 内容组', { exact: true }).waitFor()
    const beforeReset = memberRequests().length
    response = waitApi('/api/team/member'); await table('team-members').getByRole('button', { name: '重置查询', exact: true }).click(); await response; await page.waitForTimeout(150)
    assert.equal(memberRequests().length - beforeReset, 1, 'Reset must issue exactly one member request')
    assert.equal(latestMember().get('dept_id'), null); assert.equal(latestMember().get('page'), '1')
    await page.waitForFunction(() => !document.querySelector('[data-table-id="team-members"] .crm-table-active-filters .el-tag'))
    assert.equal(await table('team-members').locator('.crm-table-active-filters .el-tag').count(), 0, await table('team-members').locator('.crm-table-active-filters').innerText())
    await page.locator('.main-content').evaluate(element => { element.scrollTop = 0 })
    await page.screenshot({ path: '.orchestration/workspace-team-1366.png', fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })
    const oldResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/team/member' && new URL(response.url()).searchParams.get('username') === 'old')
    await username.fill('old'); await username.press('Enter'); await oldMemberArrived
    response = waitApi('/api/team/member'); await username.fill('new'); await username.press('Enter'); await response
    await table('team-members').getByText('new.result', { exact: true }).waitFor()
    releaseOldMember(); await (await oldResponse).finished()
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    assert.equal(await table('team-members').getByText('old.result', { exact: true }).count(), 0, 'A late old response must not replace newer member results')
    assert.equal(await table('team-members').getByText('new.result', { exact: true }).count(), 1)
    console.log('Delayed old member search preserves the latest result')
    await page.getByRole('button', { name: '部门管理', exact: true }).click()
    const deptButton = page.getByRole('button', { name: '编辑部门：内容组', exact: true })
    await deptButton.locator('..').locator('..').hover(); await deptButton.click()
    const deptDialog = page.getByRole('dialog', { name: '编辑部门', exact: true })
    assert.equal(await deptDialog.locator('.el-form-item').filter({ hasText: '上级部门' }).locator('input').inputValue(), '运营中心 / 海外业务')
    await deptDialog.getByRole('button', { name: '取消', exact: true }).click()
    console.log('Member filters, hierarchy, one-request reset and department parent passed')

    await visit('/work-items')
    await table('work-items').getByText('李明（li.ming）、陈雨（chen.yu）', { exact: true }).waitFor()
    await table('work-items').getByRole('button', { name: '复制备忘：本周节点续费核对', exact: true }).click()
    assert((await page.evaluate(() => window.__copies[0])).includes('提醒成员：李明（li.ming）、陈雨（chen.yu）'))
    const memoRows = table('work-items').locator('.el-table__body-wrapper tr.el-table__row')
    await memoRows.nth(0).locator('.el-checkbox').click(); await memoRows.nth(1).locator('.el-checkbox').click()
    await page.getByRole('button', { name: '复制选中备忘', exact: true }).click()
    const copied = await page.evaluate(() => window.__copies.at(-1))
    for (const expected of ['标题：本周节点续费核对', '标题：交接本周账号资料', '正文：', '──────────']) assert(copied.includes(expected), `Missing copied memo content: ${expected}`)
    await page.waitForFunction(() => document.querySelectorAll('[data-table-id="work-items"] .el-table__body-wrapper .el-checkbox.is-checked').length === 2)
    await table('work-items').locator('.el-scrollbar__wrap').evaluateAll(elements => elements.forEach(element => { element.scrollLeft = 0 }))
    await page.screenshot({ path: '.orchestration/workspace-memos-1366.png', fullPage: true, style: '.el-message,.el-popper { visibility:hidden !important; }' })

    dueItems = [{ id: 101, title: memos[0].title }]
    await visit('/team/manage')
    await page.locator('.el-notification').filter({ hasText: memos[0].title }).click()
    await page.waitForURL(value => value.pathname === '/work-items' && value.searchParams.get('item_id') === '101' && value.searchParams.get('mine') === 'true')
    await table('work-items').locator('.work-item-focused').filter({ hasText: memos[0].title }).waitFor()
    await table('work-items').locator('.item-content').filter({ hasText: '创建人：陈雨（chen.yu）' }).waitFor()
    assert.equal(new URL(page.url()).searchParams.get('mine'), 'true')
    dueItems = [{ id: 102, title: memos[1].title }]
    await visit('/work-items')
    await page.locator('.el-notification').filter({ hasText: memos[1].title }).waitFor()
    await page.getByPlaceholder('搜索标题或内容').fill('不存在的旧筛选')
    response = waitApi('/api/work-items'); await page.getByPlaceholder('搜索标题或内容').press('Enter'); await response
    await page.locator('.el-notification').filter({ hasText: memos[1].title }).click()
    await page.waitForURL(value => value.pathname === '/work-items' && value.searchParams.get('item_id') === '102' && value.searchParams.get('mine') === 'true')
    await table('work-items').locator('.work-item-focused').filter({ hasText: memos[1].title }).waitFor()
    await table('work-items').locator('.item-content').filter({ hasText: memos[1].content }).waitFor()
    assert.equal(await page.getByPlaceholder('搜索标题或内容').inputValue(), '', 'Reminder navigation clears stale filters on the same page')
    dueItems = []
    await visit('/work-items?item_id=103&mine=true')
    await table('work-items').locator('.work-item-focused').filter({ hasText: memos[2].title }).waitFor()
    await page.locator('.focus-notice').filter({ hasText: '已切换为全部备忘并定位' }).waitFor()
    assert(requests.some(request => request.url.pathname === '/api/work-items' && request.url.searchParams.get('status') === 'all' && request.url.searchParams.get('mine') === 'false'))
    await visit('/team/manage'); await page.getByRole('button', { name: '备忘提醒', exact: true }).click(); await page.waitForURL(value => value.pathname === '/work-items' && value.searchParams.get('mine') === 'true')
    const reminderVisit = new URL(page.url()).searchParams.get('reminder')
    await page.getByRole('group', { name: '备忘快捷筛选', exact: true }).getByRole('button', { name: '已完成', exact: true }).click()
    await table('work-items').getByText(memos[2].title, { exact: true }).waitFor()
    await page.getByRole('button', { name: '备忘提醒', exact: true }).click()
    await page.waitForURL(value => value.searchParams.get('reminder') !== reminderVisit)
    await page.waitForFunction(() => document.querySelector('.quick-filters .el-button')?.getAttribute('aria-pressed') === 'true')
    await table('work-items').getByText(memos[0].title, { exact: true }).waitFor()
    assert.equal(await table('work-items').getByText(memos[2].title, { exact: true }).count(), 0, 'Repeated bell navigation resets local completed view')
    console.log('Memo names, single/bulk copy, cross-page and same-page reminders passed')

    for (const width of [1366, 1920, 390]) {
      await page.setViewportSize({ width, height: 900 })
      for (const route of ['/team/manage', '/work-items']) { await visit(route); await page.waitForTimeout(80); await noBodyOverflow(`${route} at ${width}px`) }
    }
    assert.deepEqual(errors, [], 'Browser rendering errors')
    assert.deepEqual(unexpected, [], 'Only allowlisted GET APIs may be contacted')
    console.log('Collaboration efficiency browser acceptance passed (1366 / 1920 / 390px)')
  } finally {
    releaseOldMember()
    if (errors.length || unexpected.length) console.error({ errors, unexpected })
    const closing = browser.close(); await Promise.race([closing, new Promise(resolve => setTimeout(resolve, 2000))]); clearTimeout(deadline)
  }
}

main().then(() => process.exit(0)).catch(error => { console.error(error); clearTimeout(deadline); process.exit(1) })
