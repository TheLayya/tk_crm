const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))

async function main() {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  try {
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('token', 'isolated-email-copy-fixture')
      localStorage.setItem('user', JSON.stringify({ username: 'copy-test' }))
      localStorage.setItem('permissions', JSON.stringify(['email:view']))
      window.__copies = []
      window.__clipboardMode = 'available'
      window.__writeClipboard = async text => {
        if (window.__clipboardMode !== 'available') throw new Error('clipboard denied')
        window.__copies.push({ text, source: 'clipboard' })
      }
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: window.__writeClipboard } })
      document.execCommand = action => {
        if (action !== 'copy' || window.__clipboardMode === 'failure') return false
        window.__copies.push({ text: document.querySelector('textarea[readonly]').value, source: 'fallback' })
        return true
      }
    })
    const email = 'long-mail-address-for-desktop-copy-check@gmail.com'
    const password = 'copy-test-password-<&>'
    const recovery = 'long-recovery-address@example.invalid'
    const secret = 'JBSWY3DPEHPK3PXP'
    await page.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname
      if (!endpoint.startsWith('/api/')) return route.continue()
      const responses = {
        '/api/settings/public': { site_name: '复制验收' },
        '/api/updates/check': { current_version: '1.1.12', has_update: false },
        '/api/updates/history': { items: [] },
        '/api/work-items/summary': {},
        '/api/emails/platforms': [],
        '/api/emails': { total: 2, items: [
          { id: 1, email, password, recovery_email: recovery, totp_secret: secret, management_status: '闲置', current_relation_count: 0 },
          { id: 2, email: 'empty@example.invalid', password: null, recovery_email: null, totp_secret: null, management_status: '闲置', current_relation_count: 0 },
        ] },
        '/api/emails/1/relations': [], '/api/emails/1/asset-history': [],
        '/api/emails/2/relations': [], '/api/emails/2/asset-history': [],
      }
      assert(endpoint in responses, 'Unmocked API: ' + endpoint)
      await route.fulfill({ json: responses[endpoint] })
    })
    await page.goto((process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186') + '/emails')
    const actions = page.locator('.email-copy-actions').first()
    await actions.waitFor()
    async function expectCopy(container, label, expected, source = 'clipboard') {
      const before = await page.evaluate(() => window.__copies.length)
      await container.getByRole('button', { name: label, exact: true }).click()
      await page.waitForFunction(count => window.__copies.length === count + 1, before)
      assert.deepEqual(await page.evaluate(() => window.__copies.at(-1)), { text: expected, source })
    }
    await expectCopy(actions, '复制邮箱', email)
    await expectCopy(actions, '复制密码', password)
    const all = `邮箱：${email}\n邮箱密码：${password}\n辅助邮箱：${recovery}\n2FA 密钥：${secret}`
    await expectCopy(actions, '复制资料', all)
    assert.equal(await page.locator('.email-expanded').count(), 0, 'Copying must not open details')

    await page.locator('.email-name').first().click()
    const expanded = page.locator('.email-expanded')
    await expanded.waitFor()
    assert(!(await expanded.innerText()).includes(password), 'Password must stay masked')
    assert(!(await expanded.innerText()).includes(secret), '2FA secret must stay masked')
    await expectCopy(expanded, '复制密码', password)
    await expectCopy(expanded, '复制辅助邮箱', recovery)
    await expectCopy(expanded, '复制 2FA 密钥', secret)
    const credential = expanded.locator('.credential-field').first()
    await credential.getByRole('button', { name: '显示', exact: true }).click()
    assert.equal(await credential.locator('.credential-value').innerText(), password)
    await credential.getByRole('button', { name: '隐藏', exact: true }).click()
    assert.equal(await credential.locator('.credential-value').innerText(), '••••••')
    for (const width of [1366, 960, 683]) {
      await page.setViewportSize({ width, height: 768 })
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Page overflow at width ' + width)
      for (const button of await actions.getByRole('button').all()) {
        const bounds = await button.boundingBox()
        assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width + 1, 'Copy action outside viewport at width ' + width)
      }
    }
    await page.setViewportSize({ width: 1366, height: 768 })
    await page.evaluate(() => { window.__clipboardMode = 'denied' })
    await expectCopy(actions, '复制密码', password, 'fallback')
    await page.evaluate(() => { Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined }) })
    await expectCopy(actions, '复制邮箱', email, 'fallback')
    assert.equal(await page.locator('textarea[readonly]').count(), 0, 'Fallback must remove temporary secret textarea')
    await page.evaluate(() => { window.__clipboardMode = 'failure' })
    const beforeFailure = await page.evaluate(() => window.__copies.length)
    await actions.getByRole('button', { name: '复制邮箱', exact: true }).click()
    await page.getByText('复制失败，请展开详情后手动复制', { exact: true }).waitFor()
    assert.equal(await page.evaluate(() => window.__copies.length), beforeFailure)
    assert.equal(await page.locator('textarea[readonly]').count(), 0)

    await page.locator('.email-name').first().click()
    const empty = page.locator('.email-copy-actions').last()
    assert.equal(await empty.getByRole('button', { name: '复制密码', exact: true }).count(), 0)
    await page.evaluate(() => {
      window.__clipboardMode = 'available'
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: window.__writeClipboard } })
    })
    await expectCopy(empty, '复制资料', '邮箱：empty@example.invalid\n邮箱密码：\n辅助邮箱：\n2FA 密钥：')
    await page.locator('.email-name').last().click()
    assert.equal(await page.locator('.email-expanded').getByRole('button', { name: /复制/ }).count(), 0)
    assert.deepEqual(errors, [], 'Email runtime errors')
    if (process.env.TKCRM_EMAIL_COPY_ARTIFACT) {
      fs.mkdirSync(path.dirname(process.env.TKCRM_EMAIL_COPY_ARTIFACT), { recursive: true })
      await page.screenshot({ path: process.env.TKCRM_EMAIL_COPY_ARTIFACT, fullPage: true })
    }
  } finally { await context.close(); await browser.close() }
  console.log('Email copy: individual/bundle, masks, empty fields, fallback/failure, and widths passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
