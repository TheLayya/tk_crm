const assert = require('node:assert/strict')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || path.join(process.env.LOCALAPPDATA, 'TkCRM-Dev/ui-qa/node_modules/playwright'))

async function main() {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } })
  try {
    const page = await context.newPage()
    page.setDefaultTimeout(10000)
    const errors = []
    const requests = []
    const unexpected = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('token', 'isolated-operator-video-fixture')
      localStorage.setItem('user', JSON.stringify({ username: 'video-test' }))
      localStorage.setItem('permissions', JSON.stringify(['op_account:view']))
    })
    const accounts = [
      { id: 101, account: 'standalone-video', platform: 'tiktok', status: '正常', collect_status: 'success',
        nickname: 'Standalone', follower_count: 1200, video_count: 2, monitor_account_id: null,
        video_source: 'op', yesterday_video_count: 2, yesterday_video_plays: [345, 678] },
      { id: 102, account: 'legacy-monitor-video', platform: 'tiktok', status: '正常', collect_status: 'success',
        nickname: 'Legacy', video_count: 1, monitor_account_id: 202, video_source: 'monitor',
        yesterday_video_count: 1, yesterday_video_plays: [999] },
    ]
    const video = (id, title, play_count) => ({ id, video_id: String(id), title, play_count,
      like_count: 9, comment_count: 2, share_count: 1, published_at: '2026-10-05T04:00:00' })
    const responses = {
      '/api/settings/public': { site_name: '视频验收' },
      '/api/updates/check': { current_version: '1.1.12', has_update: false },
      '/api/updates/history': { items: [] },
      '/api/work-items/summary': {},
      '/api/op-accounts': { total: accounts.length, items: accounts },
      '/api/op-accounts/101/videos': { total: 2, items: [video(301, 'Standalone first video', 345), video(302, 'Standalone second video', 678)] },
      '/api/accounts/202/videos': { total: 1, items: [video(303, 'Legacy monitor video', 999)] },
      '/api/op-accounts/101/association-history': { counts: {}, current: [], history: [], ban_snapshots: [] },
      '/api/op-accounts/102/association-history': { counts: {}, current: [], history: [], ban_snapshots: [] },
      '/api/emails/for-account/101': [],
      '/api/emails/for-account/102': [],
    }
    await page.route('**/api/**', async route => {
      const endpoint = new URL(route.request().url()).pathname
      if (!endpoint.startsWith('/api/')) return route.continue()
      requests.push(endpoint)
      if (!(endpoint in responses)) {
        unexpected.push(endpoint)
        return route.fulfill({ status: 500, json: { detail: 'Unmocked API' } })
      }
      await route.fulfill({ json: responses[endpoint] })
    })
    await page.goto((process.env.TKCRM_UI_URL || 'http://127.0.0.1:5186') + '/op-accounts')
    const standalone = page.locator('.el-table__body tr.el-table__row').filter({ hasText: 'standalone-video' })
    try { await standalone.waitFor() } catch (error) {
      console.error('operator page body:', (await page.locator('body').innerText()).slice(0, 3000))
      console.error('requests:', requests)
      throw error
    }
    assert((await standalone.innerText()).includes('已更新 2 条'), 'Standalone yesterday count must not require a monitor')
    assert((await standalone.innerText()).includes('345 / 678'), 'Standalone yesterday plays missing')
    await standalone.locator('.account-cell').click()
    let cards = page.locator('.op-inline-details .video-card')
    await cards.first().waitFor()
    assert.equal(await cards.count(), 2)
    assert((await cards.first().innerText()).includes('Standalone first video'))
    assert(requests.includes('/api/op-accounts/101/videos'), 'Standalone must fetch its operator video ID')
    await standalone.locator('.account-cell').click()

    const legacy = page.locator('.el-table__body tr.el-table__row').filter({ hasText: 'legacy-monitor-video' })
    await legacy.locator('.account-cell').click()
    cards = page.locator('.op-inline-details .video-card')
    await cards.first().waitFor()
    assert.equal(await cards.count(), 1)
    assert((await cards.first().innerText()).includes('Legacy monitor video'))
    assert(requests.includes('/api/accounts/202/videos'), 'Legacy fallback must use the monitor ID')
    assert(!requests.includes('/api/op-accounts/102/videos'), 'Legacy fallback must not use the operator endpoint')
    await legacy.locator('.account-cell').click()

    await page.setViewportSize({ width: 390, height: 844 })
    const mobile = page.locator('.ios-card').filter({ hasText: 'standalone-video' })
    await mobile.waitFor()
    await mobile.locator('.ios-card-account-header').click()
    const detail = page.locator('.op-detail-dialog')
    await detail.waitFor()
    const mobileCards = detail.locator('.video-card')
    await mobileCards.first().waitFor()
    assert.equal(await mobileCards.count(), 2)
    assert((await mobileCards.last().innerText()).includes('Standalone second video'))
    assert.equal(requests.filter(endpoint => endpoint === '/api/op-accounts/101/videos').length, 2, 'Mobile detail must load own videos')
    assert.deepEqual(unexpected, [], 'Unexpected API paths')
    assert.deepEqual(errors, [], 'Operator video runtime errors')
  } finally {
    let timer
    const closed = await Promise.race([
      context.close().then(() => true),
      new Promise(resolve => { timer = setTimeout(() => resolve(false), 1500) }),
    ])
    clearTimeout(timer)
    const process = browser._browserProcess?.process
    if (!closed || process?.exitCode === null) {
      const pid = process?.pid
      if (pid) execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' })
      await Promise.race([browser.close(), new Promise(resolve => setTimeout(resolve, 1500))])
      if (!closed) console.warn('Browser context close exceeded 1.5 seconds; killed only the fixture browser process tree ' + pid)
    } else {
      await browser.close()
    }
  }
  console.log('Operator videos: standalone cards/summary, mobile detail, and monitor fallback passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
