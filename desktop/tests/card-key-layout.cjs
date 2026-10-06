const assert = require('node:assert/strict')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))

const project = {
  id: 1, name: '桌面布局验收', description: '隔离模拟数据，不连接业务数据库',
  target_platform: 'gemini pro', members: ['__all__'], is_active: true,
  available: 50, claimed: 1, consumed: 2, can_claim: true,
  email_normal_available: 168, email_available: 277, email_claimed: 1,
  emails_completed: 2, member_stats: [],
}
const key = {
  id: 1, content: 'https://example.invalid/' + 'long-card-key-'.repeat(40),
  status: 'claimed', claimed_by: 'layout-test', claimed_at: '2026-10-05T01:00:00Z',
  history: [],
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const artifactDir = process.env.TKCRM_UI_ARTIFACT_DIR
  if (artifactDir) require('node:fs').mkdirSync(artifactDir, { recursive: true })
  try {
    for (const deviceScaleFactor of [1, 1.25, 1.5, 2]) {
      const context = await browser.newContext({ deviceScaleFactor })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(() => {
        localStorage.setItem('token', 'isolated-layout-fixture')
        localStorage.setItem('user', JSON.stringify({ username: 'layout-test', is_super_admin: true }))
        localStorage.setItem('permissions', JSON.stringify(['*']))
      })
      await page.route('**/api/**', async route => {
        const endpoint = new URL(route.request().url()).pathname
        const responses = {
          '/api/settings/public': { site_name: '布局验收' },
          '/api/updates/check': { current_version: '1.1.15', has_update: false },
          '/api/updates/status': { status: 'idle' },
          '/api/updates/history': { items: [] },
          '/api/card-keys': [project],
          '/api/card-keys/platforms': [{ id: 1, name: 'gemini pro', is_active: true }],
          '/api/card-keys/members': [{ username: 'layout-test' }],
          '/api/card-keys/1/keys': { items: [key], total: 1 },
          '/api/card-keys/1/email': {
            id: 1, email: 'long-registration-mail-address-for-layout-check@gmail.com',
            password: 'fixture-only', recovery_email: 'recovery@example.invalid', totp_secret: 'fixture-only',
          },
          '/api/card-keys/1/email/totp': { code: '123456', remaining: 30 },
          '/api/card-keys/1/work-report': { members: [], items: [] },
          '/api/work-items/summary': {},
        }
        assert(endpoint in responses, 'Unmocked API: ' + endpoint)
        await route.fulfill({ json: responses[endpoint] })
      })
      await page.goto((process.env.TKCRM_UI_URL || 'http://127.0.0.1:8080') + '/card-keys')
      await page.locator('.pending-key code').waitFor()
      await page.locator('.email-actions').waitFor()
      for (const [width, height] of [[1366, 768], [1180, 720], [1093, 614], [960, 540], [768, 540], [683, 384]]) {
        await page.setViewportSize({ width, height })
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
        const layout = await page.evaluate(() => {
          const main = document.querySelector('.main-content')
          return { pageWidth: document.documentElement.scrollWidth, mainWidth: main.clientWidth, mainScroll: main.scrollWidth }
        })
        assert(layout.pageWidth <= width + 1, 'Page overflow: ' + JSON.stringify({ width, layout }))
        assert(layout.mainScroll <= layout.mainWidth + 1, 'Main overflow: ' + JSON.stringify({ width, layout }))
        for (const button of await page.locator('.pending-key button, .email-actions button').all()) {
          await button.scrollIntoViewIfNeeded()
          const bounds = await button.boundingBox()
          assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width + 1, 'Action outside viewport')
          assert(bounds.y >= 0 && bounds.y + bounds.height <= height + 1, 'Action cannot be scrolled into view')
        }
        for (const action of ['＋新建项目', '平台管理', '批量导入']) {
        await page.getByRole('button', { name: action, exact: true }).click()
        const dialog = page.locator('.el-dialog:visible')
        await dialog.waitFor()
        await dialog.evaluate(async element => {
          const animations = []
          for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
            animations.push(...ancestor.getAnimations())
          }
          await Promise.all(animations.filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {})))
        })
        const bounds = await dialog.boundingBox()
        assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= width + 1, 'Dialog overflows width')
        assert(bounds.y >= 0 && bounds.y + bounds.height <= height + 1, 'Dialog overflows height')
        for (const button of await dialog.locator('.el-dialog__footer button').all()) {
          const footerBounds = await button.boundingBox()
          assert(footerBounds && footerBounds.x >= 0 && footerBounds.x + footerBounds.width <= width + 1, 'Dialog footer action overflows width')
          assert(footerBounds.y >= 0 && footerBounds.y + footerBounds.height <= height + 1, 'Dialog footer action overflows height')
        }
        if (artifactDir && deviceScaleFactor === 2 && width === 683 && action === '＋新建项目') {
          await page.evaluate(() => window.scrollTo(0, 0))
          await page.screenshot({ path: path.join(artifactDir, 'project-dialog-683x384-dpr2.png'), fullPage: false })
        }
        await dialog.getByRole('button', { name: 'Close this dialog', exact: true }).click()
        await dialog.waitFor({ state: 'hidden' })
        }
        console.log(JSON.stringify({ width, height, deviceScaleFactor, cardKeyLayout: 'passed' }))
        if (artifactDir && ((deviceScaleFactor === 1 && width === 1366) || (deviceScaleFactor === 2 && width === 683))) {
          await page.screenshot({ path: require('node:path').join(artifactDir, `card-keys-${width}x${height}-dpr${deviceScaleFactor}.png`), fullPage: true })
        }
      }
      assert.deepEqual(errors, [], 'Runtime errors')
      await context.close()
    }
  } finally {
    await browser.close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
