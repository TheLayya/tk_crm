/**
 * History API module
 */
import request from './request'

/**
 * Get account history records
 */
export function getAccountHistory(accountId, params) {
  return request({
    url: `/accounts/${accountId}/history`,
    method: 'get',
    params
  })
}

/**
 * Get account trend data
 */
export function getAccountTrend(accountId, params) {
  return request({
    url: `/accounts/${accountId}/trends`,
    method: 'get',
    params
  })
}
