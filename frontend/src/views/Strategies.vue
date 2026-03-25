<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
      <h1 class="text-2xl font-bold text-center sm:text-left">Strategies</h1>
      <div class="flex items-center gap-3 overflow-x-auto">
        <!-- Editor Tabs in header -->
        <div v-if="openEditorTabs.length" class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg shrink-0">
          <div v-for="tab in openEditorTabs" :key="tab.name"
            @click="switchEditorTab(tab.name)"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer group rounded-md transition-colors"
            :class="tab.name === editingStrat ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="tab.modified ? 'bg-yellow-400' : 'bg-surface-600'"></span>
            <span class="truncate max-w-[140px]">{{ tab.name }}</span>
            <button @click.stop="closeEditorTab(tab.name)"
              class="text-surface-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">&times;</button>
          </div>
          <button @click="editingStrat = null" title="Open another strategy"
            class="w-6 h-6 flex items-center justify-center text-surface-500 hover:text-brand-400 rounded text-sm transition-colors">+</button>
        </div>
        <div class="flex gap-2">
          <button @click="showAIPanel = !showAIPanel" class="btn-sm" :class="showAIPanel ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
            AI Generate
          </button>
          <button @click="showCreate = true" class="btn-primary btn-sm">New Strategy</button>
        </div>
      </div>
    </div>

    <!-- AI Generate Panel -->
    <div v-if="showAIPanel" class="card mb-5">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-sm font-semibold text-surface-300">AI Strategy Generator</h2>
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="llmConfigured ? 'bg-green-400' : 'bg-red-400'"></span>
          <span class="text-xs text-surface-500">{{ llmConfigured ? 'LLM Connected' : 'LLM Not Configured' }}</span>
        </div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 space-y-3">
          <div>
            <label class="label">Describe your strategy</label>
            <textarea v-model="aiForm.description" class="input min-h-[80px] resize-y"
              placeholder="e.g. Buy EUR-USD when 20 EMA crosses above 50 EMA during London session, risk 1% per trade with 2:1 RR"></textarea>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div><label class="label">Name</label><input v-model="aiForm.name" class="input" placeholder="Auto" /></div>
            <div><label class="label">Asset Class</label>
              <select v-model="aiForm.asset_class" class="select">
                <option value="forex">Forex</option><option value="commodity">Commodity</option>
                <option value="index">Index</option><option value="crypto">Crypto</option>
              </select>
            </div>
            <div><label class="label">Symbol</label><input v-model="aiForm.symbol" class="input" placeholder="EUR-USD" /></div>
          </div>
          <div class="flex items-center gap-3">
            <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
              <input v-model="aiForm.save" type="checkbox" class="rounded bg-surface-700 border-surface-500" /> Save to disk
            </label>
            <button @click="aiGenerate" class="btn-primary btn-sm" :disabled="aiGenerating || !aiForm.description || !llmConfigured">
              <span v-if="aiGenerating" class="flex items-center gap-1"><svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Generating...</span>
              <span v-else>Generate</span>
            </button>
          </div>
          <p v-if="aiError" class="text-xs text-red-400">{{ aiError }}</p>
          <p v-if="aiSuccess" class="text-xs text-green-400">{{ aiSuccess }}</p>
        </div>
        <div>
          <label class="label">Preview</label>
          <pre v-if="aiCode" class="bg-surface-900 rounded-lg p-3 text-xs font-mono text-surface-300 max-h-[200px] overflow-auto whitespace-pre-wrap">{{ aiCode }}</pre>
          <div v-else class="bg-surface-900 rounded-lg p-3 text-xs text-surface-600 text-center h-[200px] flex items-center justify-center">Generated code appears here</div>
        </div>
      </div>
    </div>

    <!-- Create Strategy Modal -->
    <div v-if="showCreate" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="showCreate = false">
      <div class="card w-full max-w-sm mx-4">
        <h2 class="text-base font-semibold mb-4">New Strategy</h2>
        <div class="space-y-3">
          <div><label class="label">Strategy Name</label><input v-model="newName" class="input" placeholder="MyStrategy" /></div>
          <div class="flex gap-2">
            <button @click="createStrategy" class="btn-primary flex-1" :disabled="!newName">Create</button>
            <button @click="showCreate = false" class="btn-secondary">Cancel</button>
          </div>
          <p v-if="createError" class="text-xs text-red-400">{{ createError }}</p>
        </div>
      </div>
    </div>

    <!-- Strategy List -->
    <div v-if="loading" class="text-surface-500 text-sm">Loading strategies...</div>
    <div v-else-if="strategies.length === 0 && !playgroundActive && !editingStrat" class="card text-center py-12">
      <p class="text-surface-500">No strategies found. Create one or use AI to generate.</p>
    </div>
    <div v-else-if="!playgroundActive && !editingStrat" class="space-y-2">
      <p v-if="openEditorTabs.length" class="text-xs text-surface-500 mb-1">Select a strategy to open in a new tab:</p>
      <div v-for="strat in strategies" :key="strat"
        class="card flex items-center justify-between py-3 hover:border-surface-600 transition-colors cursor-pointer"
        @click="selectStrategy(strat)">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-surface-800 flex items-center justify-center text-brand-400 text-xs font-mono font-bold">{{ strat.slice(0, 2) }}</div>
          <div class="text-sm font-medium text-surface-100">{{ strat }}</div>
        </div>
        <div class="flex items-center gap-2">
          <button @click.stop="openPlayground(strat)" class="text-xs text-emerald-400 hover:text-emerald-300">Playground</button>
          <button @click.stop="editStrategy(strat)" class="text-xs text-brand-400 hover:text-brand-300">Edit</button>
          <button @click.stop="confirmDelete(strat)" class="text-xs text-red-400 hover:text-red-300">Delete</button>
        </div>
      </div>
    </div>

    <!-- ═══════════════ PLAYGROUND MODE ═══════════════ -->
    <div v-if="playgroundActive" class="space-y-4">
      <div class="flex items-center gap-3">
        <button @click="closePlayground" class="btn-sm bg-surface-800 text-surface-400 hover:text-surface-200">
          <svg class="w-4 h-4 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"/></svg>
          Back
        </button>
        <h2 class="text-lg font-semibold text-surface-100">Playground: {{ playgroundStrategy }}</h2>
        <button @click="editStrategy(playgroundStrategy)" class="btn-sm bg-surface-800 text-brand-400 hover:text-brand-300 ml-auto">Edit Code</button>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Left: Config Panel -->
        <div class="lg:col-span-1 space-y-4">
          <div class="card">
            <h2 class="text-sm font-semibold mb-4 text-surface-300">Scenario</h2>
            <div class="space-y-3">
              <div>
                <label class="label">Market Scenario</label>
                <select v-model="pgForm.scenario" class="select" @change="onScenarioChange">
                  <option v-for="s in scenarios" :key="s.id" :value="s.id">{{ s.name }}</option>
                </select>
                <p class="text-xs text-surface-500 mt-1">{{ currentScenarioDesc }}</p>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div><label class="label">Duration</label>
                  <select v-model.number="pgForm.duration_minutes" class="select">
                    <option :value="60">1 Hour</option><option :value="120">2 Hours</option><option :value="180">3 Hours</option>
                    <option :value="360">6 Hours</option><option :value="480">8 Hours</option><option :value="720">12 Hours</option>
                    <option :value="1440">24 Hours</option><option :value="4320">3 Days</option><option :value="10080">1 Week</option>
                  </select>
                </div>
                <div><label class="label">Start Price</label><input v-model.number="pgForm.start_price" type="number" step="0.0001" class="input" /></div>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div><label class="label">Volatility</label><input v-model.number="pgForm.volatility" type="number" step="0.00001" class="input" /></div>
                <div><label class="label">Trend Strength</label><input v-model.number="pgForm.trend_strength" type="number" step="0.00001" class="input" /></div>
              </div>
              <div><label class="label">Seed <span class="text-surface-600">(empty = random)</span></label><input v-model.number="pgForm.seed" type="number" class="input" placeholder="Random" /></div>
              <button @click="previewScenario" class="btn-secondary w-full text-sm" :disabled="pgPreviewing">{{ pgPreviewing ? 'Generating...' : 'Preview Scenario' }}</button>
            </div>
          </div>

          <div class="card">
            <h2 class="text-sm font-semibold mb-4 text-surface-300">Simulation</h2>
            <div class="space-y-3">
              <div class="grid grid-cols-2 gap-3">
                <div><label class="label">Timeframe</label>
                  <select v-model="pgForm.timeframe" class="select">
                    <option v-for="tf in pgTimeframes" :key="tf.value" :value="tf.value">{{ tf.label }}</option>
                  </select>
                </div>
                <div><label class="label">Symbol</label><input v-model="pgForm.symbol" class="input" placeholder="EUR-USD" /></div>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div><label class="label">Balance</label><input v-model.number="pgForm.balance" type="number" class="input" /></div>
                <div><label class="label">Leverage</label><input v-model.number="pgForm.leverage" type="number" class="input" min="1" /></div>
              </div>
              <div><label class="label">Warm-up Candles</label><input v-model.number="pgForm.warm_up_candles" type="number" class="input" min="0" /></div>

              <!-- Hyperparameters (auto-loaded from strategy) -->
              <div v-if="pgHyperParams.length">
                <div class="flex items-center justify-between mb-2">
                  <label class="label mb-0">Hyperparameters</label>
                  <button @click="resetHyperParams" class="text-xs text-surface-500 hover:text-surface-300">Reset Defaults</button>
                </div>
                <div v-for="(hp, idx) in pgHyperParams" :key="idx" class="mb-2">
                  <div class="flex gap-2 items-center">
                    <span class="text-xs text-surface-400 w-28 truncate" :title="hp.description || hp.name">{{ hp.name }}</span>
                    <select v-if="hp.type === 'str' && hp.options" v-model="hp.value" class="select text-xs py-1.5 flex-1">
                      <option v-for="opt in hp.options" :key="opt" :value="opt">{{ opt }}</option>
                    </select>
                    <input v-else-if="hp.type === 'str'" v-model="hp.value" class="input text-xs py-1.5 flex-1" />
                    <input v-else v-model.number="hp.value" type="number" :step="hp.type === 'int' ? 1 : 'any'"
                      :min="hp.min" :max="hp.max" class="input text-xs py-1.5 flex-1" />
                    <span v-if="hp.min !== undefined" class="text-[10px] text-surface-600 whitespace-nowrap">{{ hp.min }}-{{ hp.max }}</span>
                  </div>
                  <div v-if="hp.description" class="text-[10px] text-surface-600 ml-[7.5rem] mt-0.5">{{ hp.description }}</div>
                </div>
              </div>
              <div v-else>
                <div class="flex items-center justify-between mb-1">
                  <label class="label mb-0">Hyperparameters <span class="text-surface-600">(optional)</span></label>
                  <button @click="pgCustomHPs.push({ key: '', value: '' })" class="text-xs text-brand-400 hover:text-brand-300">+ Add</button>
                </div>
                <div v-for="(hp, idx) in pgCustomHPs" :key="idx" class="flex gap-2 mb-2 items-center">
                  <input v-model="hp.key" class="input text-xs py-1.5 flex-1" placeholder="param name" />
                  <input v-model="hp.value" class="input text-xs py-1.5 w-24" placeholder="value" type="number" step="any" />
                  <button @click="pgCustomHPs.splice(idx, 1)" class="text-surface-500 hover:text-red-400 text-lg">&times;</button>
                </div>
              </div>

              <button @click="runSimulation" class="btn-primary w-full" :disabled="pgRunning">
                <span v-if="pgRunning" class="flex items-center justify-center gap-2">
                  <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                  Running...
                </span>
                <span v-else>Run Simulation</span>
              </button>
              <button v-if="pgRunning" @click="cancelSim" class="btn-secondary w-full text-sm">Cancel</button>
            </div>
          </div>

          <ProgressBar :visible="pgRunning" :percent="pgProgress.current" :eta="pgProgress.eta" label="Simulating" />
        </div>

        <!-- Right: Charts + Results -->
        <div class="lg:col-span-2 space-y-4">
          <div v-if="pgError" class="card border-red-500/30">
            <div class="flex items-center justify-between mb-1">
              <span class="text-red-400 font-semibold text-sm">Error</span>
              <button @click="pgError = ''; pgErrorTrace = ''" class="text-surface-500 text-xs">Dismiss</button>
            </div>
            <p class="text-red-400 text-sm">{{ pgError }}</p>
            <pre v-if="pgErrorTrace" class="text-xs text-red-300/70 mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap">{{ pgErrorTrace }}</pre>
          </div>

          <div v-if="pgSuccessMsg" class="card border-green-500/30">
            <p class="text-green-400 text-sm">{{ pgSuccessMsg }}</p>
          </div>

          <!-- Interactive TradingView Chart -->
          <TradeChart
            v-show="pgShowChart"
            ref="tradeChartRef"
            :candles="pgChartCandles"
            :raw-candles="pgChartRawCandles"
            :route-timeframe="pgForm.timeframe"
            :orders="pgChartOrders"
            :trades="pgTrades"
            :equity-curve="pgEquityCurve"
            :balance="pgForm.balance"
          />

          <!-- Results -->
          <div v-if="pgHasResults" class="card">
            <div class="flex items-center gap-1 border-b border-surface-700 mb-4 -mt-1 overflow-x-auto">
              <button v-for="tab in pgResultTabs" :key="tab.id" @click="pgActiveTab = tab.id"
                class="px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors"
                :class="pgActiveTab === tab.id ? 'border-brand-500 text-brand-400' : 'border-transparent text-surface-500 hover:text-surface-300'">
                {{ tab.label }}
                <span v-if="tab.count !== undefined" class="ml-1 text-surface-600">({{ tab.count }})</span>
              </button>
            </div>

            <!-- Summary -->
            <div v-if="pgActiveTab === 'summary'">
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Performance</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in pgPerformanceMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">{{ m.label }}</div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Trade Statistics</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in pgTradeStatsMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">{{ m.label }}</div>
                    <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div>
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Risk & Ratios</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in pgRiskMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">{{ m.label }}</div>
                    <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div v-if="pgResultHyperparams && pgResultHyperparams.length" class="mt-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Hyperparameters Used</h3>
                <div class="flex flex-wrap gap-2">
                  <div v-for="hp in pgResultHyperparams" :key="hp.name" class="px-3 py-1.5 bg-surface-800 rounded-lg text-xs">
                    <span class="text-surface-500">{{ hp.name }}:</span>
                    <span class="text-surface-200 font-mono ml-1">{{ hp.value }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Sessions (hedge strategy grouping) -->
            <div v-if="pgActiveTab === 'sessions'">
              <div v-if="!pgSessions.length" class="text-surface-500 text-sm text-center py-6">No sessions recorded</div>
              <div v-else>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
                  <div class="p-2 bg-surface-800 rounded"><div class="text-surface-500 text-xs">Total</div><div class="font-mono text-surface-100">{{ pgSessions.length }}</div></div>
                  <div class="p-2 bg-surface-800 rounded"><div class="text-surface-500 text-xs">TP Hit</div><div class="font-mono text-green-400">{{ pgSessions.filter(s => s.outcome === 'tp_hit').length }}</div></div>
                  <div class="p-2 bg-surface-800 rounded"><div class="text-surface-500 text-xs">Max Levels</div><div class="font-mono text-red-400">{{ pgSessions.filter(s => s.outcome === 'max_levels').length }}</div></div>
                  <div class="p-2 bg-surface-800 rounded"><div class="text-surface-500 text-xs">Total PnL</div><div class="font-mono" :class="pgSessions.reduce((a,s) => a+s.total_pnl, 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ pgSessions.reduce((a,s) => a+s.total_pnl, 0).toFixed(2) }}</div></div>
                </div>
                <div class="space-y-2">
                  <div v-for="s in pgSessions" :key="s.session" class="bg-surface-800 rounded overflow-hidden">
                    <div @click="_togglePgSession(s.session)" class="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-surface-700/50 transition-colors">
                      <div class="flex items-center gap-3">
                        <span class="text-xs font-mono font-bold text-brand-400">S{{ s.session }}</span>
                        <span class="text-xs text-surface-400">{{ s.trade_count }} trade{{ s.trade_count !== 1 ? 's' : '' }}</span>
                        <span class="text-xs" :class="_sessionOutcomeClass(s.outcome)">{{ _sessionOutcomeLabel(s.outcome) }}</span>
                        <span v-if="s.levels > 0" class="text-[10px] text-surface-500 font-mono">L{{ s.levels }}</span>
                      </div>
                      <div class="flex items-center gap-3">
                        <span class="text-xs font-mono" :class="s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ s.total_pnl >= 0 ? '+' : '' }}{{ s.total_pnl.toFixed(2) }}</span>
                        <svg class="w-3 h-3 text-surface-500 transition-transform" :class="{ 'rotate-180': pgExpandedSessions[s.session] }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                      </div>
                    </div>
                    <div v-if="pgExpandedSessions[s.session]" class="border-t border-surface-700">
                      <table class="w-full text-xs">
                        <thead><tr class="text-surface-500 border-b border-surface-700"><th class="text-left py-1.5 px-3">Label</th><th class="text-left py-1.5 px-2">Type</th><th class="text-right py-1.5 px-2">Entry</th><th class="text-right py-1.5 px-2">Exit</th><th class="text-right py-1.5 px-2">Qty</th><th class="text-right py-1.5 px-2">PnL</th><th class="text-left py-1.5 px-2">Exit</th></tr></thead>
                        <tbody>
                          <tr v-for="(t, i) in s.trades" :key="i" class="border-b border-surface-800/30 hover:bg-surface-700/30">
                            <td class="py-1.5 px-3 font-mono font-bold" :class="t.meta?.exit_reason === 'tp_hit' ? 'text-green-400' : 'text-surface-300'">{{ t.meta?.label || `O${i+1}` }}</td>
                            <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                            <td class="py-1.5 px-2 text-right font-mono">{{ formatPrice(t.entry_price) }}</td>
                            <td class="py-1.5 px-2 text-right font-mono">{{ formatPrice(t.exit_price) }}</td>
                            <td class="py-1.5 px-2 text-right font-mono">{{ t.qty }}</td>
                            <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMoney(t.pnl) }}</td>
                            <td class="py-1.5 px-2" :class="_sessionOutcomeClass(t.meta?.exit_reason)">{{ t.meta?.exit_reason === 'tp_hit' ? 'TP' : t.meta?.exit_reason === 'sl_hit' ? 'SL' : '-' }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Trades -->
            <div v-if="pgActiveTab === 'trades'">
              <div v-if="!pgTrades.length" class="text-surface-500 text-sm text-center py-6">No trades executed</div>
              <div v-else class="overflow-x-auto">
                <table class="w-full text-xs">
                  <thead>
                    <tr class="text-left text-surface-500">
                      <th class="p-2">#</th>
                      <th v-if="pgSessions.length" class="p-2">Session</th>
                      <th class="p-2">Type</th><th class="p-2">Entry</th><th class="p-2">Exit</th>
                      <th class="p-2">Qty</th><th class="p-2">PnL</th><th class="p-2">PnL %</th><th class="p-2">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(t, i) in pgPagedTrades" :key="i" class="border-t border-surface-800">
                      <td class="p-2 text-surface-500">{{ (pgTradesPage - 1) * 25 + i + 1 }}</td>
                      <td v-if="pgSessions.length" class="p-2 font-mono text-brand-400">{{ t.meta?.label || '-' }}</td>
                      <td class="p-2"><span class="px-1.5 py-0.5 rounded text-[10px] font-medium" :class="t.type === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'">{{ t.type }}</span></td>
                      <td class="p-2 font-mono">{{ formatPrice(t.entry_price) }}</td>
                      <td class="p-2 font-mono">{{ formatPrice(t.exit_price) }}</td>
                      <td class="p-2 font-mono">{{ t.qty }}</td>
                      <td class="p-2 font-mono" :class="(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMoney(t.pnl) }}</td>
                      <td class="p-2 font-mono" :class="(t.pnl_percentage || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ (t.pnl_percentage || 0).toFixed(2) }}%</td>
                      <td class="p-2 text-surface-400">{{ t.holding_period || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-if="pgTotalTradePages > 1" class="flex items-center justify-between mt-3 text-xs text-surface-500">
                  <button @click="pgTradesPage = Math.max(1, pgTradesPage - 1)" :disabled="pgTradesPage <= 1" class="btn-sm bg-surface-700">Prev</button>
                  <span>{{ pgTradesPage }} / {{ pgTotalTradePages }}</span>
                  <button @click="pgTradesPage = Math.min(pgTotalTradePages, pgTradesPage + 1)" :disabled="pgTradesPage >= pgTotalTradePages" class="btn-sm bg-surface-700">Next</button>
                </div>
              </div>
            </div>

            <!-- Logs -->
            <div v-if="pgActiveTab === 'logs'">
              <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                  <span class="text-xs text-surface-500">Simulation Logs</span>
                  <select v-if="pgLogs.length" v-model="pgLogFilter" @change="onPgLogFilterChange" class="select text-xs py-1 w-auto">
                    <option value="all">All</option>
                    <option value="strategy">Strategy</option>
                    <option value="position">Position</option>
                    <option value="order">Order</option>
                    <option value="market">Market</option>
                  </select>
                  <span v-if="pgLogs.length" class="text-xs text-surface-600">({{ pgLogFilter === 'all' ? pgLogs.length : pgLogs.filter(l => l.type === pgLogFilter).length }} entries)</span>
                </div>
                <button v-if="pgLogsFormatted" @click="copyPgLogs" class="btn-sm bg-surface-700 text-surface-300">Copy</button>
              </div>
              <div v-if="pgLogsFormatted" class="bg-surface-900 rounded p-3 max-h-[400px] overflow-auto">
                <pre class="text-xs text-surface-400 whitespace-pre-wrap font-mono">{{ pgLogsFormatted }}</pre>
              </div>
              <div v-else class="text-surface-500 text-sm text-center py-6">No logs recorded. Strategy logs appear here after simulation.</div>
            </div>
          </div>

          <!-- Empty state -->
          <div v-if="!pgShowChart && !pgHasResults && !pgError" class="card text-center py-16">
            <div class="text-surface-600 mb-4">
              <svg class="w-12 h-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-1.47 4.41a2.25 2.25 0 01-2.133 1.59H8.603a2.25 2.25 0 01-2.133-1.59L5 14.5m14 0H5" />
              </svg>
            </div>
            <p class="text-surface-500 text-sm">Select a scenario and click <span class="text-brand-400">Preview Scenario</span> or <span class="text-brand-400">Run Simulation</span></p>
            <p class="text-surface-600 text-xs mt-2">Test {{ playgroundStrategy }} against synthetic market conditions without needing real data</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Inline Editor (active when a tab is selected) -->
    <div v-if="editingStrat && !playgroundActive" class="space-y-3">
      <div class="card flex flex-col" style="min-height: 70vh;">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold">{{ editingStrat }}</h2>
          <div class="flex items-center gap-2">
            <button @click="openPlayground(editingStrat)" class="btn-sm bg-surface-800 text-emerald-400 hover:text-emerald-300">Playground</button>
            <button @click="saveEdit" class="btn-primary btn-sm" :disabled="saving">{{ saving ? 'Saving...' : 'Save' }}</button>
          </div>
        </div>
        <div class="flex gap-2 mb-3">
          <input v-model="refineInput" class="input flex-1 text-xs" placeholder="AI feedback: e.g. Add trailing stop, only trade during high volatility..." />
          <button @click="aiRefine" class="btn-sm bg-brand-600 text-white" :disabled="aiRefining || !refineInput || !llmConfigured">
            <span v-if="aiRefining" class="flex items-center gap-1"><svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Refining...</span>
            <span v-else>AI Refine</span>
          </button>
        </div>
        <textarea v-model="editCode" class="input flex-1 font-mono text-xs resize-none min-h-[500px]"></textarea>
        <p v-if="editMsg" class="text-xs mt-2" :class="editErr ? 'text-red-400' : 'text-green-400'">{{ editMsg }}</p>
      </div>
    </div>

    <!-- Delete Confirm -->
    <div v-if="deletingStrat" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="deletingStrat = null">
      <div class="card w-full max-w-sm mx-4">
        <h2 class="text-base font-semibold mb-3">Delete Strategy</h2>
        <p class="text-sm text-surface-400 mb-4">Are you sure you want to delete <span class="text-surface-100 font-medium">{{ deletingStrat }}</span>?</p>
        <div class="flex gap-2">
          <button @click="doDelete" class="btn-danger flex-1">Delete</button>
          <button @click="deletingStrat = null" class="btn-secondary flex-1">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { api } from '../api'
import { useWebSocket } from '../useWebSocket'
import ProgressBar from '../components/ProgressBar.vue'
import TradeChart from '../components/TradeChart.vue'

// ── Strategy list state ──
const loading = ref(true)
const strategies = ref([])
const showCreate = ref(false)
const showAIPanel = ref(false)
const newName = ref('')
const createError = ref('')
const llmConfigured = ref(false)
const aiForm = ref({ description: '', name: '', asset_class: 'forex', symbol: 'EUR-USD', save: true })
const aiGenerating = ref(false)
const aiCode = ref('')
const aiError = ref('')
const aiSuccess = ref('')
const editingStrat = ref(null)
const editCode = ref('')
const saving = ref(false)
const editMsg = ref('')
const editErr = ref(false)
const refineInput = ref('')
const aiRefining = ref(false)
const deletingStrat = ref(null)

// Editor tabs
const openEditorTabs = ref([])
const editorTabCache = ref({})

// ── Playground state ──
const playgroundActive = ref(false)
const playgroundStrategy = ref('')
const scenarios = ref([])
const pgPreviewing = ref(false)
const pgRunning = ref(false)
const pgError = ref('')
const pgErrorTrace = ref('')
const pgSuccessMsg = ref('')
const pgProgress = ref({ current: 0, eta: 0 })
const pgTaskId = ref(null)
const pgMetrics = ref(null)
const pgEquityCurve = ref([])
const pgTrades = ref([])
const pgSessions = ref([])
const pgExpandedSessions = ref({})
const pgChartData = ref(null)
const pgResultHyperparams = ref(null)
const pgActiveTab = ref('summary')
const pgActiveChartTab = ref('candles')
const pgTradesPage = ref(1)
const pgLogs = ref([])
const pgLogsFormatted = ref(null)
const pgLogFilter = ref('all')
const pgHyperParams = ref([])        // Auto-loaded from strategy code
const pgHyperParamsDefaults = ref([]) // Store defaults for reset
const pgCustomHPs = ref([])           // Manual hyperparams if strategy has none

const tradeChartRef = ref(null)
const pgChartCandles = ref([])
const pgChartRawCandles = ref([])
const pgChartOrders = ref([])

const pgForm = ref({
  scenario: 'ranging',
  duration_minutes: 120,
  start_price: 1.1000,
  volatility: 0.0002,
  trend_strength: 0.00005,
  seed: null,
  timeframe: '1m',
  symbol: 'EUR-USD',
  balance: 10000,
  leverage: 30,
  warm_up_candles: 50,
})

const pgTimeframes = [
  { value: '1m', label: '1m' }, { value: '3m', label: '3m' }, { value: '5m', label: '5m' },
  { value: '15m', label: '15m' }, { value: '30m', label: '30m' }, { value: '45m', label: '45m' },
  { value: '1h', label: '1h' }, { value: '2h', label: '2h' }, { value: '3h', label: '3h' }, { value: '4h', label: '4h' },
]

// ── Computed ──
const currentScenarioDesc = computed(() => { const s = scenarios.value.find(x => x.id === pgForm.value.scenario); return s ? s.description : '' })
const pgHasResults = computed(() => !!pgMetrics.value)
const pgShowChart = ref(false)
const pgResultTabs = computed(() => {
  const tabs = [{ id: 'summary', label: 'Summary' }]
  if (pgSessions.value.length) tabs.push({ id: 'sessions', label: 'Sessions', count: pgSessions.value.length })
  tabs.push({ id: 'trades', label: 'Trades', count: pgTrades.value.length })
  tabs.push({ id: 'logs', label: 'Logs', count: pgLogs.value.length || undefined })
  return tabs
})

const pgPerformanceMetrics = computed(() => {
  if (!pgMetrics.value) return []
  const m = pgMetrics.value
  return [
    { key: 'net_profit', label: 'Net Profit', value: m.net_profit },
    { key: 'net_profit_percentage', label: 'Net Profit %', value: m.net_profit_percentage },
    { key: 'win_rate', label: 'Win Rate', value: m.win_rate },
    { key: 'profit_factor', label: 'Profit Factor', value: m.profit_factor },
    { key: 'total_return', label: 'Total Return %', value: m.total_return },
    { key: 'annual_return', label: 'Annual Return %', value: m.annual_return },
    { key: 'max_drawdown', label: 'Max Drawdown %', value: m.max_drawdown },
    { key: 'expectancy', label: 'Expectancy', value: m.expectancy },
  ].filter(x => x.value !== undefined)
})
const pgTradeStatsMetrics = computed(() => {
  if (!pgMetrics.value) return []
  const m = pgMetrics.value
  return [
    { key: 'total', label: 'Total Trades', value: m.total },
    { key: 'total_winning_trades', label: 'Winning', value: m.total_winning_trades },
    { key: 'total_losing_trades', label: 'Losing', value: m.total_losing_trades },
    { key: 'largest_winning_trade', label: 'Largest Win', value: m.largest_winning_trade },
    { key: 'largest_losing_trade', label: 'Largest Loss', value: m.largest_losing_trade },
    { key: 'average_win', label: 'Avg Win', value: m.average_win },
    { key: 'average_loss', label: 'Avg Loss', value: m.average_loss },
    { key: 'longs_count', label: 'Longs', value: m.longs_count },
    { key: 'shorts_count', label: 'Shorts', value: m.shorts_count },
  ].filter(x => x.value !== undefined)
})
const pgRiskMetrics = computed(() => {
  if (!pgMetrics.value) return []
  const m = pgMetrics.value
  return [
    { key: 'sharpe_ratio', label: 'Sharpe Ratio', value: m.sharpe_ratio },
    { key: 'sortino_ratio', label: 'Sortino Ratio', value: m.sortino_ratio },
    { key: 'calmar_ratio', label: 'Calmar Ratio', value: m.calmar_ratio },
    { key: 'omega_ratio', label: 'Omega Ratio', value: m.omega_ratio },
    { key: 'max_drawdown', label: 'Max Drawdown %', value: m.max_drawdown },
    { key: 'kelly_criterion', label: 'Kelly Criterion', value: m.kelly_criterion },
    { key: 'smart_sharpe', label: 'Smart Sharpe', value: m.smart_sharpe },
    { key: 'smart_sortino', label: 'Smart Sortino', value: m.smart_sortino },
  ].filter(x => x.value !== undefined)
})
const pgPagedTrades = computed(() => { const s = (pgTradesPage.value - 1) * 25; return pgTrades.value.slice(s, s + 25) })
const pgTotalTradePages = computed(() => Math.ceil(pgTrades.value.length / 25))

// ── Strategy list actions ──
async function loadStrategies() {
  try { const res = await api.getStrategies(); strategies.value = res.data || res.strategies || [] }
  catch { strategies.value = [] }
  finally { loading.value = false }
}
async function createStrategy() {
  createError.value = ''
  try {
    await api.makeStrategy(newName.value)
    const name = newName.value
    showCreate.value = false; newName.value = ''
    await loadStrategies()
    editStrategy(name)
  }
  catch (e) { createError.value = e.message }
}
async function selectStrategy(name) { await editStrategy(name) }
async function editStrategy(name) {
  editMsg.value = ''; editErr.value = false
  // Cache current editor before switching
  if (editingStrat.value && editingStrat.value !== name) {
    editorTabCache.value[editingStrat.value] = { code: editCode.value, msg: editMsg.value, err: editErr.value }
  }
  // Add tab if not already open
  if (!openEditorTabs.value.find(t => t.name === name)) {
    openEditorTabs.value.push({ name, modified: false })
  }
  // Restore from cache if available
  const cached = editorTabCache.value[name]
  if (cached) {
    editCode.value = cached.code; editMsg.value = cached.msg; editErr.value = cached.err
    editingStrat.value = name
    delete editorTabCache.value[name]
    return
  }
  try { const res = await api.getStrategy(name); editCode.value = res.data?.content || res.content || ''; editingStrat.value = name }
  catch (e) { editMsg.value = e.message; editErr.value = true }
}

function switchEditorTab(name) {
  if (name === editingStrat.value) return
  editStrategy(name)
}

function closeEditorTab(name) {
  openEditorTabs.value = openEditorTabs.value.filter(t => t.name !== name)
  delete editorTabCache.value[name]
  if (editingStrat.value === name) {
    if (openEditorTabs.value.length > 0) {
      const last = openEditorTabs.value[openEditorTabs.value.length - 1]
      editStrategy(last.name)
    } else {
      editingStrat.value = null; editCode.value = ''
    }
  }
}
async function saveEdit() {
  saving.value = true; editMsg.value = ''
  try { await api.saveStrategy(editingStrat.value, editCode.value); editMsg.value = 'Saved successfully'; editErr.value = false }
  catch (e) { editMsg.value = e.message; editErr.value = true }
  finally { saving.value = false }
}
async function aiGenerate() {
  aiGenerating.value = true; aiError.value = ''; aiSuccess.value = ''
  try {
    const res = await api.aiGenerateStrategy(aiForm.value)
    if (res.status === 'ok' && res.code) { aiCode.value = res.code; aiSuccess.value = res.saved ? `Strategy "${res.name}" saved!` : 'Strategy generated (not saved)'; if (res.saved) await loadStrategies() }
    else { aiError.value = res.errors?.join(', ') || 'Generation failed'; aiCode.value = res.code || '' }
  } catch (e) { aiError.value = e.message }
  finally { aiGenerating.value = false }
}
async function aiRefine() {
  aiRefining.value = true; editMsg.value = ''
  try {
    const res = await api.aiRefineStrategy({ name: editingStrat.value, feedback: refineInput.value })
    if (res.valid && res.code) { editCode.value = res.code; editMsg.value = 'Refined and saved!'; editErr.value = false; refineInput.value = '' }
    else { editMsg.value = res.errors?.join(', ') || 'Refinement failed'; editErr.value = true }
  } catch (e) { editMsg.value = e.message; editErr.value = true }
  finally { aiRefining.value = false }
}
function confirmDelete(name) { deletingStrat.value = name }
async function doDelete() {
  try { await api.deleteStrategy(deletingStrat.value); deletingStrat.value = null; await loadStrategies() } catch (e) { console.error(e) }
}

// ── Playground actions ──
async function openPlayground(name) {
  playgroundStrategy.value = name
  playgroundActive.value = true
  pgError.value = ''; pgErrorTrace.value = ''; pgSuccessMsg.value = ''
  pgMetrics.value = null; pgEquityCurve.value = []; pgTrades.value = []; pgSessions.value = []; pgExpandedSessions.value = {}
  pgChartData.value = null; pgResultHyperparams.value = null
  pgCustomHPs.value = []
  destroyCharts()

  // Load scenarios + hyperparameters in parallel
  const promises = []
  if (!scenarios.value.length) promises.push(api.getPlaygroundScenarios().then(r => { scenarios.value = r.scenarios || [] }).catch(() => {}))
  promises.push(loadStrategyHyperparams(name))
  await Promise.all(promises)
}

async function loadStrategyHyperparams(name) {
  try {
    const res = await api.getStrategyHyperparams(name)
    const hps = (res.hyperparameters || []).map(hp => ({
      name: hp.name,
      type: hp.type === 'categorical' ? 'str' : hp.type === 'int' ? 'int' : hp.type === 'float' ? 'float' : hp.type === 'str' ? 'str' : 'float',
      value: hp.default !== undefined ? hp.default : '',
      default: hp.default,
      min: hp.min,
      max: hp.max,
      description: hp.description || '',
      options: hp.options || undefined,
    }))
    pgHyperParams.value = hps
    pgHyperParamsDefaults.value = JSON.parse(JSON.stringify(hps))
  } catch {
    pgHyperParams.value = []
    pgHyperParamsDefaults.value = []
  }
}

function resetHyperParams() {
  pgHyperParams.value = JSON.parse(JSON.stringify(pgHyperParamsDefaults.value))
}

function closePlayground() {
  if (pgRunning.value) cancelSim()
  playgroundActive.value = false
  playgroundStrategy.value = ''
  destroyCharts()
}

function destroyCharts() {
  if (tradeChartRef.value) tradeChartRef.value.destroy()
  pgShowChart.value = false
  pgChartCandles.value = []
  pgChartRawCandles.value = []
  pgChartOrders.value = []
}

function onScenarioChange() {
  const presets = {
    trending_up: { volatility: 0.0002, trend_strength: 0.00005 }, trending_down: { volatility: 0.0002, trend_strength: 0.00005 },
    ranging: { volatility: 0.00012, trend_strength: 0 }, volatile: { volatility: 0.0006, trend_strength: 0 },
    flash_crash: { volatility: 0.0002, trend_strength: 0 }, flash_spike: { volatility: 0.0002, trend_strength: 0 },
    breakout_up: { volatility: 0.0002, trend_strength: 0 }, breakout_down: { volatility: 0.0002, trend_strength: 0 },
    mean_revert: { volatility: 0.0003, trend_strength: 0 }, choppy: { volatility: 0.0002, trend_strength: 0 },
    custom: { volatility: 0.0002, trend_strength: 0.00005 },
  }
  const p = presets[pgForm.value.scenario] || presets.custom
  pgForm.value.volatility = p.volatility; pgForm.value.trend_strength = p.trend_strength
}

async function previewScenario() {
  pgPreviewing.value = true; pgError.value = ''
  try {
    const res = await api.previewScenario({
      scenario: pgForm.value.scenario, duration_minutes: pgForm.value.duration_minutes,
      symbol: pgForm.value.symbol, start_price: pgForm.value.start_price,
      volatility: pgForm.value.volatility, trend_strength: pgForm.value.trend_strength,
      volume_base: 1000, seed: pgForm.value.seed || null,
    })
    pgChartCandles.value = res.candles || []
    pgChartRawCandles.value = res.candles || []
    pgChartOrders.value = []
    pgShowChart.value = true
    nextTick(() => { if (tradeChartRef.value) tradeChartRef.value.renderCandles() })
  } catch (e) { pgError.value = e.message }
  finally { pgPreviewing.value = false }
}

function buildHyperparamsPayload() {
  const hp = {}
  if (pgHyperParams.value.length) {
    for (const p of pgHyperParams.value) {
      if (p.name && p.value !== '' && p.value !== undefined) {
        hp[p.name] = p.type === 'int' ? parseInt(p.value) : p.type === 'float' ? parseFloat(p.value) : p.value
      }
    }
  } else {
    for (const p of pgCustomHPs.value) {
      if (p.key && p.value !== '') hp[p.key] = Number(p.value)
    }
  }
  return Object.keys(hp).length ? hp : null
}

async function runSimulation() {
  pgError.value = ''; pgErrorTrace.value = ''; pgSuccessMsg.value = ''
  pgMetrics.value = null; pgEquityCurve.value = []; pgTrades.value = []; pgSessions.value = []; pgExpandedSessions.value = {}
  pgChartData.value = null; pgResultHyperparams.value = null
  pgLogs.value = []; pgLogsFormatted.value = null; pgLogFilter.value = 'all'
  pgProgress.value = { current: 0, eta: 0 }; pgRunning.value = true
  pgActiveTab.value = 'summary'; pgTradesPage.value = 1

  const id = crypto.randomUUID()
  pgTaskId.value = id

  try {
    await api.runPlayground({
      id, strategy: playgroundStrategy.value, exchange: 'Sandbox',
      symbol: pgForm.value.symbol, timeframe: pgForm.value.timeframe,
      scenario: pgForm.value.scenario, duration_minutes: pgForm.value.duration_minutes,
      start_price: pgForm.value.start_price, volatility: pgForm.value.volatility,
      trend_strength: pgForm.value.trend_strength, volume_base: 1000,
      seed: pgForm.value.seed || null, balance: pgForm.value.balance,
      leverage: pgForm.value.leverage, warm_up_candles: pgForm.value.warm_up_candles,
      hyperparameters: buildHyperparamsPayload(),
    })
  } catch (e) { pgError.value = e.message; pgRunning.value = false }
}

async function cancelSim() {
  if (pgTaskId.value) { try { await api.cancelPlayground(pgTaskId.value) } catch {} }
  pgRunning.value = false; pgProgress.value = { current: 0, eta: 0 }
}

// ── Chart rendering (delegated to TradeChart component) ──
function renderCharts() {
  if (!tradeChartRef.value) return
  tradeChartRef.value.renderCandles()
  tradeChartRef.value.renderEquity()
}

// ── WebSocket ──
useWebSocket((msg) => {
  const { event, data } = msg
  if (!playgroundActive.value) return

  if (event === 'backtest.progressbar' && pgRunning.value) {
    pgProgress.value = { current: data?.current || 0, eta: data?.estimated_remaining_seconds || 0 }
  } else if (event === 'backtest.playground_result') {
    pgRunning.value = false; pgProgress.value = { current: 100, eta: 0 }
    pgSuccessMsg.value = `Simulation completed in ${data?.execution_duration || 0}s`
    pgMetrics.value = data?.metrics || null
    pgEquityCurve.value = data?.equity_curve || []
    pgTrades.value = data?.trades || []
    pgSessions.value = data?.sessions || _buildSessionsFromTrades(data?.trades || [])
    pgExpandedSessions.value = {}
    pgResultHyperparams.value = data?.hyperparameters || null
    pgChartData.value = data?.chart_data || null
    pgLogs.value = data?.logs || []
    pgLogsFormatted.value = _formatPgLogs(pgLogs.value, pgLogFilter.value)

    pgShowChart.value = true
    nextTick(() => {
      if (pgChartData.value?.candles_chart?.length) {
        const cd = pgChartData.value.candles_chart[0]
        pgChartCandles.value = cd.candles || []
        pgChartRawCandles.value = cd.candles_1m || []
        pgChartOrders.value = pgChartData.value.orders_chart?.[0]?.orders || []
      }
      nextTick(() => renderCharts())
    })
  } else if (event === 'backtest.playground_exception' && pgRunning.value) {
    pgRunning.value = false; pgProgress.value = { current: 0, eta: 0 }
    pgError.value = data?.error || 'Simulation failed'; pgErrorTrace.value = data?.traceback || ''
  } else if (event === 'backtest.metrics' && pgRunning.value && !pgMetrics.value) {
    pgMetrics.value = data; pgRunning.value = false; pgProgress.value = { current: 100, eta: 0 }; pgSuccessMsg.value = 'Simulation completed!'
  } else if (event === 'backtest.equity_curve' && pgRunning.value) {
    pgEquityCurve.value = data || []
    nextTick(() => { if (tradeChartRef.value) tradeChartRef.value.renderEquity() })
  } else if (event === 'backtest.trades' && pgRunning.value) {
    pgTrades.value = Array.isArray(data) ? data : []; pgTradesPage.value = 1
  } else if (event === 'backtest.exception' && pgRunning.value) {
    pgError.value = data?.error || 'Simulation failed'; pgErrorTrace.value = data?.traceback || ''
    pgRunning.value = false; pgProgress.value = { current: 0, eta: 0 }
  } else if (event === 'backtest.termination' && pgRunning.value) {
    pgRunning.value = false; pgSuccessMsg.value = 'Simulation terminated.'
  }
})

// ── Session helpers ──
function _buildSessionsFromTrades(tradesList) {
  const map = {}
  for (const t of tradesList) {
    const sn = t.meta?.session
    if (sn == null) continue
    if (!map[sn]) map[sn] = { session: sn, trades: [], total_pnl: 0, total_fee: 0, opened_at: t.opened_at, closed_at: null, outcome: null, levels: 0, trade_count: 0 }
    const s = map[sn]
    s.trades.push(t); s.total_pnl += (t.pnl || t.PNL || 0); s.total_fee += (t.fee || 0)
    s.levels = Math.max(s.levels, t.meta?.level || 0); s.closed_at = t.closed_at; s.outcome = t.meta?.exit_reason || s.outcome
  }
  return Object.keys(map).sort((a, b) => a - b).map(k => { const s = map[k]; s.trade_count = s.trades.length; s.total_pnl = parseFloat(s.total_pnl.toFixed(6)); s.total_fee = parseFloat(s.total_fee.toFixed(6)); return s })
}

function _togglePgSession(sn) { pgExpandedSessions.value[sn] = !pgExpandedSessions.value[sn] }

function _formatPgLogs(rawLogs, filter) {
  if (!rawLogs || !rawLogs.length) return null
  const filtered = filter === 'all' ? rawLogs : rawLogs.filter(l => l.type === filter)
  if (!filtered.length) return 'No logs matching filter.'
  return filtered.map(l => {
    const ts = l.timestamp ? new Date(l.timestamp).toISOString().replace('T', ' ').slice(0, 19) : ''
    const tag = (l.type || 'info').toUpperCase()
    return `[${ts}] [${tag}] ${l.message}`
  }).join('\n')
}

function onPgLogFilterChange() {
  pgLogsFormatted.value = _formatPgLogs(pgLogs.value, pgLogFilter.value)
}

function copyPgLogs() {
  if (pgLogsFormatted.value) navigator.clipboard.writeText(pgLogsFormatted.value)
}
function _sessionOutcomeClass(o) { return o === 'tp_hit' ? 'text-green-400' : o === 'max_levels' ? 'text-red-400' : 'text-surface-400' }
function _sessionOutcomeLabel(o) { return o === 'tp_hit' ? 'TP Hit' : o === 'max_levels' ? 'Max Levels' : o || '-' }

// ── Formatters ──
function formatMetric(val) { if (val === null || val === undefined) return '-'; if (typeof val === 'number') return Number.isInteger(val) ? val.toString() : val.toFixed(2); return val }
function formatPrice(p) { if (!p && p !== 0) return '-'; return Number(p).toFixed(5) }
function formatMoney(v) { if (!v && v !== 0) return '-'; return (v >= 0 ? '+' : '') + Number(v).toFixed(2) }
function metricColor(key, val) {
  if (key.includes('profit') || key === 'total_return' || key === 'annual_return' || key === 'expectancy') return val > 0 ? 'text-green-400' : val < 0 ? 'text-red-400' : 'text-surface-100'
  if (key.includes('drawdown')) return 'text-red-400'
  if (key === 'win_rate') return val >= 50 ? 'text-green-400' : 'text-amber-400'
  return 'text-surface-100'
}

// ── Cleanup ──
onBeforeUnmount(() => {
  destroyCharts()
})

// ── Lifecycle ──
onMounted(async () => {
  await loadStrategies()
  try { const res = await api.llmStatus(); llmConfigured.value = res.configured } catch {}
})
</script>
