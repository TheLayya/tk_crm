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
      path: '/overview',
      name: 'DataOverview',
      component: () => import('@/views/DataOverview.vue'),
      meta: { requiresAuth: true, permission: 'device:view', overviewAccess: true, breadcrumb: '数据总览' }
    },
    {
      path: '/op-accounts',
      name: 'OpAccountList',
      component: () => import('../views/OpAccountList.vue'),
      meta: { requiresAuth: true, permission: 'op_account:view', breadcrumb: '运营账号' }
    },
    {
      path: '/emails',
      name: 'EmailList',
      component: () => import('../views/EmailList.vue'),
      meta: { requiresAuth: true, permission: 'email:view', breadcrumb: '邮箱管理' }
    },
    {
      path: '/work-items',
      name: 'WorkItemList',
      component: () => import('../views/WorkItemList.vue'),
      meta: { requiresAuth: true, permission: 'work_item:view', breadcrumb: '备忘管理' }
    },
    {
      path: '/card-keys',
      name: 'CardKeyList',
      component: () => import('../views/CardKeyList.vue'),
      meta: { requiresAuth: true, permission: 'card_key:view', breadcrumb: '卡密管理' }
    },
    {
      path: '/proxy-nodes',
      name: 'ProxyNodeManage',
      component: () => import('../views/ProxyNodeManage.vue'),
      meta: { requiresAuth: true, permission: 'proxy_node:view', breadcrumb: '节点管理' }
    },
    {
      path: '/devices',
      name: 'DeviceList',
      component: () => import('../views/devices/DeviceList.vue'),
      meta: { requiresAuth: true, permission: 'device:view', breadcrumb: '终端资产' }
    },
    {
      path: '/devices/:id',
      name: 'DeviceDetail',
      component: () => import('../views/devices/DeviceDetail.vue'),
      meta: { requiresAuth: true, permission: 'device:view', breadcrumb: '设备详情' }
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('../views/Settings.vue'),
      meta: { requiresAuth: true, permission: 'settings:view', breadcrumb: '系统设置' }
    },
    {
      path: '/team',
      redirect: '/team/manage',
      meta: { breadcrumb: '团队管理' },
      children: [
        {
          path: 'manage',
          name: 'TeamManage',
          component: () => import('@/views/team/TeamManage.vue'),
          meta: { requiresAuth: true, teamAccess: true, breadcrumb: '成员管理' }
        },
        {
          path: 'dept',
          name: 'DeptManage',
          redirect: to => ({ path: '/team/manage', query: { ...to.query, panel: 'dept' } })
        },
        {
          path: 'member',
          name: 'MemberManage',
          redirect: to => ({ path: '/team/manage', query: to.query })
        },
        {
          path: 'role',
          name: 'RoleManage',
          redirect: to => ({ path: '/team/manage', query: { ...to.query, panel: 'role' } })
        },
        {
          path: 'log',
          name: 'LogView',
          redirect: to => ({ path: '/team/manage', query: { ...to.query, panel: 'log' } })
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
  if (to.meta.overviewAccess && !['device:view', 'op_account:view', 'proxy_node:view'].every(permission => authStore.hasPermission(permission))) return next('/403')
  if (to.meta.teamAccess) {
    const permissions = ['team:member:view', 'team:dept:view', 'team:role:view', 'team:log:view']
    if (!permissions.some(permission => authStore.hasPermission(permission))) return next('/403')
    const panelPermission = { dept: 'team:dept:view', role: 'team:role:view', log: 'team:log:view' }[to.query.panel]
    if (panelPermission && !authStore.hasPermission(panelPermission)) return next('/403')
  }
  next()
})

export default router
