<template>
  <div class="min-h-screen flex items-center justify-center bg-surface-950">
    <div class="w-full max-w-sm px-4">
      <div class="text-center mb-8 flex flex-col items-center">
        <img src="/favicon.svg" alt="QEngine Logo" class="w-16 h-16 mb-4 drop-shadow-lg" />
        <h1 class="text-2xl font-bold text-surface-100 tracking-tight">QEngine</h1>
        <p class="text-sm text-surface-500 mt-1">Multi-asset quant engine for analysis and production pipelines</p>
      </div>

      <!-- Tabs -->
      <div class="flex mb-4 border-b border-surface-700">
        <button
          @click="tab = 'login'"
          :class="['flex-1 pb-2 text-sm font-medium transition-colors', tab === 'login' ? 'text-surface-100 border-b-2 border-primary-500' : 'text-surface-500 hover:text-surface-300']"
        >
          Sign In
        </button>
        <button
          @click="tab = 'register'"
          :class="['flex-1 pb-2 text-sm font-medium transition-colors', tab === 'register' ? 'text-surface-100 border-b-2 border-primary-500' : 'text-surface-500 hover:text-surface-300']"
        >
          Register
        </button>
      </div>

      <!-- Sign In Form -->
      <form v-if="tab === 'login'" @submit.prevent="handleLogin" class="card space-y-4">
        <div>
          <label class="label">Username</label>
          <input v-model="username" type="text" class="input" placeholder="Enter your username" autofocus />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="password" type="password" class="input" placeholder="Enter your password" />
        </div>
        <p v-if="error" class="text-red-400 text-xs">{{ error }}</p>
        <button type="submit" class="btn-primary w-full" :disabled="loading">
          {{ loading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>

      <!-- Register Form -->
      <form v-else @submit.prevent="handleRegister" class="card space-y-4">
        <div>
          <label class="label">Full Name</label>
          <input v-model="regName" type="text" class="input" placeholder="Enter your full name" autofocus />
        </div>
        <div>
          <label class="label">Username</label>
          <input v-model="regUsername" type="text" class="input" placeholder="Choose a username" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="regPassword" type="password" class="input" placeholder="Choose a password" />
        </div>
        <div>
          <label class="label">Confirm Password</label>
          <input v-model="regConfirm" type="password" class="input" placeholder="Confirm your password" />
        </div>
        <p v-if="error" class="text-red-400 text-xs">{{ error }}</p>
        <button type="submit" class="btn-primary w-full" :disabled="loading">
          {{ loading ? 'Creating account...' : 'Register' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setAuth } from '../api'

const router = useRouter()
const tab = ref('login')
const error = ref('')
const loading = ref(false)

// Login fields
const username = ref('')
const password = ref('')

// Register fields
const regName = ref('')
const regUsername = ref('')
const regPassword = ref('')
const regConfirm = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const res = await api.login(username.value, password.value)
    setAuth(res.auth_token, res.user)
    router.push('/')
  } catch (e) {
    error.value = e.message || 'Invalid credentials'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  error.value = ''
  if (regPassword.value !== regConfirm.value) {
    error.value = 'Passwords do not match'
    return
  }
  loading.value = true
  try {
    const res = await api.register(regUsername.value, regPassword.value, regName.value)
    setAuth(res.auth_token, res.user)
    localStorage.setItem('qe_show_welcome', 'true')
    router.push('/')
  } catch (e) {
    error.value = e.message || 'Registration failed'
  } finally {
    loading.value = false
  }
}
</script>
