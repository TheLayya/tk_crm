<template>
  <div class="op-account-list">
    <!-- 统计面板 -->
    <div class="stats-panel">
      <div class="stats-grid">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value">{{ accountStats.total }}</div>
          <div class="stat-label">账号总数</div>
        </el-card>
        <el-card class="stat-card stat-card--success" shadow="hover">
          <div class="stat-value">{{ accountStats.by_status?.['正常'] ?? 0 }}</div>
          <div class="stat-label">正常</div>
        </el-card>
        <el-card class="stat-card stat-card--primary" shadow="hover">
          <div class="stat-value">{{ accountStats.by_status?.['自用'] ?? 0 }}</div>
          <div class="stat-label">自用</div>
        </el-card>
        <el-card class="stat-card stat-card--danger" shadow="hover">
          <div class="stat-value">{{ accountStats.by_status?.['封禁'] ?? 0 }}</div>
          <div class="stat-label">封禁</div>
        </el-card>
        <el-card class="stat-card stat-card--info" shadow="hover">
          <div class="stat-value">{{ accountStats.by_status?.['已售'] ?? 0 }}</div>
          <div class="stat-label">已售</div>
        </el-card>
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value">{{ formatCurrency(accountStats.total_purchase_cost) }}</div>
          <div class="stat-label">总采购成本</div>
        </el-card>
        <el-card class="stat-card stat-card--success" shadow="hover">
          <div class="stat-value">{{ formatCurrency(accountStats.total_sale_revenue) }}</div>
          <div class="stat-label">总出售收入</div>
        </el-card>
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value" :class="Number(accountStats.net_profit) >= 0 ? 'stat-value--profit' : 'stat-value--loss'">
            {{ formatCurrency(accountStats.net_profit) }}
          </div>
          <div class="stat-label">净收益</div>
        </el-card>
      </div>
    </div>

    <!-- 过滤栏 -->
    <el-card class="filter-card">
      <div class="filter-row">
        <div class="filter-inputs">
          <el-select v-model="filters.platform" placeholder="平台" clearable @change="handleFilterChange" style="width:120px">
            <el-option label="TikTok" value="tiktok" />
            <el-option label="YouTube" value="youtube" />
            <el-option label="Instagram" value="instagram" />
            <el-option label="Facebook" value="facebook" />
          </el-select>
          <el-select v-if="!isMobile" v-model="filters.status" placeholder="状态" clearable @change="handleFilterChange" style="width:110px">
            <el-option label="正常" value="正常" />
            <el-option label="自用" value="自用" />
            <el-option label="封禁" value="封禁" />
            <el-option label="已售" value="已售" />
          </el-select>
          <el-input v-model="filters.keyword" placeholder="搜索账号/昵称" clearable @clear="handleFilterChange" @keyup.enter="handleFilterChange" style="width:180px">
            <template #append><el-button :icon="Search" @click="handleFilterChange" /></template>
          </el-input>
          <el-input v-if="!isMobile" v-model="filters.purchase_channel" placeholder="采购渠道" clearable @clear="handleFilterChange" @keyup.enter="handleFilterChange" style="width:140px" />
          <el-input v-if="!isMobile" v-model="filters.sale_customer" placeholder="出售客户" clearable @clear="handleFilterChange" @keyup.enter="handleFilterChange" style="width:140px" />
        </div>
        <div class="filter-actions">
          <el-button type="primary" @click="handleCreate"><el-icon><Plus /></el-icon>新增账号</el-button>
          <template v-if="!isMobile">
            <el-button plain @click="showImportDialog = true"><el-icon><Upload /></el-icon>导入</el-button>
            <el-dropdown @command="handleExport">
              <el-button plain><el-icon><Download /></el-icon>导出<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
                  <el-dropdown-item command="xlsx">导出 Excel</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button plain @click="showColumnConfig = true"><el-icon><Setting /></el-icon>列配置</el-button>
          </template>
        </div>
      </div>

      <!-- 批量操作工具栏 -->
      <div class="batch-toolbar-new" v-if="selectedIds.length > 0">
        <span class="batch-toolbar-new__count">已选 {{ selectedIds.length }} 项</span>
        <el-button size="small" type="primary" @click="showBatchStatusDialog = true">批量修改状态</el-button>
        <el-button size="small" @click="handleBatchCollect" :loading="collectLoading">采集</el-button>
        <el-button size="small" type="danger" @click="handleBatchDelete">批量删除</el-button>
      </div>
    </el-card>

    <!-- 采集进度 -->
    <el-card v-if="collectTask.visible" class="collect-progress-card">
      <div class="collect-progress">
        <span>采集进度：{{ collectTask.completed }}/{{ collectTask.total }}</span>
        <el-progress :percentage="collectTask.percentage" :status="collectTask.status" style="flex:1;margin:0 16px" />
        <span style="color:#67C23A">成功 {{ collectTask.success }}</span>
        <span style="color:#F56C6C;margin-left:8px">失败 {{ collectTask.failed }}</span>
        <el-button v-if="collectTask.done" size="small" @click="collectTask.visible=false" style="margin-left:12px">关闭</el-button>
      </div>
    </el-card>

    <!-- 表格 -->
    <el-card>
      <el-table v-if="!isMobile" :data="accounts" v-loading="loading" @selection-change="handleSelectionChange" @row-dblclick="handleRowDblClick" border size="small">
        <el-table-column type="selection" width="40" fixed="left" />
        <el-table-column label="平台" width="100" fixed="left">
          <template #default="{ row }">
            <span :class="['op-platform-badge', `op-platform-badge--${row.platform}`]">{{ row.platform?.toUpperCase() }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账号" min-width="200" fixed="left">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px">
              <el-avatar v-if="row.avatar_url" :src="row.avatar_url" :size="32">
                <template #error>{{ (row.account||'?')[0].toUpperCase() }}</template>
              </el-avatar>
              <el-avatar v-else :size="32">{{ (row.account||'?')[0].toUpperCase() }}</el-avatar>
              <div>
                <div style="font-weight:500">{{ row.account }}</div>
                <div v-if="row.nickname" style="font-size:12px;color:#909399">{{ row.nickname }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <span :class="['op-status-badge', `op-status-badge--${statusKey(row.status)}`]">{{ row.status }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('password')" label="密码" width="120">
          <template #default="{ row }">
            <div class="secret-cell">
              <span>{{ visibleFields[row.id]?.password ? row.password : '••••••' }}</span>
              <el-icon class="eye-icon" @click="toggleVisible(row.id, 'password')">
                <View v-if="!visibleFields[row.id]?.password" /><Hide v-else />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('totp_secret')" label="2FA" width="120">
          <template #default="{ row }">
            <div class="secret-cell">
              <span>{{ visibleFields[row.id]?.totp_secret ? row.totp_secret : (row.totp_secret ? '••••••' : '-') }}</span>
              <el-icon v-if="row.totp_secret" class="eye-icon" @click="toggleVisible(row.id, 'totp_secret')">
                <View v-if="!visibleFields[row.id]?.totp_secret" /><Hide v-else />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('email')" label="绑定邮箱" min-width="160">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('email_password')" label="邮箱密码" width="120">
          <template #default="{ row }">
            <div class="secret-cell">
              <span>{{ visibleFields[row.id]?.email_password ? row.email_password : (row.email_password ? '••••••' : '-') }}</span>
              <el-icon v-if="row.email_password" class="eye-icon" @click="toggleVisible(row.id, 'email_password')">
                <View v-if="!visibleFields[row.id]?.email_password" /><Hide v-else />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('phone')" label="手机号" width="130">
          <template #default="{ row }">{{ row.phone || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('country')" label="国家" width="80">
          <template #default="{ row }">{{ row.country || '-' }}</template>
        </el-table-column>
        <!-- TikTok 专属 -->
        <el-table-column v-if="colVisible('tiktok_perms') && (!filters.platform || filters.platform === 'tiktok')" label="中视频" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.platform==='tiktok'" :type="row.tiktok_mid_video ? 'success' : 'info'" size="small">{{ row.tiktok_mid_video ? '是' : '否' }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('tiktok_perms') && (!filters.platform || filters.platform === 'tiktok')" label="橱窗" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.platform==='tiktok'" :type="row.tiktok_showcase ? 'success' : 'info'" size="small">{{ row.tiktok_showcase ? '是' : '否' }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('tiktok_perms') && (!filters.platform || filters.platform === 'tiktok')" label="手机直播" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.platform==='tiktok'" :type="row.tiktok_phone_live ? 'success' : 'info'" size="small">{{ row.tiktok_phone_live ? '是' : '否' }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('tiktok_perms') && (!filters.platform || filters.platform === 'tiktok')" label="伴侣直播" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.platform==='tiktok'" :type="row.tiktok_partner_live ? 'success' : 'info'" size="small">{{ row.tiktok_partner_live ? '是' : '否' }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <!-- 采集字段 -->
        <el-table-column v-if="colVisible('collected_ids')" label="平台UID" width="160">
          <template #default="{ row }">
            <div style="font-size:11px;line-height:1.6">
              <div v-if="row.platform_user_id"><span style="color:#909399">ID:</span> {{ row.platform_user_id }}</div>
              <div v-if="row.platform_sec_uid">
                <span style="color:#909399">SEC:</span>
                <el-tooltip :content="row.platform_sec_uid" placement="top">
                  <span>{{ row.platform_sec_uid.substring(0, 12) }}...</span>
                </el-tooltip>
              </div>
              <div v-if="!row.platform_user_id && !row.platform_sec_uid" style="color:#C0C4CC">-</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('followers')" label="粉丝数" width="90" align="right">
          <template #default="{ row }">{{ formatNum(row.follower_count) }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('following')" label="关注数" width="80" align="right">
          <template #default="{ row }">{{ formatNum(row.following_count) }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('likes')" label="点赞数" width="90" align="right">
          <template #default="{ row }">{{ formatNum(row.like_count) }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('videos')" label="视频数" width="75" align="right">
          <template #default="{ row }">{{ formatNum(row.video_count) }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('account_created_at')" label="注册时间" width="100">
          <template #default="{ row }">
            <span style="font-size:12px">{{ row.account_created_at ? formatDate(row.account_created_at) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('last_collected_at')" label="最后采集" width="100">
          <template #default="{ row }">
            <span style="font-size:12px">{{ row.last_collected_at ? formatDate(row.last_collected_at) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="colVisible('collect_status')" label="采集状态" width="90">
          <template #default="{ row }">
            <el-tag :type="collectStatusType(row.collect_status)" size="small">{{ collectStatusLabel(row.collect_status) }}</el-tag>
          </template>
        </el-table-column>
        <!-- 采购 -->
        <el-table-column v-if="colVisible('purchase')" label="采购渠道" width="110">
          <template #default="{ row }">{{ row.purchase_channel || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('purchase')" label="采购金额" width="90" align="right">
          <template #default="{ row }">{{ row.purchase_price != null ? '¥'+row.purchase_price : '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('purchase')" label="采购日期" width="100">
          <template #default="{ row }">{{ row.purchase_date || '-' }}</template>
        </el-table-column>
        <!-- 出售 -->
        <el-table-column v-if="colVisible('sale')" label="出售客户" width="110">
          <template #default="{ row }">{{ row.sale_customer || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('sale')" label="出售金额" width="90" align="right">
          <template #default="{ row }">{{ row.sale_price != null ? '¥'+row.sale_price : '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('sale')" label="出售日期" width="100">
          <template #default="{ row }">{{ row.sale_date || '-' }}</template>
        </el-table-column>
        <!-- 人员 -->
        <el-table-column v-if="colVisible('people')" label="注册人" width="90">
          <template #default="{ row }">{{ row.registrant || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('people')" label="使用人" width="90">
          <template #default="{ row }">{{ row.operator || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="colVisible('remark')" label="备注" min-width="120">
          <template #default="{ row }">
            <el-tooltip v-if="row.remark && row.remark.length > 20" :content="row.remark" placement="top">
              <span>{{ row.remark.substring(0, 20) }}...</span>
            </el-tooltip>
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-tooltip content="编辑"><el-button link type="primary" size="small" @click="handleEdit(row)"><el-icon><Edit /></el-icon></el-button></el-tooltip>
            <el-tooltip content="采集"><el-button link type="primary" size="small" @click="handleCollectOne(row)"><el-icon><Refresh /></el-icon></el-button></el-tooltip>
            <el-tooltip content="历史"><el-button link type="primary" size="small" @click="showLogs(row)"><el-icon><Document /></el-icon></el-button></el-tooltip>
            <el-tooltip content="删除"><el-button link type="danger" size="small" @click="handleDelete(row)"><el-icon><Delete /></el-icon></el-button></el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端卡片列表 -->
      <div v-if="isMobile" v-loading="loading" class="ios-card-list">
        <div v-for="row in accounts" :key="row.id" class="ios-card">
          <!-- 卡片头部 -->
          <div class="ios-card-account-header">
            <el-avatar v-if="row.avatar_url" :src="row.avatar_url" :size="40">
              <template #error>{{ (row.account||'?')[0].toUpperCase() }}</template>
            </el-avatar>
            <el-avatar v-else :size="40">{{ (row.account||'?')[0].toUpperCase() }}</el-avatar>
            <div class="ios-card-account-info">
              <div class="ios-card-account-name">{{ row.account }}</div>
              <div v-if="row.nickname" class="ios-card-account-nickname">{{ row.nickname }}</div>
            </div>
            <div class="ios-card-account-tags">
              <span :class="['op-platform-badge', `op-platform-badge--${row.platform}`]">{{ row.platform?.toUpperCase() }}</span>
              <span :class="['op-status-badge', `op-status-badge--${statusKey(row.status)}`]" style="margin-left:4px">{{ row.status }}</span>
            </div>
          </div>
          <!-- 行项 -->
          <div v-if="row.country" class="ios-card-row">
            <span class="ios-card-row-label">国家</span>
            <span class="ios-card-row-value">{{ row.country }}</span>
          </div>
          <div v-if="row.follower_count != null" class="ios-card-row">
            <span class="ios-card-row-label">粉丝数</span>
            <span class="ios-card-row-value">{{ formatNum(row.follower_count) }}</span>
          </div>
          <div v-if="row.following_count != null" class="ios-card-row">
            <span class="ios-card-row-label">关注数</span>
            <span class="ios-card-row-value">{{ formatNum(row.following_count) }}</span>
          </div>
          <div v-if="row.like_count != null" class="ios-card-row">
            <span class="ios-card-row-label">点赞数</span>
            <span class="ios-card-row-value">{{ formatNum(row.like_count) }}</span>
          </div>
          <div v-if="row.purchase_channel" class="ios-card-row">
            <span class="ios-card-row-label">采购渠道</span>
            <span class="ios-card-row-value">{{ row.purchase_channel }}</span>
          </div>
          <div v-if="row.sale_customer" class="ios-card-row">
            <span class="ios-card-row-label">出售客户</span>
            <span class="ios-card-row-value">{{ row.sale_customer }}</span>
          </div>
          <!-- 操作区 -->
          <div class="ios-card-actions">
            <el-tooltip content="编辑"><el-button link type="primary" size="small" @click="handleEdit(row)"><el-icon><Edit /></el-icon></el-button></el-tooltip>
            <el-tooltip content="采集"><el-button link type="primary" size="small" @click="handleCollectOne(row)"><el-icon><Refresh /></el-icon></el-button></el-tooltip>
            <el-tooltip content="历史"><el-button link type="primary" size="small" @click="showLogs(row)"><el-icon><Document /></el-icon></el-button></el-tooltip>
            <el-tooltip content="删除"><el-button link type="danger" size="small" @click="handleDelete(row)"><el-icon><Delete /></el-icon></el-button></el-tooltip>
          </div>
        </div>
        <el-empty v-if="!loading && accounts.length === 0" description="暂无数据" />
      </div>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.limit"
          :total="pagination.total"
          :page-sizes="[20, 50, 100, 200]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadAccounts"
          @size-change="() => { pagination.page = 1; loadAccounts() }"
        />
      </div>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="formDialog.visible" :title="formDialog.isEdit ? `编辑账号` : '新增账号'" width="720px" top="5vh">
      <template #header>
        <span>{{ formDialog.isEdit ? '编辑账号' : '新增账号' }}</span>
        <span v-if="formDialog.isEdit && form.account" style="font-size:14px;color:var(--color-text-muted);margin-left:8px">{{ form.account }}</span>
      </template>
      <el-form :model="form" ref="formRef" label-width="90px" size="default">
        <div class="form-section-title">基础信息</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="平台" prop="platform" :rules="[{required:true,message:'请选择平台'}]">
              <el-select v-model="form.platform" style="width:100%">
                <el-option label="TikTok" value="tiktok" />
                <el-option label="YouTube" value="youtube" />
                <el-option label="Instagram" value="instagram" />
                <el-option label="Facebook" value="facebook" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="账号" prop="account" :rules="[{required:true,message:'请输入账号'}]">
              <el-input v-model="form.account" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width:100%">
                <el-option label="正常" value="正常" />
                <el-option label="自用" value="自用" />
                <el-option label="封禁" value="封禁" />
                <el-option label="已售" value="已售" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="国家/地区" prop="country" :rules="[{required:true,message:'请输入国家/地区',trigger:'blur'}]"><el-input v-model="form.country" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="账号来源">
              <el-select v-model="form.source" clearable style="width:100%">
                <el-option label="自注册" value="self_register" />
                <el-option label="采购" value="purchase" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <div class="form-section-title">账号凭证</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="2FA密钥"><el-input v-model="form.totp_secret" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="绑定邮箱"><el-input v-model="form.email" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱密码"><el-input v-model="form.email_password" show-password /></el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="邮箱登录地址"><el-input v-model="form.email_login_url" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="绑定手机"><el-input v-model="form.phone" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机管理链接"><el-input v-model="form.phone_manage_url" /></el-form-item>
          </el-col>
        </el-row>

        <template v-if="form.platform === 'tiktok'">
          <div class="form-section-title">TikTok 权限</div>
          <div class="tiktok-switch-grid">
            <el-form-item label="中视频"><el-switch v-model="form.tiktok_mid_video" /></el-form-item>
            <el-form-item label="橱窗"><el-switch v-model="form.tiktok_showcase" /></el-form-item>
            <el-form-item label="手机直播"><el-switch v-model="form.tiktok_phone_live" /></el-form-item>
            <el-form-item label="伴侣直播"><el-switch v-model="form.tiktok_partner_live" /></el-form-item>
          </div>
        </template>

        <div class="form-section-title">采购信息</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="采购渠道"><el-input v-model="form.purchase_channel" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="采购金额"><el-input-number v-model="form.purchase_price" :precision="2" :min="0" style="width:100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="采购日期"><el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
          </el-col>
        </el-row>

        <div class="form-section-title">出售信息</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="出售客户"><el-input v-model="form.sale_customer" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="出售金额"><el-input-number v-model="form.sale_price" :precision="2" :min="0" style="width:100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="出售日期"><el-date-picker v-model="form.sale_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
          </el-col>
        </el-row>

        <div class="form-section-title">其他</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="注册人">
              <el-select
                v-model="form.registrant"
                filterable
                allow-create
                clearable
                placeholder="选择或输入注册人"
                style="width:100%"
              >
                <el-option v-for="m in teamMembers" :key="m.username" :label="m.real_name ? `${m.real_name}(${m.username})` : m.username" :value="m.username" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="使用人">
              <el-select
                v-model="form.operator"
                filterable
                allow-create
                clearable
                placeholder="选择或输入使用人"
                style="width:100%"
              >
                <el-option v-for="m in teamMembers" :key="m.username" :label="m.real_name ? `${m.real_name}(${m.username})` : m.username" :value="m.username" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button style="min-width:80px" @click="formDialog.visible = false">取消</el-button>
        <el-button style="min-width:80px" type="primary" @click="handleSubmit" :loading="formDialog.loading">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量修改状态对话框 -->
    <el-dialog v-model="showBatchStatusDialog" title="批量修改状态" width="420px">
      <el-form label-width="90px">
        <el-form-item label="目标状态">
          <el-select v-model="batchStatus.status" style="width:100%">
            <el-option label="正常" value="正常" />
            <el-option label="自用" value="自用" />
            <el-option label="封禁" value="封禁" />
            <el-option label="已售" value="已售" />
          </el-select>
        </el-form-item>
        <template v-if="batchStatus.status === '已售'">
          <el-form-item label="出售客户"><el-input v-model="batchStatus.sale_customer" /></el-form-item>
          <el-form-item label="出售金额"><el-input-number v-model="batchStatus.sale_price" :precision="2" :min="0" style="width:100%" /></el-form-item>
          <el-form-item label="出售日期"><el-date-picker v-model="batchStatus.sale_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showBatchStatusDialog = false">取消</el-button>
        <el-button type="primary" @click="handleBatchStatus" :loading="batchStatus.loading">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 -->
    <el-dialog v-model="showImportDialog" title="批量导入账号" width="560px">
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        <p>上传 CSV 文件，必填列：<strong>account</strong>、<strong>platform</strong>（tiktok/youtube/instagram/facebook）</p>
        <p>可选列：password, totp_secret, email, email_password, phone, country, status, registrant, operator, purchase_channel, purchase_price, purchase_date, sale_customer, sale_price, sale_date, remark</p>
      </el-alert>
      <el-form label-width="80px">
        <el-form-item label="CSV文件">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" accept=".csv" :on-change="handleFileChange" :file-list="importForm.fileList">
            <el-button type="primary">选择文件</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <div v-if="importResult" class="import-result">
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="总计">{{ importResult.total }}</el-descriptions-item>
          <el-descriptions-item label="成功"><span style="color:#67C23A">{{ importResult.success }}</span></el-descriptions-item>
          <el-descriptions-item label="重复"><span style="color:#E6A23C">{{ importResult.duplicates }}</span></el-descriptions-item>
          <el-descriptions-item label="失败"><span style="color:#F56C6C">{{ importResult.failed }}</span></el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button @click="showImportDialog = false; importResult = null">关闭</el-button>
        <el-button type="primary" @click="handleImport" :loading="importForm.loading">导入</el-button>
      </template>
    </el-dialog>

    <!-- 列配置对话框 -->
    <el-dialog v-model="showColumnConfig" title="列显示配置" width="400px">
      <el-checkbox-group v-model="visibleColumns">
        <div v-for="col in columnOptions" :key="col.key" style="margin-bottom:8px">
          <el-checkbox :label="col.key">{{ col.label }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="showColumnConfig = false">关闭</el-button>
        <el-button type="primary" @click="saveColumnConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 账号详情对话框 -->
    <el-dialog v-model="detailDialog.visible" width="680px" top="5vh" class="op-detail-dialog" :show-close="true">
      <template v-if="detailDialog.row">
        <!-- Hero 区域 -->
        <div class="detail-hero">
          <el-avatar :src="detailDialog.row.avatar_url" :size="64" class="detail-hero__avatar">
            {{ (detailDialog.row.account||'?')[0].toUpperCase() }}
          </el-avatar>
          <div class="detail-hero__info">
            <h2 class="detail-hero__name">{{ detailDialog.row.account }}</h2>
            <p v-if="detailDialog.row.nickname" class="detail-hero__nickname">{{ detailDialog.row.nickname }}</p>
            <div class="detail-hero__badges">
              <span :class="['op-platform-badge', `op-platform-badge--${detailDialog.row.platform}`]">{{ detailDialog.row.platform?.toUpperCase() }}</span>
              <span :class="['op-status-badge', `op-status-badge--${statusKey(detailDialog.row.status)}`]">{{ detailDialog.row.status }}</span>
            </div>
          </div>
        </div>

        <!-- 数据概览 -->
        <div class="section-group">
          <div class="section-group__title">数据概览</div>
          <div class="stats-grid">
            <div class="stat-item"><div class="stat-item__value">{{ formatNum(detailDialog.row.follower_count) }}</div><div class="stat-item__label">粉丝数</div></div>
            <div class="stat-item"><div class="stat-item__value">{{ formatNum(detailDialog.row.following_count) }}</div><div class="stat-item__label">关注数</div></div>
            <div class="stat-item"><div class="stat-item__value">{{ formatNum(detailDialog.row.like_count) }}</div><div class="stat-item__label">点赞数</div></div>
            <div class="stat-item"><div class="stat-item__value">{{ formatNum(detailDialog.row.video_count) }}</div><div class="stat-item__label">视频数</div></div>
          </div>
        </div>

        <!-- 账号凭证 -->
        <div class="section-group">
          <div class="section-group__title">账号凭证</div>
          <div class="section-group__body">
            <div class="info-row" v-for="field in credentialFields" :key="field.key">
              <span class="info-row__label">{{ field.label }}</span>
              <span class="info-row__value">
                <template v-if="field.sensitive">
                  <span class="sensitive-text">
                    {{ visibleFields[detailDialog.row.id]?.[field.key]
                       ? detailDialog.row[field.key]
                       : (detailDialog.row[field.key] ? '••••••' : '-') }}
                  </span>
                  <el-icon
                    v-if="detailDialog.row[field.key]"
                    class="eye-btn"
                    @click="toggleVisible(detailDialog.row.id, field.key)"
                  >
                    <View v-if="!visibleFields[detailDialog.row.id]?.[field.key]" />
                    <Hide v-else />
                  </el-icon>
                </template>
                <template v-else>
                  {{ detailDialog.row[field.key] || '-' }}
                </template>
              </span>
            </div>
          </div>
        </div>

        <!-- TikTok 权限（条件显示） -->
        <div v-if="detailDialog.row.platform === 'tiktok'" class="section-group">
          <div class="section-group__title">TikTok 权限</div>
          <div class="tiktok-perms-grid">
            <div class="perm-item" v-for="perm in tiktokPerms" :key="perm.key">
              <span class="perm-item__icon" :class="detailDialog.row[perm.key] ? 'is-on' : 'is-off'">
                {{ detailDialog.row[perm.key] ? '✓' : '✗' }}
              </span>
              <span class="perm-item__label">{{ perm.label }}</span>
            </div>
          </div>
        </div>

        <!-- 采购 / 出售 -->
        <div class="section-group">
          <div class="section-group__title">采购 / 出售</div>
          <div class="section-group__body two-col">
            <div class="info-row"><span class="info-row__label">采购渠道</span><span class="info-row__value">{{ detailDialog.row.purchase_channel || '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">采购金额</span><span class="info-row__value">{{ detailDialog.row.purchase_price != null ? '¥' + detailDialog.row.purchase_price : '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">采购日期</span><span class="info-row__value">{{ detailDialog.row.purchase_date || '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">出售客户</span><span class="info-row__value">{{ detailDialog.row.sale_customer || '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">出售金额</span><span class="info-row__value">{{ detailDialog.row.sale_price != null ? '¥' + detailDialog.row.sale_price : '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">出售日期</span><span class="info-row__value">{{ detailDialog.row.sale_date || '-' }}</span></div>
          </div>
        </div>

        <!-- 其他信息 -->
        <div class="section-group">
          <div class="section-group__title">其他信息</div>
          <div class="section-group__body">
            <div class="info-row"><span class="info-row__label">注册人</span><span class="info-row__value">{{ detailDialog.row.registrant || '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">使用人</span><span class="info-row__value">{{ detailDialog.row.operator || '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">账号来源</span><span class="info-row__value">{{ detailDialog.row.source || '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">注册时间</span><span class="info-row__value">{{ detailDialog.row.account_created_at ? formatDate(detailDialog.row.account_created_at) : '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">最后采集</span><span class="info-row__value">{{ detailDialog.row.last_collected_at ? formatDate(detailDialog.row.last_collected_at) : '-' }}</span></div>
            <div class="info-row"><span class="info-row__label">采集状态</span><span class="info-row__value">{{ collectStatusLabel(detailDialog.row.collect_status) }}</span></div>
            <div class="info-row info-row--full"><span class="info-row__label">备注</span><span class="info-row__value">{{ detailDialog.row.remark || '-' }}</span></div>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="detailDialog.visible = false">关闭</el-button>
        <el-button type="primary" @click="() => { detailDialog.visible = false; handleEdit(detailDialog.row) }">编辑</el-button>
      </template>
    </el-dialog>

    <!-- 操作历史对话框 -->
    <el-dialog v-model="logsDialog.visible" :title="`操作历史 - ${logsDialog.account}`" width="600px">
      <el-timeline v-if="logsDialog.logs.length > 0">
        <el-timeline-item v-for="log in logsDialog.logs" :key="log.id" :timestamp="formatDate(log.created_at)" placement="top">
          <el-card shadow="never" style="padding:8px">
            <el-tag size="small" :type="log.action === 'create' ? 'success' : log.action === 'delete' ? 'danger' : 'warning'">{{ log.action }}</el-tag>
            <span v-if="log.field_name" style="margin-left:8px;font-size:13px">
              <strong>{{ log.field_name }}</strong>：{{ log.old_value || '(空)' }} → {{ log.new_value || '(空)' }}
            </span>
          </el-card>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无操作记录" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Download, Search, Setting, ArrowDown, View, Hide, Edit, Delete, Refresh, Document } from '@element-plus/icons-vue'
import {
  listOpAccounts, createOpAccount, updateOpAccount, deleteOpAccount,
  batchUpdateStatus, importOpAccounts, exportOpAccounts,
  triggerCollect, getCollectTask, getAuditLogs, getOpAccountStats
} from '@/api/op_accounts'
import { getMembers } from '@/api/team'
import { useAuthStore } from '@/stores/auth'

// ===== 统计数据 =====
const accountStats = ref({
  total: 0,
  by_status: { '正常': 0, '自用': 0, '封禁': 0, '已售': 0 },
  by_platform: {},
  total_purchase_cost: 0,
  total_sale_revenue: 0,
  net_profit: 0,
})
const loadStats = async () => {
  try {
    accountStats.value = await getOpAccountStats()
  } catch (e) { console.error(e) }
}

// ===== 数据 =====
const accounts = ref([])
const loading = ref(false)
const selectedIds = ref([])
const teamMembers = ref([])
const selectedRows = ref([])
const visibleFields = ref({})

// ===== Badge 映射 =====
const STATUS_KEY_MAP = { '正常': 'normal', '自用': 'self', '封禁': 'banned', '已售': 'sold' }
const statusKey = (s) => STATUS_KEY_MAP[s] || 'normal'

// ===== 详情弹窗配置 =====
const credentialFields = [
  { key: 'password', label: '密码', sensitive: true },
  { key: 'totp_secret', label: '2FA密钥', sensitive: true },
  { key: 'email', label: '绑定邮箱', sensitive: false },
  { key: 'email_password', label: '邮箱密码', sensitive: true },
  { key: 'email_login_url', label: '邮箱登录地址', sensitive: false },
  { key: 'phone', label: '绑定手机', sensitive: false },
  { key: 'phone_manage_url', label: '手机管理链接', sensitive: false },
]
const tiktokPerms = [
  { key: 'tiktok_mid_video', label: '中视频' },
  { key: 'tiktok_showcase', label: '橱窗' },
  { key: 'tiktok_phone_live', label: '手机直播' },
  { key: 'tiktok_partner_live', label: '伴侣直播' },
]

const filters = reactive({
  platform: null, status: null,
  keyword: '', purchase_channel: '', sale_customer: ''
})
const pagination = reactive({ page: 1, limit: 50, total: 0 })

// ===== 列配置 =====
const COLUMN_CONFIG_KEY = 'op_accounts_column_config'
const columnOptions = [
  { key: 'password', label: '密码' },
  { key: 'totp_secret', label: '2FA密钥' },
  { key: 'email', label: '绑定邮箱' },
  { key: 'email_password', label: '邮箱密码' },
  { key: 'phone', label: '手机号' },
  { key: 'country', label: '国家/地区' },
  { key: 'tiktok_perms', label: 'TikTok权限' },
  { key: 'collected_ids', label: '平台UID/SEC' },
  { key: 'followers', label: '粉丝数' },
  { key: 'following', label: '关注数' },
  { key: 'likes', label: '点赞数' },
  { key: 'videos', label: '视频数' },
  { key: 'account_created_at', label: '账号注册时间' },
  { key: 'last_collected_at', label: '最后采集时间' },
  { key: 'collect_status', label: '采集状态' },
  { key: 'purchase', label: '采购信息' },
  { key: 'sale', label: '出售信息' },
  { key: 'people', label: '注册人/使用人' },
  { key: 'remark', label: '备注' },
]
const defaultColumns = ['password', 'email', 'phone', 'country', 'collected_ids', 'followers', 'collect_status', 'purchase', 'sale', 'people', 'remark']
const visibleColumns = ref(
  JSON.parse(localStorage.getItem(COLUMN_CONFIG_KEY) || 'null') || defaultColumns
)
const showColumnConfig = ref(false)
const colVisible = (key) => visibleColumns.value.includes(key)
const saveColumnConfig = () => {
  localStorage.setItem(COLUMN_CONFIG_KEY, JSON.stringify(visibleColumns.value))
  showColumnConfig.value = false
  ElMessage.success('列配置已保存')
}

// ===== 加载数据 =====
const loadAccounts = async () => {
  loading.value = true
  try {
    const params = {
      skip: (pagination.page - 1) * pagination.limit,
      limit: pagination.limit,
    }
    if (filters.platform) params.platform = filters.platform
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.purchase_channel) params.purchase_channel = filters.purchase_channel
    if (filters.sale_customer) params.sale_customer = filters.sale_customer
    const data = await listOpAccounts(params)
    accounts.value = data.items || data
    pagination.total = data.total ?? data.length
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}
const handleFilterChange = () => { pagination.page = 1; loadAccounts() }
const handleSelectionChange = (rows) => {
  selectedRows.value = rows
  selectedIds.value = rows.map(r => r.id)
}

// ===== 密码显示切换 =====
const toggleVisible = (rowId, field) => {
  if (!visibleFields.value[rowId]) visibleFields.value[rowId] = {}
  visibleFields.value[rowId][field] = !visibleFields.value[rowId][field]
}

// ===== 格式化 =====
const formatNum = (n) => n == null ? '-' : n.toLocaleString()
const formatCurrency = (val) => {
  if (val == null) return '¥0.00'
  return `¥${Number(val).toFixed(2)}`
}
const formatDate = (s) => {
  if (!s) return '-'
  const d = s.endsWith('Z') ? s : s + 'Z'
  return new Date(d).toLocaleString('zh-CN')
}
const platformTagType = (p) => ({ tiktok: '', youtube: 'danger', instagram: 'warning', facebook: 'success' }[p] || 'info')
const statusTagType = (s) => ({ '正常': 'success', '自用': '', '封禁': 'danger', '已售': 'info' }[s] || 'info')
const collectStatusType = (s) => ({ success: 'success', failed: 'danger', pending: 'info', unsupported: 'warning' }[s] || 'info')
const collectStatusLabel = (s) => ({ success: '成功', failed: '失败', pending: '待采集', unsupported: '不支持' }[s] || s)

// ===== 新增/编辑 =====
const formRef = ref(null)
const formDialog = reactive({ visible: false, isEdit: false, loading: false })
const emptyForm = () => ({
  platform: 'tiktok', account: '', password: '', totp_secret: '',
  email: '', email_password: '', email_login_url: '', phone: '', phone_manage_url: '',
  country: '', source: null, tags: '', remark: '', status: '正常', registrant: '', operator: '',
  tiktok_mid_video: false, tiktok_showcase: false, tiktok_phone_live: false, tiktok_partner_live: false,
  purchase_channel: '', purchase_price: null, purchase_date: null,
  sale_customer: '', sale_price: null, sale_date: null,
})
const form = ref(emptyForm())
const editingId = ref(null)
const detailDialog = ref({ visible: false, row: null })

const handleCreate = () => {
  editingId.value = null
  form.value = emptyForm()
  formDialog.isEdit = false
  formDialog.visible = true
}
const handleRowDblClick = (row) => {
  detailDialog.value = { visible: true, row }
}
const handleEdit = (row) => {
  editingId.value = row.id
  form.value = { ...emptyForm(), ...row }
  formDialog.isEdit = true
  formDialog.visible = true
}
const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  formDialog.loading = true
  try {
    if (editingId.value) {
      await updateOpAccount(editingId.value, form.value)
      ElMessage.success('更新成功')
    } else {
      await createOpAccount(form.value)
      ElMessage.success('创建成功，已触发信息采集')
    }
    formDialog.visible = false
    loadAccounts()
  } catch (e) { console.error(e) }
  finally { formDialog.loading = false }
}

// ===== 删除 =====
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除账号 "${row.account}" 吗？`, '删除确认', { type: 'warning' })
    await deleteOpAccount(row.id)
    ElMessage.success('删除成功')
    loadAccounts()
    loadStats()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个账号吗？`, '批量删除', { type: 'warning' })
    await Promise.all(selectedIds.value.map(id => deleteOpAccount(id)))
    ElMessage.success('批量删除成功')
    loadAccounts()
    loadStats()
  } catch (e) { if (e !== 'cancel') console.error(e) }
}

// ===== 批量修改状态 =====
const showBatchStatusDialog = ref(false)
const batchStatus = reactive({ status: '正常', sale_customer: '', sale_price: null, sale_date: null, loading: false })
const handleBatchStatus = async () => {
  batchStatus.loading = true
  try {
    await batchUpdateStatus({
      ids: selectedIds.value,
      status: batchStatus.status,
      sale_customer: batchStatus.sale_customer || null,
      sale_price: batchStatus.sale_price || null,
      sale_date: batchStatus.sale_date || null,
    })
    ElMessage.success('批量修改状态成功')
    showBatchStatusDialog.value = false
    loadAccounts()
    loadStats()
  } catch (e) { console.error(e) }
  finally { batchStatus.loading = false }
}

// ===== 导出 =====
const handleExport = async (format) => {
  try {
    const params = {}
    if (filters.platform) params.platform = filters.platform
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.purchase_channel) params.purchase_channel = filters.purchase_channel
    if (filters.sale_customer) params.sale_customer = filters.sale_customer
    const blob = await exportOpAccounts(params, format)
    const url = URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = `op_accounts.${format}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) { console.error(e) }
}

// ===== 导入 =====
const showImportDialog = ref(false)
const importResult = ref(null)
const importForm = reactive({ fileList: [], file: null, loading: false })
const handleFileChange = (file) => { importForm.file = file.raw }
const handleImport = async () => {
  if (!importForm.file) { ElMessage.warning('请选择CSV文件'); return }
  importForm.loading = true
  try {
    const fd = new FormData()
    fd.append('file', importForm.file)
    importResult.value = await importOpAccounts(fd)
    ElMessage.success(`导入完成：成功 ${importResult.value.success}，重复 ${importResult.value.duplicates}，失败 ${importResult.value.failed}`)
    loadAccounts()
  } catch (e) { console.error(e) }
  finally { importForm.loading = false }
}

// ===== 采集 =====
const collectLoading = ref(false)
const collectTask = reactive({ visible: false, total: 0, completed: 0, success: 0, failed: 0, percentage: 0, status: '', done: false })
let collectPollTimer = null

const startCollect = async (ids) => {
  collectLoading.value = true
  try {
    const res = await triggerCollect(ids)
    const taskId = res.task_id
    Object.assign(collectTask, { visible: true, total: ids.length, completed: 0, success: 0, failed: 0, percentage: 0, status: '', done: false })
    if (collectPollTimer) clearInterval(collectPollTimer)
    collectPollTimer = setInterval(async () => {
      try {
        const t = await getCollectTask(taskId)
        collectTask.completed = t.completed
        collectTask.success = t.success
        collectTask.failed = t.failed
        collectTask.percentage = t.total > 0 ? Math.round((t.completed / t.total) * 100) : 0
        if (t.status === 'completed' || t.status === 'failed') {
          clearInterval(collectPollTimer)
          collectTask.done = true
          collectTask.status = t.failed > 0 ? 'warning' : 'success'
          loadAccounts()
        }
      } catch (e) { clearInterval(collectPollTimer) }
    }, 2000)
  } catch (e) { console.error(e) }
  finally { collectLoading.value = false }
}
const handleBatchCollect = () => startCollect(selectedIds.value)
const handleCollectOne = (row) => startCollect([row.id])

// ===== 操作历史 =====
const logsDialog = reactive({ visible: false, account: '', logs: [] })
const showLogs = async (row) => {
  try {
    const logs = await getAuditLogs(row.id)
    logsDialog.account = row.account
    logsDialog.logs = logs
    logsDialog.visible = true
  } catch (e) { console.error(e) }
}

// ===== 响应式断点 =====
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const handleResize = () => { windowWidth.value = window.innerWidth }

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadAccounts()
  loadStats()
  const authStore = useAuthStore()
  if (authStore.hasPermission('team:member:view')) {
    getMembers({ size: 200 }).then(data => {
      teamMembers.value = data.items || []
    }).catch(() => {})
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.op-account-list {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  background: var(--color-bg-page);
  min-height: 100%;
}

/* ===== 统计面板 ===== */
.stats-panel {
  margin-bottom: 4px;
}

.stats-panel > .stats-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 12px;
}

@media (max-width: 1024px) {
  .stats-panel > .stats-grid { grid-template-columns: repeat(4, 1fr); }
}

@media (max-width: 767px) {
  .stats-panel > .stats-grid { grid-template-columns: repeat(4, 1fr); }
}

.stat-card {
  text-align: center;
  cursor: default;
  height: 100%;
}
.stat-card :deep(.el-card__body) {
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 72px;
}
.stat-card--success { border-top: 3px solid #67c23a; }
.stat-card--primary { border-top: 3px solid #409eff; }
.stat-card--warning { border-top: 3px solid #e6a23c; }
.stat-card--info    { border-top: 3px solid #909399; }
.stat-card--danger  { border-top: 3px solid #f56c6c; }
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
  word-break: break-all;
}
.stat-value--profit { color: #67c23a; }
.stat-value--loss   { color: #f56c6c; }

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.filter-card :deep(.el-card__body) { padding: 16px; }
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}
.filter-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.filter-actions { display: flex; gap: 8px; align-items: center; }

/* 批量工具栏 */
.batch-toolbar-new {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-accent-light);
  border-radius: var(--radius-sm);
}
.batch-toolbar-new__count {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-accent);
  margin-right: var(--space-xs);
}

.pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
.secret-cell { display: flex; align-items: center; gap: 6px; }
.eye-icon { cursor: pointer; color: #409eff; flex-shrink: 0; }
.collect-progress-card :deep(.el-card__body) { padding: 12px 16px; }
.collect-progress { display: flex; align-items: center; gap: 12px; }
.import-result { margin-top: 16px; }

/* ===== 详情弹窗 ===== */
.detail-hero {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: 0 0 var(--space-lg);
  border-bottom: 1px solid var(--color-border-subtle);
  margin-bottom: var(--space-md);
}
.detail-hero__avatar { flex-shrink: 0; font-size: 24px; }
.detail-hero__name {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 2px;
}
.detail-hero__nickname {
  font-size: 14px;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-sm);
}
.detail-hero__badges { display: flex; gap: var(--space-xs); }

/* 分组卡片 */
.section-group { margin-bottom: var(--space-md); }
.section-group__title {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: var(--space-sm);
  padding-bottom: var(--space-xs);
  border-bottom: 1px solid var(--color-border-subtle);
}
.section-group__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.section-group__body.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px var(--space-md);
}

/* 信息行 */
.info-row {
  display: flex;
  align-items: center;
  min-height: 32px;
  padding: 4px 0;
}
.info-row--full { grid-column: 1 / -1; }
.info-row__label {
  font-size: 13px;
  color: var(--color-text-muted);
  min-width: 90px;
  flex-shrink: 0;
}
.info-row__value {
  font-size: 13px;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex: 1;
}
.sensitive-text {
  font-family: 'SF Mono', 'Fira Code', monospace;
  letter-spacing: 1px;
}
.eye-btn {
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 14px;
  transition: color 150ms ease;
}
.eye-btn:hover { color: var(--color-accent); }

/* 数据概览网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
}
.stat-item {
  text-align: center;
  padding: var(--space-sm);
  background: var(--color-bg-page);
  border-radius: var(--radius-sm);
}
.stat-item__value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
}
.stat-item__label {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

/* TikTok 权限网格 */
.tiktok-perms-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-sm);
}
.perm-item {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
}
.perm-item__icon {
  font-size: 14px;
  font-weight: 700;
  width: 20px;
  text-align: center;
}
.perm-item__icon.is-on  { color: #166534; }
.perm-item__icon.is-off { color: #9CA3AF; }
.perm-item__label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* ===== 表单弹窗 ===== */
.form-section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: var(--space-md) 0 var(--space-sm);
  border-bottom: 1px solid var(--color-border-subtle);
  margin-bottom: var(--space-sm);
}
.tiktok-switch-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-sm);
}

/* 移动端样式 */
@media (max-width: 768px) {
  .op-account-list { padding: 12px; gap: 12px; }
  .filter-row { flex-wrap: wrap; gap: 8px; }
  .filter-inputs { flex-wrap: wrap; gap: 8px; }
  .filter-actions { margin-left: 0; width: 100%; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .tiktok-perms-grid { grid-template-columns: repeat(2, 1fr); }
  .section-group__body.two-col { grid-template-columns: 1fr; }
}
.ios-card-account-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--color-border-subtle, #f0f0f0);
}
.ios-card-account-info { flex: 1; min-width: 0; }
.ios-card-account-name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ios-card-account-nickname {
  font-size: 12px;
  color: var(--color-text-muted, #909399);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ios-card-account-tags {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
}
</style>
