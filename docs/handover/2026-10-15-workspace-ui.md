# 内部工作台界面与协作优化

面向团队日常高频查看、复制、批量处理和修改。基于现有 Vue 3 / Element Plus 实现，沿用 taste-skill 的现有应用审查方法；视觉采用紧凑灰蓝工作台，保留业务流程与权限。

## 本轮改动

- 全局：统一字体、配色、间距、控件焦点、弹窗与表格层次；侧栏选中更清晰，面包屑移入顶栏；分页、日期与确认控件统一中文。
- 表格：显示本页和选中数量，选中行高亮；展开选中、收起详情；按用户和表格记忆紧凑/标准行距。保留排序、筛选、列顺序和列宽。
- 运营账号：单字段、单条和选中账号复制；完整登录资料提供带列头 TSV，可粘贴表格；账号文字可选取，详情入口明确，编辑/关联/采集/记录操作文字可见。
- 邮箱：增加每行一个的选中邮箱复制，保留已有登录资料和交付格式；手机操作列随表格横滚，避免遮住邮箱。
- 节点：单条、批量地址复制，IPv6 使用方括号；批量连接资料 TSV 保留原值并转义特殊字符。
- 设备：选择列、单条名称复制、批量资产概要复制。
- 卡密：当前待消耗记录在列表本行即可复制。
- 备忘：提醒直达并展开目标，重复点击提醒也重新定位；目标已完成或提醒范围变化时明确提示；姓名与账号并列，详情显示创建人和更新时间；支持单条和选中内容复制、提醒我的/全部待处理/已完成快捷视图。
- 成员与部门：筛选回第一页，清空即应用，查询摘要和重置一致；部门保留完整路径，未分配角色明确显示，角色选项展示说明和数据范围；部门编辑上级名称修正，键盘可发现操作入口；快速搜索仅保留最新响应。
- 手机：账号筛选默认收起、展开后两列；操作文字清晰，顶部提醒和退出保留触控区域。

提醒成员仍表示通知对象；本轮未引入单独的任务负责人模型。

## 验证

浏览器使用合成数据，API 请求全部拦截，未知请求作为失败处理。覆盖 1366、1920、390 三种宽度，允许表格内部横滚，检查外层无横向溢出。

在前端开发服务 `http://127.0.0.1:5186` 启动后运行：

```powershell
npm.cmd --prefix frontend run build
node frontend/tests/table-state.cjs
node frontend/tests/table-controls.cjs
node frontend/tests/workspace-efficiency.cjs
node frontend/tests/collaboration-efficiency.cjs
node frontend/tests/email-copy.cjs
node frontend/tests/email-sale.cjs
node frontend/tests/op-account-refresh.cjs
```

上述检查通过，包括复制原值/特殊字符、批量展开、密度记忆与用户隔离、提醒同页/跨页/重复点击、部门筛选回第一页、单次重置请求和旧搜索响应竞争。构建仍提示既有较大 chunk 和 auth store 静态/动态混合导入。

验收截图保存在 `.orchestration/workspace-{emails,accounts,devices,nodes,team,memos}-1366.png`，以及 `.orchestration/workspace-{emails,accounts}-390.png`；内容均为合成数据。

本轮交付为本地源代码，未提交、发布或部署。工作区中原有及并行的后端、导入和文档修改保留。
