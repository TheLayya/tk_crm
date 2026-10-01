import request from './request'

export const listEmails = (params) => request({ url: '/emails', method: 'get', params })
export const createEmail = (data) => request({ url: '/emails', method: 'post', data })
export const updateEmail = (id, data) => request({ url: `/emails/${id}`, method: 'put', data })
export const deleteEmail = (id) => request({ url: `/emails/${id}`, method: 'delete' })
export const importEmails = (text, trade) => request({ url: '/emails/import', method: 'post', data: { text, ...trade } })
export const checkEmails = (ids) => request({ url: '/emails/check', method: 'post', data: { account_ids: ids, consent: true }, timeout: 90000 })
export const getEmailRelations = (id) => request({ url: `/emails/${id}/relations`, method: 'get' })
export const getEmailAccountOptions = (keyword = '') => request({ url: '/emails/account-options', method: 'get', params: { keyword } })
export const bindEmailAccount = (emailId, data) => request({ url: `/emails/${emailId}/relations`, method: 'post', data })
export const unbindEmailAccount = (emailId, relationId) => request({ url: `/emails/${emailId}/relations/${relationId}`, method: 'delete' })
