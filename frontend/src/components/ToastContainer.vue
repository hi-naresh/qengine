<template>
  <div class="fixed bottom-20 lg:bottom-4 right-3 left-3 sm:left-auto sm:right-4 z-[100] space-y-2 sm:max-w-sm">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id"
        class="flex items-start gap-3 px-4 py-3 rounded-2xl shadow-lg border backdrop-blur-xl cursor-pointer"
        :class="toastClass(t.type)"
        @click="dismiss(t.id)">
        <span class="mt-0.5 flex-shrink-0">
          <svg v-if="t.type === 'success'" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
          <svg v-else-if="t.type === 'error'" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>
          <svg v-else-if="t.type === 'warning'" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
          <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>
        </span>
        <p class="text-sm flex-1">{{ t.message }}</p>
        <button @click.stop="dismiss(t.id)" class="flex-shrink-0 opacity-60 hover:opacity-100">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { useToast } from '../useToast'
const { toasts, dismiss } = useToast()

function toastClass(type) {
  switch (type) {
    case 'success': return 'bg-green-900/90 border-green-500/30 text-green-300'
    case 'error': return 'bg-red-900/90 border-red-500/30 text-red-300'
    case 'warning': return 'bg-amber-900/90 border-amber-500/30 text-amber-300'
    default: return 'bg-surface-800/90 border-surface-600/30 text-surface-200'
  }
}
</script>

<style scoped>
/* Mobile: slide up from bottom with spring easing */
@media (hover: none) and (pointer: coarse) {
  .toast-enter-active { transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1); }
  .toast-leave-active { transition: all 0.2s ease-in; }
  .toast-enter-from { transform: translateY(100%); opacity: 0; }
  .toast-leave-to { transform: translateY(40%); opacity: 0; }
}
/* Desktop: slide from right */
@media (hover: hover) and (pointer: fine) {
  .toast-enter-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
  .toast-leave-active { transition: all 0.2s ease-in; }
  .toast-enter-from { transform: translateX(100%); opacity: 0; }
  .toast-leave-to { transform: translateX(100%); opacity: 0; }
}
.toast-move { transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
</style>
