import request from './request'

// Department
export const getDeptTree = () => request.get('/team/dept/tree')
export const createDept = (data) => request.post('/team/dept', data)
export const updateDept = (id, data) => request.put(`/team/dept/${id}`, data)
export const deleteDept = (id) => request.delete(`/team/dept/${id}`)

// Member
export const getMembers = (params) => request.get('/team/member', { params })
export const createMember = (data) => request.post('/team/member', data)
export const updateMember = (id, data) => request.put(`/team/member/${id}`, data)
export const deleteMember = (id, operationToken) =>
  request.delete(`/team/member/${id}`, { headers: { 'X-Operation-Token': operationToken } })
export const resetMemberPassword = (id, new_password, operationToken) =>
  request.post(`/team/member/${id}/reset-password`, { new_password }, {
    headers: { 'X-Operation-Token': operationToken }
  })

export const unlockMember = (id) =>
  request.post(`/team/member/${id}/unlock`)

// Role
export const getRoles = () => request.get('/team/role')
export const createRole = (data) => request.post('/team/role', data)
export const updateRole = (id, data) => request.put(`/team/role/${id}`, data)
export const deleteRole = (id) => request.delete(`/team/role/${id}`)

// Logs
export const getLoginLogs = (params) => request.get('/team/log/login', { params })
export const getOperationLogs = (params) => request.get('/team/log/operation', { params })
