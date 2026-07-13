<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2><span></span> 登录树洞</h2>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="username" type="text" placeholder="请输入用户名" required />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入密码" required />
        </div>
        <button class="btn btn-primary" type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>
      <div class="auth-link">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const res = await api.login(username.value, password.value)
    localStorage.setItem('token', res.access_token)
    router.push('/chat')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
