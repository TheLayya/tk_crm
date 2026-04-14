/**
 * 示例 API 模块
 * 演示如何使用 request 实例
 */
import request from './request'

// 示例：获取项目列表
export function getProjects() {
  return request({
    url: '/projects',
    method: 'get'
  })
}

// 示例：创建项目
export function createProject(data) {
  return request({
    url: '/projects',
    method: 'post',
    data
  })
}

// 示例：获取账号列表
export function getAccounts(params) {
  return request({
    url: '/accounts',
    method: 'get',
    params
  })
}
