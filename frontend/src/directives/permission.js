import { useAuthStore } from '@/stores/auth'

export const permission = {
  mounted(el, binding) {
    const authStore = useAuthStore()
    if (!authStore.hasPermission(binding.value)) {
      el.parentNode?.removeChild(el)
    }
  }
}

export default permission
