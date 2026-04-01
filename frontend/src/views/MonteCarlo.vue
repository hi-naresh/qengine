<template>
  <div>
    <!-- Header + Workspace Tabs -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Monte Carlo</h1>
        <p class="text-xs text-surface-500 mt-0.5">Simulate thousands of random trade sequences to stress-test strategy robustness</p>
      </div>
      <!-- Workspace tabs + History in the same bar -->
      <div class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg overflow-x-auto">
        <div v-for="wt in workspaceTabs" :key="wt.id"
          @click="pageTab = 'run'; !running && switchWorkspace(wt.id)"
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer group rounded-md transition-colors"
          :class="[
            pageTab === 'run' && wt.id === activeWorkspaceId ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300',
            running && wt.id !== activeWorkspaceId ? 'opacity-40 cursor-not-allowed' : ''
          ]">
          <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="wt.running ? 'bg-green-400 animate-pulse' : wt.hasResults ? 'bg-brand-400' : 'bg-surface-600'"></span>
          <span class="truncate max-w-[140px]">{{ wt.label }}</span>
          <button v-if="workspaceTabs.length > 1 && !running" @click.stop="closeWorkspace(wt.id)"
            class="text-surface-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">&times;</button>
        </div>
        <button @click="addWorkspace" :disabled="running"
          class="w-6 h-6 flex items-center justify-center text-surface-500 hover:text-brand-400 rounded text-sm transition-colors"
          :class="running ? 'opacity-40 cursor-not-allowed' : ''" title="New workspace">+</button>
        <div class="w-px h-5 bg-surface-600 mx-1"></div>
        <div @click="pageTab = 'history'; loadSessions()"
          class="px-3 py-1.5 text-xs cursor-pointer rounded-md transition-colors"
          :class="pageTab === 'history' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
          History
          <span v-if="sessions.length" class="ml-1 text-surface-600">({{ sessions.length }})</span>
        </div>
      </div>
    </div>
    <SectionGuide category="monte-carlo" title="What is Monte Carlo & why it matters" />

    <!-- ═══ RUN VIEW ═══ -->
    <div v-show="pageTab === 'run'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <!-- Left: Config Panel -->
      <div class="md:col-span-1 lg:col-span-1 space-y-4" v-show="!running || showConfig">
        <div class="card">
          <h2 class="text-sm font-semibold mb-1 text-surface-300">Configuration</h2>
          <p class="text-[11px] text-surface-500 mb-4">Backtest first, then run Monte Carlo to see how results hold under randomized trade ordering</p>

          <div class="space-y-3">
            <div>
              <label class="label">Exchange / Broker</label>
              <select v-model="form.exchange" class="select" @change="onExchangeChange">
                <option v-for="b in brokers" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>

            <div>
              <label class="label">Symbol</label>
              <select v-if="availableSymbols.length" v-model="form.symbol" class="select" @change="onSymbolChange">
                <option v-for="s in availableSymbols" :key="s" :value="s">{{ s }}</option>
              </select>
              <input v-else v-model="form.symbol" class="input" placeholder="EUR-USD" />
              <div v-if="dataRange" class="text-xs text-surface-500 mt-1">
                Data: {{ dataRange.start }} to {{ dataRange.end }}
              </div>
            </div>

            <div>
              <label class="label">Timeframe</label>
              <select v-model="form.timeframe" class="select">
                <option v-for="tf in timeframes" :key="tf.value" :value="tf.value">{{ tf.label }}</option>
              </select>
            </div>

            <div>
              <label class="label">Strategy</label>
              <div class="flex items-center gap-1">
                <select v-if="strategies.length" v-model="form.strategy" class="select flex-1">
                  <option v-for="s in strategies" :key="s.name" :value="s.name">{{ s.name }}</option>
                </select>
                <input v-else v-model="form.strategy" class="input flex-1" placeholder="ForexMA" />
                <router-link v-if="form.strategy" :to="'/strategies?edit=' + encodeURIComponent(form.strategy)"
                  class="w-8 h-8 rounded-md bg-surface-800 text-surface-400 hover:text-brand-400 hover:bg-surface-700 transition-colors flex items-center justify-center flex-shrink-0" title="Edit strategy code">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Z" /></svg>
                </router-link>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="label">Start Date</label>
                <input v-model="form.startDate" type="date" class="input" />
              </div>
              <div>
                <label class="label">End Date</label>
                <input v-model="form.finishDate" type="date" class="input" />
              </div>
            </div>

            <div>
              <label class="label">Starting Balance</label>
              <input v-model.number="form.balance" type="number" class="input" />
              <div class="text-[10px] text-surface-600 mt-1">Initial account equity for each simulation run. Use the same balance as your backtest for comparable results.</div>
            </div>

            <div>
              <label class="label">Number of Scenarios</label>
              <input v-model.number="form.numScenarios" type="number" class="input" min="5" max="1000" />
              <div class="text-[10px] text-surface-600 mt-1">How many randomized simulations to run. More scenarios = more statistical confidence but longer runtime. 50-100 is a good starting point, 200+ for publication-grade results.</div>
            </div>

            <div>
              <label class="label">CPU Cores</label>
              <input v-model.number="form.cpuCores" type="number" class="input" :max="maxCpuCores" min="1" />
              <div class="text-[10px] text-surface-600 mt-1">Parallel workers for simulation. More cores = faster completion. Leave 1-2 cores free for system responsiveness. Available: {{ maxCpuCores }}</div>
            </div>

            <div class="border-t border-surface-700 pt-3">
              <div class="text-xs font-semibold text-surface-400 mb-2">Simulation Types</div>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer mb-1">
                <input v-model="form.runTrades" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                Trade Shuffle
              </label>
              <div class="text-[10px] text-surface-600 mb-3 ml-6">Randomly reorders actual backtest trades. Tests whether your equity growth depends on lucky sequencing or is genuinely robust to any trade ordering.</div>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer mb-1">
                <input v-model="form.runCandles" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                Candle Simulation
              </label>
              <div class="text-[10px] text-surface-600 ml-6">Generates synthetic price data that preserves statistical properties of the original candles, then re-runs the full strategy. Tests whether your strategy works on "similar but different" markets, not just the exact history.</div>
            </div>

            <div v-if="form.runCandles" class="border-t border-surface-700 pt-3">
              <div class="text-xs font-semibold text-surface-400 mb-2">Candle Pipeline</div>
              <select v-model="form.pipelineType" class="select">
                <option value="moving_block_bootstrap">Moving Block Bootstrap</option>
                <option value="gaussian">Gaussian Noise</option>
              </select>
              <div class="text-[10px] text-surface-600 mt-1 mb-2">
                <span v-if="form.pipelineType === 'moving_block_bootstrap'">Reshuffles blocks of consecutive candles to create new price series. Preserves local price patterns (trends, volatility clusters) while changing the overall sequence — realistic synthetic data.</span>
                <span v-else>Adds random Gaussian noise to each candle's OHLC values. Simpler approach that tests sensitivity to small price variations while keeping the overall path structure intact.</span>
              </div>

              <div v-if="form.pipelineType === 'moving_block_bootstrap'" class="mt-2">
                <label class="label">Block Size (candles)</label>
                <input v-model.number="form.pipelineParams.batch_size" type="number" class="input" min="100" />
                <div class="text-[10px] text-surface-600 mt-1">Number of consecutive candles per block. Larger blocks preserve more market structure (trends, mean-reversion). Smaller blocks create more randomization. For 1h candles: 168 = 1 week, 720 = 1 month.</div>
              </div>

              <div v-if="form.pipelineType === 'gaussian'" class="mt-2 space-y-2">
                <div>
                  <label class="label">Close Sigma</label>
                  <input v-model.number="form.pipelineParams.close_sigma" type="number" step="0.0001" class="input" />
                  <div class="text-[10px] text-surface-600 mt-1">Standard deviation of noise added to close prices. 0.001 = ~0.1% perturbation per candle. Higher values create more extreme synthetic scenarios.</div>
                </div>
                <div>
                  <label class="label">High Sigma</label>
                  <input v-model.number="form.pipelineParams.high_sigma" type="number" step="0.0001" class="input" />
                  <div class="text-[10px] text-surface-600 mt-1">Noise on high prices. Affects stop-loss triggers and wick-based signals. Keep smaller than close sigma for realistic candle shapes.</div>
                </div>
                <div>
                  <label class="label">Low Sigma</label>
                  <input v-model.number="form.pipelineParams.low_sigma" type="number" step="0.0001" class="input" />
                  <div class="text-[10px] text-surface-600 mt-1">Noise on low prices. Affects take-profit triggers and support levels. Keep similar to high sigma for balanced perturbation.</div>
                </div>
              </div>
            </div>

            <!-- Advanced Risk Config -->
            <div class="border-t border-surface-700 pt-3">
              <button @click="showAdvanced = !showAdvanced" class="flex items-center gap-1.5 text-xs font-semibold text-surface-400 hover:text-surface-300 transition-colors w-full">
                <svg class="w-3 h-3 transition-transform" :class="showAdvanced ? 'rotate-90' : ''" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd" /></svg>
                Advanced Risk Configuration
              </button>
              <div v-if="showAdvanced" class="mt-3 space-y-3">
                <div>
                  <label class="label">Bust Threshold (%)</label>
                  <input v-model.number="form.bustThreshold" type="number" step="1" min="1" max="100" class="input" />
                  <div class="text-[10px] text-surface-600 mt-1">Maximum drawdown (%) that makes recovery impractical. P(Bust) counts simulations exceeding this DD. For hedging/grid strategies use 15-25%. For trend-following use 30-50%. Lower = stricter risk assessment.</div>
                </div>
                <div>
                  <label class="label">Ruin Threshold (%)</label>
                  <input v-model.number="form.ruinThreshold" type="number" step="1" min="-100" max="-50" class="input" />
                  <div class="text-[10px] text-surface-600 mt-1">Account loss level (%) that constitutes total ruin. P(Ruin) counts simulations where balance drops below this. -98% means account effectively wiped out. Use -90% if margin calls would stop you before total loss.</div>
                </div>
              </div>
            </div>

            <div v-if="!dataRange && form.exchange" class="p-2 bg-amber-500/10 rounded text-xs text-amber-400">
              No candle data found for {{ form.exchange }} / {{ form.symbol }}.
              <router-link to="/import" class="underline">Import data first</router-link>.
            </div>

            <button @click="startMonteCarlo" class="btn-primary w-full mt-2" :disabled="running || (!form.runTrades && !form.runCandles)">
              <span v-if="running" class="flex items-center justify-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Running...
              </span>
              <span v-else>Start Monte Carlo</span>
            </button>
            <button v-if="running" @click="cancelMonteCarlo" class="btn-secondary w-full text-sm">
              Cancel
            </button>
          </div>
        </div>
      </div>

      <!-- Right: Results Panel -->
      <div :class="running && !showConfig ? 'md:col-span-2 lg:col-span-3' : 'md:col-span-1 lg:col-span-2'" class="space-y-4 min-w-0">
        <!-- Error -->
        <div v-if="error" class="card border-red-500/30">
          <div class="flex items-center gap-2 mb-1">
            <span class="text-red-400 font-semibold text-sm">Error</span>
            <button @click="error = ''; errorTrace = ''" class="ml-auto text-surface-500 text-xs">Dismiss</button>
          </div>
          <p class="text-red-400 text-sm">{{ error }}</p>
          <pre v-if="errorTrace" class="text-xs text-red-300/70 mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap">{{ errorTrace }}</pre>
        </div>

        <!-- Alert message -->
        <div v-if="alertMessage" class="card" :class="alertType === 'success' ? 'border-green-500/30' : 'border-amber-500/30'">
          <p :class="alertType === 'success' ? 'text-green-400' : 'text-amber-400'" class="text-sm">{{ alertMessage }}</p>
        </div>

        <!-- Progress + General Info + Terminate (during run) -->
        <div v-if="running || completed" class="card p-5 space-y-4">
          <div class="flex items-center gap-5">
            <!-- Circular gauge -->
            <div class="relative w-24 h-24 flex-shrink-0">
              <svg class="w-24 h-24 -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="8" class="text-surface-800" />
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="8"
                  :class="completed ? 'text-green-500' : 'text-purple-500'"
                  class="transition-all duration-500 ease-out"
                  stroke-linecap="round"
                  :stroke-dasharray="2 * Math.PI * 52"
                  :stroke-dashoffset="2 * Math.PI * 52 * (1 - overallProgress / 100)" />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center">
                <svg v-if="completed" class="w-8 h-8 text-green-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/></svg>
                <span v-else class="text-xl font-bold text-surface-100 tabular-nums">{{ Math.round(overallProgress) }}%</span>
              </div>
            </div>
            <!-- Info + progress bars -->
            <div class="flex-1 min-w-0 space-y-2">
              <div class="flex items-center gap-2">
                <span v-if="running" class="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></span>
                <span v-else-if="completed" class="w-2 h-2 rounded-full bg-green-400"></span>
                <span class="text-sm font-medium text-surface-200">{{ running ? 'Monte Carlo' : 'Completed' }}</span>
                <span class="text-xs text-surface-500">{{ form.strategy }} &middot; {{ form.symbol }}</span>
              </div>
              <div class="space-y-1.5">
                <div v-if="form.runTrades" class="flex items-center gap-2">
                  <span class="text-[10px] text-surface-500 w-14 shrink-0">Trades</span>
                  <div class="flex-1 h-1.5 bg-surface-800 rounded-full overflow-hidden">
                    <div class="h-full bg-brand-500 rounded-full transition-all duration-500 ease-out" :style="{ width: tradesProgressPct + '%' }"></div>
                  </div>
                  <span class="text-[10px] text-surface-400 tabular-nums w-16 text-right">{{ tradesProgress.current }}/{{ tradesProgress.total }}</span>
                </div>
                <div v-if="form.runCandles" class="flex items-center gap-2">
                  <span class="text-[10px] text-surface-500 w-14 shrink-0">Candles</span>
                  <div class="flex-1 h-1.5 bg-surface-800 rounded-full overflow-hidden">
                    <div class="h-full bg-purple-500 rounded-full transition-all duration-500 ease-out" :style="{ width: candlesProgressPct + '%' }"></div>
                  </div>
                  <span class="text-[10px] text-surface-400 tabular-nums w-16 text-right">{{ candlesProgress.current }}/{{ candlesProgress.total }}</span>
                </div>
              </div>
              <div class="flex items-center gap-4 text-xs text-surface-500">
                <span v-if="running && (tradesProgress.eta > 0 || candlesProgress.eta > 0)" class="flex items-center gap-1">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  ~{{ formatEta(Math.max(tradesProgress.eta, candlesProgress.eta)) }} remaining
                </span>
                <span v-if="runStartedAt" class="flex items-center gap-1">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"/></svg>
                  {{ elapsedTime }}
                </span>
                <span class="text-surface-600">{{ form.numScenarios }} scenarios &middot; {{ form.cpuCores }} cores</span>
              </div>
            </div>
          </div>

          <!-- General Info (inline, during run) -->
          <div v-if="running && generalInfo" class="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-1 text-xs border-t border-surface-700 pt-3">
            <div class="flex justify-between"><span class="text-surface-500">Trade Shuffle</span><span class="text-surface-200">{{ generalInfo.run_trades ? 'Yes' : 'No' }}</span></div>
            <div class="flex justify-between"><span class="text-surface-500">Candle Sim</span><span class="text-surface-200">{{ generalInfo.run_candles ? 'Yes' : 'No' }}</span></div>
            <div class="flex justify-between"><span class="text-surface-500">Exchange Type</span><span class="text-surface-200">{{ generalInfo.exchange_type }}</span></div>
            <div class="flex justify-between"><span class="text-surface-500">Leverage</span><span class="text-surface-200">{{ generalInfo.leverage_mode }} {{ generalInfo.leverage }}</span></div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-3 pt-1">
            <button v-if="running" @click="cancelMonteCarlo" class="btn-sm border border-red-500/30 text-red-400 hover:bg-red-500/10">Terminate</button>
            <button v-if="running" @click="showConfig = !showConfig" class="btn-sm bg-surface-700 text-surface-300">{{ showConfig ? 'Hide Config' : 'Show Config' }}</button>
            <button v-if="completed && currentTaskId" @click="viewResultsFromRun()" class="btn-primary btn-sm flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/></svg>
              View Results
            </button>
            <span v-if="completed" class="text-xs text-surface-500">{{ alertMessage }}</span>
          </div>
        </div>

        <!-- Session Results (sub-tabbed): shown when a session is selected -->
        <template v-if="selectedSession">
          <!-- Session header bar -->
          <div class="card p-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="statusBadgeClass(selectedSession.status)">{{ selectedSession.status }}</span>
                <span class="text-sm text-surface-200 font-medium">{{ sessionStrategy(selectedSession) }}</span>
                <span class="text-xs text-surface-500">{{ sessionExchange(selectedSession) }} / {{ selectedSession.state?.form?.symbol || '-' }}</span>
                <span class="text-xs text-surface-600">{{ formatDateTime(selectedSession.created_at) }}</span>
              </div>
              <button @click="selectedSession = null; equityCurveData = null; logsContent = ''" class="text-xs text-surface-500 hover:text-surface-200">Close</button>
            </div>
          </div>

          <!-- Result sub-tabs -->
          <div class="flex items-center gap-1 border-b border-surface-700 mb-4 -mt-1 overflow-x-auto">
            <button v-for="tab in resultTabs" :key="tab.id"
              @click="activeResultTab = tab.id"
              class="px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors"
              :class="activeResultTab === tab.id
                ? 'border-brand-500 text-brand-400'
                : 'border-transparent text-surface-500 hover:text-surface-300'">
              {{ tab.label }}
            </button>
          </div>

          <!-- Sub-tab: Results (metrics tables) -->
          <div v-if="activeResultTab === 'results'">
            <!-- Session exceptions -->
            <div v-if="selectedSession.trades_session?.exception" class="card p-3 border-red-500/30 mb-4">
              <div class="text-red-400 text-xs font-semibold mb-1">Trades Exception</div>
              <p class="text-red-300 text-xs">{{ selectedSession.trades_session.exception }}</p>
              <pre v-if="selectedSession.trades_session.traceback" class="text-[10px] text-red-300/70 mt-1 max-h-[150px] overflow-auto whitespace-pre-wrap">{{ selectedSession.trades_session.traceback }}</pre>
            </div>
            <div v-if="selectedSession.candles_session?.exception" class="card p-3 border-red-500/30 mb-4">
              <div class="text-red-400 text-xs font-semibold mb-1">Candles Exception</div>
              <p class="text-red-300 text-xs">{{ selectedSession.candles_session.exception }}</p>
              <pre v-if="selectedSession.candles_session.traceback" class="text-[10px] text-red-300/70 mt-1 max-h-[150px] overflow-auto whitespace-pre-wrap">{{ selectedSession.candles_session.traceback }}</pre>
            </div>

            <!-- Trades Metrics -->
            <div v-if="activeTradesMetrics.length > 0" class="card mb-4">
              <div class="flex items-center justify-between mb-1">
                <h2 class="text-sm font-semibold text-surface-300">Trade Shuffle Results</h2>
                <button @click="showTooltips = !showTooltips" class="text-[10px] px-2 py-0.5 rounded transition-colors"
                  :class="showTooltips ? 'bg-brand-500/20 text-brand-400' : 'bg-surface-700 text-surface-500'">
                  {{ showTooltips ? 'Hints On' : 'Hints Off' }}
                </button>
              </div>
              <SectionGuide category="monte-carlo" title="How to read Monte Carlo results" />
              <div class="overflow-x-auto">
                <table class="w-full text-xs">
                  <thead><tr class="border-b border-surface-700">
                    <th class="text-left py-2 px-2 text-surface-500 font-medium">Metric</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Original</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Worst 5%</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Median</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Best 5%</th>
                  </tr></thead>
                  <tbody>
                    <tr v-for="m in activeTradesMetrics" :key="m.metric" class="border-b border-surface-800">
                      <td class="py-2 px-2 text-surface-400"><MetricTooltip :metric-key="m.metric" position="below" align="left">{{ formatMetricName(m.metric) }}</MetricTooltip></td>
                      <td class="py-2 px-2 text-surface-200 font-mono text-right">{{ formatNum(m.original) }}</td>
                      <td class="py-2 px-2 font-mono text-right text-red-400">{{ formatNum(m.worst_5) }}</td>
                      <td class="py-2 px-2 font-mono text-right text-surface-200">{{ formatNum(m.median) }}</td>
                      <td class="py-2 px-2 font-mono text-right text-green-400">{{ formatNum(m.best_5) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Candles Metrics -->
            <div v-if="activeCandlesMetrics.length > 0" class="card">
              <h2 class="text-sm font-semibold text-surface-300 mb-4">Candle Simulation Results</h2>
              <div class="overflow-x-auto">
                <table class="w-full text-xs">
                  <thead><tr class="border-b border-surface-700">
                    <th class="text-left py-2 px-2 text-surface-500 font-medium">Metric</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Original</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Worst 5%</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Median</th>
                    <th class="text-right py-2 px-2 text-surface-500 font-medium">Best 5%</th>
                  </tr></thead>
                  <tbody>
                    <tr v-for="m in activeCandlesMetrics" :key="m.metric" class="border-b border-surface-800">
                      <td class="py-2 px-2 text-surface-400"><MetricTooltip :metric-key="m.metric" position="below" align="left">{{ formatMetricName(m.metric) }}</MetricTooltip></td>
                      <td class="py-2 px-2 text-surface-200 font-mono text-right">{{ formatNum(m.original) }}</td>
                      <td class="py-2 px-2 font-mono text-right text-red-400">{{ formatNum(m.worst_5) }}</td>
                      <td class="py-2 px-2 font-mono text-right text-surface-200">{{ formatNum(m.median) }}</td>
                      <td class="py-2 px-2 font-mono text-right text-green-400">{{ formatNum(m.best_5) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-if="!activeTradesMetrics.length && !activeCandlesMetrics.length" class="text-surface-500 text-sm py-8 text-center">
              No metric results available for this session.
            </div>
          </div>

          <!-- Sub-tab: Charts (equity curves) -->
          <div v-if="activeResultTab === 'charts'">
            <div v-if="equityCurveData" class="card">
              <div class="flex items-center justify-between mb-4">
                <h2 class="text-sm font-semibold text-surface-300">Equity Curves</h2>
                <div class="flex items-center gap-2">
                  <span v-if="activeEquityCurves?.scenarios" class="text-[10px] text-surface-500">{{ activeEquityCurves.scenarios.length }} scenarios</span>
                  <select v-model="equityCurveType" class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300">
                    <option v-if="equityCurveData.trades" value="trades">Trade Shuffle</option>
                    <option v-if="equityCurveData.candles" value="candles">Candle Simulation</option>
                  </select>
                </div>
              </div>
              <div class="relative select-none" style="height: 320px;" @mousemove="onChartHover" @mouseleave="chartHoverX = null">
                <svg :viewBox="`0 0 ${ecChartWidth} ${ecChartHeight}`" class="w-full h-full" preserveAspectRatio="xMidYMid meet">
                  <rect :x="ecPad.left" :y="ecPad.top" :width="ecChartWidth - ecPad.left - ecPad.right" :height="ecChartHeight - ecPad.top - ecPad.bottom" fill="#0a0a0f" rx="4" />
                  <line v-for="i in 5" :key="'ecgrid-' + i" :x1="ecPad.left" :x2="ecChartWidth - ecPad.right" :y1="ecPad.top + (i - 1) * ((ecChartHeight - ecPad.top - ecPad.bottom) / 4)" :y2="ecPad.top + (i - 1) * ((ecChartHeight - ecPad.top - ecPad.bottom) / 4)" stroke="#1f2937" stroke-width="0.5" />
                  <text v-for="i in 5" :key="'ecy-' + i" :x="ecPad.left - 4" :y="ecPad.top + (i - 1) * ((ecChartHeight - ecPad.top - ecPad.bottom) / 4) + 3" text-anchor="end" fill="#6b7280" font-size="9" font-family="monospace">{{ ecYLabel(i - 1) }}</text>
                  <polygon v-if="percentileBandPath" :points="percentileBandPath" fill="#6366f1" opacity="0.08" />
                  <polyline v-for="(path, idx) in scenarioLinePaths" :key="'sc-' + idx" :points="path" fill="none" stroke="#6366f1" stroke-width="0.5" opacity="0.15" />
                  <polyline v-if="medianLinePath" :points="medianLinePath" fill="none" stroke="#a78bfa" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.7" />
                  <polyline v-if="originalLinePath" :points="originalLinePath" fill="none" stroke="#22c55e" stroke-width="2" />
                  <line :x1="ecPad.left" :x2="ecChartWidth - ecPad.right" :y1="balanceY" :y2="balanceY" stroke="#fbbf24" stroke-width="0.5" stroke-dasharray="6,4" opacity="0.4" />
                  <line v-if="chartHoverX !== null" :x1="chartHoverX" :x2="chartHoverX" :y1="ecPad.top" :y2="ecChartHeight - ecPad.bottom" stroke="#6b7280" stroke-width="0.5" stroke-dasharray="3,3" />
                </svg>
                <div class="absolute top-3 left-14 flex items-center gap-4 text-[10px]">
                  <span class="flex items-center gap-1"><span class="w-4 h-0.5 bg-green-500 inline-block"></span> Original</span>
                  <span class="flex items-center gap-1"><span class="w-4 h-0.5 bg-purple-400 inline-block opacity-70" style="border-bottom: 1px dashed;"></span> Median</span>
                  <span class="flex items-center gap-1"><span class="w-4 h-2 bg-indigo-500 inline-block opacity-20 rounded-sm"></span> 5-95th Pctl</span>
                  <span class="flex items-center gap-1"><span class="w-4 h-0.5 bg-amber-400 inline-block opacity-50" style="border-bottom: 1px dashed;"></span> Start Balance</span>
                </div>
                <div v-if="ecSummary" class="absolute bottom-3 left-14 flex items-center gap-4 text-[10px]">
                  <span class="text-green-400">Final: ${{ ecSummary.originalFinal?.toFixed(0) }}</span>
                  <span class="text-red-400">Worst: ${{ ecSummary.worstFinal?.toFixed(0) }}</span>
                  <span class="text-surface-400">Median: ${{ ecSummary.medianFinal?.toFixed(0) }}</span>
                  <span class="text-green-400/70">Best: ${{ ecSummary.bestFinal?.toFixed(0) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="text-surface-500 text-sm py-8 text-center">No equity curve data available for this session.</div>
          </div>

          <!-- Sub-tab: Risk (probability cards) -->
          <div v-if="activeResultTab === 'risk'">
            <SectionGuide category="monte-carlo" title="How to read risk probabilities" />
            <template v-if="tradesRiskMetrics || candlesRiskMetrics">
              <!-- Trade Shuffle Risk -->
              <div v-if="tradesRiskMetrics" class="card mb-4">
                <h2 class="text-sm font-semibold text-surface-300 mb-4">Trade Shuffle Risk</h2>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="p_ruin" position="below">P(Ruin)</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono" :class="tradesRiskMetrics.p_ruin > 0.01 ? 'text-red-400' : tradesRiskMetrics.p_ruin > 0 ? 'text-yellow-400' : 'text-green-400'">
                      {{ (tradesRiskMetrics.p_ruin * 100).toFixed(2) }}%
                    </div>
                    <div class="text-[10px] text-surface-600 mt-0.5">Return &le; {{ tradesRiskMetrics.ruin_threshold || -98 }}% ({{ tradesRiskMetrics.ruin_count }}/{{ tradesRiskMetrics.num_simulations }})</div>
                  </div>
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="p_bust" position="below">P(Bust)</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono" :class="tradesRiskMetrics.p_bust > 0.05 ? 'text-red-400' : tradesRiskMetrics.p_bust > 0.01 ? 'text-yellow-400' : 'text-green-400'">
                      {{ (tradesRiskMetrics.p_bust * 100).toFixed(2) }}%
                    </div>
                    <div class="text-[10px] text-surface-600 mt-0.5">DD &ge; {{ tradesRiskMetrics.bust_threshold }}% ({{ tradesRiskMetrics.bust_count }}/{{ tradesRiskMetrics.num_simulations }})</div>
                  </div>
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="avg_max_consecutive_losses" position="below">Avg Max Consec. Losses</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono text-surface-200">{{ tradesRiskMetrics.avg_max_consecutive_losses?.toFixed(1) || '—' }}</div>
                  </div>
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="p95_max_consecutive_losses" position="below">P95 Max Consec. Losses</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono text-surface-200">{{ tradesRiskMetrics.p95_max_consecutive_losses?.toFixed(1) || '—' }}</div>
                  </div>
                </div>
                <p class="text-[10px] text-surface-600 mt-3">Tests if trade ordering affects risk. Same trades, different sequences.</p>
              </div>
              <!-- Candle Simulation Risk -->
              <div v-if="candlesRiskMetrics" class="card mb-4">
                <h2 class="text-sm font-semibold text-surface-300 mb-4">Candle Simulation Risk</h2>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="p_ruin" position="below">P(Ruin)</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono" :class="candlesRiskMetrics.p_ruin > 0.01 ? 'text-red-400' : candlesRiskMetrics.p_ruin > 0 ? 'text-yellow-400' : 'text-green-400'">
                      {{ (candlesRiskMetrics.p_ruin * 100).toFixed(2) }}%
                    </div>
                    <div class="text-[10px] text-surface-600 mt-0.5">Return &le; {{ candlesRiskMetrics.ruin_threshold || -98 }}% ({{ candlesRiskMetrics.ruin_count }}/{{ candlesRiskMetrics.num_simulations }})</div>
                  </div>
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="p_bust" position="below">P(Bust)</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono" :class="candlesRiskMetrics.p_bust > 0.05 ? 'text-red-400' : candlesRiskMetrics.p_bust > 0.01 ? 'text-yellow-400' : 'text-green-400'">
                      {{ (candlesRiskMetrics.p_bust * 100).toFixed(2) }}%
                    </div>
                    <div class="text-[10px] text-surface-600 mt-0.5">DD &ge; {{ candlesRiskMetrics.bust_threshold }}% ({{ candlesRiskMetrics.bust_count }}/{{ candlesRiskMetrics.num_simulations }})</div>
                  </div>
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="avg_max_consecutive_losses" position="below">Avg Max Consec. Losses</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono text-surface-200">{{ candlesRiskMetrics.avg_max_consecutive_losses?.toFixed(1) || '—' }}</div>
                  </div>
                  <div class="bg-surface-800/60 rounded-lg p-3 text-center">
                    <div class="text-[10px] uppercase tracking-wider text-surface-500 mb-1"><MetricTooltip metric-key="p95_max_consecutive_losses" position="below">P95 Max Consec. Losses</MetricTooltip></div>
                    <div class="text-lg font-bold font-mono text-surface-200">{{ candlesRiskMetrics.p95_max_consecutive_losses?.toFixed(1) || '—' }}</div>
                  </div>
                </div>
                <p class="text-[10px] text-surface-600 mt-3">Tests strategy on synthetic market paths. Different price action, full re-simulation.</p>
              </div>
            </template>
            <div v-else class="text-surface-500 text-sm py-8 text-center">No risk metrics available for this session.</div>
          </div>

          <!-- Sub-tab: Logs (per-run) -->
          <div v-if="activeResultTab === 'logs'">
            <div class="card">
              <div class="flex items-center justify-between mb-3">
                <span class="text-sm font-semibold text-surface-300">Run Logs</span>
                <div class="flex items-center gap-2">
                  <span v-if="logsContent" class="text-[10px] text-surface-600">{{ logsContent.split('\n').length }} lines</span>
                  <button @click="loadLogsInline(selectedSession.id)" class="btn-sm bg-surface-700 text-surface-300" :disabled="logsLoading">
                    {{ logsLoading ? 'Loading...' : logsContent ? 'Refresh' : 'Load Logs' }}
                  </button>
                </div>
              </div>
              <div v-if="logsContent" class="bg-surface-900 rounded p-3 max-h-[500px] overflow-auto">
                <pre class="text-xs text-surface-400 whitespace-pre-wrap font-mono">{{ logsContent }}</pre>
              </div>
              <div v-else class="text-surface-500 text-sm py-8 text-center">
                {{ logsLoading ? 'Loading logs...' : 'Click "Load Logs" to fetch logs for this run.' }}
              </div>
            </div>
          </div>
        </template>

        <!-- Empty state: no session selected, not running -->
        <div v-if="!running && !completed && !selectedSession" class="text-surface-500 text-sm py-16 text-center">
          Configure and start a Monte Carlo simulation, or view a past run from History.
        </div>
      </div>
    </div>

    <!-- ═══ HISTORY VIEW ═══ -->
    <div v-show="pageTab === 'history'" class="space-y-4">
      <div class="card">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-sm font-semibold text-surface-300">Session History</h2>
            <p class="text-[11px] text-surface-500 mt-0.5">Browse, compare, and manage past Monte Carlo runs</p>
          </div>
          <div class="flex items-center gap-2">
            <button @click="loadSessions" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
            <button v-if="sessions.length" @click="showPurgeConfirm = true" class="text-xs text-red-400 hover:text-red-300">Purge</button>
          </div>
        </div>

        <!-- Purge Confirm -->
        <div v-if="showPurgeConfirm" class="mb-4 p-3 bg-red-500/10 rounded-lg border border-red-500/20">
          <p class="text-xs text-red-300 mb-2">Delete sessions older than:</p>
          <div class="flex items-center gap-2">
            <select v-model="purgeDays" class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300">
              <option :value="7">7 days</option>
              <option :value="30">30 days</option>
              <option :value="90">90 days</option>
              <option :value="null">All</option>
            </select>
            <button @click="purge" class="text-xs bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600">Purge</button>
            <button @click="showPurgeConfirm = false" class="text-xs text-surface-400 hover:text-surface-200">Cancel</button>
          </div>
        </div>

        <!-- Filters -->
        <div v-if="sessions.length > 3 || sessionsStatusFilter !== 'all'" class="flex items-center gap-3 mb-3">
          <input v-model="sessionsSearch" placeholder="Search by strategy, symbol..." class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300 flex-1" />
          <select v-model="sessionsStatusFilter" class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300">
            <option value="all">All Statuses</option>
            <option value="finished">Finished</option>
            <option value="running">Running</option>
            <option value="stopped">Stopped</option>
            <option value="terminated">Terminated</option>
          </select>
        </div>

        <div v-if="loadingSessions" class="text-surface-500 text-sm py-8 text-center">Loading...</div>

        <div v-else-if="sessions.length === 0" class="text-surface-500 text-sm py-8 text-center">
          No Monte Carlo sessions yet. Run a simulation to see results here.
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-surface-500 text-xs border-b border-surface-700">
                <th class="text-left py-2 px-2 font-medium">Status</th>
                <th class="text-left py-2 px-2 font-medium">Strategy / Config</th>
                <th v-if="showOwnerColumn" class="text-left py-2 px-2 font-medium">Owner</th>
                <th class="text-left py-2 px-2 font-medium">Type</th>
                <th class="text-left py-2 px-2 font-medium">Date</th>
                <th class="text-right py-2 px-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in filteredSessions" :key="s.id"
                class="border-b border-surface-800 hover:bg-surface-800/50 cursor-pointer transition-colors"
                :class="selectedSession?.id === s.id ? 'bg-surface-800/70 border-l-2 border-l-brand-500' : ''"
                @click="viewSessionFromHistory(s)">
                <td class="py-2.5 px-2">
                  <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="statusBadgeClass(s.status)">{{ s.status }}</span>
                </td>
                <td class="py-2.5 px-2">
                  <div class="text-surface-200 font-medium">{{ sessionStrategy(s) }}</div>
                  <div class="text-surface-500 text-[10px] mt-0.5">{{ sessionExchange(s) }} {{ s.state?.form?.symbol ? '/ ' + s.state.form.symbol : '' }}</div>
                </td>
                <td v-if="showOwnerColumn" class="py-2.5 px-2">
                  <span v-if="s.owner_username" class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 font-medium">{{ s.owner_username }}</span>
                </td>
                <td class="py-2.5 px-2 text-surface-400">
                  <span v-if="s.has_trades" class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/20 text-brand-400 mr-1">Trades</span>
                  <span v-if="s.has_candles" class="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">Candles</span>
                </td>
                <td class="py-2.5 px-2 text-surface-500">{{ formatDateTime(s.updated_at) }}</td>
                <td class="py-2.5 px-2 text-right">
                  <div class="flex items-center gap-2 justify-end">
                    <button @click.stop="viewSessionFromHistory(s)"
                      class="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-brand-600/20 text-brand-400 hover:bg-brand-600/30 transition-colors" title="View results">
                      <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                      View
                    </button>
                    <button @click.stop="removeSession(s)"
                      class="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors" title="Delete session">
                      <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, defaultBrokerId, isAdmin, isImpersonating } from '../api'
import { useWebSocket } from '../useWebSocket'
import { useGuides } from '../useGuides'
import MetricTooltip from '../components/MetricTooltip.vue'
import SectionGuide from '../components/SectionGuide.vue'
import { useProcessManager } from '../useProcessManager'

const pm = useProcessManager()
const currentRoute = useRoute()

const { showTooltips } = useGuides()

const brokers = ref([])
const strategies = ref([])
const sessions = ref([])
const selectedSession = ref(null)
const openTabs = ref([])
const tabCache = ref({})
const running = ref(false)

// Workspace tabs
const workspaceTabs = ref([{ id: 'ws-1', label: 'Monte Carlo 1', running: false, hasResults: false }])
const activeWorkspaceId = ref('ws-1')
const workspaceCache = ref({})
let wsCounter = 1
const showConfig = ref(false)
const pageTab = ref('run')  // 'run', 'history'
const activeResultTab = ref('results')  // 'results', 'charts', 'risk', 'logs'
const loadingSessions = ref(false)
const error = ref('')
const errorTrace = ref('')
const alertMessage = ref('')
const alertType = ref('success')
const currentTaskId = ref(null)
const maxCpuCores = ref(12)
const logsContent = ref('')
const logsLoading = ref(false)
const showPurgeConfirm = ref(false)
const purgeDays = ref(30)
const sessionsSearch = ref('')
const sessionsStatusFilter = ref('all')
const existingCandles = ref([])
let pollTimer = null
const runStartedAt = ref(null)
const elapsedNow = ref(Date.now())
let elapsedTimer = null

// WebSocket-driven state
const tradesProgress = ref({ current: 0, total: 0, eta: 0 })
const candlesProgress = ref({ current: 0, total: 0, eta: 0 })
const generalInfo = ref(null)
const tradesSummaryMetrics = ref([])
const candlesSummaryMetrics = ref([])
const equityCurveData = ref(null)
const equityCurveType = ref('trades')

const timeframes = [
  { value: '1m', label: '1 Minute' },
  { value: '3m', label: '3 Minutes' },
  { value: '5m', label: '5 Minutes' },
  { value: '15m', label: '15 Minutes' },
  { value: '30m', label: '30 Minutes' },
  { value: '1h', label: '1 Hour' },
  { value: '2h', label: '2 Hours' },
  { value: '4h', label: '4 Hours' },
  { value: '6h', label: '6 Hours' },
  { value: '1D', label: '1 Day' },
]

const form = ref({
  exchange: '',
  symbol: 'EUR-USD',
  timeframe: '1h',
  strategy: 'ForexMA',
  startDate: '2024-01-01',
  finishDate: '2024-09-01',
  balance: 10000,
  numScenarios: 50,
  cpuCores: 6,
  runTrades: true,
  runCandles: true,
  pipelineType: 'moving_block_bootstrap',
  pipelineParams: {
    batch_size: 10080,
    close_sigma: 0.001,
    high_sigma: 0.0001,
    low_sigma: 0.0001,
  },
  fastMode: true,
  // Advanced risk thresholds
  bustThreshold: 25,
  ruinThreshold: -98,
})

const showAdvanced = ref(false)

const availableSymbols = computed(() => {
  const exch = form.value.exchange
  if (!exch) return []
  const syms = new Set()
  for (const c of existingCandles.value) {
    if (c.exchange === exch) syms.add(c.symbol)
  }
  return [...syms]
})

const dataRange = computed(() => {
  const match = existingCandles.value.find(
    c => c.exchange === form.value.exchange && c.symbol === form.value.symbol
  )
  if (!match) return null
  return {
    start: match.from || match.start_date || '',
    end: match.to || match.end_date || '',
  }
})

const showOwnerColumn = computed(() => isAdmin() && !isImpersonating())
const filteredSessions = computed(() => {
  let list = sessions.value
  if (sessionsStatusFilter.value !== 'all') {
    list = list.filter(s => s.status === sessionsStatusFilter.value)
  }
  if (sessionsSearch.value) {
    const q = sessionsSearch.value.toLowerCase()
    list = list.filter(s => {
      const title = (s.title || '').toLowerCase()
      const strategy = sessionStrategy(s).toLowerCase()
      return title.includes(q) || strategy.includes(q) || s.id?.includes(q)
    })
  }
  return list
})

const resultTabs = computed(() => {
  const tabs = [
    { id: 'results', label: 'Results' },
    { id: 'charts', label: 'Charts' },
    { id: 'risk', label: 'Risk' },
    { id: 'logs', label: 'Logs' },
  ]
  return tabs
})

const tradesProgressPct = computed(() => {
  if (!tradesProgress.value.total) return 0
  return (tradesProgress.value.current / tradesProgress.value.total) * 100
})

const candlesProgressPct = computed(() => {
  if (!candlesProgress.value.total) return 0
  return (candlesProgress.value.current / candlesProgress.value.total) * 100
})

const completed = computed(() => !running.value && alertType.value === 'success' && !!alertMessage.value)

const overallProgress = computed(() => {
  if (completed.value) return 100
  let total = 0
  let done = 0
  if (form.value.runTrades) {
    total += form.value.numScenarios
    done += tradesProgress.value.current
  }
  if (form.value.runCandles) {
    total += form.value.numScenarios
    done += candlesProgress.value.current
  }
  if (total === 0) return 0
  return (done / total) * 100
})

const elapsedTime = computed(() => {
  if (!runStartedAt.value) return ''
  const diff = Math.floor((elapsedNow.value - runStartedAt.value) / 1000)
  if (diff < 60) return `${diff}s elapsed`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s elapsed`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m elapsed`
})

// Elapsed timer
watch(running, (isRunning) => {
  if (isRunning) {
    elapsedNow.value = Date.now()
    elapsedTimer = setInterval(() => { elapsedNow.value = Date.now() }, 1000)
  } else {
    if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
  }
})

// Metrics: only from loaded session (not live WebSocket — user clicks "View Results")
const activeTradesMetrics = computed(() => {
  if (selectedSession.value?.trades_session?.summary_metrics?.length) return selectedSession.value.trades_session.summary_metrics
  return []
})

const activeCandlesMetrics = computed(() => {
  if (selectedSession.value?.candles_session?.summary_metrics?.length) return selectedSession.value.candles_session.summary_metrics
  return []
})

const tradesRiskMetrics = computed(() => selectedSession.value?.trades_session?.risk_metrics || null)
const candlesRiskMetrics = computed(() => selectedSession.value?.candles_session?.risk_metrics || null)
const activeRiskMetrics = computed(() => tradesRiskMetrics.value || candlesRiskMetrics.value || null)

// Equity curve chart
const ecChartWidth = 800
const ecChartHeight = 320
const ecPad = { top: 20, right: 10, bottom: 20, left: 60 }
const chartHoverX = ref(null)

const activeEquityCurves = computed(() => {
  if (!equityCurveData.value) return null
  return equityCurveData.value[equityCurveType.value] || null
})

function getEquityCurvePrices(curve) {
  if (!curve || !curve.data) return []
  return curve.data.map(p => p.value)
}

function computeEquityLinePath(prices, yMin, yMax) {
  const n = prices.length
  if (n === 0) return ''
  const xRange = ecChartWidth - ecPad.left - ecPad.right
  const yRange = ecChartHeight - ecPad.top - ecPad.bottom
  const points = []
  for (let i = 0; i < n; i++) {
    const v = prices[i]
    if (v === null || v === undefined) continue
    const x = ecPad.left + (i / Math.max(n - 1, 1)) * xRange
    const y = yMax === yMin
      ? ecPad.top + yRange / 2
      : ecPad.top + yRange - ((v - yMin) / (yMax - yMin)) * yRange
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return points.join(' ')
}

const ecYBounds = computed(() => {
  const curves = activeEquityCurves.value
  if (!curves) return { yMin: 0, yMax: 10000 }
  let allVals = []
  if (curves.original) allVals.push(...getEquityCurvePrices(curves.original))
  for (const sc of (curves.scenarios || [])) {
    allVals.push(...getEquityCurvePrices(sc))
  }
  allVals = allVals.filter(v => v !== null && v !== undefined && isFinite(v))
  if (allVals.length === 0) return { yMin: 0, yMax: 10000 }
  let yMin = Math.min(...allVals)
  let yMax = Math.max(...allVals)
  if (yMin === yMax) { yMin -= 100; yMax += 100 }
  const pad = (yMax - yMin) * 0.05
  return { yMin: yMin - pad, yMax: yMax + pad }
})

const ecYMin = computed(() => ecYBounds.value.yMin)
const ecYMax = computed(() => ecYBounds.value.yMax)

const originalLinePath = computed(() => {
  const curves = activeEquityCurves.value
  if (!curves?.original) return ''
  const prices = getEquityCurvePrices(curves.original)
  return computeEquityLinePath(prices, ecYMin.value, ecYMax.value)
})

const scenarioLinePaths = computed(() => {
  const curves = activeEquityCurves.value
  if (!curves?.scenarios) return []
  return curves.scenarios.map(sc => {
    const prices = getEquityCurvePrices(sc)
    return computeEquityLinePath(prices, ecYMin.value, ecYMax.value)
  })
})

function ecYLabel(idx) {
  const range = ecYMax.value - ecYMin.value
  const val = ecYMax.value - (idx / 4) * range
  return '$' + val.toFixed(0)
}

const balanceY = computed(() => {
  const bal = form.value.balance
  const { yMin, yMax } = ecYBounds.value
  if (yMax === yMin) return ecPad.top + (ecChartHeight - ecPad.top - ecPad.bottom) / 2
  const yRange = ecChartHeight - ecPad.top - ecPad.bottom
  return ecPad.top + yRange - ((bal - yMin) / (yMax - yMin)) * yRange
})

const medianLinePath = computed(() => {
  const curves = activeEquityCurves.value
  if (!curves?.scenarios?.length) return ''
  const allPrices = curves.scenarios.map(sc => getEquityCurvePrices(sc))
  const maxLen = Math.max(...allPrices.map(p => p.length))
  if (maxLen === 0) return ''
  const medians = []
  for (let i = 0; i < maxLen; i++) {
    const vals = allPrices.map(p => p[Math.min(i, p.length - 1)]).filter(v => v != null).sort((a, b) => a - b)
    if (vals.length) medians.push(vals[Math.floor(vals.length / 2)])
  }
  return computeEquityLinePath(medians, ecYMin.value, ecYMax.value)
})

const percentileBandPath = computed(() => {
  const curves = activeEquityCurves.value
  if (!curves?.scenarios?.length) return ''
  const allPrices = curves.scenarios.map(sc => getEquityCurvePrices(sc))
  const maxLen = Math.max(...allPrices.map(p => p.length))
  if (maxLen === 0) return ''

  const xRange = ecChartWidth - ecPad.left - ecPad.right
  const yRange = ecChartHeight - ecPad.top - ecPad.bottom
  const { yMin, yMax } = ecYBounds.value
  const toY = (v) => yMax === yMin ? ecPad.top + yRange / 2 : ecPad.top + yRange - ((v - yMin) / (yMax - yMin)) * yRange
  const toX = (i) => ecPad.left + (i / Math.max(maxLen - 1, 1)) * xRange

  const upper = []
  const lower = []
  for (let i = 0; i < maxLen; i++) {
    const vals = allPrices.map(p => p[Math.min(i, p.length - 1)]).filter(v => v != null).sort((a, b) => a - b)
    if (vals.length) {
      upper.push(`${toX(i).toFixed(1)},${toY(vals[Math.floor(vals.length * 0.95)]).toFixed(1)}`)
      lower.push(`${toX(i).toFixed(1)},${toY(vals[Math.floor(vals.length * 0.05)]).toFixed(1)}`)
    }
  }
  return [...upper, ...lower.reverse()].join(' ')
})

const ecSummary = computed(() => {
  const curves = activeEquityCurves.value
  if (!curves) return null
  const origPrices = curves.original ? getEquityCurvePrices(curves.original) : []
  const scenarioPrices = (curves.scenarios || []).map(sc => getEquityCurvePrices(sc))
  const finals = scenarioPrices.map(p => p[p.length - 1]).filter(v => v != null).sort((a, b) => a - b)
  if (!finals.length) return null
  return {
    originalFinal: origPrices.length ? origPrices[origPrices.length - 1] : null,
    worstFinal: finals[0],
    medianFinal: finals[Math.floor(finals.length / 2)],
    bestFinal: finals[finals.length - 1],
  }
})

function onChartHover(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * ecChartWidth
  if (x >= ecPad.left && x <= ecChartWidth - ecPad.right) {
    chartHoverX.value = x
  } else {
    chartHoverX.value = null
  }
}

function onExchangeChange() {
  const syms = availableSymbols.value
  if (syms.length && !syms.includes(form.value.symbol)) {
    form.value.symbol = syms[0]
  }
  autoSetDates()
}

function onSymbolChange() {
  autoSetDates()
}

function autoSetDates() {
  const range = dataRange.value
  if (range && range.start && range.end) {
    form.value.startDate = range.start
    form.value.finishDate = range.end
  }
}

// ── Workspace management ──
const _wsRefs = {
  form, running, showConfig, error, errorTrace, alertMessage, alertType, currentTaskId,
  tradesProgress, candlesProgress, generalInfo,
  tradesSummaryMetrics, candlesSummaryMetrics,
  equityCurveData, equityCurveType,
  selectedSession, openTabs, tabCache, activeResultTab,
}

function _snapshotWs() {
  const snap = {}
  for (const [k, r] of Object.entries(_wsRefs)) snap[k] = JSON.parse(JSON.stringify(r.value))
  return snap
}

function _restoreWs(snap) {
  for (const [k, r] of Object.entries(_wsRefs)) {
    if (k in snap) r.value = snap[k]
  }
}

function _freshDefaults() {
  return {
    form: {
      exchange: form.value.exchange, symbol: 'EUR-USD', timeframe: '1h',
      strategy: strategies.value[0]?.name || 'ForexMA',
      startDate: '2024-01-01', finishDate: '2024-09-01',
      balance: 10000, numScenarios: 50,
      cpuCores: Math.min(6, maxCpuCores.value),
      runTrades: true, runCandles: true,
      pipelineType: 'moving_block_bootstrap',
      pipelineParams: { batch_size: 10080, close_sigma: 0.001, high_sigma: 0.0001, low_sigma: 0.0001 },
      fastMode: true,
    },
    running: false, showConfig: false, error: '', errorTrace: '',
    alertMessage: '', alertType: 'success', currentTaskId: null,
    tradesProgress: { current: 0, total: 0, eta: 0 },
    candlesProgress: { current: 0, total: 0, eta: 0 },
    generalInfo: null,
    tradesSummaryMetrics: [], candlesSummaryMetrics: [],
    equityCurveData: null, equityCurveType: 'trades',
    selectedSession: null, openTabs: [], tabCache: {},
    activeResultTab: 'results',
  }
}

function addWorkspace() {
  if (running.value) return
  wsCounter++
  const id = `ws-${wsCounter}`
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  workspaceTabs.value.push({ id, label: `Monte Carlo ${wsCounter}`, running: false, hasResults: false })
  activeWorkspaceId.value = id
  _restoreWs(_freshDefaults())
}

function switchWorkspace(id) {
  if (id === activeWorkspaceId.value || running.value) return
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  activeWorkspaceId.value = id
  const cached = workspaceCache.value[id]
  if (cached) { _restoreWs(cached); delete workspaceCache.value[id] }
  else _restoreWs(_freshDefaults())
}

function closeWorkspace(id) {
  if (workspaceTabs.value.length <= 1 || running.value) return
  const wasActive = id === activeWorkspaceId.value
  workspaceTabs.value = workspaceTabs.value.filter(t => t.id !== id)
  delete workspaceCache.value[id]
  if (wasActive) {
    const last = workspaceTabs.value[workspaceTabs.value.length - 1]
    activeWorkspaceId.value = last.id
    const cached = workspaceCache.value[last.id]
    if (cached) { _restoreWs(cached); delete workspaceCache.value[last.id] }
  }
}

function _updateActiveWsTab(props) {
  const tab = workspaceTabs.value.find(t => t.id === activeWorkspaceId.value)
  if (tab) Object.assign(tab, props)
}

// WebSocket handler
useWebSocket((msg) => {
  const { event, data } = msg

  if (event === 'monte-carlo.trades_progressbar') {
    tradesProgress.value = {
      current: data?.current || 0,
      total: data?.total || form.value.numScenarios,
      eta: data?.estimated_remaining_seconds || 0,
    }
    if (currentTaskId.value) pm.update(currentTaskId.value, { progress: overallProgress.value, eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'monte-carlo.candles_progressbar') {
    candlesProgress.value = {
      current: data?.current || 0,
      total: data?.total || form.value.numScenarios,
      eta: data?.estimated_remaining_seconds || 0,
    }
    if (currentTaskId.value) pm.update(currentTaskId.value, { progress: overallProgress.value, eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'monte-carlo.general_info') {
    generalInfo.value = data
  } else if (event === 'monte-carlo.monte_carlo_trades_summary') {
    tradesSummaryMetrics.value = data || []
  } else if (event === 'monte-carlo.monte_carlo_candles_summary') {
    candlesSummaryMetrics.value = data || []
  } else if (event === 'monte-carlo.alert') {
    alertMessage.value = data?.message || ''
    alertType.value = data?.type || 'success'
    if (data?.type === 'success') {
      running.value = false
      showConfig.value = false
      stopPolling()
      pm.complete(currentTaskId.value)
      _updateActiveWsTab({ running: false, hasResults: true })
      setTimeout(loadSessions, 1000)
    }
  } else if (event === 'monte-carlo.exception') {
    error.value = data?.error || 'Monte Carlo simulation failed'
    errorTrace.value = data?.traceback || ''
    running.value = false
    showConfig.value = false
    stopPolling()
    pm.fail(currentTaskId.value)
    _updateActiveWsTab({ running: false })
  } else if (event === 'monte-carlo.termination') {
    running.value = false
    showConfig.value = false
    stopPolling()
    alertMessage.value = 'Monte Carlo simulation was terminated.'
    alertType.value = 'warning'
    pm.cancel(currentTaskId.value)
    _updateActiveWsTab({ running: false })
  } else if (event === 'monte-carlo.unexpectedTermination') {
    running.value = false
    showConfig.value = false
    stopPolling()
    error.value = data?.message || 'Simulation terminated unexpectedly'
    pm.fail(currentTaskId.value)
    _updateActiveWsTab({ running: false })
  }
})

function statusBadgeClass(status) {
  if (status === 'finished') return 'bg-green-500/20 text-green-400'
  if (status === 'running') return 'bg-yellow-500/20 text-yellow-400'
  if (status === 'stopped' || status === 'terminated' || status === 'failed') return 'bg-red-500/20 text-red-400'
  return 'bg-surface-700 text-surface-400'
}

function formatNum(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toLocaleString()
    return val.toFixed(2)
  }
  return val
}

function formatMetricName(key) {
  const names = {
    total_return: 'Total Return',
    net_profit_percentage: 'Net Profit %',
    max_drawdown: 'Max Drawdown',
    sharpe_ratio: 'Sharpe Ratio',
    calmar_ratio: 'Calmar Ratio',
    sortino_ratio: 'Sortino Ratio',
    win_rate: 'Win Rate',
    total: 'Total Trades',
    annual_return: 'Annual Return',
  }
  return names[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatPipelineName(type) {
  const names = {
    moving_block_bootstrap: 'Moving Block Bootstrap',
    gaussian: 'Gaussian Noise',
  }
  return names[type] || type || '-'
}

function formatDateTime(d) {
  if (!d) return ''
  try {
    const date = typeof d === 'number' ? new Date(d) : new Date(d)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch { return d }
}

function formatEta(seconds) {
  if (!seconds || seconds <= 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

function sessionStrategy(s) {
  if (s.state?.form?.strategy) return s.state.form.strategy
  if (s.title) return s.title
  return s.id?.slice(0, 8) || '-'
}

function sessionExchange(s) {
  if (s.state?.form?.exchange) return s.state.form.exchange
  return ''
}

function startNewSession() {
  selectedSession.value = null
  equityCurveData.value = null
}

function buildState() {
  return { form: { ...form.value } }
}

async function startMonteCarlo() {
  _updateActiveWsTab({ label: `${form.value.strategy} ${form.value.symbol}`, running: true, hasResults: false })
  error.value = ''
  errorTrace.value = ''
  alertMessage.value = ''
  tradesSummaryMetrics.value = []
  candlesSummaryMetrics.value = []
  generalInfo.value = null
  tradesProgress.value = { current: 0, total: form.value.numScenarios, eta: 0 }
  candlesProgress.value = { current: 0, total: form.value.numScenarios, eta: 0 }
  equityCurveData.value = null
  selectedSession.value = null
  running.value = true
  runStartedAt.value = Date.now()
  showConfig.value = false

  const id = crypto.randomUUID()
  currentTaskId.value = id

  const mcLabel = `Monte Carlo · ${form.value.strategy} · ${form.value.symbol}`
  pm.register(id, { type: 'monte-carlo', label: mcLabel, cancelFn: cancelMonteCarlo, routePath: '/monte-carlo' })

  try {
    startPolling()
    await api.runMonteCarlo({
      id,
      exchange: form.value.exchange,
      routes: [{
        exchange: form.value.exchange,
        symbol: form.value.symbol,
        timeframe: form.value.timeframe,
        strategy: form.value.strategy,
      }],
      data_routes: [],
      config: {
        starting_balance: form.value.balance,
        warm_up_candles: 210,
        logging: { order_submission: true, order_cancellation: true, order_execution: true, position_opened: true, position_increased: true, position_reduced: true, position_closed: true, shorter_period_candles: false, trading_candles: false, balance_update: true },
        exchange: {
          type: '',
          fee: 0,
        },
        exchanges: {
          [form.value.exchange]: {
            name: form.value.exchange,
            type: '',
            fee: 0,
            balance: form.value.balance,
          }
        },
      },
      start_date: form.value.startDate,
      finish_date: form.value.finishDate,
      run_trades: form.value.runTrades,
      run_candles: form.value.runCandles,
      num_scenarios: form.value.numScenarios,
      fast_mode: form.value.fastMode,
      cpu_cores: form.value.cpuCores,
      pipeline_type: form.value.pipelineType,
      pipeline_params: form.value.runCandles ? {
        batch_size: form.value.pipelineParams.batch_size,
        ...(form.value.pipelineType === 'gaussian' ? {
          close_sigma: form.value.pipelineParams.close_sigma,
          high_sigma: form.value.pipelineParams.high_sigma,
          low_sigma: form.value.pipelineParams.low_sigma,
        } : {})
      } : {},
      risk_config: {
        bust_threshold: form.value.bustThreshold,
        ruin_threshold: form.value.ruinThreshold,
      },
      state: buildState(),
    })
  } catch (e) {
    error.value = e.message
    running.value = false
    pm.fail(id)
  }
}

async function cancelMonteCarlo() {
  if (!currentTaskId.value) return
  try {
    await api.terminateMonteCarlo(currentTaskId.value)
    alertMessage.value = 'Termination requested...'
    alertType.value = 'warning'
  } catch (e) {
    error.value = e.message
  }
  stopPolling()
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollSessionProgress, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollSessionProgress() {
  if (!currentTaskId.value || !running.value) {
    stopPolling()
    return
  }
  try {
    const res = await api.getMonteCarloSession(currentTaskId.value)
    const session = res.session
    if (!session) return

    // Update progress from child sessions
    if (session.trades_session) {
      const ts = session.trades_session
      const dbVal = ts.completed_scenarios || 0
      if (dbVal > tradesProgress.value.current) {
        tradesProgress.value = {
          current: dbVal,
          total: ts.num_scenarios || form.value.numScenarios,
          eta: tradesProgress.value.eta,
        }
      }
      if (ts.summary_metrics?.length) {
        tradesSummaryMetrics.value = ts.summary_metrics
      }
    }
    if (session.candles_session) {
      const cs = session.candles_session
      const dbVal = cs.completed_scenarios || 0
      // Only update if DB value is higher (don't overwrite WebSocket live data)
      if (dbVal > candlesProgress.value.current) {
        candlesProgress.value = {
          current: dbVal,
          total: cs.num_scenarios || form.value.numScenarios,
          eta: candlesProgress.value.eta,
        }
      }
      if (cs.summary_metrics?.length) {
        candlesSummaryMetrics.value = cs.summary_metrics
      }
    }

    // Detect completion
    if (session.status === 'finished') {
      running.value = false
      showConfig.value = false
      stopPolling()
      pm.complete(currentTaskId.value)
      if (!alertMessage.value) {
        alertMessage.value = 'Monte Carlo simulation completed successfully!'
        alertType.value = 'success'
      }
      loadSessions()
    } else if (session.status === 'terminated' || session.status === 'stopped' || session.status === 'failed') {
      running.value = false
      showConfig.value = false
      stopPolling()
      pm.fail(currentTaskId.value)
      if (!alertMessage.value && !error.value) {
        alertMessage.value = `Monte Carlo simulation ${session.status}.`
        alertType.value = 'warning'
      }
      loadSessions()
    }
  } catch {
    // Ignore poll errors
  }
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await api.getMonteCarloSessions({ limit: 50 })
    sessions.value = res.sessions || []
  } catch {
    sessions.value = []
  } finally {
    loadingSessions.value = false
  }
}

async function viewSession(s) {
  // Only clear equity data if switching to a different session
  if (selectedSession.value?.id !== s.id) {
    equityCurveData.value = null
  }
  if (!openTabs.value.find(t => t.id === s.id)) {
    const label = sessionStrategy(s) || s.id?.slice(0, 8)
    openTabs.value.push({ id: s.id, label })
  }
  if (selectedSession.value && selectedSession.value.id !== s.id) {
    tabCache.value[selectedSession.value.id] = selectedSession.value
  }
  if (tabCache.value[s.id]) {
    selectedSession.value = tabCache.value[s.id]
  } else {
    try {
      const res = await api.getMonteCarloSession(s.id)
      selectedSession.value = res.session || s
      tabCache.value[s.id] = selectedSession.value
    } catch {
      selectedSession.value = s
    }
  }
  // Auto-load equity curves for finished sessions
  if (selectedSession.value?.status === 'finished') {
    loadEquityCurves(s.id)
  }
}

async function viewResultsFromRun() {
  if (!currentTaskId.value) return
  await viewSession({ id: currentTaskId.value })
  activeResultTab.value = 'results'
}

async function viewSessionFromHistory(s) {
  await viewSession(s)
  activeResultTab.value = 'results'
  logsContent.value = ''
  pageTab.value = 'run'
}

function switchToTab(id) {
  const s = tabCache.value[id] || sessions.value.find(x => x.id === id)
  if (s) viewSession(s)
}

function closeTab(id) {
  openTabs.value = openTabs.value.filter(t => t.id !== id)
  delete tabCache.value[id]
  if (selectedSession.value?.id === id) {
    equityCurveData.value = null
    if (openTabs.value.length > 0) {
      switchToTab(openTabs.value[openTabs.value.length - 1].id)
    } else {
      selectedSession.value = null
    }
  }
}

async function removeSession(s) {
  try {
    await api.removeMonteCarloSession(s.id)
    closeTab(s.id)
    loadSessions()
  } catch (e) {
    error.value = e.message
  }
}

async function loadEquityCurves(sessionId) {
  try {
    const res = await api.getMonteCarloEquityCurves(sessionId)
    equityCurveData.value = res
    if (res.trades) {
      equityCurveType.value = 'trades'
    } else if (res.candles) {
      equityCurveType.value = 'candles'
    }
  } catch (e) {
    error.value = e.message
  }
}

async function loadLogsInline(sessionId) {
  if (!sessionId) return
  logsLoading.value = true
  logsContent.value = ''
  try {
    const res = await api.getMonteCarloLogs(sessionId)
    logsContent.value = res.logs || ''
  } catch {
    logsContent.value = ''
  } finally {
    logsLoading.value = false
  }
}

async function purge() {
  try {
    await api.purgeMonteCarloSessions(purgeDays.value)
    showPurgeConfirm.value = false
    loadSessions()
    alertMessage.value = 'Sessions purged successfully'
    alertType.value = 'success'
    setTimeout(() => { if (alertMessage.value === 'Sessions purged successfully') alertMessage.value = '' }, 3000)
  } catch (e) {
    error.value = e.message
  }
}

async function loadExistingCandles() {
  try {
    const res = await api.getExistingCandles({})
    existingCandles.value = res.data || []
  } catch {
    existingCandles.value = []
  }
}

async function checkRunningSession() {
  try {
    const res = await api.getRunningMonteCarloSession()
    if (res.session_id) {
      currentTaskId.value = res.session_id

      // Load session details to restore form state and progress
      try {
        const detail = await api.getMonteCarloSession(res.session_id)
        const session = detail.session
        if (session) {
          // Restore form from saved state
          if (session.state?.form) {
            const f = session.state.form
            if (f.exchange) form.value.exchange = f.exchange
            if (f.symbol) form.value.symbol = f.symbol
            if (f.timeframe) form.value.timeframe = f.timeframe
            if (f.strategy) form.value.strategy = f.strategy
            if (f.startDate) form.value.startDate = f.startDate
            if (f.finishDate) form.value.finishDate = f.finishDate
            if (f.balance) form.value.balance = f.balance
            if (f.numScenarios) form.value.numScenarios = f.numScenarios
            if (f.cpuCores) form.value.cpuCores = f.cpuCores
            if (f.runTrades !== undefined) form.value.runTrades = f.runTrades
            if (f.runCandles !== undefined) form.value.runCandles = f.runCandles
            if (f.pipelineType) form.value.pipelineType = f.pipelineType
            if (f.fastMode !== undefined) form.value.fastMode = f.fastMode
          }

          // Restore progress from child sessions
          if (session.trades_session) {
            tradesProgress.value = {
              current: session.trades_session.completed_scenarios || 0,
              total: session.trades_session.num_scenarios || form.value.numScenarios,
              eta: 0,
            }
            if (session.trades_session.summary_metrics?.length) {
              tradesSummaryMetrics.value = session.trades_session.summary_metrics
            }
          }
          if (session.candles_session) {
            candlesProgress.value = {
              current: session.candles_session.completed_scenarios || 0,
              total: session.candles_session.num_scenarios || form.value.numScenarios,
              eta: 0,
            }
            if (session.candles_session.summary_metrics?.length) {
              candlesSummaryMetrics.value = session.candles_session.summary_metrics
            }
          }
        }
      } catch { /* proceed with defaults */ }

      running.value = true
      startPolling()
      const resumeLabel = `Monte Carlo · ${form.value.strategy} · ${form.value.symbol}`
      if (!pm.get(currentTaskId.value)) pm.register(currentTaskId.value, { type: 'monte-carlo', label: resumeLabel, cancelFn: cancelMonteCarlo, routePath: '/monte-carlo' })
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  try {
    const [bRes, sRes, sysRes] = await Promise.all([
      api.getBacktestingBrokers(),
      api.getStrategies().catch(() => ({ data: [] })),
      api.getGeneralInfo().catch(() => ({})),
    ])
    brokers.value = bRes.data || []
    strategies.value = sRes.data || sRes.strategies || []
    if (sysRes.cpu_cores) maxCpuCores.value = sysRes.cpu_cores
    form.value.exchange = defaultBrokerId(brokers.value)
    if (strategies.value.length > 0) form.value.strategy = strategies.value[0].name
    form.value.cpuCores = Math.max(1, Math.min(form.value.cpuCores, maxCpuCores.value))
  } catch (e) {
    console.error(e)
  }

  await loadExistingCandles()
  onExchangeChange()
  await loadSessions()
  await checkRunningSession()

  // Handle ?session=<id> query param (from process manager "view results")
  const qSession = currentRoute.query.session
  if (qSession && !running.value) {
    const s = sessions.value.find(x => x.id === qSession)
    if (s) {
      await viewSessionFromHistory(s)
    }
  }
})

onBeforeUnmount(() => {
  stopPolling()
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
})
</script>
