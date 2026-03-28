<template>
  <div class="fixed top-4 right-4 z-[100] space-y-2 max-w-sm">
    <TransitionGroup name="notif">
      <div v-for="n in notifications" :key="n.id"
        class="flex items-start gap-3 px-4 py-3 rounded-2xl shadow-lg border backdrop-blur-xl cursor-pointer bg-brand-900/90 border-brand-500/30 text-brand-200"
        @click="dismiss(n.id)">
        <span class="mt-0.5 flex-shrink-0">
          <svg v-if="n.icon === 'issue'" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
          <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"/></svg>
        </span>
        <p class="text-sm flex-1">{{ n.message }}</p>
        <button @click.stop="dismiss(n.id)" class="flex-shrink-0 opacity-60 hover:opacity-100">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useWebSocket } from '../useWebSocket'
import { isAdmin } from '../api'

const notifications = ref([])
let idCounter = 0

function show(message, icon = 'info', duration = 6000) {
  const id = ++idCounter
  notifications.value.push({ id, message, icon })
  if (duration > 0) setTimeout(() => dismiss(id), duration)
}

function dismiss(id) {
  notifications.value = notifications.value.filter(n => n.id !== id)
}

useWebSocket((msg) => {
  if (msg.event !== 'system.admin_notification') return
  if (!isAdmin()) return

  const data = msg.data
  if (!data) return

  if (data.type === 'new_issue') {
    const priority = data.priority === 'high' ? ' [HIGH]' : data.priority === 'critical' ? ' [CRITICAL]' : ''
    show(`New issue${priority}: "${data.title}" by ${data.username}`, 'issue')
  } else if (data.type === 'new_user') {
    const display = data.name ? `${data.name} (@${data.username})` : `@${data.username}`
    show(`New user registered: ${display}`, 'user')
  }
})
</script>

<style scoped>
.notif-enter-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.notif-leave-active { transition: all 0.2s ease-in; }
.notif-enter-from { transform: translateX(100%); opacity: 0; }
.notif-leave-to { transform: translateX(100%); opacity: 0; }
.notif-move { transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
</style>
