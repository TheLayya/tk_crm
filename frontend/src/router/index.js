import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/monitor'
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/403',
      name: 'Forbidden',
      component: () => import('@/views/Forbidden.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/monitor',
      name: 'MonitorManage',
      component: () => import('../views/MonitorManage.vue'),
      meta: { requiresAuth: true, permission: 'monitor:view' }
    },
    {
      path: '/accounts/:id',
      name: 'AccountDetail',
      component: () => import('../views/AccountDetail.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/op-accounts',
      name: 'OpAccountList',
      component: () => import('../views/OpAccountList.vue'),
      meta: { requiresAuth: true, permission: 'op_account:view' }
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('../views/Settings.vue'),
      meta: { requiresAuth: true, permission: 'settings:view' }
    },
    {
      path: '/team/dept',
      name: 'DeptManage',
      component: () => import('@/views/team/DeptManage.vue'),
      meta: { requiresAuth: true, permission: 'team:dept:view' }
    },
    {
      path: '/team/member',
      name: 'MemberManage',
      component: () => import('@/views/team/MemberManage.vue'),
      meta: { requiresAuth: true, permission: 'team:member:view' }
    },
    {
      path: '/team/role',
      name: 'RoleManage',
      component: () => import('@/views/team/RoleManage.vue'),
      meta: { requiresAuth: true, permission: 'team:role:view' }
    },
    {
      path: '/team/log',
      name: 'LogView',
      component: () => import('@/views/team/LogView.vue'),
      meta: { requiresAuth: true, permission: 'team:log:view' }
    }
  ]
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    return next('/login')
  }
  if (to.meta.permission && !authStore.hasPermission(to.meta.permission)) {
    return next('/403')
  }
  next()
})

export default router
