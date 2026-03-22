<template>
  <div v-if="visible" class="space-y-1">
    <div class="flex items-center justify-between text-xs">
      <span class="text-surface-400">{{ label }}</span>
      <span class="text-surface-300 font-mono">{{ Math.round(percent) }}%</span>
    </div>
    <div class="w-full h-2 bg-surface-800 rounded-full overflow-hidden">
      <div class="h-full bg-brand-500 rounded-full transition-all duration-300 ease-out"
        :style="{ width: percent + '%' }"></div>
    </div>
    <div v-if="eta > 0" class="text-xs text-surface-500 text-right">
      ~{{ formatEta(eta) }} remaining
    </div>
  </div>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  percent: { type: Number, default: 0 },
  eta: { type: Number, default: 0 },
  label: { type: String, default: 'Progress' },
})

function formatEta(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}
</script>
