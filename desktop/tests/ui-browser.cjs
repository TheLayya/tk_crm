const assert = require('node:assert/strict')
const { spawnSync } = require('node:child_process')

async function launchUiBrowser(chromium) {
  const server = await chromium.launchServer({ headless: true })
  const browser = await chromium.connect(server.wsEndpoint())
  return { browser, close: async () => {
    let timer
    let forced = false
    try {
      const graceful = await Promise.race([
        server.close().then(() => true),
        new Promise(resolve => { timer = setTimeout(() => resolve(false), 2000) }),
      ])
      if (!graceful) {
        const child = server.process()
        const pid = Number(child.pid)
        assert(Number.isInteger(pid) && pid > 0, 'Owned UI browser PID was invalid')
        const command = `$p=Get-Process -Id ${pid} -ErrorAction SilentlyContinue; if ($p -and -not $p.HasExited) { Stop-Process -Id ${pid} -Force -ErrorAction Stop; $deadline=(Get-Date).AddSeconds(5); do {$p.Refresh(); if ($p.HasExited) {break}; Start-Sleep -Milliseconds 100} while ((Get-Date) -lt $deadline); if (-not $p.HasExited) {throw 'Owned browser remained'} }; Write-Output 'Owned browser process exited'`
        const result = spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command], { windowsHide: true, timeout: 10000 })
        assert.equal(result.status, 0, 'Owned UI browser cleanup was not verified: ' + String(result.stderr))
        forced = true
        for (const pipe of child.stdio || []) pipe?.destroy?.()
        child.unref()
        await browser.close()
        await server.kill()
        console.warn('UI fixture cleanup: verified its own browser exited after graceful close timed out')
      }
      if (!forced) assert.notEqual(server.process().exitCode, null, 'Owned UI browser remained after cleanup')
    } finally { clearTimeout(timer) }
  } }
}

module.exports = { launchUiBrowser }
