# API 模块说明

## request.js - Axios 实例配置

### 功能特性

1. **基础配置**
   - baseURL: `/api` - 所有请求自动添加 `/api` 前缀
   - timeout: 30000ms (30秒) - 请求超时时间
   - Content-Type: `application/json` - 默认请求头

2. **请求拦截器**
   - 在请求发送前执行
   - 可用于添加认证 token、修改请求配置等

3. **响应拦截器**
   - 成功响应：自动提取 `response.data`，简化调用代码
   - 错误响应：统一错误处理和 toast 通知

### 错误处理

系统自动处理以下 HTTP 状态码并显示友好提示：

| 状态码 | 说明 | 提示信息 |
|--------|------|---------|
| 400 | 请求参数错误 | 显示服务器返回的详细信息 |
| 401 | 未授权 | "未授权，请重新登录" |
| 403 | 权限不足 | "拒绝访问，权限不足" |
| 404 | 资源不存在 | "请求的资源不存在" |
| 409 | 资源冲突 | 显示服务器返回的详细信息（如重复创建） |
| 422 | 数据验证失败 | 显示服务器返回的详细信息 |
| 500 | 服务器内部错误 | "服务器内部错误，请稍后重试" |
| 502 | 网关错误 | "网关错误，请稍后重试" |
| 503 | 服务不可用 | "服务暂时不可用，请稍后重试" |
| 504 | 网关超时 | "网关超时，请稍后重试" |
| 网络错误 | 无响应 | "网络连接失败，请检查网络设置" |

### 使用示例

#### 1. 基础 GET 请求

```javascript
import request from './request'

// 获取项目列表
const getProjects = async () => {
  try {
    const data = await request.get('/projects')
    console.log(data)
  } catch (error) {
    // 错误已被拦截器处理，会自动显示 toast
    console.error(error)
  }
}
```

#### 2. 带查询参数的 GET 请求

```javascript
// 获取账号列表（带分页和过滤）
const getAccounts = async () => {
  try {
    const data = await request.get('/accounts', {
      params: {
        page: 1,
        page_size: 20,
        keyword: 'test',
        is_active: true
      }
    })
    console.log(data)
  } catch (error) {
    console.error(error)
  }
}
```

#### 3. POST 请求

```javascript
// 创建项目
const createProject = async () => {
  try {
    const data = await request.post('/projects', {
      name: '新项目',
      description: '项目描述'
    })
    console.log('创建成功:', data)
  } catch (error) {
    // 如果是 409 冲突（名称重复），会自动显示错误提示
    console.error(error)
  }
}
```

#### 4. PUT 请求

```javascript
// 更新账号
const updateAccount = async (id) => {
  try {
    const data = await request.put(`/accounts/${id}`, {
      is_active: false,
      monitor_interval: 60
    })
    console.log('更新成功:', data)
  } catch (error) {
    console.error(error)
  }
}
```

#### 5. DELETE 请求

```javascript
// 删除项目
const deleteProject = async (id) => {
  try {
    await request.delete(`/projects/${id}`)
    console.log('删除成功')
  } catch (error) {
    // 如果项目不存在，会显示 404 错误提示
    console.error(error)
  }
}
```

#### 6. 完整配置的请求

```javascript
// 使用完整配置
const customRequest = async () => {
  try {
    const data = await request({
      url: '/accounts',
      method: 'get',
      params: { page: 1 },
      headers: { 'Custom-Header': 'value' },
      timeout: 10000
    })
    console.log(data)
  } catch (error) {
    console.error(error)
  }
}
```

### 创建 API 模块

建议按资源类型创建独立的 API 模块文件：

```javascript
// src/api/projects.js
import request from './request'

export function getProjects() {
  return request.get('/projects')
}

export function createProject(data) {
  return request.post('/projects', data)
}

export function updateProject(id, data) {
  return request.put(`/projects/${id}`, data)
}

export function deleteProject(id) {
  return request.delete(`/projects/${id}`)
}
```

在组件中使用：

```javascript
import { getProjects, createProject } from '@/api/projects'

// 在 setup 或方法中调用
const loadProjects = async () => {
  const data = await getProjects()
  // 处理数据
}
```

### 开发环境代理

在开发环境中，Vite 已配置代理将 `/api` 请求转发到后端服务器：

```javascript
// vite.config.js
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

### 生产环境

在生产环境中，nginx 配置会将 `/api` 请求反向代理到后端服务，无需修改前端代码。

### 注意事项

1. **错误处理**：所有 API 调用都应使用 try-catch 包裹，虽然错误会自动显示 toast，但可能需要在组件中执行额外的错误处理逻辑

2. **响应数据**：响应拦截器已自动提取 `response.data`，直接使用返回值即可

3. **超时设置**：默认超时 30 秒，如需调整可在单个请求中覆盖 `timeout` 配置

4. **取消请求**：如需取消请求，可使用 axios 的 CancelToken 功能

5. **并发请求**：可使用 `Promise.all()` 或 `axios.all()` 处理多个并发请求
