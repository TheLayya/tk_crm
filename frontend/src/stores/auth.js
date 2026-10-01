import { defineStore } from 'pinia'
import { login as apiLogin, logout as apiLogout, refreshToken as apiRefreshToken } from '@/api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    permissions: JSON.parse(localStorage.getItem('permissions') || '[]'),
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    hasPermission: (state) => (perm) => {
      if (state.user?.is_super_admin) return true
      // 兜底：如果 permissions 包含所有权限标记则视为超管
      if (state.permissions?.includes('*')) return true
      if (state.permissions.includes(perm)) return true
      const legacyAliases = {
        'email:view': ['op_account:view'],
        'email:manage': ['op_account:edit'],
        'email:import': ['op_account:import'],
        'email:check': ['op_account:collect'],
        'card_key:view': ['card_key:manage'],
        'work_item:view': ['work_item:manage']
      }
      return (legacyAliases[perm] || []).some(alias => state.permissions.includes(alias))
    },
  },

  actions: {
    async login(username, password) {
      const data = await apiLogin(username, password)
      this.token = data.access_token
      this.refreshToken = data.refresh_token
      this.user = data.user
      this.permissions = data.permissions
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('refreshToken', data.refresh_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      localStorage.setItem('permissions', JSON.stringify(data.permissions))
    },

    async logout() {
      try {
        if (this.refreshToken) {
          await apiLogout(this.refreshToken)
        }
      } catch (e) {
        // ignore errors on logout
      } finally {
        this._clearState()
      }
    },

    async refreshAccessToken() {
      if (!this.refreshToken) throw new Error('No refresh token')
      const data = await apiRefreshToken(this.refreshToken)
      this.token = data.access_token
      this.refreshToken = data.refresh_token
      this.permissions = data.permissions
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('refreshToken', data.refresh_token)
      localStorage.setItem('permissions', JSON.stringify(data.permissions))
    },

    _clearState() {
      this.token = null
      this.refreshToken = null
      this.user = null
      this.permissions = []
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
      localStorage.removeItem('user')
      localStorage.removeItem('permissions')
    },
  },
})
