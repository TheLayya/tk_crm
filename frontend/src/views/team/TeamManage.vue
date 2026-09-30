<template>
  <div class="team-manage">
    <MemberManage v-if="authStore.hasPermission('team:member:view')" ref="memberView" @view-logs="openLogs">
      <template #management-actions><div class="team-actions">
        <el-button v-if="authStore.hasPermission('team:dept:view')" @click="departmentVisible = true">部门管理</el-button>
        <el-button v-if="authStore.hasPermission('team:role:view')" @click="roleVisible = true">角色权限</el-button>
        <el-button v-if="authStore.hasPermission('team:log:view')" @click="openLogs()">操作日志</el-button>
      </div></template>
    </MemberManage>
    <el-card v-else>
      <div class="team-actions">
        <strong>团队管理</strong>
        <el-button v-if="authStore.hasPermission('team:dept:view')" @click="departmentVisible = true">部门管理</el-button>
        <el-button v-if="authStore.hasPermission('team:role:view')" @click="roleVisible = true">角色权限</el-button>
        <el-button v-if="authStore.hasPermission('team:log:view')" @click="openLogs()">操作日志</el-button>
      </div>
      <p>您没有成员列表查看权限，可使用已授权的管理功能。</p>
    </el-card>
    <el-dialog v-if="authStore.hasPermission('team:dept:view')" v-model="departmentVisible" title="部门管理" width="min(900px, 94vw)" destroy-on-close @closed="refreshMembers">
      <DeptManage v-if="departmentVisible" />
    </el-dialog>
    <el-dialog v-if="authStore.hasPermission('team:role:view')" v-model="roleVisible" title="角色权限" width="min(1100px, 94vw)" destroy-on-close @closed="refreshMembers">
      <RoleManage v-if="roleVisible" />
    </el-dialog>
    <el-drawer v-if="authStore.hasPermission('team:log:view')" v-model="logVisible" :title="logUsername ? '操作记录 · ' + logUsername : '团队日志'" :size="isMobile ? '100%' : 'min(1400px, 90vw)'" destroy-on-close>
      <LogView v-if="logVisible" :key="logUsername" :username="logUsername" initial-tab="operation" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import MemberManage from './MemberManage.vue'

const DeptManage = defineAsyncComponent(() => import('./DeptManage.vue'))
const RoleManage = defineAsyncComponent(() => import('./RoleManage.vue'))
const LogView = defineAsyncComponent(() => import('./LogView.vue'))
const authStore = useAuthStore()
const route = useRoute()
const memberView = ref(null)
const departmentVisible = ref(false)
const roleVisible = ref(false)
const logVisible = ref(false)
const logUsername = ref('')
const width = ref(window.innerWidth)
const isMobile = computed(() => width.value <= 768)
const resize = () => { width.value = window.innerWidth }
const refreshMembers = () => memberView.value?.refresh()
const openLogs = (username = '') => {
  logUsername.value = username
  logVisible.value = true
}
watch(() => route.query.panel, (panel) => {
  departmentVisible.value = panel === 'dept' && authStore.hasPermission('team:dept:view')
  roleVisible.value = panel === 'role' && authStore.hasPermission('team:role:view')
  logVisible.value = false
  if (panel === 'log' && authStore.hasPermission('team:log:view')) openLogs()
}, { immediate: true })
onMounted(() => window.addEventListener('resize', resize))
onUnmounted(() => window.removeEventListener('resize', resize))
</script>

<style scoped>
.team-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.team-actions :deep(.el-button + .el-button) { margin-left: 0; }
.team-manage :deep(.el-dialog__body) { max-height: 72vh; overflow: auto; }
.team-manage :deep(.el-dialog__body > div > .el-card) { border: 0; box-shadow: none; }
.team-manage :deep(.el-dialog__body > div > .el-card > .el-card__body) { padding: 8px 0; }
.team-manage :deep(.el-drawer__body > div > .el-card) { box-shadow: none; }
</style>
