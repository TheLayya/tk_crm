/**
 * 从 route.matched 生成面包屑数组
 *
 * 过滤条件：
 * 1. 排除根路径 / 重定向记录
 * 2. meta.breadcrumb 存在且非空字符串
 *
 * @param {import('vue-router').RouteLocationMatched[]} matched
 * @returns {{ title: string, path: string, isLast: boolean }[]}
 */
export function generateBreadcrumbs(matched) {
  const filtered = matched.filter(
    r => r.path !== '/' && r.meta?.breadcrumb && r.meta.breadcrumb.trim() !== ''
  )
  return filtered.map((r, index) => ({
    title: r.meta.breadcrumb,
    path: r.path,
    isLast: index === filtered.length - 1
  }))
}
