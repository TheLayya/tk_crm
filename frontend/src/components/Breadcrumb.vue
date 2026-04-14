<template>
  <el-breadcrumb v-if="!isMobile" separator="/" class="breadcrumb-nav">
    <el-breadcrumb-item
      v-for="item in breadcrumbs"
      :key="item.path"
    >
      <a v-if="!item.isLast" class="breadcrumb-link" @click.prevent="router.push(item.path)">
        {{ item.title }}
      </a>
      <span v-else>{{ item.title }}</span>
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { generateBreadcrumbs } from '@/utils/breadcrumb'

defineProps({
  isMobile: {
    type: Boolean,
    default: false
  }
})

const route = useRoute()
const router = useRouter()

const breadcrumbs = computed(() => generateBreadcrumbs(route.matched))
</script>

<style scoped>
.breadcrumb-nav {
  padding: 8px 16px 12px;
}

.breadcrumb-link {
  cursor: pointer;
  color: var(--el-text-color-regular);
  text-decoration: none;
}

.breadcrumb-link:hover {
  color: var(--el-color-primary);
}

@media (max-width: 768px) {
  .breadcrumb-nav {
    font-size: 12px;
  }
}
</style>
