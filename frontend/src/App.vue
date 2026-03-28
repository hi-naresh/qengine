<template>
  <div v-if="$route.name === 'Login'" class="min-h-screen">
    <router-view />
  </div>
  <div v-else class="min-h-screen flex">
    <Sidebar />
    <main class="flex-1 ml-0 px-4 py-5 md:px-8 md:py-6 lg:px-10 lg:py-8 pb-24 lg:pb-8 min-h-screen overflow-auto transition-all duration-200"
      :class="collapsed ? 'lg:ml-16' : 'lg:ml-60'">
      <router-view />
    </main>
    <BottomNav />
  </div>
  <ProcessManager />
  <ToastContainer />
</template>

<script setup>
import Sidebar from './components/Sidebar.vue'
import BottomNav from './components/BottomNav.vue'
import ToastContainer from './components/ToastContainer.vue'
import ProcessManager from './components/ProcessManager.vue'
import { useSidebar } from './useSidebar'

const { collapsed } = useSidebar()
</script>
