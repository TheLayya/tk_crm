<template>
  <div class="proxy-node-manage">
    <el-card style="margin-top: 16px;">
      <template #header>
        <div class="card-header">
          <span class="card-title">节点管理</span>
          <div class="header-actions">
            <el-button type="primary" :icon="Plus" @click="openCreate">添加节点</el-button>
            <el-button :icon="Upload" @click="importDialogVisible = true">导入</el-button>
            <el-button :icon="Download" @click="openExportDialog">导出</el-button>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <el-form inline class="filter-form">
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="全部状态"
            style="width: 160px;"
            @change="handleFilterChange"
          >
            <el-option label="闲置" value="idle" />
            <el-option label="自用" value="active" />
            <el-option label="已出售" value="sold" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="协议">
          <el-select
            v-model="filters.protocol"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="全部协议"
            style="width: 160px;"
            @change="handleFilterChange"
          >
            <el-option label="SOCKS5" value="socks5" />
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
          </el-select>
        </el-form-item>
        <el-form-item label="采购渠道">
          <el-input
            v-model="filters.purchase_channel"
            placeholder="搜索采购渠道"
            clearable
            style="width: 160px;"
            @input="handleFilterChange"
            @clear="handleFilterChange"
          />
        </el-form-item>
        <el-form-item label="出售客户">
          <el-input
            v-model="filters.sale_customer"
            placeholder="搜索出售客户"
            clearable
            style="width: 160px;"
            @input="handleFilterChange"
            @clear="handleFilterChange"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 批量操作工具栏 -->
      <div v-if="selectedNodes.length > 0" class="batch-toolbar">
        <span class="batch-info">已选 {{ selectedNodes.length }} 项</span>
        <el-button type="primary" size="small" :loading="batchTesting" @click="handleBatchTest">
          <el-icon><Connection /></el-icon>
          批量测试
        </el-button>
        <el-select
          v-model="batchStatusTarget"
          placeholder="批量修改状态"
          size="small"
          style="width: 140px;"
          @change="handleBatchUpdateStatus"
        >
          <el-option label="闲置" value="idle" />
          <el-option label="自用" value="active" />
          <el-option label="已出售" value="sold" />
          <el-option label="停用" value="disabled" />
        </el-select>
        <el-button type="danger" size="small" @click="handleBatchDelete">
          <el-icon><Delete /></el-icon>
          批量删除 ({{ selectedNodes.length }})
        </el-button>
      </div>

      <!-- 节点数据表格 -->
      <el-table
        ref="nodeTable"
        @expand-change="loadExpandedNode"
        row-key="id"
        size="small"
        :data="nodes"
        v-loading="loading"
        @selection-change="handleSelectionChange"
        stripe
        style="width: 100%;"
      >
        <el-table-column type="selection" width="50" fixed="left" />
        <el-table-column type="expand" width="36" fixed="left">
          <template #default="{ row }">
            <div class="node-inline-details resource-state-grid" :style="{ width: nodeTable?.$el?.clientWidth ? nodeTable.$el.clientWidth + 'px' : '100%' }">
              <section>
                <strong>当前状态</strong>
                <div class="inline-detail-section"><b>业务状态</b><el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag><b>最近检测</b><span>{{ row.last_test_result === 'success' ? '检测成功' : row.last_test_result === 'failed' ? '检测失败' : '尚未检测' }}{{ row.last_test_latency != null ? ' · ' + row.last_test_latency + 'ms' : '' }}</span></div>
                <div class="inline-detail-section"><b>检测时间</b>{{ row.last_test_at ? new Date(row.last_test_at).toLocaleString('zh-CN') : '—' }}</div>
                <div class="inline-detail-section"><b>关联终端（{{ row.devices?.length || 0 }}）</b><el-tag v-for="device in row.devices || []" :key="device.id" size="small">{{ device.name }}</el-tag><span v-if="!row.devices?.length">未绑定</span></div>
                <div class="inline-detail-section"><b>关联账号（{{ row.accounts?.length || 0 }}）</b><span>{{ (row.accounts || []).map(account => account.username).join(' / ') || '未关联' }}</span></div>
                <div class="inline-detail-section"><b>到期</b>{{ row.expire_date || '未设置' }}</div>
                <div v-if="row.remark" class="inline-detail-section"><b>备注</b><span>{{ row.remark }}</span></div>
                <div class="state-note">检测结果仅代表最近一次检测，不代表实时连通状态。</div>
              <AssociationOverview kind="node" :resource-id="row.id" />
              </section>
              <ResourceActivity :logs="nodeActivity[row.id]?.items || []" :total="nodeActivity[row.id]?.total || 0" :page="nodeActivityPage[row.id] || 1" :loading="nodeActivityLoading[row.id]" :error="nodeActivityError[row.id]" note="已有单节点操作记录；批量操作和从终端侧调整关联不在此记录范围内。" @page-change="loadNodeActivity(row.id, $event)" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="IP" width="130" fixed="left">
          <template #default="{ row }">
            <button type="button" class="resource-expand-trigger" :aria-expanded="expandedNodeIds.includes(row.id)" :title="expandedNodeIds.includes(row.id) ? '点击收起节点详情' : '点击展开节点详情'" @click="nodeTable.toggleRowExpansion(row)">{{ row.ip }}</button>
          </template>
        </el-table-column>
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column prop="country" label="国家/地区" width="100"><template #default="{ row }">{{ row.country || '未填写' }}</template></el-table-column>
        <el-table-column prop="protocol" label="协议" width="90">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.protocol?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="绑定终端" min-width="180">
          <template #default="{ row }">
            <el-space wrap v-if="row.devices?.length">
              <el-tag v-for="d in row.devices" :key="d.id" size="small">{{ d.name }}</el-tag>
            </el-space>
            <span v-else>未绑定</span>
          </template>
        </el-table-column>
        <el-table-column label="关联账号" min-width="400">
          <template #default="{ row }">
            <LinkedAccountCards :accounts="row.accounts || []" empty-text="未关联" />
          </template>
        </el-table-column>
        <el-table-column prop="relay_ip" label="中转IP" width="130">
          <template #default="{ row }">{{ row.relay_ip || '-' }}</template>
        </el-table-column>
        <el-table-column prop="relay_port" label="中转端口" width="90">
          <template #default="{ row }">{{ row.relay_port || '-' }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="expire_date" label="到期日期" width="120">
          <template #default="{ row }">
            <span :class="{ 'expiring-soon': isExpiringSoon(row.expire_date) }">
              {{ row.expire_date || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="last_test_result" label="测试结果" width="100">
          <template #default="{ row }">
            <span v-if="row.last_test_result" class="test-result">
              <el-icon v-if="row.last_test_result === 'success'" color="#67c23a"><CircleCheck /></el-icon>
              <el-icon v-else color="#f56c6c"><CircleClose /></el-icon>
              {{ row.last_test_result === 'success' ? '成功' : '失败' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_test_latency" label="延迟(ms)" width="90">
          <template #default="{ row }">
            {{ row.last_test_latency != null ? row.last_test_latency : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="purchase_channel" label="采购渠道" width="120">
          <template #default="{ row }">{{ row.purchase_channel || '-' }}</template>
        </el-table-column>
        <el-table-column prop="sale_customer" label="出售客户" width="120">
          <template #default="{ row }">{{ row.sale_customer || '-' }}</template>
        </el-table-column>
        <el-table-column label="出售人" width="120">
          <template #default="{ row }">
            <span v-if="row.sellers && row.sellers.length">{{ row.sellers.join('、') }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="密码" width="130">
          <template #default="{ row }">
            <div v-if="row.password" style="display: flex; align-items: center; gap: 6px;">
              <span>{{ visiblePasswords[row.id] ? row.password : '******' }}</span>
              <el-icon style="cursor: pointer; color: #409eff;" @click="togglePasswordVisibility(row.id)">
                <View v-if="!visiblePasswords[row.id]" />
                <Hide v-else />
              </el-icon>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="215" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              :loading="testingIds.includes(row.id)"
              @click="handleTest(row)"
            >测试</el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="success" size="small" @click="openRelation(row)">关联</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
            <el-button
              v-if="authStore.user?.is_super_admin"
              link
              type="warning"
              size="small"
              @click="showQrDialog(row)"
            >二维码</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @current-change="loadNodes"
        @size-change="handleSizeChange"
      />
    </el-card>

    <!-- 添加/编辑节点对话框 -->
    <el-dialog
      v-model="nodeDialogVisible"
      :title="editingId ? '编辑节点' : '添加节点'"
      width="640px"
      :close-on-click-modal="false"
    >
      <!-- 新增时显示模式切换 -->
      <div v-if="!editingId" style="margin-bottom: 16px;">
        <el-radio-group v-model="addMode" size="small">
          <el-radio-button value="single">单个添加</el-radio-button>
          <el-radio-button value="batch">批量粘贴</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 批量粘贴模式 -->
      <div v-if="!editingId && addMode === 'batch'">
        <div class="form-section-title">节点列表</div>
        <el-input
          v-model="batchText"
          type="textarea"
          :rows="8"
          placeholder="每行一个节点，格式：ip:port:username:password&#10;例如：&#10;82.153.181.89:8022:user1:pass1&#10;14.192.51.76:9566:user2:pass2"
          style="font-family: monospace; font-size: 13px;"
        />
        <div style="margin-top: 6px; color: #909399; font-size: 12px;">
          支持格式：<code>ip:port:username:password</code> 或 <code>ip:port</code>（无认证）
        </div>

        <!-- 批量公共信息 -->
        <div class="form-section-title" style="margin-top: 16px;">公共信息（应用到所有节点）</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="协议" label-width="80px">
              <el-select v-model="batchCommon.protocol" style="width: 100%;">
                <el-option label="SOCKS5" value="socks5" />
                <el-option label="HTTP" value="http" />
                <el-option label="HTTPS" value="https" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态" label-width="80px">
              <el-select v-model="batchCommon.status" style="width: 100%;">
                <el-option label="闲置" value="idle" />
                <el-option label="自用" value="active" />
                <el-option label="已出售" value="sold" />
                <el-option label="停用" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="采购渠道" required label-width="80px">
              <el-input v-model="batchCommon.purchase_channel" placeholder="请输入采购渠道" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="采购单价" required label-width="80px">
              <el-input-number v-model="batchCommon.purchase_price" :min="0" :precision="2" :controls="false" style="width: 100%;" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="采购日期" required label-width="80px">
              <el-date-picker v-model="batchCommon.purchase_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%;" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="到期日期" required label-width="80px">
              <el-date-picker v-model="batchCommon.expire_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="状态" label-width="80px">
              <el-select v-model="batchCommon.status" style="width: 100%;">
                <el-option label="正常" value="active" />
                <el-option label="已到期" value="expired" />
                <el-option label="已出售" value="sold" />
                <el-option label="停用" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注" label-width="80px">
              <el-input v-model="batchCommon.remark" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="国家/地区" required label-width="80px"><el-input v-model="batchCommon.country" maxlength="100" placeholder="例如：美国" /></el-form-item>

        <el-row v-if="batchCommon.status === 'sold'" :gutter="16">
          <el-col :span="12"><el-form-item label="出售客户" required label-width="80px"><el-input v-model="batchCommon.sale_customer" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="单个售价" required label-width="80px"><el-input-number v-model="batchCommon.sale_price" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="出售人" required label-width="80px"><SellerSelector v-model="batchCommon.sellers" /></el-form-item></el-col>
        </el-row>

        <!-- 解析预览 -->
        <div v-if="batchPreview.length > 0" style="margin-top: 8px;">
          <div style="font-size: 12px; color: #606266; margin-bottom: 6px;">
            已解析 <span style="color: #67c23a; font-weight: 600;">{{ batchPreview.filter(r => !r.error).length }}</span> 条有效，
            <span v-if="batchPreview.filter(r => r.error).length > 0" style="color: #f56c6c; font-weight: 600;">{{ batchPreview.filter(r => r.error).length }} 条格式错误</span>
          </div>
          <div v-for="(item, idx) in batchPreview.slice(0, 5)" :key="idx" style="font-size: 12px; font-family: monospace; padding: 2px 0;" :style="{ color: item.error ? '#f56c6c' : '#606266' }">
            {{ item.error ? `✗ 第${idx+1}行: ${item.error}` : `✓ ${item.ip}:${item.port} ${item.username || ''}` }}
          </div>
          <div v-if="batchPreview.length > 5" style="font-size: 12px; color: #909399;">...还有 {{ batchPreview.length - 5 }} 条</div>
        </div>
      </div>

      <!-- 单个添加 / 编辑模式 -->
      <el-form
        v-if="editingId || addMode === 'single'"
        ref="nodeFormRef"
        :model="nodeForm"
        :rules="editingId ? { ip: nodeRules.ip, port: nodeRules.port } : nodeRules"
        label-width="100px"
        style="max-height: 60vh; overflow-y: auto; padding-right: 8px;"
      >
        <!-- 原始节点信息 -->
        <div class="form-section-title">原始节点信息</div>
        <el-form-item label="国家/地区" prop="country"><el-input v-model="nodeForm.country" placeholder="例如：美国" maxlength="100" /></el-form-item>
        <el-row :gutter="16">
          <el-col :span="14">
            <el-form-item label="IP 地址" prop="ip">
              <el-input v-model="nodeForm.ip" placeholder="例如: 192.168.1.1" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="端口" prop="port">
              <el-input-number v-model="nodeForm.port" :min="1" :max="65535" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="nodeForm.username" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="nodeForm.password" type="password" show-password placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="协议">
              <el-select v-model="nodeForm.protocol" style="width: 100%;">
                <el-option label="SOCKS5" value="socks5" />
                <el-option label="HTTP" value="http" />
                <el-option label="HTTPS" value="https" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 中转节点信息（可折叠） -->
        <el-collapse v-model="activeCollapse" style="margin-bottom: 12px;">
          <el-collapse-item title="中转节点信息" name="relay">
            <el-row :gutter="16">
              <el-col :span="14">
                <el-form-item label="中转 IP">
                  <el-input v-model="nodeForm.relay_ip" placeholder="可选" />
                </el-form-item>
              </el-col>
              <el-col :span="10">
                <el-form-item label="中转端口">
                  <el-input-number v-model="nodeForm.relay_port" :min="1" :max="65535" :controls="false" style="width: 100%;" placeholder="可选" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="中转协议">
                  <el-select v-model="nodeForm.relay_protocol" clearable placeholder="可选" style="width: 100%;">
                    <el-option label="SOCKS5" value="socks5" />
                    <el-option label="HTTP" value="http" />
                    <el-option label="HTTPS" value="https" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
          </el-collapse-item>

          <!-- 采购信息（可折叠） -->
          <el-collapse-item :title="editingId ? '采购信息' : '采购信息（必填）'" name="purchase">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="采购日期" prop="purchase_date">
                  <el-date-picker v-model="nodeForm.purchase_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%;" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="到期日期" prop="expire_date">
                  <el-date-picker v-model="nodeForm.expire_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%;" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="采购单价" prop="purchase_price">
                  <el-input-number v-model="nodeForm.purchase_price" :min="0" :precision="2" :controls="false" style="width: 100%;" placeholder="可选" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="采购渠道" prop="purchase_channel">
                  <el-input v-model="nodeForm.purchase_channel" placeholder="请输入采购渠道" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-collapse-item>

          <!-- 出售信息（可折叠） -->
          <el-collapse-item v-if="nodeForm.status === 'sold'" title="出售信息（必填）" name="sale">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="出售客户" required>
                  <el-input v-model="nodeForm.sale_customer" placeholder="请输入出售客户" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="出售价格" required>
                  <el-input-number v-model="nodeForm.sale_price" :min="0" :precision="2" :controls="false" style="width: 100%;" placeholder="请输入售价" />
                </el-form-item>
              </el-col>
              <el-col :span="24">
                <el-form-item label="出售人" required>
                  <SellerSelector v-model="nodeForm.sellers" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-collapse-item>
        </el-collapse>

        <!-- 状态与备注 -->
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="nodeForm.status" style="width: 100%;" @change="openSaleFields">
                <el-option label="闲置" value="idle" />
                <el-option label="自用" value="active" />
                <el-option label="已出售" value="sold" />
                <el-option label="停用" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="nodeForm.remark" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleNodeSubmit">
          {{ !editingId && addMode === 'batch' ? `批量添加 (${batchPreview.filter(r => !r.error).length} 条)` : '确定' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchSaleVisible" title="批量出售节点" width="480px">
      <el-form label-width="90px">
        <el-form-item label="出售客户" required><el-input v-model="batchSale.sale_customer" /></el-form-item>
        <el-form-item label="单个售价" required><el-input-number v-model="batchSale.sale_price" :min="0" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="出售人" required><SellerSelector v-model="batchSale.sellers" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="batchSaleVisible = false">取消</el-button><el-button type="primary" :loading="batchSaleLoading" @click="submitBatchSale">确认出售</el-button></template>
    </el-dialog>

    <!-- 导入对话框 -->
  <el-dialog v-model="importDialogVisible" title="批量导入节点" width="560px" :close-on-click-modal="false">
      <div style="margin-bottom: 12px;">
        <el-link type="primary" :underline="false" @click="handleDownloadTemplate">
          <el-icon><Download /></el-icon>
          下载导入模板
        </el-link>
        <span style="color: #909399; font-size: 13px; margin-left: 12px;">支持 .csv 和 .xlsx 格式</span>
      </div>

      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        accept=".csv,.xlsx"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        drag
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .csv 或 .xlsx 文件</div>
        </template>
      </el-upload>

      <!-- 导入结果 -->
      <div v-if="importResult" style="margin-top: 16px;">
        <el-alert
          :title="`导入完成：成功 ${importResult.success_count} 条，失败 ${importResult.fail_count} 条`"
          :type="importResult.fail_count > 0 ? 'warning' : 'success'"
          :closable="false"
          show-icon
        />
        <el-collapse v-if="importResult.errors?.length > 0" style="margin-top: 8px;">
          <el-collapse-item :title="`失败详情（${importResult.errors.length} 条）`" name="errors">
            <div v-for="(err, idx) in importResult.errors" :key="idx" class="import-error-item">
              {{ err }}
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>

      <template #footer>
        <el-button @click="closeImportDialog">关闭</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!importFile"
          @click="handleImport"
        >开始导入</el-button>
      </template>
  </el-dialog>

  <el-dialog v-model="relationDialogVisible" title="节点关联管理" width="520px" :close-on-click-modal="false">
    <el-form label-width="110px">
      <el-form-item label="绑定终端">
        <el-select v-model="relationForm.device_id" filterable clearable placeholder="选择终端（留空解除）" style="width:100%">
          <el-option v-for="d in relationDevices" :key="d.id" :label="`${d.name} (#${d.id})`" :value="d.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="运营账号">
        <el-select v-model="relationForm.account_id" filterable clearable placeholder="选择账号（留空解除）" style="width:100%">
          <el-option v-for="a in relationAccounts" :key="a.id" :label="`${a.account || a.username || '账号'} (#${a.id})`" :value="a.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer><el-button @click="relationDialogVisible=false">取消</el-button><el-button type="primary" @click="saveRelation">确认保存</el-button></template>
  </el-dialog>

    <!-- 导出对话框 -->
    <el-dialog v-model="exportDialogVisible" title="导出节点数据" width="360px">
      <p style="color: #606266; margin-bottom: 16px;">
        将导出当前筛选条件下的所有节点数据（共约 {{ total }} 条）
      </p>
      <div style="display: flex; gap: 16px; justify-content: center;">
        <el-button type="primary" :loading="exporting" @click="handleExport('csv')">
          <el-icon><Document /></el-icon>
          导出 CSV
        </el-button>
        <el-button type="success" :loading="exporting" @click="handleExport('xlsx')">
          <el-icon><Document /></el-icon>
          导出 Excel
        </el-button>
      </div>
      <template #footer>
        <el-button @click="exportDialogVisible = false">取消</el-button>
      </template>
    </el-dialog>

    <!-- 节点二维码对话框（仅超管） -->
    <QRCodeDialog
      v-model:visible="qrDialogVisible"
      :uri="qrUri"
      :title="qrTitle"
      @closed="closeQrDialog"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Upload, Download, Delete, View, Hide,
  Connection, CircleCheck, CircleClose, UploadFilled, Document
} from '@element-plus/icons-vue'
import SellerSelector from '@/components/SellerSelector.vue'
import { saleInformationError } from '@/utils/saleValidation'
import QRCodeDialog from '@/components/QRCodeDialog.vue'
import LinkedAccountCards from '@/components/LinkedAccountCards.vue'
import AssociationOverview from '@/components/AssociationOverview.vue'
import ResourceActivity from '@/components/ResourceActivity.vue'
import { getProxyNodeLogs } from '@/api/proxy_nodes'
import { useAuthStore } from '@/stores/auth'
import {
  getProxyNodes,
  getProxyNode,
  createProxyNode,
  updateProxyNode,
  deleteProxyNode,
  batchDeleteProxyNodes,
  batchUpdateStatus,
  testProxyNode,
  batchTestProxyNodes,
  importProxyNodes,
  downloadImportTemplate,
  exportProxyNodes,
  getNodeUri
  , updateNodeRelation
} from '@/api/proxy_nodes'
import { isExpiringSoon } from '@/utils/proxyNodeUtils'

const authStore = useAuthStore()
const route = useRoute()
const nodeTable = ref(null)
const expandedNodeIds = ref([])
const nodeActivity = ref({})
const nodeActivityPage = ref({})
const nodeActivityLoading = ref({})
const nodeActivityError = ref({})
async function loadNodeActivity(id, page = 1) {
  nodeActivityPage.value[id] = page
  nodeActivityLoading.value[id] = true
  nodeActivityError.value[id] = ''
  try { nodeActivity.value[id] = await getProxyNodeLogs(id, { skip: (page - 1) * 5, limit: 5 }) }
  catch { nodeActivityError.value[id] = '轨迹加载失败，收起后重新展开重试' }
  finally { nodeActivityLoading.value[id] = false }
}
function loadExpandedNode(row, expandedRows) {
  expandedNodeIds.value = expandedRows.map(item => item.id)
  if (expandedRows.some(item => item.id === row.id)) loadNodeActivity(row.id)
}

const relationDialogVisible = ref(false)
const relationRow = ref(null)
const relationForm = ref({ device_id: null, account_id: null })
const relationDevices = ref([])
const relationAccounts = ref([])
async function openRelation(row) {
  try {
    relationRow.value = row
    const [{ getDevices }, accountsApi] = await Promise.all([import('@/api/devices'), import('@/api/op_accounts')])
    const [devices, accounts] = await Promise.all([getDevices({ limit: 200 }), accountsApi.listOpAccounts({ limit: 200 })])
    relationDevices.value = devices.items || devices || []
    relationAccounts.value = accounts.items || accounts || []
    relationForm.value = { device_id: row.devices?.[0]?.id ?? null, account_id: row.accounts?.[0]?.id ?? null }
    relationDialogVisible.value = true
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '加载关联对象失败')
  }
}
async function saveRelation() {
  try {
    await ElMessageBox.confirm(`确认保存终端与运营账号关联吗？`, '确认关联变更', { type: 'warning' })
    await updateNodeRelation(relationRow.value.id, relationForm.value)
    relationDialogVisible.value = false
    ElMessage.success('节点关联已更新')
    await loadNodes()
  } catch (err) { if (err !== 'cancel') ElMessage.error(err?.response?.data?.detail || '关联操作失败') }
}

// ─── 节点二维码 ─────────────────────────────────────────────
const qrDialogVisible = ref(false)
const qrUri = ref('')
const qrTitle = ref('')
let qrRequestSeq = 0

async function showQrDialog(row) {
  const seq = ++qrRequestSeq
  qrTitle.value = `节点二维码 - ${row.ip}:${row.port}`
  qrUri.value = ''
  qrDialogVisible.value = true
  try {
    const res = await getNodeUri(row.id)
    // 序号守卫：仅当前点击的节点可写入 URI，防止 A 节点的凭据显示在 B 节点标题下
    if (seq !== qrRequestSeq) return
    qrUri.value = res.uri
  } catch (err) {
    if (seq !== qrRequestSeq) return
    qrDialogVisible.value = false
    qrUri.value = ''
    ElMessage.error(err?.response?.data?.detail || '获取节点 URI 失败')
  }
}

function closeQrDialog() {
  // 关闭时清空凭据 URI（防残留于响应式状态）
  qrRequestSeq++
  qrDialogVisible.value = false
  qrUri.value = ''
  qrTitle.value = ''
}

// ─── 筛选条件 ────────────────────────────────────────────────
const filters = reactive({
  status: [],
  protocol: [],
  purchase_channel: '',
  sale_customer: ''
})

let filterTimer = null
const handleFilterChange = () => {
  clearTimeout(filterTimer)
  filterTimer = setTimeout(() => {
    page.value = 1
    loadNodes()
  }, 300)
}

const resetFilters = () => {
  filters.status = []
  filters.protocol = []
  filters.purchase_channel = ''
  filters.sale_customer = ''
  page.value = 1
  loadNodes()
}

// ─── 节点列表 ────────────────────────────────────────────────
const nodes = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

const buildQueryParams = () => {
  const params = {
    skip: (page.value - 1) * pageSize.value,
    limit: pageSize.value
  }
  if (filters.status.length) params.status = filters.status
  if (filters.protocol.length) params.protocol = filters.protocol
  if (filters.purchase_channel) params.purchase_channel = filters.purchase_channel
  if (filters.sale_customer) params.sale_customer = filters.sale_customer
  return params
}

const loadNodes = async () => {
  loading.value = true
  try {
    const data = await getProxyNodes(buildQueryParams())
    // 后端返回 { items: [], total: N } 或直接数组
    if (Array.isArray(data)) {
      nodes.value = data
      total.value = data.length
    } else {
      nodes.value = data.items ?? data
      total.value = data.total ?? (data.items?.length ?? 0)
    }
  } catch (err) {
    ElMessage.error('加载节点列表失败')
    console.error(err)
  } finally {
    loading.value = false
  }
}

const handleSizeChange = () => {
  page.value = 1
  loadNodes()
}

// ─── 密码可见性 ──────────────────────────────────────────────
const visiblePasswords = ref({})
const togglePasswordVisibility = (id) => {
  visiblePasswords.value[id] = !visiblePasswords.value[id]
}

// ─── 多选 ────────────────────────────────────────────────────
const selectedNodes = ref([])
const handleSelectionChange = (selection) => {
  selectedNodes.value = selection
}

// ─── 单节点测试 ──────────────────────────────────────────────
const testingIds = ref([])
const handleTest = async (row) => {
  testingIds.value.push(row.id)
  try {
    const result = await testProxyNode(row.id)
    if (result.success) {
      ElMessage.success(`测试成功，延迟 ${result.latency_ms} ms`)
    } else {
      ElMessage.warning(`测试失败：${result.error || '未知错误'}`)
    }
    await loadNodes()
  } catch (err) {
    ElMessage.error('测试请求失败')
    console.error(err)
  } finally {
    testingIds.value = testingIds.value.filter(id => id !== row.id)
  }
}

// ─── 删除节点 ────────────────────────────────────────────────
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除节点 ${row.ip}:${row.port} 吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await deleteProxyNode(row.id)
    ElMessage.success('删除成功')
    await loadNodes()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '删除失败')
    }
  }
}

// ─── 批量操作 ────────────────────────────────────────────────
const batchTesting = ref(false)
const batchStatusTarget = ref(null)

const handleBatchTest = async () => {
  batchTesting.value = true
  try {
    const ids = selectedNodes.value.map(n => n.id)
    const result = await batchTestProxyNodes(ids)
    ElMessage.success(`批量测试完成：成功 ${result.success_count}，失败 ${result.fail_count}`)
    await loadNodes()
  } catch (err) {
    ElMessage.error('批量测试失败')
    console.error(err)
  } finally {
    batchTesting.value = false
  }
}

const handleBatchUpdateStatus = async (status) => {
  if (!status) return
  if (status === 'sold') {
    Object.assign(batchSale, { sale_customer: '', sale_price: null, sellers: [] })
    batchStatusTarget.value = null
    batchSaleVisible.value = true
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${selectedNodes.value.length} 个节点状态修改为 "${status}" 吗？`,
      '批量修改状态',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    const ids = selectedNodes.value.map(n => n.id)
    await batchUpdateStatus(ids, status)
    ElMessage.success('批量修改状态成功')
    batchStatusTarget.value = null
    await loadNodes()
  } catch (err) {
    batchStatusTarget.value = null
    if (err !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '批量修改状态失败')
    }
  }
}

const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedNodes.value.length} 个节点吗？此操作不可恢复！`,
      '批量删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    const ids = selectedNodes.value.map(n => n.id)
    await batchDeleteProxyNodes(ids)
    ElMessage.success(`成功删除 ${ids.length} 个节点`)
    await loadNodes()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '批量删除失败')
    }
  }
}

// ─── 添加/编辑对话框 ─────────────────────────────────────────
const nodeDialogVisible = ref(false)
const batchSaleVisible = ref(false)
const batchSaleLoading = ref(false)
const batchSale = reactive({ sale_customer: '', sale_price: null, sellers: [] })
const submitBatchSale = async () => {
  const error = saleInformationError(batchSale)
  if (error) return ElMessage.warning(error)
  batchSaleLoading.value = true
  try {
    await batchUpdateStatus(selectedNodes.value.map(node => node.id), 'sold', batchSale)
    batchSaleVisible.value = false
    ElMessage.success('批量出售成功')
    await loadNodes()
  } finally { batchSaleLoading.value = false }
}
const editingId = ref(null)
const submitting = ref(false)
const nodeFormRef = ref(null)
const activeCollapse = ref([])
const openSaleFields = (status) => {
  if (status === 'sold' && !activeCollapse.value.includes('sale')) activeCollapse.value.push('sale')
}

// 添加模式：single | batch
const addMode = ref('single')

// 批量粘贴
const batchText = ref('')
const batchCommon = ref({
  country: '',
  sale_customer: '', sale_price: null, sellers: [],
  protocol: 'socks5',
  status: 'idle',
  purchase_channel: '',
  purchase_price: null,
  purchase_date: null,
  expire_date: null,
  remark: '',
})

// 解析批量文本，返回预览列表
const batchPreview = computed(() => {
  if (!batchText.value.trim()) return []
  return batchText.value
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .map(line => {
      // 支持多种分隔符：冒号、空格、制表符
      const parts = line.split(/[:\s\t]+/)
      if (parts.length < 2) return { error: '格式错误，至少需要 ip:port', raw: line }
      const ip = parts[0]
      const port = parseInt(parts[1])
      if (!ip) return { error: 'IP 不能为空', raw: line }
      if (isNaN(port) || port < 1 || port > 65535) return { error: `端口 "${parts[1]}" 不合法`, raw: line }
      return {
        ip,
        port,
        username: parts[2] || null,
        password: parts[3] || null,
        raw: line,
      }
    })
})

const defaultNodeForm = () => ({
  ip: '',
  port: null,
  country: '',
  username: '',
  password: '',
  protocol: 'socks5',
  relay_ip: '',
  relay_port: null,
  relay_protocol: null,
  purchase_date: null,
  purchase_price: null,
  purchase_channel: '',
  expire_date: null,
  sale_customer: '',
  sale_price: null,
  sellers: [],
  status: 'idle',
  remark: ''
})

const nodeForm = ref(defaultNodeForm())

const nodeRules = {
  country: [{ required: true, message: '请输入国家/地区', trigger: 'blur' }],
  ip: [{ required: true, message: '请输入 IP 地址', trigger: 'blur' }],
  port: [
    { required: true, message: '请输入端口号', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value == null || value === '') {
          callback(new Error('请输入端口号'))
        } else if (!Number.isInteger(value) || value < 1 || value > 65535) {
          callback(new Error('端口号必须是 1-65535 之间的整数'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ],
  purchase_date: [{ required: true, message: '请选择采购日期', trigger: 'change' }],
  purchase_price: [{ required: true, message: '请输入采购单价', trigger: 'change' }],
  purchase_channel: [{ required: true, message: '请输入采购渠道', trigger: 'blur' }],
  expire_date: [{ required: true, message: '请选择到期日期', trigger: 'change' }]
}

const openCreate = () => {
  editingId.value = null
  nodeForm.value = defaultNodeForm()
  activeCollapse.value = ['purchase']
  addMode.value = 'single'
  batchText.value = ''
  batchCommon.value = {
    country: '',
    sale_customer: '', sale_price: null, sellers: [],
    protocol: 'socks5',
    status: 'idle',
    purchase_channel: '',
    purchase_price: null,
    purchase_date: null,
    expire_date: null,
    remark: '',
  }
  nodeDialogVisible.value = true
}

const openEdit = (row) => {
  editingId.value = row.id
  nodeForm.value = {
    ip: row.ip || '',
    country: row.country || '',
    port: row.port || null,
    username: row.username || '',
    password: row.password || '',
    protocol: row.protocol || 'socks5',
    relay_ip: row.relay_ip || '',
    relay_port: row.relay_port || null,
    relay_protocol: row.relay_protocol || null,
    purchase_date: row.purchase_date || null,
    purchase_price: row.purchase_price != null ? Number(row.purchase_price) : null,
    purchase_channel: row.purchase_channel || '',
    expire_date: row.expire_date || null,
    sale_customer: row.sale_customer || '',
    sale_price: row.sale_price != null ? Number(row.sale_price) : null,
    sellers: Array.isArray(row.sellers) ? row.sellers : [],
    status: row.status || 'idle',
    remark: row.remark || ''
  }
  // 展开有数据的折叠面板
  const open = []
  if (row.relay_ip || row.relay_port) open.push('relay')
  if (row.purchase_date || row.purchase_price || row.purchase_channel || row.expire_date) open.push('purchase')
  if (row.status === 'sold') open.push('sale')
  activeCollapse.value = open
  nodeDialogVisible.value = true
}

const handleNodeSubmit = async () => {
  const saleData = !editingId.value && addMode.value === 'batch' ? batchCommon.value : nodeForm.value
  if (!editingId.value) {
    for (const [field, label] of [['country', '国家/地区'], ['purchase_channel', '采购渠道'], ['purchase_date', '采购日期'], ['purchase_price', '采购单价'], ['expire_date', '到期日期']]) {
      if (saleData[field] == null || String(saleData[field]).trim() === '') return ElMessage.warning(`请填写${label}`)
    }
    if (!Number.isFinite(Number(saleData.purchase_price)) || Number(saleData.purchase_price) < 0) return ElMessage.warning('采购单价必须为非负数字')
  }
  if (saleData.status === 'sold') {
    const error = saleInformationError(saleData)
    if (error) return ElMessage.warning(error)
  }
  // 批量模式
  if (!editingId.value && addMode.value === 'batch') {
    const validItems = batchPreview.value.filter(r => !r.error)
    if (validItems.length === 0) {
      ElMessage.warning('没有有效的节点数据，请检查格式')
      return
    }
    submitting.value = true
    let successCount = 0
    let failCount = 0
    try {
      for (const item of validItems) {
        try {
          await createProxyNode({
            ip: item.ip,
            port: item.port,
            username: item.username || null,
            password: item.password || null,
            protocol: batchCommon.value.protocol,
            status: batchCommon.value.status,
            sale_customer: batchCommon.value.sale_customer,
            sale_price: batchCommon.value.sale_price,
            sellers: batchCommon.value.sellers,
            purchase_channel: batchCommon.value.purchase_channel || null,
            country: batchCommon.value.country.trim(),
            purchase_price: batchCommon.value.purchase_price ?? null,
            purchase_date: batchCommon.value.purchase_date || null,
            expire_date: batchCommon.value.expire_date || null,
            remark: batchCommon.value.remark || null,
          })
          successCount++
        } catch {
          failCount++
        }
      }
      if (failCount === 0) {
        ElMessage.success(`成功添加 ${successCount} 个节点`)
      } else {
        ElMessage.warning(`添加完成：成功 ${successCount}，失败 ${failCount}`)
      }
      nodeDialogVisible.value = false
      await loadNodes()
    } finally {
      submitting.value = false
    }
    return
  }

  // 单个添加 / 编辑模式
  const valid = await nodeFormRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    // 清理空字符串为 null
    const data = { ...nodeForm.value }
    const strFields = ['username', 'password', 'relay_ip', 'relay_protocol', 'country', 'purchase_channel', 'sale_customer', 'remark']
    strFields.forEach(f => { if (data[f] === '') data[f] = null })
    if (!data.relay_port) data.relay_port = null
    if (!data.purchase_price && data.purchase_price !== 0) data.purchase_price = null
    if (!data.sale_price && data.sale_price !== 0) data.sale_price = null

    if (editingId.value) {
      await updateProxyNode(editingId.value, data)
      ElMessage.success('节点更新成功')
    } else {
      await createProxyNode(data)
      ElMessage.success('节点创建成功')
    }
    nodeDialogVisible.value = false
    await loadNodes()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

// ─── 导入对话框 ──────────────────────────────────────────────
const importDialogVisible = ref(false)
const importing = ref(false)
const importFile = ref(null)
const importResult = ref(null)
const uploadRef = ref(null)

const handleFileChange = (file) => {
  importFile.value = file.raw
  importResult.value = null
}

const handleFileRemove = () => {
  importFile.value = null
  importResult.value = null
}

const handleDownloadTemplate = async () => {
  try {
    await downloadImportTemplate()
  } catch (err) {
    ElMessage.error('下载模板失败')
  }
}

const handleImport = async () => {
  if (!importFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  importing.value = true
  try {
    const result = await importProxyNodes(importFile.value)
    importResult.value = result
    if (result.success_count > 0) {
      await loadNodes()
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

const closeImportDialog = () => {
  importDialogVisible.value = false
  importFile.value = null
  importResult.value = null
  uploadRef.value?.clearFiles()
}

// ─── 导出对话框 ──────────────────────────────────────────────
const exportDialogVisible = ref(false)
const exporting = ref(false)

const openExportDialog = () => {
  exportDialogVisible.value = true
}

const handleExport = async (format) => {
  exporting.value = true
  try {
    const exportParams = {}
    if (filters.status.length) exportParams.status = filters.status
    if (filters.protocol.length) exportParams.protocol = filters.protocol
    if (filters.purchase_channel) exportParams.purchase_channel = filters.purchase_channel
    if (filters.sale_customer) exportParams.sale_customer = filters.sale_customer

    await exportProxyNodes(exportParams, format)
    ElMessage.success('导出成功')
    exportDialogVisible.value = false
  } catch (err) {
    ElMessage.error('导出失败')
    console.error(err)
  } finally {
    exporting.value = false
  }
}

// ─── 工具函数 ────────────────────────────────────────────────
const statusTagType = (status) => {
  const map = { idle: 'info', active: 'success', sold: 'warning', disabled: 'danger' }
  return map[status] || 'info'
}

const statusLabel = (status) => {
  const map = { idle: '闲置', active: '自用', sold: '已出售', disabled: '停用' }
  return map[status] || status
}

const formatCurrency = (val) => {
  if (val == null) return '¥0.00'
  return `¥${Number(val).toFixed(2)}`
}

// ─── 初始化 ──────────────────────────────────────────────────
onMounted(async () => {
  await loadNodes()
  const nodeId = Number(route.query.node_id)
  if (nodeId) {
    let node = nodes.value.find(item => item.id === nodeId)
    if (!node) {
      try {
        node = await getProxyNode(nodeId)
        nodes.value = [node]
        total.value = 1
      } catch {
        ElMessage.error('无法加载该节点')
      }
    }
    if (node) {
      nodeTable.value?.toggleRowExpansion(node, true)
      expandedNodeIds.value = [node.id]
    }
  }
})
</script>

<style scoped>
.resource-expand-trigger { display: block; width: 100%; padding: 0; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; line-height: inherit; overflow-wrap: anywhere; }
.resource-expand-trigger:hover { color: var(--el-color-primary); }
.resource-expand-trigger:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.resource-state-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 20px; }
.resource-state-grid > section { min-width: 0; }
.state-note { margin-top: 5px; font-size: 11px; color: #909399; }
@media (max-width: 1100px) { .resource-state-grid { grid-template-columns: minmax(0, 1fr); gap: 10px; } }
.node-inline-details { box-sizing: border-box; max-width: 100%; padding: 10px 16px; background: #f8fafc; font-size: 12px; }
.inline-detail-fields, .inline-detail-section { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; line-height: 22px; }
.inline-detail-fields b, .inline-detail-section b { margin-right: 8px; color: #909399; font-weight: 500; }
.inline-detail-section { margin-top: 6px; overflow-wrap: anywhere; }
.proxy-node-manage {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
}

.card-title {
  font-weight: 600;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

@media (max-width: 767px) {
  .header-actions .el-button span {
    display: none;  /* 移动端只显示图标 */
  }
}

/* 筛选栏 */
.filter-form {
  margin-bottom: 12px;
  flex-wrap: wrap;
}

/* 批量操作工具栏 */
.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #ecf5ff;
  border-radius: 4px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.batch-info {
  font-size: 13px;
  color: #409eff;
  font-weight: 500;
}

/* 到期高亮 */
.expiring-soon {
  color: #e6a23c;
  font-weight: 600;
}

/* 测试结果 */
.test-result {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

/* 分页 */
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

/* 表单分组标题 */
.form-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 12px;
  padding-left: 4px;
  border-left: 3px solid #409eff;
}

/* 导入错误列表 */
.import-error-item {
  font-size: 12px;
  color: #f56c6c;
  padding: 2px 0;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .proxy-node-manage {
    padding: 8px;
  }

  .header-actions {
    flex-wrap: wrap;
    gap: 4px;
  }

  .filter-form :deep(.el-form-item) {
    margin-bottom: 8px;
  }
}
</style>
