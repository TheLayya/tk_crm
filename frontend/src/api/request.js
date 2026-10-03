import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

// 创建 axios 实例
const request = axios.create({
  baseURL: '/api',
  timeout: 120000, // 增加到120秒，支持批量检查和视频监控
  headers: {
    'Content-Type': 'application/json'
  }
})

// The API rotates refresh tokens and revokes the old one.  A burst of expired
// requests must therefore share one refresh request instead of replaying the
// same refresh token concurrently.
let refreshPromise = null
let redirectPromise = null

const requestUrl = (config) => String(config?.url || '')
const isAuthRequest = (config) => {
  const url = requestUrl(config)
  return url.includes('/auth/login') || url.includes('/auth/refresh')
}

const redirectToLogin = () => {
  if (redirectPromise) return redirectPromise

  redirectPromise = (async () => {
    const { useAuthStore } = await import('@/stores/auth')
    useAuthStore()._clearState()
    if (router.currentRoute.value.path !== '/login') {
      await router.replace('/login')
    }
  })().finally(() => {
    redirectPromise = null
  })

  return redirectPromise
}

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error) => {
    // 处理网络错误
    if (!error.response) {
      ElMessage.error('网络连接失败，请检查网络设置')
      return Promise.reject(error)
    }

    const { status, data } = error.response
    const originalRequest = error.config

    const authRequest = isAuthRequest(originalRequest)

    // 401: 尝试刷新 token，刷新失败则跳转登录页
    // 登录/刷新接口的 401 不触发再次刷新。
    if (status === 401 && !originalRequest._retry && !authRequest) {
      originalRequest._retry = true
      try {
        if (!refreshPromise) {
          refreshPromise = (async () => {
            const { useAuthStore } = await import('@/stores/auth')
            await useAuthStore().refreshAccessToken()
            return localStorage.getItem('token')
          })().finally(() => {
            refreshPromise = null
          })
        }

        const token = await refreshPromise
        if (!token) throw new Error('Refresh did not return an access token')
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers['Authorization'] = `Bearer ${token}`
        return request(originalRequest)
      } catch (refreshError) {
        await redirectToLogin()
        return Promise.reject(refreshError)
      }
    }

    if (originalRequest?.ignoredErrorStatuses?.includes(status)) {
      return Promise.reject(error)
    }

    // 根据 HTTP 状态码显示不同错误信息
    switch (status) {
      case 400:
        ElMessage.error(data?.detail || '请求参数错误')
        break
      case 401:
        // Login/refresh failures are handled by their callers.  In particular,
        // do not show a second “unauthorized” toast for a failed refresh.
        if (!authRequest) {
          ElMessage.error('未授权，请重新登录')
        }
        break
      case 403:
        ElMessage.error('拒绝访问，权限不足')
        break
      case 404:
        ElMessage.error(data?.detail || '请求的资源不存在')
        break
      case 409:
        ElMessage.error(data?.detail || '资源冲突，操作失败')
        break
      case 422:
        ElMessage.error(data?.detail || '数据验证失败')
        break
      case 500:
        ElMessage.error('服务器内部错误，请稍后重试')
        break
      case 502:
        ElMessage.error('网关错误，请稍后重试')
        break
      case 503:
        ElMessage.error('服务暂时不可用，请稍后重试')
        break
      case 504:
        ElMessage.error('网关超时，请稍后重试')
        break
      default:
        ElMessage.error(data?.detail || `请求失败 (${status})`)
    }

    return Promise.reject(error)
  }
)

export default request
