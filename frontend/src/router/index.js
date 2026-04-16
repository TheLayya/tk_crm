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
      meta: { requiresAuth: true, permission: 'monitor:view', breadcrumb: '监控管理' }
    },
    {
      path: '/accounts/:id',
      name: 'AccountDetail',
      component: () => import('../views/AccountDetail.vue'),
      meta: { requiresAuth: true, breadcrumb: '账号详情' }
    },
    {
      path: '/op-accounts',
      name: 'OpAccountList',
      component: () => import('../views/OpAccountList.vue'),
      meta: { requiresAuth: true, permission: 'op_account:view', breadcrumb: '运营账号' }
    },
    {
      path: '/proxy-nodes',
      name: 'ProxyNodeManage',
      component: () => import('../views/ProxyNodeManage.vue'),
      meta: { requiresAuth: true, breadcrumb: '节点管理' }
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('../views/Settings.vue'),
      meta: { requiresAuth: true, permission: 'settings:view', breadcrumb: '系统设置' }
    },
    {
      path: '/team',
      meta: { breadcrumb: '团队管理' },
      children: [
        {
          path: 'dept',
          name: 'DeptManage',
          component: () => import('@/views/team/DeptManage.vue'),
          meta: { requiresAuth: true, permission: 'team:dept:view', breadcrumb: '部门管理' }
        },
        {
          path: 'member',
          name: 'MemberManage',
          component: () => import('@/views/team/MemberManage.vue'),
          meta: { requiresAuth: true, permission: 'team:member:view', breadcrumb: '成员管理' }
        },
        {
          path: 'role',
          name: 'RoleManage',
          component: () => import('@/views/team/RoleManage.vue'),
          meta: { requiresAuth: true, permission: 'team:role:view', breadcrumb: '角色管理' }
        },
        {
          path: 'log',
          name: 'LogView',
          component: () => import('@/views/team/LogView.vue'),
          meta: { requiresAuth: true, permission: 'team:log:view', breadcrumb: '操作日志' }
        }
      ]
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
