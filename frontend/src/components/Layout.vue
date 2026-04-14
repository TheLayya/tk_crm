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
        <el-menu-item v-if="authStore.hasPermission('monitor:view')" index="/monitor">
          <el-icon><Monitor /></el-icon>
          <template #title><span>监控管理</span></template>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('op_account:view')" index="/op-accounts">
          <el-icon><Briefcase /></el-icon>
          <template #title><span>运营账号</span></template>
        </el-menu-item>
        <el-sub-menu
          v-if="authStore.hasPermission('team:dept:view') || authStore.hasPermission('team:member:view') || authStore.hasPermission('team:role:view') || authStore.hasPermission('team:log:view')"
          index="/team"
        >
          <template #title>
            <el-icon><UserFilled /></el-icon>
            <span>团队管理</span>
          </template>
          <el-menu-item v-if="authStore.hasPermission('team:dept:view')" index="/team/dept">
            <el-icon><OfficeBuilding /></el-icon>
            <template #title><span>部门管理</span></template>
          </el-menu-item>
          <el-menu-item v-if="authStore.hasPermission('team:member:view')" index="/team/member">
            <el-icon><User /></el-icon>
            <template #title><span>成员管理</span></template>
          </el-menu-item>
          <el-menu-item v-if="authStore.hasPermission('team:role:view')" index="/team/role">
            <el-icon><Key /></el-icon>
            <template #title><span>角色管理</span></template>
          </el-menu-item>
          <el-menu-item v-if="authStore.hasPermission('team:log:view')" index="/team/log">
            <el-icon><Document /></el-icon>
            <template #title><span>操作日志</span></template>
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item v-if="authStore.hasPermission('settings:view')" index="/settings">
          <el-icon><Setting /></el-icon>
          <template #title><span>系统设置</span></template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部栏 -->
      <el-header class="header" :class="{ 'header-mobile': isMobile }">
        <!-- 移动端：iOS 风格顶部栏 -->
        <template v-if="isMobile">
          <div class="header-mobile-left"></div>
          <span class="header-title">{{ currentPageTitle }}</span>
          <div class="header-mobile-right">
            <el-button link @click="handleLogout" class="logout-icon-btn">
              <el-icon size="20"><SwitchButton /></el-icon>
            </el-button>
          </div>
        </template>
        <!-- 桌面端/平板端：原有样式 -->
        <template v-else>
          <div class="header-right">
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
        <!-- 移动端团队子导航 -->
        <div v-if="isMobile && route.path.startsWith('/team')" class="team-sub-nav">
          <button
            v-if="authStore.hasPermission('team:member:view')"
            class="team-sub-btn"
            :class="{ 'is-active': route.path === '/team/member' }"
            @click="router.push('/team/member')"
          >成员</button>
          <button
            v-if="authStore.hasPermission('team:dept:view')"
            class="team-sub-btn"
            :class="{ 'is-active': route.path === '/team/dept' }"
            @click="router.push('/team/dept')"
          >部门</button>
          <button
            v-if="authStore.hasPermission('team:role:view')"
            class="team-sub-btn"
            :class="{ 'is-active': route.path === '/team/role' }"
            @click="router.push('/team/role')"
          >角色</button>
          <button
            v-if="authStore.hasPermission('team:log:view')"
            class="team-sub-btn"
            :class="{ 'is-active': route.path === '/team/log' }"
            @click="router.push('/team/log')"
          >日志</button>
        </div>
        <router-view />
      </el-main>
    </el-container>

    <!-- 移动端底部 Tab Bar -->
    <MobileTabBar v-if="isMobile" />
  </el-container>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Setting, Briefcase, UserFilled, User, Key, Document, OfficeBuilding, SwitchButton } from '@element-plus/icons-vue'
import { getSettings } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import Breadcrumb from '@/components/Breadcrumb.vue'
import MobileTabBar from '@/components/MobileTabBar.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// 响应式断点状态
const windowWidth = ref(window.innerWidth)
const isMobile = computed(() => windowWidth.value <= 768)
const isTablet = computed(() => windowWidth.value > 768 && windowWidth.value <= 1024)
const isDesktop = computed(() => windowWidth.value > 1024)
const sidebarCollapsed = computed(() => isTablet.value)

const handleResize = () => {
  windowWidth.value = window.innerWidth
}
onMounted(() => window.addEventListener('resize', handleResize))
onUnmounted(() => window.removeEventListener('resize', handleResize))

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
  if (path.startsWith('/settings')) return '/settings'
  if (path.startsWith('/team')) return path
  return path
})

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
}

const loadSettings = async () => {
  if (!authStore.hasPermission('settings:view')) return
  try {
    const data = await getSettings()
    settings.value = {
      site_name: data.site_name || 'TikTok Monitor',
      logo_image: data.logo_image || ''
    }
    document.title = settings.value.site_name
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
}

watch(() => route.path, (newPath) => {
  if (newPath !== '/settings') {
    loadSettings()
  }
})

onMounted(() => {
  loadSettings()
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

/* ===== 移动端团队子导航 ===== */
.team-sub-nav {
  display: flex;
  background: rgba(118, 118, 128, 0.12);
  border-radius: 9px;
  padding: 2px;
  margin: 0 16px 12px;
}

.team-sub-btn {
  flex: 1;
  border: none;
  background: transparent;
  border-radius: 7px;
  padding: 6px 0;
  font-size: 13px;
  font-weight: 500;
  color: #3C3C43;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s;
  min-height: 32px;
}

.team-sub-btn.is-active {
  background: #FFFFFF;
  color: #000000;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}
</style>
