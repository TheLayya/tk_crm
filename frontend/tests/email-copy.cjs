const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))
const { launchUiBrowser } = require('../../desktop/tests/ui-browser.cjs')

async function main() {
  const { browser, close } = await launchUiBrowser(chromium)
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } })
  try {
    const page = await context.newPage()
    page.setDefaultTimeout(12000)
    await page.clock.install()
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
    let totpRequests = 0, totpMode = 'valid', releaseTotp
    await page.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname
      if (!endpoint.startsWith('/api/')) return route.continue()
      if (endpoint === '/api/emails/1/totp') {
        totpRequests += 1
        const response = totpRequests === 1 ? { code: '287082', remaining: 2, valid_for: 2 } : { code: '359152', remaining: 30, valid_for: 30 }
        if (totpMode === 'invalid') return route.fulfill({ status: 422, json: { detail: '2FA 密钥格式无效' } })
        if (totpMode === 'delayed') return new Promise(resolve => {
          releaseTotp = async () => { await route.fulfill({ json: response }); resolve() }
        })
        return route.fulfill({ json: response })
      }
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
    const totp = expanded.locator('.email-totp')
    await totp.getByText('287082', { exact: true }).waitFor()
    assert.equal(totpRequests, 1, 'Expanding must automatically request the code')
    await expectCopy(totp, '复制验证码', '287082')
    const clockBefore = await page.evaluate(() => performance.now())
    await page.clock.fastForward(2000)
    await totp.getByText('359152', { exact: true }).waitFor()
    assert((await page.evaluate(() => performance.now())) >= clockBefore + 2000, 'TOTP test must advance the monotonic clock')
    assert.equal(totpRequests, 2, 'Expiry must automatically refresh the code')
    await expectCopy(totp, '复制验证码', '359152')
    assert(!(await expanded.innerText()).includes(secret), 'Generating and copying a code must not reveal its key')
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
    if (process.env.TKCRM_EMAIL_COPY_ARTIFACT) {
      await page.clock.fastForward(5000)
      fs.mkdirSync(path.dirname(process.env.TKCRM_EMAIL_COPY_ARTIFACT), { recursive: true })
      await page.screenshot({ path: process.env.TKCRM_EMAIL_COPY_ARTIFACT, fullPage: true, style: '.el-message { visibility: hidden !important }' })
    }
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
    const afterCollapse = totpRequests
    await page.clock.fastForward(31000)
    assert.equal(totpRequests, afterCollapse, 'Collapsing must stop TOTP refresh requests')
    const empty = page.locator('.email-copy-actions').last()
    assert.equal(await empty.getByRole('button', { name: '复制密码', exact: true }).count(), 0)
    await page.evaluate(() => {
      window.__clipboardMode = 'available'
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: window.__writeClipboard } })
    })
    await expectCopy(empty, '复制资料', '邮箱：empty@example.invalid\n邮箱密码：\n辅助邮箱：\n2FA 密钥：')
    await page.locator('.email-name').last().click()
    assert.equal(await page.locator('.email-expanded').getByRole('button', { name: /复制/ }).count(), 0)
    assert.equal(await page.locator('.email-totp').count(), 0, 'Empty keys must not create a code or request')
    await page.locator('.email-name').last().click()

    totpMode = 'invalid'
    await page.locator('.email-name').first().click()
    await totp.getByText('2FA 密钥格式无效', { exact: true }).waitFor()
    assert.equal(await totp.locator('code').count(), 0, 'Invalid keys must not display a stale code')
    assert.equal(await totp.getByRole('button', { name: '复制验证码', exact: true }).count(), 0)
    const afterInvalid = totpRequests
    await page.clock.fastForward(31000)
    assert.equal(totpRequests, afterInvalid, 'Invalid keys must wait for an explicit retry')
    totpMode = 'valid'
    await totp.getByRole('button', { name: '重试', exact: true }).click()
    await totp.getByText('359152', { exact: true }).waitFor()
    assert.equal(totpRequests, afterInvalid + 1, 'Retry must issue a new request')

    totpMode = 'delayed'
    const refreshRequest = page.waitForRequest('**/api/emails/1/totp')
    await page.clock.fastForward(31000)
    await refreshRequest
    await totp.getByText('正在获取验证码…', { exact: true }).waitFor()
    assert.equal(await totp.locator('code').count(), 0, 'Expired codes must disappear while refresh is pending')
    assert.equal(await totp.getByRole('button', { name: '复制验证码', exact: true }).count(), 0)
    await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1000))
    await page.clock.fastForward(31000)
    await releaseTotp()
    await totp.getByText('正在更新验证码…', { exact: true }).waitFor()
    assert.equal(await totp.locator('code').count(), 0, 'A late response must not extend an expired code lifetime')
    assert.equal(await totp.getByRole('button', { name: '重试', exact: true }).count(), 0, 'Expired responses must automatically retry')
    totpMode = 'valid'
    await page.clock.fastForward(250)
    await totp.getByText('359152', { exact: true }).waitFor()
    await page.clock.resume()

    totpMode = 'delayed'
    const collapseRequest = page.waitForRequest('**/api/emails/1/totp')
    await page.clock.fastForward(31000)
    await collapseRequest
    await page.locator('.email-name').first().click()
    await expanded.waitFor({ state: 'hidden' })
    const afterDelayedCollapse = totpRequests
    await releaseTotp()
    await page.clock.fastForward(31000)
    assert.equal(totpRequests, afterDelayedCollapse, 'A late response must not restart a collapsed timer')
    assert.equal(await page.locator('.email-totp').count(), 0)

    const unmountRequest = page.waitForRequest('**/api/emails/1/totp')
    await page.locator('.email-name').first().click()
    await unmountRequest
    await page.evaluate(() => document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/403'))
    await page.locator('.forbidden-container').waitFor()
    const afterUnmount = totpRequests
    await releaseTotp()
    await page.clock.fastForward(31000)
    assert.equal(totpRequests, afterUnmount, 'A late response must not restart requests after page unmount')
    assert.deepEqual(errors, [], 'Email runtime errors')
  } finally { await close() }
  console.log('Email copy/TOTP: copies, masks, expiry refresh, invalid-key retry, collapse/unmount, fallback, and widths passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
