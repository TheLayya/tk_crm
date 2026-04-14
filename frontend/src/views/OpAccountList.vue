<template>
  <div class="op-account-list">
    <!-- 过滤栏 -->
    <el-card class="filter-card">
      <div class="filter-row">
        <el-select v-model="filters.platform" placeholder="平台" clearable @change="handleFilterChange" style="width:120px">
          <el-option label="TikTok" value="tiktok" />
          <el-option label="YouTube" value="youtube" />
          <el-option label="Instagram" value="instagram" />
          <el-option label="Facebook" value="facebook" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable @change="handleFilterChange" style="width:110px">
          <el-option label="正常" value="正常" />
          <el-option label="自用" value="自用" />
          <el-option label="封禁" value="封禁" />
          <el-option label="已售" value="已售" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="搜索账号/昵称" clearable @clear="handleFilterChange" @keyup.enter="handleFilterChange" style="width:180px">
          <template #append><el-button :icon="Search" @click="handleFilterChange" /></template>
        </el-input>
        <el-input v-model="filters.purchase_channel" placeholder="采购渠道" clearable @clear="handleFilterChange" @keyup.enter="handleFilterChange" style="width:140px" />
        <el-input v-model="filters.sale_customer" placeholder="出售客户" clearable @clear="handleFilterChange" @keyup.enter="handleFilterChange" style="width:140px" />
        <div class="filter-actions">
          <el-button type="primary" @click="handleCreate"><el-icon><Plus /></el-icon>新增账号</el-button>
          <el-button @click="showImportDialog = true"><el-icon><Upload /></el-icon>批量导入</el-button>
          <el-dropdown @command="handleExport">
            <el-button><el-icon><Download /></el-icon>导出<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
                <el-dropdown-item command="xlsx">导出 Excel</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button @click="showColumnConfig = true"><el-icon><Setting /></el-icon>列配置</el-button>
        </div>
      </div>

      <!-- 批量操作工具栏 -->
      <div class="batch-toolbar" v-if="selectedIds.length > 0">
        <span>已选 {{ selectedIds.length }} 项</span>
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
      <el-table :data="accounts" v-loading="loading" @selection-change="handleSelectionChange" @row-dblclick="handleRowDblClick" border size="small">
        <el-table-column type="selection" width="40" fixed="left" />
        <el-table-column label="平台" width="90" fixed="left">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.platform)" size="small">{{ row.platform?.toUpperCase() }}</el-tag>
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
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
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
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="handleCollectOne(row)">采集</el-button>
            <el-button link type="primary" size="small" @click="showLogs(row)">历史</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

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
    <el-dialog v-model="formDialog.visible" :title="formDialog.isEdit ? '编辑账号' : '新增账号'" width="700px" top="5vh">
      <el-form :model="form" ref="formRef" label-width="100px" size="small">
        <el-divider content-position="left">基础信息</el-divider>
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

        <el-divider content-position="left">账号凭证</el-divider>
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
          <el-divider content-position="left">TikTok 权限</el-divider>
          <el-row :gutter="16">
            <el-col :span="6"><el-form-item label="中视频"><el-switch v-model="form.tiktok_mid_video" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="橱窗"><el-switch v-model="form.tiktok_showcase" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="手机直播"><el-switch v-model="form.tiktok_phone_live" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="伴侣直播"><el-switch v-model="form.tiktok_partner_live" /></el-form-item></el-col>
          </el-row>
        </template>

        <el-divider content-position="left">采购信息</el-divider>
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
          <el-col :span="12">
            <el-form-item label="养号成本"><el-input-number v-model="form.maintenance_cost" :precision="2" :min="0" style="width:100%" /></el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left"><span style="color:#E6A23C">出售信息</span></el-divider>
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

        <el-divider content-position="left">其他</el-divider>
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
        <el-button @click="formDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="formDialog.loading">确定</el-button>
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
    <el-dialog v-model="detailDialog.visible" :title="`账号详情 - ${detailDialog.row?.account}`" width="760px" top="5vh">
      <template v-if="detailDialog.row">
        <el-row :gutter="16">
          <!-- 左侧：头像 + 基础采集信息 -->
          <el-col :span="6" style="text-align:center">
            <el-avatar v-if="detailDialog.row.avatar_url" :src="detailDialog.row.avatar_url" :size="80" style="margin-bottom:8px" />
            <el-avatar v-else :size="80" style="margin-bottom:8px;font-size:28px">{{ (detailDialog.row.account||'?')[0].toUpperCase() }}</el-avatar>
            <div style="font-weight:600;font-size:15px">{{ detailDialog.row.account }}</div>
            <div v-if="detailDialog.row.nickname" style="color:#909399;font-size:13px">{{ detailDialog.row.nickname }}</div>
            <el-tag :type="statusTagType(detailDialog.row.status)" size="small" style="margin-top:6px">{{ detailDialog.row.status }}</el-tag>
          </el-col>
          <!-- 右侧：详细信息 -->
          <el-col :span="18">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="平台">{{ detailDialog.row.platform?.toUpperCase() }}</el-descriptions-item>
              <el-descriptions-item label="国家/地区">{{ detailDialog.row.country || '-' }}</el-descriptions-item>
              <el-descriptions-item label="平台UID" :span="2">{{ detailDialog.row.platform_user_id || '-' }}</el-descriptions-item>
              <el-descriptions-item label="SEC UID" :span="2">
                <el-tooltip v-if="detailDialog.row.platform_sec_uid" :content="detailDialog.row.platform_sec_uid" placement="top">
                  <span>{{ detailDialog.row.platform_sec_uid?.substring(0,30) }}...</span>
                </el-tooltip>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="粉丝数">{{ formatNum(detailDialog.row.follower_count) }}</el-descriptions-item>
              <el-descriptions-item label="关注数">{{ formatNum(detailDialog.row.following_count) }}</el-descriptions-item>
              <el-descriptions-item label="点赞数">{{ formatNum(detailDialog.row.like_count) }}</el-descriptions-item>
              <el-descriptions-item label="视频数">{{ formatNum(detailDialog.row.video_count) }}</el-descriptions-item>
              <el-descriptions-item label="注册时间">{{ detailDialog.row.account_created_at ? formatDate(detailDialog.row.account_created_at) : '-' }}</el-descriptions-item>
              <el-descriptions-item label="最后采集">{{ detailDialog.row.last_collected_at ? formatDate(detailDialog.row.last_collected_at) : '-' }}</el-descriptions-item>
              <el-descriptions-item label="采集状态">
                <el-tag :type="collectStatusType(detailDialog.row.collect_status)" size="small">{{ collectStatusLabel(detailDialog.row.collect_status) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="账号来源">{{ detailDialog.row.source || '-' }}</el-descriptions-item>
            </el-descriptions>

            <el-divider content-position="left" style="margin:12px 0 8px">账号凭证</el-divider>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="密码">{{ detailDialog.row.password ? '••••••' : '-' }}</el-descriptions-item>
              <el-descriptions-item label="2FA密钥">{{ detailDialog.row.totp_secret ? '••••••' : '-' }}</el-descriptions-item>
              <el-descriptions-item label="绑定邮箱">{{ detailDialog.row.email || '-' }}</el-descriptions-item>
              <el-descriptions-item label="邮箱密码">{{ detailDialog.row.email_password ? '••••••' : '-' }}</el-descriptions-item>
              <el-descriptions-item label="邮箱登录地址" :span="2">{{ detailDialog.row.email_login_url || '-' }}</el-descriptions-item>
              <el-descriptions-item label="绑定手机">{{ detailDialog.row.phone || '-' }}</el-descriptions-item>
              <el-descriptions-item label="手机管理链接">{{ detailDialog.row.phone_manage_url || '-' }}</el-descriptions-item>
            </el-descriptions>

            <template v-if="detailDialog.row.platform === 'tiktok'">
              <el-divider content-position="left" style="margin:12px 0 8px">TikTok 权限</el-divider>
              <el-descriptions :column="4" border size="small">
                <el-descriptions-item label="中视频"><el-tag :type="detailDialog.row.tiktok_mid_video ? 'success':'info'" size="small">{{ detailDialog.row.tiktok_mid_video ? '是':'否' }}</el-tag></el-descriptions-item>
                <el-descriptions-item label="橱窗"><el-tag :type="detailDialog.row.tiktok_showcase ? 'success':'info'" size="small">{{ detailDialog.row.tiktok_showcase ? '是':'否' }}</el-tag></el-descriptions-item>
                <el-descriptions-item label="手机直播"><el-tag :type="detailDialog.row.tiktok_phone_live ? 'success':'info'" size="small">{{ detailDialog.row.tiktok_phone_live ? '是':'否' }}</el-tag></el-descriptions-item>
                <el-descriptions-item label="伴侣直播"><el-tag :type="detailDialog.row.tiktok_partner_live ? 'success':'info'" size="small">{{ detailDialog.row.tiktok_partner_live ? '是':'否' }}</el-tag></el-descriptions-item>
              </el-descriptions>
            </template>

            <el-divider content-position="left" style="margin:12px 0 8px">采购 / 出售</el-divider>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="采购渠道">{{ detailDialog.row.purchase_channel || '-' }}</el-descriptions-item>
              <el-descriptions-item label="采购金额">{{ detailDialog.row.purchase_price != null ? '¥'+detailDialog.row.purchase_price : '-' }}</el-descriptions-item>
              <el-descriptions-item label="采购日期">{{ detailDialog.row.purchase_date || '-' }}</el-descriptions-item>
              <el-descriptions-item label="养号成本">{{ detailDialog.row.maintenance_cost != null ? '¥'+detailDialog.row.maintenance_cost : '-' }}</el-descriptions-item>
              <el-descriptions-item label="出售客户">{{ detailDialog.row.sale_customer || '-' }}</el-descriptions-item>
              <el-descriptions-item label="出售金额">{{ detailDialog.row.sale_price != null ? '¥'+detailDialog.row.sale_price : '-' }}</el-descriptions-item>
              <el-descriptions-item label="出售日期">{{ detailDialog.row.sale_date || '-' }}</el-descriptions-item>
              <el-descriptions-item label="-"> </el-descriptions-item>
            </el-descriptions>

            <el-divider content-position="left" style="margin:12px 0 8px">其他</el-divider>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="注册人">{{ detailDialog.row.registrant || '-' }}</el-descriptions-item>
              <el-descriptions-item label="使用人">{{ detailDialog.row.operator || '-' }}</el-descriptions-item>
              <el-descriptions-item label="备注" :span="2">{{ detailDialog.row.remark || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-col>
        </el-row>
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
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Download, Search, Setting, ArrowDown, View, Hide } from '@element-plus/icons-vue'
import {
  listOpAccounts, createOpAccount, updateOpAccount, deleteOpAccount,
  batchUpdateStatus, importOpAccounts, exportOpAccounts,
  triggerCollect, getCollectTask, getAuditLogs
} from '@/api/op_accounts'
import { getMembers } from '@/api/team'
import { useAuthStore } from '@/stores/auth'

// ===== 数据 =====
const accounts = ref([])
const loading = ref(false)
const selectedIds = ref([])
const teamMembers = ref([])
const selectedRows = ref([])
const visibleFields = ref({})

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
  purchase_channel: '', purchase_price: null, purchase_date: null, maintenance_cost: null,
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
  } catch (e) { if (e !== 'cancel') console.error(e) }
}
const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个账号吗？`, '批量删除', { type: 'warning' })
    await Promise.all(selectedIds.value.map(id => deleteOpAccount(id)))
    ElMessage.success('批量删除成功')
    loadAccounts()
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

onMounted(() => {
  loadAccounts()
  const authStore = useAuthStore()
  if (authStore.hasPermission('team:member:view')) {
    getMembers({ size: 200 }).then(data => {
      teamMembers.value = data.items || []
    }).catch(() => {})
  }
})
</script>

<style scoped>
.op-account-list { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.filter-card :deep(.el-card__body) { padding: 16px; }
.filter-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.filter-actions { display: flex; gap: 8px; margin-left: auto; }
.batch-toolbar { display: flex; align-items: center; gap: 10px; margin-top: 12px; padding: 8px 12px; background: #f0f2f5; border-radius: 4px; }
.pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
.secret-cell { display: flex; align-items: center; gap: 6px; }
.eye-icon { cursor: pointer; color: #409eff; flex-shrink: 0; }
.collect-progress-card :deep(.el-card__body) { padding: 12px 16px; }
.collect-progress { display: flex; align-items: center; gap: 12px; }
.import-result { margin-top: 16px; }
</style>
