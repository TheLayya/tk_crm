# 实现计划：运营账号 UI 重设计（op-account-ui-redesign）

## 概述

按照"设计令牌 + 局部覆盖"的分层架构，逐步将 `OpAccountList.vue` 及相关样式从 Element Plus 默认风格升级为 2025 大厂风格。改造分为五个阶段：建立设计令牌系统 → 重设计列表页与过滤栏 → 重设计状态/平台标识 → 重设计详情弹窗 → 重设计表单弹窗，最后完成响应式与动效收尾。

## 任务

- [x] 1. 建立设计令牌系统并接入主入口
  - 在 `frontend/src/styles/` 目录下新建 `op-account-design.css`
  - 按设计文档定义所有 CSS 变量：颜色令牌（`--color-bg-page`、`--color-bg-card`、`--color-bg-hover`、`--color-border`、`--color-border-subtle`、`--color-text-primary`、`--color-text-secondary`、`--color-text-muted`、`--color-accent`、`--color-accent-light`）
  - 定义间距令牌（`--space-xs/sm/md/lg/xl`）、圆角令牌（`--radius-sm/md/lg`）、阴影令牌（`--shadow-card`、`--shadow-dialog`）
  - 在 `:root` 中覆盖 Element Plus CSS 变量（`--el-color-primary`、`--el-border-color` 等）
  - 在 `frontend/src/main.js` 中添加 `import './styles/op-account-design.css'`（置于 `responsive.css` 之前）
  - _需求：1.1、1.2、1.3、1.4、1.5、1.6_

- [x] 2. 重设计账号列表页整体布局与表格样式
  - [x] 2.1 修改 `OpAccountList.vue` 的页面背景色和卡片样式
    - 将页面根元素背景色改为 `var(--color-bg-page)`
    - 在 `op-account-design.css` 中覆盖 `.el-card` 样式：应用 `--shadow-card`、`--radius-md`、`--color-border` 边框
    - 确保过滤栏卡片与表格卡片之间保持 `--space-md` 垂直间距
    - _需求：2.1、2.2、2.3_

  - [x] 2.2 修改表格视觉样式
    - 在 `op-account-design.css` 中覆盖 `.el-table` 相关变量：表头背景 `#FAFBFC`、表头字色 `--color-text-secondary`、表头字号 12px 字重 500
    - 去除列间竖线（`.el-table--border .el-table__cell { border-right: none }`），保留行间分隔线（`border-bottom: 1px solid var(--color-border-subtle)`）
    - 添加行悬停过渡：`transition: background-color 150ms ease`
    - _需求：2.4、2.5、2.6_

  - [ ]* 2.3 为表格样式覆盖编写单元测试
    - 验证 `.el-card` 应用了正确的圆角和阴影 CSS 变量
    - 验证表格行悬停时背景色变为 `--color-bg-hover`
    - _需求：2.2、2.4_

- [x] 3. 重设计过滤栏与批量操作工具栏
  - [x] 3.1 重构 `Filter_Bar` 布局
    - 将过滤栏内容分为左侧过滤项区域和右侧操作按钮区域（使用 flexbox `justify-content: space-between`）
    - 将"新增账号"按钮保持 `type="primary"`（填充型），其余按钮（导入、导出、列配置）改为 `plain` 描边型
    - 统一过滤输入框尺寸为 `size="default"`（高度 32px）
    - _需求：3.1、3.2、3.3_

  - [x] 3.2 重构批量操作工具栏
    - 将现有 `.batch-toolbar` 替换为 `.batch-toolbar-new`
    - 应用背景色 `var(--color-accent-light)`（`#EEF2FF`）、圆角 `var(--radius-sm)`
    - 已选数量文字使用 `--color-accent` 颜色、字重 500
    - _需求：3.4_

  - [ ]* 3.3 为过滤栏布局编写单元测试
    - 验证 `selectedIds` 为空时批量工具栏不渲染
    - 验证 `selectedIds` 非空时批量工具栏渲染且背景色正确
    - _需求：3.4_

- [ ] 4. 检查点 —— 确保所有测试通过，如有问题请告知用户

- [x] 5. 重设计状态与平台标识（Badge）
  - [x] 5.1 在 `op-account-design.css` 中定义 Badge 样式类
    - 定义 `.op-status-badge` 基础样式（`display: inline-flex`、`padding: 2px 8px`、`border-radius: var(--radius-sm)`、`font-size: 12px`、`font-weight: 500`）
    - 定义四种状态修饰类：`--normal`（绿）、`--self`（蓝）、`--banned`（红）、`--sold`（灰）
    - 定义 `.op-platform-badge` 基础样式及四种平台修饰类：`--tiktok`、`--youtube`、`--instagram`、`--facebook`
    - _需求：4.1、4.2、4.3、4.4_

  - [x] 5.2 在 `OpAccountList.vue` 中替换 `el-tag` 为 Badge
    - 在 `<script setup>` 中提取 `STATUS_CONFIG` 和 `PLATFORM_CONFIG` 常量映射
    - 添加 `statusKey(status)` 辅助函数，将中文状态值映射为 CSS class 后缀
    - 将表格中所有 `el-tag` 状态标签替换为 `<span :class="['op-status-badge', ...]">`
    - 将表格中所有 `el-tag` 平台标签替换为 `<span :class="['op-platform-badge', ...]">`
    - _需求：4.1、4.2、4.3、4.4_

  - [ ]* 5.3 为 Badge class 映射编写属性测试（属性 1）
    - **属性 1：Badge class 映射正确性**
    - 使用 fast-check 验证：对任意有效状态值，`STATUS_CONFIG` 映射返回唯一且非空的 CSS class
    - 使用 fast-check 验证：对任意有效平台值，`PLATFORM_CONFIG` 映射返回唯一且非空的 CSS class
    - **验证：需求 4.2、4.4**

- [x] 6. 重设计账号详情弹窗
  - [x] 6.1 重构详情弹窗 Hero 区域
    - 将现有 `el-col` + `el-avatar` 布局替换为 `.detail-hero` 容器（flex 水平排列）
    - Hero 区域包含：64px 圆形头像、账号名（18px 字重 600）、昵称（14px `--color-text-muted`）、Platform_Badge、Status_Badge
    - 添加 Hero 区域底部分隔线（`1px solid var(--color-border-subtle)`）
    - _需求：5.1、5.2_

  - [x] 6.2 重构详情弹窗信息分组区域
    - 将 `el-descriptions` 替换为 `.section-group` + `.info-row` 自定义布局
    - 实现"数据概览"区块：4 列网格（`grid-template-columns: repeat(4, 1fr)`），每项含数字（20px 字重 700）和标签（12px 灰色）
    - 实现"账号凭证"区块：密码、2FA密钥、绑定邮箱、邮箱密码、绑定手机，敏感字段默认显示 `••••••`
    - 实现"采购 / 出售"区块：2 列网格布局（`grid-template-columns: 1fr 1fr`）
    - 实现"其他信息"区块：注册人、使用人、账号来源、注册时间、最后采集时间、备注
    - 在 `<script setup>` 中定义 `credentialFields` 数组配置敏感字段列表
    - _需求：5.3、5.4、5.8_

  - [x] 6.3 实现 TikTok 权限区块（条件显示）
    - 添加"TikTok 权限"Section_Group，仅当 `detailDialog.row.platform === 'tiktok'` 时渲染
    - 使用 `.tiktok-perms-grid`（4 列网格）展示中视频、橱窗、手机直播、伴侣直播
    - 权限状态使用 ✓/✗ 图标，开启时颜色 `#166534`，关闭时颜色 `#9CA3AF`
    - _需求：5.4_

  - [x] 6.4 实现敏感字段显示/遮蔽切换
    - 保留现有 `visibleFields` 响应式状态和 `toggleVisible` 函数
    - 敏感字段值使用 `font-family: 'SF Mono', monospace` 等宽字体
    - 眼睛图标（`.eye-btn`）悬停时颜色变为 `--color-accent`，过渡 150ms
    - 字段为空时不渲染眼睛图标（`v-if="detailDialog.row[field.key]"`）
    - _需求：5.5、5.6_

  - [x] 6.5 更新详情弹窗尺寸与 footer
    - 将弹窗宽度改为 680px
    - Footer 提供"关闭"（描边）和"编辑"（`type="primary"`）两个按钮
    - 点击"编辑"时关闭详情弹窗并打开编辑表单
    - _需求：5.1、5.7_

  - [ ]* 6.6 为敏感字段切换编写属性测试（属性 2）
    - **属性 2：敏感字段显示切换 Round-Trip**
    - 使用 fast-check 验证：对任意包含非空敏感字段的账号，`toggleVisible` 调用两次后 `visibleFields` 状态恢复初始值
    - **验证：需求 5.5、5.6**

  - [ ]* 6.7 为 formatNum 编写属性测试（属性 3）
    - **属性 3：formatNum 格式化一致性**
    - 使用 fast-check 验证：对任意 n ≥ 1000 的整数，`formatNum(n)` 结果字符串长度大于 `String(n).length`
    - 使用 fast-check 验证：`formatNum(null)` 和 `formatNum(undefined)` 返回 `'-'` 或 `'—'`
    - **验证：需求 5.8**

- [ ] 7. 检查点 —— 确保所有测试通过，如有问题请告知用户

- [x] 8. 重设计新增/编辑账号表单弹窗
  - [x] 8.1 替换表单分组标题
    - 将所有 `<el-divider>` 替换为 `.form-section-title` 自定义标题（12px 大写 `--color-text-muted` 字重 600，底部 `1px solid var(--color-border-subtle)`）
    - 分组顺序：基础信息 → 账号凭证 → TikTok 权限（条件）→ 采购信息 → 出售信息 → 其他
    - _需求：6.2、6.3_

  - [x] 8.2 实现 TikTok 权限 2×2 网格
    - 将 TikTok 权限四个开关改为 `.tiktok-switch-grid`（`grid-template-columns: 1fr 1fr`）布局
    - 使用 `v-show` 配合 CSS transition 控制 TikTok 权限区域的显示/隐藏
    - _需求：6.6、6.7_

  - [x] 8.3 更新表单弹窗尺寸与 footer
    - 将弹窗宽度改为 720px
    - 统一表单标签宽度为 90px，输入框尺寸为 `default`
    - 编辑模式下在弹窗标题旁显示账号名（灰色 14px）
    - Footer 按钮：取消（描边）、保存（`type="primary"`），最小宽度 80px
    - _需求：6.1、6.4、6.5、6.8_

  - [ ]* 8.4 为平台条件渲染编写属性测试（属性 4）
    - **属性 4：平台条件渲染正确性**
    - 使用 fast-check 验证：对任意非 tiktok 平台值，`form.platform === 'tiktok'` 为 false（TikTok 权限区域不可见）
    - 使用 fast-check 验证：对 tiktok 平台值，条件为 true（TikTok 权限区域可见）
    - **验证：需求 6.7_**

  - [ ]* 8.5 为表单验证编写单元测试
    - 验证平台为空时提交被阻止（`el-form` 校验失败）
    - 验证账号为空时提交被阻止
    - 验证国家/地区为空时提交被阻止
    - _需求：6.9_

- [x] 9. 表格列视觉优化与空状态
  - [x] 9.1 优化操作列按钮
    - 将操作列（固定右侧）的文字链接按钮替换为图标按钮，添加 `el-tooltip` 显示操作名称（编辑、采集、历史、删除）
    - 操作列宽度设为不超过 120px
    - _需求：7.2_

  - [x] 9.2 优化敏感字段列显示
    - 将表格中敏感字段列（密码、2FA、邮箱密码）的遮蔽符号改为 `—` 加锁图标（`el-icon`）
    - 点击锁图标后显示真实值（复用 `toggleVisible` 逻辑）
    - _需求：7.3_

  - [x] 9.3 优化采集进度条卡片样式
    - 将采集进度条卡片的样式与主卡片对齐（相同圆角、阴影）
    - 进度条颜色改为 `--color-accent`（通过 `color` prop 或 CSS 覆盖）
    - _需求：7.5_

- [x] 10. 响应式适配与交互动效
  - [x] 10.1 升级移动端卡片样式
    - 将移动端 `.ios-card` 样式同步更新为新设计风格（使用 `--shadow-card`、`--radius-md`、`--color-border`）
    - 移动端过滤栏仅保留"新增账号"按钮，其余操作折叠到 `el-dropdown` 更多菜单
    - _需求：8.1、8.3_

  - [x] 10.2 添加弹窗入场动画
    - 在 `op-account-design.css` 中为 `.el-dialog` 添加入场动画：`transform: scale(0.96) → scale(1)` + `opacity: 0 → 1`，持续 200ms，缓动 `cubic-bezier(0.16, 1, 0.3, 1)`
    - 确保 transition 属性仅作用于合成层属性（`background-color`、`opacity`、`transform`、`box-shadow`）
    - _需求：9.1、9.5_

  - [x] 10.3 保留安全区域适配
    - 确认 `responsive.css` 中的 `env(safe-area-inset-*)` 逻辑未被覆盖
    - 确认移动端弹窗 `width: 95vw`、`max-height: 90vh` 规则在 `op-account-design.css` 中正确设置
    - _需求：8.2、8.4_

- [ ] 11. 最终检查点 —— 确保所有测试通过，如有问题请告知用户

## 备注

- 标有 `*` 的子任务为可选测试任务，可跳过以加快 MVP 交付
- 属性测试需要安装 `fast-check`：`npm install --save-dev fast-check`（在 `frontend/` 目录下执行）
- 每个属性测试文件顶部注释格式：`// Feature: op-account-ui-redesign, Property {N}: {属性描述}`
- 所有 CSS 改动优先写入 `op-account-design.css`，组件内部细节使用 `<style scoped>`
- 改造过程中保持现有 API 调用、数据流、权限指令（`v-permission`）逻辑不变
