<template>
  <!-- Bottom Nav Bar — mobile only -->
  <nav class="fixed bottom-0 left-0 right-0 z-50 lg:hidden">
    <div class="bottom-nav-glass flex items-stretch justify-around px-2 mx-6 mb-4 rounded-3xl">
      <!-- Home -->
      <router-link to="/" class="bottom-tab" :class="isHome ? 'bottom-tab-active' : 'bottom-tab-idle'"
        @click="closeSheets">
        <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" /></svg>
        <span class="text-[10px] mt-0.5">Home</span>
      </router-link>

      <!-- Trading -->
      <button @click="toggleTrading" class="bottom-tab"
        :class="isTradingActive ? 'bottom-tab-active' : 'bottom-tab-idle'">
        <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" /></svg>
        <span class="text-[10px] mt-0.5">Trading</span>
      </button>

      <!-- More -->
      <button @click="toggleMore" class="bottom-tab"
        :class="isMoreActive ? 'bottom-tab-active' : 'bottom-tab-idle'">
        <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" /></svg>
        <span class="text-[10px] mt-0.5">More</span>
      </button>
    </div>
  </nav>

  <!-- Overlay -->
  <Transition name="fade">
    <div v-if="showTrading || showMore" class="fixed inset-0 bg-black/40 z-40 lg:hidden" @click="closeSheets"></div>
  </Transition>

  <!-- Trading Sheet -->
  <Transition name="sheet">
    <div v-if="showTrading" class="fixed bottom-0 left-0 right-0 z-40 lg:hidden">
      <div class="sheet-glass rounded-t-2xl pb-24 px-5 pt-4">
        <div class="w-10 h-1 bg-surface-500/30 rounded-full mx-auto mb-4"></div>
        <div class="grid grid-cols-3 gap-3">
          <router-link v-for="item in tradingItems" :key="item.to" :to="item.to"
            class="sheet-item" :class="isActive(item.to) ? 'sheet-item-active' : ''"
            @click="closeSheets">
            <component :is="item.icon" class="w-6 h-6 mb-1.5" />
            <span class="text-xs">{{ item.label }}</span>
          </router-link>
        </div>
      </div>
    </div>
  </Transition>

  <!-- More Sheet -->
  <Transition name="sheet">
    <div v-if="showMore" class="fixed bottom-0 left-0 right-0 z-40 lg:hidden">
      <div class="sheet-glass rounded-t-2xl pb-24 px-5 pt-4">
        <div class="w-10 h-1 bg-surface-500/30 rounded-full mx-auto mb-4"></div>
        <div class="grid grid-cols-3 gap-3 mb-5">
          <router-link v-for="item in moreItems" :key="item.to" :to="item.to"
            class="sheet-item" :class="isActive(item.to) ? 'sheet-item-active' : ''"
            @click="closeSheets">
            <component :is="item.icon" class="w-6 h-6 mb-1.5" />
            <span class="text-xs">{{ item.label }}</span>
          </router-link>
        </div>
        <div class="border-t border-white/[0.06] pt-4 flex gap-3">
          <button @click="toggleTheme" class="sheet-action-btn flex-1">
            <component :is="isDark ? SunIcon : MoonIcon" class="w-5 h-5" />
            {{ isDark ? 'Light Mode' : 'Dark Mode' }}
          </button>
          <button @click="handleLogout" class="flex-1 flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-red-500/10 text-red-400 text-sm active:bg-red-500/20 transition-colors">
            <LogoutIcon class="w-5 h-5" />
            Logout
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, h, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { logout } from '../api'

const router = useRouter()
const route = useRoute()

const showTrading = ref(false)
const showMore = ref(false)
const isDark = ref(document.documentElement.classList.contains('dark'))

const tradingPaths = ['/strategies', '/backtest', '/optimization', '/monte-carlo', '/live', '/import']
const morePaths = ['/tools', '/llm', '/brokers', '/issues', '/settings']

const isHome = computed(() => route.path === '/')
const isTradingActive = computed(() => tradingPaths.some(p => route.path.startsWith(p)) || showTrading.value)
const isMoreActive = computed(() => morePaths.some(p => route.path.startsWith(p)) || showMore.value)

function isActive(to) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

function toggleTrading() {
  showMore.value = false
  showTrading.value = !showTrading.value
}

function toggleMore() {
  showTrading.value = false
  showMore.value = !showMore.value
}

function closeSheets() {
  showTrading.value = false
  showMore.value = false
}

function toggleTheme() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.classList.add('dark')
    localStorage.setItem('te-theme', 'dark')
  } else {
    document.documentElement.classList.remove('dark')
    localStorage.setItem('te-theme', 'light')
  }
  closeSheets()
}

function handleLogout() {
  closeSheets()
  logout()
  router.push('/login')
}

// Close sheets on route change
watch(() => route.path, () => closeSheets())

// Icon helper
const icon = (paths) => ({
  render: () => h('svg', {
    xmlns: 'http://www.w3.org/2000/svg', fill: 'none', viewBox: '0 0 24 24',
    'stroke-width': '1.5', stroke: 'currentColor'
  }, paths.map(d => h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', d })))
})

const StratIcon = icon(['M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5'])
const BacktestIcon = icon(['M3 4.5h14.25M3 9h9.75M3 13.5h9.75m4.5-4.5v12m0 0l-3.75-3.75M17.25 21L21 17.25'])
const OptimizeIcon = icon(['M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6z', 'M13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z'])
const MonteCarloIcon = icon(['M3 3v18h18', 'M7 16l4-8 4 5 4-10'])
const LiveIcon = icon(['M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z'])
const ImportIcon = icon(['M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5'])
const InstrIcon = icon(['M11.42 15.17l-5.1-5.1a2.1 2.1 0 112.97-2.97l5.1 5.1M18.36 8.04l-1.42 1.42m3.54-.71l-1.42 1.42M14.83 18.36l1.42-1.42m-.71 3.54l1.42-1.42'])
const LLMIcon = icon(['M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z'])
const BrokerIcon = icon(['M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418'])
const IssuesIcon = icon(['M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z'])
const SettingsIcon = icon(['M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.431.992a7.723 7.723 0 010 .255c-.007.38.138.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.28z', 'M15 12a3 3 0 11-6 0 3 3 0 016 0z'])
const LogoutIcon = icon(['M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9'])
const SunIcon = icon(['M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z'])
const MoonIcon = icon(['M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z'])

const tradingItems = [
  { to: '/strategies', label: 'Strategies', icon: StratIcon },
  { to: '/backtest', label: 'Backtest', icon: BacktestIcon },
  { to: '/optimization', label: 'Optimize', icon: OptimizeIcon },
  { to: '/monte-carlo', label: 'Monte Carlo', icon: MonteCarloIcon },
  { to: '/live', label: 'Live Trade', icon: LiveIcon },
  { to: '/import', label: 'Import Data', icon: ImportIcon },
]

const moreItems = [
  { to: '/tools', label: 'Tools', icon: InstrIcon },
  { to: '/llm', label: 'LLM Studio', icon: LLMIcon },
  { to: '/brokers', label: 'Brokers', icon: BrokerIcon },
  { to: '/issues', label: 'Issues', icon: IssuesIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]
</script>

<style scoped>
.bottom-nav-glass {
  background: var(--glass-bg);
  backdrop-filter: blur(24px) saturate(1.5);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
}
.sheet-glass {
  background: var(--glass-bg);
  backdrop-filter: blur(32px) saturate(1.6);
  -webkit-backdrop-filter: blur(32px) saturate(1.6);
  border-top: 1px solid var(--glass-border);
}
.bottom-tab {
  @apply flex flex-col items-center justify-center py-3 px-4 min-w-[72px] transition-all duration-200;
}
.bottom-tab-active {
  @apply text-brand-400;
}
.bottom-tab-idle {
  @apply text-surface-500;
}
.sheet-item {
  @apply flex flex-col items-center justify-center py-5 rounded-2xl text-surface-400 transition-all duration-200;
  background: var(--glass-inset-bg);
}
.sheet-item:active {
  transform: scale(0.96);
}
.sheet-item-active {
  @apply text-brand-400;
  background: rgba(0, 128, 255, 0.12);
}
.sheet-action-btn {
  @apply flex items-center justify-center gap-2 py-3.5 rounded-2xl text-surface-300 text-sm transition-all duration-200;
  background: var(--glass-inset-bg);
}
.sheet-action-btn:active {
  transform: scale(0.97);
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.sheet-enter-active { transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.sheet-leave-active { transition: transform 0.2s ease-in; }
.sheet-enter-from { transform: translateY(100%); }
.sheet-leave-to { transform: translateY(100%); }
</style>
