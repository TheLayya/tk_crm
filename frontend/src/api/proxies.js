/**
 * Proxy API module
 */
import request from './request'

/**
 * Get all proxies
 */
export async function getProxies() {
  const items = []
  // These small configuration tables use the complete collection for local queries.
  for (let skip = 0; ; skip += 100) {
    const page = await request({ url: '/proxies', method: 'get', params: { skip, limit: 100 } })
    const rows = Array.isArray(page) ? page : page.items || []
    items.push(...rows)
    if (rows.length < 100) return items
  }
}

/**
 * Get single proxy by ID
 */
export function getProxy(id) {
  return request({
    url: `/proxies/${id}`,
    method: 'get'
  })
}

/**
 * Create a new proxy
 */
export function createProxy(data) {
  return request({
    url: '/proxies',
    method: 'post',
    data
  })
}

/**
 * Update a proxy
 */
export function updateProxy(id, data) {
  return request({
    url: `/proxies/${id}`,
    method: 'put',
    data
  })
}

/**
 * Delete a proxy
 */
export function deleteProxy(id) {
  return request({
    url: `/proxies/${id}`,
    method: 'delete'
  })
}

/**
 * Test proxy connectivity
 */
export function testProxy(id) {
  return request({
    url: `/proxies/${id}/test`,
    method: 'post'
  })
}

/**
 * Batch create proxies from text
 */
export function batchCreateProxies(data) {
  return request({
    url: '/proxies/batch',
    method: 'post',
    data
  })
}
