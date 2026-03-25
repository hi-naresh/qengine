<template>
  <div v-if="$route.name === 'Login'" class="min-h-screen">
    <router-view />
  </div>
  <div v-else class="min-h-screen flex">
    <Sidebar />
    <main class="flex-1 ml-0 lg:ml-60 px-4 py-5 md:px-8 md:py-6 lg:px-10 lg:py-8 pb-24 lg:pb-8 min-h-screen overflow-auto">
      <router-view />
    </main>
    <BottomNav />
  </div>
  <ToastContainer />
</template>

<script setup>
import Sidebar from './components/Sidebar.vue'
import BottomNav from './components/BottomNav.vue'
import ToastContainer from './components/ToastContainer.vue'
</script>
