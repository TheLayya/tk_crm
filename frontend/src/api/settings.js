/**
 * Settings API module
 */
import request from './request'

/**
 * Get system settings (requires auth)
 */
export function getSettings() {
  return request({
    url: '/settings',
    method: 'get'
  })
}

/**
 * Get public settings (no auth required, for login page)
 */
export function getPublicSettings() {
  return request({
    url: '/settings/public',
    method: 'get'
  })
}

/**
 * Update system settings
 */
export function updateSettings(data) {
  return request({
    url: '/settings',
    method: 'put',
    data
  })
}
