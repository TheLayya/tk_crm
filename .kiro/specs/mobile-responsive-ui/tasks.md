# 实现计划：移动端响应式 UI

## 概述

基于设计文档，将 TikTok Monitor 前端改造为支持移动端（iOS 卡片风格底部 Tab Bar）、平板端（折叠侧边栏）和桌面端三种响应式布局，并新增面包屑导航组件。

## 任务

- [x] 1. 配置路由元信息与全局响应式样式
  - [x] 1.1 改造 `frontend/src/router/index.js`，将现有扁平路由重构为嵌套结构，为 `/team/*` 子路由添加父路由 `/team`（仅用于面包屑层级），并为每条路由的 `meta` 添加 `breadcrumb` 字段
    - 参照设计文档路由 meta 表格，为 `/monitor`、`/accounts/:id`、`/op-accounts`、`/settings`、`/team/dept`、`/team/member`、`/team/role`、`/team/log` 添加对应中文 `breadcrumb` 值
    - `/login`、`/403`、`/` 不设置 `breadcrumb`
    - _需求：6.1、6.2_
  - [x] 1.2 新建 `frontend/src/styles/responsive.css`，添加全局响应式样式
    - 移动端主内容区偏移（为固定顶部栏和底部 Tab Bar 留空间）
    - 平板端及以下表格横向滚动
    - 移动端对话框全屏覆盖（95vw、90vh、iOS 圆角）
    - iOS 系统字体覆盖
    - iOS 风格分隔线
    - iOS CSS 变量（`--ios-bg`、`--ios-card-bg`、`--ios-blue` 等）
    - 安全区域 fallback 兼容写法
    - _需求：3.1、3.2、3.3、4.1、4.2_
  - [x] 1.3 在 `frontend/src/main.js` 中引入 `responsive.css`
    - _需求：3.1、4.1_

- [x] 2. 新增面包屑导航组件
  - [x] 2.1 新建 `frontend/src/components/Breadcrumb.vue`
    - 基于 `route.matched` 过滤有 `meta.breadcrumb` 且非空字符串的路由记录
    - 过滤根路径 `/` 重定向记录
    - 生成 `BreadcrumbItem[]`，最后一项 `isLast=true`，其余为 `false`
    - 使用 `el-breadcrumb` 渲染，非最后项为可点击链接（`router.push`），最后项为纯文字
    - 移动端（`isMobile`）通过 `v-if` 隐藏，接收父组件传入的 `isMobile` prop
    - 移动端字体大小 12px（通过 CSS media query）
    - _需求：5.1、5.2、5.3、5.4、5.5、5.6、6.3、6.4_
  - [ ]* 2.2 为面包屑生成逻辑编写属性测试（Property 1：面包屑过滤正确性）
    - **属性 1：面包屑过滤正确性**
    - 提取 `generateBreadcrumbs` 为可独立测试的纯函数
    - 使用 fast-check 验证：对任意 `route.matched` 数组，输出仅包含 `meta.breadcrumb` 存在且非空的记录，顺序一致
    - **验证：需求 5.2、6.3、6.4**
  - [ ]* 2.3 为面包屑生成逻辑编写属性测试（Property 2：最后一项标记正确性）
    - **属性 2：最后一项标记正确性**
    - 使用 fast-check 验证：对任意长度 ≥ 1 的有效面包屑数组，有且仅有最后一项 `isLast=true`
    - **验证：需求 5.3、5.5**
  - [ ]* 2.4 为 Breadcrumb.vue 编写单元测试
    - 空 `matched` 数组 → 输出空数组
    - 所有记录均无 `breadcrumb` → 输出空数组
    - 单条有 `breadcrumb` 的记录 → 输出 1 项，`isLast=true`
    - 根路径 `/` 重定向记录混入 → 被过滤掉
    - _需求：5.2、6.3、6.4_

- [ ] 3. 检查点 - 确保路由和面包屑逻辑正确
  - 确保所有测试通过，如有疑问请向用户确认。

- [x] 4. 新增移动端底部 Tab Bar 组件
  - [x] 4.1 新建 `frontend/src/components/MobileTabBar.vue`
    - 定义 `tabs` 计算属性，包含监控、运营、团队、设置四个 Tab 项，通过 `authStore.hasPermission` 过滤
    - 定义 `activeTab` 计算属性，根据当前路由路径匹配对应 Tab（`/accounts/*` 归属 `/monitor`，`/team/*` 归属 `/team/member`）
    - 点击 Tab 项调用 `router.push(tab.key)`
    - 应用 iOS 风格样式：毛玻璃背景、`env(safe-area-inset-bottom)` 适配、固定底部、触摸区域 44px
    - _需求：1.1、1.2、1.5_
  - [ ]* 4.2 为 MobileTabBar.vue 编写单元测试
    - 用户有 `monitor:view` 权限 → tabs 包含监控项
    - 用户无任何权限 → tabs 为空数组
    - 当前路由为 `/accounts/123` → `activeTab === '/monitor'`
    - 当前路由为 `/team/dept` → `activeTab === '/team/member'`
    - _需求：1.1、1.5_

- [x] 5. 改造 Layout.vue 响应式布局
  - [x] 5.1 在 `frontend/src/components/Layout.vue` 的 `<script setup>` 中添加响应式断点逻辑
    - 添加 `windowWidth` ref，初始值为 `window.innerWidth`
    - 添加 `isMobile`、`isTablet`、`isDesktop`、`sidebarCollapsed` 计算属性
    - 在 `onMounted` 注册 `resize` 事件监听，在 `onUnmounted` 移除，防止内存泄漏
    - _需求：1.1、1.6、1.7、7.1、7.4_
  - [x] 5.2 改造 Layout.vue 模板结构
    - `el-aside` 添加 `v-if="!isMobile"`，动态绑定 `width`（桌面端 200px，平板端 64px）
    - `el-menu` 绑定 `:collapse="sidebarCollapsed"`
    - 移除汉堡按钮和遮罩层相关代码
    - 顶部栏：移动端显示页面标题（居中）和退出图标，桌面端/平板端显示用户名和退出按钮
    - 用户名 `span.username` 添加 `v-show="!isMobile"`
    - 在布局底部插入 `<MobileTabBar v-if="isMobile" />`
    - 在主内容区顶部插入 `<Breadcrumb v-if="!isMobile" :isMobile="isMobile" />`
    - 引入并注册 `Breadcrumb`、`MobileTabBar` 组件
    - _需求：1.1、1.2、1.3、1.4、1.6、1.7、2.1、2.2、2.3、5.1、7.1、7.2、7.3、7.4_
  - [x] 5.3 为 Layout.vue 添加移动端顶部栏 iOS 毛玻璃样式
    - 移动端顶部栏：`position: fixed`，毛玻璃背景（`backdrop-filter: blur(20px) saturate(180%)`），`env(safe-area-inset-top)` 适配
    - 提供 `backdrop-filter` 不支持时的不透明背景色降级方案
    - 平板端折叠侧边栏样式（宽度 64px）
    - _需求：2.1、2.2、2.3、7.1、7.2_
  - [ ]* 5.4 为 Layout.vue 响应式计算属性编写单元测试
    - `windowWidth=768` → `isMobile=true`，`isTablet=false`
    - `windowWidth=769` → `isMobile=false`，`isTablet=false`
    - `windowWidth=900` → `isTablet=true`，`sidebarCollapsed=true`
    - `windowWidth=1024` → `isTablet=true`，`sidebarCollapsed=true`
    - `windowWidth=1025` → `isDesktop=true`，`sidebarCollapsed=false`
    - _需求：1.1、1.6、7.1、7.4_

- [ ] 6. 检查点 - 确保布局改造正确
  - 确保所有测试通过，如有疑问请向用户确认。

- [x] 7. 改造视图组件支持移动端 iOS 卡片列表
  - [x] 7.1 改造 `frontend/src/views/MonitorManage.vue`，添加移动端 iOS 卡片列表渲染
    - 添加 `isMobile` 响应式状态（复用断点逻辑）
    - 使用 `v-if="!isMobile"` 保留桌面端 `el-table`
    - 使用 `v-else` 渲染 iOS 卡片列表（`ios-card-list` / `ios-card` / `ios-card-row`），展示账号名、状态等关键字段
    - 卡片操作按钮区（`ios-card-actions`）包含编辑、删除等操作
    - _需求：3.1、3.2、3.3_
  - [x] 7.2 改造 `frontend/src/views/OpAccountList.vue`，添加移动端 iOS 卡片列表渲染
    - 同 7.1 模式，展示运营账号关键字段
    - _需求：3.1、3.2、3.3_
  - [x] 7.3 改造 `frontend/src/views/team/MemberManage.vue`，添加移动端 iOS 卡片列表渲染
    - 同 7.1 模式，展示成员关键字段
    - _需求：3.1、3.2、3.3_
  - [x] 7.4 改造 `frontend/src/views/team/DeptManage.vue`、`RoleManage.vue`、`LogView.vue`，添加移动端 iOS 卡片列表渲染
    - 同 7.1 模式，各自展示对应关键字段
    - _需求：3.1、3.2、3.3_

- [ ] 8. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有疑问请向用户确认。

## 备注

- 标有 `*` 的子任务为可选项，可跳过以加快 MVP 交付
- 每个任务均引用具体需求条款以保证可追溯性
- 属性测试使用 fast-check，单元测试使用 Vitest + Vue Test Utils
- 属性测试验证面包屑生成逻辑的普遍正确性，单元测试验证具体示例和边界值
- 移动端采用 iOS 卡片风格，而非简单响应式缩放，需在真实设备或 Safari 上验证毛玻璃效果和安全区域适配
