<template>
  <section class="account-emails" v-loading="loading">
    <b>关联邮箱</b>
    <span v-if="error">加载失败 <el-button link @click="load">重试</el-button></span>
    <template v-else>
      <span v-if="!current.length">暂无当前关联</span>
      <el-tag v-for="relation in current" :key="relation.id" size="small" type="success">{{ relation.email }}{{ relation.check_status ? ` · ${relation.check_status}` : '' }}</el-tag>
      <details v-if="history.length"><summary>历史关联 {{ history.length }} 次</summary><div v-for="relation in history" :key="relation.id">{{ relation.email }} · 已解绑</div></details>
      <el-button link type="primary" @click="router.push('/emails')">管理邮箱</el-button>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import request from '@/api/request'
const props = defineProps({ accountId: { type: Number, required: true } })
const router = useRouter()
const relations = ref([])
const loading = ref(false)
const error = ref(false)
const current = computed(() => relations.value.filter(row => !row.unbound_at))
const history = computed(() => relations.value.filter(row => row.unbound_at))
const load = async () => {
  loading.value = true
  error.value = false
  try { relations.value = await request.get(`/emails/for-account/${props.accountId}`) }
  catch { error.value = true }
  finally { loading.value = false }
}
watch(() => props.accountId, load, { immediate: true })
</script>

<style scoped>
.account-emails { display:flex; align-items:center; flex-wrap:wrap; gap:6px 10px; padding:8px 0; font-size:12px; border-top:1px solid #edf0f5; }
.account-emails > b { color:#909399; font-weight:500; }
summary { cursor:pointer; }
</style>
