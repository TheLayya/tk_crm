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

export function checkUpdate() {
  return request({ url: '/updates/check', method: 'get' })
}

export function applyUpdate() {
  return request({ url: '/updates/apply', method: 'post' })
}

export function getUpdateStatus() {
  return request({ url: '/updates/status', method: 'get' })
}

export function getUpdateHistory() {
  return request({ url: '/updates/history', method: 'get' })
}
