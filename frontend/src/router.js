import { createRouter, createWebHashHistory } from 'vue-router'
import { isAuthenticated, isAdmin, hasFeature } from './api'

import Login from './views/Login.vue'
import Dashboard from './views/Dashboard.vue'
import Brokers from './views/Brokers.vue'
import Tools from './views/Tools.vue'
import Backtest from './views/Backtest.vue'
import Strategies from './views/Strategies.vue'
import LiveTrade from './views/LiveTrade.vue'
import ImportData from './views/ImportData.vue'
import LLMStudio from './views/LLMStudio.vue'
import Settings from './views/Settings.vue'
import Admin from './views/Admin.vue'
import Optimization from './views/Optimization.vue'
import MonteCarlo from './views/MonteCarlo.vue'
import Issues from './views/Issues.vue'
import Help from './views/Help.vue'

const routes = [
  { path: '/login', name: 'Login', component: Login, meta: { public: true } },
  { path: '/', name: 'Dashboard', component: Dashboard, meta: { feature: 'dashboard' } },
  { path: '/brokers', name: 'Brokers', component: Brokers, meta: { feature: 'brokers' } },
  { path: '/tools', name: 'Tools', component: Tools, meta: { feature: 'tools' } },
  { path: '/instruments', redirect: '/tools' },
  { path: '/strategies', name: 'Strategies', component: Strategies, meta: { feature: 'strategies' } },
  { path: '/backtest', name: 'Backtest', component: Backtest, meta: { feature: 'backtest' } },
  { path: '/optimization', name: 'Optimization', component: Optimization, meta: { feature: 'optimization' } },
  { path: '/monte-carlo', name: 'Monte Carlo', component: MonteCarlo, meta: { feature: 'monte_carlo' } },
  { path: '/live', name: 'Live Trade', component: LiveTrade, meta: { feature: 'live' } },
  { path: '/import', name: 'Import Data', component: ImportData, meta: { feature: 'import_data' } },
  { path: '/llm', name: 'LLM Studio', component: LLMStudio, meta: { feature: 'llm_studio' } },
  { path: '/settings', name: 'Settings', component: Settings, meta: { feature: 'settings' } },
  { path: '/issues', name: 'Issues', component: Issues, meta: { feature: 'issues' } },
  { path: '/admin', name: 'Admin', component: Admin, meta: { requiresAdmin: true } },
  { path: '/help', name: 'Help', component: Help },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!to.meta.public && !isAuthenticated()) {
    return { name: 'Login' }
  }
  if (to.meta.requiresAdmin && !isAdmin()) {
    return { name: 'Dashboard' }
  }
  if (to.meta.feature && !hasFeature(to.meta.feature)) {
    return { name: 'Dashboard' }
  }
})

export default router
