<template>
  <div class="email-page">
    <div class="page-heading">
      <div>
        <h2>邮箱管理</h2>
        <span>可复用邮箱资源 · 当前关联和累计关联分开查看</span>
      </div>
      <div class="heading-actions">
        <el-button v-if="canCheck && selected.length" :loading="checking" @click="checkSelected">检测选中 {{ selected.length }}</el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">新增邮箱</el-button>
        <el-button v-if="canImport" @click="importVisible = true">批量导入</el-button>
      </div>
    </div>

    <el-card class="filter-card" shadow="never">
      <div class="filters">
        <el-select v-model="filters.platform" clearable filterable placeholder="已注册平台标签" @change="page = 1; load()"><el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.name" /></el-select>
        <el-input v-model="filters.keyword" clearable placeholder="搜索邮箱/辅助邮箱" @keyup.enter="load" @clear="load" />
        <el-select v-model="filters.management_status" clearable placeholder="使用状态" @change="load">
          <el-option v-for="status in statuses" :key="status" :label="status" :value="status" />
        </el-select>
        <el-button type="primary" plain @click="load">搜索</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <div class="batch-actions">
        <span>已选 {{ selected.length }} 个邮箱</span>
        <el-button v-if="canManage" type="primary" :disabled="!selected.length || loading" @click="openBatchSale">批量售出</el-button>
        <el-button v-if="canManage" :disabled="!selected.length || loading || batchStatusSaving" @click="openBatchStatus('management')">批量修改使用状态</el-button>
        <el-button v-if="canManage" :disabled="!selected.length || loading || batchStatusSaving" @click="openBatchStatus('check')">批量修改检测状态</el-button>
        <el-button :disabled="!selected.length || loading" @click="copySelectedCredentials">复制选中资料</el-button>
        <el-button :disabled="!selected.length || loading" @click="copySelectedEmails">复制选中邮箱</el-button>
        <el-button v-if="selected.length" link @click="tableRef.clearSelection()">清空选择</el-button>
      </div>
      <crm-table table-id="emails" remote :query="tableQuery" @query-change="handleTableQuery" class="email-table" ref="tableRef" v-loading="loading" :data="items" row-key="id" stripe @expand-change="handleExpand" @selection-change="selected = $event">
        <el-table-column column-key="selection" table-tools-disabled type="selection" width="40" />
        <el-table-column column-key="expand" table-tools-disabled type="expand" width="42">
          <template #default="{ row }">
            <div class="email-expanded">
              <div class="detail-grid">
                <span class="credential-field"><b>邮箱密码</b><span class="credential-value">{{ row.showPassword ? row.password : mask(row.password) }}</span><span v-if="row.password" class="credential-actions"><el-button link @click="row.showPassword = !row.showPassword">{{ row.showPassword ? '隐藏' : '显示' }}</el-button><el-button link type="primary" @click="copy(row.password, '邮箱密码')">复制密码</el-button></span></span>
                <span class="credential-field"><b>辅助邮箱</b><span class="credential-value">{{ row.recovery_email || '—' }}</span><el-button v-if="row.recovery_email" link type="primary" @click="copy(row.recovery_email, '辅助邮箱')">复制辅助邮箱</el-button></span>
                <span class="credential-field"><b>2FA 密钥</b><span class="credential-value">{{ row.showTotp ? row.totp_secret : mask(row.totp_secret) }}</span><span v-if="row.totp_secret" class="credential-actions"><el-button link @click="row.showTotp = !row.showTotp">{{ row.showTotp ? '隐藏密钥' : '显示密钥' }}</el-button><el-button link type="primary" @click="copy(row.totp_secret, '2FA 密钥')">复制 2FA 密钥</el-button></span><EmailTotp v-if="row.totp_secret" :key="row.id" :email-id="row.id" @copy="value => copy(value, '2FA 验证码')" /></span>
                <span><b>注册</b>{{ row.account_created_at || row.account_created_year || '—' }}</span>
                <span><b>检测</b>{{ row.gmail_check_status || '未检测' }}<span v-if="row.gmail_check_raw_status === '手动标记'" class="manual-check-note">（人工标记，未实际检测）</span></span>
                <span><b>添加人</b>{{ row.registrant || '—' }}</span>
                <span><b>使用人</b>{{ row.operator || '—' }}</span>
                <span><b>采购</b>{{ row.purchase_channel || '—' }} · {{ money(row.purchase_price) }} · {{ row.purchase_date || '—' }}</span>
                <span><b>出售</b>{{ row.sale_customer || '—' }} · {{ money(row.sale_price) }} · {{ row.sale_date || '—' }}</span>
                <span><b>出售人</b>{{ row.sellers?.join(' / ') || '—' }}</span>
                <span><b>手机</b>{{ row.device_name || '未绑定' }}</span>
                <span><b>节点</b>{{ row.node_ip || '未绑定' }}</span>
              </div>
              <details v-if="row.assetHistory?.length"><summary>手机 / 节点关联轨迹（{{ row.assetHistory.length }}）</summary><div v-for="entry in row.assetHistory" :key="entry.id" class="relation-item"><b>{{ entry.kind }} · {{ entry.name }}</b><el-tag size="small" :type="entry.unbound_at ? 'info' : 'success'">{{ entry.unbound_at ? '历史关联' : '当前关联' }}</el-tag><span>{{ formatDate(entry.bound_at) }}{{ entry.unbound_at ? ` → ${formatDate(entry.unbound_at)}` : '' }}</span><span>{{ entry.operator }}</span></div></details>
              <div class="relation-heading">
                <b>关联轨迹</b><span>累计 {{ row.relations?.length || 0 }} 次</span>
                <el-button v-if="canLink" size="small" type="primary" plain @click="openBind(row)">关联账号</el-button>
              </div>
              <el-empty v-if="!row.relations?.length" description="暂无关联记录" :image-size="42" />
              <div v-else class="relation-list">
                <div v-for="relation in row.relations" :key="relation.id" class="relation-item">
                  <span class="relation-main">{{ relation.platform?.toUpperCase() }} · {{ relation.account }}</span>
                  <el-tag size="small" :type="relation.unbound_at ? 'info' : 'success'">{{ relation.unbound_at ? '已解绑' : '当前关联' }}</el-tag>
                  <span class="relation-time">{{ formatDate(relation.bound_at) }}{{ relation.unbound_at ? ` → ${formatDate(relation.unbound_at)}` : '' }}</span>
                  <span class="relation-time">{{ relation.operator }}{{ relation.unbound_by ? ` / 解绑：${relation.unbound_by}` : '' }}</span>
                  <el-button v-if="canLink && !relation.unbound_at" link type="danger" @click="unbind(row, relation)">解绑</el-button>
                </div>
              </div>
              <div v-if="row.remark" class="remark">备注：{{ row.remark }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column column-key="email" prop="email" filter-type="text" label="邮箱" min-width="250">
          <template #default="{ row }">
            <el-button class="email-name" link @click="tableRef.toggleRowExpansion(row)">{{ row.email }}</el-button>
            <div class="email-copy-actions">
              <el-button link type="primary" @click="copy(row.email, '邮箱')">复制邮箱</el-button>
              <el-button v-if="row.password" link type="primary" @click="copy(row.password, '邮箱密码')">复制密码</el-button>
              <el-button link type="primary" @click="copyCredentials(row)">复制资料</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column column-key="country" filter-type="text" prop="country" label="国家" width="110" />
        <el-table-column column-key="platform_tags" prop="platform_tags" filter-type="text" :table-fields="[{ prop: 'platform_tags', label: '已注册平台', type: 'text' }, { prop: 'claimed_by', label: '领取人', type: 'text' }, { prop: 'claimed_platform', label: '领取平台', type: 'text' }]" label="平台注册 / 领取" min-width="220"><template #default="{ row }"><el-tag v-for="tag in row.platform_tags" :key="tag" size="small" style="margin:2px">{{ tag }}<span v-if="row.platform_registrants?.[tag]"> · {{ row.platform_registrants[tag] }}</span></el-tag><span v-if="!row.platform_tags?.length">未标记</span><div v-if="row.claimed_by" class="remark">{{ row.claimed_by }} 正在注册 {{ row.claimed_platform }}</div></template></el-table-column>
        <el-table-column column-key="gmail_check_status" prop="gmail_check_status" filter-type="text" label="检测状态" width="145">
          <template #default="{ row }"><el-tag size="small" :type="checkTag(row.gmail_check_status)">{{ row.gmail_check_status || '未检测' }}</el-tag><el-tag v-if="row.gmail_check_raw_status === '手动标记'" class="manual-check-tag" size="small" type="info" title="人工标记状态，未实际检测">手动</el-tag></template>
        </el-table-column>
        <el-table-column column-key="current_relation_count" prop="current_relation_count" filter-type="number" label="当前关联" width="110" align="center">
          <template #default="{ row }"><span class="count">{{ row.current_relation_count }}</span> 个账号</template>
        </el-table-column>
        <el-table-column column-key="management_status" prop="management_status" filter-type="enum" :filter-options="statuses.map(status => ({ label: status, value: status }))" label="使用状态" width="110">
          <template #default="{ row }"><el-tag size="small" :type="statusTag(row.management_status)">{{ row.management_status }}</el-tag></template>
        </el-table-column>
        <el-table-column column-key="gmail_checked_at" prop="gmail_checked_at" filter-type="date" label="最后检测" width="165"><template #default="{ row }">{{ formatDate(row.gmail_checked_at) }}</template></el-table-column>
        <el-table-column column-key="device_name" filter-type="text" prop="device_name" label="绑定手机" width="110" />
        <el-table-column column-key="node_ip" filter-type="text" prop="node_ip" label="绑定节点" width="170" />
        <el-table-column column-key="purchase_channel" prop="purchase_channel" filter-type="text" :table-fields="[{ prop: 'purchase_channel', label: '采购渠道', type: 'text' }, { prop: 'purchase_price', label: '采购金额', type: 'number' }, { prop: 'purchase_date', label: '采购日期', type: 'date' }, { prop: 'sale_customer', label: '出售客户', type: 'text' }, { prop: 'sale_price', label: '出售金额', type: 'number' }, { prop: 'sale_date', label: '出售日期', type: 'date' }]" label="采购 / 出售" width="180"><template #default="{ row }"><div>{{ row.purchase_channel || '未登记采购' }} · {{ money(row.purchase_price) }}</div><div>{{ row.sale_customer || '未登记出售' }} · {{ money(row.sale_price) }}</div></template></el-table-column>
        <el-table-column column-key="actions" table-tools-disabled label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canCheck && row.email.endsWith('@gmail.com')" :disabled="checking" link type="primary" @click="check(row)">检测</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage && !row.current_relation_count" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </crm-table>
      <div class="pager"><span>共 {{ total }} 条</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[50, 100, 200, 500]" layout="sizes, prev, pager, next" :total="total" @current-change="load" @size-change="page = 1; load()" /></div>
    </el-card>

    <el-dialog v-model="batchStatusVisible" :title="batchStatusTitle" width="min(560px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!batchStatusSaving" :show-close="!batchStatusSaving" :before-close="closeBatchStatus" @closed="batchStatusRows = []">
      <p>本次修改 {{ batchStatusRows.length }} 个邮箱的{{ batchStatusKind === 'management' ? '使用状态' : '检测状态' }}。</p>
      <p class="import-tip">{{ batchStatusKind === 'management' ? '统一更新使用状态。出售邮箱请使用“批量售出”登记交易资料；已出售或领取中的邮箱请先处理后再选择。' : '手动标记检测状态，不会发起 Gmail 检测；会清除原检测时间，检测状态旁显示“手动”。选择“未检测”将清空原标记。' }}</p>
      <el-alert v-if="batchStatusError" class="batch-status-error" :title="batchStatusError" type="error" :closable="false" show-icon />
      <el-form label-width="100px" :disabled="batchStatusSaving">
        <el-form-item label="目标状态" required>
          <el-select v-model="batchStatusValue" placeholder="请选择目标状态" aria-label="目标状态" style="width:100%">
            <el-option v-for="option in batchStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <details class="sale-email-list"><summary>查看本次修改的邮箱（{{ batchStatusRows.length }} 个）</summary><div v-for="row in batchStatusRows" :key="row.id">{{ row.email }}</div></details>
      <template #footer><el-button :disabled="batchStatusSaving" @click="batchStatusVisible = false">取消</el-button><el-button type="primary" :loading="batchStatusSaving" :disabled="batchStatusSaving" @click="submitBatchStatus">确认修改</el-button></template>
    </el-dialog>

    <el-dialog v-model="batchSaleVisible" title="批量售出邮箱" width="min(620px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!batchSelling" :show-close="!batchSelling" @closed="batchSaleRows = []">
      <template v-if="!batchSaleCompleted">
        <p>本次售出 {{ batchSaleRows.length }} 个邮箱，统一登记以下信息。</p>
        <el-form label-width="140px" :disabled="batchSelling">
          <el-form-item label="出售客户" required><el-input v-model="batchSale.sale_customer" maxlength="255" placeholder="填写客户名称" /></el-form-item>
          <el-form-item label="出售单价（每个）" required><el-input-number v-model="batchSale.sale_price" :min="0" :max="99999999.99" :precision="2" controls-position="right" style="width:100%" /></el-form-item>
          <el-form-item label="出售日期" required><el-date-picker v-model="batchSale.sale_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
          <el-form-item label="出售人" required>
            <SellerSelector v-if="auth.hasPermission('team:member:view')" v-model="batchSale.sellers" :disabled="batchSelling" />
            <el-input v-else :model-value="batchSale.sellers.join(' / ')" readonly />
          </el-form-item>
        </el-form>
        <p class="sale-total">{{ batchSaleRows.length }} 个 × {{ money(batchSale.sale_price) }}，合计 {{ money(batchSaleTotal) }}</p>
        <details class="sale-email-list"><summary>查看本次售出的邮箱（{{ batchSaleRows.length }} 个）</summary><div v-for="row in batchSaleRows" :key="row.id">{{ row.email }}</div></details>
      </template>
      <template v-else>
        <el-alert :title="`成功售出 ${batchSaleRows.length} 个邮箱`" type="success" :closable="false" />
        <p>{{ batchSale.sale_customer }} · 合计 {{ money(batchSaleTotal) }} · {{ batchSale.sale_date }}</p>
        <p class="import-tip">交付格式：邮箱----密码----辅助邮箱----2FA 密钥，每行一个邮箱。可重新复制或直接选中下方资料手动复制。</p>
        <el-input class="delivery-text" :model-value="batchDeliveryText" type="textarea" :rows="8" readonly />
      </template>
      <template #footer>
        <template v-if="batchSaleCompleted"><el-button @click="batchSaleVisible = false">完成</el-button><el-button type="primary" @click="copyBatchDelivery">复制交付资料</el-button></template>
        <template v-else><el-button :disabled="batchSelling" @click="batchSaleVisible = false">取消</el-button><el-button type="primary" :loading="batchSelling" :disabled="batchSelling" @click="sellBatch">确认售出并复制资料</el-button></template>
      </template>
    </el-dialog>

    <el-dialog v-model="formVisible" :title="editing ? '编辑邮箱' : '新增邮箱'" width="760px" top="5vh">
      <el-form label-width="100px">
        <el-form-item label="邮箱" required><el-input v-model="form.email" :disabled="editing" /></el-form-item>
        <el-form-item label="邮箱密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="辅助邮箱"><el-input v-model="form.recovery_email" /></el-form-item>
        <el-form-item label="2FA 密钥"><el-input v-model="form.totp_secret" type="password" show-password /></el-form-item>
        <el-form-item label="注册时间"><el-input v-model="form.account_created_at" placeholder="YYYY-MM-DD 或 YYYY-MM-DD HH:mm:ss，也可只填年份" /></el-form-item>
        <el-form-item label="国家"><el-input v-model="form.country" /></el-form-item>
        <el-form-item label="使用状态"><el-select v-model="form.management_status"><el-option v-for="status in statuses" :key="status" :label="status" :value="status" /></el-select></el-form-item>
        <el-form-item label="已注册平台"><el-select v-model="form.platform_tags" multiple filterable placeholder="选择已注册的平台" style="width:100%"><el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.name" /></el-select></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="绑定手机"><el-select v-model="form.device_id" filterable clearable @visible-change="loadAssetOptions"><el-option v-for="device in devices" :key="device.id" :label="device.name" :value="device.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="绑定节点"><el-select v-model="form.node_id" filterable clearable @visible-change="loadAssetOptions"><el-option v-for="node in nodes" :key="node.id" :label="`${node.ip}:${node.port}`" :value="node.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购渠道" :required="!editing"><el-input v-model="form.purchase_channel" placeholder="例如：供应商、自注册" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购成本" :required="!editing"><el-input-number v-model="form.purchase_price" :min="0" :precision="2" placeholder="免费来源请填 0" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购日期"><el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <template v-if="form.management_status === '已出售'">
            <el-col :span="12"><el-form-item label="出售客户" required><el-input v-model="form.sale_customer" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="出售金额" required><el-input-number v-model="form.sale_price" :min="0" :precision="2" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="出售日期" required><el-date-picker v-model="form.sale_date" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="出售人" required><SellerSelector v-model="form.sellers" /></el-form-item></el-col>
          </template>
          <el-col :span="12"><el-form-item label="使用人"><SellerSelector v-model="form.operator" :multiple="false" placeholder="选择使用人" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="formVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="批量导入邮箱" width="620px">
      <el-upload :auto-upload="false" :show-file-list="false" accept=".txt" :on-change="readImportFile"><el-button size="small">读取 TXT 文件</el-button></el-upload>
      <el-input v-model="importText" type="textarea" :rows="8" placeholder="邮箱----密码----辅助邮箱----2FA&#10;邮箱----密码----2FA----国家&#10;邮箱----密码----辅助邮箱----2FA----国家&#10;三至六项可混合粘贴；保留连续分隔符中的空字段" />
      <el-row :gutter="12" class="import-trade-fields">
        <el-col :span="12"><el-form-item label="字段格式"><el-select v-model="importFormat" style="width:100%">
          <el-option label="逐行识别混合格式" value="auto" />
          <el-option label="三项：邮箱/密码/2FA" value="credentials_3" />
          <el-option label="四项：邮箱/密码/辅助邮箱/2FA（强制）" value="credentials_4" />
          <el-option label="四项：邮箱/密码/辅助邮箱或2FA/国家" value="country_4" />
          <el-option label="五项：邮箱/密码/辅助邮箱或2FA/2FA/国家" value="country_5" />
          <el-option label="六项：再加注册时间/国家" value="full_6" />
        </el-select></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="分隔符"><el-select v-model="importDelimiter" style="width:100%">
          <el-option label="自动识别" value="auto" /><el-option label="----" value="----" /><el-option label="竖线 |" value="|" /><el-option label="冒号 :" value=":" />
          <el-option label="英文逗号 ," value="," /><el-option label="中文逗号 ，" value="，" /><el-option label="制表符 Tab" :value="'\t'" />
        </el-select></el-form-item></el-col>
      </el-row>
      <el-row :gutter="12" class="import-trade-fields">
        <el-col :span="12"><el-form-item label="采购渠道" required><el-input v-model="importPurchaseChannel" placeholder="例如：供应商" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="采购成本（每个）" required><el-input-number v-model="importPurchasePrice" :min="0" :precision="2" placeholder="单个邮箱成本" controls-position="right" style="width:100%" /></el-form-item></el-col>
      </el-row>
      <div class="import-tip">自动模式逐行识别三至六项和 ----、|、:、英文/中文逗号、Tab，可混合粘贴。第三项可为辅助邮箱或 2FA；四项末列若为明确国家代码或名称，自动按国家处理。需要固定第四项为 2FA 时选择强制格式。连续 ---- 中的空字段会保留，辅助邮箱可填 null 或留空；密码按原文保存。国家支持代码或名称，重复邮箱自动跳过。采购渠道和单个邮箱成本必填，免费来源请填写 0。</div>
      <div v-if="importResult" class="import-result">成功 {{ importResult.success }} · 重复 {{ importResult.duplicates }} · 失败 {{ importResult.failed }}{{ checkingImport ? ' · 正在检测新 Gmail…' : (importCheckResult ? ` · 已检测 ${importCheckResult.checked} 个` : '') }}</div>
      <div v-for="result in importResult?.rows?.filter(row => row._result === 'failed') || []" :key="result.line" class="import-result">第 {{ result.line }} 行：{{ result._reason }}</div>
      <template #footer><el-button @click="importVisible = false">取消</el-button><el-button type="primary" :loading="importing" @click="importData">导入</el-button></template>
    </el-dialog>

    <el-dialog v-model="bindVisible" title="关联运营账号" width="520px">
      <el-select v-model="bindAccountId" filterable remote clearable placeholder="搜索运营账号" :remote-method="searchAccounts" style="width:100%">
        <el-option v-for="account in accountOptions" :key="account.id" :label="account.label" :value="account.id" />
      </el-select>
      <el-input v-model="bindRemark" placeholder="关联备注（可选）" style="margin-top:14px" />
      <template #footer><el-button @click="bindVisible = false">取消</el-button><el-button type="primary" :loading="binding" @click="bind">确认关联</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { useTableQuery } from '@/composables/useTableQuery'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listEmails, createEmail, updateEmail, batchSellEmails, batchUpdateEmailStatus, deleteEmail, importEmails, checkEmails, getEmailRelations, getEmailAccountOptions, bindEmailAccount, unbindEmailAccount, getEmailPlatforms } from '@/api/emails'
import { useAuthStore } from '@/stores/auth'
import request from '@/api/request'
import { getDevices } from '@/api/devices'
import { getProxyNodes } from '@/api/proxy_nodes'
import SellerSelector from '@/components/SellerSelector.vue'
import { copyText } from '@/utils/clipboard'
import { saleInformationError } from '@/utils/saleValidation'
import EmailTotp from '@/components/EmailTotp.vue'

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('email:manage'))
const canImport = computed(() => auth.hasPermission('email:import'))
const canCheck = computed(() => auth.hasPermission('email:check'))
const canLink = computed(() => canManage.value && auth.hasPermission('op_account:edit') && auth.hasPermission('op_account:view'))
const selected = ref([])
const checking = ref(false)
const tableRef = ref(null)
const statuses = ['闲置', '使用中', '锁定', '已出售', '废弃']
const platforms = ref([])
const devices = ref([])
const nodes = ref([])
const tradeDefaults = () => ({ device_id: null, node_id: null, purchase_channel: '', purchase_price: null, purchase_date: null, sale_customer: '', sale_price: null, sale_date: null, sellers: [], operator: '' })
const money = (value) => value == null ? '—' : `¥${Number(value).toFixed(2)}`
const loadAssetOptions = async (visible) => {
  if (!visible) return
  if (auth.hasPermission('device:view')) devices.value = (await getDevices({ limit: 200, device_type: 'phone' })).items
  if (auth.hasPermission('proxy_node:view')) nodes.value = (await getProxyNodes({ limit: 500 })).items.filter(node => ['idle', 'active'].includes(node.status))
}
const { tableQuery, queryParams } = useTableQuery('emails')
const handleTableQuery = (nextQuery) => { tableQuery.value = nextQuery; page.value = 1; load() }

const filters = reactive({ keyword: '', management_status: '', platform: '' })
const items = ref([]); const total = ref(0); const page = ref(1); const pageSize = ref(50); const loading = ref(false)
const formVisible = ref(false); const editing = ref(false); const saving = ref(false)
const form = reactive({ email: '', password: '', recovery_email: '', totp_secret: '', account_created_at: '', account_created_year: null, country: '', management_status: '闲置', platform_tags: [], remark: '' })
const importVisible = ref(false); const importText = ref(''); const importFormat = ref('auto'); const importDelimiter = ref('auto'); const importPurchaseChannel = ref(''); const importPurchasePrice = ref(null); const importResult = ref(null); const importing = ref(false); const checkingImport = ref(false); const importCheckResult = ref(null)
const bindVisible = ref(false); const binding = ref(false); const bindEmail = ref(null); const bindAccountId = ref(null); const bindRemark = ref(''); const accountOptions = ref([])
const batchSaleVisible = ref(false); const batchSelling = ref(false); const batchSaleCompleted = ref(false); const batchSaleRows = ref([])
const batchStatusVisible = ref(false); const batchStatusSaving = ref(false); const batchStatusRows = ref([])
const batchStatusKind = ref('management'); const batchStatusValue = ref(''); const batchStatusError = ref('')
const batchStatusTitle = computed(() => batchStatusKind.value === 'management' ? '批量修改使用状态' : '批量修改检测状态')
const batchStatusOptions = computed(() => (batchStatusKind.value === 'management' ? ['闲置', '使用中', '锁定', '废弃'] : ['正常', '封禁', '验证', '未注册', '检测失败', '未检测']).map(value => ({ value, label: value === '未检测' ? '未检测（清空标记）' : value })))
const batchSale = reactive({ sale_customer: '', sale_price: null, sale_date: '', sellers: [] })
const batchSaleTotal = computed(() => batchSale.sale_price == null ? null : Math.round(batchSale.sale_price * 100) * batchSaleRows.value.length / 100)
const deliveryText = (rows) => rows.map(row => [row.email, row.password || '', row.recovery_email || '', row.totp_secret || ''].join('----')).join('\n')
const batchDeliveryText = computed(() => deliveryText(batchSaleRows.value))

const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
const mask = (value) => value ? '••••••' : '—'
const copy = async (value, label) => {
  try { await copyText(value); ElMessage.success(`已复制${label}`) }
  catch { ElMessage.warning('复制失败，请展开详情后手动复制') }
}
const copyCredentials = (row) => copy([
  `邮箱：${row.email}`,
  `邮箱密码：${row.password || ''}`,
  `辅助邮箱：${row.recovery_email || ''}`,
  `2FA 密钥：${row.totp_secret || ''}`,
].join('\n'), '登录资料')
const copySelectedCredentials = () => copy(deliveryText(selected.value), `${selected.value.length} 个邮箱的登录资料`)
const copySelectedEmails = () => copy(selected.value.map(row => row.email).join('\n'), `${selected.value.length} 个邮箱`)
const copyBatchDelivery = async () => {
  try { await copyText(batchDeliveryText.value); ElMessage.success(`已复制 ${batchSaleRows.value.length} 个邮箱的交付资料`) }
  catch { ElMessage.warning('售出已保存，复制失败，请手动复制下方交付资料或重试') }
}
const openBatchStatus = (kind) => {
  if (!canManage.value || !selected.value.length || batchStatusSaving.value) return
  if (selected.value.length > 500) return ElMessage.warning('每次最多修改 500 个邮箱')
  if (kind === 'management' && selected.value.some(row => row.management_status === '已出售')) return ElMessage.warning('选中邮箱包含已出售记录，请取消选择后重试')
  if (kind === 'management' && selected.value.some(row => row.claimed_by)) return ElMessage.warning('选中邮箱正在被领取使用，请先完成注册或归还后再修改使用状态')
  batchStatusKind.value = kind
  batchStatusValue.value = ''
  batchStatusError.value = ''
  batchStatusRows.value = selected.value.map(({ id, email }) => ({ id, email }))
  batchStatusVisible.value = true
}
const closeBatchStatus = (done) => { if (!batchStatusSaving.value) done() }
const submitBatchStatus = async () => {
  if (!canManage.value || batchStatusSaving.value || !batchStatusRows.value.length) return
  if (!batchStatusOptions.value.some(option => option.value === batchStatusValue.value)) return ElMessage.warning('请选择目标状态')
  const field = batchStatusKind.value === 'management' ? 'management_status' : 'gmail_check_status'
  const count = batchStatusRows.value.length
  batchStatusSaving.value = true
  batchStatusError.value = ''
  try {
    try { await batchUpdateEmailStatus({ email_ids: batchStatusRows.value.map(row => row.id), [field]: batchStatusValue.value === '未检测' ? null : batchStatusValue.value }) }
    catch (error) {
      const detail = error?.response?.data?.detail
      batchStatusError.value = typeof detail === 'string' ? detail : '修改失败，请重试'
      return
    }
    tableRef.value?.clearSelection()
    selected.value = []
    batchStatusVisible.value = false
    ElMessage.success(`已修改 ${count} 个邮箱的${batchStatusKind.value === 'management' ? '使用状态' : '检测状态'}`)
    try { await load() }
    catch { ElMessage.warning('状态已保存，列表刷新失败，请稍后刷新') }
  } finally { batchStatusSaving.value = false }
}
const openBatchSale = () => {
  if (!selected.value.length || !canManage.value) return
  if (selected.value.some(row => row.management_status === '已出售')) return ElMessage.warning('选中邮箱包含已出售记录，请取消选择后重试')
  if (selected.value.some(row => row.claimed_by)) return ElMessage.warning('选中邮箱正在被领取使用，请取消选择后重试')
  const today = new Date()
  Object.assign(batchSale, { sale_customer: '', sale_price: null, sale_date: `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`, sellers: auth.user?.username ? [auth.user.username] : [] })
  batchSaleRows.value = selected.value.map(row => ({ ...row }))
  batchSaleCompleted.value = false
  batchSaleVisible.value = true
}
const sellBatch = async () => {
  if (batchSelling.value || batchSaleCompleted.value || !canManage.value) return
  const error = saleInformationError(batchSale, true)
  if (error) return ElMessage.warning(error)
  batchSelling.value = true
  try {
    try { await batchSellEmails({ ...batchSale, sale_customer: batchSale.sale_customer.trim(), email_ids: batchSaleRows.value.map(row => row.id) }) }
    catch { return }
    batchSaleCompleted.value = true
    tableRef.value?.clearSelection()
    selected.value = []
    await copyBatchDelivery()
    try { await load() }
    catch { ElMessage.warning('售出已保存，列表刷新失败，请稍后刷新') }
  } finally { batchSelling.value = false }
}
const statusTag = (value) => ({ '使用中': 'success', '已出售': 'warning', '锁定': 'warning', '废弃': 'danger' }[value] || 'info')
const checkTag = (value) => ({ 正常: 'success', 封禁: 'danger', 验证: 'warning', 未注册: 'info' }[value] || 'info')
const load = async () => { loading.value = true; try { const data = await listEmails({ ...filters, ...queryParams.value, skip: (page.value - 1) * pageSize.value, limit: pageSize.value }); items.value = data.items; total.value = data.total } finally { loading.value = false } }
const handleExpand = async (row, expanded) => { if (expanded.some(item => item.id === row.id)) { row.relations = await getEmailRelations(row.id); row.assetHistory = await request.get(`/emails/${row.id}/asset-history`) } }
const resetForm = () => Object.assign(form, { email: '', password: '', recovery_email: '', totp_secret: '', account_created_at: '', account_created_year: null, country: '', management_status: '闲置', platform_tags: [], remark: '' })
const openCreate = () => { editing.value = false; resetForm(); Object.assign(form, tradeDefaults()); formVisible.value = true }
const openEdit = (row) => { editing.value = true; resetForm(); Object.assign(form, tradeDefaults(), row, { password: '', totp_secret: '', account_created_at: row.account_created_at || String(row.account_created_year || '') }); formVisible.value = true }
const save = async () => {
  if (!editing.value && !form.purchase_channel?.trim()) return ElMessage.warning('请填写采购渠道')
  if (!editing.value && (form.purchase_price == null || !Number.isFinite(form.purchase_price) || form.purchase_price < 0)) return ElMessage.warning('请填写有效的采购成本，免费来源请填 0')
  if (form.management_status === '已出售') {
    const error = saleInformationError(form, true)
    if (error) return ElMessage.warning(error)
  }
  saving.value = true
  try {
    const data = Object.fromEntries(['email', 'password', 'recovery_email', 'totp_secret', 'country', 'management_status', 'platform_tags', 'remark'].map(field => [field, form[field]]))
    for (const field of Object.keys(tradeDefaults())) data[field] = form[field] ?? null
    data.device_id = form.device_id || null
    data.node_id = form.node_id || null
    if (editing.value) { if (!data.password) delete data.password; if (!data.totp_secret) delete data.totp_secret }
    const registered = String(form.account_created_at || '').trim()
    data.account_created_at = /^\d{4}$/.test(registered) || !registered ? null : registered
    data.account_created_year = /^\d{4}$/.test(registered) ? Number(registered) : null
    if (editing.value) await updateEmail(form.id, data); else await createEmail(data)
    ElMessage.success('已保存'); formVisible.value = false; await load()
  } finally { saving.value = false }
}
const importData = async () => {
  if (!importText.value.trim()) return ElMessage.warning('请输入邮箱内容')
  if (!importPurchaseChannel.value.trim()) return ElMessage.warning('请填写采购渠道')
  if (importPurchasePrice.value == null || importPurchasePrice.value < 0) return ElMessage.warning('请填写采购成本')
  importing.value = true
  importCheckResult.value = null
  try {
    importResult.value = await importEmails(importText.value, { purchase_channel: importPurchaseChannel.value.trim(), purchase_price: importPurchasePrice.value }, { import_format: importFormat.value, delimiter: importDelimiter.value })
    const ids = (importResult.value.rows || []).filter(row => row._result === 'success' && row._id && row.email?.toLowerCase().endsWith('@gmail.com')).map(row => row._id)
    if (ids.length && canCheck.value) {
      checkingImport.value = true
      let checked = 0
      for (let index = 0; index < ids.length; index += 50) {
        const result = await checkEmails(ids.slice(index, index + 50))
        checked += result.checked || ids.slice(index, index + 50).length
      }
      importCheckResult.value = { checked }
      ElMessage.success(`导入完成，已自动检测 ${checked} 个 Gmail`)
    } else {
      ElMessage.success(ids.length ? '导入完成' : '导入完成，没有可检测的 Gmail')
    }
    await load()
  } catch (error) {
    if (importResult.value?.success) ElMessage.warning('邮箱已导入，但自动检测失败，可稍后手动检测')
    throw error
  } finally { importing.value = false; checkingImport.value = false }
}
const readImportFile = async (file) => { importText.value = await file.raw.text(); importResult.value = null }
const checkSelected = () => checkRows(selected.value)
const check = (row) => checkRows([row])
const checkRows = async (rows) => {
  if (rows.length > 50 || rows.some(row => !row.email.endsWith('@gmail.com'))) return ElMessage.warning('每次请选择 1-50 个 Gmail 邮箱')
  try { await ElMessageBox.confirm('检测仅用于判断邮箱状态，不会发送密码或 2FA。结果来自第三方探测，不代表邮箱一定可以登录。是否继续？', '邮箱状态检测', { type: 'warning' }) } catch { return }
  checking.value = true
  try { await checkEmails(rows.map(row => row.id)); ElMessage.success('检测完成'); await load() }
  finally { checking.value = false }
}
const remove = async (row) => { await ElMessageBox.confirm(`确认删除 ${row.email}？`, '删除邮箱', { type: 'warning' }); await deleteEmail(row.id); ElMessage.success('已删除'); await load() }
const openBind = async (row) => { bindEmail.value = row; bindAccountId.value = null; bindRemark.value = ''; accountOptions.value = await getEmailAccountOptions(); bindVisible.value = true }
const searchAccounts = async (keyword) => { accountOptions.value = await getEmailAccountOptions(keyword) }
const bind = async () => { if (!bindAccountId.value) return ElMessage.warning('请选择运营账号'); binding.value = true; try { await bindEmailAccount(bindEmail.value.id, { op_account_id: bindAccountId.value, remark: bindRemark.value }); bindEmail.value.relations = await getEmailRelations(bindEmail.value.id); bindVisible.value = false; await load(); ElMessage.success('已关联') } finally { binding.value = false } }
const unbind = async (row, relation) => { await ElMessageBox.confirm(`确认解绑 ${relation.account}？历史记录会保留。`, '解除关联', { type: 'warning' }); await unbindEmailAccount(row.id, relation.id); row.relations = await getEmailRelations(row.id); await load(); ElMessage.success('已解绑') }
onMounted(async () => { platforms.value = await getEmailPlatforms(); await load() })
</script>

<style scoped>
.email-page { padding: 12px 16px 28px; }
.page-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
.page-heading h2 { margin:0 0 5px; color:#1f2937; font-size:22px; }
.page-heading span, .import-tip { color:#909399; font-size:13px; }
.heading-actions { display:flex; gap:8px; }
.batch-actions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
.batch-actions > span { color:#606266; font-size:13px; margin-right:4px; }
.batch-actions .el-button { margin-left:0; }
.batch-status-error { margin-bottom:14px; }
.manual-check-tag { margin-left:4px; }
.manual-check-note { color:var(--el-text-color-secondary); font-size:12px; }
.sale-total { font-weight:600; }
.sale-email-list { margin-top:12px; color:#606266; overflow-wrap:anywhere; }
.sale-email-list > div { padding-top:6px; }
.delivery-text { margin-top:10px; }
.filter-card, .table-card { margin-bottom:14px; border-radius:10px; }
.filters { display:flex; gap:10px; max-width:760px; }
.filters .el-input { width:340px; } .filters .el-select { width:140px; }
.count { color:#409eff; font-weight:700; }
.email-name { font-weight:600; font-size:12px; }
.email-copy-actions, .credential-actions { display:flex; flex-wrap:wrap; gap:4px 10px; }
.email-copy-actions { margin-top:4px; }
.email-copy-actions .el-button, .credential-actions .el-button { margin-left:0; }
.email-copy-actions .el-button { font-size:12px; }
.credential-field { display:flex; flex-direction:column; align-items:flex-start; gap:4px; }
.credential-value { user-select:text; overflow-wrap:anywhere; }
.email-table { container-type:inline-size; }
.email-expanded { width:100cqw; box-sizing:border-box; position:sticky; left:0; padding:12px 22px 16px 52px; background:#f8fafc; overflow-wrap:anywhere; }
.detail-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(180px, 100%), 1fr)); gap:8px 26px; padding-bottom:12px; border-bottom:1px solid #ebeef5; }
.detail-grid > span { min-width:0; }
.detail-grid b { display:inline-block; width:72px; color:#909399; font-weight:400; }
.relation-heading { display:flex; align-items:center; gap:10px; padding:12px 0 8px; color:#606266; }
.relation-heading span { color:#909399; font-size:12px; } .relation-heading .el-button { margin-left:auto; }
.relation-list { display:flex; flex-direction:column; gap:6px; }
.relation-item { display:flex; align-items:center; flex-wrap:wrap; gap:10px; min-height:28px; padding:5px 8px; background:#fff; border:1px solid #ebeef5; border-radius:5px; }
.relation-item > * { min-width:0; max-width:100%; }
.relation-main { flex:1 1 250px; font-weight:500; } .relation-time { color:#909399; font-size:12px; }
.remark { margin-top:10px; color:#909399; font-size:12px; }
.pager { display:flex; justify-content:flex-end; align-items:center; flex-wrap:wrap; gap:20px; padding-top:14px; color:#909399; font-size:13px; }
.import-tip { margin-top:10px; line-height:1.6; } .import-result { margin-top:10px; color:#606266; }
@media (max-width:768px) { .email-page { padding:8px; } .page-heading { align-items:flex-start; gap:10px; } .page-heading h2 { font-size:18px; } .filters { flex-wrap:wrap; } .filters .el-input { width:100%; } .filters .el-select { width:140px; } .detail-grid { grid-template-columns:1fr; } .email-expanded { padding:10px; } .relation-item { flex-wrap:wrap; } .relation-main { min-width:0; } }
</style>
