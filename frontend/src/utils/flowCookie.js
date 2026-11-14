const COOKIE_NAMES = ['__Secure-1PSID', 'SID', 'OSID', '__Secure-1PSIDTS']
const REQUIRED_NAMES = COOKIE_NAMES.slice(0, 3)
const INVALID_NAME = /[\x00-\x20\x7f;=]/
const INVALID_VALUE = /[\x00-\x1f\x7f;]/

function headerRows(input) {
  const header = input.replace(/^cookie\s*:\s*/i, '')
  return header.split(';').filter(part => part.trim()).map(part => {
    const separator = part.indexOf('=')
    if (separator < 1) throw new Error('CK 格式无效，请粘贴 Cookie Header 或 JSON Cookie')
    const name = part.slice(0, separator).trim()
    let value = part.slice(separator + 1).trim()
    if (!name || INVALID_NAME.test(name)) throw new Error('CK 格式无效，请检查 Cookie 名称')
    if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1)
    return { name, value }
  })
}

function cookieRows(input, depth = 0) {
  if (depth > 6) throw new Error('CK 包装层数过多，请粘贴 Cookie 数组或 Header')
  if (typeof input === 'string') {
    const text = input.trim()
    if (!text) throw new Error('请先填写 CK（Cookie）')
    if (/^[\[{]/.test(text)) {
      let parsed
      try { parsed = JSON.parse(text) }
      catch { throw new Error('CK 的 JSON 格式无效，请检查后重试') }
      return cookieRows(parsed, depth + 1)
    }
    return headerRows(text)
  }
  if (Array.isArray(input)) return input
  if (input && typeof input === 'object') {
    const wrappers = ['cookies', 'refreshCookie'].filter(key => Object.hasOwn(input, key))
    if (wrappers.length > 1) throw new Error('CK 中有多个 Cookie 包装字段，请仅保留一份后重试')
    if (wrappers.length) return cookieRows(input[wrappers[0]], depth + 1)
    return Object.entries(input).map(([name, value]) => ({ name, value }))
  }
  throw new Error('CK 格式无效，请粘贴 Cookie Header 或 JSON Cookie')
}

function candidate(row, now) {
  if (!row || typeof row !== 'object' || !COOKIE_NAMES.includes(row.name)) return null
  const { name, value } = row
  if (typeof value !== 'string' || !value || INVALID_VALUE.test(value)) return null
  if (row.partitionKey || row.partitioned) return null
  for (const field of ['hostOnly', 'secure', 'httpOnly', 'session']) {
    if (Object.hasOwn(row, field) && typeof row[field] !== 'boolean') return null
  }

  // Headers and old name/value maps have no browser scope metadata. Keep the
  // reference project's compatibility defaults; never override supplied scope.
  const legacy = row.domain == null || row.domain === ''
  const domain = legacy ? (name === 'OSID' ? 'flow.google.com' : '.google.com') : row.domain
  if (typeof domain !== 'string') return null
  const host = domain.toLowerCase().replace(/^\./, '')
  const hostOnly = row.hostOnly ?? !domain.startsWith('.')
  // Flow-host values take precedence over parent-domain values. Cookies for
  // accounts.google.com, host-only google.com, and foreign domains cannot serve
  // a flow.google.com request and must not be mixed into its credentials.
  if (host !== 'flow.google.com' && (host !== 'google.com' || hostOnly)) return null
  const path = row.path || '/'
  if (path !== '/') return null
  const secure = row.secure ?? (legacy && name.startsWith('__Secure-'))
  if (name.startsWith('__Secure-') && !secure) return null

  const expires = row.expirationDate ?? row.expires
  if (row.session !== true && expires != null && expires !== -1) {
    if (!['number', 'string'].includes(typeof expires) || String(expires).trim() === '') return null
    const expiry = Number(expires)
    if (!Number.isFinite(expiry) || (expiry !== -1 && expiry <= now)) return null
  }
  return { name, value, rank: host === 'flow.google.com' ? 2 : 1 }
}

/** Extract saved Flow credentials locally; this does not log in or renew them. */
export function extractFlowCookie(input) {
  const candidates = new Map(COOKIE_NAMES.map(name => [name, []]))
  const now = Date.now() / 1000
  for (const row of cookieRows(input)) {
    const item = candidate(row, now)
    if (item) candidates.get(item.name).push(item)
  }
  const selected = new Map()
  for (const [name, items] of candidates) {
    if (!items.length) continue
    const rank = items.reduce((highest, item) => Math.max(highest, item.rank), 0)
    const values = new Set(items.filter(item => item.rank === rank).map(item => item.value))
    if (values.size > 1) throw new Error(`CK 中 ${name} 存在多个不同值，请仅保留同一账号的 Cookie 后重试`)
    selected.set(name, values.values().next().value)
  }
  const missing = REQUIRED_NAMES.filter(name => !selected.has(name))
  if (missing.length) throw new Error(`CK 缺少有效 Cookie：${missing.join('、')}`)
  return {
    value: COOKIE_NAMES.filter(name => selected.has(name)).map(name => selected.get(name)).join('::'),
    hasTimestamp: selected.has('__Secure-1PSIDTS'),
  }
}
