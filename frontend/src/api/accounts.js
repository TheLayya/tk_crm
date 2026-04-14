/**
 * Account API module
 */
import request from './request'

/**
 * Get accounts list with filters
 */
export function getAccounts(params) {
  return request({
    url: '/accounts',
    method: 'get',
    params
  })
}

/**
 * Get single account by ID
 */
export function getAccount(id) {
  return request({
    url: `/accounts/${id}`,
    method: 'get'
  })
}

/**
 * Create a new account
 */
export function createAccount(data) {
  return request({
    url: '/accounts',
    method: 'post',
    data
  })
}

/**
 * Update an account
 */
export function updateAccount(id, data) {
  return request({
    url: `/accounts/${id}`,
    method: 'put',
    data
  })
}

/**
 * Delete an account
 */
export function deleteAccount(id) {
  return request({
    url: `/accounts/${id}`,
    method: 'delete'
  })
}

/**
 * Trigger manual check for an account
 */
export function triggerCheck(id) {
  return request({
    url: `/accounts/${id}/check`,
    method: 'post'
  })
}

/**
 * Batch import accounts from text
 */
export function batchImportAccounts(data) {
  return request({
    url: '/accounts/import',
    method: 'post',
    data
  })
}

/**
 * Batch action on multiple accounts
 */
export function batchAction(data) {
  return request({
    url: '/accounts/batch',
    method: 'post',
    data
  })
}

/**
 * Import accounts from file (CSV/Excel)
 */
export function importFile(formData) {
  return request({
    url: '/accounts/import-file',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * Export accounts to file
 */
export function exportAccounts(params) {
  return request({
    url: '/accounts/export',
    method: 'get',
    params,
    responseType: 'blob'
  })
}
