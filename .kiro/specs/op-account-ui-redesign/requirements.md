# 需求文档

## 简介

本功能对 TikTok Monitor 项目的运营账号模块（`OpAccountList.vue`）进行全面 UI 重设计，目标是将现有陈旧的 Element Plus 默认风格升级为 2025 大厂风格的精美界面。设计参考 Linear、GitHub、Notion 的核心设计语言：极简克制、信息层次清晰、精准的间距系统、卡片式布局、柔和阴影与圆角。

重设计范围涵盖三个核心区域：
1. **账号详情弹窗**（当前使用 `el-descriptions` 多列表格，视觉陈旧）
2. **账号列表页整体布局与视觉风格**（过滤栏、表格、分页）
3. **新增/编辑账号表单对话框**（当前为标准 `el-form` 多分区布局）

技术栈：Vue 3 + Element Plus + Vite，不引入新的 UI 框架，在现有技术栈内实现设计升级。

---

## 词汇表

- **UI_System**：运营账号模块的前端界面系统，包含列表页、详情弹窗、表单弹窗
- **Detail_Dialog**：账号详情弹窗，双击表格行触发，展示账号完整信息
- **Form_Dialog**：新增/编辑账号表单弹窗
- **List_Page**：运营账号列表页，包含过滤栏、数据表格、分页
- **Filter_Bar**：列表页顶部的过滤与操作工具栏
- **Status_Badge**：账号状态的视觉标识（正常/自用/封禁/已售）
- **Platform_Badge**：账号平台的视觉标识（TikTok/YouTube/Instagram/Facebook）
- **Section_Group**：表单或详情中的信息分组区块（如"账号凭证"、"采购信息"）
- **Design_Token**：CSS 自定义属性（变量），用于统一管理颜色、间距、圆角、阴影等设计值
- **Sensitive_Field**：需要遮蔽显示的敏感字段（密码、2FA密钥、邮箱密码）

---

## 需求

### 需求 1：建立统一的设计令牌系统

**用户故事：** 作为前端开发者，我希望有一套统一的 CSS 设计令牌，以便整个运营账号模块的视觉风格保持一致，并支持未来的主题扩展。

#### 验收标准

1. THE UI_System SHALL 在独立的 CSS 文件或 `<style>` 块中定义设计令牌，包含颜色、间距、圆角、阴影、字体大小等变量
2. THE UI_System SHALL 使用以下核心颜色令牌：
   - `--color-bg-page`：页面背景色（`#F7F8FA`，浅灰）
   - `--color-bg-card`：卡片背景色（`#FFFFFF`）
   - `--color-bg-hover`：悬停背景色（`#F5F7FA`）
   - `--color-border`：默认边框色（`#E4E7ED`）
   - `--color-border-subtle`：细边框色（`rgba(0,0,0,0.06)`）
   - `--color-text-primary`：主文字色（`#1A1A2E`）
   - `--color-text-secondary`：次要文字色（`#606266`）
   - `--color-text-muted`：弱化文字色（`#909399`）
   - `--color-accent`：强调色（`#5B6CF8`，Linear 风格蓝紫）
3. THE UI_System SHALL 使用以下间距令牌：`--space-xs`（4px）、`--space-sm`（8px）、`--space-md`（16px）、`--space-lg`（24px）、`--space-xl`（32px）
4. THE UI_System SHALL 使用以下圆角令牌：`--radius-sm`（6px）、`--radius-md`（10px）、`--radius-lg`（14px）
5. THE UI_System SHALL 使用以下阴影令牌：`--shadow-card`（`0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)`）、`--shadow-dialog`（`0 20px 60px rgba(0,0,0,0.15)`）
6. WHEN 设计令牌发生变更，THE UI_System SHALL 通过修改令牌值即可全局生效，无需逐一修改组件样式

---

### 需求 2：重设计账号列表页整体布局

**用户故事：** 作为运营人员，我希望账号列表页有清晰的视觉层次和现代感，以便快速浏览和操作大量账号数据。

#### 验收标准

1. THE List_Page SHALL 使用 `--color-bg-page` 作为页面背景色，替换现有的 `#f0f2f5`
2. THE List_Page SHALL 将过滤栏、表格区域渲染为白色卡片（`--color-bg-card`），卡片使用 `--shadow-card` 阴影和 `--radius-md` 圆角，替换现有的 `el-card` 默认样式
3. THE List_Page SHALL 在卡片之间保持 `--space-md`（16px）的垂直间距
4. WHEN 鼠标悬停在表格行上，THE List_Page SHALL 将该行背景色变为 `--color-bg-hover`，过渡时间为 150ms
5. THE List_Page SHALL 将表格的 `border` 属性替换为仅保留行间分隔线（`border-bottom: 1px solid var(--color-border-subtle)`），去除列间竖线
6. THE List_Page SHALL 将表格头部背景色设为 `#FAFBFC`，字体颜色设为 `--color-text-secondary`，字号为 12px，字重为 500
7. THE List_Page SHALL 将分页组件对齐方式保持右对齐，并与表格卡片底部保持 `--space-md` 间距

---

### 需求 3：重设计过滤栏与操作工具栏

**用户故事：** 作为运营人员，我希望过滤栏和操作按钮布局清晰、视觉克制，以便高效筛选和批量操作账号。

#### 验收标准

1. THE Filter_Bar SHALL 将过滤输入项（平台、状态、关键词等）与操作按钮（新增、导入、导出、列配置）分为左右两个区域，左侧为过滤项，右侧为操作项
2. THE Filter_Bar SHALL 将"新增账号"按钮样式设为填充型（`type="primary"`），其余操作按钮（导入、导出、列配置）设为描边型（`plain`），以区分主次操作
3. THE Filter_Bar SHALL 将过滤输入框的高度统一为 32px（`size="default"`），与按钮高度对齐
4. WHEN 已选中账号数量大于 0，THE Filter_Bar SHALL 在过滤栏下方显示批量操作工具栏，工具栏背景色为 `#EEF2FF`（浅蓝紫），圆角为 `--radius-sm`，包含已选数量提示和批量操作按钮
5. THE Filter_Bar SHALL 将平台筛选器的选项使用对应颜色的小圆点图标辅助标识（TikTok 黑、YouTube 红、Instagram 紫、Facebook 蓝）

---

### 需求 4：重设计状态与平台标识

**用户故事：** 作为运营人员，我希望账号状态和平台信息通过视觉色块清晰呈现，以便一眼识别账号状态，无需逐字阅读标签文字。

#### 验收标准

1. THE UI_System SHALL 将账号状态（正常/自用/封禁/已售）从 `el-tag` 替换为自定义 Status_Badge 组件，使用填充色块而非描边标签
2. THE Status_Badge SHALL 使用以下配色方案：
   - 正常：背景 `#DCFCE7`，文字 `#166534`（绿色系）
   - 自用：背景 `#DBEAFE`，文字 `#1E40AF`（蓝色系）
   - 封禁：背景 `#FEE2E2`，文字 `#991B1B`（红色系）
   - 已售：背景 `#F3F4F6`，文字 `#6B7280`（灰色系）
3. THE Status_Badge SHALL 使用 `--radius-sm`（6px）圆角，内边距为 `2px 8px`，字号为 12px，字重为 500
4. THE Platform_Badge SHALL 使用对应平台品牌色的浅色背景，字体使用对应品牌色：
   - TikTok：背景 `#F0F0F0`，文字 `#1A1A1A`
   - YouTube：背景 `#FEE2E2`，文字 `#CC0000`
   - Instagram：背景 `#FDF2F8`，文字 `#9333EA`
   - Facebook：背景 `#EFF6FF`，文字 `#1D4ED8`
5. WHEN 采集状态为"失败"，THE UI_System SHALL 在采集状态列显示红色 Status_Badge，并在鼠标悬停时通过 tooltip 显示失败原因（如有）

---

### 需求 5：重设计账号详情弹窗

**用户故事：** 作为运营人员，我希望账号详情弹窗有清晰的信息层次和精美的视觉设计，以便快速获取账号的完整信息，而不是面对一堆密集的表格单元格。

#### 验收标准

1. THE Detail_Dialog SHALL 将弹窗宽度设为 680px，使用 `--shadow-dialog` 阴影，`--radius-lg`（14px）圆角
2. THE Detail_Dialog SHALL 在弹窗顶部设计账号 Hero 区域，包含：头像（64px，圆形）、账号名（18px，字重 600）、昵称（14px，`--color-text-muted`）、Platform_Badge、Status_Badge，水平排列，左对齐
3. THE Detail_Dialog SHALL 将信息内容区域替换 `el-descriptions` 为自定义的分组卡片布局，每个 Section_Group 为独立的视觉区块
4. THE Detail_Dialog SHALL 包含以下 Section_Group，每组有标题行（12px，大写，`--color-text-muted`，字重 600）和内容行：
   - **数据概览**：粉丝数、关注数、点赞数、视频数，以 2×2 网格展示，每项包含数字（20px，字重 700）和标签（12px，灰色）
   - **账号凭证**：密码、2FA密钥、绑定邮箱、邮箱密码、绑定手机，每行左侧为字段名，右侧为值（Sensitive_Field 默认遮蔽）
   - **TikTok 权限**（仅 TikTok 账号显示）：中视频、橱窗、手机直播、伴侣直播，使用开关图标（✓/✗）而非 el-tag
   - **采购 / 出售**：采购渠道、采购金额、采购日期、出售客户、出售金额、出售日期
   - **其他信息**：注册人、使用人、账号来源、注册时间、最后采集时间、备注
5. WHEN Sensitive_Field 处于遮蔽状态，THE Detail_Dialog SHALL 显示 `••••••` 占位符和眼睛图标按钮
6. WHEN 用户点击眼睛图标，THE Detail_Dialog SHALL 切换对应 Sensitive_Field 的显示/遮蔽状态
7. THE Detail_Dialog SHALL 在弹窗底部 footer 区域提供"关闭"和"编辑"两个操作按钮，"编辑"按钮使用 `--color-accent` 填充色
8. THE Detail_Dialog SHALL 在数据概览区域的数字使用 `formatNum` 函数格式化（千分位分隔），空值显示 `—`（破折号）而非 `-`

---

### 需求 6：重设计新增/编辑账号表单弹窗

**用户故事：** 作为运营人员，我希望新增和编辑账号的表单弹窗布局清晰、分组合理，以便高效填写账号信息，减少视觉疲劳。

#### 验收标准

1. THE Form_Dialog SHALL 将弹窗宽度设为 720px，使用 `--shadow-dialog` 阴影，`--radius-lg` 圆角
2. THE Form_Dialog SHALL 将表单内容按 Section_Group 分组，每组使用轻量分隔线（`1px solid var(--color-border-subtle)`）和组标题（12px，大写，`--color-text-muted`，字重 600）替换现有的 `el-divider`
3. THE Form_Dialog SHALL 包含以下 Section_Group，顺序为：基础信息、账号凭证、TikTok 权限（条件显示）、采购信息、出售信息、其他
4. THE Form_Dialog SHALL 将表单标签宽度统一为 90px，输入框使用 `default` 尺寸（高度 32px）
5. WHEN 表单处于编辑模式，THE Form_Dialog SHALL 在弹窗标题旁显示账号名称（灰色，14px），以区分新增和编辑状态
6. THE Form_Dialog SHALL 将 TikTok 权限的四个开关（中视频、橱窗、手机直播、伴侣直播）排列为 2×2 网格，每项包含开关控件和标签文字
7. WHEN 用户选择平台为非 TikTok，THE Form_Dialog SHALL 隐藏 TikTok 权限 Section_Group，过渡使用 `v-show` 配合 CSS transition
8. THE Form_Dialog SHALL 在 footer 区域提供"取消"（描边）和"保存"（填充，`--color-accent`）两个按钮，按钮宽度不小于 80px
9. IF 表单提交时必填字段（平台、账号、国家/地区）为空，THEN THE Form_Dialog SHALL 在对应字段下方显示红色错误提示文字，并阻止提交

---

### 需求 7：表格列的视觉优化

**用户故事：** 作为运营人员，我希望表格中的数据列视觉清晰、信息密度合理，以便在不滚动的情况下获取关键信息。

#### 验收标准

1. THE List_Page SHALL 将账号列（固定左侧）的头像尺寸保持 32px，账号名字重设为 500，昵称字号设为 12px，颜色为 `--color-text-muted`
2. THE List_Page SHALL 将操作列（固定右侧）的按钮替换为图标按钮（Icon Button），使用 tooltip 显示操作名称，减少列宽占用，操作列宽度不超过 120px
3. THE List_Page SHALL 将敏感字段列（密码、2FA、邮箱密码）的遮蔽符号从 `••••••` 改为统一的 `—`（破折号）加锁图标，点击锁图标后显示真实值
4. WHEN 表格数据为空，THE List_Page SHALL 显示居中的空状态插图和"暂无账号数据"提示文字，替换 Element Plus 默认的 `el-empty`
5. THE List_Page SHALL 将采集进度条卡片的视觉样式与主卡片保持一致（相同圆角、阴影），进度条使用 `--color-accent` 颜色

---

### 需求 8：响应式适配保持

**用户故事：** 作为移动端用户，我希望重设计后的界面在移动设备上仍然可用，以便在手机上管理运营账号。

#### 验收标准

1. THE UI_System SHALL 保留现有的移动端卡片列表视图（`isMobile` 判断逻辑），并将卡片样式同步升级为新设计风格
2. WHILE 屏幕宽度小于等于 768px，THE UI_System SHALL 将 Detail_Dialog 和 Form_Dialog 的宽度设为 `95vw`，最大高度设为 `90vh`，并支持内容区域滚动
3. WHILE 屏幕宽度小于等于 768px，THE Filter_Bar SHALL 将操作按钮折叠为仅显示"新增账号"按钮，其余操作通过更多菜单（`el-dropdown`）访问
4. THE UI_System SHALL 保持现有的 `env(safe-area-inset-*)` 安全区域适配逻辑不变

---

### 需求 9：交互动效与过渡

**用户故事：** 作为用户，我希望界面的交互有适度的动效反馈，以便感知操作结果，同时不影响操作效率。

#### 验收标准

1. WHEN Detail_Dialog 或 Form_Dialog 打开，THE UI_System SHALL 使用 `transform: scale(0.96) → scale(1)` 配合 `opacity: 0 → 1` 的入场动画，持续时间为 200ms，缓动函数为 `cubic-bezier(0.16, 1, 0.3, 1)`
2. WHEN 用户悬停在表格行上，THE List_Page SHALL 在 150ms 内完成背景色过渡
3. WHEN Status_Badge 或 Platform_Badge 渲染，THE UI_System SHALL 不使用动画（静态渲染，避免列表滚动时的性能问题）
4. WHEN 采集进度更新，THE List_Page SHALL 使用 Element Plus `el-progress` 的内置过渡动画，不额外添加自定义动画
5. THE UI_System SHALL 确保所有 CSS transition 属性仅作用于 `background-color`、`opacity`、`transform`、`box-shadow` 等合成层属性，避免触发布局重排
