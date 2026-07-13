import { createRouter, createWebHistory } from 'vue-router'

import MainLayout from '../layouts/MainLayout.vue'
import ChatPage from '../pages/ChatPage.vue'
import MemoryPage from '../pages/MemoryPage.vue'
import SettingsPage from '../pages/SettingsPage.vue'
import LoginPage from '../pages/LoginPage.vue'
import RegisterPage from '../pages/RegisterPage.vue'

const routes = [
  { path: '/', redirect: '/chat' },

  // 无需认证的页面（无外壳，独立全屏布局）
  { path: '/login', component: LoginPage, meta: { guest: true } },
  { path: '/register', component: RegisterPage, meta: { guest: true } },

  // 需要认证的页面（MainLayout 外壳）
  {
    path: '/',
    component: MainLayout,
    meta: { requiresAuth: true },
    children: [
      { path: 'chat', component: ChatPage },
      { path: 'memories', component: MemoryPage },
      { path: 'settings', component: SettingsPage },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ── 路由守卫 ──
router.beforeEach(async (to) => {
  const token = localStorage.getItem('token')

  if (to.matched.some(r => r.meta.requiresAuth) && !token) {
    return '/login'
  }

  if (to.meta.guest && token) {
    return '/chat'
  }
})

export default router
