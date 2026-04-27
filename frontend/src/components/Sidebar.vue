<template>
  <aside class="fixed left-0 top-0 h-screen flex-col z-40 hidden lg:flex sidebar-glass transition-all duration-200"
    :class="collapsed ? 'w-16' : 'w-60'">
    <div class="border-b border-white/[0.06]" :class="collapsed ? 'p-3 flex justify-center' : 'p-5'">
      <div class="flex items-center gap-2">
        <img src="/favicon.svg" alt="QEngine" class="w-8 h-8 flex-shrink-0" />
        <div v-if="!collapsed">
          <div class="text-sm font-semibold text-surface-100 tracking-tight">QEngine</div>
          <div class="text-[10px] text-surface-500 font-medium">v2.0</div>
        </div>
      </div>
    </div>

    <nav class="flex-1 py-4 space-y-0.5 overflow-auto" :class="collapsed ? 'px-2' : 'px-3'">
      <div v-if="!collapsed" class="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-surface-600 font-semibold">Overview</div>
      <router-link v-for="item in overviewItems" :key="item.to" :to="item.to"
        class="nav-link group" :class="[isActive(item.to) ? 'nav-active' : 'nav-idle', collapsed ? 'justify-center px-0 py-2.5' : '']" :title="collapsed ? item.label : item.hint">
        <component :is="item.icon" class="w-4 h-4 flex-shrink-0" />
        <div v-if="!collapsed" class="min-w-0">
          <div class="text-sm leading-tight">{{ item.label }}</div>
          <div class="text-[10px] leading-tight mt-0.5 transition-colors" :class="isActive(item.to) ? 'text-brand-400/50' : 'text-surface-600 group-hover:text-surface-500'">{{ item.hint }}</div>
        </div>
      </router-link>

      <div v-if="!collapsed" class="px-3 pt-4 pb-1 text-[10px] uppercase tracking-wider text-surface-600 font-semibold">Trading</div>
      <div v-else class="border-t border-white/[0.06] my-2"></div>
      <router-link v-for="item in tradingItems" :key="item.to" :to="item.to"
        class="nav-link group" :class="[isActive(item.to) ? 'nav-active' : 'nav-idle', collapsed ? 'justify-center px-0 py-2.5' : '']" :title="collapsed ? item.label : item.hint">
        <div class="relative flex-shrink-0">
          <component :is="item.icon" class="w-4 h-4" :class="collapsed ? '' : 'mt-0.5'" />
          <span v-if="badgeCount(item.to) && collapsed"
            class="absolute -top-1.5 -right-1.5 w-[14px] h-[14px] flex items-center justify-center text-[9px] font-bold text-white bg-green-500 rounded-full animate-pulse">
            {{ badgeCount(item.to) }}
          </span>
        </div>
        <div v-if="!collapsed" class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-sm leading-tight">{{ item.label }}</span>
            <span v-if="badgeCount(item.to)"
              class="w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0"></span>
          </div>
          <div class="text-[10px] leading-tight mt-0.5 transition-colors" :class="isActive(item.to) ? 'text-brand-400/50' : 'text-surface-600 group-hover:text-surface-500'">{{ item.hint }}</div>
        </div>
      </router-link>

      <div v-if="!collapsed" class="px-3 pt-4 pb-1 text-[10px] uppercase tracking-wider text-surface-600 font-semibold">Tools</div>
      <div v-else class="border-t border-white/[0.06] my-2"></div>
      <router-link v-for="item in toolItems" :key="item.to" :to="item.to"
        class="nav-link group" :class="[isActive(item.to) ? 'nav-active' : 'nav-idle', collapsed ? 'justify-center px-0 py-2.5' : '']" :title="collapsed ? item.label : item.hint">
        <div class="relative flex-shrink-0">
          <component :is="item.icon" class="w-4 h-4" :class="collapsed ? '' : 'mt-0.5'" />
          <span v-if="item.to === '/issues' && (activeIssueCount + errorReportCount) > 0 && collapsed"
            class="absolute -top-1.5 -right-1.5 min-w-[14px] h-[14px] flex items-center justify-center text-[9px] font-bold text-white rounded-full px-0.5 leading-none"
            :class="errorReportCount > 0 ? 'bg-orange-500' : 'bg-red-500'">
            {{ (activeIssueCount + errorReportCount) > 99 ? '99+' : (activeIssueCount + errorReportCount) }}
          </span>
        </div>
        <div v-if="!collapsed" class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-sm leading-tight">{{ item.label }}</span>
            <span v-if="item.to === '/issues' && (activeIssueCount + errorReportCount) > 0"
              class="min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold text-white rounded-full px-1 leading-none"
              :class="errorReportCount > 0 ? 'bg-orange-500' : 'bg-red-500'">
              {{ (activeIssueCount + errorReportCount) > 99 ? '99+' : (activeIssueCount + errorReportCount) }}
            </span>
          </div>
          <div class="text-[10px] leading-tight mt-0.5 transition-colors" :class="isActive(item.to) ? 'text-brand-400/50' : 'text-surface-600 group-hover:text-surface-500'">{{ item.hint }}</div>
        </div>
      </router-link>
    </nav>

    <div class="border-t border-white/[0.06] space-y-1" :class="collapsed ? 'p-2' : 'p-4'">
      <!-- User profile -->
      <div v-if="currentUser" class="flex items-center gap-2 mb-2" :class="collapsed ? 'justify-center' : 'px-3 py-2'">
        <div class="w-7 h-7 rounded-full bg-primary-500/20 text-primary-400 flex items-center justify-center text-xs font-bold flex-shrink-0" :title="collapsed ? (currentUser.name || currentUser.username) : ''">
          {{ (currentUser.name || currentUser.username || '?').charAt(0).toUpperCase() }}
        </div>
        <div v-if="!collapsed" class="min-w-0 flex-1">
          <div class="text-sm font-medium text-surface-200 truncate">{{ currentUser.name || currentUser.username }}</div>
          <div v-if="currentUser.name" class="text-[10px] text-surface-500 truncate">@{{ currentUser.username }}</div>
        </div>
      </div>
      <button @click="toggleSidebar" class="flex items-center gap-2 w-full rounded-lg text-sm text-surface-400 hover:text-surface-200 hover:bg-surface-800 transition-colors"
        :class="collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2'" :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 transition-transform duration-200" :class="collapsed ? 'rotate-180' : ''">
          <path stroke-linecap="round" stroke-linejoin="round" d="M18.75 19.5l-7.5-7.5 7.5-7.5m-6 15L5.25 12l7.5-7.5" />
        </svg>
        <span v-if="!collapsed">Collapse</span>
      </button>
      <button @click="toggleTheme" class="flex items-center gap-2 w-full rounded-lg text-sm text-surface-400 hover:text-surface-200 hover:bg-surface-800 transition-colors"
        :class="collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2'" :title="collapsed ? (isDark ? 'Light Mode' : 'Dark Mode') : ''">
        <component :is="isDark ? SunIcon : MoonIcon" class="w-4 h-4" />
        <span v-if="!collapsed">{{ isDark ? 'Light Mode' : 'Dark Mode' }}</span>
      </button>
      <button @click="handleLogout" class="flex items-center gap-2 w-full rounded-lg text-sm text-surface-500 hover:text-red-400 hover:bg-surface-800 transition-colors"
        :class="collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2'" :title="collapsed ? 'Logout' : ''">
        <LogoutIcon class="w-4 h-4" />
        <span v-if="!collapsed">Logout</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { useRouter, useRoute } from 'vue-router'
import { logout, api, isAdmin, getCurrentUser, hasFeature } from '../api'
import { h, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSidebar } from '../useSidebar'
import { useProcessManager } from '../useProcessManager'

const router = useRouter()
const route = useRoute()
const { collapsed, toggle: toggleSidebar } = useSidebar()

const pm = useProcessManager()
const isDark = ref(document.documentElement.classList.contains('dark'))
const activeIssueCount = ref(0)
const errorReportCount = ref(0)
const liveSessionCount = ref(0)

// Running process badges per route
const runningByRoute = computed(() => {
  const map = {}
  for (const p of pm.running.value) {
    const route = p.routePath || ''
    map[route] = (map[route] || 0) + 1
  }
  return map
})

function badgeCount(routePath) {
  if (routePath === '/live') return liveSessionCount.value
  return runningByRoute.value[routePath] || 0
}

async function loadLiveSessionCount() {
  if (!getCurrentUser()) return
  try {
    const res = await api.getLiveSessions({ limit: 50 })
    const sessions = res.sessions || []
    liveSessionCount.value = sessions.filter(s => s.status === 'running' || s.status === 'starting').length
  } catch { /* ignore */ }
}
const currentUser = ref(getCurrentUser())

let issueCountInterval = null

async function loadActiveIssueCount() {
  if (!getCurrentUser()) return
  try {
    const res = await api.getActiveIssueCount()
    activeIssueCount.value = res.count || 0
  } catch (e) { /* ignore */ }
}

async function loadErrorReportCount() {
  if (!getCurrentUser()) return
  try {
    const res = await api.getReportCount()
    errorReportCount.value = res.count || 0
  } catch (e) { /* ignore */ }
}

onMounted(() => {
  loadActiveIssueCount()
  loadErrorReportCount()
  loadLiveSessionCount()
  issueCountInterval = setInterval(() => {
    loadActiveIssueCount()
    loadErrorReportCount()
    loadLiveSessionCount()
  }, 10000)
})

onBeforeUnmount(() => {
  if (issueCountInterval) clearInterval(issueCountInterval)
})

function toggleTheme() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.classList.add('dark')
    localStorage.setItem('te-theme', 'dark')
  } else {
    document.documentElement.classList.remove('dark')
    localStorage.setItem('te-theme', 'light')
  }
}

function handleLogout() {
  if (!confirm('Are you sure you want to logout?')) return
  logout()
  router.push('/login')
}

function isActive(to) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

const icon = (paths) => ({ render: () => h('svg', { xmlns: 'http://www.w3.org/2000/svg', fill: 'none', viewBox: '0 0 24 24', 'stroke-width': '1.5', stroke: 'currentColor', class: 'w-4 h-4' }, paths.map(d => h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', d }))) })

const DashIcon = icon(['M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z'])
const BrokerIcon = icon(['M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418'])
const InstrIcon = icon(['M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z'])
const StratIcon = icon(['M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5'])
const BacktestIcon = icon(['M3 4.5h14.25M3 9h9.75M3 13.5h9.75m4.5-4.5v12m0 0l-3.75-3.75M17.25 21L21 17.25'])
const OptimizeIcon = icon(['M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6z', 'M13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z'])
const MonteCarloIcon = icon(['M3 3v18h18', 'M7 16l4-8 4 5 4-10'])
const AutopilotIcon = icon(['M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.964m11.49-9.642l1.149-.964M7.501 19.795l.75-1.3m7.5-12.99l.75-1.3m-6.063 16.658l.26-1.477m2.605-14.772l.26-1.477m-2.604.39l.26 1.477m2.605 14.772l.26 1.477'])
const LiveIcon = icon(['M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z'])
const ImportIcon = icon(['M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5'])
const LLMIcon = icon(['M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z'])
const SettingsIcon = icon(['M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.431.992a7.723 7.723 0 010 .255c-.007.38.138.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.28z', 'M15 12a3 3 0 11-6 0 3 3 0 016 0z'])
const IssuesIcon = icon(['M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z'])
const ReportsIcon = icon(['M12 12.75c1.148 0 2.278.08 3.383.237 1.037.146 1.866.966 1.866 2.013 0 3.728-2.35 6.75-5.25 6.75S6.75 18.728 6.75 15c0-1.046.83-1.867 1.866-2.013A24.204 24.204 0 0112 12.75zm0 0c2.883 0 5.647.508 8.207 1.44a23.91 23.91 0 01-1.152 6.06M12 12.75c-2.883 0-5.647.508-8.208 1.44.125 2.104.52 4.136 1.153 6.06M12 12.75a2.25 2.25 0 002.248-2.354M12 12.75a2.25 2.25 0 01-2.248-2.354M12 8.25c.995 0 1.971-.08 2.922-.236.403-.066.74-.358.795-.762a3.778 3.778 0 00-.399-2.25M12 8.25c-.995 0-1.97-.08-2.922-.236-.402-.066-.74-.358-.795-.762a3.734 3.734 0 01.4-2.253M12 8.25a2.25 2.25 0 00-2.248 2.146M12 8.25a2.25 2.25 0 012.248 2.146M8.683 5a6.032 6.032 0 01-1.155-1.002c.07-.63.27-1.222.574-1.747m.581 2.749A3.75 3.75 0 0112 3.75c1.274 0 2.394.636 3.069 1.608M15.317 5a6.032 6.032 0 001.155-1.002 4.484 4.484 0 00-.575-1.748'])
const AdminIcon = icon(['M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z'])
const HelpIcon = icon(['M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z'])
const LogoutIcon = icon(['M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9'])
const SunIcon = icon(['M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z'])
const MoonIcon = icon(['M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z'])

// Feature-to-route mapping
const featureRoute = { dashboard: '/', strategies: '/strategies', backtest: '/backtest', optimization: '/optimization', monte_carlo: '/monte-carlo', live: '/live', import_data: '/import', tools: '/tools', llm_studio: '/llm', issues: '/issues', settings: '/settings' }

const allOverviewItems = [
  { to: '/', label: 'Dashboard', icon: DashIcon, hint: 'Activity & system status', feature: 'dashboard' },
]

const allTradingItems = [
  { to: '/strategies', label: 'Strategies', icon: StratIcon, hint: 'Create & test strategies', feature: 'strategies' },
  { to: '/backtest', label: 'Backtest', icon: BacktestIcon, hint: 'Test on historical data', feature: 'backtest' },
  { to: '/optimization', label: 'Optimization', icon: OptimizeIcon, hint: 'Tune hyperparameters', feature: 'optimization' },
  { to: '/monte-carlo', label: 'Monte Carlo', icon: MonteCarloIcon, hint: 'Stress-test robustness', feature: 'monte_carlo' },
  { to: '/autopilot', label: 'Pipelines', icon: AutopilotIcon, hint: 'Browse registered pipelines', feature: 'backtest' },
  { to: '/live', label: 'Live / Paper', icon: LiveIcon, hint: 'Trade live or simulate', feature: 'live' },
  { to: '/import', label: 'Import Data', icon: ImportIcon, hint: 'Download OHLCV candles', feature: 'import_data' },
]

const overviewItems = computed(() => allOverviewItems.filter(i => hasFeature(i.feature)))
const tradingItems = computed(() => allTradingItems.filter(i => hasFeature(i.feature)))

const toolItems = computed(() => {
  const items = []
  if (hasFeature('tools')) items.push({ to: '/tools', label: 'Tools', icon: InstrIcon, hint: 'Instruments & calculators' })
  if (hasFeature('llm_studio')) items.push({ to: '/llm', label: 'LLM Studio', icon: LLMIcon, hint: 'AI strategy generation' })
  if (hasFeature('issues')) items.push({ to: '/issues', label: 'Issues', icon: IssuesIcon, hint: 'Issues & error reports' })
  items.push({ to: '/help', label: 'Help', icon: HelpIcon, hint: 'Testing guide & FAQ' })
  if (isAdmin()) {
    items.push({ to: '/admin', label: 'Admin', icon: AdminIcon, hint: 'User management' })
  }
  if (hasFeature('settings')) items.push({ to: '/settings', label: 'Settings', icon: SettingsIcon, hint: 'API keys & config' })
  return items
})
</script>

<style scoped>
.sidebar-glass {
  background: var(--glass-bg);
  backdrop-filter: blur(24px) saturate(1.5);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  border-right: 1px solid var(--glass-border);
}
.nav-link {
  @apply flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-150;
}
.nav-active {
  @apply text-brand-400;
  background: rgba(0, 128, 255, 0.1);
}
.nav-idle {
  @apply text-surface-400 hover:text-surface-200;
}
.nav-idle:hover {
  background: var(--glass-inset-bg);
}
</style>
