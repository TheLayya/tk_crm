// Run against Vite/preview: node frontend/tests/failure-reports.cjs. Every API uses fixtures.
const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')
const { spawnSync } = require('node:child_process')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==', 'base64')
const artifactDir = path.resolve('.orchestration/failure-reports-20261016/images')

async function main() {
  const browserProcess = await spawnBrowser()
  const { browser, close } = browserProcess
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })
  const state = { reports: [], submissions: [], images: [], unexpected: [], errors: [], conflict: false, defer: false, release: null, pendingEmail: true, keyInvalid: false }
  await context.addInitScript(() => {
    localStorage.setItem('token', 'failure-report-test-token')
    localStorage.setItem('user', JSON.stringify({ username: 'report.member' }))
    localStorage.setItem('permissions', JSON.stringify(['card_key:view', 'card_key:manage', 'email:view']))
    window.__revoked = []
    const revoke = URL.revokeObjectURL.bind(URL)
    URL.revokeObjectURL = value => { window.__revoked.push(value); revoke(value) }
  })
  const metadata = kind => state.reports.filter(report => report.kind === kind).map((report, index) => ({ id: index + 1, kind, username: 'report.member', remark: report.remark, created_at: '2026-10-16T01:00:00Z', project_name: '售后验收项目', platform: 'TikTok', image_count: report.screenshots.length, images: report.screenshots.map((image, imageIndex) => ({ name: image.name, content_type: image.content_type, size: png.length, width: 1, height: 1, url: `${kind === 'email' ? '/emails/7' : '/card-keys/1/keys/9'}/failure-reports/${index + 1}/screenshots/${imageIndex}` })) }))
  const key = () => ({ id: 9, content: 'TEAM-FAILURE-CARD', status: state.keyInvalid ? 'invalid' : 'available', batch_name: '供应商 A', batch_id: 10, batch_status: 'active', history: state.keyInvalid ? [{ action: 'invalid', username: 'report.member', remark: '截图售后', time: '2026-10-16T01:00:00Z' }] : [], failure_report_count: metadata('card_key').length, screenshot_count: state.reports.filter(report => report.kind === 'card_key').reduce((sum, report) => sum + report.screenshots.length, 0) })
  const email = () => ({ id: 7, email: 'failure@example.invalid', management_status: '废弃', platform_tags: [], current_relation_count: 0, failure_report_count: metadata('email').length, screenshot_count: state.reports.filter(report => report.kind === 'email').reduce((sum, report) => sum + report.screenshots.length, 0), latest_failure_remark: '注册错误，等待上游处理' })
  await context.route('**/api/**', async route => {
    const request = route.request(), endpoint = new URL(request.url()).pathname
    if (!endpoint.startsWith('/api/')) return route.continue()
    const reply = json => route.fulfill({ json })
    if (endpoint.endsWith('/failure-reports') && request.method() === 'GET') return reply(metadata(endpoint.startsWith('/api/emails/') ? 'email' : 'card_key'))
    if (endpoint.includes('/screenshots/')) {
      state.images.push({ endpoint, authorization: request.headers().authorization })
      return route.fulfill({ contentType: 'image/png', body: png })
    }
    if (request.method() === 'POST' && (endpoint.endsWith('/invalid') || endpoint.endsWith('/email/fail'))) {
      const body = request.postDataJSON(), kind = endpoint.endsWith('/invalid') ? 'card_key' : 'email'
      state.submissions.push({ endpoint, body })
      const respond = async () => {
        if (state.conflict) return route.fulfill({ status: 409, json: { detail: '资源状态已变化，请核实后重试' } })
        state.reports.push({ ...body, kind })
        if (kind === 'card_key') state.keyInvalid = true
        else state.pendingEmail = false
        return reply({ success: true })
      }
      if (state.defer) return new Promise(resolve => { state.release = async () => { await respond(); resolve() } })
      return respond()
    }
    if (endpoint === '/api/card-keys/1/keys') return reply({ items: new URL(request.url()).searchParams.get('mine') === 'true' ? [] : [key()], total: 1 })
    if (endpoint === '/api/card-keys/1/email') return reply(state.pendingEmail ? { id: 7, email: 'failure@example.invalid' } : null)
    if (endpoint === '/api/emails') return reply({ items: [email()], total: 1 })
    const responses = {
      '/api/settings/public': { site_name: '失败截图验收' }, '/api/updates/check': { current_version: '1.1.23', has_update: false }, '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] }, '/api/work-items/summary': {},
      '/api/card-keys': [{ id: 1, name: '售后验收项目', members: ['__all__'], is_active: true, available: 1, claimed: 0, consumed: 0, can_claim: true, target_platform: 'TikTok', member_stats: [] }], '/api/card-keys/platforms': [], '/api/card-keys/members': [], '/api/card-keys/1/batches': [{ id: 10, name: '供应商 A', status: 'active', available: 1, total: 1 }], '/api/emails/platforms': [],
    }
    if (request.method() === 'GET' && Object.hasOwn(responses, endpoint)) return reply(responses[endpoint])
    state.unexpected.push(`${request.method()} ${endpoint}`)
    return route.fulfill({ status: 500, json: { detail: 'Unexpected fixture API' } })
  })
  const page = await context.newPage()
  page.setDefaultTimeout(60000)
  page.on('pageerror', error => state.errors.push(error.message))
  const dialog = () => page.getByRole('dialog', { name: '报告卡密无效', exact: true })
  const upload = (target, files) => target.getByLabel('上传失败截图', { exact: true }).setInputFiles(files)
  const paste = async target => target.getByRole('group', { name: '粘贴失败截图', exact: true }).evaluate((element, data) => {
    const transfer = new DataTransfer()
    transfer.items.add(new File([Uint8Array.from(atob(data), character => character.charCodeAt(0))], 'clipboard.png', { type: 'image/png' }))
    element.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }))
  }, png.toString('base64'))
  try {
    await page.goto(url + '/card-keys', { waitUntil: 'domcontentloaded' })
    console.log('Failure fixture: card-key page loaded')
    await page.getByRole('button', { name: '标记无效', exact: true }).click()
    let report = dialog()
    await report.getByRole('button', { name: '保存失败记录', exact: true }).click()
    await report.getByText('请至少添加一张失败截图', { exact: true }).waitFor()
    assert.equal(state.submissions.length, 0)
    await report.getByLabel('失败说明', { exact: true }).fill('仅文字不应提交')
    await report.getByRole('button', { name: '保存失败记录', exact: true }).click()
    await report.getByText('请至少添加一张失败截图', { exact: true }).waitFor()
    assert.equal(state.submissions.length, 0, 'A screenshot is required even with a description')
    await paste(report)
    await report.locator('.failure-previews img').waitFor()
    await upload(report, [{ name: 'upload.png', mimeType: 'image/png', buffer: png }])
    await page.waitForFunction(() => document.querySelectorAll('.failure-previews img').length === 2)
    await report.getByRole('button', { name: '移除截图 1', exact: true }).click()
    assert.equal(await report.locator('.failure-previews img').count(), 1)
    await upload(report, [{ name: 'too-large.png', mimeType: 'image/png', buffer: Buffer.alloc(3 * 1024 * 1024 + 1) }])
    await report.getByText('单张截图最多 3 MiB，请缩小图片后重新添加', { exact: true }).waitFor()
    await upload(report, [{ name: 'wrong.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg />') }])
    await report.getByText('请选择 PNG、JPEG 或 WebP 图片', { exact: true }).waitFor()
    await report.getByLabel('失败说明', { exact: true }).fill('兑换报错，联系上游售后')
    state.conflict = true
    await report.getByRole('button', { name: '保存失败记录', exact: true }).click()
    await report.getByText('资源状态已变化，请核实后重试', { exact: true }).waitFor()
    assert.equal(await report.getByLabel('失败说明', { exact: true }).inputValue(), '兑换报错，联系上游售后')
    assert.equal(await report.locator('.failure-previews img').count(), 1, 'Conflict preserves images')
    fs.mkdirSync(artifactDir, { recursive: true })
    await page.screenshot({ path: path.join(artifactDir, 'failure-dialog-1366.png'), fullPage: true })
    state.conflict = false; state.defer = true
    const pendingSubmission = page.waitForRequest('**/api/card-keys/1/keys/9/invalid')
    await report.getByRole('button', { name: '保存失败记录', exact: true }).click()
    await pendingSubmission
    assert(await report.getByRole('button', { name: '取消', exact: true }).isDisabled())
    await page.keyboard.press('Escape')
    assert(await report.isVisible())
    await state.release(); state.defer = false
    await report.waitFor({ state: 'hidden' })
    const sent = state.submissions.at(-1)
    assert.equal(sent.endpoint, '/api/card-keys/1/keys/9/invalid')
    assert.deepEqual(sent.body.screenshots, [{ name: 'upload.png', content_type: 'image/png', data: png.toString('base64') }])
    assert(!sent.body.screenshots[0].data.startsWith('data:'))
    await page.locator('.failure-report-badge').getByText('失败 1 · 截图 1', { exact: true }).click()
    let history = page.getByRole('dialog', { name: '失败记录与售后凭证', exact: true })
    await history.getByText('兑换报错，联系上游售后', { exact: true }).waitFor()
    assert.equal(state.images.length, 0, 'History opens metadata without images')
    await history.getByRole('button', { name: '查看截图 1', exact: true }).click()
    await history.locator('.history-image img').waitFor()
    await page.waitForFunction(() => { const img = document.querySelector('.history-image img'); return img?.complete && img.naturalWidth > 0 })
    assert.equal(state.images.at(-1).authorization, 'Bearer failure-report-test-token')
    assert((await history.locator('.history-image img').getAttribute('src')).startsWith('blob:'))
    await page.screenshot({ path: path.join(artifactDir, 'card-failure-history-1366.png'), fullPage: true })
    await history.getByRole('button', { name: '关闭', exact: true }).click()

    await page.getByRole('button', { name: '注册失败', exact: true }).click()
    report = page.getByRole('dialog', { name: '报告邮箱注册失败', exact: true })
    await paste(report)
    await report.locator('.failure-previews img').waitFor()
    await report.getByRole('button', { name: '保存失败记录', exact: true }).click()
    await report.waitFor({ state: 'hidden' })
    const emailSent = state.submissions.at(-1)
    assert.equal(emailSent.endpoint, '/api/card-keys/1/email/fail')
    assert.equal(emailSent.body.expected_email_id, 7)
    assert.equal(emailSent.body.remark, '', 'Image-only report is accepted')
    await page.goto(url + '/emails', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '查看邮箱失败凭证：failure@example.invalid', exact: true }).waitFor()
    await page.screenshot({ path: path.join(artifactDir, 'email-failure-badge-1366.png'), fullPage: true })
    await page.getByRole('button', { name: '查看邮箱失败凭证：failure@example.invalid', exact: true }).click()
    history = page.getByRole('dialog', { name: '失败记录与售后凭证', exact: true })
    await history.getByRole('button', { name: '查看截图 1', exact: true }).waitFor()
    await history.getByRole('button', { name: '查看截图 1', exact: true }).click()
    await history.locator('.history-image img').waitFor()
    await page.waitForFunction(() => { const img = document.querySelector('.history-image img'); return img?.complete && img.naturalWidth > 0 })
    assert.equal(state.images.at(-1).endpoint, '/api/emails/7/failure-reports/1/screenshots/0')
    assert.equal(state.images.at(-1).authorization, 'Bearer failure-report-test-token')
    await page.setViewportSize({ width: 390, height: 844 })
    const box = await history.boundingBox()
    assert(box.x >= 0 && box.x + box.width <= 391, 'History fits a phone viewport')
    await page.screenshot({ path: path.join(artifactDir, 'email-failure-history-390.png'), fullPage: true })
    assert.deepEqual(state.errors, [])
    assert.deepEqual(state.unexpected, [])
    console.log('Failure reports passed: required screenshot, clipboard paste, uploads, limits, remove, conflict retention, pending lock, exact base64 payload, image-only email report, target ID, metadata and authenticated blob screenshots, decoded image dimensions, email badge and phone layout')
  } catch (error) { console.error('Failure report acceptance:', error); throw error }
  finally { await context.close(); await close() }
}

async function spawnBrowser() {
  // A direct system Chrome connection avoids the local headless-shell websocket shutdown issue.
  const childProcess = require('node:child_process')
  const originalSpawn = childProcess.spawn
  let owned
  childProcess.spawn = function (command, args) {
    const child = originalSpawn.apply(this, arguments)
    if (/chrome\.exe$/i.test(String(command)) && args?.some(arg => String(arg).startsWith('--user-data-dir=')) && !args.some(arg => String(arg).startsWith('--type='))) owned = child
    return child
  }
  let browser
  try { browser = await chromium.launch({ headless: true, channel: 'chrome' }) }
  finally { childProcess.spawn = originalSpawn }
  return { browser, close: async () => {
    let timer
    try {
      await Promise.race([browser.close().catch(() => {}), new Promise(resolve => { timer = setTimeout(resolve, 2000) })])
      if (owned?.exitCode === null && owned.signalCode === null) {
        assert(Number.isInteger(owned.pid) && owned.pid > 0)
        const result = spawnSync('taskkill.exe', ['/PID', String(owned.pid), '/T', '/F'], { windowsHide: true, timeout: 15000 })
        assert([0, 128].includes(result.status), 'Owned test Chrome cleanup failed: ' + String(result.stderr))
      }
      for (const pipe of owned?.stdio || []) pipe?.destroy?.()
      owned?.unref()
      console.log('Failure report test owned browser shutdown verified')
      setTimeout(() => process.exit(process.exitCode || 0), 50).unref()
    } finally { clearTimeout(timer) }
  } }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
