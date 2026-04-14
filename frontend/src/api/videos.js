/**
 * Video API module
 */
import request from './request'

/**
 * Get account videos
 */
export function getAccountVideos(accountId, params) {
  return request({
    url: `/accounts/${accountId}/videos`,
    method: 'get',
    params
  })
}

/**
 * Get video stats history
 */
export function getVideoStats(videoId) {
  return request({
    url: `/videos/${videoId}/stats`,
    method: 'get'
  })
}
