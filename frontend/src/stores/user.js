import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/index.js'

export const useUserStore = defineStore('user', () => {
  // ── state ──
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(null)

  // ── getters ──
  const isLoggedIn = computed(() => !!token.value && !!user.value)

  // ── actions ──
  function setToken(t) {
    token.value = t
    if (t) {
      localStorage.setItem('token', t)
    } else {
      localStorage.removeItem('token')
    }
  }

  async function login(username, password) {
    const res = await api.login(username, password)
    setToken(res.access_token)
    await fetchUser()
    return res
  }

  async function register(username, password) {
    const res = await api.register(username, password)
    return res
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      user.value = await api.me()
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    setToken('')
  }

  return {
    token,
    user,
    isLoggedIn,
    login,
    register,
    fetchUser,
    logout,
    setToken,
  }
})
