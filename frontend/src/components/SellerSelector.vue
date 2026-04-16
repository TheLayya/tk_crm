<template>
  <div class="seller-selector">
    <el-select
      :model-value="modelValue"
      multiple
      filterable
      clearable
      :placeholder="placeholder"
      :disabled="disabled"
      :loading="loading"
      style="width: 100%"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <el-option
        v-for="member in members"
        :key="member.username"
        :label="member.real_name ? `${member.real_name}（${member.username}）` : member.username"
        :value="member.username"
      />
    </el-select>
    <div v-if="error" class="seller-selector__error">
      <span>加载成员失败</span>
      <el-button link type="primary" size="small" @click="loadMembers">重试</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getMembers } from '@/api/team'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  placeholder: {
    type: String,
    default: '选择出售人'
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

defineEmits(['update:modelValue'])

const members = ref([])
const loading = ref(false)
const error = ref(false)

async function loadMembers() {
  loading.value = true
  error.value = false
  try {
    const res = await getMembers({ page: 1, size: 200 })
    members.value = res.items || []
  } catch (e) {
    error.value = true
    members.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadMembers)
</script>

<style scoped>
.seller-selector__error {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
