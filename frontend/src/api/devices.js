/**
 * 终端资产（设备）API 模块
 */
import request from './request'

/**
 * 获取设备列表（分页 + 筛选）
 * @param {Object} params - skip, limit, keyword, device_type, owner_id
 */
export function getDevices(params) {
  return request({
    url: '/devices',
    method: 'get',
    params
  })
}

/**
 * 获取设备详情
 * @param {number|string} id - 设备 ID
 */
export function getDevice(id) {
  return request({
    url: `/devices/${id}`,
    method: 'get'
  })
}

/**
 * 创建设备
 * @param {Object} data - name, device_type, owner_id(超管), node_id, remark
 */
export function createDevice(data) {
  return request({
    url: '/devices',
    method: 'post',
    data
  })
}

/**
 * 更新设备（PATCH 语义，node_id 传 null 表示解绑）
 * @param {number|string} id - 设备 ID
 * @param {Object} data - 要更新的字段
 */
export function updateDevice(id, data) {
  return request({
    url: `/devices/${id}`,
    method: 'patch',
    data
  })
}

export function updateDeviceRelations(id, data) {
  return request({ url: `/devices/${id}/relations`, method: 'put', data })
}

/**
 * 删除设备（软删除，历史轨迹保留）
 * @param {number|string} id - 设备 ID
 */
export function deleteDevice(id) {
  return request({
    url: `/devices/${id}`,
    method: 'delete'
  })
}

/**
 * 获取设备历史轨迹（含已删除，仅超管可查已删除设备）
 * @param {number|string} id - 设备 ID
 * @param {Object} [params] - skip, limit
 */
export function getDeviceLogs(id, params) {
  return request({
    url: `/devices/${id}/logs`,
    method: 'get',
    params
  })
}

/**
 * 获取可绑定节点（仅空闲/使用中且未被占用；编辑时传 exclude_device_id 放行自身）
 * @param {Object} [params] - q, exclude_device_id
 */
export function getBindableNodes(params) {
  return request({
    url: '/devices/bindable-nodes',
    method: 'get',
    params
  })
}
