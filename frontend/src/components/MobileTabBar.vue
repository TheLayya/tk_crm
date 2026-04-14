<template>
  <div class="mobile-tab-bar">
    <div
      v-for="tab in tabs"
      :key="tab.key"
      class="tab-item"
      :class="{ 'is-active': activeTab === tab.key }"
      @click="router.push(tab.key)"
    >
      <el-icon class="tab-icon"><component :is="tab.icon" /></el-icon>
      <span class="tab-label">{{ tab.label }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Briefcase, UserFilled, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const tabs = computed(() => [
  {
    key: '/monitor',
    label: '监控',
    icon: Monitor,
    permission: 'monitor:view'
  },
  {
    key: '/op-accounts',
    label: '运营',
    icon: Briefcase,
    permission: 'op_account:view'
  },
  {
    key: '/team/member',
    label: '团队',
    icon: UserFilled,
    permission: 'team:member:view'
  },
  {
    key: '/settings',
    label: '设置',
    icon: Setting,
    permission: 'settings:view'
  }
].filter(tab => authStore.hasPermission(tab.permission)))

const activeTab = computed(() => {
  const path = route.path
  if (path.startsWith('/monitor') || path.startsWith('/accounts')) return '/monitor'
  if (path.startsWith('/op-accounts')) return '/op-accounts'
  if (path.startsWith('/team')) return '/team/member'
  if (path.startsWith('/settings')) return '/settings'
  return ''
})
</script>

<style scoped>
.mobile-tab-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 49px; /* fallback */
  height: calc(49px + env(safe-area-inset-bottom));
  padding-bottom: 0; /* fallback */
  padding-bottom: env(safe-area-inset-bottom);
  background: rgba(249, 249, 249, 0.94);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-top: 0.5px solid rgba(0, 0, 0, 0.12);
  display: flex;
  align-items: flex-start;
  padding-top: 6px;
  z-index: 100;
}

.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-height: 44px;
  cursor: pointer;
  color: #8E8E93;
  transition: color 0.15s ease;
}

.tab-item.is-active {
  color: #007AFF;
}

.tab-icon {
  font-size: 22px;
}

.tab-label {
  font-size: 10px;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
  font-weight: 500;
  letter-spacing: -0.1px;
}
</style>
