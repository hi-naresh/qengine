<template>
  <div class="min-h-screen flex items-center justify-center bg-surface-950">
    <div class="w-full max-w-sm px-4">
      <div class="text-center mb-8 flex flex-col items-center">
        <img src="/favicon.svg" alt="QEngine Logo" class="w-16 h-16 mb-4 drop-shadow-lg" />
        <h1 class="text-2xl font-bold text-surface-100 tracking-tight">QEngine</h1>
        <p class="text-sm text-surface-500 mt-1">Multi-asset algorithmic trading platform</p>
      </div>

      <form @submit.prevent="handleLogin" class="card space-y-4">
        <div>
          <label class="label">Password</label>
          <input v-model="password" type="password" class="input" placeholder="Enter your password" autofocus />
        </div>
        <p v-if="error" class="text-red-400 text-xs">{{ error }}</p>
        <button type="submit" class="btn-primary w-full" :disabled="loading">
          {{ loading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setToken } from '../api'

const router = useRouter()
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const res = await api.login(password.value)
    setToken(res.auth_token)
    router.push('/')
  } catch (e) {
    error.value = 'Invalid password'
  } finally {
    loading.value = false
  }
}
</script>
