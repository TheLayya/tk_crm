<template>
  <div class="card-key-page">
    <div class="page-heading">
      <div><h2>卡密管理</h2><span>按项目统一领取，避免遗漏和重复使用</span></div>
      <div class="heading-actions"><el-button v-if="canManage" @click="platformVisible = true">平台管理</el-button><el-button v-if="canManage" type="primary" @click="openProject()">＋新建项目</el-button></div>
    </div>
    <el-card shadow="never" class="project-card">
      <div class="toolbar">
        <el-select v-model="selectedId" filterable aria-label="选择项目" placeholder="选择项目" style="width:280px" @change="changeProject">
          <el-option v-for="project in projects" :key="project.id" :label="`${project.name}${project.is_active ? '' : '（已结束）'}`" :value="project.id" />
        </el-select>
        <el-tag v-if="selected" type="success">可领取 {{ selected.available }}</el-tag>
        <el-tag v-if="selected" type="info">已领取 {{ selected.claimed }}</el-tag>
        <el-tag v-if="selected">已消耗 {{ selected.consumed }}</el-tag>
        <el-tag v-if="selected?.target_platform" type="warning">邮箱平台：{{ selected.target_platform }}</el-tag>
        <span class="project-description" :title="selected?.description">{{ selected?.description }}</span>
        <el-button v-if="canManage && selected" :disabled="!selected.is_active" @click="openImport">批量导入</el-button>
        <el-button v-if="canManage && selected" @click="openBatches">批次管理</el-button>
        <el-button v-if="canManage && selected" @click="openProject(selected)">编辑项目</el-button><el-button v-if="canManage && selected" type="danger" plain @click="deleteProject">删除项目</el-button>
      </div>
      <el-alert v-if="selected && !selected.is_active" title="项目已结束，停止新领取，已领取卡密仍可确认消耗" type="warning" :closable="false" />
      <el-empty v-if="!selected" :description="canManage ? '先新建项目，选择协助成员并导入卡密' : '暂无分配给你的项目'" :image-size="70" />
      <div v-if="selected" class="batch-bar" v-loading="loading">
        <strong>领取批次</strong>
        <el-select v-model="selectedBatchId" filterable aria-label="领取批次" placeholder="选择领取批次" class="batch-select" @change="reloadKeys">
          <el-option label="自动选择正常批次" :value="-1" />
          <el-option v-for="batch in currentBatches" :key="batch.id" :label="`${batch.name} · ${batch.status === 'active' ? '可领 ' + batch.available : batchStatusLabel(batch.status)}`" :value="batch.id" />
        </el-select>
        <template v-if="selectedBatch"><el-tag size="small" :type="batchStatusType(selectedBatch.status)">{{ batchStatusLabel(selectedBatch.status) }}</el-tag><span class="batch-counts">库存 {{ selectedBatch.available }} · 待消耗 {{ selectedBatch.claimed }} · 已消耗 {{ selectedBatch.consumed }} · 无效 {{ selectedBatch.invalid }}</span><span v-if="selectedBatch.batch_no" class="muted">{{ selectedBatch.batch_no }}</span></template>
        <span v-else class="muted">按导入顺序领取，自动跳过暂停、归档批次</span>
        <p v-if="selectedBatch?.remark" class="batch-note">批次备注：{{ selectedBatch.remark }}</p>
        <el-alert v-if="selectedBatch && selectedBatch.status !== 'active'" :title="`${batchStatusLabel(selectedBatch.status)}，已停止新领取${selectedBatch.pause_reason ? '：' + selectedBatch.pause_reason : ''}`" type="warning" :closable="false" />
      </div>
      <div v-if="selected" class="claim-bar">
        <div><strong>当前项目</strong><span>{{ selected.name }}</span><small>协助成员：{{ memberLabel(selected.members) }}</small></div>
        <div class="project-metrics"><template v-if="selected.target_platform"><el-tag size="small" type="success">检测正常可领 {{ selected.email_normal_available }}</el-tag><el-tag size="small">可领总数 {{ selected.email_available }}</el-tag><el-tag size="small" type="info">领取中 {{ selected.email_claimed }}</el-tag><el-tag size="small">注册完成 {{ selected.emails_completed }}</el-tag></template><el-popover placement="bottom" width="360" trigger="click"><template #reference><el-button link type="primary">成员完成量</el-button></template><div v-for="stat in selected.member_stats" :key="stat.username" class="member-stat"><span>{{ stat.username }}</span><span>卡密已消耗 {{ stat.consumed }} · 待消耗 {{ stat.claimed }} · 注册 {{ stat.emails_completed }}</span></div></el-popover></div>
        <el-button type="primary" :disabled="!canClaimKey" :loading="claiming" @click="claim">{{ selectedBatch ? '领取所选批次' : '领取下一份' }}</el-button>
      </div>
      <div v-if="pendingKey" class="pending-key">
        <strong>我的待消耗</strong><span class="pending-batch">{{ pendingKey.batch_name || '历史未分批' }}</span><code>{{ pendingKey.content }}</code>
        <el-button size="small" @click="copy(pendingKey.content)">复制</el-button>
        <el-button size="small" type="primary" :loading="consuming" @click="consume(pendingKey)">确认已消耗</el-button>
        <el-button size="small" :disabled="consuming" @click="release(pendingKey)">归还未使用</el-button>
        <el-button size="small" type="danger" plain :disabled="consuming" @click="invalid(pendingKey)">报告无效</el-button>
      </div>
      <el-alert v-if="pendingKey && pendingKey.batch_status && pendingKey.batch_status !== 'active'" class="pending-batch-warning" :title="`待消耗卡密所属批次${batchStatusLabel(pendingKey.batch_status)}${pendingKey.batch_pause_reason ? '：' + pendingKey.batch_pause_reason : ''}。请核实后确认消耗、归还或报告无效；流转记录持续保留。`" type="warning" :closable="false" />
      <div v-if="selected" class="email-claim-bar">
        <div><strong>注册邮箱</strong><span v-if="selected.target_platform">{{ selected.target_platform }}</span><span v-else class="email-platform-empty">未设置目标平台</span><small>{{ pendingEmail ? '注册完成后标记平台并释放' : selected.target_platform ? '领取未注册该平台的闲置邮箱' : '请先设置目标平台，才能领取对应邮箱' }}</small></div>
        <div v-if="!pendingEmail"><el-button v-if="selected.target_platform" type="primary" plain :disabled="!selected.can_claim" :loading="claimingEmail" @click="claimEmailAction">领取邮箱</el-button><el-button v-else-if="canManage" type="primary" plain @click="openProject(selected)">设置目标平台</el-button><el-tag v-else type="info">等待管理员设置</el-tag></div>
        <div v-else class="email-actions"><code>{{ pendingEmail.email }}</code><el-button size="small" @click="copy(pendingEmail.email)">复制邮箱</el-button><el-button v-if="pendingEmail.password" size="small" @click="copy(pendingEmail.password)">复制密码</el-button><el-button v-if="pendingEmail.recovery_email" size="small" @click="copy(pendingEmail.recovery_email)">辅助邮箱</el-button><el-button v-if="totp" size="small" type="success" @click="copy(totp.code)">验证码 {{ totp.code }}（{{ totp.remaining }}s）</el-button><el-button v-else-if="pendingEmail.totp_secret" size="small" @click="copy(pendingEmail.totp_secret)">复制 2FA 密钥</el-button><el-button size="small" type="primary" @click="completeEmailAction">注册完成</el-button><el-button size="small" type="warning" @click="releaseEmailAction">归还</el-button><el-button size="small" type="danger" plain @click="failEmailAction">注册失败</el-button></div>
      </div>
      <div v-if="selected" class="record-filters">
        <strong>{{ canManage ? '卡密记录' : '我的领取记录' }}</strong>
        <el-select v-model="filters.status" clearable placeholder="全部状态" style="width:125px" @change="reloadKeys"><el-option label="可领取" value="available" v-if="canManage" /><el-option label="待消耗" value="claimed" /><el-option label="已消耗" value="consumed" /><el-option label="无效售后" value="invalid" /></el-select>
        <el-checkbox v-if="canManage" v-model="filters.mine" @change="reloadKeys">只看我的</el-checkbox>
        <el-input v-model="filters.keyword" clearable placeholder="搜索卡密 / 链接" style="width:220px" @keyup.enter="reloadKeys" @clear="reloadKeys" /><el-button link type="primary" @click="reloadKeys">搜索</el-button><el-button link type="primary" @click="load">刷新</el-button>
      </div>
      <crm-table table-id="card-key-records" remote :query="tableQuery" @query-change="handleTableQuery" v-if="selected" v-loading="loading" :data="keys" size="small" empty-text="暂无记录，领取后在这里找回">
        <el-table-column column-key="content" prop="content" filter-type="text" label="卡密 / 链接" min-width="420"><template #default="{ row }"><code v-if="row.content">{{ row.content }}</code><span v-else class="muted">领取后可见</span></template></el-table-column>
        <el-table-column column-key="batch_name" prop="batch_name" table-tools-disabled label="批次" min-width="180"><template #default="{ row }"><span>{{ row.batch_name || '历史未分批' }}</span><el-tag v-if="row.batch_status && row.batch_status !== 'active'" class="batch-state-tag" size="small" :type="batchStatusType(row.batch_status)">{{ batchStatusLabel(row.batch_status) }}</el-tag><div v-if="row.batch_remark" class="batch-row-remark" :title="row.batch_remark">{{ row.batch_remark }}</div></template></el-table-column>
        <el-table-column column-key="status" prop="status" filter-type="enum" :filter-options="[{ label: '可领取', value: 'available' }, { label: '待消耗', value: 'claimed' }, { label: '已消耗', value: 'consumed' }, { label: '无效售后', value: 'invalid' }]" label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag><div v-if="row.remark" class="key-remark" :title="row.remark">{{ row.remark }}</div></template></el-table-column>
        <el-table-column column-key="claimed_by" filter-type="text" label="领取人" prop="claimed_by" width="130" />
        <el-table-column column-key="claimed_at" prop="claimed_at" filter-type="date" label="领取时间" width="180"><template #default="{ row }">{{ formatDate(row.claimed_at) }}</template></el-table-column>
        <el-table-column column-key="consumed_at" prop="consumed_at" filter-type="date" label="消耗时间" width="180"><template #default="{ row }">{{ formatDate(row.consumed_at) }}</template></el-table-column>
        <el-table-column column-key="actions" table-tools-disabled label="操作" width="235" fixed="right"><template #default="{ row }"><el-button v-if="row.content" link type="primary" @click="copy(row.content)">复制</el-button><template v-if="row.id !== pendingKey?.id"><el-button v-if="canManage && row.status === 'available'" link type="danger" @click="invalid(row)">标记无效</el-button><template v-if="row.status === 'claimed' && (row.claimed_by === username || canManage)"><el-button :disabled="consuming" link type="primary" @click="consume(row)">确认消耗</el-button><el-button :disabled="consuming" link type="warning" @click="release(row)">归还</el-button></template></template><el-button v-if="canManage || row.claimed_by === username" link @click="editKeyRemark(row)">备注</el-button><el-button v-if="row.history?.length" link @click="historyRow = row">记录</el-button></template></el-table-column>
      </crm-table>
      <el-pagination v-if="total" class="pagination" v-model:current-page="filters.page" :page-size="filters.page_size" :total="total" layout="total, prev, pager, next" @current-change="loadKeys" />
    </el-card>
    <el-dialog :model-value="!!historyRow" title="卡密流转记录" width="min(800px, 94vw)" @close="historyRow = null">
      <crm-table table-id="card-key-flow-history" :data="historyRow?.history || []" size="small"><el-table-column column-key="action" prop="action" filter-type="text" label="操作" width="85"><template #default="{ row }">{{ { claim: '领取', release: '归还', consume: '消耗', invalid: '无效售后', remark: '更新备注' }[row.action] }}</template></el-table-column><el-table-column column-key="username" filter-type="text" prop="username" label="操作人" /><el-table-column column-key="time" prop="time" filter-type="date" label="时间" width="190"><template #default="{ row }">{{ formatDate(row.time) }}</template></el-table-column><el-table-column column-key="remark" filter-type="text" prop="remark" label="备注" min-width="180" /></crm-table>
    </el-dialog>
    <CardKeyWorkReport v-if="canManage && selected" :project-id="selected.id" :project-name="selected.name" />
    <el-dialog v-model="projectVisible" :title="editing ? '编辑项目' : '新建项目'" width="min(600px, 94vw)">
      <el-form label-width="90px"><el-form-item label="项目名称" required><el-input v-model="projectForm.name" /></el-form-item><el-form-item label="项目备注"><el-input v-model="projectForm.description" type="textarea" :rows="3" placeholder="任务说明、上游联系方式、采购批次与售后说明" /></el-form-item><el-form-item label="目标平台"><el-select v-model="projectForm.target_platform" filterable clearable placeholder="选择目标平台" style="width:100%"><el-option v-for="platform in activePlatforms" :key="platform.id" :label="platform.name" :value="platform.name" /></el-select><div class="form-hint">没有合适的平台？关闭此窗口后点击“平台管理”创建。</div></el-form-item><el-form-item label="协助成员" required><el-select v-model="projectForm.members" multiple filterable style="width:100%" @change="normalizeMembers"><el-option label="全员" value="__all__" /><el-option v-for="member in members" :key="member.username" :label="member.real_name ? `${member.username}（${member.real_name}）` : member.username" :value="member.username" /></el-select></el-form-item><el-form-item label="项目状态"><el-switch v-model="projectForm.is_active" active-text="进行中" inactive-text="已结束" /></el-form-item></el-form>
      <template #footer><el-button @click="projectVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProject">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="platformVisible" title="平台管理" width="min(620px, 94vw)">
      <div class="platform-create"><el-input v-model="platformDraft.name" placeholder="例如 TikTok" @keyup.enter="savePlatform" /><el-button type="primary" :loading="platformSaving" @click="savePlatform">{{ platformDraft.id ? '保存修改' : '新增平台' }}</el-button><el-button v-if="platformDraft.id" @click="resetPlatformDraft">取消编辑</el-button></div>
      <crm-table table-id="card-key-platforms" :data="platforms" size="small" empty-text="还没有平台配置"><el-table-column column-key="name" filter-type="text" prop="name" label="平台" /><el-table-column column-key="is_active" prop="is_active" filter-type="enum" :filter-options="[{ label: '启用', value: true }, { label: '禁用', value: false }]" label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column column-key="actions" table-tools-disabled fixed="right" label="操作" width="180"><template #default="{ row }"><el-button link type="primary" @click="editPlatform(row)">编辑</el-button><el-button link :type="row.is_active ? 'warning' : 'success'" @click="togglePlatform(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template></el-table-column></crm-table>
      <template #footer><el-button @click="platformVisible=false">关闭</el-button></template>
    </el-dialog>
    <el-dialog v-model="completeVisible" title="注册完成并创建运营账号" width="min(520px, 94vw)"><el-form label-width="100px"><el-form-item label="注册邮箱"><span>{{ pendingEmail?.email }}</span></el-form-item><el-form-item label="平台账号" required><el-input v-model="completeForm.account" placeholder="填写刚注册的平台用户名" /></el-form-item><el-form-item label="账号密码"><el-input v-model="completeForm.password" type="password" show-password /></el-form-item><el-form-item label="账号 2FA"><el-input v-model="completeForm.totp_secret" placeholder="没有可留空" /></el-form-item><p class="form-hint">确认后自动创建运营账号、关联当前邮箱、添加平台标签并释放邮箱。</p></el-form><template #footer><el-button @click="completeVisible=false">取消</el-button><el-button type="primary" :loading="completing" @click="submitCompleteEmail">确认完成</el-button></template></el-dialog>
      <el-dialog v-model="importVisible" title="批量导入卡密" width="min(680px, 94vw)" :close-on-click-modal="!importing" :close-on-press-escape="!importing" :show-close="!importing"><p>导入项目：<strong>{{ importTarget.name }}</strong></p><el-form label-width="80px" :disabled="importing"><el-form-item label="批次名称"><el-input v-model="importBatch.name" maxlength="200" placeholder="例如 10月15日 · 供应商 A；留空自动生成" /></el-form-item><el-form-item label="批次备注"><el-input v-model="importBatch.remark" type="textarea" :rows="2" maxlength="2000" show-word-limit placeholder="供应商、采购日期、有效期、使用要求或售后联系方式" /></el-form-item></el-form><p class="hint">每次导入建立一个批次，一行一份；重复内容自动跳过并保留原批次。</p><el-input v-model="importText" :disabled="importing" type="textarea" :rows="10" placeholder="每行粘贴一份卡密或链接" /><template #footer><el-button :disabled="importing" @click="importVisible=false">取消</el-button><el-button type="primary" :loading="importing" @click="saveImport">导入并建立批次</el-button></template></el-dialog>
    <el-dialog v-model="batchVisible" :title="`批次管理 · ${batchTarget.name}`" width="min(1040px, 96vw)" :close-on-click-modal="!batchSaving" :close-on-press-escape="!batchSaving" :show-close="!batchSaving">
      <div class="batch-manager-toolbar"><span class="hint">异常批次先暂停，处理后可恢复；删除时有流转记录的批次会归档保留。</span><el-checkbox v-model="showArchivedBatches" :disabled="batchSaving">显示归档批次</el-checkbox></div>
      <el-alert v-if="batchError" class="batch-error" :title="batchError" type="error" :closable="false" />
      <el-table :data="managedBatches" size="small" v-loading="batchSaving" empty-text="暂无批次，请先导入卡密">
        <el-table-column label="批次 / 备注" min-width="280"><template #default="{ row }"><strong>{{ row.name }}</strong><div class="muted">{{ row.batch_no || '历史存量' }} · {{ row.created_by || '—' }}</div><p v-if="row.remark" class="batch-note">{{ row.remark }}</p><div v-if="row.pause_reason" class="batch-pause-reason">{{ row.pause_reason }}</div></template></el-table-column>
        <el-table-column label="库存 / 流转" min-width="210"><template #default="{ row }"><div>库存 {{ row.available }} · 待消耗 {{ row.claimed }}</div><div class="muted">已消耗 {{ row.consumed }} · 无效 {{ row.invalid }} · 总数 {{ row.total }}</div></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag size="small" :type="batchStatusType(row.status)">{{ batchStatusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="240" fixed="right"><template #default="{ row }"><el-button link type="primary" :disabled="batchSaving" @click="viewBatch(row)">查看</el-button><template v-if="row.id > 0 && row.status !== 'archived'"><el-button link type="primary" :disabled="batchSaving" @click="editBatch(row)">编辑</el-button><el-button link :type="row.status === 'paused' ? 'success' : 'warning'" :disabled="batchSaving" @click="toggleBatch(row)">{{ row.status === 'paused' ? '恢复' : '暂停' }}</el-button><el-button link type="danger" :disabled="batchSaving" @click="deleteBatch(row)">删除</el-button></template><span v-else-if="row.id === 0" class="muted">历史存量</span></template></el-table-column>
      </el-table>
      <template #footer><el-button :disabled="batchSaving" @click="batchVisible=false">关闭</el-button></template>
    </el-dialog>
    <el-dialog v-model="batchEditVisible" title="编辑批次" width="min(540px, 94vw)" :close-on-click-modal="!batchSaving" :close-on-press-escape="!batchSaving" :show-close="!batchSaving"><el-alert v-if="batchError" class="batch-error" :title="batchError" type="error" :closable="false" /><el-form label-width="80px" :disabled="batchSaving"><el-form-item label="批次名称" required><el-input v-model="batchForm.name" maxlength="200" /></el-form-item><el-form-item label="批次备注"><el-input v-model="batchForm.remark" type="textarea" :rows="4" maxlength="2000" show-word-limit /></el-form-item></el-form><template #footer><el-button :disabled="batchSaving" @click="batchEditVisible=false">取消</el-button><el-button type="primary" :loading="batchSaving" @click="saveBatch">保存</el-button></template></el-dialog>
  </div>
</template>

<script setup>
import { useTableQuery } from '@/composables/useTableQuery'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import CardKeyWorkReport from '@/components/CardKeyWorkReport.vue'
import { copyText } from '@/utils/clipboard'
import { updateCardKeyRemark, getCardKeyBatches, updateCardKeyBatch, deleteCardKeyBatch } from '@/api/card_keys'
import { getCardKeyProjects, getCardKeyMembers, createCardKeyProject, updateCardKeyProject, deleteCardKeyProject, importCardKeys, getCardKeys, claimCardKey, consumeCardKey, releaseCardKey, markCardKeyInvalid, getClaimedEmail, getClaimedEmailTotp, claimEmail, releaseEmail, failEmail, completeEmail, getCardKeyPlatforms, createCardKeyPlatform, updateCardKeyPlatform } from '@/api/card_keys'
const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('card_key:manage'))
const username = computed(() => auth.user?.username)
const projects = ref([]); const members = ref([]); const keys = ref([]); const selectedId = ref(null); const loading = ref(false); const claiming = ref(false); const saving = ref(false); const importing = ref(false); const projectVisible = ref(false); const importVisible = ref(false); const editing = ref(false); const importText = ref('')
const projectForm = reactive({ id: null, name: '', description: '', target_platform: '', members: [], is_active: true }); const selected = computed(() => projects.value.find(x => x.id === selectedId.value))
const { tableQuery, queryParams } = useTableQuery('card-key-records')
const handleTableQuery = (nextQuery) => { tableQuery.value = nextQuery; filters.page = 1; loadKeys() }

const filters = reactive({ page: 1, page_size: 30, status: '', mine: false, keyword: '' })
const total = ref(0)
const pendingKey = ref(null)
const pendingEmail = ref(null)
const totp = ref(null)
let totpTimer = null
const claimingEmail = ref(false)
const emailUpdating = ref(false)
const platforms = ref([]); const platformVisible = ref(false); const platformSaving = ref(false); const platformDraft = reactive({ id: null, name: '' })
const completeVisible = ref(false); const completing = ref(false); const completeForm = reactive({ account: '', password: '', totp_secret: '' })
const completeTarget = reactive({ id: null, platform: '' })
const activePlatforms = computed(() => platforms.value.filter(platform => platform.is_active))
const consuming = ref(false)
const historyRow = ref(null)
const importTarget = reactive({ id: null, name: '' })
const importBatch = reactive({ name: '', remark: '' })
const batches = ref([])
const batchesProjectId = ref(null)
const selectedBatchId = ref(-1)
const currentBatches = computed(() => batchesProjectId.value === selectedId.value ? batches.value.filter(batch => batch.status !== 'archived' || batch.id === selectedBatchId.value) : [])
const selectedBatch = computed(() => currentBatches.value.find(batch => batch.id === selectedBatchId.value))
const canClaimKey = computed(() => selected.value?.can_claim && !loading.value && !pendingKey.value && (selectedBatchId.value === -1 ? selected.value.available > 0 : selectedBatch.value?.status === 'active' && selectedBatch.value.available > 0))
const batchVisible = ref(false)
const batchEditVisible = ref(false)
const batchSaving = ref(false)
const batchError = ref('')
const showArchivedBatches = ref(false)
const batchTarget = reactive({ id: null, name: '' })
const batchForm = reactive({ id: null, name: '', remark: '' })
const managedBatches = computed(() => batchesProjectId.value === batchTarget.id ? batches.value.filter(batch => showArchivedBatches.value || batch.status !== 'archived') : [])
const batchStatusLabel = status => ({ active: '正常', paused: '已暂停', archived: '已归档' }[status] || status)
const batchStatusType = status => ({ active: 'success', paused: 'warning', archived: 'info' }[status] || 'info')
let requestVersion = 0
let projectRequestVersion = 0
const clearData = () => {
  requestVersion++
  loading.value = false
  projects.value = []
  selectedId.value = null
  keys.value = []
  total.value = 0
  pendingKey.value = null
  pendingEmail.value = null
  historyRow.value = null
  batches.value = []
  batchesProjectId.value = null
  selectedBatchId.value = -1
  filters.page = 1
}
const load = async () => {
  const version = ++projectRequestVersion
  try {
    const [result, platformResult] = await Promise.all([getCardKeyProjects(), getCardKeyPlatforms()])
    if (version !== projectRequestVersion) return
    projects.value = result
    platforms.value = platformResult
    if (!projects.value.some(project => project.id === selectedId.value)) {
      selectedId.value = projects.value[0]?.id || null
      selectedBatchId.value = -1
      batches.value = []
      batchesProjectId.value = null
      filters.page = 1
      keys.value = []
      total.value = 0
      pendingKey.value = null
      historyRow.value = null
    }
    await loadKeys()
  } catch (error) {
    if (version === projectRequestVersion) clearData()
    throw error
  }
}
const loadKeys = async () => {
  const version = ++requestVersion
  const projectId = selectedId.value
  if (!projectId) { keys.value = []; total.value = 0; pendingKey.value = null; pendingEmail.value = null; batches.value = []; batchesProjectId.value = null; loading.value = false; return }
  loading.value = true
  try {
    const [result, pending, email, batchResult] = await Promise.all([
      getCardKeys(projectId, { ...filters, ...queryParams.value, batch_id: selectedBatchId.value === -1 ? undefined : selectedBatchId.value }),
      getCardKeys(projectId, { mine: true, status: 'claimed', page_size: 1 }),
      selected.value?.target_platform ? getClaimedEmail(projectId) : Promise.resolve(null),
      getCardKeyBatches(projectId, { include_archived: true })
    ])
    if (version !== requestVersion) return
    keys.value = result.items
    total.value = result.total
    pendingKey.value = pending.items[0] || null
    pendingEmail.value = email
    batches.value = batchResult
    batchesProjectId.value = projectId
    if (selectedBatchId.value !== -1 && !batchResult.some(batch => batch.id === selectedBatchId.value)) {
      selectedBatchId.value = -1
      filters.page = 1
      return loadKeys()
    }
    await refreshTotp()
  } catch (error) {
    if (version === requestVersion) {
      keys.value = []
      total.value = 0
      pendingKey.value = null
      pendingEmail.value = null
      historyRow.value = null
      batches.value = []
      batchesProjectId.value = null
    }
    throw error
  } finally { if (version === requestVersion) loading.value = false }
}
const refreshTotp = async () => {
  const projectId = selectedId.value
  const emailId = pendingEmail.value?.id
  totp.value = null
  if (emailUpdating.value || !projectId || !pendingEmail.value?.totp_secret) return
  try { const result = await getClaimedEmailTotp(projectId); if (!emailUpdating.value && selectedId.value === projectId && pendingEmail.value?.id === emailId) totp.value = { ...result, expiresAt: Date.now() + result.remaining * 1000 } }
  catch { if (selectedId.value === projectId && pendingEmail.value?.id === emailId) totp.value = null }
}
const reloadKeys = () => { filters.page = 1; keys.value = []; total.value = 0; historyRow.value = null; return loadKeys() }
const changeProject = () => {
  selectedBatchId.value = -1
  batches.value = []
  batchesProjectId.value = null
  pendingKey.value = null
  pendingEmail.value = null
  totp.value = null
  batchVisible.value = false
  batchEditVisible.value = false
  return reloadKeys()
}
const openProject = (row) => { editing.value = !!row; Object.assign(projectForm, row ? { ...row, members: [...row.members] } : { id: null, name: '', description: '', target_platform: '', members: [], is_active: true }); projectVisible.value = true }
const normalizeMembers = (values) => { if (values.includes('__all__')) projectForm.members = ['__all__'] }
const memberLabel = (values) => values.includes('__all__') ? '全员' : values.join('、')
const saveProject = async () => { if (!projectForm.name.trim() || !projectForm.members.length) return ElMessage.warning('请填写项目名称并选择协助成员'); saving.value = true; try { const data = { name: projectForm.name, description: projectForm.description, target_platform: projectForm.target_platform, members: projectForm.members, is_active: projectForm.is_active }; const result = editing.value ? await updateCardKeyProject(projectForm.id, data) : await createCardKeyProject(data); projectVisible.value = false; await load(); if (selectedId.value !== result.id) { selectedId.value = result.id; await changeProject() } } finally { saving.value = false } }
const deleteProject = async () => { if (!selected.value) return; try { await ElMessageBox.confirm(`确认删除项目“${selected.value.name}”？项目卡密记录也会删除，已有完成记录的项目不能删除。`, '删除项目', { type: 'warning', confirmButtonText: '确认删除' }) } catch { return }; await deleteCardKeyProject(selected.value.id); selectedId.value = null; await load(); ElMessage.success('项目已删除') }
const claimEmailAction = async () => {
  const projectId = selectedId.value
  claimingEmail.value = true
  try { const email = await claimEmail(projectId); if (selectedId.value === projectId) { pendingEmail.value = email; await refreshTotp() }; ElMessage.success('已锁定邮箱，请注册完成后释放') }
  finally { claimingEmail.value = false }
}
const resetPlatformDraft = () => Object.assign(platformDraft, { id: null, name: '' })
const editPlatform = (row) => Object.assign(platformDraft, { id: row.id, name: row.name })
const savePlatform = async () => {
  if (!platformDraft.name.trim()) return ElMessage.warning('请填写平台名称')
  platformSaving.value = true
  try { const data = { name: platformDraft.name, is_active: true }; if (platformDraft.id) await updateCardKeyPlatform(platformDraft.id, data); else await createCardKeyPlatform(data); await load(); resetPlatformDraft(); ElMessage.success('平台已保存') }
  finally { platformSaving.value = false }
}
const togglePlatform = async (row) => { await updateCardKeyPlatform(row.id, { name: row.name, is_active: !row.is_active }); await load(); ElMessage.success(row.is_active ? '平台已停用' : '平台已启用') }
const runEmailTransition = async (projectId, action) => {
  emailUpdating.value = true
  totp.value = null
  try {
    const result = await action()
    if (selectedId.value === projectId) pendingEmail.value = null
    await load()
    return result
  } finally {
    emailUpdating.value = false
    await refreshTotp()
  }
}
const releaseEmailAction = async () => {
  if (emailUpdating.value) return
  const projectId = selectedId.value
  try { await ElMessageBox.confirm('确认尚未注册该平台？已注册请使用“注册完成”，避免重复分配。', '归还邮箱', { type: 'warning' }) } catch { return }
  await runEmailTransition(projectId, () => releaseEmail(projectId)); ElMessage.success('邮箱已归还，未添加平台标签')
}
const failEmailAction = async () => {
  if (emailUpdating.value) return
  const projectId = selectedId.value
  let value
  try {
    ({ value } = await ElMessageBox.prompt('邮箱无法完成注册时，请填写失败原因；标记后邮箱将进入废弃状态，不再被领取。', '标记邮箱注册失败', { inputType: 'textarea', inputPlaceholder: '例如：邮箱收不到验证码、密码错误、账号已被限制', inputValidator: text => text?.trim() ? true : '请填写失败原因', confirmButtonText: '确认标记失败' }))
  } catch { return }
  await runEmailTransition(projectId, () => failEmail(projectId, value))
  ElMessage.success('邮箱已标记为注册失败并移出可领取池')
}
const completeEmailAction = async () => {
  if (emailUpdating.value) return
  const projectId = selectedId.value
  const platform = selected.value.target_platform
  if (!['tiktok', 'youtube', 'instagram', 'facebook'].includes(platform.toLowerCase())) {
    try { await ElMessageBox.confirm('确认已注册完成？将添加平台标签并释放邮箱。', '注册完成', { type: 'warning' }) } catch { return }
    await runEmailTransition(projectId, () => completeEmail(projectId, { platform })); ElMessage.success('已标记注册完成并释放邮箱'); return
  }
  if (!auth.hasPermission('op_account:create')) return ElMessage.warning('请联系管理员授予创建运营账号权限')
  Object.assign(completeTarget, { id: projectId, platform })
  Object.assign(completeForm, { account: '', password: '', totp_secret: '' }); completeVisible.value = true
}
const submitCompleteEmail = async () => { if (emailUpdating.value) return; if (!completeForm.account.trim()) return ElMessage.warning('请填写平台账号'); completing.value = true; try { const result = await runEmailTransition(completeTarget.id, () => completeEmail(completeTarget.id, { platform: completeTarget.platform, ...completeForm })); completeVisible.value = false; ElMessage.success(`已创建运营账号 ${result.op_account}，邮箱已关联并释放`) } finally { completing.value = false } }
const openImport = () => { if (!selected.value) return; Object.assign(importTarget, { id: selected.value.id, name: selected.value.name }); Object.assign(importBatch, { name: '', remark: '' }); importText.value = ''; importVisible.value = true }
const saveImport = async () => {
  if (importing.value) return
  if (!importText.value.trim()) return ElMessage.warning('请粘贴卡密内容')
  const projectId = importTarget.id
  importing.value = true
  try {
    const result = await importCardKeys(projectId, importText.value, { batch_name: importBatch.name.trim(), remark: importBatch.remark.trim() })
    ElMessage.success(`导入 ${result.added} 份，跳过重复 ${result.duplicates} 份${result.batch ? ' · ' + result.batch.name : ''}`)
    importVisible.value = false
    if (selectedId.value === projectId && result.batch) selectedBatchId.value = result.batch.id
    await load()
  } finally { importing.value = false }
}
const openBatches = () => { Object.assign(batchTarget, { id: selected.value.id, name: selected.value.name }); batchError.value = ''; showArchivedBatches.value = false; batchVisible.value = true }
const viewBatch = (batch) => { if (selectedId.value !== batchTarget.id) return; selectedBatchId.value = batch.id; batchVisible.value = false; reloadKeys() }
const editBatch = (batch) => { Object.assign(batchForm, { id: batch.id, name: batch.name, remark: batch.remark || '' }); batchError.value = ''; batchEditVisible.value = true }
const saveBatch = async () => {
  if (batchSaving.value) return
  if (!batchForm.name.trim()) return ElMessage.warning('请填写批次名称')
  batchSaving.value = true
  batchError.value = ''
  try {
    await updateCardKeyBatch(batchTarget.id, batchForm.id, { name: batchForm.name.trim(), remark: batchForm.remark.trim() })
    batchEditVisible.value = false
    await load()
    ElMessage.success('批次已保存')
  } catch (error) { batchError.value = error.response?.data?.detail || '批次保存失败，请稍后重试' }
  finally { batchSaving.value = false }
}
const toggleBatch = async (batch) => {
  if (batchSaving.value) return
  const projectId = batchTarget.id
  const paused = batch.status === 'paused'
  let reason = ''
  try {
    if (paused) await ElMessageBox.confirm(`确认恢复“${batch.name}”的领取？请先核实问题已经处理。`, '恢复批次', { type: 'warning', confirmButtonText: '恢复领取' })
    else ({ value: reason } = await ElMessageBox.prompt('填写暂停原因，团队成员会看到提示。暂停后停止新领取，已领取卡密保留处理入口。', '暂停批次', { inputType: 'textarea', inputPlaceholder: '例如：供应商反馈部分卡密异常，等待售后核实', inputValidator: value => value?.trim() && value.length <= 2000 ? true : '请填写原因，最多 2000 字', confirmButtonText: '暂停领取' }))
  } catch { return }
  batchSaving.value = true
  batchError.value = ''
  try {
    await updateCardKeyBatch(projectId, batch.id, { status: paused ? 'active' : 'paused', pause_reason: paused ? '' : reason.trim() })
    await load()
    ElMessage.success(paused ? '批次已恢复领取' : '批次已暂停领取')
  } catch (error) { batchError.value = error.response?.data?.detail || '批次状态修改失败，请稍后重试' }
  finally { batchSaving.value = false }
}
const deleteBatch = async (batch) => {
  if (batchSaving.value) return
  const projectId = batchTarget.id
  try { await ElMessageBox.confirm(`删除批次“${batch.name}”？从未领取或流转的整批卡密会一并清理；只要存在领取、归还、消耗或异常记录，整批将归档并停止新领取，保留全部卡密和历史。`, '删除批次', { type: 'warning', confirmButtonText: '确认删除 / 归档' }) } catch { return }
  batchSaving.value = true
  batchError.value = ''
  try {
    const result = await deleteCardKeyBatch(projectId, batch.id)
    if (selectedId.value === projectId && selectedBatchId.value === batch.id) selectedBatchId.value = -1
    await load()
    ElMessage.success(result.archived ? '批次已归档，停止新领取，卡密和历史已保留' : `批次已删除，清理 ${result.deleted_keys || 0} 份未使用卡密`)
  } catch (error) { batchError.value = error.response?.data?.detail || '批次删除失败，请稍后重试' }
  finally { batchSaving.value = false }
}
const claim = async () => {
  if (claiming.value || !canClaimKey.value) return
  const projectId = selectedId.value
  const batchId = selectedBatchId.value === -1 ? undefined : selectedBatchId.value
  claiming.value = true
  try {
    const key = await claimCardKey(projectId, batchId)
    if (selectedId.value === projectId) pendingKey.value = key
    await load()
    ElMessage.success('已领取并锁定，复制后使用，完成再确认消耗')
  } finally { claiming.value = false }
}
const copy = async (content) => {
  try { await copyText(content); ElMessage.success('已复制') }
  catch { ElMessage.warning('复制失败，请手动复制') }
}
const consume = async (row) => {
  const projectId = selectedId.value
  try { await ElMessageBox.confirm('确认这份卡密已经使用？确认后不会重新分配。', '确认消耗', { type: 'warning' }) }
  catch { return }
  consuming.value = true
  try { await consumeCardKey(projectId, row.id); await load(); ElMessage.success('已确认消耗') }
  finally { consuming.value = false }
}
const release = async (row) => {
  const projectId = selectedId.value
  const inactiveBatch = row.batch_status && row.batch_status !== 'active'
  try { await ElMessageBox.confirm(`请确认卡密尚未使用，也未提交给其他服务。${inactiveBatch ? '归还后仍保留在当前暂停或归档批次，停止新领取。' : '归还后其他成员可以立即领取。'}已经使用或不确定是否使用时，请勿归还。`, '归还未使用卡密', { type: 'warning', confirmButtonText: '确认未使用并归还' }) }
  catch { return }
  consuming.value = true
  try { await releaseCardKey(projectId, row.id); await load(); ElMessage.success(inactiveBatch ? '已归还，所属批次继续停止新领取' : '已归还，卡密重新可领取') }
  finally { consuming.value = false }
}
const invalid = async (row) => { let value; try { ({ value } = await ElMessageBox.prompt('填写无效原因或上游售后信息', '标记卡密无效', { inputPlaceholder: '例如：兑换失败，已提交供应商售后', inputValidator: value => value?.trim() ? true : '请填写原因', confirmButtonText: '确认标记' })) } catch { return }; await markCardKeyInvalid(selectedId.value, row.id, value); await load(); ElMessage.success('已标记无效') }
const editKeyRemark = async (row) => {
  let value
  try { ({ value } = await ElMessageBox.prompt('记录供应商售后进度、补发情况或其他备注；修改历史会保留。', '卡密备注', { inputValue: row.remark || '', inputType: 'textarea', inputValidator: value => (value || '').length <= 2000 || '备注最多 2000 字' })) } catch { return }
  await updateCardKeyRemark(selectedId.value, row.id, value || ''); await load(); ElMessage.success('备注已保存')
}
const formatDate = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'; const statusLabel = value => ({ available: '可领取', claimed: '已领取', consumed: '已消耗', invalid: '无效售后' }[value] || value); const statusType = value => ({ available: 'success', claimed: 'warning', consumed: 'info', invalid: 'danger' }[value] || '')
onMounted(async () => {
  totpTimer = window.setInterval(() => {
    if (!pendingEmail.value) { totp.value = null; return }
    if (!totp.value) return
    totp.value.remaining = Math.max(0, Math.ceil((totp.value.expiresAt - Date.now()) / 1000))
    if (!totp.value.remaining) refreshTotp()
  }, 1000)
  await load()
  if (canManage.value) members.value = await getCardKeyMembers()
})
onBeforeUnmount(() => { if (totpTimer) window.clearInterval(totpTimer) })
</script>

<style scoped>
.batch-bar { display:flex; align-items:center; flex-wrap:wrap; gap:9px; padding:12px; margin:12px 0; border:1px solid #dce4ed; border-radius:8px; background:#f8fafc; }
.batch-select { width:300px; max-width:100%; }
.batch-counts { font-size:13px; color:#475569; }
.batch-note { flex-basis:100%; margin:3px 0 0; color:#606266; font-size:13px; white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.55; }
.batch-bar .el-alert { width:100%; }
.batch-state-tag { margin-left:6px; }
.batch-row-remark { color:#909399; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.batch-manager-toolbar { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.batch-error { margin-bottom:12px; }
.batch-pause-reason { color:#b7791f; font-size:12px; margin-top:4px; overflow-wrap:anywhere; }
.pending-batch { color:#475569; font-size:12px; }
.pending-batch-warning { margin-bottom:10px; }
.email-claim-bar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:12px; margin:12px 0; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; }
.email-claim-bar span,.email-claim-bar small { margin-left:10px; color:#64748b; }
.email-claim-bar .email-platform-empty { color:#e6a23c; }
.email-actions { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
.email-actions .el-button { margin-left:0; }
.project-metrics { display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-left:auto; }
.claim-bar { flex-wrap:wrap; gap:10px; }
.claim-bar > div { min-width:0; }
.record-filters { flex-wrap:wrap; }
.email-actions code { min-width:0; overflow-wrap:anywhere; }
.member-stat { display:flex; justify-content:space-between; gap:18px; padding:5px 0; border-bottom:1px solid #ebeef5; color:#606266; font-size:13px; }
.key-remark { max-width:90px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#909399; font-size:12px; }
.heading-actions { display:flex; gap:8px; }
.platform-create { display:flex; gap:8px; margin-bottom:14px; }
.platform-create .el-input { flex:1; }
.form-hint { color:#909399; font-size:12px; line-height:1.5; margin-top:5px; }
 .card-key-page { max-width:1500px; margin:0 auto; min-width:0; }
 .page-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:16px; }
 .page-heading h2 { margin:0 0 6px; color:#1f2937; }
 .page-heading span,.hint,.muted { color:#909399; font-size:13px; }
 .heading-actions { display:flex; flex-wrap:wrap; gap:8px; }
 .project-card,.project-list-card { margin-bottom:16px; }
 .toolbar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
 .project-description { color:#909399; flex:1 1 180px; min-width:120px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
 .claim-bar { display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-top:1px solid #ebeef5; border-bottom:1px solid #ebeef5; margin-bottom:10px; }
 .claim-bar > div { min-width:0; }
 .claim-bar span,.claim-bar small { margin-left:12px; color:#606266; }
 .claim-bar small { color:#909399; }
 code { color:#303133; word-break:break-all; white-space:pre-wrap; }
 .pending-key { display:flex; align-items:center; gap:10px; padding:10px 12px; margin:10px 0; border:1px solid #d9ecff; background:#ecf5ff; border-radius:6px; }
 .pending-key code { flex:1 1 220px; min-width:0; }
 .record-filters { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin:12px 0; }
 .pagination { justify-content:flex-end; margin-top:12px; }
 @media(max-width:768px) {
   .page-heading { flex-direction:column; gap:10px; }
   .heading-actions { width:100%; }
   .heading-actions .el-button { flex:1 1 auto; }
   .toolbar .el-select { max-width:100%; }
   .claim-bar { align-items:flex-start; gap:8px; }
   .claim-bar small { display:block; margin:5px 0; }
   .pending-key { align-items:flex-start; flex-wrap:wrap; }
   .pending-key code { flex-basis:100%; }
   .pending-key .el-button { flex:1 1 auto; }
   .project-description { flex-basis:100%; }
 }
</style>
