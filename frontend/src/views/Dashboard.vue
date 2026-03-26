<template>
  <div>
    <div class="text-center mb-8">
      <h1 class="text-2xl font-bold">Dashboard</h1>
      <p class="text-sm text-surface-500 mt-1">Overview of running tasks, recent activity, and system health</p>
    </div>

    <div v-if="loading" class="text-surface-500 text-sm">Loading...</div>

    <div v-else class="space-y-6">

      <!-- ═══ Activity Overview ═══ -->
      <div v-if="hasActivity" class="card border-brand-500/20">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold text-surface-300">Activity Overview</h2>
          <button @click="refreshActivity" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
        </div>

        <!-- Running Tasks -->
        <div v-if="runningTasks.length" class="mb-4">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-2">Running Now</div>
          <div class="space-y-2">
            <div v-for="task in runningTasks" :key="task.id"
              class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-surface-800 rounded-lg hover:bg-surface-750 transition-colors cursor-pointer"
              @click="navigateTo(task.route)">
              <div class="flex items-center gap-3 min-w-0">
                <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse shrink-0"></span>
                <span class="badge text-[10px] shrink-0" :class="taskBadgeClass(task.type)">{{ task.type }}</span>
                <span class="text-sm text-surface-200 truncate">{{ task.label }}</span>
                <span class="text-xs text-surface-500 truncate hidden sm:inline">{{ task.detail }}</span>
              </div>
              <div class="flex items-center gap-3 shrink-0">
                <div v-if="task.progress != null" class="flex items-center gap-2">
                  <div class="w-24 h-1.5 bg-surface-700 rounded-full overflow-hidden">
                    <div class="h-full bg-brand-500 rounded-full transition-all" :style="{ width: task.progress + '%' }"></div>
                  </div>
                  <span class="text-xs text-surface-400 font-mono w-10 text-right">{{ task.progress }}%</span>
                </div>
                <svg class="w-4 h-4 text-surface-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
              </div>
            </div>
          </div>
        </div>

        <!-- Recent Activity Summary -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="p-3 bg-surface-800 rounded-lg cursor-pointer hover:bg-surface-750 transition-colors" @click="navigateTo('#/backtest')">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-1.5 h-1.5 rounded-full" :class="activityCounts.backtest.running ? 'bg-green-400 animate-pulse' : 'bg-surface-600'"></span>
              <span class="text-[10px] text-surface-500 uppercase tracking-wider">Backtests</span>
            </div>
            <div class="text-lg font-bold text-surface-100">{{ activityCounts.backtest.total }}</div>
            <div class="text-[10px] text-surface-500">
              <span v-if="activityCounts.backtest.running" class="text-green-400">{{ activityCounts.backtest.running }} running</span>
              <span v-else>{{ activityCounts.backtest.finished }} completed</span>
            </div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg cursor-pointer hover:bg-surface-750 transition-colors" @click="navigateTo('#/optimization')">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-1.5 h-1.5 rounded-full" :class="activityCounts.optimization.running ? 'bg-green-400 animate-pulse' : 'bg-surface-600'"></span>
              <span class="text-[10px] text-surface-500 uppercase tracking-wider">Optimizations</span>
            </div>
            <div class="text-lg font-bold text-surface-100">{{ activityCounts.optimization.total }}</div>
            <div class="text-[10px] text-surface-500">
              <span v-if="activityCounts.optimization.running" class="text-green-400">{{ activityCounts.optimization.running }} running</span>
              <span v-else>{{ activityCounts.optimization.finished }} completed</span>
            </div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg cursor-pointer hover:bg-surface-750 transition-colors" @click="navigateTo('#/monte-carlo')">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-1.5 h-1.5 rounded-full" :class="activityCounts.montecarlo.running ? 'bg-green-400 animate-pulse' : 'bg-surface-600'"></span>
              <span class="text-[10px] text-surface-500 uppercase tracking-wider">Monte Carlo</span>
            </div>
            <div class="text-lg font-bold text-surface-100">{{ activityCounts.montecarlo.total }}</div>
            <div class="text-[10px] text-surface-500">
              <span v-if="activityCounts.montecarlo.running" class="text-green-400">{{ activityCounts.montecarlo.running }} running</span>
              <span v-else>{{ activityCounts.montecarlo.finished }} completed</span>
            </div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg cursor-pointer hover:bg-surface-750 transition-colors" @click="navigateTo('#/live')">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-1.5 h-1.5 rounded-full" :class="activityCounts.live.running ? 'bg-green-400 animate-pulse' : 'bg-surface-600'"></span>
              <span class="text-[10px] text-surface-500 uppercase tracking-wider">Live Trading</span>
            </div>
            <div class="text-lg font-bold text-surface-100">{{ activityCounts.live.total }}</div>
            <div class="text-[10px] text-surface-500">
              <span v-if="activityCounts.live.running" class="text-green-400">{{ activityCounts.live.running }} running</span>
              <span v-else>{{ activityCounts.live.stopped }} stopped</span>
            </div>
          </div>
        </div>

        <!-- Recent Sessions List -->
        <div v-if="recentSessions.length" class="mt-4">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-2">Recent Sessions</div>
          <div class="space-y-1">
            <div v-for="s in recentSessions" :key="s.id"
              class="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-surface-800/60 cursor-pointer transition-colors"
              @click="navigateTo(s.route)">
              <div class="flex items-center gap-3">
                <span class="w-1.5 h-1.5 rounded-full" :class="s.status === 'running' ? 'bg-green-400 animate-pulse' : s.status === 'finished' ? 'bg-surface-500' : 'bg-red-400'"></span>
                <span class="badge text-[10px]" :class="taskBadgeClass(s.type)">{{ s.type }}</span>
                <span class="text-sm text-surface-200">{{ s.label }}</span>
              </div>
              <div class="flex items-center gap-3 text-xs text-surface-500">
                <span :class="s.status === 'running' ? 'text-green-400' : s.status === 'finished' ? 'text-surface-400' : 'text-red-400'">{{ s.status }}</span>
                <span>{{ formatDate(s.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- No Activity -->
      <div v-else class="card text-center py-8">
        <p class="text-surface-500 text-sm mb-3">No recent activity.</p>
        <div class="flex items-center justify-center gap-3">
          <a href="#/backtest" class="btn-sm bg-surface-800 text-brand-400 hover:text-brand-300">Run Backtest</a>
          <a href="#/live" class="btn-sm bg-surface-800 text-green-400 hover:text-green-300">Start Trading</a>
        </div>
      </div>

      <!-- Market Status -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="card">
          <div class="text-xs text-surface-500 mb-1">Current Session</div>
          <div class="text-lg font-semibold capitalize" :class="sessionColor">{{ session.session || '-' }}</div>
          <div class="text-xs text-surface-500 mt-2">{{ new Date().toLocaleString() }}</div>
        </div>

        <div class="card">
          <div class="text-xs text-surface-500 mb-1">EUR-USD Status</div>
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full" :class="eurusd.is_open ? 'bg-green-400' : 'bg-red-400'"></span>
            <span class="text-lg font-semibold">{{ eurusd.is_open ? 'Open' : 'Closed' }}</span>
          </div>
          <div v-if="eurusd.minutes_to_close" class="text-xs text-surface-500 mt-2">
            Closes in {{ formatMinutes(eurusd.minutes_to_close) }}
          </div>
        </div>

        <div class="card">
          <div class="text-xs text-surface-500 mb-1">Connected Brokers</div>
          <div class="text-lg font-semibold">{{ connectedBrokers.length }}</div>
          <div class="text-xs text-surface-500 mt-2">
            <a href="#/brokers" class="text-brand-400 hover:underline">Manage</a>
          </div>
        </div>
      </div>

      <!-- Connected Brokers -->
      <div class="card" v-if="connectedBrokers.length > 0">
        <h2 class="text-sm font-semibold mb-3 text-surface-300">Connected Brokers</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <div v-for="b in connectedBrokers" :key="b.id"
            class="p-3 bg-surface-800 rounded-lg">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full bg-green-400"></span>
              <span class="text-sm font-medium text-surface-200">{{ b.name }}</span>
              <span v-if="b.is_demo" class="text-[10px] px-1 py-0.5 rounded bg-amber-500/20 text-amber-400">Demo</span>
            </div>
            <div class="text-xs text-surface-500 space-y-0.5">
              <div v-if="b.account_id">Account: <span class="text-surface-300 font-mono">{{ b.account_id }}</span></div>
              <div><span class="capitalize">{{ b.type }}</span> &middot; {{ b.default_leverage }}x &middot; {{ b.settlement_currency }}</div>
              <div class="flex gap-1 mt-1">
                <span v-for="ac in b.asset_classes" :key="ac"
                  class="px-1 py-0.5 text-[10px] rounded bg-surface-700 text-surface-400 capitalize">{{ ac }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="card">
        <div class="text-sm text-surface-500 text-center py-4">
          No brokers connected. <a href="#/brokers" class="text-brand-400 hover:underline">Connect a broker</a>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- LLM Status -->
        <div class="card">
          <h2 class="text-sm font-semibold mb-3 text-surface-300">LLM Strategy Engine</h2>
          <div class="flex items-center gap-3">
            <span class="w-2 h-2 rounded-full" :class="llm.configured ? 'bg-green-400' : 'bg-surface-500'"></span>
            <span class="text-sm text-surface-200">
              {{ llm.configured ? `${llm.provider} (${llm.model})` : 'Not configured' }}
            </span>
            <a v-if="!llm.configured" href="#/settings" class="text-xs text-brand-400 hover:underline">
              Configure
            </a>
          </div>
        </div>

        <!-- Quick Pip Values -->
        <div class="card">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-semibold text-surface-300">Pip Values (1 std lot)</h2>
            <a href="#/tools" class="text-xs text-brand-400 hover:underline">Calculator</a>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div v-for="pv in pipValues" :key="pv.symbol"
              class="flex justify-between py-1.5 px-2 bg-surface-800/50 rounded text-xs">
              <span class="text-surface-400">{{ pv.symbol }}</span>
              <span class="text-surface-200 font-mono">${{ pv.pip_value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import { useWebSocket } from '../useWebSocket'

const loading = ref(true)
const session = ref({})
const eurusd = ref({})
const connectedBrokers = ref([])
const pipValues = ref([])
const llm = ref({})

// Activity state
const backtestSessions = ref([])
const optimizationSessions = ref([])
const montecarloSessions = ref([])
const liveSessions = ref([])
let activityTimer = null

const sessionColor = computed(() => {
  const s = session.value.session
  if (s === 'london') return 'text-blue-400'
  if (s === 'new_york') return 'text-green-400'
  if (s === 'tokyo') return 'text-yellow-400'
  if (s === 'overlap') return 'text-purple-400'
  return 'text-surface-500'
})

// Activity computed
function countByStatus(sessions, runningStatuses = ['running'], finishedStatuses = ['finished']) {
  let running = 0, finished = 0
  for (const s of sessions) {
    if (runningStatuses.includes(s.status)) running++
    else if (finishedStatuses.includes(s.status)) finished++
  }
  return { total: sessions.length, running, finished, stopped: sessions.length - running - finished }
}

const activityCounts = computed(() => ({
  backtest: countByStatus(backtestSessions.value),
  optimization: countByStatus(optimizationSessions.value),
  montecarlo: countByStatus(montecarloSessions.value),
  live: countByStatus(liveSessions.value),
}))

const hasActivity = computed(() => {
  return backtestSessions.value.length > 0 || optimizationSessions.value.length > 0 ||
    montecarloSessions.value.length > 0 || liveSessions.value.length > 0
})

const runningTasks = computed(() => {
  const tasks = []
  for (const s of backtestSessions.value.filter(s => s.status === 'running')) {
    const routes = parseRoutes(s)
    tasks.push({ id: s.id, type: 'Backtest', label: routes, detail: s.exchange || '', route: '#/backtest', progress: null })
  }
  for (const s of optimizationSessions.value.filter(s => s.status === 'running')) {
    const routes = parseRoutes(s)
    tasks.push({ id: s.id, type: 'Optimization', label: routes, detail: s.exchange || '', route: '#/optimization', progress: null })
  }
  for (const s of montecarloSessions.value.filter(s => s.status === 'running')) {
    const routes = parseRoutes(s)
    tasks.push({ id: s.id, type: 'Monte Carlo', label: routes, detail: s.exchange || '', route: '#/monte-carlo', progress: null })
  }
  for (const s of liveSessions.value.filter(s => s.status === 'running')) {
    const routes = parseRoutes(s)
    tasks.push({ id: s.id, type: 'Live', label: routes, detail: s.exchange || '', route: '#/live', progress: null })
  }
  return tasks
})

const recentSessions = computed(() => {
  const all = []
  for (const s of backtestSessions.value.slice(0, 5)) {
    all.push({ id: s.id, type: 'Backtest', label: parseRoutes(s), status: s.status, created_at: s.created_at, route: '#/backtest' })
  }
  for (const s of optimizationSessions.value.slice(0, 3)) {
    all.push({ id: s.id, type: 'Optimization', label: parseRoutes(s), status: s.status, created_at: s.created_at, route: '#/optimization' })
  }
  for (const s of montecarloSessions.value.slice(0, 3)) {
    all.push({ id: s.id, type: 'Monte Carlo', label: parseRoutes(s), status: s.status, created_at: s.created_at, route: '#/monte-carlo' })
  }
  for (const s of liveSessions.value.slice(0, 3)) {
    all.push({ id: s.id, type: 'Live', label: parseRoutes(s), status: s.status, created_at: s.created_at || s.started_at, route: '#/live' })
  }
  // Sort by date descending, take top 8
  all.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  return all.slice(0, 8)
})

function parseRoutes(session) {
  const state = session.state
  if (!state) return session.title || session.id?.slice(0, 8) || '-'
  let parsed = state
  if (typeof state === 'string') {
    try { parsed = JSON.parse(state) } catch { return session.title || '-' }
  }
  const routes = parsed?.form?.routes || parsed?.routes || []
  if (routes.length === 0) return session.title || '-'
  return routes.map(r => `${r.symbol || ''} ${r.strategy || ''}`).join(', ').trim() || '-'
}

function taskBadgeClass(type) {
  if (type === 'Backtest') return 'bg-blue-500/20 text-blue-400'
  if (type === 'Optimization') return 'bg-purple-500/20 text-purple-400'
  if (type === 'Monte Carlo') return 'bg-amber-500/20 text-amber-400'
  if (type === 'Live') return 'bg-green-500/20 text-green-400'
  return 'bg-surface-700 text-surface-400'
}

function navigateTo(route) {
  window.location.hash = route.replace('#', '')
}

function formatMinutes(m) {
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r > 0 ? `${h}h ${r}m` : `${h}h`
}

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return d.toLocaleDateString()
}

async function loadActivity() {
  try {
    const [bt, opt, mc, live] = await Promise.all([
      api.getBacktestSessions({ limit: 10 }).catch(() => ({ sessions: [] })),
      api.getOptimizationSessions({ limit: 5 }).catch(() => ({ sessions: [] })),
      api.getMonteCarloSessions({ limit: 5 }).catch(() => ({ sessions: [] })),
      api.getLiveSessions({ limit: 5 }).catch(() => ({ sessions: [] })),
    ])
    backtestSessions.value = bt.sessions || []
    optimizationSessions.value = opt.sessions || []
    montecarloSessions.value = mc.sessions || []
    liveSessions.value = live.sessions || []
  } catch { /* ignore */ }
}

async function refreshActivity() {
  await loadActivity()
}

// Auto-refresh activity if anything is running
function startActivityPolling() {
  stopActivityPolling()
  activityTimer = setInterval(loadActivity, 5000)
}
function stopActivityPolling() {
  if (activityTimer) { clearInterval(activityTimer); activityTimer = null }
}

// Listen for WS events to update running state
useWebSocket((msg) => {
  const { event } = msg
  if (event === 'backtest.metrics' || event === 'backtest.exception' || event === 'backtest.termination' ||
      event === 'optimize.alert' || event === 'optimize.exception' || event === 'optimize.termination' ||
      event === 'monte-carlo.alert' || event === 'monte-carlo.exception' || event === 'monte-carlo.termination' ||
      event === 'candles.alert' || event === 'candles.exception' || event === 'candles.termination') {
    setTimeout(loadActivity, 1500)
  }
})

onMounted(async () => {
  try {
    const [sessionRes, eurusdRes, connRes, llmRes] = await Promise.all([
      api.getSession(),
      api.getMarketHours('EUR-USD'),
      api.getConnectedBrokers(),
      api.llmStatus(),
    ])
    session.value = sessionRes.data
    eurusd.value = eurusdRes.data
    connectedBrokers.value = connRes.data
    llm.value = llmRes

    const pvSymbols = ['EUR-USD', 'GBP-USD', 'USD-JPY', 'XAU-USD']
    const pvResults = await Promise.all(pvSymbols.map(s => api.getPipValue(s)))
    pipValues.value = pvResults.map(r => r.data)
  } catch (e) {
    console.error('Dashboard load error:', e)
  } finally {
    loading.value = false
  }

  await loadActivity()
  // Poll if any running tasks
  if (runningTasks.value.length) startActivityPolling()
})

onUnmounted(() => {
  stopActivityPolling()
})
</script>
