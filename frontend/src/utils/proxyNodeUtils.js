/**
 * 判断到期日期是否即将到期（距今不足 thresholdDays 天，含今天）
 * @param {string|null} expireDate - 到期日期字符串（YYYY-MM-DD）或 null
 * @param {number} thresholdDays - 阈值天数，默认 7
 * @returns {boolean}
 */
export function isExpiringSoon(expireDate, thresholdDays = 7) {
  if (!expireDate) return false
  const expire = new Date(expireDate)
  const now = new Date()
  // 只比较日期部分，忽略时间
  const nowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const expireDay = new Date(expire.getFullYear(), expire.getMonth(), expire.getDate())
  const diffMs = expireDay - nowDate
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))
  return diffDays <= thresholdDays
}
