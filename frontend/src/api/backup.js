import request from './request'

export function triggerBackup() {
  return request({
    url: '/backup/trigger',
    method: 'post',
    responseType: 'blob',
  }).then((blob) => {
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ts = new Date().toISOString().slice(0, 19).replace('T', '_').replaceAll(':', '').replace('-', '').replace('-', '')
    a.download = `monitor_backup_${ts}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  })
}

export function restoreBackup(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: '/backup/restore',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}
