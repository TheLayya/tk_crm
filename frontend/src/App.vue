<template>
  <router-view v-if="isAuthPage" />
  <Layout v-else />
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import Layout from './components/Layout.vue'
import { getPublicSettings } from '@/api/settings'

const route = useRoute()
const isAuthPage = computed(() => ['/login', '/403'].includes(route.path))

const updateSiteMeta = (settings) => {
  if (settings?.site_name) document.title = settings.site_name
  let favicon = document.querySelector('link[rel="icon"]')
  if (!favicon) {
    favicon = document.createElement('link')
    favicon.rel = 'icon'
    document.head.appendChild(favicon)
  }
  favicon.type = settings?.logo_image ? 'image/png' : 'image/svg+xml'
  favicon.href = settings?.logo_image || '/favicon.svg'
}

const handleSiteSettingsUpdated = (event) => updateSiteMeta(event.detail)

onUnmounted(() => window.removeEventListener('site-settings-updated', handleSiteSettingsUpdated))

onMounted(async () => {
  window.addEventListener('site-settings-updated', handleSiteSettingsUpdated)
  try {
    updateSiteMeta(await getPublicSettings())
  } catch {
    updateSiteMeta({ site_name: 'TikTok Monitor' })
  }
})
</script>
