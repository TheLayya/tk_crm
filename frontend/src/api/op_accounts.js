/**
 * Op Account API module
 */
import request from './request'

/**
 * Get op account stats (total, by_status, by_platform, costs)
 */
export function getOpAccountStats() {
  return request({
    url: '/op-accounts/stats',
    method: 'get'
  })
}

/**
 * List op accounts with filters
 * @param {Object} params - project_id, platform, status, keyword, tags, purchase_channel, sale_customer, skip, limit
 */
export function listOpAccounts(params) {
  return request({
    url: '/op-accounts',
    method: 'get',
    params
  })
}

/**
 * Create a new op account
 */
export function createOpAccount(data) {
  return request({
    url: '/op-accounts',
    method: 'post',
    data
  })
}

/**
 * Update an op account
 */
export function updateOpAccount(id, data) {
  return request({
    url: `/op-accounts/${id}`,
    method: 'put',
    data
  })
}

/**
 * Delete an op account
 */
export function deleteOpAccount(id) {
  return request({
    url: `/op-accounts/${id}`,
    method: 'delete'
  })
}

/**
 * Batch update status for multiple op accounts
 * @param {Object} data - { ids, status, sale_customer?, sale_price?, sale_date? }
 */
export function batchUpdateStatus(data) {
  return request({
    url: '/op-accounts/batch-status',
    method: 'post',
    data
  })
}

/**
 * Import op accounts from file (multipart/form-data)
 */
export function importOpAccounts(formData) {
  return request({
    url: '/op-accounts/import',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * Export op accounts to file
 * @param {Object} params - filter conditions + format
 * @param {string} format - 'csv' | 'xlsx'
 */
export function exportOpAccounts(params, format) {
  return request({
    url: '/op-accounts/export',
    method: 'get',
    params: { ...params, format },
    responseType: 'blob'
  })
}

/**
 * Trigger data collection for specified accounts
 * @param {Array} accountIds - list of account IDs
 */
export function triggerCollect(accountIds) {
  return request({
    url: '/op-accounts/collect',
    method: 'post',
    data: { account_ids: accountIds }
  })
}

/**
 * Get collect task status by task ID
 */
export function getCollectTask(taskId) {
  return request({
    url: `/op-accounts/tasks/${taskId}`,
    method: 'get'
  })
}

/**
 * Get audit logs for an op account
 */
export function getAuditLogs(id) {
  return request({
    url: `/op-accounts/${id}/logs`,
    method: 'get'
  })
}
