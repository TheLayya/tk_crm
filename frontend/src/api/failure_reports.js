import request from './request'

export const getFailureReports = source => request.get(source.kind === 'card_key' ? `/card-keys/${source.projectId}/keys/${source.keyId}/failure-reports` : `/emails/${source.emailId}/failure-reports`)
export const getFailureScreenshot = url => request.get(url.replace(/^\/api(?=\/)/, ''), { responseType: 'blob' })
