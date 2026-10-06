const assert = require('node:assert/strict')
const path = require('node:path')
const moduleCandidates = [
  process.env.PLAYWRIGHT_MODULE,
  'playwright',
  path.join(process.env.LOCALAPPDATA || '', 'TkCRM-Dev', 'ui-qa', 'node_modules', 'playwright'),
].filter(Boolean)
let playwright
for (const candidate of moduleCandidates) {
  try { playwright = require(candidate); break } catch {}
}
if (!playwright) throw new Error('找不到 Playwright；请安装依赖或设置 PLAYWRIGHT_MODULE')
const { chromium } = playwright

async function main() {
  const browser = await chromium.launch({ headless: true })
  const artifactDir = process.env.TKCRM_UI_ARTIFACT_DIR
  if (artifactDir) require('node:fs').mkdirSync(artifactDir, { recursive: true })
  try {
    for (const deviceScaleFactor of [1, 1.25, 1.5, 2]) {
    const context = await browser.newContext({ deviceScaleFactor })
    const page = await context.newPage()
    const failures = []
    page.on('pageerror', error => failures.push(error.message))
    await page.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname
      if (endpoint === '/api/auth/login') {
        await route.fulfill({ status: 401, json: { detail: 'Invalid credentials' } })
        return
      }
      const responses = {
        '/api/settings/public': {
          site_name: 'Windows高缩放布局验收LongTeamNameWithoutSpaces'.repeat(3),
          login_screen_text: '数据连接团队，协作创造价值',
        },
        '/api/updates/check': { current_version: '1.1.15', has_update: false },
        '/api/updates/status': { status: 'idle' },
        '/api/updates/history': { items: [] },
      }
      assert(endpoint in responses, 'Unmocked API: ' + endpoint)
      await route.fulfill({ json: responses[endpoint] })
    })
    await page.goto((process.env.TKCRM_UI_URL || 'http://127.0.0.1:8080') + '/login/')
    await page.locator('.login-card').waitFor()
    await page.locator('.login-header h2').filter({ hasText: 'LongTeamNameWithoutSpaces' }).waitFor()
    await page.locator('input[autocomplete=username]').fill('layout-test')
    await page.locator('input[autocomplete=current-password]').fill('fixture-only')
    await page.locator('.login-btn').click()
      await page.locator('.login-error').waitFor()
      await page.evaluate(() => window.scrollTo(0, 0))
    for (const [width, height] of [[1920, 1080], [1366, 768], [1093, 614], [960, 540], [768, 540], [683, 384], [1180, 720]]) {
      await page.setViewportSize({ width, height })
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      const metrics = await page.evaluate(() => {
        const card = document.querySelector('.login-card')
        const bounds = card.getBoundingClientRect()
        return {
          width: window.innerWidth,
          pageWidth: document.documentElement.scrollWidth,
          left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom,
          viewportHeight: window.innerHeight,
          sidebarCount: document.querySelectorAll('.sidebar').length,
          cardWidth: card.clientWidth,
          cardScrollWidth: card.scrollWidth,
        }
      })
      assert(metrics.pageWidth <= metrics.width + 1, 'Page overflows horizontally: ' + JSON.stringify(metrics))
      assert(metrics.left >= -1 && metrics.right <= width + 1, 'Login card exceeds width')
      assert(metrics.top >= -1 && metrics.bottom <= height + 1, 'Login card exceeds height: ' + JSON.stringify(metrics))
      assert(metrics.cardScrollWidth <= metrics.cardWidth + 1, 'Long branding overflows login card')
      assert.equal(metrics.sidebarCount, 0, 'Login must not display the application sidebar')
      await page.locator('.login-btn').scrollIntoViewIfNeeded()
      const button = await page.locator('.login-btn').boundingBox()
      assert(button && button.y >= 0 && button.y + button.height <= height + 1, 'Login button is inaccessible')
      console.log(JSON.stringify({ width, height, deviceScaleFactor, passed: true }))
      if (artifactDir && ((deviceScaleFactor === 1 && width === 1366) || (deviceScaleFactor === 2 && width === 683))) {
        await page.evaluate(() => window.scrollTo(0, 0))
        await page.screenshot({ path: require('node:path').join(artifactDir, `login-${width}x${height}-dpr${deviceScaleFactor}.png`), fullPage: true })
      }
    }
    await page.route('**/api/settings/public', route => route.fulfill({ json: { site_name: 'TikTok Monitor' } }))
    for (const [width, height] of [[780, 467], [780, 449], [1180, 674], [1366, 720]]) {
      await page.setViewportSize({ width, height })
      await page.reload()
      await page.locator('.login-header h2').filter({ hasText: 'TikTok Monitor' }).waitFor()
      const initialLayout = await page.locator('.login-card').evaluate(card => {
        const button = card.querySelector('.login-btn').getBoundingClientRect()
        const bounds = card.getBoundingClientRect()
        return { height: card.clientHeight, scrollHeight: card.scrollHeight, buttonBottom: button.bottom, cardBottom: bounds.bottom }
      })
      assert(initialLayout.scrollHeight <= initialLayout.height + 1, 'Default login requires internal scrolling: ' + JSON.stringify(initialLayout))
      assert(initialLayout.buttonBottom <= initialLayout.cardBottom && initialLayout.buttonBottom <= height, 'Default login button is clipped')
      console.log(JSON.stringify({ width, height, deviceScaleFactor, defaultLogin: 'passed' }))
      if (artifactDir && deviceScaleFactor === 1 && width === 780 && height === 467) {
        await page.screenshot({ path: path.join(artifactDir, 'login-default-780x467.png') })
      }
    }
    assert.deepEqual(failures, [], 'Browser runtime errors')
    await context.close()
    }
  } finally {
    await browser.close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
