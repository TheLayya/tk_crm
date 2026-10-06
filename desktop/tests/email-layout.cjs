const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))

async function main() {
  const browser = await chromium.launch({ headless: true })
  try {
    for (const deviceScaleFactor of [1, 1.25, 1.5, 2]) {
      const context = await browser.newContext({ deviceScaleFactor })
      const page = await context.newPage()
      const errors = []
      const artifactDir = process.env.TKCRM_UI_ARTIFACT_DIR
      if (artifactDir) fs.mkdirSync(artifactDir, { recursive: true })
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(() => {
        localStorage.setItem('token', 'isolated-layout-fixture')
        localStorage.setItem('user', JSON.stringify({ username: 'layout-test', is_super_admin: true }))
        localStorage.setItem('permissions', JSON.stringify(['*']))
      })
      await page.route('**/api/**', async route => {
        const requestUrl = new URL(route.request().url())
        const endpoint = requestUrl.pathname
        const responses = {
          '/api/settings/public': { site_name: '布局验收' },
          '/api/updates/check': { current_version: '1.1.16', has_update: false },
          '/api/updates/status': { status: 'idle' },
          '/api/updates/history': { items: [] },
          '/api/work-items/summary': {},
          '/api/team/member': { items: [{ username: 'layout-test' }], total: 1 },
          '/api/emails/platforms': [{ id: 1, name: 'long-platform-name-for-registration', is_active: true }],
          '/api/emails': { total: 1000, items: [{ id: 1, email: (requestUrl.searchParams.get('skip') === '50' ? 'page-two-' : '') + 'long-mail-address-for-desktop-layout-check@gmail.com', recovery_email: 'long-recovery-address@example.invalid', management_status: '闲置', platform_tags: ['long-platform-name-for-registration'], platform_registrants: { 'long-platform-name-for-registration': 'long-member-name-for-attribution' }, current_relation_count: 0, gmail_check_status: '正常', remark: 'long remark '.repeat(25) }] },
          '/api/emails/1/relations': [{ id: 1, platform: 'tiktok', account: 'long-account-without-spaces-'.repeat(10), operator: 'long-registration-member', bound_at: '2026-10-05T01:00:00Z' }],
          '/api/emails/1/asset-history': [{ id: 1, kind: '终端', name: 'long-device-name-'.repeat(8), operator: 'layout-test', bound_at: '2026-10-05T01:00:00Z' }],
        }
        assert(endpoint in responses, 'Unmocked API: ' + endpoint)
        await route.fulfill({ json: responses[endpoint] })
      })
      await page.goto((process.env.TKCRM_UI_URL || 'http://127.0.0.1:8080') + '/emails')
      await page.locator('.email-name').waitFor()
      for (const [width, height] of [[1366, 768], [1180, 674], [960, 540], [683, 384]]) {
        await page.setViewportSize({ width, height })
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
        const metrics = await page.evaluate(() => {
          const main = document.querySelector('.main-content')
          return { page: document.documentElement.scrollWidth, main: main.clientWidth, scroll: main.scrollWidth }
        })
        assert(metrics.page <= width + 1 && metrics.scroll <= metrics.main + 1, 'Email page overflow: ' + JSON.stringify({ width, metrics }))
        for (const control of await page.locator('.heading-actions button, .pager button').all()) {
          await control.scrollIntoViewIfNeeded()
          const bounds = await control.boundingBox()
          assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width + 1 && bounds.y >= 0 && bounds.y + bounds.height <= height + 1, 'Email control outside viewport')
        }
        const nextResponse = page.waitForResponse(response => {
          const url = new URL(response.url())
          return url.pathname === '/api/emails' && url.searchParams.get('skip') === '50'
        })
        await page.locator('.pager .btn-next').click()
        await nextResponse
        await page.locator('.email-name').filter({ hasText: 'page-two-' }).waitFor()
        const previousResponse = page.waitForResponse(response => {
          const url = new URL(response.url())
          return url.pathname === '/api/emails' && url.searchParams.get('skip') === '0'
        })
        await page.locator('.pager .btn-prev').click()
        await previousResponse
        await page.locator('.email-name').click()
        const expanded = page.locator('.email-expanded')
        await expanded.locator('.relation-list').waitFor()
        await expanded.locator('summary').click()
        const expandedMetrics = await page.evaluate(() => {
          const main = document.querySelector('.main-content')
          return { page: document.documentElement.scrollWidth, main: main.clientWidth, scroll: main.scrollWidth }
        })
        assert(expandedMetrics.page <= width + 1 && expandedMetrics.scroll <= expandedMetrics.main + 1, 'Expanded email page overflow')
        const expandedWidth = await expanded.evaluate(element => ({ width: element.getBoundingClientRect().width, tableWidth: element.closest('.el-table').clientWidth }))
        assert(expandedWidth.width <= expandedWidth.tableWidth + 1, 'Expanded details exceed visible table width: ' + JSON.stringify(expandedWidth))
        if (artifactDir && deviceScaleFactor === 1 && width === 1366) {
          await expanded.scrollIntoViewIfNeeded()
          await page.screenshot({ path: path.join(artifactDir, 'email-expanded-1366x768.png') })
        }
        await page.locator('.email-name').click()
        for (const action of ['新增邮箱', '批量导入']) {
          await page.getByRole('button', { name: action, exact: true }).click()
          const dialog = page.locator('.el-dialog:visible')
          await dialog.waitFor()
          await dialog.evaluate(async element => {
            const animations = []
            for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) animations.push(...ancestor.getAnimations())
            await Promise.all(animations.filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {})))
          })
          const bounds = await dialog.boundingBox()
          assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width + 1 && bounds.y >= 0 && bounds.y + bounds.height <= height + 1, 'Email dialog overflow')
          for (const button of await dialog.locator('.el-dialog__footer button').all()) {
            const footer = await button.boundingBox()
            assert(footer && footer.y >= 0 && footer.y + footer.height <= height + 1, 'Email dialog footer clipped')
          }
          await dialog.getByRole('button', { name: 'Close this dialog', exact: true }).click()
          await dialog.waitFor({ state: 'hidden' })
        }
        console.log(JSON.stringify({ width, height, deviceScaleFactor, emailLayout: 'passed' }))
      }
      assert.deepEqual(errors, [], 'Email runtime errors')
      await context.close()
    }
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
