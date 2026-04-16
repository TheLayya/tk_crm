/**
 * Proxy Node API module
 */
import request from './request'

/**
 * 序列化数组参数为多个同名查询参数
 * axios 默认会将数组序列化为 key[]=val 格式，
 * 后端 FastAPI 期望的是多个同名参数 key=val1&key=val2
 */
function buildArrayParams(params) {
  if (!params) return params
  const result = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      result[key] = value
    }
  }
  return result
}

/**
 * 获取节点列表（带分页和筛选）
 * @param {Object} params - skip, limit, status[], usage[], protocol[], purchase_channel, sale_customer, expire_date_from, expire_date_to
 */
export function getProxyNodes(params) {
  return request({
    url: '/proxy-nodes',
    method: 'get',
    params: buildArrayParams(params),
    // 使用 paramsSerializer 确保数组参数序列化为多个同名参数
    paramsSerializer: {
      indexes: null // 禁用索引，生成 key=val1&key=val2 格式
    }
  })
}

/**
 * 获取单个节点详情
 * @param {number|string} id - 节点 ID
 */
export function getProxyNode(id) {
  return request({
    url: `/proxy-nodes/${id}`,
    method: 'get'
  })
}

/**
 * 创建节点
 * @param {Object} data - 节点数据，ip 和 port 为必填
 */
export function createProxyNode(data) {
  return request({
    url: '/proxy-nodes',
    method: 'post',
    data
  })
}

/**
 * 更新节点（部分更新）
 * @param {number|string} id - 节点 ID
 * @param {Object} data - 要更新的字段
 */
export function updateProxyNode(id, data) {
  return request({
    url: `/proxy-nodes/${id}`,
    method: 'patch',
    data
  })
}

/**
 * 删除节点
 * @param {number|string} id - 节点 ID
 */
export function deleteProxyNode(id) {
  return request({
    url: `/proxy-nodes/${id}`,
    method: 'delete'
  })
}

/**
 * 批量删除节点
 * @param {Array<number|string>} nodeIds - 节点 ID 列表
 */
export function batchDeleteProxyNodes(nodeIds) {
  return request({
    url: '/proxy-nodes/batch',
    method: 'delete',
    data: { node_ids: nodeIds }
  })
}

/**
 * 批量修改节点状态
 * @param {Array<number|string>} nodeIds - 节点 ID 列表
 * @param {string} status - 目标状态（active/expired/sold/disabled）
 */
export function batchUpdateStatus(nodeIds, status) {
  return request({
    url: '/proxy-nodes/batch/status',
    method: 'patch',
    data: { node_ids: nodeIds, status }
  })
}

/**
 * 测试单个节点连通性
 * @param {number|string} id - 节点 ID
 */
export function testProxyNode(id) {
  return request({
    url: `/proxy-nodes/${id}/test`,
    method: 'post'
  })
}

/**
 * 批量测试节点连通性
 * @param {Array<number|string>} nodeIds - 节点 ID 列表
 */
export function batchTestProxyNodes(nodeIds) {
  return request({
    url: '/proxy-nodes/batch/test',
    method: 'post',
    data: { node_ids: nodeIds }
  })
}

/**
 * 导入节点（CSV 或 Excel 文件）
 * @param {File} file - 要上传的文件对象
 */
export function importProxyNodes(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: '/proxy-nodes/import',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 下载导入模板 CSV
 * 通过 request 获取 blob 后创建隐藏 <a> 标签触发浏览器下载，
 * 确保请求携带 Authorization header
 */
export function downloadImportTemplate() {
  return request({
    url: '/proxy-nodes/import/template',
    method: 'get',
    responseType: 'blob'
  }).then((blob) => {
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = 'proxy_nodes_template.csv'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(objectUrl)
  })
}

/**
 * 导出节点数据（触发文件下载）
 * @param {Object} params - 筛选参数（与 getProxyNodes 相同）
 * @param {string} format - 导出格式：'csv' 或 'xlsx'
 */
export function exportProxyNodes(params, format) {
  return request({
    url: '/proxy-nodes/export',
    method: 'get',
    params: { ...buildArrayParams(params), format },
    paramsSerializer: {
      indexes: null
    },
    responseType: 'blob'
  }).then((blob) => {
    const ext = format === 'xlsx' ? 'xlsx' : 'csv'
    const filename = `proxy_nodes_export.${ext}`
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(objectUrl)
  })
}

/**
 * 获取节点统计数据
 * @param {Object} [params] - 可选筛选参数，包含 expire_date_from, expire_date_to
 */
export function getProxyNodeStats(params) {
  return request({
    url: '/proxy-nodes/stats',
    method: 'get',
    params: buildArrayParams(params)
  })
}
