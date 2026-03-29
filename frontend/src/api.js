const BASE = ''

function getToken() {
  return localStorage.getItem('te_token') || ''
}

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: {
      'Authorization': getToken(),
      'Content-Type': 'application/json',
    },
  }
  if (body) opts.body = JSON.stringify(body)

  let res
  try {
    res = await fetch(`${BASE}${path}`, opts)
  } catch (e) {
    // Network error (server down, ECONNREFUSED, etc.)
    const msg = e.message.includes('fetch') || e.message.includes('network') || e.message.includes('Failed')
      ? 'Backend server is not reachable. Please check that the server is running.'
      : e.message
    console.error(`[API] ${method} ${path} failed:`, msg)
    throw new Error(msg)
  }

  if (res.status === 401) {
    localStorage.removeItem('te_token')
    window.location.hash = '#/login'
    throw new Error('Unauthorized')
  }

  const text = await res.text()
  let data
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(text || `Server error (${res.status})`)
  }
  if (!res.ok) throw new Error(data.error || data.message || 'Request failed')
  return data
}

export const api = {
  // Auth
  login: (username, password) => request('POST', '/auth', { username, password }),
  register: (username, password, name) => request('POST', '/auth/register', { username, password, name }),
  getMe: () => request('GET', '/auth/me'),

  // System
  getGeneralInfo: () => request('POST', '/system/general-info'),

  // Brokers
  getBrokers: () => request('GET', '/broker/list'),
  getBrokersGrouped: () => request('GET', '/broker/grouped'),
  getConnectedBrokers: () => request('GET', '/broker/connected'),
  getBacktestingBrokers: () => request('GET', '/broker/backtesting'),
  getLiveBrokers: () => request('GET', '/broker/live-trading'),
  getBrokerInfo: (id) => request('GET', `/broker/info/${id}`),
  getAssetClasses: () => request('GET', '/broker/asset-classes'),
  getCostModel: (brokerId) => request('GET', `/broker/cost-model/${brokerId}`),
  updateCostModel: (data) => request('POST', '/broker/cost-model/update', data),
  getExchangeTypes: () => request('GET', '/broker/exchange-types'),

  // Market Data
  getSession: () => request('GET', '/market-data/session'),
  getMarketHours: (symbol) => request('GET', `/market-data/market-hours/${symbol}`),
  getInstrument: (symbol) => request('GET', `/market-data/instrument/${symbol}`),
  getInstruments: (assetClass) => {
    const q = assetClass ? `?asset_class=${assetClass}` : ''
    return request('GET', `/market-data/instruments${q}`)
  },
  getPipValue: (symbol, lotSize = 1) =>
    request('GET', `/market-data/pip-value/${symbol}?lot_size=${lotSize}`),
  calculate: (data) => request('POST', '/market-data/calculate', data),

  // Settings
  getBrokerSettings: () => request('GET', '/settings/brokers'),
  saveBrokerSettings: (data) => request('POST', '/settings/brokers', data),
  deleteBrokerSettings: (id) => request('DELETE', `/settings/brokers/${id}`),
  getLLMSettings: () => request('GET', '/settings/llm'),
  saveLLMSettings: (data) => request('POST', '/settings/llm', data),
  deleteLLMSettings: () => request('DELETE', '/settings/llm'),
  getAllSettings: () => request('GET', '/settings/all'),
  testBrokerConnection: (data) => request('POST', '/settings/test-broker', data),
  testLLMConnection: (data) => request('POST', '/settings/test-llm', data),
  getBacktestSettings: (brokerId) => request('GET', `/settings/backtest/${brokerId}`),
  saveBacktestSettings: (data) => request('POST', '/settings/backtest', data),

  // API Key Import/Export
  downloadApiKeys: (password) => request('POST', '/download/download-api-keys', { password }),
  importApiKeys: (content) => request('POST', '/download/import-api-keys', { content }),

  // LLM
  llmStatus: () => request('GET', '/llm/status'),
  generateStrategy: (data) => request('POST', '/llm/generate', data),
  refineStrategy: (data) => request('POST', '/llm/refine', data),
  validateStrategy: (code) => request('POST', '/llm/validate', { code }),
  configureLLM: (data) => request('POST', '/llm/configure', data),

  // Strategies
  getStrategies: () => request('GET', '/strategy/all'),
  getStrategy: (name) => request('POST', '/strategy/get', { name }),
  makeStrategy: (name) => request('POST', '/strategy/make', { name }),
  saveStrategy: (name, content) => request('POST', '/strategy/save', { name, content }),
  deleteStrategy: (name) => request('POST', '/strategy/delete', { name }),
  aiGenerateStrategy: (data) => request('POST', '/strategy/ai/generate', data),
  aiRefineStrategy: (data) => request('POST', '/strategy/ai/refine', data),

  // Backtest
  runBacktest: (data) => request('POST', '/backtest', data),
  getBacktestSessions: (params) => request('POST', '/backtest/sessions', params || {}),
  getBacktestSession: (id) => request('POST', `/backtest/sessions/${id}`),
  cancelBacktest: (id) => request('POST', '/backtest/cancel', { id }),
  getExposureTable: (data) => request('POST', '/backtest/exposure-table', data),
  removeBacktestSession: (id) => request('POST', `/backtest/sessions/${id}/remove`),
  updateBacktestNotes: (id, title, description, strategyCodes) =>
    request('POST', `/backtest/sessions/${id}/notes`, { title, description, strategy_codes: strategyCodes }),
  updateBacktestState: (id, state) => request('POST', '/backtest/update-state', { id, state }),
  purgeBacktestSessions: (daysOld) => request('POST', '/backtest/purge-sessions', { days_old: daysOld }),
  getBacktestChartData: (id) => request('POST', `/backtest/sessions/${id}/chart-data`),
  getBacktestStrategyCode: (id) => request('POST', `/backtest/sessions/${id}/strategy-code`),
  getBacktestSessionLogs: (id) => request('POST', `/backtest/sessions/${id}/logs`),
  getBacktestLogs: (sessionId) => {
    const token = getToken()
    return request('GET', `/backtest/logs/${sessionId}?token=${token}`)
  },
  getBacktestLogDownloadUrl: (sessionId) => {
    const token = getToken()
    return `/backtest/download-log/${sessionId}?token=${token}`
  },

  // Config
  getConfig: (currentConfig) => request('POST', '/config/get', { current_config: currentConfig }),
  updateConfig: (config) => request('POST', '/config/update', { current_config: config }),

  // Exchange
  getExchangeSymbols: (exchange) => request('POST', '/exchange/supported-symbols', { exchange }),
  getExchangeApiKeys: () => request('GET', '/exchange/api-keys'),

  // Import Candles
  importCandles: (data) => request('POST', '/candles/import', data),
  cancelImport: (id) => request('POST', '/candles/cancel-import', { id }),
  getCandles: (data) => request('POST', '/candles/get', data),
  getExistingCandles: (data) => request('POST', '/candles/existing', data),
  deleteCandles: (exchange, symbol) => request('POST', '/candles/delete', { exchange, symbol }),
  deleteAllCandles: () => request('POST', '/candles/delete-all'),

  // Live Trading
  startLive: (data) => request('POST', '/live', data),
  cancelLive: (id) => request('POST', '/live/cancel', { id }),
  getLiveLogs: (id, type, startTime) => request('POST', '/live/logs', { id, type, start_time: startTime || 0 }),
  getLiveOrders: (id, sessionId) => request('POST', '/live/orders', { id, session_id: sessionId }),
  getLivePositions: (sessionId) => request('POST', '/live/positions', { session_id: sessionId }),
  getLiveState: (sessionId) => request('GET', `/live/state/${sessionId}`),
  getLiveReport: (sessionId) => request('GET', `/live/report/${sessionId}`),
  getLiveSessions: (params) => request('POST', '/live/sessions', params || {}),
  getLiveSession: (id) => request('POST', `/live/sessions/${id}`),
  removeLiveSession: (id) => request('POST', `/live/sessions/${id}/remove`),
  updateLiveNotes: (id, title, description, strategyCodes) =>
    request('POST', `/live/sessions/${id}/notes`, { title, description, strategy_codes: strategyCodes }),
  updateLiveState: (id, state) => request('POST', '/live/update-state', { id, state }),
  getEquityCurve: (sessionId) => request('GET', `/live/equity-curve?session_id=${sessionId}`),

  // Live History (cross-session)
  getOrdersHistory: (params) => request('POST', '/orders/live-history', params || {}),
  getTradesHistory: (params) => request('POST', '/closed-trades/live-history', params || {}),
  purgeLiveSessions: (daysOld) => request('POST', '/live/purge-sessions', { days_old: daysOld }),

  // Optimization
  runOptimization: (data) => request('POST', '/optimization', data),
  rerunOptimization: (data) => request('POST', '/optimization/rerun', data),
  cancelOptimization: (id) => request('POST', '/optimization/cancel', { id }),
  terminateOptimization: (id) => request('POST', '/optimization/terminate', { id }),
  resumeOptimization: (data) => request('POST', '/optimization/resume', data),
  getOptimizationSessions: (params) => request('POST', '/optimization/sessions', params || {}),
  getOptimizationSession: (id) => request('POST', `/optimization/sessions/${id}`),
  removeOptimizationSession: (id) => request('POST', `/optimization/sessions/${id}/remove`),
  updateOptimizationNotes: (id, title, description, strategyCodes) =>
    request('POST', `/optimization/sessions/${id}/notes`, { id, title, description, strategy_codes: strategyCodes }),
  getOptimizationNotes: (id) => request('POST', `/optimization/sessions/${id}/get-notes`),
  getOptimizationStrategyCodes: (id) => request('POST', `/optimization/sessions/${id}/strategy-codes`),
  getOptimizationLogs: (id) => request('POST', `/optimization/sessions/${id}/logs`),
  purgeOptimizationSessions: (daysOld) => request('POST', '/optimization/purge-sessions', { days_old: daysOld }),
  getRunningOptimizationSession: () => request('GET', '/optimization/running-session'),

  // Monte Carlo
  runMonteCarlo: (data) => request('POST', '/monte-carlo', data),
  cancelMonteCarlo: (id) => request('POST', '/monte-carlo/cancel', { id }),
  terminateMonteCarlo: (id) => request('POST', '/monte-carlo/terminate', { id }),
  resumeMonteCarlo: (data) => request('POST', '/monte-carlo/resume', data),
  getMonteCarloSessions: (params) => request('POST', '/monte-carlo/sessions', params || {}),
  getMonteCarloSession: (id) => request('POST', `/monte-carlo/sessions/${id}`),
  getMonteCarloEquityCurves: (id) => request('POST', `/monte-carlo/sessions/${id}/equity-curves`),
  removeMonteCarloSession: (id) => request('POST', `/monte-carlo/sessions/${id}/remove`),
  updateMonteCarloNotes: (id, title, description, strategyCodes) =>
    request('POST', `/monte-carlo/sessions/${id}/notes`, { id, title, description, strategy_codes: strategyCodes }),
  getMonteCarloStrategyCode: (id) => request('POST', `/monte-carlo/sessions/${id}/strategy-code`),
  getMonteCarloLogs: (id) => request('POST', `/monte-carlo/sessions/${id}/logs`),
  updateMonteCarloState: (id, state) => request('POST', '/monte-carlo/update-state', { id, state }),
  purgeMonteCarloSessions: (daysOld) => request('POST', '/monte-carlo/purge-sessions', { days_old: daysOld }),
  getRunningMonteCarloSession: () => request('GET', '/monte-carlo/running-session'),

  // Notifications
  getNotificationKeys: () => request('GET', '/notification/api-keys'),
  storeNotificationKey: (data) => request('POST', '/notification/api-keys/store', data),
  deleteNotificationKey: (id) => request('POST', '/notification/api-keys/delete', { id }),
  testNotification: (data) => request('POST', '/system/test-notification', data),

  // Maintenance
  getStorageInfo: () => request('GET', '/system/storage-info'),
  getDbStorage: () => request('GET', '/system/db-storage'),
  flushData: (data) => request('POST', '/system/flush-data', data),
  clearCache: () => request('POST', '/system/clear-cache'),
  flushRedis: () => request('POST', '/system/flush-redis'),
  clearLogs: () => request('POST', '/system/clear-logs'),
  clearCandleCache: () => request('POST', '/candles/clear-cache'),

  // Playground
  getPlaygroundScenarios: () => request('GET', '/playground/scenarios'),
  getStrategyHyperparams: (name) => request('POST', '/playground/strategy-hyperparams', { name }),
  previewScenario: (data) => request('POST', '/playground/preview-scenario', data),
  runPlayground: (data) => request('POST', '/playground/run', data),
  cancelPlayground: (id) => request('POST', '/playground/cancel', { id }),

  // Profile / Account
  updateProfile: (data) => request('POST', '/auth/update-profile', data),
  deleteMyData: (password) => request('POST', '/auth/delete-my-data', { password }),
  deleteAccount: (password, deleteData = true) => request('POST', '/auth/delete-account', { password, delete_data: deleteData }),

  // Admin / Users
  getUsers: () => request('GET', '/auth/users'),
  updateUser: (data) => request('POST', '/auth/users/update', data),
  updateUserQuota: (data) => request('POST', '/auth/users/quota', data),
  impersonate: (userId) => request('POST', '/auth/impersonate', { user_id: userId }),
  stopImpersonate: () => request('POST', '/auth/stop-impersonate'),
  adminCreateUser: (data) => request('POST', '/auth/users/create', data),
  adminDeleteUser: (userId, deleteData = true) => request('POST', '/auth/users/delete', { user_id: userId, delete_data: deleteData }),
  adminResetPassword: (userId, newPassword) => request('POST', '/auth/users/reset-password', { user_id: userId, new_password: newPassword }),

  // Quota Requests
  submitQuotaRequest: (data) => request('POST', '/auth/quota-request', data),
  getQuotaRequests: () => request('GET', '/auth/quota-requests'),
  reviewQuotaRequest: (data) => request('POST', '/auth/quota-requests/review', data),

  // Issues
  getIssues: (params) => request('POST', '/issues/list', params || {}),
  createIssue: (data) => request('POST', '/issues/create', data),
  updateIssue: (data) => request('POST', '/issues/update', data),
  deleteIssue: (id) => request('POST', '/issues/delete', { id }),
  clearIssues: (status) => request('POST', '/issues/clear', { status: status || null }),
  getActiveIssueCount: () => request('POST', '/issues/active-count', {}),
  getComments: (issue_id) => request('POST', '/issues/comments/list', { issue_id }),
  createComment: (data) => request('POST', '/issues/comments/create', data),
  deleteComment: (id) => request('POST', '/issues/comments/delete', { id }),
}

export function setToken(token) {
  localStorage.setItem('te_token', token)
}

export function setAuth(token, user) {
  localStorage.setItem('te_token', token)
  if (user) localStorage.setItem('te_user', JSON.stringify(user))
}

export function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('te_user') || 'null')
  } catch { return null }
}

export function isAuthenticated() {
  const token = localStorage.getItem('te_token')
  if (!token) return false
  // Require both token and user object (clears stale legacy sessions)
  if (!localStorage.getItem('te_user')) {
    localStorage.removeItem('te_token')
    return false
  }
  // Check JWT expiry client-side (avoids showing app shell before 401 kicks in)
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      logout()
      return false
    }
  } catch {
    // Not a valid JWT — clear stale token
    logout()
    return false
  }
  return true
}

export function isAdmin() {
  const user = getCurrentUser()
  return user?.role === 'admin'
}

export function isImpersonating() {
  const user = getCurrentUser()
  return !!user?.impersonating
}

export function getUserFeatures() {
  const user = getCurrentUser()
  if (!user) return []
  if (user.role === 'admin') return null // null = all features
  return user.allowed_features || ['dashboard', 'strategies', 'backtest', 'settings', 'issues']
}

export function hasFeature(feature) {
  const features = getUserFeatures()
  if (features === null) return true // admin
  return features.includes(feature)
}

export function logout() {
  localStorage.removeItem('te_token')
  localStorage.removeItem('te_user')
}

/**
 * Pick the default broker from a list. Prefers OANDA, then OANDA Demo, then first available.
 */
export function defaultBrokerId(brokerList) {
  if (!brokerList || brokerList.length === 0) return ''
  const preferred = ['OANDA', 'OANDA Demo']
  for (const id of preferred) {
    const found = brokerList.find(b => b.id === id)
    if (found) return found.id
  }
  return brokerList[0].id
}
