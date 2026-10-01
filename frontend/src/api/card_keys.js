import request from './request'

export const getCardKeyProjects = () => request.get('/card-keys')
export const getCardKeyMembers = () => request.get('/card-keys/members')
export const createCardKeyProject = (data) => request.post('/card-keys', data)
export const updateCardKeyProject = (id, data) => request.put(`/card-keys/${id}`, data)
export const importCardKeys = (id, content) => request.post(`/card-keys/${id}/import`, { content })
export const getCardKeys = (id, params) => request.get(`/card-keys/${id}/keys`, { params })
export const claimCardKey = (id) => request.post(`/card-keys/${id}/claim`)
export const consumeCardKey = (projectId, keyId) => request.post(`/card-keys/${projectId}/keys/${keyId}/consume`)
export const releaseCardKey = (projectId, keyId) => request.post(`/card-keys/${projectId}/keys/${keyId}/release`)
