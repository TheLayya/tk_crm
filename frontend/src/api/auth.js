import request from './request'

export const login = (username, password) =>
  request.post('/auth/login', { username, password })

export const refreshToken = (refresh_token) =>
  request.post('/auth/refresh', { refresh_token })

export const logout = (refresh_token) =>
  request.post('/auth/logout', { refresh_token })

export const verifyPassword = (password) =>
  request.post('/auth/verify-password', { password })
