import { createRouter, createWebHistory } from 'vue-router'
import UserInfo from '../components/UserInfo.vue'
import Home from '../components/Home.vue'
import ProxyAccess from '../components/ProxyAccess.vue'
import AdminPanel from '../components/AdminPanel.vue'
import NotFound from '../components/NotFound.vue'
import AuthLoginPage from '../components/auth/AuthLoginPage.vue'
import AuthRegisterPage from '../components/auth/AuthRegisterPage.vue'
import AuthPasswordPage from '../components/auth/AuthPasswordPage.vue'
import AppShell from '../components/app/AppShell.vue'
import AppOverviewPage from '../components/app/AppOverviewPage.vue'
import AppSubscriptionsPage from '../components/app/AppSubscriptionsPage.vue'
import AppPurchasePage from '../components/app/AppPurchasePage.vue'
import AppHelpPage from '../components/app/AppHelpPage.vue'
import AppProfilePage from '../components/app/AppProfilePage.vue'
import AppPaymentsPage from '../components/app/AppPaymentsPage.vue'
import { ensureSession } from '../stores/session'

const adminPathSegment = String(import.meta.env.VITE_ADMIN_PATH || '')
  .trim()
  .replace(/^\/+|\/+$/g, '')

const routes = [
  {
    path: '/subscription/:token',
    name: 'UserInfo',
    component: UserInfo,
    props: true
  },
  {
    path: '/subscription/whitelist/:token',
    name: 'WhiteListUserInfo',
    component: UserInfo,
    props: true
  },
  {
    path: '/proxy',
    alias: ['/proxy/'],
    name: 'ProxyAccess',
    component: ProxyAccess
  },
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/auth/login',
    name: 'AuthLogin',
    component: AuthLoginPage,
    meta: {
      guestOnly: true
    }
  },
  {
    path: '/auth/register',
    name: 'AuthRegister',
    component: AuthRegisterPage,
    meta: {
      guestOnly: true
    }
  },
  {
    path: '/auth/password',
    name: 'AuthPassword',
    component: AuthPasswordPage,
    meta: {
      guestOnly: true
    }
  },
  {
    path: '/app',
    component: AppShell,
    meta: {
      requiresAuth: true
    },
    children: [
      {
        path: '',
        name: 'AppOverview',
        component: AppOverviewPage,
      },
      {
        path: 'subscriptions',
        name: 'AppSubscriptions',
        component: AppSubscriptionsPage,
      },
      {
        path: 'purchase',
        name: 'AppPurchase',
        component: AppPurchasePage,
      },
      {
        path: 'help',
        name: 'AppHelp',
        component: AppHelpPage,
      },
      {
        path: 'payments',
        name: 'AppPayments',
        component: AppPaymentsPage,
      },
      {
        path: 'profile',
        name: 'AppProfile',
        component: AppProfilePage,
      },
    ]
  }

]

if (adminPathSegment) {
  routes.push({
    path: `/${adminPathSegment}`,
    name: 'AdminPanel',
    component: AdminPanel
  })
}

routes.push({
  path: '/:pathMatch(.*)*',
  name: 'NotFound',
  component: NotFound
})

export const router = createRouter({history: createWebHistory(), routes})

router.beforeEach(async (to) => {
  const requiresAuth = to.matched.some((record) => record.meta?.requiresAuth)
  const guestOnly = to.matched.some((record) => record.meta?.guestOnly)

  if (!requiresAuth && !guestOnly) {
    return true
  }

  let me = null
  try {
    me = await ensureSession()
  } catch (error) {
    console.error('Failed to resolve web session during navigation', error)

    if (guestOnly) {
      return true
    }

    return {
      path: '/auth/login',
      query: {
        next: to.fullPath,
        session_error: '1',
      },
    }
  }

  if (requiresAuth && !me) {
    return {
      path: '/auth/login',
      query: {
        next: to.fullPath,
      },
    }
  }

  if (guestOnly && me && typeof to.query.link_token !== 'string') {
    const next = typeof to.query.next === 'string' && to.query.next.startsWith('/')
      ? to.query.next
      : '/app'
    return next
  }

  return true
})
