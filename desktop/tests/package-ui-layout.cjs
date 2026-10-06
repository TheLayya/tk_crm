const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const net = require('node:net')
const { spawn } = require('node:child_process')

async function main() {
  const root = path.resolve(__dirname, '../..')
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'TkCRM-package-ui-'))
  const listener = net.createServer()
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve))
  const port = listener.address().port
  await new Promise(resolve => listener.close(resolve))
  const url = `http://127.0.0.1:${port}`
  const server = spawn(path.join(root, 'desktop/runtime/windows-x64/server/TkCrm.Server.exe'), [], {
    cwd: data, windowsHide: true,
    env: { ...process.env, TKCRM_DATA_DIR: data, TKCRM_LEGACY_DATA_DIR: '', TKCRM_MANAGED: '1', PORT: String(port), PYTHONUTF8: '1' },
  })
  let logs = ''
  server.stdout.on('data', chunk => { logs += chunk })
  server.stderr.on('data', chunk => { logs += chunk })
  const exited = new Promise(resolve => server.once('exit', resolve))
  try {
    let health
    for (let attempt = 0; attempt < 60; attempt++) {
      assert(server.exitCode === null, 'Packaged server exited: ' + logs)
      try { health = await (await fetch(url + '/health', { signal: AbortSignal.timeout(1000) })).json() } catch {}
      if (health?.status === 'ok') break
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    assert.equal(health?.status, 'ok', logs)
    for (const filename of (process.env.TKCRM_UI_TEST_FILES || 'ui-layout.cjs,card-key-layout.cjs,email-layout.cjs').split(',')) {
      const test = spawn(process.execPath, [path.join(__dirname, filename)], {
        cwd: root, windowsHide: true, stdio: 'inherit',
        env: { ...process.env, TKCRM_UI_URL: url, TKCRM_UI_ARTIFACT_DIR: path.join(data, 'screenshots') },
      })
      const code = await new Promise((resolve, reject) => { test.once('exit', resolve); test.once('error', reject) })
      assert.equal(code, 0, filename + ' failed; service logs: ' + logs)
    }
    console.log(`PASS packaged UI layout: version=${health.version} port=${port} screenshots=${path.join(data, 'screenshots')}`)
  } finally {
    if (server.exitCode === null) server.stdin.end('shutdown\n')
    await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 10000))])
    if (server.exitCode === null) { server.kill(); await exited }
    fs.writeFileSync(path.join(data, 'server.log'), logs)
    console.log('Packaged UI test logs: ' + data)
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
