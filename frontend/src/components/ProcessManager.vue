<template>
  <!-- Only render when there are processes -->
  <Transition name="pm-slide">
    <div v-if="list.length" class="fixed bottom-36 lg:bottom-16 right-3 sm:right-4 z-[90] sm:max-w-xs w-[calc(100%-1.5rem)] sm:w-80">

      <!-- Minimized badge -->
      <div v-if="minimized" @click="minimized = false"
        class="ml-auto w-fit flex items-center gap-2 px-3 py-2 rounded-xl bg-surface-800/95 backdrop-blur-xl border border-surface-700/50 shadow-lg cursor-pointer hover:border-surface-600 transition-colors">
        <span class="relative flex h-2.5 w-2.5">
          <span v-if="running.length" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5" :class="running.length ? 'bg-brand-500' : 'bg-green-500'"></span>
        </span>
        <span class="text-xs text-surface-300 font-medium">
          {{ running.length ? `${running.length} running` : `${finished.length} done` }}
        </span>
        <!-- Mini progress for first running task -->
        <div v-if="running.length" class="w-12 h-1.5 bg-surface-700 rounded-full overflow-hidden">
          <div class="h-full bg-brand-500 rounded-full transition-all duration-500" :style="{ width: running[0].progress + '%' }"></div>
        </div>
      </div>

      <!-- Expanded panel -->
      <div v-else class="rounded-xl bg-surface-800/95 backdrop-blur-xl border border-surface-700/50 shadow-xl overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-3 py-2 border-b border-surface-700/50">
          <span class="text-xs font-medium text-surface-300">Processes</span>
          <div class="flex items-center gap-1">
            <button v-if="finished.length" @click="clearFinished"
              class="text-[10px] text-surface-500 hover:text-surface-300 px-1.5 py-0.5 rounded hover:bg-surface-700 transition-colors">
              Clear done
            </button>
            <button @click="minimized = true"
              class="text-surface-500 hover:text-surface-300 p-1 rounded hover:bg-surface-700 transition-colors">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M19 13H5"/></svg>
            </button>
          </div>
        </div>

        <!-- Process list -->
        <TransitionGroup name="pm-item" tag="div" class="max-h-64 overflow-y-auto">
          <div v-for="p in list" :key="p.id" class="px-3 py-2.5 border-b border-surface-700/30 last:border-b-0">
            <div class="flex items-center gap-2">
              <!-- Status indicator -->
              <span class="flex-shrink-0 w-2 h-2 rounded-full"
                :class="{
                  'bg-brand-500 animate-pulse': p.status === 'running',
                  'bg-green-500': p.status === 'completed',
                  'bg-red-500': p.status === 'error',
                  'bg-surface-500': p.status === 'cancelled'
                }"></span>

              <!-- Label + type -->
              <div class="flex-1 min-w-0">
                <div class="text-xs text-surface-200 truncate">{{ p.label }}</div>
                <div class="text-[10px] text-surface-500 flex items-center gap-1.5">
                  <span class="capitalize">{{ p.type }}</span>
                  <span v-if="p.status === 'running' && p.eta > 0">&middot; ~{{ formatEta(p.eta) }}</span>
                  <span v-if="p.status === 'completed'" class="text-green-400">Done</span>
                  <span v-if="p.status === 'error'" class="text-red-400">Failed</span>
                  <span v-if="p.status === 'cancelled'" class="text-surface-400">Cancelled</span>
                </div>
              </div>

              <!-- Actions -->
              <div class="flex items-center gap-1 flex-shrink-0">
                <!-- Navigate to page -->
                <button v-if="p.status === 'completed'" @click="goTo(p)"
                  class="text-[10px] text-brand-400 hover:text-brand-300 px-1.5 py-0.5 rounded hover:bg-surface-700 transition-colors"
                  title="View results">
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>
                </button>
                <!-- Cancel -->
                <button v-if="p.status === 'running' && p.cancelFn" @click="doCancel(p)"
                  class="text-[10px] text-surface-500 hover:text-red-400 px-1.5 py-0.5 rounded hover:bg-surface-700 transition-colors"
                  title="Cancel">
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
                <!-- Dismiss finished -->
                <button v-if="p.status !== 'running'" @click="remove(p.id)"
                  class="text-surface-600 hover:text-surface-400 p-0.5 rounded hover:bg-surface-700 transition-colors"
                  title="Dismiss">
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
              </div>
            </div>

            <!-- Progress bar (running only) -->
            <div v-if="p.status === 'running'" class="mt-1.5 w-full h-1.5 bg-surface-700 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all duration-500 ease-out"
                :class="p.type === 'monte-carlo' ? 'bg-purple-500' : p.type === 'optimization' ? 'bg-amber-500' : p.type === 'import' ? 'bg-cyan-500' : 'bg-brand-500'"
                :style="{ width: p.progress + '%' }"></div>
            </div>
          </div>
        </TransitionGroup>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProcessManager } from '../useProcessManager'
import { useWebSocket } from '../useWebSocket'

const router = useRouter()
const pm = useProcessManager()
const { list, running, finished, remove, get, update, complete, fail, cancel } = pm
const minimized = ref(false)

// Global WS listener — keeps progress updating even when navigated away from source pages
useWebSocket((msg) => {
  const { event, data, id } = msg

  if (event === 'backtest.progressbar' && id && get(id)) {
    update(id, { progress: data?.current || 0, eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'backtest.metrics' && id && get(id)) {
    complete(id)
  } else if (event === 'backtest.exception' && id && get(id)) {
    fail(id)
  } else if (event === 'backtest.termination' && id && get(id)) {
    cancel(id)
  } else if (event === 'monte-carlo.trades_progressbar' && get(currentMcId())) {
    // MC events don't carry an id on the WS message, use the registered MC process
    const mcId = currentMcId()
    if (mcId) {
      const p = get(mcId)
      // Estimate overall from trades progress (will be corrected by candles too)
      if (p) update(mcId, { eta: data?.estimated_remaining_seconds || 0 })
    }
  } else if (event === 'monte-carlo.candles_progressbar' && get(currentMcId())) {
    const mcId = currentMcId()
    if (mcId) update(mcId, { eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'monte-carlo.alert' && data?.type === 'success') {
    const mcId = currentMcId()
    if (mcId) complete(mcId)
  } else if (event === 'monte-carlo.exception') {
    const mcId = currentMcId()
    if (mcId) fail(mcId)
  } else if (event === 'monte-carlo.termination') {
    const mcId = currentMcId()
    if (mcId) cancel(mcId)
  } else if (event === 'monte-carlo.unexpectedTermination') {
    const mcId = currentMcId()
    if (mcId) fail(mcId)
  } else if (event === 'candles.progressbar') {
    const impId = currentImportId()
    if (impId) update(impId, { progress: data?.current || 0, eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'candles.alert') {
    const impId = currentImportId()
    if (impId) {
      if (data?.type === 'success') complete(impId)
      else if (data?.type === 'error') fail(impId)
    }
  } else if (event === 'candles.exception') {
    const impId = currentImportId()
    if (impId) fail(impId)
  } else if (event === 'candles.termination') {
    const impId = currentImportId()
    if (impId) cancel(impId)
  }
})

function currentMcId() {
  return running.value.find(p => p.type === 'monte-carlo')?.id || null
}

function currentImportId() {
  return running.value.find(p => p.type === 'import')?.id || null
}

function formatEta(seconds) {
  if (!seconds || seconds <= 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

function doCancel(p) {
  if (p.cancelFn) p.cancelFn()
}

function goTo(p) {
  router.push({ path: p.routePath, query: { session: p.id } })
  remove(p.id)
}

function clearFinished() {
  finished.value.forEach(p => remove(p.id))
}
</script>

<style scoped>
.pm-slide-enter-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.pm-slide-leave-active { transition: all 0.2s ease-in; }
.pm-slide-enter-from { transform: translateY(20px); opacity: 0; }
.pm-slide-leave-to { transform: translateY(20px); opacity: 0; }

.pm-item-enter-active { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.pm-item-leave-active { transition: all 0.15s ease-in; position: absolute; width: 100%; }
.pm-item-enter-from { opacity: 0; transform: translateX(20px); }
.pm-item-leave-to { opacity: 0; transform: translateX(-20px); }
.pm-item-move { transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
</style>
