const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

async function main() {
  const source = fs.readFileSync(path.join(__dirname, '../src/utils/flowCookie.js'), 'utf8')
  const { extractFlowCookie } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
  const values = { SID: 'sid=value==', OSID: 'osid%2Fvalue', '__Secure-1PSID': 'psid' }
  const base = Object.entries(values).map(([name, value]) => ({ name, value }))
  const expected = { value: 'psid::sid=value==::osid%2Fvalue', hasTimestamp: false }
  let cases = 0
  function check(input, result = expected) { assert.deepEqual(extractFlowCookie(input), result); cases++ }
  function fails(input, pattern) {
    assert.throws(() => extractFlowCookie(input), error => {
      assert.match(error.message, pattern)
      assert(!error.message.includes('SENSITIVE_TEST_VALUE'), 'Errors must not disclose supplied Cookie values')
      return true
    })
    cases++
  }

  for (const input of [values, base, JSON.stringify(base), { cookies: base }, { refreshCookie: JSON.stringify(values) }, JSON.stringify({ cookies: values })]) check(input)
  const header = Object.entries(values).map(([name, value]) => `${name}=${value}`).join('; ')
  check(header)
  check(`Cookie: ${header};`)
  check(`cookie: ${header}; SID=sid=value==`)
  check(`${header}; __Secure-1PSIDTS=timestamp`, { ...expected, value: expected.value + '::timestamp', hasTimestamp: true })
  check(`${header}; __Secure-1PSIDTS=`)
  check(`${header}; __Secure-3PSID=unrelated; SAPISID=unrelated`)
  check('SID="sid=value=="; OSID=osid%2Fvalue; __Secure-1PSID=psid')

  const scoped = base.map(row => ({ ...row, domain: row.name === 'OSID' ? 'flow.google.com' : '.google.com', path: '/', secure: true }))
  check(scoped)
  const mixedScopes = [
    ...scoped,
    { name: 'SID', value: 'flow-host', domain: 'flow.google.com' },
    { name: 'SID', value: 'wrong-accounts', domain: 'accounts.google.com' },
    { name: 'SID', value: 'wrong-google-host', domain: 'google.com' },
    { name: 'SID', value: 'wrong-path', domain: 'flow.google.com', path: '/other' },
    { name: 'OSID', value: 'wrong-domain', domain: 'evilgoogle.com' },
    { name: 'OSID', value: 'wrong-subdomain', domain: 'google.com.evil.invalid' },
    { name: '__Secure-1PSIDTS', value: 'expired', domain: '.google.com', secure: true, expirationDate: 1 },
  ]
  const hostExpected = { value: 'psid::flow-host::osid%2Fvalue', hasTimestamp: false }
  check(mixedScopes, hostExpected)
  check([...mixedScopes].reverse(), hostExpected)
  check(scoped.map(row => ({ ...row, domain: row.name === 'OSID' ? 'FLOW.GOOGLE.COM' : 'GOOGLE.COM', hostOnly: false })))
  check([...scoped, { name: '__Secure-1PSIDTS', value: 'session', expires: -1 }], { value: expected.value + '::session', hasTimestamp: true })
  check([...scoped, { name: '__Secure-1PSIDTS', value: 'session', expires: '-1' }], { value: expected.value + '::session', hasTimestamp: true })
  check([...scoped, { name: '__Secure-1PSIDTS', value: 'session', session: true, expires: 1 }], { value: expected.value + '::session', hasTimestamp: true })
  check(scoped.map(row => ({ ...row, expires: String(Date.now() / 1000 + 3600) })))

  for (const input of ['', 'not-a-cookie', '{broken-json', null, 42, { cookies: base, refreshCookie: base }]) fails(input, /填写|格式|包装/)
  fails('SID=SENSITIVE_TEST_VALUE', /__Secure-1PSID、OSID/)
  fails('__Secure-3PSID=SENSITIVE_TEST_VALUE; SID=s; OSID=o', /__Secure-1PSID/)
  fails(`${header}; SID=SENSITIVE_TEST_VALUE`, /SID 存在多个不同值/)
  fails([...scoped, { name: 'SID', value: 'SENSITIVE_TEST_VALUE', domain: '.google.com' }], /SID 存在多个不同值/)
  check([...mixedScopes, { name: 'SID', value: 'parent-conflict', domain: '.google.com' }], hostExpected)

  for (const invalid of [
    { domain: 'example.invalid', secure: true },
    { domain: 'evilgoogle.com', secure: true },
    { domain: '.google.com.evil.invalid', secure: true },
    { domain: 'google.com', secure: true },
    { domain: '.google.com', hostOnly: true, secure: true },
    { domain: '.google.com', secure: false },
    { domain: '.google.com' },
    { domain: '.google.com', secure: true, path: '/other' },
    { partitioned: true },
    { partitionKey: { topLevelSite: 'https://example.invalid' } },
    { expires: 1 },
    { expirationDate: 'invalid' },
    { expirationDate: '' },
    { expirationDate: false },
    { expirationDate: Infinity },
    { secure: 'true' },
    { hostOnly: 'false' },
    { httpOnly: null },
    { value: 'SENSITIVE_TEST_VALUE\nheader-injection' },
    { value: 'SENSITIVE_TEST_VALUE;bad' },
    { value: 123 },
  ]) fails(base.map(row => row.name === '__Secure-1PSID' ? { ...row, ...invalid } : row), /__Secure-1PSID/)

  const cyclic = {}; cyclic.cookies = cyclic
  fails(cyclic, /包装层数/)
  console.log(`Flow Cookie extraction: ${cases} synthetic cases passed`)
}

main().catch(error => { console.error(error); process.exitCode = 1 })
