<template>
  <div class="monitor-manage">
    <el-alert
      v-if="batchCheckRunning && !progressDialog.visible"
      class="batch-check-background"
      type="info"
      :closable="false"
      show-icon
    >
      <span>批量检查正在后台运行：{{ progressDialog.success + progressDialog.failed }}/{{ progressDialog.total }} 已完成</span>
      <el-button link type="primary" @click="progressDialog.visible = true">查看进度</el-button>
    </el-alert>
      <!-- 项目管理 -->
      <el-dialog v-model="projectManagerVisible" title="项目管理" width="min(1200px, 92vw)" destroy-on-close @open="loadProjects">
        <el-card shadow="never" :body-style="{ padding: '0' }">
          <template #header>
            <div class="card-header">
              <span>项目管理</span>
              <el-button type="primary" @click="handleCreateProject">
                <el-icon><Plus /></el-icon>
                新建项目
              </el-button>
            </div>
          </template>
          <!-- 桌面端表格 -->
          <crm-table table-id="monitor-projects" v-if="!isMobile" :data="projects" v-loading="projectLoading">
            <el-table-column column-key="name" filter-type="text" prop="name" label="项目名称" />
            <el-table-column column-key="description" filter-type="text" prop="description" label="描述" />
            <el-table-column column-key="created_by" filter-type="text" prop="created_by" label="创建人" width="120">
              <template #default="{ row }">{{ row.created_by || '-' }}</template>
            </el-table-column>
            <el-table-column column-key="account_count" filter-type="number" prop="account_count" label="账号数量" width="120" />
            <el-table-column column-key="created_at" filter-type="date" prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column column-key="actions" table-tools-disabled label="操作" width="300" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="handleEditProject(row)">编辑</el-button>
                <el-button link type="primary" @click="viewProjectAccounts(row)">查看账号</el-button>
                <el-button link type="warning" @click="handleProjectMembers(row)">协作成员</el-button>
                <el-button link type="danger" @click="handleDeleteProject(row)">删除</el-button>
              </template>
            </el-table-column>
          </crm-table>
          <!-- 移动端 iOS 卡片列表 -->
          <div v-else class="ios-card-list" v-loading="projectLoading">
            <div v-for="row in projects" :key="row.id" class="ios-card">
              <div class="ios-card-title">{{ row.name }}</div>
              <div class="ios-card-row" v-if="row.description">
                <span class="ios-card-row-label">描述</span>
                <span class="ios-card-row-value">{{ row.description }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">账号数量</span>
                <span class="ios-card-row-value">{{ row.account_count ?? 0 }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">创建人</span>
                <span class="ios-card-row-value">{{ row.created_by || '-' }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">创建时间</span>
                <span class="ios-card-row-value">{{ formatDate(row.created_at) }}</span>
              </div>
              <div class="ios-card-actions">
                <el-button size="small" @click="handleEditProject(row)">编辑</el-button>
                <el-button size="small" type="primary" @click="viewProjectAccounts(row)">查看账号</el-button>
                <el-button size="small" type="warning" @click="handleProjectMembers(row)">协作成员</el-button>
                <el-button size="small" type="danger" @click="handleDeleteProject(row)">删除</el-button>
              </div>
            </div>
            <div v-if="!projects.length" class="ios-empty">暂无项目</div>
          </div>
        </el-card>
      </el-dialog>

      <!-- 账号列表 -->
      <div v-if="!isMobile">
        <el-card shadow="never" :body-style="{ padding: '0' }">
          <template #header>
            <div class="card-header">
              <span>账号列表</span>
              <div class="header-actions">
                <el-button @click="projectManagerVisible = true">项目管理</el-button>
                <el-button v-if="authStore.hasPermission('monitor:proxy')" @click="proxyManagerVisible = true">代理管理</el-button>
                <el-button type="primary" @click="handleCreateAccount">
                  <el-icon><Plus /></el-icon>添加账号
                </el-button>
                <el-button @click="showBatchAddDialog">
                  <el-icon><DocumentAdd /></el-icon>批量添加
                </el-button>
                <el-button @click="showImportDialog">
                  <el-icon><Upload /></el-icon>导入
                </el-button>
                <el-button @click="handleExport">
                  <el-icon><Download /></el-icon>导出
                </el-button>
              </div>
            </div>
          </template>

          <div class="filters">
            <el-select v-model="accountFilters.project_id" placeholder="选择项目" clearable @change="loadAccounts">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-input
              v-model="accountFilters.keyword"
              placeholder="搜索用户名/昵称"
              clearable
              @clear="loadAccounts"
              @keyup.enter="loadAccounts"
              style="width: 250px"
            >
              <template #append>
                <el-button :icon="Search" @click="loadAccounts" />
              </template>
            </el-input>
            <el-select v-model="accountFilters.is_active" placeholder="状态" clearable @change="loadAccounts">
              <el-option label="已激活" :value="true" />
              <el-option label="已禁用" :value="false" />
            </el-select>
          </div>

          <div class="batch-toolbar" v-if="selectedIds.length > 0">
            <span>已选择 {{ selectedIds.length }} 项</span>
            <el-button size="small" @click="batchCheck">批量检查</el-button>
            <el-button size="small" @click="batchEnable">批量启用</el-button>
            <el-button size="small" @click="batchDisable">批量禁用</el-button>
            <el-button size="small" @click="showBatchMoveDialog">批量移动</el-button>
            <el-button size="small" type="danger" @click="batchDelete">批量删除</el-button>
          </div>

          <crm-table table-id="monitor-accounts" remote :query="tableQuery" @query-change="handleTableQuery" ref="accountTable" class="compact-account-table" v-if="!isMobile" :data="accounts" row-key="id" size="small" v-loading="accountLoading" @selection-change="handleSelectionChange" @expand-change="handleAccountExpansion">
            <el-table-column column-key="selection" table-tools-disabled type="selection" width="42" />
            <el-table-column column-key="expand" table-tools-disabled type="expand" width="36">
              <template #default="{ row }">
                <div class="account-expanded" :style="{ width: accountTable?.$el?.clientWidth ? accountTable.$el.clientWidth + 'px' : '100%' }">
                  <el-alert v-if="['not_found', 'failed', 'verification_required', 'partial'].includes(row.latest_check_status)" :title="accountCheckNotice(row).title" :description="accountCheckNotice(row).description" :type="row.latest_check_status === 'not_found' ? 'error' : 'warning'" :closable="false" show-icon />
                  <details v-if="row.latest_check_error"><summary>查看技术原因</summary>{{ row.latest_check_error }}</details>
                  <InlineAccountVideos :account-id="row.id" />
                  <div class="account-detail-grid">
                  <section class="account-profile-panel">
                  <div class="detail-panel-heading">账号资料</div>
                  <el-descriptions :column="3" size="small" border>
                    <el-descriptions-item label="昵称">{{ row.nickname || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="关注 / 点赞 / 视频">{{ formatNumber(row.following_count) }} / {{ formatNumber(row.like_count) }} / {{ row.video_count ?? 0 }}</el-descriptions-item>
                    <el-descriptions-item label="地区 / 注册">{{ row.region || '-' }} / {{ formatShortDate(row.account_created_at) }}</el-descriptions-item>
                    <el-descriptions-item label="TikTok ID">{{ row.tiktok_id || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="UID" :span="2">{{ row.sec_uid || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="简介" :span="3">{{ row.bio || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="代理">{{ row.use_proxy ? '启用' : '关闭' }}</el-descriptions-item>
                    <el-descriptions-item label="视频监控">{{ row.enable_video_monitoring ? '启用' : '关闭' }}</el-descriptions-item>
                    <el-descriptions-item label="视频数据更新">{{ formatDate(row.video_data_updated_at) }}</el-descriptions-item>
                    <el-descriptions-item label="监控间隔">{{ row.monitor_interval / 60 }} 分钟</el-descriptions-item>
                  </el-descriptions>
                  </section>
                  <section class="account-history-panel">
                  <div class="detail-panel-heading">最近检查 <span>粉丝变化对比上次检查，非日增量</span></div>
                  <crm-table table-id="monitor-recent-history" class="check-history-table" :data="recentTrend(row.id)" size="small" height="190" empty-text="暂无历史记录">
                    <el-table-column column-key="checked_at" prop="checked_at" filter-type="date" label="检查时间" min-width="150"><template #default="{ row: point }"><time>{{ formatDate(point.checked_at) }}</time></template></el-table-column>
                    <el-table-column column-key="follower_count" prop="follower_count" filter-type="number" label="粉丝" min-width="64" align="right"><template #default="{ row: point }">{{ formatNumber(point.follower_count) }}</template></el-table-column>
                    <el-table-column column-key="followers_change" prop="followers_change" filter-type="number" label="粉丝变化" min-width="76" align="right"><template #default="{ row: point }"><span :class="deltaClass(point.followers_change)">{{ formatDelta(point.followers_change) }}</span></template></el-table-column>
                    <el-table-column column-key="like_count" prop="like_count" filter-type="number" label="点赞" min-width="68" align="right"><template #default="{ row: point }">{{ formatNumber(point.like_count) }}</template></el-table-column>
                    <el-table-column column-key="video_count" filter-type="number" prop="video_count" label="视频" min-width="52" align="right" />
                  </crm-table>
                  </section>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column column-key="username" prop="username" filter-type="text" :table-fields="[{ prop: 'username', label: '用户名', type: 'text' }, { prop: 'nickname', label: '昵称', type: 'text' }]" label="账号" min-width="250">
              <template #default="{ row }"><div class="compact-account" role="button" tabindex="0" :aria-expanded="expandedAccountIds.includes(row.id)" :aria-label="(expandedAccountIds.includes(row.id) ? '收起' : '展开') + '账号 ' + row.username + '详情'" :title="expandedAccountIds.includes(row.id) ? '点击收起账号详情' : '点击展开账号详情'" @click="toggleAccountExpansion(row)" @keydown.enter.prevent="toggleAccountExpansion(row)" @keydown.space.prevent="toggleAccountExpansion(row)"><el-avatar :src="row.avatar_url" :size="32"><el-icon><User /></el-icon></el-avatar><div><strong>@{{ row.username }}</strong><span>{{ row.nickname || row.username }}</span><div class="account-metrics" aria-label="账号数据"><span title="粉丝数">粉丝 {{ formatNumber(row.follower_count) }}</span><span title="关注数">关注 {{ formatNumber(row.following_count) }}</span><span title="点赞数">赞 {{ formatNumber(row.like_count) }}</span><span title="视频数">视频 {{ formatNumber(row.video_count) }}</span></div></div></div></template>
            </el-table-column>
            <el-table-column column-key="follower_count" prop="follower_count" filter-type="number" label="粉丝数" min-width="110" align="right"><template #default="{ row }"><strong>{{ formatNumber(row.follower_count) }}</strong></template></el-table-column>
            <el-table-column column-key="followers_change" prop="followers_change" filter-type="number" label="较上次变化" min-width="130" align="right"><template #default="{ row }"><span :class="deltaClass(followerDelta(row.id))">{{ formatDelta(followerDelta(row.id)) }}</span></template></el-table-column>
            <el-table-column column-key="follower_trend" table-tools-disabled label="粉丝趋势" width="150"><template #default="{ row }"><div :ref="el => setChartRef('follower_count_' + row.id, el)" class="mini-chart"></div></template></el-table-column>
            <el-table-column column-key="video_count" prop="video_count" filter-type="number" label="视频数量" width="95" align="right"><template #default="{ row }">{{ formatNumber(row.video_count) }}</template></el-table-column>
            <el-table-column column-key="yesterday_video_count" prop="yesterday_video_count" filter-type="number" label="昨日更新（北京时间）" width="175" align="center"><template #default="{ row }"><el-tooltip content="依据已采集视频的发布时间判断，北京时间昨日 00:00–24:00；未发现不等于确认未发布。" placement="top"><el-tag :type="row.yesterday_video_count > 0 ? 'success' : 'info'" size="small">{{ yesterdayVideoLabel(row) }}</el-tag></el-tooltip></template></el-table-column>
            <el-table-column column-key="yesterday_video_plays" prop="yesterday_video_plays" filter-type="number" label="昨日视频流量" min-width="190">
              <template #default="{ row }"><el-tooltip content="北京时间昨日发布视频的最新累计播放量，按发布时间从新到旧逐条展示；不是昨日新增播放量。排序和筛选按这些播放量合计。" placement="top"><span class="yesterday-video-plays">{{ yesterdayVideoPlaysLabel(row) }}</span></el-tooltip></template>
            </el-table-column>
            <el-table-column column-key="project_name" filter-type="text" prop="project_name" label="项目" min-width="110" show-overflow-tooltip />
            <el-table-column column-key="latest_check_status" prop="latest_check_status" filter-type="enum" :filter-options="[{ label: '尚未检查', value: 'pending' }, { label: '资料成功，视频未完成', value: 'partial' }, { label: '成功', value: 'success' }, { label: '失败', value: 'failed' }, { label: '账号不存在', value: 'not_found' }, { label: '验证拦截', value: 'verification_required' }]" label="最近检查" width="125"><template #default="{ row }"><el-tooltip :content="row.latest_check_error || '最近账号检查结果；数据在检查失败时保留历史值。'"><el-tag :type="row.latest_check_status === 'not_found' ? 'danger' : ['failed', 'verification_required', 'partial'].includes(row.latest_check_status) ? 'warning' : row.latest_check_status === 'success' ? 'success' : 'info'" size="small">{{ row.latest_check_status === 'not_found' ? '账号不存在' : row.latest_check_status === 'verification_required' ? '验证拦截' : row.latest_check_status === 'failed' ? '检查失败' : row.latest_check_status === 'partial' ? '视频未完成' : row.latest_check_status === 'success' ? '检查成功' : '尚未检查' }}</el-tag></el-tooltip></template></el-table-column>
            <el-table-column column-key="is_active" prop="is_active" filter-type="enum" :filter-options="[{ label: '启用', value: true }, { label: '禁用', value: false }]" label="监控开关" width="85"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag></template></el-table-column>
            <el-table-column column-key="last_checked_at" prop="last_checked_at" filter-type="date" label="最后检查" width="165"><template #default="{ row }">{{ formatDate(row.last_checked_at) }}</template></el-table-column>
            <el-table-column column-key="actions" table-tools-disabled label="操作" width="175" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="handleCheckAccount(row)">检查</el-button><el-button link type="primary" @click="handleEditAccount(row)">编辑</el-button><el-button link type="danger" @click="handleDeleteAccount(row)">删除</el-button></template></el-table-column>
          </crm-table>

          <!-- 移动端 iOS 卡片列表 -->
          <div v-if="isMobile" class="ios-card-list" v-loading="accountLoading">
            <div v-for="row in accounts" :key="row.id" class="ios-card">
              <div class="ios-card-account-header">
                <el-avatar :src="row.avatar_url" :size="44" v-if="row.avatar_url">
                  <template #error><el-icon><User /></el-icon></template>
                </el-avatar>
                <el-avatar :size="44" v-else><el-icon><User /></el-icon></el-avatar>
                <div class="ios-card-account-info">
                  <span class="ios-card-account-name">@{{ row.username }}</span>
                  <span v-if="row.nickname" class="ios-card-account-nick">{{ row.nickname }}</span>
                </div>
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '激活' : '禁用' }}</el-tag>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">粉丝数</span>
                <span class="ios-card-row-value">{{ formatNumber(row.follower_count) }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">关注数</span>
                <span class="ios-card-row-value">{{ formatNumber(row.following_count) }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">点赞数</span>
                <span class="ios-card-row-value">{{ formatNumber(row.like_count) }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">所属项目</span>
                <span class="ios-card-row-value">{{ row.project_name || '-' }}</span>
              </div>
              <div class="ios-card-actions">
                <el-button size="small" type="primary" @click="viewAccountDetail(row)">详情</el-button>
                <el-button size="small" @click="handleCheckAccount(row)">立即检查</el-button>
                <el-button size="small" @click="handleEditAccount(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDeleteAccount(row)">删除</el-button>
              </div>
            </div>
            <div v-if="!accounts.length" class="ios-empty">暂无账号</div>
          </div>

          <div class="pagination">
            <el-pagination
              v-model:current-page="accountPagination.page"
              v-model:page-size="accountPagination.limit"
              :total="accountPagination.total"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="loadAccounts"
              @size-change="loadAccounts"
            />
          </div>
        </el-card>
      </div>

      <!-- 代理管理 -->
      <el-dialog v-if="authStore.hasPermission('monitor:proxy')" v-model="proxyManagerVisible" title="代理管理" width="min(1200px, 92vw)" destroy-on-close @open="loadProxies">
        <el-card shadow="never" :body-style="{ padding: '0' }">
          <template #header>
            <div class="card-header">
              <span>代理管理</span>
              <div class="header-actions">
                <template v-if="selectedProxies.length > 0">
                  <el-button type="success" @click="handleBatchEnableProxy">
                    <el-icon><Check /></el-icon>批量启用 ({{ selectedProxies.length }})
                  </el-button>
                  <el-button type="warning" @click="handleBatchDisableProxy">
                    <el-icon><Close /></el-icon>批量禁用 ({{ selectedProxies.length }})
                  </el-button>
                  <el-button type="danger" @click="handleBatchDeleteProxy">
                    <el-icon><Delete /></el-icon>批量删除 ({{ selectedProxies.length }})
                  </el-button>
                </template>
                <el-button type="success" @click="handleBatchCreateProxy">
                  <el-icon><Upload /></el-icon>批量导入
                </el-button>
                <el-button type="primary" @click="handleCreateProxy">
                  <el-icon><Plus /></el-icon>添加代理
                </el-button>
              </div>
            </div>
          </template>

          <crm-table table-id="monitor-proxies" v-if="!isMobile" :data="proxies" v-loading="proxyLoading" @selection-change="handleProxySelectionChange">
            <el-table-column column-key="selection" table-tools-disabled type="selection" width="55" />
            <el-table-column column-key="proxy_type" filter-type="enum" :filter-options="[{ label: 'HTTP', value: 'http' }, { label: 'SOCKS5', value: 'socks5' }]" prop="proxy_type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.proxy_type?.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column column-key="host" filter-type="text" prop="host" label="IP" width="150" />
            <el-table-column column-key="port" filter-type="number" prop="port" label="端口" width="100" />
            <el-table-column column-key="username" filter-type="text" prop="username" label="用户名" width="120">
              <template #default="{ row }">{{ row.username || '-' }}</template>
            </el-table-column>
            <el-table-column column-key="password" table-tools-disabled prop="password" filter-type="text" label="密码" width="150">
              <template #default="{ row }">
                <div v-if="row.password" style="display: flex; align-items: center; gap: 8px;">
                  <span>{{ visiblePasswords[row.id] ? row.password : '******' }}</span>
                  <el-icon style="cursor: pointer; color: #409eff;" @click="togglePasswordVisibility(row.id)">
                    <View v-if="!visiblePasswords[row.id]" /><Hide v-else />
                  </el-icon>
                </div>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column column-key="is_active" filter-type="enum" :filter-options="[{ label: '启用', value: true }, { label: '禁用', value: false }]" prop="is_active" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column column-key="last_test_result" filter-type="text" prop="last_test_result" label="测试结果" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.last_test_result" :type="row.last_test_result === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.last_test_result === 'success' ? '成功' : '失败' }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column column-key="last_test_at" filter-type="date" prop="last_test_at" label="最后测试" width="180">
              <template #default="{ row }">{{ formatDate(row.last_test_at) }}</template>
            </el-table-column>
            <el-table-column column-key="actions" table-tools-disabled label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="handleTestProxy(row)" :loading="testingIds.includes(row.id)">测试</el-button>
                <el-button link type="primary" @click="handleEditProxy(row)">编辑</el-button>
                <el-button link type="danger" @click="handleDeleteProxy(row)">删除</el-button>
              </template>
            </el-table-column>
          </crm-table>

          <!-- 移动端 iOS 卡片列表 -->
          <div v-if="isMobile" class="ios-card-list" v-loading="proxyLoading">
            <div v-for="row in proxies" :key="row.id" class="ios-card">
              <div class="ios-card-row">
                <span class="ios-card-row-label">类型</span>
                <span class="ios-card-row-value">
                  <el-tag size="small">{{ row.proxy_type?.toUpperCase() }}</el-tag>
                </span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">地址</span>
                <span class="ios-card-row-value">{{ row.host }}:{{ row.port }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">用户名</span>
                <span class="ios-card-row-value">{{ row.username || '-' }}</span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">状态</span>
                <span class="ios-card-row-value">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
                </span>
              </div>
              <div class="ios-card-row">
                <span class="ios-card-row-label">测试结果</span>
                <span class="ios-card-row-value">
                  <el-tag v-if="row.last_test_result" :type="row.last_test_result === 'success' ? 'success' : 'danger'" size="small">
                    {{ row.last_test_result === 'success' ? '成功' : '失败' }}
                  </el-tag>
                  <span v-else>-</span>
                </span>
              </div>
              <div class="ios-card-actions">
                <el-button size="small" type="primary" @click="handleTestProxy(row)" :loading="testingIds.includes(row.id)">测试</el-button>
                <el-button size="small" @click="handleEditProxy(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDeleteProxy(row)">删除</el-button>
              </div>
            </div>
            <div v-if="!proxies.length" class="ios-empty">暂无代理</div>
          </div>

        </el-card>
      </el-dialog>


    <!-- 移动端账号列表 -->
    <div v-if="isMobile">
      <div class="mobile-section-header">
        <span>账号列表</span>
        <div class="mobile-manager-actions"><el-button size="small" @click="projectManagerVisible = true">项目管理</el-button><el-button v-if="authStore.hasPermission('monitor:proxy')" size="small" @click="proxyManagerVisible = true">代理管理</el-button></div>
        <el-button type="primary" size="small" @click="handleCreateAccount">
          <el-icon><Plus /></el-icon>添加
        </el-button>
      </div>
      <div class="ios-card-list" v-loading="accountLoading">
        <div v-for="row in accounts" :key="row.id" class="ios-card">
          <div class="ios-card-account-header">
            <el-avatar :src="row.avatar_url" :size="44" v-if="row.avatar_url">
              <template #error><el-icon><User /></el-icon></template>
            </el-avatar>
            <el-avatar :size="44" v-else><el-icon><User /></el-icon></el-avatar>
            <div class="ios-card-account-info">
              <span class="ios-card-account-name">@{{ row.username }}</span>
              <span v-if="row.nickname" class="ios-card-account-nick">{{ row.nickname }}</span>
            </div>
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '激活' : '禁用' }}</el-tag>
          </div>
          <div class="ios-card-row">
            <span class="ios-card-row-label">粉丝 / 较上次</span>
            <span class="ios-card-row-value">{{ formatNumber(row.follower_count) }} <span :class="deltaClass(followerDelta(row.id))">{{ formatDelta(followerDelta(row.id)) }}</span></span>
          </div>
          <div class="ios-card-row"><span class="ios-card-row-label">视频数量</span><span class="ios-card-row-value">{{ formatNumber(row.video_count) }}</span></div>
          <div class="ios-card-row"><span class="ios-card-row-label">昨日更新（北京时间）</span><span class="ios-card-row-value">{{ yesterdayVideoLabel(row) }}</span></div>
          <div class="ios-card-row"><span class="ios-card-row-label">昨日视频流量</span><span class="ios-card-row-value">{{ yesterdayVideoPlaysLabel(row) }}</span></div>
          <el-alert v-if="['not_found', 'failed', 'verification_required', 'partial'].includes(row.latest_check_status)" :title="accountCheckNotice(row).title" :description="accountCheckNotice(row).description" :type="row.latest_check_status === 'not_found' ? 'error' : 'warning'" :closable="false" show-icon />
          <div v-if="expandedMobileAccounts.includes(row.id)" class="mobile-account-details">
            <div>项目：{{ row.project_name || '-' }}</div>
            <div>关注 {{ formatNumber(row.following_count) }} · 点赞 {{ formatNumber(row.like_count) }} · 视频 {{ row.video_count ?? 0 }}</div>
            <div>最后检查：{{ formatDate(row.last_checked_at) }}</div>
            <div>简介：{{ row.bio || '-' }}</div>
            <div v-for="point in recentTrend(row.id)" :key="point.checked_at">{{ formatDate(point.checked_at) }} · 粉丝 {{ formatNumber(point.follower_count) }} <span :class="deltaClass(point.followers_change)">{{ formatDelta(point.followers_change) }}</span></div>
            <InlineAccountVideos :account-id="row.id" />
          </div>
          <div class="ios-card-actions">
            <el-button size="small" type="primary" @click="toggleMobileAccount(row.id)">{{ expandedMobileAccounts.includes(row.id) ? '收起' : '展开详情' }}</el-button>
            <el-button size="small" @click="handleCheckAccount(row)">立即检查</el-button>
            <el-button size="small" @click="handleEditAccount(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteAccount(row)">删除</el-button>
          </div>
        </div>
        <div v-if="!accounts.length" class="ios-empty">暂无账号</div>
      </div>
    </div>

    <!-- 移动端代理列表 -->
    <!-- ===== 项目弹窗 ===== -->
    <el-dialog v-model="projectDialogVisible" :title="projectDialogTitle" width="500px">
      <el-form :model="projectForm" :rules="projectRules" ref="projectFormRef" label-width="80px">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="projectForm.name" placeholder="请输入项目名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="projectForm.description" type="textarea" :rows="3" placeholder="请输入项目描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitProject" :loading="projectSubmitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- ===== 协作成员弹窗 ===== -->
    <el-dialog v-model="membersDialogVisible" title="协作成员管理" width="480px" append-to-body>
      <div style="font-size: 13px; color: #909399; margin-bottom: 12px;">
        被添加的成员可查看该项目及其下的监控账号。
      </div>
      <el-select
        v-model="memberUsernames"
        multiple
        filterable
        allow-create
        collapse-tags
        collapse-tags-tooltip
        placeholder="输入或选择用户名"
        style="width: 100%"
        popper-append-to-body
      >
        <el-option
          v-for="u in allTeamMembers"
          :key="u.username"
          :label="u.real_name ? `${u.real_name} (${u.username})` : u.username"
          :value="u.username"
        />
      </el-select>
      <div v-if="memberUsernames.length" style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px;">
        <el-tag
          v-for="name in memberUsernames"
          :key="name"
          closable
          @close="memberUsernames = memberUsernames.filter(n => n !== name)"
        >{{ name }}</el-tag>
      </div>
      <template #footer>
        <el-button @click="membersDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMembersSubmit" :loading="membersSubmitting">保存</el-button>
      </template>
    </el-dialog>

    <!-- ===== 账号相关弹窗 ===== -->
    <BatchAddDialog v-model="batchAddVisible" :projects="projects" @success="loadAccounts" />
    <ImportDialog v-model="importVisible" :projects="projects" @success="loadAccounts" />
    <ExportDialog v-model="exportVisible" :projects="projects" :current-project-id="accountFilters.project_id" />
    <AccountDialog v-model="accountDialogVisible" :projects="projects" :account="editingAccount" @success="loadAccounts" />

    <el-dialog v-model="batchMoveVisible" title="批量移动" width="400px">
      <el-form>
        <el-form-item label="目标项目">
          <el-select v-model="targetProjectId" placeholder="选择目标项目">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchMoveVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmBatchMove">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="progressDialog.visible" title="批量检查进度" width="500px"
      :close-on-click-modal="false" :close-on-press-escape="true" :show-close="true">
      <div class="progress-content">
        <el-progress :percentage="progressDialog.percentage" :status="progressDialog.status" :stroke-width="20" />
        <div class="progress-info">
          <p>总数: {{ progressDialog.total }}</p>
          <p>成功: <span style="color: #67C23A">{{ progressDialog.success }}</span></p>
          <p>失败: <span style="color: #F56C6C">{{ progressDialog.failed }}</span></p>
          <p>进行中: <span style="color: #409EFF">{{ progressDialog.processing }}</span></p>
        </div>
        <div v-if="progressDialog.currentAccount" class="current-account">
          <el-text type="info">正在检查: {{ progressDialog.currentAccount }}</el-text>
        </div>
      </div>
      <template #footer>
        <el-button v-if="!progressDialog.completed" @click="progressDialog.visible = false">后台运行</el-button>
        <el-button v-else type="primary" @click="progressDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- ===== 代理弹窗 ===== -->
    <el-dialog v-model="proxyDialogVisible" :title="proxyDialogTitle" width="500px">
      <el-form :model="proxyForm" :rules="proxyRules" ref="proxyFormRef" label-width="100px">
        <el-form-item label="代理类型" prop="proxy_type">
          <el-select v-model="proxyForm.proxy_type" placeholder="选择代理类型">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>
        <el-form-item label="IP地址" prop="host">
          <el-input v-model="proxyForm.host" placeholder="例如: 127.0.0.1" />
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input-number v-model="proxyForm.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="proxyForm.username" placeholder="可选" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="proxyForm.password" type="password" placeholder="可选" show-password />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="proxyForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="proxyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitProxy" :loading="proxySubmitting">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchProxyDialogVisible" title="批量导入代理" width="600px">
      <el-alert title="格式说明" type="info" :closable="false" style="margin-bottom: 15px">
        <p>每行一个代理，支持以下格式：</p>
        <ul style="margin: 5px 0; padding-left: 20px;">
          <li><code>ip:port</code></li>
          <li><code>ip:port:username:password</code></li>
        </ul>
      </el-alert>
      <el-form :model="batchProxyForm" label-width="100px">
        <el-form-item label="代理类型">
          <el-select v-model="batchProxyForm.proxy_type">
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="SOCKS5" value="socks5" />
          </el-select>
        </el-form-item>
        <el-form-item label="代理列表">
          <el-input v-model="batchProxyForm.proxies_text" type="textarea" :rows="10"
            placeholder="请输入代理列表，每行一个&#10;例如：&#10;192.168.1.1:8080:user1:pass1" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="batchProxyForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchProxyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBatchSubmitProxy" :loading="batchProxySubmitting">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { useTableQuery } from '@/composables/useTableQuery'
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, DocumentAdd, Upload, Download, Search, User, View, Hide, Delete, Check, Close } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getProjects, createProject, updateProject, deleteProject, getProjectMembers, setProjectMembers } from '@/api/projects'
import { getAccounts, deleteAccount, triggerCheck, batchAction } from '@/api/accounts'
import { getAccountTrend } from '@/api/history'
import InlineAccountVideos from '@/components/InlineAccountVideos.vue'
import { getProxies, createProxy, updateProxy, deleteProxy, testProxy, batchCreateProxies } from '@/api/proxies'
import { getMembers } from '@/api/team'
import { useAuthStore } from '@/stores/auth'
import BatchAddDialog from '@/components/BatchAddDialog.vue'
import ImportDialog from '@/components/ImportDialog.vue'
import ExportDialog from '@/components/ExportDialog.vue'
import AccountDialog from '@/components/AccountDialog.vue'

const accountCheckNotice = (row) => {
  if (row.latest_check_status === 'partial') return { title: '账号资料已更新，视频采集未完成', description: row.latest_check_error || '原有视频数据已保留，可稍后重新检查。' }
  if (row.latest_check_status === 'not_found') return { title: '账号已不可访问：TikTok 提示找不到此账号', description: '可能已改名、删除或被平台移除。下方粉丝和视频仅为历史记录，不代表当前数据。' }
  if (row.latest_check_status === 'verification_required') return { title: '检查未完成：TikTok 要求验证', description: '系统暂时无法确认账号是否仍可访问。下方显示历史数据，请打开 TikTok 主页核实或稍后重新检查。' }
  return { title: '检查未完成：未获取到有效账号数据', description: '当前账号状态尚未确认，不能据此判断正常或不存在。下方显示历史数据，请打开 TikTok 主页核实或重新检查。' }
}

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const projectManagerVisible = ref(false)
const proxyManagerVisible = ref(false)

// ===== 响应式断点 =====
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const handleResize = () => { windowWidth.value = window.innerWidth }

// ===== 工具函数 =====
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
const formatShortDate = (dateStr) => {
  if (!dateStr) return '-'
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
const formatNumber = (num) => {
  if (num == null) return '-'
  return num.toLocaleString()
}

// ===== 项目管理 =====
const projects = ref([])
const projectLoading = ref(false)
const projectDialogVisible = ref(false)
const projectSubmitting = ref(false)
const projectFormRef = ref(null)
const editingProjectId = ref(null)
const projectForm = ref({ name: '', description: '' })
const projectRules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { max: 100, message: '项目名称不能超过100个字符', trigger: 'blur' }
  ]
}
const projectDialogTitle = computed(() => editingProjectId.value ? '编辑项目' : '新建项目')

const loadProjects = async () => {
  projectLoading.value = true
  try {
    projects.value = await getProjects()
  } catch (e) {
    console.error(e)
  } finally {
    projectLoading.value = false
  }
}

const handleCreateProject = () => {
  editingProjectId.value = null
  projectForm.value = { name: '', description: '' }
  projectDialogVisible.value = true
}
const handleEditProject = (row) => {
  editingProjectId.value = row.id
  projectForm.value = { name: row.name, description: row.description || '' }
  projectDialogVisible.value = true
}
const handleSubmitProject = async () => {
  const valid = await projectFormRef.value.validate().catch(() => false)
  if (!valid) return
  projectSubmitting.value = true
  try {
    if (editingProjectId.value) {
      await updateProject(editingProjectId.value, projectForm.value)
      ElMessage.success('项目更新成功')
    } else {
      await createProject(projectForm.value)
      ElMessage.success('项目创建成功')
    }
    projectDialogVisible.value = false
    loadProjects()
  } finally {
    projectSubmitting.value = false
  }
}
const handleDeleteProject = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除项目"${row.name}"吗？`, '删除确认', { type: 'warning' })
    await deleteProject(row.id)
    ElMessage.success('项目删除成功')
    loadProjects()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}
const viewProjectAccounts = (row) => {
  accountFilters.value.project_id = row.id
  projectManagerVisible.value = false
  loadAccounts()
}

// ===== 协作成员 =====
const membersDialogVisible = ref(false)
const membersSubmitting = ref(false)
const memberUsernames = ref([])
const allTeamMembers = ref([])
const currentMembersProjectId = ref(null)

const handleProjectMembers = async (row) => {
  currentMembersProjectId.value = row.id
  memberUsernames.value = await getProjectMembers(row.id).catch(() => [])
  if (authStore.hasPermission('team:member:view')) {
    const data = await getMembers({ size: 200 }).catch(() => ({ items: [] }))
    allTeamMembers.value = (data.items || []).filter(u => u.username !== row.created_by)
  } else {
    allTeamMembers.value = []
  }
  membersDialogVisible.value = true
}

const handleMembersSubmit = async () => {
  membersSubmitting.value = true
  try {
    await setProjectMembers(currentMembersProjectId.value, memberUsernames.value)
    ElMessage.success('协作成员已保存')
    membersDialogVisible.value = false
  } finally {
    membersSubmitting.value = false
  }
}

const { tableQuery, queryParams } = useTableQuery('monitor-accounts')
const handleTableQuery = (nextQuery) => { tableQuery.value = nextQuery; accountPagination.value.page = 1; loadAccounts() }

// ===== 账号列表 =====
const accounts = ref([])
const accountLoading = ref(false)
const selectedIds = ref([])
const accountFilters = ref({ project_id: null, keyword: '', is_active: null })
const accountPagination = ref({ page: 1, limit: 50, total: 0 })
const batchAddVisible = ref(false)
const importVisible = ref(false)
const exportVisible = ref(false)
const batchMoveVisible = ref(false)
const targetProjectId = ref(null)
const accountDialogVisible = ref(false)
const editingAccount = ref(null)
const progressDialog = ref({
  visible: false, total: 0, success: 0, failed: 0, processing: 0,
  percentage: 0, status: '', completed: false, currentAccount: ''
})
const batchCheckRunning = ref(false)

const loadAccounts = async () => {
  accountLoading.value = true
  try {
    const params = {
      ...queryParams.value,
      skip: (accountPagination.value.page - 1) * accountPagination.value.limit,
      limit: accountPagination.value.limit
    }
    if (accountFilters.value.project_id) params.project_id = accountFilters.value.project_id
    if (accountFilters.value.keyword) params.keyword = accountFilters.value.keyword
    if (accountFilters.value.is_active !== null) params.is_active = accountFilters.value.is_active
    const data = await getAccounts(params)
    accounts.value = data.items || data
    accountPagination.value.total = data.total ?? data.length
    await nextTick()
    renderAllCharts()
  } catch (e) {
    console.error(e)
  } finally {
    accountLoading.value = false
  }
}

const handleSelectionChange = (sel) => { selectedIds.value = sel.map(i => i.id) }
const handleCreateAccount = () => { editingAccount.value = null; accountDialogVisible.value = true }
const handleEditAccount = (row) => { editingAccount.value = row; accountDialogVisible.value = true }
const viewAccountDetail = (row) => router.push(`/accounts/${row.id}`)
const showBatchAddDialog = () => { batchAddVisible.value = true }
const showImportDialog = () => { importVisible.value = true }
const handleExport = () => { exportVisible.value = true }
const showBatchMoveDialog = () => { targetProjectId.value = null; batchMoveVisible.value = true }

const handleDeleteAccount = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除账号"${row.username}"吗？`, '删除确认', { type: 'warning' })
    await deleteAccount(row.id)
    ElMessage.success('账号删除成功')
    loadAccounts()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}
const handleCheckAccount = async (row) => {
  try {
    await triggerCheck(row.id)
    ElMessage.success('检查任务已触发')
    setTimeout(() => loadAccounts(false), 2000)
  } catch (e) { console.error(e) }
}
const batchEnable = async () => {
  try {
    await batchAction({ action: 'enable', account_ids: selectedIds.value })
    ElMessage.success('批量启用成功')
    loadAccounts()
  } catch (e) { console.error(e) }
}
const batchDisable = async () => {
  try {
    await batchAction({ action: 'disable', account_ids: selectedIds.value })
    ElMessage.success('批量禁用成功')
    loadAccounts()
  } catch (e) { console.error(e) }
}
const batchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedIds.value.length} 个账号吗？`, '批量删除确认', { type: 'warning' })
    await batchAction({ action: 'delete', account_ids: selectedIds.value })
    ElMessage.success('批量删除成功')
    loadAccounts()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}
const confirmBatchMove = async () => {
  if (!targetProjectId.value) { ElMessage.warning('请选择目标项目'); return }
  try {
    await batchAction({ action: 'move', account_ids: selectedIds.value, target_project_id: targetProjectId.value })
    ElMessage.success('批量移动成功')
    batchMoveVisible.value = false
    loadAccounts()
  } catch (e) { console.error(e) }
}
const batchCheck = async () => {
  if (batchCheckRunning.value) {
    ElMessage.info('批量检查正在后台运行')
    return
  }
  try {
    await ElMessageBox.confirm(`确定要立即检查选中的 ${selectedIds.value.length} 个账号吗？`, '批量检查', { type: 'info' })
    progressDialog.value = {
      visible: true, total: selectedIds.value.length, success: 0, failed: 0,
      processing: 0, percentage: 0, status: '', completed: false, currentAccount: ''
    }
    const accountMap = {}
    accounts.value.forEach(a => { accountMap[a.id] = a.username })
    const triggerWithRetry = async (id) => {
      progressDialog.value.processing++
      progressDialog.value.currentAccount = accountMap[id] || `账号${id}`
      try {
        await triggerCheck(id)
        progressDialog.value.success++
        return { success: true }
      } catch (e) {
        progressDialog.value.failed++
        return { success: false }
      } finally {
        progressDialog.value.processing--
        progressDialog.value.percentage = Math.round(((progressDialog.value.success + progressDialog.value.failed) / progressDialog.value.total) * 100)
      }
    }
    batchCheckRunning.value = true
    const ids = [...selectedIds.value]
    const workerCount = Math.min(12, ids.length)
    let cursor = 0
    const results = []
    const worker = async () => {
      while (cursor < ids.length) {
        const id = ids[cursor++]
        results.push(await triggerWithRetry(id))
      }
    }
    await Promise.all(Array.from({ length: workerCount }, worker))
    const failCount = progressDialog.value.failed
    progressDialog.value.completed = true
    progressDialog.value.currentAccount = ''
    progressDialog.value.status = failCount > 0 ? 'warning' : 'success'
    batchCheckRunning.value = false
    ElMessage[failCount > 0 ? 'warning' : 'success'](`已触发 ${results.length - failCount} 个账号检查${failCount > 0 ? `，${failCount} 个失败` : ''}`)
    loadAccounts(false)
  } catch (e) {
    batchCheckRunning.value = false
    if (e !== 'cancel') console.error(e)
  }
}

// ===== 图表 =====
const yesterdayVideoPlaysLabel = (row) => {
  if (!Object.hasOwn(row, 'yesterday_video_plays')) return '接口待更新'
  if (row.yesterday_video_plays == null) return '暂无可靠数据'
  return row.yesterday_video_plays.length ? row.yesterday_video_plays.join(' / ') : '—'
}
const yesterdayVideoLabel = (row) => {
  if (!Object.hasOwn(row, 'yesterday_video_count')) return '接口待更新'
  if (row.yesterday_video_count != null) return row.yesterday_video_count > 0 ? '已更新 ' + row.yesterday_video_count + ' 条' : '未发现更新'
  if (!row.enable_video_monitoring) return '视频监控未启用'
  return row.video_data_updated_at ? '视频数据待刷新' : '尚无视频记录'
}
const accountTable = ref(null)
const expandedAccountIds = ref([])
const handleAccountExpansion = (_row, expandedRows) => { expandedAccountIds.value = expandedRows.map(row => row.id) }
const toggleAccountExpansion = (row) => accountTable.value?.toggleRowExpansion(row)
const accountTrends = ref({})
const expandedMobileAccounts = ref([])
const recentTrend = (accountId) => (accountTrends.value[accountId]?.data_points || [])
  .map((point, index) => ({ ...point, followers_change: index === 0 ? null : point.followers_change }))
  .slice(-10).reverse()
const followerDelta = (accountId) => {
  const points = accountTrends.value[accountId]?.data_points || []
  return points.length > 1 ? points[points.length - 1].follower_count - points[points.length - 2].follower_count : null
}
const formatDelta = (delta) => delta == null ? '暂无对比' : (delta > 0 ? '+' : '') + delta.toLocaleString()
const deltaClass = (delta) => delta > 0 ? 'delta-up' : delta < 0 ? 'delta-down' : 'delta-neutral'
const toggleMobileAccount = (accountId) => {
  expandedMobileAccounts.value = expandedMobileAccounts.value.includes(accountId)
    ? expandedMobileAccounts.value.filter(id => id !== accountId)
    : [...expandedMobileAccounts.value, accountId]
}
const chartRefs = ref({})
const chartInstances = ref({})
const setChartRef = (id, el) => {
  if (chartRefs.value[id] === el) return
  chartInstances.value[id]?.dispose()
  delete chartInstances.value[id]
  if (el) {
    chartRefs.value[id] = el
    const account = accounts.value.find(item => `follower_count_${item.id}` === id)
    if (account && accountTrends.value[account.id]) nextTick(() => renderMiniChartWithData(account, 'follower_count', accountTrends.value[account.id]))
  }
  else delete chartRefs.value[id]
}
let trendGeneration = 0
const renderAllCharts = async () => {
  const generation = ++trendGeneration
  accountTrends.value = {}
  Object.values(chartInstances.value).forEach(chart => chart.dispose())
  chartInstances.value = {}
  for (const account of accounts.value.slice()) {
    let trendData = null
    try {
      trendData = await getAccountTrend(account.id)
    } catch (error) {
      if (generation !== trendGeneration) return
      continue
    }
    if (generation !== trendGeneration) return
    accountTrends.value[account.id] = trendData
    renderMiniChartWithData(account, 'follower_count', trendData)
  }
}
const renderMiniChartWithData = (account, metric, data) => {
  const key = `${metric}_${account.id}`
  const el = chartRefs.value[key]
  if (!el || !data?.data_points?.length) return
  if (chartInstances.value[key]) chartInstances.value[key].dispose()
  const chart = echarts.init(el)
  chartInstances.value[key] = chart
  const colors = {
    follower_count: { line: '#409EFF', area1: 'rgba(64,158,255,0.3)', area2: 'rgba(64,158,255,0.05)' },
    following_count: { line: '#E6A23C', area1: 'rgba(230,162,60,0.3)', area2: 'rgba(230,162,60,0.05)' },
    like_count: { line: '#F56C6C', area1: 'rgba(245,108,108,0.3)', area2: 'rgba(245,108,108,0.05)' },
    video_count: { line: '#67C23A', area1: 'rgba(103,194,58,0.3)', area2: 'rgba(103,194,58,0.05)' }
  }
  const c = colors[metric]
  chart.setOption({
    grid: { left: 5, right: 5, top: 5, bottom: 5 },
    xAxis: { type: 'category', show: false, data: data.data_points.map(p => p.checked_at) },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'line', data: data.data_points.map(p => p[metric]),
      smooth: true, symbol: 'none',
      lineStyle: { width: 2, color: c.line },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: c.area1 }, { offset: 1, color: c.area2 }] } }
    }]
  })
}

// ===== 代理管理 =====
const proxies = ref([])
const proxyLoading = ref(false)
const proxyDialogVisible = ref(false)
const proxySubmitting = ref(false)
const batchProxyDialogVisible = ref(false)
const batchProxySubmitting = ref(false)
const proxyFormRef = ref(null)
const editingProxyId = ref(null)
const testingIds = ref([])
const visiblePasswords = ref({})
const selectedProxies = ref([])
const proxyForm = ref({ proxy_type: 'http', host: '', port: null, username: '', password: '', is_active: true })
const batchProxyForm = ref({ proxies_text: '', proxy_type: 'socks5', is_active: true })
const proxyRules = {
  proxy_type: [{ required: true, message: '请选择代理类型', trigger: 'change' }],
  host: [{ required: true, message: '请输入IP地址', trigger: 'blur' }],
  port: [{ required: true, message: '请输入端口号', trigger: 'blur' }]
}
const proxyDialogTitle = computed(() => editingProxyId.value ? '编辑代理' : '添加代理')

const loadProxies = async () => {
  proxyLoading.value = true
  try {
    proxies.value = await getProxies()
  } catch (e) { console.error(e) }
  finally { proxyLoading.value = false }
}
const handleProxySelectionChange = (sel) => { selectedProxies.value = sel }
const togglePasswordVisibility = (id) => { visiblePasswords.value[id] = !visiblePasswords.value[id] }
const handleCreateProxy = () => {
  editingProxyId.value = null
  proxyForm.value = { proxy_type: 'http', host: '', port: null, username: '', password: '', is_active: true }
  proxyDialogVisible.value = true
}
const handleEditProxy = (row) => {
  editingProxyId.value = row.id
  proxyForm.value = { proxy_type: row.proxy_type, host: row.host, port: row.port, username: row.username || '', password: '', is_active: row.is_active }
  proxyDialogVisible.value = true
}
const handleSubmitProxy = async () => {
  const valid = await proxyFormRef.value.validate().catch(() => false)
  if (!valid) return
  proxySubmitting.value = true
  try {
    const data = { ...proxyForm.value }
    if (!data.username) delete data.username
    if (!data.password) delete data.password
    if (editingProxyId.value) {
      await updateProxy(editingProxyId.value, data)
      ElMessage.success('代理更新成功')
    } else {
      await createProxy(data)
      ElMessage.success('代理创建成功')
    }
    proxyDialogVisible.value = false
    loadProxies()
  } finally { proxySubmitting.value = false }
}
const handleBatchCreateProxy = () => {
  batchProxyForm.value = { proxies_text: '', proxy_type: 'socks5', is_active: true }
  batchProxyDialogVisible.value = true
}
const handleBatchSubmitProxy = async () => {
  if (!batchProxyForm.value.proxies_text.trim()) { ElMessage.warning('请输入代理列表'); return }
  batchProxySubmitting.value = true
  try {
    const result = await batchCreateProxies(batchProxyForm.value)
    if (result.errors?.length > 0) {
      ElMessageBox.alert(result.errors.join('\n'), '导入结果', { type: result.success_count > 0 ? 'warning' : 'error' })
    } else {
      ElMessage.success(`成功导入 ${result.success_count} 个代理`)
    }
    if (result.success_count > 0) { batchProxyDialogVisible.value = false; loadProxies() }
  } finally { batchProxySubmitting.value = false }
}
const handleDeleteProxy = async (row) => {
  const name = row.username ? `${row.username}@${row.host}:${row.port}` : `${row.host}:${row.port}`
  try {
    await ElMessageBox.confirm(`确定要删除代理"${name}"吗？`, '删除确认', { type: 'warning' })
    await deleteProxy(row.id)
    ElMessage.success('代理删除成功')
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleTestProxy = async (row) => {
  testingIds.value.push(row.id)
  try {
    const result = await testProxy(row.id)
    if (result.success) ElMessage.success(`代理测试成功 (响应时间: ${result.response_time}ms)`)
    else ElMessage.error(`代理测试失败: ${result.error}`)
    loadProxies()
  } finally { testingIds.value = testingIds.value.filter(id => id !== row.id) }
}
const handleBatchEnableProxy = async () => {
  try {
    await ElMessageBox.confirm(`确定要启用选中的 ${selectedProxies.value.length} 个代理吗？`, '批量启用', { type: 'warning' })
    let ok = 0, fail = 0
    for (const p of selectedProxies.value) {
      try { await updateProxy(p.id, { is_active: true }); ok++ } catch { fail++ }
    }
    ElMessage.success(`成功启用 ${ok} 个代理${fail > 0 ? `，失败 ${fail} 个` : ''}`)
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleBatchDisableProxy = async () => {
  try {
    await ElMessageBox.confirm(`确定要禁用选中的 ${selectedProxies.value.length} 个代理吗？`, '批量禁用', { type: 'warning' })
    let ok = 0, fail = 0
    for (const p of selectedProxies.value) {
      try { await updateProxy(p.id, { is_active: false }); ok++ } catch { fail++ }
    }
    ElMessage.success(`成功禁用 ${ok} 个代理${fail > 0 ? `，失败 ${fail} 个` : ''}`)
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleBatchDeleteProxy = async () => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedProxies.value.length} 个代理吗？`, '批量删除', { type: 'warning' })
    let ok = 0, fail = 0
    for (const p of selectedProxies.value) {
      try { await deleteProxy(p.id); ok++ } catch { fail++ }
    }
    ElMessage.success(`成功删除 ${ok} 个代理${fail > 0 ? `，失败 ${fail} 个` : ''}`)
    loadProxies()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  // 支持从其他页面跳转带 tab 参数
  if (route.query.tab === 'projects') projectManagerVisible.value = true
  else if (route.query.tab === 'proxies' && authStore.hasPermission('monitor:proxy')) proxyManagerVisible.value = true
  if (route.query.project_id) accountFilters.value.project_id = parseInt(route.query.project_id)
  loadProjects()
  loadAccounts()
})

onUnmounted(() => {
  trendGeneration++
  window.removeEventListener('resize', handleResize)
  Object.values(chartInstances.value).forEach(chart => chart.dispose())
})
</script>

<style scoped>
.mobile-manager-actions { display: flex; gap: 4px; margin-left: auto; }
.monitor-manage :deep(.el-dialog__body) { max-height: 72vh; overflow: auto; }
.monitor-manage {
  padding: 20px;
}

.mobile-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px 4px;
  font-size: 15px;
  font-weight: 600;
  color: #000;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ===== iOS 卡片列表 ===== */
.ios-card-list {
  padding: 8px 12px 12px;
  background: #F2F2F7;
  min-height: 100px;
}

.ios-card {
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 12px;
  overflow: hidden;
}

.ios-card-title {
  padding: 14px 16px 10px;
  font-size: 16px;
  font-weight: 600;
  color: #000;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
}

.ios-card-row {
  display: flex;
  align-items: center;
  padding: 11px 16px;
  min-height: 44px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
}

.ios-card-row:last-of-type {
  border-bottom: none;
}

.ios-card-row-label {
  font-size: 14px;
  color: #8E8E93;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  min-width: 72px;
  flex-shrink: 0;
}

.ios-card-row-value {
  font-size: 14px;
  color: #000000;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  flex: 1;
  text-align: right;
}

.ios-card-actions {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 0.5px solid rgba(0, 0, 0, 0.08);
  background: #FAFAFA;
  flex-wrap: wrap;
}

.ios-card-actions .el-button {
  flex: 1;
  min-height: 34px;
  border-radius: 8px;
  min-width: 60px;
}

/* 账号卡片头部 */
.ios-card-account-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
}

.ios-card-account-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ios-card-account-name {
  font-size: 15px;
  font-weight: 600;
  color: #000;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

.ios-card-account-nick {
  font-size: 13px;
  color: #8E8E93;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ios-empty {
  text-align: center;
  padding: 40px 0;
  color: #8E8E93;
  font-size: 14px;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

/* 移动端布局 */
@media (max-width: 768px) {
  .monitor-manage {
    padding: 0;
  }
}
.card-header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.filters {
  display: flex;
  gap: 10px;
  margin: 16px 0 10px;
  padding: 0 20px;
}
.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  background-color: #f0f2f5;
  margin-bottom: 10px;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  padding: 0 20px 16px;
}
.compact-account { display: flex; align-items: center; gap: 8px; cursor: pointer; border-radius: 4px; }
.compact-account:hover strong { color: var(--el-color-primary); }
.compact-account:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.compact-account > div { min-width: 0; }
.compact-account strong, .compact-account span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compact-account span { font-size: 12px; color: #909399; }
.compact-account .el-avatar { flex-shrink: 0; }
.compact-account .account-metrics { display: flex; flex-wrap: wrap; column-gap: 8px; color: #909399; font-size: 11px; line-height: 16px; }
.compact-account .account-metrics span { display: inline; overflow: visible; text-overflow: clip; white-space: nowrap; font-size: 11px; }
.compact-account-table :deep(.el-table__cell) { padding: 5px 0; }
.account-expanded { box-sizing: border-box; max-width: 100%; padding: 10px 16px 12px; background: #f8fafc; }
.account-expanded :deep(.el-descriptions__content) { overflow-wrap: anywhere; }
.account-detail-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(420px, 0.42fr); gap: 12px; align-items: start; margin-top: 6px; }
.account-profile-panel, .account-history-panel { min-width: 0; overflow: hidden; }
.detail-panel-heading { display: flex; align-items: baseline; gap: 10px; margin-bottom: 5px; font-weight: 600; color: #606266; }
.detail-panel-heading span { font-weight: 400; font-size: 11px; color: #909399; }
.account-profile-panel :deep(.el-descriptions__cell) { padding: 4px 8px !important; font-size: 12px; line-height: 20px; }
.account-profile-panel :deep(.el-descriptions__label) { white-space: nowrap; }
.account-profile-panel :deep(.el-descriptions__body) { height: 190px; overflow: auto; }
.account-profile-panel :deep(.el-descriptions__table) { width: 100%; height: 190px; table-layout: fixed; }
.check-history-table { width: 100%; max-width: 100%; font-variant-numeric: tabular-nums; }
.check-history-table :deep(.el-table__cell) { padding: 2px 0; }
.check-history-table :deep(.cell) { padding: 0 8px; line-height: 22px; }
.check-history-table time { white-space: nowrap; }
@media (max-width: 1200px) {
  .account-detail-grid { grid-template-columns: minmax(0, 1fr); gap: 10px; }
}
.delta-up { color: #169b62; font-weight: 600; }
.delta-down { color: #e5484d; font-weight: 600; }
.delta-neutral { color: #909399; }
.yesterday-video-plays { white-space: normal; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.mobile-account-details { padding: 0 16px 12px; font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }
.stat-value {
  font-size: 14px;
  font-weight: 500;
}
.mini-chart {
  width: 130px;
  height: 28px;
}
.mini-chart-small {
  width: 130px;
  height: 35px;
}
.progress-content {
  padding: 20px 0;
}
.progress-info {
  margin-top: 20px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.progress-info p {
  margin: 0;
  font-size: 14px;
  color: #606266;
}
.current-account {
  margin-top: 15px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
  text-align: center;
}
code {
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}
</style>
