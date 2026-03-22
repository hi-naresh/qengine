<template>
  <div v-if="$route.name === 'Login'" class="min-h-screen">
    <router-view />
  </div>
  <div v-else class="min-h-screen flex">
    <Sidebar />
    <main class="flex-1 ml-56 p-6 min-h-screen overflow-auto">
      <router-view />
    </main>
  </div>
  <ToastContainer />
</template>

<script setup>
import Sidebar from './components/Sidebar.vue'
import ToastContainer from './components/ToastContainer.vue'
</script>
