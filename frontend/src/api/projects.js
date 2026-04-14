/**
 * Project API module
 */
import request from './request'

/**
 * Get all projects
 */
export function getProjects() {
  return request({
    url: '/projects',
    method: 'get'
  })
}

/**
 * Get single project by ID
 */
export function getProject(id) {
  return request({
    url: `/projects/${id}`,
    method: 'get'
  })
}

/**
 * Create a new project
 */
export function createProject(data) {
  return request({
    url: '/projects',
    method: 'post',
    data
  })
}

/**
 * Update a project
 */
export function updateProject(id, data) {
  return request({
    url: `/projects/${id}`,
    method: 'put',
    data
  })
}

/**
 * Delete a project
 */
export function deleteProject(id) {
  return request({
    url: `/projects/${id}`,
    method: 'delete'
  })
}

/**
 * Get project members
 */
export function getProjectMembers(id) {
  return request({ url: `/projects/${id}/members`, method: 'get' })
}

/**
 * Set project members (full replace)
 */
export function setProjectMembers(id, usernames) {
  return request({ url: `/projects/${id}/members`, method: 'put', data: { usernames } })
}
