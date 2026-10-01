import request from './request'

export const getWorkItems = (params) => request.get('/work-items', { params })
export const getWorkItemSummary = () => request.get('/work-items/summary')
export const getReminderMembers = () => request.get('/work-items/members')
export const getWorkItemCategories = () => request.get('/work-items/categories')
export const updateWorkItemCategories = (categories) => request.put('/work-items/categories', { categories })
export const createWorkItem = (data) => request.post('/work-items', data)
export const updateWorkItem = (id, data) => request.put(`/work-items/${id}`, data)
export const deleteWorkItem = (id) => request.delete(`/work-items/${id}`)
