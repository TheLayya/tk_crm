# 需求文档

## 简介

TikTok Monitor 是一个基于 Vue 3 + Element Plus 的前端管理系统，目前仅针对桌面端设计，缺乏移动端适配，且没有面包屑导航。本功能旨在为系统添加响应式移动端布局支持，以及面包屑导航组件，提升在手机、平板等小屏设备上的使用体验，同时帮助用户在多级页面中快速定位当前位置。

## 术语表

- **Layout**：系统主布局组件（`frontend/src/components/Layout.vue`），包含侧边栏、顶部栏和主内容区
- **Sidebar**：侧边导航栏，宽度固定为 200px，包含所有一级和二级菜单项
- **Breadcrumb**：面包屑导航组件，显示当前页面在路由层级中的位置路径
- **Breakpoint**：响应式断点，本项目定义移动端为视口宽度 ≤ 768px，平板端为 769px–1024px
- **Overlay**：遮罩层，移动端侧边栏展开时覆盖主内容区的半透明蒙层
- **Hamburger**：汉堡菜单按钮，移动端用于切换侧边栏显示/隐藏的图标按钮
- **Router_Meta**：Vue Router 路由元信息，用于存储面包屑标题等页面元数据

## 需求

### 需求 1：响应式侧边栏

**用户故事：** 作为移动端用户，我希望侧边栏在小屏设备上能够折叠隐藏，并通过汉堡菜单按钮控制展开，以便在手机上获得更大的内容浏览空间。

#### 验收标准

1. WHEN 视口宽度小于或等于 768px，THE Layout SHALL 隐藏侧边栏并在顶部栏左侧显示汉堡菜单按钮
2. WHEN 用户点击汉堡菜单按钮，THE Layout SHALL 以滑入动画展开侧边栏覆盖在主内容区上方
3. WHEN 侧边栏处于展开状态，THE Layout SHALL 在主内容区显示半透明遮罩层
4. WHEN 用户点击遮罩层，THE Layout SHALL 关闭侧边栏并移除遮罩层
5. WHEN 用户在移动端侧边栏中点击任意菜单项，THE Layout SHALL 自动关闭侧边栏
6. WHEN 视口宽度大于 768px，THE Layout SHALL 始终显示侧边栏且不显示汉堡菜单按钮
7. WHEN 视口宽度从移动端变化为桌面端，THE Layout SHALL 自动关闭移动端侧边栏并恢复桌面端布局

---

### 需求 2：响应式顶部栏

**用户故事：** 作为移动端用户，我希望顶部栏在小屏设备上能够合理布局，不出现内容溢出或遮挡，以便正常使用顶部功能。

#### 验收标准

1. WHEN 视口宽度小于或等于 768px，THE Layout SHALL 在顶部栏左侧显示汉堡菜单按钮，右侧显示用户名和退出按钮
2. WHILE 视口宽度小于或等于 768px，THE Layout SHALL 将顶部栏高度保持在 50px 以上以确保可点击区域足够
3. WHEN 视口宽度小于或等于 480px，THE Layout SHALL 隐藏用户名文字，仅显示退出图标按钮

---

### 需求 3：响应式主内容区

**用户故事：** 作为移动端用户，我希望主内容区的内边距和布局在小屏设备上自动调整，以便内容不超出屏幕宽度。

#### 验收标准

1. WHEN 视口宽度小于或等于 768px，THE Layout SHALL 将主内容区的水平内边距从 20px 调整为 12px
2. WHILE 视口宽度小于或等于 768px，THE Layout SHALL 确保主内容区宽度为 100vw 减去侧边栏宽度（移动端侧边栏收起时为 100vw）
3. WHEN 视口宽度小于或等于 768px，THE Layout SHALL 为所有 `el-table` 启用横向滚动，防止表格内容溢出屏幕

---

### 需求 4：响应式对话框

**用户故事：** 作为移动端用户，我希望弹出对话框在手机屏幕上能够全屏或接近全屏显示，以便正常填写表单内容。

#### 验收标准

1. WHEN 视口宽度小于或等于 768px，THE Layout SHALL 将所有 `el-dialog` 的宽度覆盖为 95vw
2. WHEN 视口宽度小于或等于 768px，THE Layout SHALL 将所有 `el-dialog` 的最大高度限制为 90vh 并启用内部滚动

---

### 需求 5：面包屑导航组件

**用户故事：** 作为系统用户，我希望在每个页面顶部看到面包屑导航，以便快速了解当前所在位置并能一键返回上级页面。

#### 验收标准

1. THE Breadcrumb SHALL 显示在主内容区顶部、页面内容上方
2. WHEN 用户访问任意路由，THE Breadcrumb SHALL 根据当前路由路径自动生成对应的层级导航项
3. WHEN 面包屑导航包含多个层级，THE Breadcrumb SHALL 将除最后一项外的所有层级渲染为可点击链接
4. WHEN 用户点击面包屑中的可点击层级，THE Breadcrumb SHALL 导航至对应路由路径
5. THE Breadcrumb SHALL 将最后一个层级项渲染为不可点击的当前页文字
6. WHEN 视口宽度小于或等于 768px，THE Breadcrumb SHALL 将字体大小调整为 12px 以适应小屏显示

---

### 需求 6：路由元信息配置

**用户故事：** 作为开发者，我希望通过路由元信息统一配置每个页面的面包屑标题，以便面包屑组件能够自动读取并展示正确的页面名称。

#### 验收标准

1. THE Router_Meta SHALL 为每条路由记录添加 `breadcrumb` 字段，值为该页面在面包屑中显示的中文名称
2. WHEN 路由存在父子层级关系，THE Router_Meta SHALL 通过 `matched` 数组按层级顺序提供面包屑数据
3. THE Breadcrumb SHALL 过滤掉 `breadcrumb` 字段为空或未定义的路由层级，不将其渲染为导航项
4. WHEN 路由为根路径 `/` 的重定向，THE Breadcrumb SHALL 不显示该重定向路由的导航项

---

### 需求 7：平板端适配

**用户故事：** 作为平板用户，我希望系统在 769px–1024px 宽度范围内能够以折叠侧边栏模式运行，以便在平板上获得更宽的内容展示区域。

#### 验收标准

1. WHEN 视口宽度在 769px 到 1024px 之间，THE Layout SHALL 将侧边栏折叠为仅显示图标的窄栏（宽度 64px）
2. WHEN 侧边栏处于折叠状态，THE Layout SHALL 通过 Element Plus `el-menu` 的 `collapse` 属性隐藏菜单文字
3. WHEN 用户将鼠标悬停在折叠侧边栏的菜单项上，THE Layout SHALL 通过 Element Plus 内置 tooltip 显示菜单项名称
4. WHEN 视口宽度超过 1024px，THE Layout SHALL 恢复展开侧边栏并显示完整菜单文字
