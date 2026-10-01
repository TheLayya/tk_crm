import request from './request'

export function getDataOverview(params) {
  return request({
    url: '/overview',
    method: 'get',
    params
  })
}
