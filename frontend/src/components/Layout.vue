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
        <el-icon v-else class="logo-symbol"><Monitor /></el-icon>
        <span v-if="!sidebarCollapsed" class="logo-text">{{ settings.site_name }}</span>
      </div>
      <div v-if="!sidebarCollapsed" class="workspace-caption">团队工作台</div>
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
      <el-header class="header" :class="{ 'header-mobile': isMobile }" :height="isMobile ? undefined : '56px'">
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
          <div class="header-context"><Breadcrumb :isMobile="isMobile" /></div>
          <div class="header-right">
            <MemoReminder v-if="authStore.hasPermission('work_item:view')" />
            <div class="user-identity"><span class="user-avatar" aria-hidden="true">{{ (authStore.user?.real_name || authStore.user?.username || '团').slice(0, 1) }}</span><span class="username">{{ authStore.user?.real_name || authStore.user?.username }}</span></div>
            <el-button link @click="handleLogout">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-button>
          </div>
        </template>
      </el-header>

      <el-main class="main-content">
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
const APP_VERSION = '1.1.23'
const versionDrawerVisible = ref(false)
const RELEASES = [
  {
    version: APP_VERSION,
    date: '2026-10-16',
    items: ['长卡密单行预览，点击查看全文并完整复制', '卡密记录按视口自适应滚动，分页保持可见', '成员工作量独立页签，按日期和成员查看汇总与明细']
  },
  {
    version: '1.1.22',
    date: '2026-10-15',
    items: ['卡密导入支持批次名称和备注，领取可指定批次', '异常批次支持暂停、恢复、删除或保留历史归档', '统一内部工作台视觉与中文控件，邮箱支持批量状态修改']
  },
  {
    version: '1.1.20',
    date: '2026-10-15',
    items: ['邮箱导入逐行识别混合三至六项格式', '支持带国家格式、空列和错列 2FA 密钥', '增加逗号和 Tab 分隔，重复邮箱自动跳过']
  },
  {
    version: '1.1.19',
    date: '2026-10-12',
    items: ['邮箱支持批量售出，一次登记客户与单价', '售出后自动复制整批交付资料，支持失败重试', '邮箱详情显示 2FA 验证码，支持每页 500 条']
  },
  {
    version: '1.1.18',
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
  height: 100dvh;
}

.sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #172333;
  color: #d3dce7;
  border-right: 1px solid #223247;
  transition: width 160ms ease;
}

.logo {
  height: 68px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
}

.logo-collapsed { padding: 0 12px; justify-content: center; }
.logo-text { font-size: 16px; font-weight: 650; letter-spacing: -.3px; color: #f1f5fa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.logo-symbol { width: 28px; height: 28px; flex-shrink: 0; color: #91baf0; font-size: 22px; }
.logo-image { max-width: 48px; max-height: 36px; object-fit: contain; flex-shrink: 0; }
.logo-collapsed .logo-image { max-width: 36px; max-height: 36px; }
.workspace-caption { padding: 6px 22px 10px; color: #7e90a8; font-size: 11px; letter-spacing: 1px; }

.sidebar-menu {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #aebed0;
  --el-menu-hover-bg-color: #223247;
  --el-menu-active-color: #e7f0fc;
  --el-menu-item-height: 42px;
  min-height: 0;
  overflow-y: auto;
  border-right: 0;
  background: transparent;
  flex: 1;
  padding: 0 0 12px;
  scrollbar-width: thin;
  scrollbar-color: #3b4c63 transparent;
}

.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  height: 42px;
  line-height: 42px;
  margin: 3px 10px;
  border-radius: 6px;
  color: #aebed0;
  font-size: 13px;
  transition: color 140ms ease, background-color 140ms ease;
}

.sidebar-menu :deep(.el-menu-item .el-icon) { font-size: 18px; margin-right: 10px; }
.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) { background: #223247; color: #f1f5fa; }
.sidebar-menu :deep(.el-menu-item.is-active) { background: #293d56; color: #f1f6ff; box-shadow: inset 3px 0 #86b6f4; font-weight: 600; }
.sidebar-menu :deep(.el-menu--inline) { background: #142030; }
.sidebar-menu :deep(.el-menu--inline .el-menu-item) { min-width: unset; }
.sidebar-menu :deep(.el-menu-item:focus-visible) { outline: 2px solid #86b6f4; outline-offset: -2px; }
.sidebar-collapsed .sidebar-menu { width: 64px; }
.sidebar-collapsed .sidebar-menu :deep(.el-menu-item) { margin: 4px 8px; padding: 0; justify-content: center; }
.sidebar-collapsed .sidebar-menu :deep(.el-menu-item .el-icon) { margin: 0; }

.sidebar-version {
  flex-shrink: 0;
  width: calc(100% - 24px);
  min-height: 44px;
  margin: 0 12px;
  padding: 0 10px;
  border: 0;
  border-top: 1px solid #2a394c;
  background: transparent;
  color: #8fa1b8;
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}
.sidebar-version:hover { color: #e3edf9; }
.sidebar-version:focus-visible { outline: 2px solid #86b6f4; outline-offset: -2px; }
.sidebar-collapsed .sidebar-version { width: 100%; margin: 0; padding: 0; text-align: center; font-size: 10px; }
.version-update-dot { display: inline-block; width: 7px; height: 7px; margin-left: 6px; border-radius: 50%; background: #ef8a87; vertical-align: middle; }

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 16px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid var(--color-border);
}
.header-context { min-width: 0; overflow: hidden; }
.header-context :deep(.breadcrumb-nav) { padding: 0; white-space: nowrap; font-size: 13px; }
.header-context :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) { color: var(--color-text-primary); font-weight: 600; }
.header-context :deep(.el-breadcrumb__separator) { color: #bac3cf; font-weight: 400; margin: 0 12px; }
.header-right { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.user-identity { display: flex; align-items: center; gap: 8px; padding-left: 16px; border-left: 1px solid var(--color-border); }
.user-avatar { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: #edf2f8; border: 1px solid #dfe6ef; border-radius: 7px; color: #3d5879; font-size: 12px; font-weight: 600; }
.username { font-size: 13px; color: #425268; }
.header-right :deep(.el-button.is-link) { font-size: 12px; color: #64758b; }
.header-right :deep(.el-button.is-link:hover) { color: var(--color-accent); }

.main-content { background: var(--color-bg-page); padding: 18px 20px 24px; }

/* Mobile keeps its fixed navigation and touch targets. */
.header-mobile {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: calc(44px + env(safe-area-inset-top));
  padding-top: env(safe-area-inset-top);
  padding-left: 8px;
  padding-right: 8px;
  background: rgba(255, 255, 255, .94);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--color-border);
  z-index: 100;
}
.header-mobile-left { width: 44px; flex-shrink: 0; }
.header-mobile-right { width: 88px; display: flex; align-items: center; justify-content: flex-end; gap: 4px; flex-shrink: 0; }
.header-mobile-right :deep(.el-button) { min-width: 36px; min-height: 44px; }
.header-title { position: absolute; left: 50%; transform: translateX(-50%); font-size: 17px; font-weight: 600; color: var(--color-text-primary); letter-spacing: -.4px; }
.logout-icon-btn { min-height: 44px; min-width: 44px; display: flex; align-items: center; justify-content: center; color: var(--color-accent); }

.version-history { color: var(--color-text-primary); }
.version-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.version-actions > span { flex: 1; color: var(--color-text-secondary); font-size: 13px; }
.update-changes, .release-item ul { margin: 12px 0 0; padding-left: 20px; color: var(--color-text-secondary); line-height: 1.8; }
.release-item + .release-item { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--color-border); }
.release-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.release-heading strong { font-size: 18px; }
.release-heading span { color: var(--color-text-muted); font-size: 12px; }

@media (min-width: 769px) and (max-width: 1180px) {
  .main-content { padding: 16px; }
  .header { padding: 0 16px; }
}
@media (max-width: 768px) {
  .main-content {
    padding-top: calc(44px + env(safe-area-inset-top) + 12px) !important;
    padding-bottom: calc(49px + env(safe-area-inset-bottom) + 12px) !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    background: var(--ios-bg);
  }
}
</style>
