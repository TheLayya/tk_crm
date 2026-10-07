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
          <el-button size="small" :loading="updateChecking" :disabled="updateInfo?.updating || updateInfo?.update_waiting" @click="handleCheckUpdate">检查更新</el-button>
          <el-button v-if="updateInfo?.update_waiting" size="small" :loading="updateChecking" @click="resumeUpdate(true)">查询更新状态</el-button>
          <el-button v-if="updateInfo?.has_update && authStore.hasPermission('settings:edit')" type="primary" size="small" :disabled="!updateInfo.configured || (updateInfo.client_type === 'desktop' && updateInfo.desktop_supported === false) || updateInfo.updating || updateInfo.update_waiting" :loading="updateApplying" @click="handleApplyUpdate">立即更新</el-button>
        </div>
        <el-alert v-if="updateInfo?.has_update" type="info" :closable="false" title="有新版本可用" />
        <el-alert v-if="updateInfo?.updating" type="info" :closable="false" :title="updateInfo.update_message || '正在更新，服务可能暂时重启，等待恢复后页面会自动刷新'" />
        <el-alert v-if="updateInfo?.update_waiting" type="warning" :closable="false" :title="updateInfo.update_message" show-icon />
        <el-alert v-if="updateInfo?.update_error" type="error" :closable="false" :title="updateInfo.update_error" show-icon />
        <el-alert v-if="updateInfo && !updateInfo.error && !updateInfo.configured" type="warning" :closable="false" title="本机尚未初始化更新器，暂不能自动更新" />
        <el-alert v-if="updateInfo?.has_update && updateInfo.client_type === 'desktop' && updateInfo.desktop_supported === false" type="warning" :closable="false" title="当前发布暂未提供 Windows 安装包，请联系管理员发布桌面安装包" />
        <el-alert v-if="updateInfo?.has_update && !authStore.hasPermission('settings:edit')" type="warning" :closable="false" title="当前账号只有查看权限，请联系管理员执行更新" />
        <ul v-if="updateInfo?.has_update" class="update-changes">
          <li v-for="change in updateInfo.changes" :key="change">{{ change }}</li>
        </ul>
        <article v-for="release in displayReleases" :key="`${release.version}-${release.installed_at || release.date}`" class="release-item">
          <div class="release-heading">
            <strong>v{{ release.version }}</strong>
            <span>{{ release.installed_at || release.date }}</span>
          </div>
          <ul>
            <li v-for="item in (release.items || release.changes)" :key="item">{{ item }}</li>
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
import { getPublicSettings, checkUpdate, applyUpdate, getUpdateStatus, getUpdateVersion, getUpdateHistory } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import Breadcrumb from '@/components/Breadcrumb.vue'
import MobileTabBar from '@/components/MobileTabBar.vue'
import FloatingTableScrollbar from '@/components/FloatingTableScrollbar.vue'
import MemoReminder from '@/components/MemoReminder.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const APP_VERSION = '1.1.18'
const versionDrawerVisible = ref(false)
const RELEASES = [
  {
    version: APP_VERSION,
    date: '2026-10-07',
    items: ['修复邮箱展开详情在统一表格中的宽度', 'Windows安装验收改为等待实际就绪状态', '增加项目内发布技能和双端发布校验工具']
  },
  {
    version: '1.1.17',
    date: '2026-10-07',
    items: ['全站表格支持排序、筛选、列显示和自定义顺序', '采集增加有限重试、代理切换、任务互斥和中断恢复', '视频部分结果和失败状态更准确，保留已采资料']
  },
  {
    version: '1.1.16',
    date: '2026-10-06',
    items: ['修复监控账号导出24小时变化量始终为0', '严格类型检查与80%测试覆盖率门禁全部通过', 'Windows更新增加跨进程互斥，防止重开窗口重复更新']
  },
  {
    version: '1.1.15',
    date: '2026-10-06',
    items: ['成员可查看本人终端绑定的运营账号和节点', '列表、统计、导出和关联操作统一数据范围', '修复越权关联校验，采集任务按发起成员隔离']
  },
  {
    version: '1.1.14',
    date: '2026-10-06',
    items: ['导入与手动采集均采集账号资料和视频', '运营账号粉丝变化使用自身最近两次采集记录', '昨日视频和已展开详情在采集后自动刷新']
  },
  {
    version: '1.1.13',
    date: '2026-10-06',
    items: ['运营账号自动采集视频并显示昨日更新与播放量', '邮箱列表可直接复制邮箱、密码和完整登录资料', '更新断连后恢复状态，避免重复提交更新']
  },
  {
    version: '1.1.12',
    date: '2026-10-05',
    items: ['邮箱导入支持三、四、六字段和手动格式选择', '辅助邮箱可留空或填写 null', '密码保留原值，兼容完整注册时间']
  },
  {
    version: '1.1.7',
    date: '2026-10-03',
    items: ['修复平台注册完成后邮箱管理不显示注册人的问题', '邮箱平台标签与成员注册归因保持一致', '增加邮箱注册失败备注并移出可领取池']
  },
  {
    version: '1.1.6',
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
const releaseHistory = ref([])
const updateChecking = ref(false)
const updateApplying = ref(false)
let updateTimer = null
let updateCheckTimer = null
let updatePageTimer = null
let updatePageController = null
let updateJob = null
let disposed = false
const UPDATE_JOB_KEY = 'tk-crm:update-job'
const UPDATE_WAIT_LIMIT = 10 * 60 * 1000
const hasUpdate = computed(() => Boolean(updateInfo.value?.has_update))
const displayReleases = computed(() => {
  const recorded = new Map(releaseHistory.value.map((release) => [release.version, release]))
  return [...releaseHistory.value, ...RELEASES.filter((release) => !recorded.has(release.version))]
})

const loadUpdateHistory = async () => {
  try {
    const result = await getUpdateHistory()
    releaseHistory.value = Array.isArray(result?.items) ? result.items : []
  } catch (_) {
    releaseHistory.value = []
  }
}

const handleCheckUpdate = async () => {
  if (updateChecking.value || updateJob) return
  updateChecking.value = true
  try {
    const result = await checkUpdate()
    if (disposed || updateJob) return
    updateInfo.value = result
    await loadUpdateHistory()
    if (result.has_update) {
      ElMessage.success(`发现新版本 v${result.latest_version}`)
    } else {
      ElMessage.success(`当前已是最新版本 v${result.current_version}`)
    }
  } catch (error) {
    if (disposed || updateJob) return
    const message = error?.response?.data?.detail || error?.message || '检查更新失败'
    updateInfo.value = { error: message }
    ElMessage.error(message)
  } finally {
    updateChecking.value = false
  }
}

const checkUpdateSilently = async () => {
  if (updateChecking.value || updateJob || !authStore.hasPermission('settings:view')) return
  updateChecking.value = true
  try {
    const result = await checkUpdate()
    if (disposed || updateJob) return
    updateInfo.value = result
    await loadUpdateHistory()
  } catch (_) {
    // Background checks must not interrupt normal application use.
  } finally {
    updateChecking.value = false
  }
}

const openVersionDrawer = () => {
  versionDrawerVisible.value = true
  checkUpdateSilently()
}

const storeUpdateJob = (job) => {
  try {
    if (job) localStorage.setItem(UPDATE_JOB_KEY, JSON.stringify(job))
    else localStorage.removeItem(UPDATE_JOB_KEY)
  } catch (_) {}
}

const stopUpdatePolling = (clearSaved = true) => {
  if (updateTimer) window.clearTimeout(updateTimer)
  if (updatePageTimer) window.clearTimeout(updatePageTimer)
  updatePageController?.abort()
  updateTimer = null
  updatePageTimer = null
  updatePageController = null
  updateJob = null
  if (clearSaved) storeUpdateJob(null)
}

const finishUpdateWithError = (message, status) => {
  stopUpdatePolling()
  updateInfo.value = { ...(updateInfo.value || {}), updating: false, update_waiting: false, update_error: message, update_status: status }
  versionDrawerVisible.value = true
  ElMessage.error(message)
}

const finishUpdateWaiting = (message) => {
  if (updateTimer) window.clearTimeout(updateTimer)
  updateTimer = null
  updateInfo.value = { ...(updateInfo.value || {}), updating: false, update_waiting: true, update_message: message }
  versionDrawerVisible.value = true
}

const pollUpdate = async (manual = false) => {
  const job = updateJob
  if (!job || disposed) return
  if (!manual && Date.now() - job.startedAt >= UPDATE_WAIT_LIMIT) {
    finishUpdateWaiting('等待更新超过 10 分钟，尚未确认完成。请查询状态确认结束，确认前不要重复提交更新。')
    return
  }
  try {
    const status = await getUpdateStatus()
    if (disposed || updateJob !== job) return
    updateInfo.value = { ...(updateInfo.value || {}), updating: true, update_status: status }
    // The agent retains its previous terminal state; it must match this job.
    if (status.latest_version === job.targetVersion) {
      if (status.status === 'running') {
        job.confirmed = true
        storeUpdateJob(job)
        updateInfo.value.update_message = '正在更新，服务可能暂时重启，等待恢复后页面会自动刷新'
      }
      if (status.status === 'failed' && job.confirmed) {
        finishUpdateWithError(`更新失败：${status.message || '请检查服务日志'}`, status)
        return
      }
      if (status.status === 'completed') {
        const version = await getUpdateVersion()
        if (disposed || updateJob !== job) return
        if (version.current_version === job.targetVersion) {
          const controller = new AbortController()
          updatePageController = controller
          updatePageTimer = window.setTimeout(() => controller.abort(), 5000)
          try {
            const page = await fetch(window.location.href, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal })
            const html = page.ok && page.headers.get('content-type')?.includes('text/html') ? await page.text() : ''
            if (disposed || updateJob !== job) return
            if (/<div[^>]+id=["']app["']/.test(html)) {
              stopUpdatePolling()
              window.location.reload()
              return
            }
          } finally {
            if (updatePageTimer) window.clearTimeout(updatePageTimer)
            updatePageTimer = null
            updatePageController = null
          }
        }
      }
    }
  } catch (error) {
    if (disposed || updateJob !== job) return
    if (error.response && ![502, 503, 504].includes(error.response.status)) {
      finishUpdateWaiting(error.response.data?.detail || '无法读取更新状态，请检查权限或服务器更新记录。确认结束前不要重复提交更新。')
      return
    }
    // A restart may close connections or temporarily return a gateway error.
  }
  if (!disposed && updateJob === job) {
    if (Date.now() - job.startedAt >= UPDATE_WAIT_LIMIT) {
      finishUpdateWaiting('更新仍未确认完成，请稍后再次查询状态。确认结束前不要重复提交更新。')
    } else {
      updateTimer = window.setTimeout(() => pollUpdate(), 3000)
    }
  }
}

const beginUpdatePolling = (job) => {
  stopUpdatePolling(false)
  updateJob = job
  storeUpdateJob(job)
  updateInfo.value = { ...(updateInfo.value || {}), current_version: updateInfo.value?.current_version || APP_VERSION, updating: true, update_waiting: false, update_error: '' }
  versionDrawerVisible.value = true
}

const resumeUpdate = async (manual = false) => {
  if (disposed || updateChecking.value || !authStore.hasPermission('settings:view')) return
  updateChecking.value = true
  try {
    const saved = JSON.parse(localStorage.getItem(UPDATE_JOB_KEY) || 'null')
    if (saved?.targetVersion && Number.isFinite(saved.startedAt)) {
      if (!manual && Date.now() - saved.startedAt >= UPDATE_WAIT_LIMIT) {
        updateJob = saved
        updateInfo.value = { ...(updateInfo.value || {}), current_version: APP_VERSION, updating: false, update_waiting: true, update_message: '上次更新仍未确认完成，请查询状态确认结束，确认前不要重复提交更新。' }
        versionDrawerVisible.value = true
        return
      }
      beginUpdatePolling(saved)
      await pollUpdate(manual)
      return
    }
    const status = await getUpdateStatus()
    if (disposed) return
    if (status.status === 'running' && status.latest_version) {
      beginUpdatePolling({ targetVersion: status.latest_version, startedAt: Date.now(), confirmed: true })
      await pollUpdate()
    }
  } catch (_) {
    // An unavailable agent alone does not imply that an update was submitted.
  } finally {
    updateChecking.value = false
  }
}

const handleApplyUpdate = async () => {
  if (updateApplying.value || updateJob || !updateInfo.value?.has_update) return
  updateApplying.value = true
  try {
    await ElMessageBox.confirm(
      `确认更新到 v${updateInfo.value.latest_version}？更新期间服务会短暂重启。`,
      '确认更新',
      { type: 'warning', confirmButtonText: '开始更新', cancelButtonText: '取消' }
    )
  } catch (_) {
    updateApplying.value = false
    return
  }
  if (disposed) return
  beginUpdatePolling({ targetVersion: updateInfo.value.latest_version, startedAt: Date.now(), confirmed: false })
  try {
    const status = await applyUpdate()
    if (disposed || !updateJob) return
    updateJob.confirmed = true
    if (status.latest_version) {
      updateJob.targetVersion = status.latest_version
    }
    storeUpdateJob(updateJob)
  } catch (error) {
    if (disposed) return
    if (error.response && [400, 401, 403, 404, 422].includes(error.response.status)) {
      finishUpdateWithError(error.response.data?.detail || '提交更新失败，请检查服务器更新记录。')
      return
    }
    if (error.response && ![502, 503, 504].includes(error.response.status)) {
      const message = error.response.data?.detail || '提交更新失败，请检查服务器更新记录。'
      finishUpdateWaiting(`${message} 正在确认服务器状态，请勿重复提交更新。`)
      return
    }
    updateInfo.value = { ...updateInfo.value, update_message: '提交响应中断，正在确认更新状态，请勿重复提交' }
  } finally {
    updateApplying.value = false
  }
  // A lost POST response must be resolved through status, never by retrying it.
  if (updateJob && !disposed) pollUpdate()
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
onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await resumeUpdate()
  if (disposed) return
  checkUpdateSilently()
  updateCheckTimer = window.setInterval(checkUpdateSilently, 10 * 60 * 1000)
})
onUnmounted(() => {
  disposed = true
  stopUpdatePolling(false)
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
  min-height: 0;
  overflow-y: auto;
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
