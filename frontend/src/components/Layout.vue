<template>
  <el-container class="layout-container">
    <!-- 侧边栏：移动端隐藏 -->
    <el-aside
      v-if="!isMobile"
      :width="isTablet ? '64px' : '200px'"
      class="sidebar"
      :class="{ 'sidebar-collapsed': sidebarCollapsed }"
    >
      <div class="logo" :class="{ 'logo-collapsed': sidebarCollapsed }">
        <img v-if="settings.logo_image" :src="settings.logo_image" alt="Logo" class="logo-image" />
        <span v-if="!sidebarCollapsed" class="logo-text">{{ settings.site_name }}</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        router
        class="sidebar-menu"
      >
        <el-menu-item v-if="authStore.hasPermission('device:view') && authStore.hasPermission('op_account:view') && authStore.hasPermission('proxy_node:view')" index="/overview">
          <el-icon><Monitor /></el-icon>
          <template #title><span>数据总览</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('monitor:view')" index="/monitor">
          <el-icon><Monitor /></el-icon>
          <template #title><span>监控管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('op_account:view')" index="/op-accounts">
          <el-icon><Briefcase /></el-icon>
          <template #title><span>运营账号</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('device:view')" index="/devices">
          <el-icon><Iphone /></el-icon>
          <template #title><span>终端资产</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('proxy_node:view')" index="/proxy-nodes">
          <el-icon><Connection /></el-icon>
          <template #title><span>节点管理</span></template>
        </el-menu-item>
        <el-menu-item
          v-if="authStore.hasPermission('team:dept:view') || authStore.hasPermission('team:member:view') || authStore.hasPermission('team:role:view') || authStore.hasPermission('team:log:view')"
          index="/team/manage"
        >
          <el-icon><UserFilled /></el-icon>
          <template #title><span>团队管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('email:view')" index="/emails">
          <el-icon><Message /></el-icon>
          <template #title><span>邮箱管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('work_item:view')" index="/work-items">
          <el-icon><Memo /></el-icon>
          <template #title><span>备忘管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('card_key:view')" index="/card-keys">
          <el-icon><Memo /></el-icon><template #title><span>卡密管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('settings:view')" index="/settings">
          <el-icon><Setting /></el-icon>
          <template #title><span>系统设置</span></template>
        </el-menu-item>
      </el-menu>
      <button class="sidebar-version" type="button" @click="openVersionDrawer">
        <span v-if="!sidebarCollapsed">版本 {{ APP_VERSION }}</span>
        <span v-else>v{{ APP_VERSION }}</span>
        <i v-if="hasUpdate" class="version-update-dot" aria-label="有新版本" />
      </button>
    </el-aside>

    <el-container>
      <!-- 顶部栏 -->
      <el-header class="header" :class="{ 'header-mobile': isMobile }">
        <!-- 移动端：iOS 风格顶部栏 -->
        <template v-if="isMobile">
          <div class="header-mobile-left"></div>
          <span class="header-title">{{ currentPageTitle }}</span>
          <div class="header-mobile-right">
            <MemoReminder v-if="authStore.hasPermission('work_item:view')" />
            <el-button link @click="handleLogout" class="logout-icon-btn">
              <el-icon size="20"><SwitchButton /></el-icon>
            </el-button>
          </div>
        </template>
        <!-- 桌面端/平板端：原有样式 -->
        <template v-else>
          <div class="header-right">
            <MemoReminder v-if="authStore.hasPermission('work_item:view')" />
            <span v-show="!isMobile" class="username">{{ authStore.user?.real_name || authStore.user?.username }}</span>
            <el-button link @click="handleLogout">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-button>
          </div>
        </template>
      </el-header>

      <el-main class="main-content">
        <Breadcrumb :isMobile="isMobile" />
        <router-view />
      </el-main>
    </el-container>

    <!-- 移动端底部 Tab Bar -->
    <FloatingTableScrollbar />
    <MobileTabBar v-if="isMobile" />

    <el-drawer v-model="versionDrawerVisible" title="更新日志" size="420px">
      <div class="version-history">
        <div class="version-actions">
          <span v-if="updateInfo">
            <template v-if="updateInfo.error">{{ updateInfo.error }}</template>
            <template v-else>当前 v{{ updateInfo.current_version }}<template v-if="updateInfo.has_update">，发现 v{{ updateInfo.latest_version }}</template><template v-else>，已是最新版本</template></template>
          </span>
          <span v-else>检查服务器是否有新版本</span>
          <el-button size="small" :loading="updateChecking" @click="handleCheckUpdate">检查更新</el-button>
          <el-button v-if="updateInfo?.has_update" type="primary" size="small" :disabled="!updateInfo.configured || updateInfo.updating" :loading="updateApplying" @click="handleApplyUpdate">立即更新</el-button>
        </div>
        <el-alert v-if="updateInfo?.has_update" type="info" :closable="false" title="有新版本可用" />
        <el-alert v-if="updateInfo && !updateInfo.error && !updateInfo.configured" type="warning" :closable="false" title="本机尚未初始化更新器，暂不能自动更新" />
        <ul v-if="updateInfo?.has_update" class="update-changes">
          <li v-for="change in updateInfo.changes" :key="change">{{ change }}</li>
        </ul>
        <article v-for="release in RELEASES" :key="release.version" class="release-item">
          <div class="release-heading">
            <strong>v{{ release.version }}</strong>
            <span>{{ release.date }}</span>
          </div>
          <ul>
            <li v-for="item in release.items" :key="item">{{ item }}</li>
          </ul>
        </article>
      </div>
    </el-drawer>
  </el-container>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Setting, Briefcase, UserFilled, SwitchButton, Connection, Iphone, Message, Memo } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getPublicSettings, checkUpdate, applyUpdate, getUpdateStatus } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import Breadcrumb from '@/components/Breadcrumb.vue'
import MobileTabBar from '@/components/MobileTabBar.vue'
import FloatingTableScrollbar from '@/components/FloatingTableScrollbar.vue'
import MemoReminder from '@/components/MemoReminder.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const APP_VERSION = '1.1.0'
const versionDrawerVisible = ref(false)
const RELEASES = [
  {
    version: APP_VERSION,
    date: '2026-10-02',
    items: ['卡密项目支持邮箱领取、注册归因与 2FA 验证码', '增加成员工作量报表、卡密备注、搜索和操作追踪', '优化登录页与部署稳定性']
  },
  {
    version: '1.0.0',
    date: '2026-10-01',
    items: ['团队资产、运营账号、邮箱、节点和卡密统一管理', '上线数据总览与人员、终端关联视图']
  }
]
const updateInfo = ref(null)
const updateChecking = ref(false)
const updateApplying = ref(false)
let updateTimer = null
let updateCheckTimer = null
const hasUpdate = computed(() => Boolean(updateInfo.value?.has_update))

const handleCheckUpdate = async () => {
  updateChecking.value = true
  try {
    const result = await checkUpdate()
    updateInfo.value = result
    if (result.has_update) {
      ElMessage.success(`发现新版本 v${result.latest_version}`)
    } else {
      ElMessage.success(`当前已是最新版本 v${result.current_version}`)
    }
  } catch (error) {
    const message = error?.response?.data?.detail || error?.message || '检查更新失败'
    updateInfo.value = { error: message }
    ElMessage.error(message)
  } finally {
    updateChecking.value = false
  }
}

const checkUpdateSilently = async () => {
  try {
    updateInfo.value = await checkUpdate()
  } catch (_) {
    // Background checks must not interrupt normal application use.
  }
}

const openVersionDrawer = () => {
  versionDrawerVisible.value = true
  checkUpdateSilently()
}

const handleApplyUpdate = async () => {
  try {
    await ElMessageBox.confirm(
      `确认更新到 v${updateInfo.value.latest_version}？更新期间服务会短暂重启。`,
      '确认更新',
      { type: 'warning', confirmButtonText: '开始更新', cancelButtonText: '取消' }
    )
  } catch (_) {
    return
  }
  updateApplying.value = true
  try {
    await applyUpdate()
    updateInfo.value = { ...(updateInfo.value || {}), updating: true }
    updateTimer = window.setInterval(async () => {
      try {
        const status = await getUpdateStatus()
        if (status.status === 'failed') {
          window.clearInterval(updateTimer)
          updateTimer = null
          updateInfo.value = { ...(updateInfo.value || {}), updating: false, update_status: status }
          ElMessage.error(`更新失败：${status.message || '请检查服务日志'}`)
        } else if (status.status === 'completed') {
          window.clearInterval(updateTimer)
          updateTimer = null
          window.location.reload()
        }
      } catch (_) {
        // The backend may restart during a successful update.
      }
    }, 3000)
  } finally {
    updateApplying.value = false
  }
}

// 响应式断点状态
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const isTablet = computed(() => windowWidth.value > 768 && windowWidth.value <= 1024)
const isDesktop = computed(() => windowWidth.value > 1024)
const sidebarCollapsed = computed(() => isTablet.value)

const handleResize = () => {
  windowWidth.value = window.innerWidth
}
onMounted(() => {
  window.addEventListener('resize', handleResize)
  checkUpdateSilently()
  updateCheckTimer = window.setInterval(checkUpdateSilently, 10 * 60 * 1000)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (updateCheckTimer) window.clearInterval(updateCheckTimer)
})

// 当前页面标题（移动端顶部栏用）
const currentPageTitle = computed(() => {
  const matched = route.matched
  // 取最后一个有 breadcrumb 的路由
  for (let i = matched.length - 1; i >= 0; i--) {
    if (matched[i].meta?.breadcrumb) {
      return matched[i].meta.breadcrumb
    }
  }
  return settings.value.site_name || 'TikTok Monitor'
})

const settings = ref({
  site_name: 'TikTok Monitor',
  logo_image: ''
})

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/monitor')) return '/monitor'
  if (path.startsWith('/accounts')) return '/monitor'
  if (path.startsWith('/op-accounts')) return '/op-accounts'
  if (path.startsWith('/proxy-nodes')) return '/proxy-nodes'
  if (path.startsWith('/settings')) return '/settings'
  if (path.startsWith('/team')) return '/team/manage'
  if (path.startsWith('/work-items')) return '/work-items'
  if (path.startsWith('/card-keys')) return '/card-keys'
  return path
})

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
}

const loadSettings = async () => {
  try {
    const data = await getPublicSettings()
    settings.value = {
      site_name: data.site_name || 'TikTok Monitor',
      logo_image: data.logo_image || ''
    }
    document.title = settings.value.site_name
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
}

const handleSiteSettingsUpdated = (event) => {
  settings.value = {
    site_name: event.detail?.site_name || 'TikTok Monitor',
    logo_image: event.detail?.logo_image || ''
  }
  document.title = settings.value.site_name
}

watch(() => route.path, (newPath) => {
  if (newPath !== '/settings') {
    loadSettings()
  }
})

onMounted(() => {
  loadSettings()
  window.addEventListener('site-settings-updated', handleSiteSettingsUpdated)
})
onUnmounted(() => {
  window.removeEventListener('site-settings-updated', handleSiteSettingsUpdated)
  if (updateTimer) window.clearInterval(updateTimer)
})
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.sidebar {
  background-color: #304156;
  color: #fff;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 0 15px;
  background-color: #263445;
  flex-shrink: 0;
}

.logo-collapsed {
  padding: 0 8px;
  justify-content: center;
}

.logo-text {
  font-size: 18px;
  font-weight: bold;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logo-image {
  max-width: 80px;
  max-height: 50px;
  object-fit: contain;
  flex-shrink: 0;
}

.logo-collapsed .logo-image {
  max-width: 40px;
  max-height: 40px;
}

.sidebar-menu {
  border-right: none;
  background-color: #304156;
  flex: 1;
}

.sidebar-version {
  flex-shrink: 0;
  width: 100%;
  min-height: 36px;
  padding: 0 16px;
  border: 0;
  background: transparent;
  color: #91a1b5;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.sidebar-version:hover {
  color: #fff;
  background-color: #263445;
}

.version-update-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-left: 6px;
  border-radius: 50%;
  background: #f56c6c;
  box-shadow: 0 0 0 2px rgba(245, 108, 108, 0.16);
  vertical-align: middle;
}

.sidebar-collapsed .sidebar-version {
  padding: 0;
  text-align: center;
}

.version-history {
  color: #303133;
}

.version-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.version-actions > span {
  flex: 1;
  color: #606266;
  font-size: 13px;
}

.update-changes {
  margin: 12px 0 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.8;
}

.release-item + .release-item {
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid #ebeef5;
}

.release-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.release-heading strong {
  font-size: 18px;
}

.release-heading span {
  color: #909399;
  font-size: 13px;
}

.release-item ul {
  margin: 12px 0 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.8;
}

.sidebar-menu .el-menu-item,
.sidebar-menu .el-sub-menu__title {
  color: #bfcbd9;
}

.sidebar-menu .el-menu-item:hover,
.sidebar-menu .el-sub-menu__title:hover {
  background-color: #263445;
  color: #fff;
}

.sidebar-menu .el-menu-item.is-active {
  background-color: #409eff;
  color: #fff;
}

/* 强制覆盖禁用状态颜色 */
.sidebar-menu :deep(.el-sub-menu__title),
.sidebar-menu :deep(.el-sub-menu.is-disabled > .el-sub-menu__title) {
  color: #bfcbd9 !important;
  cursor: pointer !important;
  opacity: 1 !important;
}

/* 子菜单背景和文字颜色 */
.sidebar-menu :deep(.el-menu--inline) {
  background-color: #263445 !important;
}

.sidebar-menu :deep(.el-menu--inline .el-menu-item) {
  background-color: #263445 !important;
  color: #bfcbd9 !important;
  min-width: unset;
}

.sidebar-menu :deep(.el-menu--inline .el-menu-item:hover) {
  background-color: #1f2d3d !important;
  color: #fff !important;
}

.sidebar-menu :deep(.el-menu--inline .el-menu-item.is-active) {
  background-color: #409eff !important;
  color: #fff !important;
}

/* 修复子菜单图标颜色 */
.sidebar-menu :deep(.el-menu--inline .el-menu-item .el-icon) {
  color: inherit;
}

/* 折叠模式下菜单宽度适配 */
.sidebar-collapsed .sidebar-menu {
  width: 64px !important;
}

/* ===== 顶部栏 ===== */
.header {
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 20px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username {
  font-size: 14px;
  color: #606266;
}

/* ===== 移动端顶部栏（iOS 毛玻璃风格）===== */
.header-mobile {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 44px; /* fallback */
  height: calc(44px + env(safe-area-inset-top));
  padding-top: 0; /* fallback */
  padding-top: env(safe-area-inset-top);
  padding-left: 8px;
  padding-right: 8px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.12);
  z-index: 100;
  justify-content: space-between;
}

.header-mobile-left {
  width: 44px;
  flex-shrink: 0;
}

.header-mobile-right {
  width: 44px;
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.header-title {
  font-size: 17px;
  font-weight: 600;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  color: #000000;
  letter-spacing: -0.4px;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.logout-icon-btn {
  min-height: 44px;
  min-width: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #007AFF;
}

/* ===== 主内容区 ===== */
.main-content {
  background-color: #f0f2f5;
  padding: 20px;
}

/* 移动端主内容区偏移（为固定顶部栏和底部 Tab Bar 留空间）*/
@media (max-width: 768px) {
  .main-content {
    padding-top: calc(44px + env(safe-area-inset-top) + 12px) !important;
    padding-bottom: calc(49px + env(safe-area-inset-bottom) + 12px) !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    background: #F2F2F7;
  }
}

</style>
