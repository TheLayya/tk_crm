// Run against Vite: node frontend/tests/email-import.cjs. All API traffic is mocked.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')

const url = process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186'
const mixed = [
  'three@example.invalid----  synthetic password  ----JBSWY3DPEHPK3PXP',
  'four@example.invalid|synthetic-password|helper@example.invalid|FIXTURE_KEY',
  'country@example.invalid,synthetic-password,helper@example.invalid,US',
  'five@example.invalid，synthetic-password，helper@example.invalid，FIXTURE_KEY，美国',
  'six@example.invalid\tsynthetic-password\thelper@example.invalid\tFIXTURE_KEY\t2021\tBR',
  'three@example.invalid----  synthetic password  ----JBSWY3DPEHPK3PXP----',
].join('\n')

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  try {
    const context = await browser.newContext({ viewport: { width: 1366, height: 1000 } })
    const page = await context.newPage()
    page.setDefaultTimeout(12000)
    await page.addInitScript(() => {
      localStorage.setItem('token', 'isolated-email-import-fixture')
      localStorage.setItem('user', JSON.stringify({ username: 'import-test' }))
      localStorage.setItem('permissions', JSON.stringify(['email:view', 'email:import']))
    })
    const errors = [], unexpected = [], attempts = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/**', async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname
      if (!endpoint.startsWith('/api/')) return route.continue()
      if (endpoint === '/api/emails/import') {
        assert.equal(request.method(), 'POST')
        const body = request.postDataJSON()
        attempts.push(body)
        const total = body.text.split('\n').length
        return route.fulfill({ json: { total, success: total - 1, duplicates: 1, failed: 0, rows: [
          { line: 1, email: 'three@example.invalid', _result: 'success', _id: 1 },
          { line: total, email: 'three@example.invalid', _result: 'duplicate' },
        ] } })
      }
      const responses = {
        '/api/settings/public': { site_name: '混合格式导入验收' },
        '/api/updates/check': { current_version: '1.1.19', has_update: false },
        '/api/updates/status': { status: 'idle' }, '/api/updates/history': { items: [] },
        '/api/work-items/summary': {}, '/api/emails/platforms': [], '/api/emails': { items: [], total: 0 },
      }
      if (!(endpoint in responses)) {
        unexpected.push(endpoint)
        return route.fulfill({ status: 500, json: { detail: 'Unexpected isolated API ' + endpoint } })
      }
      return route.fulfill({ json: responses[endpoint] })
    })
    await page.goto(url + '/emails')
    await page.getByRole('button', { name: '批量导入', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '批量导入邮箱', exact: true })
    const item = label => dialog.locator('.el-form-item').filter({ has: page.getByText(label, { exact: true }) })
    const select = async (label, choice) => {
      await item(label).locator('.el-select').click()
      await page.getByRole('option', { name: choice, exact: true }).click()
    }
    assert((await item('字段格式').innerText()).includes('逐行识别混合格式'))
    await item('字段格式').locator('.el-select').click()
    for (const choice of ['逐行识别混合格式', '四项：邮箱/密码/辅助邮箱或2FA/国家', '五项：邮箱/密码/辅助邮箱或2FA/2FA/国家']) {
      await page.getByRole('option', { name: choice, exact: true }).waitFor({ state: 'visible' })
    }
    await page.keyboard.press('Escape')
    await item('分隔符').locator('.el-select').click()
    for (const choice of ['英文逗号 ,', '中文逗号 ，', '制表符 Tab']) {
      await page.getByRole('option', { name: choice, exact: true }).waitFor({ state: 'visible' })
    }
    await page.keyboard.press('Escape')
    const help = await dialog.locator('.import-tip').innerText()
    for (const text of ['第三项可为辅助邮箱或 2FA', '连续 ---- 中的空字段会保留', '密码按原文保存', '重复邮箱自动跳过']) assert(help.includes(text))
    await item('采购渠道').locator('input').fill('  synthetic supplier  ')
    await item('采购成本（每个）').locator('input').fill('1.25')
    await item('采购成本（每个）').locator('input').press('Tab')
    const submit = async (text, import_format, delimiter) => {
      await dialog.locator('textarea').fill(text)
      const expectedCount = attempts.length + 1
      await Promise.all([
        page.waitForResponse(response => new URL(response.url()).pathname === '/api/emails/import'),
        dialog.getByRole('button', { name: '导入', exact: true }).click(),
      ])
      await page.waitForFunction(count => document.querySelector('.import-result')?.textContent.includes(`成功 ${count - 1}`), text.split('\n').length)
      assert.equal(attempts.length, expectedCount)
      assert.deepEqual(attempts.at(-1), { text, purchase_channel: 'synthetic supplier', purchase_price: 1.25, import_format, delimiter })
      assert.match(await dialog.locator('.import-result').first().innerText(), /重复 1 · 失败 0/)
    }
    await submit(mixed, 'auto', 'auto')
    await select('字段格式', '四项：邮箱/密码/辅助邮箱或2FA/国家')
    await select('分隔符', '英文逗号 ,')
    await submit('country@example.invalid," pass,word ",helper@example.invalid,US\ncountry@example.invalid," pass,word ",helper@example.invalid,US', 'country_4', ',')
    await select('字段格式', '五项：邮箱/密码/辅助邮箱或2FA/2FA/国家')
    await select('分隔符', '中文逗号 ，')
    await submit('five@example.invalid，synthetic-password，helper@example.invalid，FIXTURE_KEY，美国\nfive@example.invalid，synthetic-password，helper@example.invalid，FIXTURE_KEY，美国', 'country_5', '，')
    await select('分隔符', '制表符 Tab')
    await submit('five@example.invalid\t synthetic password \t\tFIXTURE_KEY\tBR\nfive@example.invalid\t synthetic password \t\tFIXTURE_KEY\tBR', 'country_5', '\t')
    assert.deepEqual(errors, [], 'Email import runtime errors')
    assert.deepEqual(unexpected, [], 'Unexpected APIs')
    if (process.env.TKCRM_EMAIL_IMPORT_ARTIFACT) {
      fs.mkdirSync(path.dirname(process.env.TKCRM_EMAIL_IMPORT_ARTIFACT), { recursive: true })
      await page.screenshot({ path: process.env.TKCRM_EMAIL_IMPORT_ARTIFACT, fullPage: true, style: '.el-message { visibility: hidden !important }' })
    }
    await context.close()
  } finally { await close() }
  console.log('Email import: mixed raw text, country formats, comma/Chinese comma/Tab values, unchanged passwords, and success/duplicate results passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
