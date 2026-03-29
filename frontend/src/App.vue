<template>
  <div v-if="$route.name === 'Login'" class="min-h-screen">
    <router-view />
  </div>
  <div v-else class="min-h-screen flex" :class="impersonating ? 'pt-9' : ''">
    <!-- Impersonation banner -->
    <div v-if="impersonating" class="fixed top-0 left-0 right-0 z-50 bg-amber-500/90 text-black text-center py-1.5 text-sm font-medium backdrop-blur-sm">
      Viewing as <strong>{{ impersonatingUsername }}</strong>
      <button @click="stopImpersonating" class="ml-3 px-2 py-0.5 bg-black/20 hover:bg-black/30 rounded text-xs font-bold transition-colors">
        Stop
      </button>
    </div>
    <Sidebar />
    <main class="flex-1 ml-0 px-4 py-5 md:px-8 md:py-6 lg:px-10 lg:py-8 pb-24 lg:pb-8 min-h-screen overflow-auto transition-all duration-200"
      :class="collapsed ? 'lg:ml-16' : 'lg:ml-60'">
      <router-view />
    </main>
    <BottomNav />
  </div>
  <ProcessManager />
  <AdminNotifier />
  <WelcomeModal />
  <ToastContainer />
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import BottomNav from './components/BottomNav.vue'
import ToastContainer from './components/ToastContainer.vue'
import ProcessManager from './components/ProcessManager.vue'
import AdminNotifier from './components/AdminNotifier.vue'
import WelcomeModal from './components/WelcomeModal.vue'
import { useSidebar } from './useSidebar'
import { getCurrentUser, isAuthenticated, isImpersonating, api, setAuth, logout } from './api'

const { collapsed } = useSidebar()
const router = useRouter()

// On startup, validate session with backend and refresh user profile
onMounted(async () => {
  if (!isAuthenticated()) return
  try {
    const res = await api.getMe()
    if (res.user) {
      localStorage.setItem('te_user', JSON.stringify(res.user))
    }
  } catch {
    // Token rejected by backend — force re-login
    logout()
    router.push({ name: 'Login' })
  }
})

const impersonating = computed(() => isImpersonating())
const impersonatingUsername = computed(() => {
  const user = getCurrentUser()
  return user?.impersonating?.username || ''
})

async function stopImpersonating() {
  const res = await api.stopImpersonate()
  setAuth(res.auth_token, res.user || getCurrentUser())
  location.reload()
}
</script>
