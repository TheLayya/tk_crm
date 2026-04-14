<template>
  <router-view v-if="isAuthPage" />
  <Layout v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Layout from './components/Layout.vue'

const route = useRoute()
const isAuthPage = computed(() => ['/login', '/403'].includes(route.path))
</script>
