<template>
  <el-container class="layout-container">
    <el-aside width="200px" class="sidebar">
      <div class="logo">
        <img v-if="settings.logo_image" :src="settings.logo_image" alt="Logo" class="logo-image" />
        <span class="logo-text">{{ settings.site_name }}</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="sidebar-menu"
      >
        <el-menu-item v-if="authStore.hasPermission('monitor:view')" index="/monitor">
          <el-icon><Monitor /></el-icon>
          <span>监控管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.hasPermission('op_account:view')" index="/op-accounts">
          <el-icon><Briefcase /></el-icon>
          <span>运营账号</span>
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
            <span>部门管理</span>
          </el-menu-item>
          <el-menu-item v-if="authStore.hasPermission('team:member:view')" index="/team/member">
            <el-icon><User /></el-icon>
            <span>成员管理</span>
          </el-menu-item>
          <el-menu-item v-if="authStore.hasPermission('team:role:view')" index="/team/role">
            <el-icon><Key /></el-icon>
            <span>角色管理</span>
          </el-menu-item>
          <el-menu-item v-if="authStore.hasPermission('team:log:view')" index="/team/log">
            <el-icon><Document /></el-icon>
            <span>操作日志</span>
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item v-if="authStore.hasPermission('settings:view')" index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-right">
          <span class="username">{{ authStore.user?.real_name || authStore.user?.username }}</span>
          <el-button link @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出登录
          </el-button>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Setting, Briefcase, UserFilled, User, Key, Document, OfficeBuilding, SwitchButton } from '@element-plus/icons-vue'
import { getSettings } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

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

.main-content {
  background-color: #f0f2f5;
  padding: 20px;
}
</style>
