<template>
  <div>
    <!-- Workspace Tabs -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
      <h1 class="text-2xl font-bold text-center sm:text-left">Backtest</h1>
      <div class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg overflow-x-auto">
        <div v-for="wt in workspaceTabs" :key="wt.id"
          @click="!running && switchWorkspace(wt.id)"
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer group rounded-md transition-colors"
          :class="[
            wt.id === activeWorkspaceId ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300',
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
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Config Panel (Left) -->
      <div class="lg:col-span-1 space-y-4">
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Configuration</h2>

          <div class="space-y-3">
            <!-- Exchange -->
            <div>
              <label class="label">Exchange / Broker</label>
              <select v-model="form.exchange" class="select" @change="onExchangeChange">
                <option v-for="b in brokers" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>

            <!-- Routes -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="label mb-0">Routes</label>
                <button @click="addRoute" class="text-xs text-brand-400 hover:text-brand-300">+ Add Route</button>
              </div>
              <div v-for="(route, idx) in form.routes" :key="idx" class="flex gap-2 mb-2 items-start">
                <div class="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-1.5">
                  <div>
                    <select v-if="availableSymbols.length" v-model="route.symbol" class="select text-xs py-1.5" @change="onSymbolChange">
                      <option v-for="s in availableSymbols" :key="s" :value="s">{{ s }}</option>
                    </select>
                    <input v-else v-model="route.symbol" class="input text-xs py-1.5" placeholder="EUR-USD" />
                  </div>
                  <div>
                    <select v-model="route.timeframe" class="select text-xs py-1.5">
                      <option v-for="tf in timeframes" :key="tf.value" :value="tf.value">{{ tf.label }}</option>
                    </select>
                  </div>
                  <div>
                    <select v-if="strategies.length" v-model="route.strategy" class="select text-xs py-1.5">
                      <option v-for="s in strategies" :key="s" :value="s">{{ s }}</option>
                    </select>
                    <input v-else v-model="route.strategy" class="input text-xs py-1.5" placeholder="Strategy" />
                  </div>
                </div>
                <button v-if="form.routes.length > 1" @click="removeRoute(idx)" class="text-surface-500 hover:text-red-400 text-lg mt-1">&times;</button>
              </div>
            </div>

            <!-- Data Routes (Extra) -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="label mb-0">Data Routes <span class="text-surface-600">(optional)</span></label>
                <button @click="addDataRoute" class="text-xs text-brand-400 hover:text-brand-300">+ Add</button>
              </div>
              <div v-for="(dr, idx) in form.data_routes" :key="idx" class="flex gap-2 mb-2 items-start">
                <div class="flex-1 grid grid-cols-2 gap-1.5">
                  <div>
                    <select v-if="availableSymbols.length" v-model="dr.symbol" class="select text-xs py-1.5">
                      <option v-for="s in availableSymbols" :key="s" :value="s">{{ s }}</option>
                    </select>
                    <input v-else v-model="dr.symbol" class="input text-xs py-1.5" placeholder="EUR-USD" />
                  </div>
                  <div>
                    <select v-model="dr.timeframe" class="select text-xs py-1.5">
                      <option v-for="tf in timeframes" :key="tf.value" :value="tf.value">{{ tf.label }}</option>
                    </select>
                  </div>
                </div>
                <button @click="removeDataRoute(idx)" class="text-surface-500 hover:text-red-400 text-lg mt-1">&times;</button>
              </div>
            </div>

            <!-- Date range -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Start Date</label>
                <input v-model="form.startDate" type="date" class="input" />
              </div>
              <div>
                <label class="label">End Date</label>
                <input v-model="form.endDate" type="date" class="input" />
              </div>
            </div>

            <!-- Data range info -->
            <div v-if="dataRange" class="text-xs text-surface-500">
              Data: {{ dataRange.start }} to {{ dataRange.end }}
              <span v-if="dataRange.timeframes && dataRange.timeframes.length" class="ml-1 text-surface-400">
                ({{ dataRange.timeframes.join(', ') }})
              </span>
            </div>

            <!-- Starting balance -->
            <div>
              <label class="label">Starting Balance</label>
              <input v-model.number="form.balance" type="number" class="input" />
            </div>

            <!-- Warm-up candles -->
            <div>
              <label class="label">Warm-up Candles</label>
              <input v-model.number="form.warmUpCandles" type="number" class="input" min="0" />
            </div>

            <!-- Options -->
            <div class="pt-2 space-y-2">
              <h3 class="text-xs font-semibold text-surface-400 mb-1">Options</h3>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                <input v-model="form.debugMode" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                <span>Debug Mode</span>
                <span class="text-xs text-surface-600 ml-1">— logs every step, slower</span>
              </label>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                <input v-model="form.exportChart" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                <span>Generate Charts</span>
                <span class="text-xs text-surface-600 ml-1">— interactive candle charts</span>
              </label>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                <input v-model="form.exportTradingview" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                <span>Export TradingView</span>
              </label>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                <input v-model="form.exportCsv" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                <span>Export CSV</span>
              </label>
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                <input v-model="form.exportJson" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                <span>Export JSON</span>
              </label>
<!-- for future use when we have a faster backtesting algorithm that can sacrifice some accuracy for speed -->
<!--              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">-->
<!--                <input v-model="form.fastMode" type="checkbox" class="rounded bg-surface-700 border-surface-500" />-->
<!--                <span>Fast Mode</span>-->
<!--                <span class="text-xs text-surface-600 ml-1">— faster with improved algorithm</span>-->
<!--              </label>-->
              <!-- benchmark is for cryptos, where we can compare against actual price movements to see how slippage/spread would affect the strategy performance -->
<!--              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">-->
<!--                <input v-model="form.benchmark" type="checkbox" class="rounded bg-surface-700 border-surface-500" />-->
<!--                <span>Benchmark</span>-->
<!--              </label>-->
              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                <input v-model="form.costModel" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                <span>Cost Model</span>
                <span class="text-xs text-surface-600 ml-1">— apply spread, slippage &amp; swap</span>
              </label>
            </div>

            <!-- Hyperparameters (auto-loaded from strategy) -->
            <div v-if="btHyperParams.length" class="pt-2">
              <div class="flex items-center justify-between mb-2">
                <h3 class="text-xs font-semibold text-surface-400">Hyperparameters</h3>
                <button @click="resetBtHyperParams" class="text-xs text-surface-500 hover:text-surface-300">Reset Defaults</button>
              </div>
              <div v-for="(hp, idx) in btHyperParams" :key="idx" v-show="isHpVisible(hp)" class="mb-2">
                <div class="flex gap-2 items-center">
                  <span class="text-xs text-surface-400 w-28 truncate" :title="hp.description || hp.name">{{ hp.name }}</span>
                  <select v-if="hp.options" v-model="hp.value" class="select text-xs py-1.5 flex-1">
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

            <!-- No data warning -->
            <div v-if="!dataRange && form.exchange" class="p-2 bg-amber-500/10 rounded text-xs text-amber-400">
              No candle data found for {{ form.exchange }} / {{ form.routes[0]?.symbol }}.
              <router-link to="/import" class="underline">Import data first</router-link>.
            </div>

            <!-- Action buttons -->
            <button @click="runBacktest" class="btn-primary w-full mt-2" :disabled="running">
              <span v-if="running" class="flex items-center justify-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Running...
              </span>
              <span v-else>Run Backtest</span>
            </button>
            <button v-if="running" @click="cancelBacktest" class="btn-secondary w-full text-sm">
              Cancel
            </button>
          </div>
        </div>

        <!-- Progress -->
        <ProgressBar
          :visible="running"
          :percent="progress.current"
          :eta="progress.eta"
          label="Backtesting"
        />

        <!-- General Info during run -->
        <div v-if="running && generalInfo" class="card text-xs space-y-1">
          <div v-for="(val, key) in generalInfo" :key="key" class="text-surface-500">
            {{ key }}: <span class="text-surface-300">{{ val }}</span>
          </div>
        </div>
      </div>

      <!-- Results Panel (Right) -->
      <div class="lg:col-span-2 space-y-4">
        <!-- Open Session Tabs -->
        <div v-if="openTabs.length > 0" class="flex items-center gap-1 overflow-x-auto pb-1">
          <div v-for="tab in openTabs" :key="tab.id"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs cursor-pointer shrink-0 border border-b-0 transition-colors"
            :class="selectedSession?.id === tab.id ? 'bg-surface-800 text-surface-100 border-surface-600' : 'bg-surface-900 text-surface-500 border-surface-700 hover:text-surface-300'"
            @click="switchToTab(tab.id)">
            <span class="max-w-[120px] truncate">{{ tab.label }}</span>
            <button @click.stop="closeTab(tab.id)" class="text-surface-600 hover:text-red-400 text-sm leading-none">&times;</button>
          </div>
        </div>

        <!-- Error -->
        <div v-if="error" class="card border-red-500/30">
          <div class="flex items-center gap-2 mb-1">
            <span class="text-red-400 font-semibold text-sm">Error</span>
            <div class="ml-auto flex items-center gap-2">
              <button v-if="form.routes[0]?.strategy" @click="openStrategyEditor" class="text-xs text-brand-400 hover:text-brand-300">Edit Strategy</button>
              <button @click="error = ''; errorTrace = ''" class="text-surface-500 text-xs">Dismiss</button>
            </div>
          </div>
          <p class="text-red-400 text-sm">{{ error }}</p>
          <pre v-if="errorTrace" class="text-xs text-red-300/70 mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap">{{ errorTrace }}</pre>
        </div>

        <!-- Inline Strategy Editor (shown on error) -->
        <div v-if="editingStrategy" class="card border-brand-500/30">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-semibold text-surface-300">{{ editingStrategy }} — Fix &amp; Retry</h2>
            <div class="flex items-center gap-2">
              <button @click="saveAndRetry" class="btn-primary btn-sm" :disabled="strategySaving">{{ strategySaving ? 'Saving...' : 'Save & Retry' }}</button>
              <button @click="saveStrategyCode" class="btn-sm bg-surface-700 text-surface-300" :disabled="strategySaving">Save</button>
              <button @click="editingStrategy = null" class="text-surface-500 hover:text-surface-200 text-xl">&times;</button>
            </div>
          </div>
          <div class="flex gap-2 mb-3">
            <input v-model="strategyRefineInput" class="input flex-1 text-xs" placeholder="AI: e.g. Fix the error, add stop loss..." />
            <button @click="refineFromBacktest" class="btn-sm bg-brand-600 text-white" :disabled="strategyRefining || !strategyRefineInput || !llmConfigured">
              <span v-if="strategyRefining" class="flex items-center gap-1">
                <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Refining...
              </span>
              <span v-else>AI Fix</span>
            </button>
          </div>
          <textarea v-model="strategyCode" class="input w-full font-mono text-xs resize-none min-h-[350px]"></textarea>
          <p v-if="strategyMsg" class="text-xs mt-2" :class="strategyMsgErr ? 'text-red-400' : 'text-green-400'">{{ strategyMsg }}</p>
        </div>

        <!-- Completion message -->
        <div v-if="message" class="card border-green-500/30">
          <p class="text-green-400 text-sm">{{ message }}</p>
        </div>

        <!-- Exposure Table (always visible when available) -->
        <div v-if="exposureTable.length && !hasResults" class="card">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-surface-300">Exposure Table</h3>
            <div class="flex items-center gap-3">
              <span v-if="exposureMeta.contract_size" class="text-[10px] text-surface-600">
                1 lot = {{ Number(exposureMeta.contract_size).toLocaleString() }} units &middot;
                Leverage {{ exposureMeta.leverage }}:1 &middot;
                Price ~{{ exposureMeta.price }}
              </span>
              <div class="flex items-center bg-surface-800 rounded text-[10px]">
                <button @click="exposureSizeDisplay = 'lots'"
                  class="px-2 py-1 rounded-l transition-colors"
                  :class="exposureSizeDisplay === 'lots' ? 'bg-brand-600 text-white' : 'text-surface-400 hover:text-surface-200'">Lots</button>
                <button @click="exposureSizeDisplay = 'units'"
                  class="px-2 py-1 rounded-r transition-colors"
                  :class="exposureSizeDisplay === 'units' ? 'bg-brand-600 text-white' : 'text-surface-400 hover:text-surface-200'">Units</button>
              </div>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="text-surface-500 border-b border-surface-700">
                  <th class="text-left py-2 px-2">Level</th>
                  <th class="text-left py-2 px-2">Dir</th>
                  <th class="text-right py-2 px-2">% Equity</th>
                  <th class="text-right py-2 px-2">{{ exposureSizeDisplay === 'lots' ? 'Lots' : 'Units' }}</th>
                  <th class="text-right py-2 px-2">Margin</th>
                  <th class="text-right py-2 px-2">Cumul. Margin</th>
                  <th class="text-right py-2 px-2">Margin %</th>
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2">Leg Loss</th>
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2">Worst Float</th>
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2">TP Profit</th>
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2">Net if TP</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in exposureTable" :key="row.level"
                    class="border-b border-surface-800 hover:bg-surface-800/50"
                    :class="row.margin_pct > 80 ? 'bg-red-900/10' : ''">
                  <td class="py-1.5 px-2 font-mono font-bold text-brand-400">L{{ row.level }}</td>
                  <td class="py-1.5 px-2 font-mono" :class="row.direction === 'LONG' ? 'text-green-400' : 'text-red-400'">{{ row.direction }}</td>
                  <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ row.equity_pct }}%</td>
                  <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ exposureSizeDisplay === 'lots' ? row.lots : Number(row.units).toLocaleString() }}</td>
                  <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ formatMetric(row.margin) }}</td>
                  <td class="py-1.5 px-2 text-right font-mono text-amber-400">{{ formatMetric(row.cumul_margin) }}</td>
                  <td class="py-1.5 px-2 text-right font-mono" :class="row.margin_pct > 80 ? 'text-red-400 font-bold' : row.margin_pct > 50 ? 'text-amber-400' : 'text-surface-300'">{{ row.margin_pct }}%</td>
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono text-red-400">{{ formatMetric(row.leg_loss) }}</td>
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono text-red-400 font-bold">{{ formatMetric(row.worst_float) }}</td>
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono text-green-400">{{ formatMetric(row.tp_profit) }}</td>
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono" :class="row.net_if_tp >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(row.net_if_tp) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Results Tabs -->
        <div v-if="hasResults" class="card">
          <!-- Tab bar -->
          <div class="flex items-center gap-1 border-b border-surface-700 mb-4 -mt-1 overflow-x-auto">
            <button v-for="tab in resultTabs" :key="tab.id"
              @click="activeTab = tab.id"
              class="px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors"
              :class="activeTab === tab.id
                ? 'border-brand-500 text-brand-400'
                : 'border-transparent text-surface-500 hover:text-surface-300'">
              {{ tab.label }}
              <span v-if="tab.count !== undefined" class="ml-1 text-surface-600">({{ tab.count }})</span>
            </button>
          </div>

          <!-- Summary Tab -->
          <div v-if="activeTab === 'summary'">
            <!-- Route selector (for multi-route) -->
            <div v-if="form.routes.length > 1" class="mb-4">
              <select v-model="selectedRouteIdx" class="select text-xs w-auto inline-block">
                <option v-for="(r, i) in form.routes" :key="i" :value="i">{{ r.strategy }} - {{ r.symbol }} {{ r.timeframe }}</option>
              </select>
            </div>

            <!-- Performance metrics -->
            <div class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Performance</h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in performanceMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">{{ m.label }}</div>
                  <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>

            <!-- Hedge Session Stats -->
            <div v-if="hedgeSessionMetrics.length" class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Hedge Session Stats</h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in hedgeSessionMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">{{ m.label }}</div>
                  <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>

            <!-- Risk metrics -->
            <div class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Risk &amp; Ratios</h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in riskMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">{{ m.label }}</div>
                  <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>

            <!-- Trade Stats -->
            <div class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Trade Statistics</h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in tradeStatsMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">{{ m.label }}</div>
                  <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>

            <!-- Forex/CFD Costs -->
            <div v-if="forexMetrics.length" class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Forex / CFD Costs</h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in forexMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">{{ m.label }}</div>
                  <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>
            
            <!-- Hyperparameters -->
            <div v-if="hyperparameters && hyperparameters.length" class="mt-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Hyperparameters</h3>
              <div class="flex flex-wrap gap-2">
                <div v-for="(hp, idx) in hyperparameters" :key="idx" class="px-3 py-1.5 bg-surface-800 rounded-lg text-xs">
                  <span class="text-surface-500">{{ Array.isArray(hp) ? hp[0] : hp.name }}:</span>
                  <span class="text-surface-200 font-mono ml-1">{{ Array.isArray(hp) ? hp[1] : hp.value }}</span>
                </div>
              </div>
            </div>

            <!-- Downloads -->
            <div v-if="sessionId" class="mt-4 flex flex-wrap gap-2">
              <a v-if="form.exportTradingview" :href="downloadUrl('tradingview')" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                TradingView
              </a>
              <a v-if="form.exportCsv" :href="downloadUrl('csv')" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                CSV
              </a>
              <a v-if="form.exportJson" :href="downloadUrl('json')" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                JSON
              </a>
              <a :href="downloadUrl('full-reports')" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                Full Report
              </a>
            </div>
          </div>

          <!-- Exposure Tab -->
          <!-- Charts Tab (Trade Chart + Equity, Floating PnL, Margin Usage) -->
          <div v-if="activeTab === 'charts'">
            <!-- Interactive Trade Chart -->
            <div v-if="btChartVisible || btChartCandles.length" class="mb-6">
              <h3 class="text-xs font-semibold text-surface-500 mb-2">Price Chart &amp; Orders</h3>
              <TradeChart
                v-show="btChartVisible"
                ref="btTradeChartRef"
                :candles="btChartCandles"
                :raw-candles="btChartRawCandles"
                :route-timeframe="form.routes[0]?.timeframe || '1h'"
                :orders="btChartOrders"
                :trades="trades"
                :equity-curve="equityCurve"
                :balance="form.balance"
              />
            </div>
            <div v-else-if="form.exportChart" class="text-surface-500 text-sm py-4 text-center mb-4">
              No trade chart data available yet.
            </div>
            <div v-else class="text-surface-500 text-sm py-4 text-center mb-4">
              Enable "Generate Charts" option to see interactive price charts.
            </div>

            <!-- Equity / Floating PnL / Margin Usage -->
            <div v-if="equityCurve.length && extractEquityValues(equityCurve).length" class="space-y-1">
              <div class="flex items-center justify-between mb-2">
                <span class="text-xs text-surface-500">Synced charts — scroll to zoom, drag to pan</span>
                <button @click="fitAllCharts" class="text-xs text-brand-400 hover:text-brand-300">Fit All</button>
              </div>
              <div>
                <div class="text-[10px] text-surface-500 mb-0.5 px-1">Equity Curve</div>
                <div ref="equityChartEl" class="w-full h-[220px] bg-surface-800 rounded"></div>
              </div>
              <div>
                <div class="text-[10px] text-surface-500 mb-0.5 px-1">Floating PnL</div>
                <div ref="floatingPnlChartEl" class="w-full h-[180px] bg-surface-800 rounded"></div>
              </div>
              <div>
                <div class="text-[10px] text-surface-500 mb-0.5 px-1">Margin Usage</div>
                <div ref="marginChartEl" class="w-full h-[180px] bg-surface-800 rounded"></div>
              </div>
            </div>
          </div>

          <!-- Sessions Tab (hedge session grouping) -->
          <div v-if="activeTab === 'sessions'">
            <div v-if="!hedgeSessions.length" class="text-surface-500 text-sm py-8 text-center">No sessions recorded.</div>
            <div v-if="hedgeSessions.length">
              <!-- Session summary stats -->
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Total Sessions</div>
                  <div class="font-mono text-surface-100">{{ hedgeSessions.length }}</div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Wins</div>
                  <div class="font-mono text-green-400">{{ hedgeSessions.filter(s => s.outcome === 'tp_hit' || s.outcome === 'bucket_hit').length }}</div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Max Levels</div>
                  <div class="font-mono text-red-400">{{ hedgeSessions.filter(s => s.outcome === 'max_levels').length }}</div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Total PnL</div>
                  <div class="font-mono" :class="hedgeSessions.reduce((a, s) => a + s.total_pnl, 0) >= 0 ? 'text-green-400' : 'text-red-400'">
                    {{ hedgeSessions.reduce((a, s) => a + s.total_pnl, 0).toFixed(2) }}
                  </div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Worst Session Float</div>
                  <div class="font-mono text-red-400">{{ Math.min(...hedgeSessions.map(s => s.min_float || 0)).toFixed(2) }}</div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Peak Equity Used</div>
                  <div class="font-mono" :class="Math.max(...hedgeSessions.map(s => s.peak_equity_pct || 0)) > 80 ? 'text-red-400' : 'text-amber-400'">
                    {{ Math.max(...hedgeSessions.map(s => s.peak_equity_pct || 0)).toFixed(1) }}%
                  </div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Margin Blocks</div>
                  <div class="font-mono" :class="hedgeSessions.filter(s => s.margin_block_leg != null).length > 0 ? 'text-red-400 font-bold' : 'text-green-400'">
                    {{ hedgeSessions.filter(s => s.margin_block_leg != null).length }}
                  </div>
                </div>
                <div class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs">Total Fees</div>
                  <div class="font-mono text-red-400">{{ hedgeSessions.reduce((a, s) => a + (s.total_fee || 0), 0).toFixed(2) }}</div>
                </div>
              </div>

              <!-- Sessions list -->
              <div class="space-y-2">
                <div v-for="s in paginatedSessions" :key="s.session" class="bg-surface-800 rounded overflow-hidden">
                  <!-- Session header (clickable) -->
                  <div
                    @click="toggleSession(s.session)"
                    class="flex items-center justify-between px-3 py-2.5 cursor-pointer hover:bg-surface-700/50 transition-colors"
                  >
                    <div class="flex items-center gap-3">
                      <span class="text-xs font-mono font-bold text-brand-400">S{{ s.session }}</span>
                      <span class="text-xs text-surface-400">{{ s.trade_count }} trade{{ s.trade_count !== 1 ? 's' : '' }}</span>
                      <span class="text-xs" :class="sessionOutcomeClass(s.outcome)">{{ sessionOutcomeLabel(s.outcome) }}</span>
                      <span v-if="s.levels > 0" class="text-xs text-surface-500">L{{ s.levels }}</span>
                      <span v-if="s.margin_block_leg != null" class="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 font-bold">Margin Block L{{ s.margin_block_leg }}</span>
                    </div>
                    <div class="flex items-center gap-4">
                      <span v-if="s.min_float" class="text-[10px] text-surface-500" title="Max adverse floating PnL">
                        Float <span class="font-mono text-red-400">{{ s.min_float.toFixed(2) }}</span>
                      </span>
                      <span v-if="s.peak_equity_pct" class="text-[10px] text-surface-500" title="Peak equity used %">
                        Eq <span class="font-mono" :class="s.peak_equity_pct > 80 ? 'text-red-400' : s.peak_equity_pct > 50 ? 'text-amber-400' : 'text-surface-300'">{{ s.peak_equity_pct.toFixed(1) }}%</span>
                      </span>
                      <span class="text-xs font-mono" :class="s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'">
                        {{ s.total_pnl >= 0 ? '+' : '' }}{{ s.total_pnl.toFixed(2) }}
                      </span>
                      <span class="text-xs text-surface-500">{{ formatTimestamp(s.opened_at) }}</span>
                      <svg
                        class="w-3.5 h-3.5 text-surface-500 transition-transform"
                        :class="{ 'rotate-180': expandedSessions[s.session] }"
                        viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                      >
                        <path d="M6 9l6 6 6-6"/>
                      </svg>
                    </div>
                  </div>

                  <!-- Expanded: session stats + trades -->
                  <div v-if="expandedSessions[s.session]" class="border-t border-surface-700">
                    <!-- Per-session stats bar -->
                    <div class="flex flex-wrap gap-4 px-3 py-2 bg-surface-850 border-b border-surface-700 text-[10px]">
                      <div>
                        <span class="text-surface-500">Max Float:</span>
                        <span class="font-mono ml-1" :class="(s.max_float || 0) > 0 ? 'text-green-400' : 'text-surface-300'">{{ (s.max_float || 0).toFixed(2) }}</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Min Float:</span>
                        <span class="font-mono ml-1 text-red-400">{{ (s.min_float || 0).toFixed(2) }}</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Peak Margin:</span>
                        <span class="font-mono ml-1 text-surface-300">${{ (s.peak_margin || 0).toFixed(2) }}</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Peak Equity Used:</span>
                        <span class="font-mono ml-1" :class="(s.peak_equity_pct || 0) > 80 ? 'text-red-400' : (s.peak_equity_pct || 0) > 50 ? 'text-amber-400' : 'text-green-400'">{{ (s.peak_equity_pct || 0).toFixed(1) }}%</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Total Fee:</span>
                        <span class="font-mono ml-1 text-red-400">{{ (s.total_fee || 0).toFixed(2) }}</span>
                      </div>
                      <div v-if="s.margin_block_leg != null">
                        <span class="text-red-500 font-bold">Margin Block at Level {{ s.margin_block_leg }}</span>
                      </div>
                    </div>
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="text-surface-500 border-b border-surface-700">
                          <th class="text-left py-1.5 px-3">Label</th>
                          <th class="text-left py-1.5 px-2">Type</th>
                          <th class="text-right py-1.5 px-2">Entry</th>
                          <th class="text-right py-1.5 px-2">Exit</th>
                          <th class="text-right py-1.5 px-2">Qty</th>
                          <th class="text-right py-1.5 px-2">PnL</th>
                          <th class="text-left py-1.5 px-2">Exit Reason</th>
                          <th class="text-left py-1.5 px-2">Duration</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(t, i) in s.trades" :key="i" class="border-b border-surface-800/50 hover:bg-surface-700/30">
                          <td class="py-1.5 px-3 font-mono font-bold" :class="t.meta?.exit_reason === 'tp_hit' || t.meta?.exit_reason === 'bucket_hit' ? 'text-green-400' : 'text-surface-300'">
                            {{ t.meta?.label || (t.meta?.session != null ? `S${t.meta.session}.L${t.meta.leg_index ?? i}` : `O${i + 1}`) }}
                          </td>
                          <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.entry_price) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.exit_price) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ formatMetric(t.qty) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl || t.PNL || 0) >= 0 ? 'text-green-400' : 'text-red-400'">
                            {{ formatMetric(t.pnl || t.PNL) }}
                          </td>
                          <td class="py-1.5 px-2" :class="sessionOutcomeClass(t.meta?.exit_reason)">
                            {{ t.meta?.exit_reason === 'tp_hit' ? 'TP' : t.meta?.exit_reason === 'bucket_hit' ? 'Bucket' : t.meta?.exit_reason === 'max_levels' ? 'Bust' : t.meta?.exit_reason === 'sl_hit' ? 'SL (Hedge)' : '-' }}
                          </td>
                          <td class="py-1.5 px-2 text-surface-500">{{ t.holding_period || '-' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <!-- Pagination -->
              <div v-if="hedgeSessions.length > sessionsPerPage" class="flex items-center justify-between mt-3 text-xs text-surface-500">
                <span>{{ hedgeSessions.length }} sessions</span>
                <div class="flex items-center gap-2">
                  <button @click="sessionsPage = Math.max(1, sessionsPage - 1)" :disabled="sessionsPage <= 1" class="btn-sm bg-surface-700 text-surface-300">Prev</button>
                  <span>{{ sessionsPage }} / {{ totalSessionsPages }}</span>
                  <button @click="sessionsPage = Math.min(totalSessionsPages, sessionsPage + 1)" :disabled="sessionsPage >= totalSessionsPages" class="btn-sm bg-surface-700 text-surface-300">Next</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Trades Tab -->
          <div v-if="activeTab === 'trades'">
            <div v-if="!trades.length" class="text-surface-500 text-sm py-8 text-center">No trades executed.</div>
            <div v-else class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-surface-500 border-b border-surface-700">
                    <th class="text-left py-2 px-2">#</th>
                    <th v-if="hedgeSessions.length" class="text-left py-2 px-2">Session</th>
                    <th class="text-left py-2 px-2">Symbol</th>
                    <th class="text-left py-2 px-2">Type</th>
                    <th class="text-right py-2 px-2">Entry</th>
                    <th class="text-right py-2 px-2">Exit</th>
                    <th class="text-right py-2 px-2">Qty</th>
                    <th class="text-right py-2 px-2">PnL</th>
                    <th class="text-right py-2 px-2">PnL %</th>
                    <th class="text-left py-2 px-2">Opened</th>
                    <th class="text-left py-2 px-2">Closed</th>
                    <th class="text-left py-2 px-2">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(t, i) in paginatedTrades" :key="i" class="border-b border-surface-800 hover:bg-surface-800/50">
                    <td class="py-1.5 px-2 text-surface-500">{{ (tradesPage - 1) * tradesPerPage + i + 1 }}</td>
                    <td v-if="hedgeSessions.length" class="py-1.5 px-2 font-mono text-brand-400 text-xs">{{ t.meta?.label || (t.meta?.session != null ? `S${t.meta.session}.L${t.meta.leg_index ?? '?'}` : '-') }}</td>
                    <td class="py-1.5 px-2 text-surface-300">{{ t.symbol || '-' }}</td>
                    <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.entry_price) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.exit_price) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ formatMetric(t.qty) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(t.pnl) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl_percentage || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ t.pnl_percentage != null ? t.pnl_percentage.toFixed(2) + '%' : '-' }}</td>
                    <td class="py-1.5 px-2 text-surface-500">{{ formatTimestamp(t.opened_at) }}</td>
                    <td class="py-1.5 px-2 text-surface-500">{{ formatTimestamp(t.closed_at) }}</td>
                    <td class="py-1.5 px-2 text-surface-500">{{ t.holding_period || '-' }}</td>
                  </tr>
                </tbody>
              </table>
              <!-- Pagination -->
              <div v-if="trades.length > tradesPerPage" class="flex items-center justify-between mt-3 text-xs text-surface-500">
                <span>{{ trades.length }} trades</span>
                <div class="flex items-center gap-2">
                  <button @click="tradesPage = Math.max(1, tradesPage - 1)" :disabled="tradesPage <= 1" class="btn-sm bg-surface-700 text-surface-300">Prev</button>
                  <span>{{ tradesPage }} / {{ totalTradesPages }}</span>
                  <button @click="tradesPage = Math.min(totalTradesPages, tradesPage + 1)" :disabled="tradesPage >= totalTradesPages" class="btn-sm bg-surface-700 text-surface-300">Next</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Costs Tab -->
          <div v-if="activeTab === 'costs'">
            <div v-if="!metrics" class="text-surface-500 text-sm py-8 text-center">No cost data available.</div>
            <div v-else class="space-y-6">

              <!-- Cost Summary -->
              <div>
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Cost Summary</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Total Fees (Orders)</div>
                    <div class="font-mono text-red-400">{{ fmtCost(metrics.fee) }}</div>
                  </div>
                  <div v-if="metrics.total_spread_cost != null" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Spread + Commission</div>
                    <div class="font-mono text-red-400">{{ fmtCost(metrics.total_spread_cost) }}</div>
                  </div>
                  <div v-if="metrics.total_swap_cost != null" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Overnight Swap</div>
                    <div class="font-mono text-red-400">{{ fmtCost(metrics.total_swap_cost) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Total All Costs</div>
                    <div class="font-mono text-red-400 font-bold">{{ fmtCost(totalCosts) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Cost / Net Profit</div>
                    <div class="font-mono" :class="costProfitRatio > 50 ? 'text-red-400' : costProfitRatio > 25 ? 'text-amber-400' : 'text-green-400'">
                      {{ costProfitRatio != null ? costProfitRatio.toFixed(1) + '%' : '-' }}
                    </div>
                  </div>
                  <div v-if="metrics.total_pips != null" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Total Pips</div>
                    <div class="font-mono text-surface-100">{{ metrics.total_pips }}</div>
                  </div>
                  <div v-if="metrics.avg_pips_per_trade != null" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Avg Pips/Trade</div>
                    <div class="font-mono text-surface-100">{{ metrics.avg_pips_per_trade }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Avg Cost/Trade</div>
                    <div class="font-mono text-surface-100">{{ trades.length ? fmtCost(totalCosts / trades.length) : '-' }}</div>
                  </div>
                </div>
              </div>

              <!-- Margin Summary -->
              <div>
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Margin &amp; Risk</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Peak Margin Used</div>
                    <div class="font-mono text-surface-100">{{ fmtCost(metrics.peak_margin_used) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Peak Equity Usage</div>
                    <div class="font-mono" :class="(metrics.peak_equity_usage_pct || 0) > 80 ? 'text-red-400' : (metrics.peak_equity_usage_pct || 0) > 50 ? 'text-amber-400' : 'text-green-400'">
                      {{ metrics.peak_equity_usage_pct != null ? metrics.peak_equity_usage_pct.toFixed(1) + '%' : '-' }}
                    </div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Worst Floating PnL</div>
                    <div class="font-mono text-red-400">{{ fmtCost(metrics.worst_floating_pnl) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Max Drawdown</div>
                    <div class="font-mono text-red-400">{{ fmtCost(metrics.max_drawdown) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Margin Closeouts</div>
                    <div class="font-mono" :class="(metrics.margin_closeouts || 0) > 0 ? 'text-red-400 font-bold' : 'text-green-400'">
                      {{ metrics.margin_closeouts || 0 }}
                    </div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Account Blown</div>
                    <div class="font-mono" :class="metrics.account_blown ? 'text-red-400 font-bold' : 'text-green-400'">
                      {{ metrics.account_blown ? 'YES' : 'No' }}
                    </div>
                  </div>
                  <div v-if="metrics.var_95 != null" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">VaR 95%</div>
                    <div class="font-mono text-surface-100">{{ fmtCost(metrics.var_95) }}</div>
                  </div>
                  <div v-if="metrics.cvar_95 != null" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">CVaR 95%</div>
                    <div class="font-mono text-surface-100">{{ fmtCost(metrics.cvar_95) }}</div>
                  </div>
                </div>
              </div>

              <!-- Margin Events (from logs) -->
              <div v-if="marginEvents.length">
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Margin Events ({{ marginEvents.length }})</h3>
                <div class="bg-surface-900 rounded p-3 max-h-[250px] overflow-auto space-y-1">
                  <div v-for="(evt, i) in marginEvents" :key="i" class="flex items-start gap-2 text-xs">
                    <span class="text-red-500 font-bold shrink-0">MARGIN</span>
                    <span class="text-surface-500 shrink-0">{{ formatTimestamp(evt.timestamp) }}</span>
                    <span class="text-surface-300">{{ evt.message }}</span>
                  </div>
                </div>
              </div>

              <!-- Per-Trade Cost Breakdown -->
              <div v-if="trades.length">
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Per-Trade Costs</h3>
                <div class="overflow-x-auto max-h-[350px]">
                  <table class="w-full text-xs">
                    <thead class="sticky top-0 bg-surface-850">
                      <tr class="text-surface-500 border-b border-surface-700">
                        <th class="text-left py-2 px-2">#</th>
                        <th class="text-left py-2 px-2">Symbol</th>
                        <th class="text-left py-2 px-2">Type</th>
                        <th class="text-right py-2 px-2">Entry</th>
                        <th class="text-right py-2 px-2">Exit</th>
                        <th class="text-right py-2 px-2">Qty</th>
                        <th class="text-right py-2 px-2">Fee</th>
                        <th class="text-right py-2 px-2">PnL</th>
                        <th class="text-right py-2 px-2">PnL After Costs</th>
                        <th class="text-right py-2 px-2">Cost Impact</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(t, i) in paginatedCostTrades" :key="i" class="border-b border-surface-800 hover:bg-surface-800/50">
                        <td class="py-1.5 px-2 text-surface-500">{{ (costTradesPage - 1) * costTradesPerPage + i + 1 }}</td>
                        <td class="py-1.5 px-2 text-surface-300">{{ t.symbol || '-' }}</td>
                        <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.entry_price) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.exit_price) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ formatMetric(t.qty) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ fmtCost(t.fee) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(t.pnl) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="((t.pnl || 0) - Math.abs(t.fee || 0)) >= 0 ? 'text-green-400' : 'text-red-400'">
                          {{ formatMetric((t.pnl || 0)) }}
                        </td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-400">
                          {{ t.pnl && t.fee ? ((Math.abs(t.fee) / Math.abs(t.pnl)) * 100).toFixed(1) + '%' : '-' }}
                        </td>
                      </tr>
                    </tbody>
                    <tfoot class="border-t border-surface-600">
                      <tr class="font-semibold">
                        <td colspan="6" class="py-2 px-2 text-surface-400 text-right">Totals:</td>
                        <td class="py-2 px-2 text-right font-mono text-red-400">{{ fmtCost(trades.reduce((s, t) => s + Math.abs(t.fee || 0), 0)) }}</td>
                        <td class="py-2 px-2 text-right font-mono" :class="trades.reduce((s, t) => s + (t.pnl || 0), 0) >= 0 ? 'text-green-400' : 'text-red-400'">
                          {{ formatMetric(trades.reduce((s, t) => s + (t.pnl || 0), 0)) }}
                        </td>
                        <td colspan="2"></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
                <!-- Pagination -->
                <div v-if="trades.length > costTradesPerPage" class="flex items-center justify-between mt-3 text-xs text-surface-500">
                  <span>{{ trades.length }} trades</span>
                  <div class="flex items-center gap-2">
                    <button @click="costTradesPage = Math.max(1, costTradesPage - 1)" :disabled="costTradesPage <= 1" class="btn-sm bg-surface-700 text-surface-300">Prev</button>
                    <span>{{ costTradesPage }} / {{ totalCostTradesPages }}</span>
                    <button @click="costTradesPage = Math.min(totalCostTradesPages, costTradesPage + 1)" :disabled="costTradesPage >= totalCostTradesPages" class="btn-sm bg-surface-700 text-surface-300">Next</button>
                  </div>
                </div>
              </div>

            </div>
          </div>

          <!-- Logs Tab -->
          <div v-if="activeTab === 'logs'">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <span class="text-xs text-surface-500">Backtest Logs</span>
                <select v-if="backtestLogs.length" v-model="logFilter" @change="onLogFilterChange" class="select text-xs py-1 w-auto">
                  <option value="all">All</option>
                  <option value="strategy">Strategy</option>
                  <option value="position">Position</option>
                  <option value="order">Order</option>
                  <option value="market">Market</option>
                </select>
                <span v-if="backtestLogs.length" class="text-xs text-surface-600">({{ logFilter === 'all' ? backtestLogs.length : backtestLogs.filter(l => l.type === logFilter).length }} entries)</span>
              </div>
              <div class="flex items-center gap-2">
                <button v-if="logs" @click="copyLogs" class="btn-sm bg-surface-700 text-surface-300">Copy</button>
                <a v-if="sessionId" :href="api.getBacktestLogDownloadUrl(sessionId)" target="_blank" class="btn-sm bg-surface-700 text-surface-300">Download</a>
                <button v-if="!logs && sessionId" @click="loadLogs" class="btn-sm bg-surface-700 text-surface-300" :disabled="loadingLogs">
                  {{ loadingLogs ? 'Loading...' : 'Load Logs' }}
                </button>
              </div>
            </div>
            <div v-if="logs" class="bg-surface-900 rounded p-3 max-h-[500px] overflow-auto">
              <pre class="text-xs text-surface-400 whitespace-pre-wrap font-mono">{{ logs }}</pre>
            </div>
            <div v-else class="text-surface-500 text-sm py-8 text-center">
              {{ sessionId ? 'Click "Load Logs" to fetch logs.' : 'No logs available.' }}
            </div>
          </div>

          <!-- Strategy Code Tab -->
          <div v-if="activeTab === 'strategy'">
            <div class="flex items-center justify-between mb-3">
              <span class="text-xs text-surface-500">Strategy Code Snapshot</span>
              <div class="flex items-center gap-2">
                <button v-if="sessionStrategyCodes" @click="copyStrategyCode" class="btn-sm bg-surface-700 text-surface-300">Copy</button>
                <button v-if="!sessionStrategyCodes && sessionId" @click="loadStrategyCode" class="btn-sm bg-surface-700 text-surface-300" :disabled="loadingStrategyCode">
                  {{ loadingStrategyCode ? 'Loading...' : 'Load Code' }}
                </button>
              </div>
            </div>
            <!-- Route selector for strategy code -->
            <div v-if="sessionStrategyCodes && Object.keys(sessionStrategyCodes).length > 1" class="mb-3">
              <select v-model="selectedStrategyCodeKey" class="select text-xs w-auto inline-block">
                <option v-for="k in Object.keys(sessionStrategyCodes)" :key="k" :value="k">{{ k }}</option>
              </select>
            </div>
            <div v-if="currentStrategyCode" class="bg-surface-900 rounded p-3 max-h-[500px] overflow-auto">
              <pre class="text-xs text-surface-400 whitespace-pre-wrap font-mono">{{ currentStrategyCode }}</pre>
            </div>
            <div v-else class="text-surface-500 text-sm py-8 text-center">
              {{ sessionId ? 'Click "Load Code" to fetch strategy code.' : 'No strategy code available.' }}
            </div>
          </div>
        </div>

        <!-- Sessions List -->
        <div class="card">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-surface-300">Recent Sessions</h2>
            <div class="flex items-center gap-2">
              <button @click="loadSessions" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
              <button v-if="sessions.length > 0" @click="showPurgeConfirm = true" class="text-xs text-red-400 hover:text-red-300">Purge Old</button>
            </div>
          </div>

          <!-- Search / Filter -->
          <div v-if="sessions.length > 3" class="flex gap-2 mb-3">
            <input v-model="sessionSearch" class="input text-xs flex-1" placeholder="Search by title..." />
            <select v-model="sessionStatusFilter" class="select text-xs w-auto">
              <option value="">All</option>
              <option value="finished">Finished</option>
              <option value="cancelled">Cancelled</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          <div v-if="loadingSessions" class="text-surface-500 text-sm">Loading...</div>

          <div v-else-if="filteredSessions.length === 0" class="text-surface-500 text-sm">
            No backtest sessions yet. Run a backtest to see results here.
          </div>

          <div v-else class="space-y-2">
            <div v-for="s in filteredSessions" :key="s.id"
              class="p-3 bg-surface-800/50 rounded-lg hover:bg-surface-800 transition-colors cursor-pointer group"
              @click="viewSession(s)">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="text-xs px-2 py-0.5 rounded-full font-medium"
                    :class="statusBadgeClass(s.status)">{{ s.status }}</span>
                  <span class="text-sm text-surface-200">{{ s.title || sessionLabel(s) }}</span>
                  <span v-if="s.net_profit_percentage != null" class="text-xs font-mono" :class="s.net_profit_percentage >= 0 ? 'text-green-400' : 'text-red-400'">
                    {{ s.net_profit_percentage >= 0 ? '+' : '' }}{{ s.net_profit_percentage.toFixed(2) }}%
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-xs text-surface-500">{{ formatDate(s.updated_at) }}</span>
                  <button @click.stop="removeSession(s)" class="text-surface-600 hover:text-red-400 opacity-0 group-hover:opacity-100 text-sm" title="Remove">&times;</button>
                </div>
              </div>
              <div v-if="s.state" class="text-xs text-surface-500 mt-1">
                {{ formatSessionRoutes(s.state) }}
              </div>
              <div v-if="s.hyperparameters && s.hyperparameters.length" class="flex flex-wrap gap-1 mt-1">
                <span v-for="(hp, idx) in s.hyperparameters" :key="idx" class="text-[10px] px-1.5 py-0.5 bg-surface-700 rounded text-surface-400 font-mono">
                  {{ Array.isArray(hp) ? hp[0] : hp.name }}={{ Array.isArray(hp) ? hp[1] : hp.value }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Selected Session Detail -->
        <div v-if="selectedSession" class="card">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-3">
              <h2 class="text-sm font-semibold text-surface-300">Session Detail</h2>
              <button @click="editSessionNotes" class="text-xs text-brand-400 hover:text-brand-300">Edit Notes</button>
            </div>
            <div class="flex items-center gap-2">
              <button v-if="selectedSession.has_chart_data && !selectedSession.chart_data" @click="loadChartData" class="text-xs text-brand-400 hover:text-brand-300" :disabled="loadingChart">
                {{ loadingChart ? 'Loading...' : 'Load Chart' }}
              </button>
              <button @click="loadSessionAsForm" class="text-xs text-brand-400 hover:text-brand-300">Re-run</button>
              <button @click="closeTab(selectedSession.id)" class="text-surface-500 hover:text-surface-200 text-xs">Close</button>
            </div>
          </div>

          <!-- Session title editing -->
          <div v-if="editingNotes" class="mb-4 space-y-2">
            <input v-model="noteTitle" class="input text-xs" placeholder="Session title" />
            <textarea v-model="noteDescription" class="input text-xs resize-none h-16" placeholder="Description (optional)"></textarea>
            <div class="flex gap-2">
              <button @click="saveNotes" class="btn-sm bg-brand-600 text-white" :disabled="savingNotes">{{ savingNotes ? 'Saving...' : 'Save' }}</button>
              <button @click="editingNotes = false" class="btn-sm bg-surface-700 text-surface-300">Cancel</button>
            </div>
          </div>

          <!-- Session metrics -->
          <div v-if="selectedSession.metrics" class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div v-for="(val, key) in selectedSession.metrics" :key="key" class="p-2 bg-surface-800 rounded">
              <div class="text-surface-500 text-xs capitalize">{{ formatKey(key) }}</div>
              <div class="font-mono" :class="metricColor(key, val)">{{ formatMetric(val) }}</div>
            </div>
          </div>

          <!-- Session hyperparameters -->
          <div v-if="selectedSession.hyperparameters && selectedSession.hyperparameters.length" class="mt-4">
            <h3 class="text-xs font-semibold text-surface-500 mb-2">Hyperparameters</h3>
            <div class="flex flex-wrap gap-2">
              <div v-for="(hp, idx) in selectedSession.hyperparameters" :key="idx" class="px-3 py-1.5 bg-surface-800 rounded-lg text-xs">
                <span class="text-surface-500">{{ Array.isArray(hp) ? hp[0] : hp.name }}:</span>
                <span class="text-surface-200 font-mono ml-1">{{ Array.isArray(hp) ? hp[1] : hp.value }}</span>
              </div>
            </div>
          </div>

          <!-- Session equity curve -->
          <div v-if="selectedSession.equity_curve && (selectedSession.equity_curve.length || selectedSession.equity_curve.equity)" class="mt-4">
            <h3 class="text-xs font-semibold text-surface-500 mb-2">Equity Curve</h3>
            <div ref="sessionEquityEl" class="w-full h-[300px] bg-surface-800 rounded"></div>
          </div>

          <!-- Session trades -->
          <div v-if="selectedSession.trades && selectedSession.trades.length" class="mt-4">
            <h3 class="text-xs font-semibold text-surface-500 mb-2">Trades ({{ selectedSession.trades.length }})</h3>
            <div class="overflow-x-auto max-h-[300px]">
              <table class="w-full text-xs">
                <thead class="sticky top-0 bg-surface-850">
                  <tr class="text-surface-500 border-b border-surface-700">
                    <th class="text-left py-2 px-2">#</th>
                    <th class="text-left py-2 px-2">Type</th>
                    <th class="text-right py-2 px-2">Entry</th>
                    <th class="text-right py-2 px-2">Exit</th>
                    <th class="text-right py-2 px-2">PnL</th>
                    <th class="text-right py-2 px-2">PnL %</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(t, i) in selectedSession.trades" :key="i" class="border-b border-surface-800">
                    <td class="py-1 px-2 text-surface-500">{{ i + 1 }}</td>
                    <td class="py-1 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                    <td class="py-1 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.entry_price) }}</td>
                    <td class="py-1 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.exit_price) }}</td>
                    <td class="py-1 px-2 text-right font-mono" :class="(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(t.pnl) }}</td>
                    <td class="py-1 px-2 text-right font-mono" :class="(t.pnl_percentage || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ t.pnl_percentage != null ? t.pnl_percentage.toFixed(2) + '%' : '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else-if="selectedSession.metrics" class="mt-4 text-surface-500 text-sm">No trade data stored for this session.</div>

          <!-- Candle Chart (loaded separately) -->
          <div v-if="selectedSession.chart_data" class="mt-4">
            <h3 class="text-xs font-semibold text-surface-500 mb-2">Price Chart &amp; Orders</h3>
            <div v-for="(route, ri) in (selectedSession.chart_data.candles_chart || [])" :key="ri" class="mb-4">
              <div class="text-xs text-surface-400 mb-1">{{ route.symbol }} {{ route.timeframe }}</div>
              <div :ref="el => { if (el) renderCandleChart(el, route, ri) }" class="w-full h-[350px] bg-surface-900 rounded"></div>
            </div>
          </div>
        </div>

        <!-- Purge confirm modal -->
        <div v-if="showPurgeConfirm" class="card border-red-500/30">
          <h3 class="text-sm font-semibold text-red-400 mb-2">Purge Old Sessions</h3>
          <p class="text-xs text-surface-400 mb-3">Delete sessions older than:</p>
          <div class="flex items-center gap-3">
            <select v-model.number="purgeDays" class="select text-xs w-auto">
              <option :value="7">7 days</option>
              <option :value="30">30 days</option>
              <option :value="90">90 days</option>
              <option :value="null">All sessions</option>
            </select>
            <button @click="purgeSessions" class="btn-danger btn-sm">Purge</button>
            <button @click="showPurgeConfirm = false" class="btn-sm bg-surface-700 text-surface-300">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { api, defaultBrokerId } from '../api'
import { useWebSocket } from '../useWebSocket'
import { createChart, ColorType, LineSeries, AreaSeries, BaselineSeries } from 'lightweight-charts'
import ProgressBar from '../components/ProgressBar.vue'
import TradeChart from '../components/TradeChart.vue'

const brokers = ref([])
const strategies = ref([])
const sessions = ref([])
const selectedSession = ref(null)
const openTabs = ref([])
const tabCache = ref({})
const running = ref(false)

// Workspace tabs
const workspaceTabs = ref([{ id: 'ws-1', label: 'Backtest 1', running: false, hasResults: false }])
const activeWorkspaceId = ref('ws-1')
const workspaceCache = ref({})
let wsCounter = 1
const loadingSessions = ref(false)
const error = ref('')
const errorTrace = ref('')
const message = ref('')
const currentTaskId = ref(null)
const sessionId = ref(null)

// Available candle data
const existingCandles = ref([])

// WebSocket-driven state
const progress = ref({ current: 0, eta: 0 })
const metrics = ref(null)
const hyperparameters = ref(null)
const generalInfo = ref(null)
const equityCurve = ref([])
const floatingPnlCurve = ref(null)
const marginUsageCurve = ref(null)
const trades = ref([])
const hedgeSessions = ref([])
const exposureTable = ref([])
const exposureHasTpSl = ref(false)
const exposureMeta = ref({})  // contract_size, leverage, price
const exposureSizeDisplay = ref('lots')  // 'lots' or 'units' for display toggle
const llmConfigured = ref(false)

// Results tabs
const activeTab = ref('summary')
const selectedRouteIdx = ref(0)

// Trades pagination
const tradesPage = ref(1)
const tradesPerPage = 25

// Sessions state
const expandedSessions = ref({})
const sessionsPage = ref(1)
const sessionsPerPage = 10

// Logs
const logs = ref(null)
const loadingLogs = ref(false)
const backtestLogs = ref([])
const logFilter = ref('all')

// Backtest hyperparameters (loaded from strategy code)
const btHyperParams = ref([])
const btHyperParamsDefaults = ref([])
const btCustomHPs = ref([])

// Strategy code
const sessionStrategyCodes = ref(null)
const selectedStrategyCodeKey = ref('')
const loadingStrategyCode = ref(false)

// Chart
const loadingChart = ref(false)
const equityChartEl = ref(null)
const floatingPnlChartEl = ref(null)
const marginChartEl = ref(null)
const sessionEquityEl = ref(null)
const btTradeChartRef = ref(null)
const btChartCandles = ref([])
const btChartRawCandles = ref([])
const btChartOrders = ref([])
const btChartVisible = ref(false)

// Session management
const sessionSearch = ref('')
const sessionStatusFilter = ref('')
const showPurgeConfirm = ref(false)
const purgeDays = ref(30)
const editingNotes = ref(false)
const noteTitle = ref('')
const noteDescription = ref('')
const savingNotes = ref(false)

// Inline strategy editor
const editingStrategy = ref(null)
const strategyCode = ref('')
const strategySaving = ref(false)
const strategyMsg = ref('')
const strategyMsgErr = ref(false)
const strategyRefineInput = ref('')
const strategyRefining = ref(false)

const timeframes = [
  { value: '1m', label: '1m' },
  { value: '3m', label: '3m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '45m', label: '45m' },
  { value: '1h', label: '1h' },
  { value: '2h', label: '2h' },
  { value: '3h', label: '3h' },
  { value: '4h', label: '4h' },
  { value: '6h', label: '6h' },
  { value: '8h', label: '8h' },
  { value: '1D', label: '1D' },
]

const form = ref({
  exchange: '',
  routes: [{ symbol: 'EUR-USD', timeframe: '1m', strategy: 'ForexMA' }],
  data_routes: [],
  startDate: '2024-01-01',
  endDate: '2024-06-01',
  balance: 10000,
  warmUpCandles: 240,
  debugMode: true,
  exportChart: true,
  exportTradingview: true,
  exportCsv: true,
  exportJson: false,
  fastMode: false,
  benchmark: false,
  costModel: true,
})

// Route management
function addRoute() {
  const last = form.value.routes[form.value.routes.length - 1]
  form.value.routes.push({
    symbol: last?.symbol || 'EUR-USD',
    timeframe: last?.timeframe || '1h',
    strategy: last?.strategy || '',
  })
}
function removeRoute(idx) {
  form.value.routes.splice(idx, 1)
}
function addDataRoute() {
  form.value.data_routes.push({
    exchange: form.value.exchange,
    symbol: form.value.routes[0]?.symbol || 'EUR-USD',
    timeframe: '5m',
  })
}
function removeDataRoute(idx) {
  form.value.data_routes.splice(idx, 1)
}

// Symbols that have data for the selected exchange
const availableSymbols = computed(() => {
  const exch = form.value.exchange
  if (!exch) return []
  const syms = new Set()
  for (const c of existingCandles.value) {
    if (c.exchange === exch) syms.add(c.symbol)
  }
  return [...syms]
})

// Date range for current exchange+symbol
const dataRange = computed(() => {
  const sym = form.value.routes[0]?.symbol
  const match = existingCandles.value.find(
    c => c.exchange === form.value.exchange && c.symbol === sym
  )
  if (!match) return null
  return {
    start: match.from || match.start_date || '',
    end: match.to || match.end_date || '',
    timeframes: match.timeframes || [],
  }
})

function onExchangeChange() {
  const syms = availableSymbols.value
  for (const r of form.value.routes) {
    if (syms.length && !syms.includes(r.symbol)) {
      r.symbol = syms[0]
    }
  }
  autoSetDates()
}
function onSymbolChange() {
  autoSetDates()
}
function autoSetDates() {
  const range = dataRange.value
  if (range) {
    form.value.startDate = range.start
    form.value.endDate = range.end
  }
}

// ── Hyperparameter loading ──
async function loadBacktestHyperparams(name) {
  if (!name) { btHyperParams.value = []; btHyperParamsDefaults.value = []; return }
  try {
    const res = await api.getStrategyHyperparams(name)
    const hps = (res.hyperparameters || []).map(hp => ({
      name: hp.name,
      type: hp.type === 'categorical' ? 'categorical' : hp.type === 'int' ? 'int' : hp.type === 'float' ? 'float' : hp.type === 'str' ? 'str' : 'float',
      value: hp.default !== undefined ? hp.default : '',
      default: hp.default,
      min: hp.min,
      max: hp.max,
      description: hp.description || '',
      options: hp.options || undefined,
      depends_on: hp.depends_on || undefined,
    }))
    btHyperParams.value = hps
    btHyperParamsDefaults.value = JSON.parse(JSON.stringify(hps))
  } catch {
    btHyperParams.value = []
    btHyperParamsDefaults.value = []
  }
}

function isHpVisible(hp) {
  if (!hp.depends_on) return true
  for (const [key, allowedValues] of Object.entries(hp.depends_on)) {
    const parent = btHyperParams.value.find(p => p.name === key)
    if (parent && !allowedValues.includes(parent.value)) return false
  }
  return true
}

function resetBtHyperParams() {
  btHyperParams.value = JSON.parse(JSON.stringify(btHyperParamsDefaults.value))
}

function buildBtHyperparamsPayload() {
  const hp = {}
  if (btHyperParams.value.length) {
    for (const p of btHyperParams.value) {
      if (p.name && p.value !== '' && p.value !== undefined) {
        hp[p.name] = p.type === 'int' ? parseInt(p.value) : p.type === 'float' ? parseFloat(p.value) : String(p.value)
      }
    }
  } else {
    for (const p of btCustomHPs.value) {
      if (p.key && p.value !== '') hp[p.key] = Number(p.value)
    }
  }
  return Object.keys(hp).length ? hp : null
}

// Watch first route's strategy to auto-load hyperparameters
watch(() => form.value.routes[0]?.strategy, (newStrat, oldStrat) => {
  if (newStrat && newStrat !== oldStrat) {
    loadBacktestHyperparams(newStrat)
  }
})

// ── Exposure Table (pre-run) ──
let _exposureDebounce = null
async function fetchExposureTable() {
  const hp = buildBtHyperparamsPayload()
  const symbol = form.value.routes[0]?.symbol
  const exchange = form.value.exchange
  const balance = form.value.balance
  if (!symbol || !exchange) { exposureTable.value = []; return }
  try {
    const res = await api.getExposureTable({ exchange, symbol, hyperparameters: hp || {}, balance })
    exposureTable.value = res.table || []
    exposureHasTpSl.value = res.has_tp_sl || false
    exposureMeta.value = { contract_size: res.contract_size, leverage: res.leverage, price: res.price }
  } catch {
    exposureTable.value = []
  }
}

function debouncedFetchExposure() {
  clearTimeout(_exposureDebounce)
  _exposureDebounce = setTimeout(fetchExposureTable, 400)
}

// Re-fetch exposure when relevant form fields change
watch(() => btHyperParams.value, debouncedFetchExposure, { deep: true })
watch(() => form.value.routes[0]?.symbol, debouncedFetchExposure)
watch(() => form.value.exchange, debouncedFetchExposure)
watch(() => form.value.balance, debouncedFetchExposure)

// ── Metrics helpers ──
const hasResults = computed(() => metrics.value && Object.keys(metrics.value).length > 0)

const resultTabs = computed(() => {
  const tabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'charts', label: 'Charts' },
  ]
  if (hedgeSessions.value.length) {
    tabs.push({ id: 'sessions', label: 'Sessions', count: hedgeSessions.value.length })
  }
  tabs.push({ id: 'trades', label: 'Trades', count: trades.value.length })
  tabs.push({ id: 'costs', label: 'Costs' })
  tabs.push({ id: 'logs', label: 'Logs', count: backtestLogs.value.length || undefined })
  tabs.push({ id: 'strategy', label: 'Strategy Code' })
  return tabs
})

function pickMetrics(keys) {
  if (!metrics.value) return []
  return keys
    .filter(([key]) => key in metrics.value)
    .map(([key, label]) => ({ key, label, value: metrics.value[key] }))
}

const performanceMetrics = computed(() => pickMetrics([
  ['gross_pnl', 'Gross PnL (Trades)'],
  ['net_profit', 'Net Profit'],
  ['net_profit_percentage', 'Net Profit %'],
  ['annual_return', 'Annual Return'],
  ['win_rate', 'Win Rate'],
  ['profit_factor', 'Profit Factor'],
  ['expectancy', 'Expectancy'],
  ['starting_balance', 'Starting Balance'],
  ['finishing_balance', 'Finishing Balance'],
]))

const tradeStatsMetrics = computed(() => pickMetrics([
  ['total', 'Total Trades'],
  ['total_completed_trades', 'Completed Trades'],
  ['total_winning_trades', 'Winning Trades'],
  ['total_losing_trades', 'Losing Trades'],
  ['total_open_trades', 'Open Trades'],
  ['longs_count', 'Longs'],
  ['shorts_count', 'Shorts'],
  ['longs_percentage', 'Longs %'],
  ['shorts_percentage', 'Shorts %'],
  ['largest_winning_trade', 'Largest Win'],
  ['largest_losing_trade', 'Largest Loss'],
  ['winning_streak', 'Win Streak'],
  ['losing_streak', 'Lose Streak'],
  ['average_win', 'Avg Win'],
  ['average_loss', 'Avg Loss'],
  ['average_win_loss', 'Win/Loss Ratio'],
  ['fee', 'Total Fees'],
  ['open_pl', 'Open P&L'],
]))

const riskMetrics = computed(() => pickMetrics([
  ['max_drawdown', 'Max Drawdown'],
  ['max_drawdown_percentage', 'Max Drawdown %'],
  ['sharpe_ratio', 'Sharpe Ratio'],
  ['smart_sharpe', 'Smart Sharpe'],
  ['sortino_ratio', 'Sortino Ratio'],
  ['smart_sortino', 'Smart Sortino'],
  ['calmar_ratio', 'Calmar Ratio'],
  ['omega_ratio', 'Omega Ratio'],
  ['serenity_index', 'Serenity Index'],
  ['kelly_criterion', 'Kelly Criterion'],
  ['var_95', 'VaR 95%'],
  ['var_99', 'VaR 99%'],
  ['cvar_95', 'CVaR 95% (Tail Risk)'],
  ['cvar_99', 'CVaR 99% (Tail Risk)'],
  ['worst_floating_pnl', 'Worst Floating Loss'],
  ['peak_margin_used', 'Peak Margin Used'],
  ['peak_equity_usage_pct', 'Peak Equity Used %'],
  ['margin_closeouts', 'Margin Close-outs'],
  ['account_blown', 'Account Blown'],
]))

const forexMetrics = computed(() => pickMetrics([
  ['total_pips', 'Total Pips'],
  ['avg_pips_per_trade', 'Avg Pips/Trade'],
  ['total_spread_cost', 'Total Spread Cost'],
  ['total_swap_cost', 'Total Swap Cost'],
]))

const hedgeSessionMetrics = computed(() => pickMetrics([
  ['total_sessions', 'Total Sessions'],
  ['session_win_rate', 'Session Win Rate'],
  ['avg_session_win', 'Avg Session Win'],
  ['avg_session_loss', 'Avg Session Loss'],
  ['ev_per_session', 'EV / Session'],
  ['avg_legs_per_session', 'Avg Legs / Session'],
  ['max_legs_in_session', 'Max Legs in Session'],
  ['sessions_with_1_leg', 'Sessions with 1 Leg'],
  ['max_consecutive_session_wins', 'Max Consec. Session Wins'],
  ['max_consecutive_session_losses', 'Max Consec. Session Losses'],
]))

// Trades pagination
const totalTradesPages = computed(() => Math.ceil(trades.value.length / tradesPerPage))
const paginatedTrades = computed(() => {
  const start = (tradesPage.value - 1) * tradesPerPage
  return trades.value.slice(start, start + tradesPerPage)
})

// Sessions pagination
const totalSessionsPages = computed(() => Math.ceil(hedgeSessions.value.length / sessionsPerPage))
const paginatedSessions = computed(() => {
  const start = (sessionsPage.value - 1) * sessionsPerPage
  return hedgeSessions.value.slice(start, start + sessionsPerPage)
})

// Costs tab
const costTradesPage = ref(1)
const costTradesPerPage = 25
const totalCostTradesPages = computed(() => Math.ceil(trades.value.length / costTradesPerPage))
const paginatedCostTrades = computed(() => {
  const start = (costTradesPage.value - 1) * costTradesPerPage
  return trades.value.slice(start, start + costTradesPerPage)
})

const totalCosts = computed(() => {
  if (!metrics.value) return 0
  return Math.abs(metrics.value.fee || 0)
    + Math.abs(metrics.value.total_spread_cost || 0)
    + Math.abs(metrics.value.total_swap_cost || 0)
})

const costProfitRatio = computed(() => {
  if (!metrics.value || !metrics.value.net_profit) return null
  const np = Math.abs(metrics.value.net_profit)
  if (np === 0) return null
  return (totalCosts.value / np) * 100
})

const marginEvents = computed(() => {
  return backtestLogs.value.filter(l =>
    l.message && (
      l.message.includes('MARGIN CALL') ||
      l.message.includes('Insufficient margin') ||
      l.message.includes('margin') && l.message.includes('force-closed')
    )
  )
})

function fmtCost(val) {
  if (val === null || val === undefined || val === 0) return '$0.00'
  return (val < 0 ? '-' : '') + '$' + Math.abs(val).toFixed(2)
}

function toggleSession(sessionNum) {
  expandedSessions.value[sessionNum] = !expandedSessions.value[sessionNum]
}

function sessionOutcomeClass(outcome) {
  if (outcome === 'tp_hit' || outcome === 'bucket_hit') return 'text-green-400'
  if (outcome === 'max_levels') return 'text-red-400'
  return 'text-surface-400'
}

function sessionOutcomeLabel(outcome) {
  if (outcome === 'tp_hit') return 'TP Hit'
  if (outcome === 'bucket_hit') return 'Bucket Hit'
  if (outcome === 'max_levels') return 'Max Levels'
  if (outcome === 'standalone') return 'Single'
  return outcome || '-'
}

const currentStrategyCode = computed(() => {
  if (!sessionStrategyCodes.value) return null
  const keys = Object.keys(sessionStrategyCodes.value)
  const key = selectedStrategyCodeKey.value || keys[0]
  return sessionStrategyCodes.value[key] || null
})

const filteredSessions = computed(() => {
  let list = sessions.value
  if (sessionSearch.value) {
    const q = sessionSearch.value.toLowerCase()
    list = list.filter(s => (s.title || s.id || '').toLowerCase().includes(q))
  }
  if (sessionStatusFilter.value) {
    list = list.filter(s => s.status === sessionStatusFilter.value)
  }
  return list
})

// ── Workspace management ──
const _wsRefs = {
  form, running, error, errorTrace, message, currentTaskId, sessionId,
  progress, metrics, hyperparameters, generalInfo,
  equityCurve, floatingPnlCurve, marginUsageCurve,
  trades, hedgeSessions, exposureTable, exposureHasTpSl, exposureMeta, exposureSizeDisplay,
  activeTab, selectedRouteIdx, tradesPage, sessionsPage, expandedSessions, costTradesPage,
  logs, backtestLogs, logFilter,
  btHyperParams, btHyperParamsDefaults, btCustomHPs,
  sessionStrategyCodes, selectedStrategyCodeKey,
  btChartCandles, btChartRawCandles, btChartOrders, btChartVisible,
  selectedSession, openTabs, tabCache,
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
      exchange: form.value.exchange,
      routes: [{ symbol: 'EUR-USD', timeframe: '1m', strategy: strategies.value[0] || 'ForexMA' }],
      data_routes: [], startDate: '2024-01-01', endDate: '2024-06-01', balance: 10000, warmUpCandles: 240,
      debugMode: true, exportChart: true, exportTradingview: true, exportCsv: true, exportJson: false,
      fastMode: false, benchmark: false, costModel: true,
    },
    running: false, error: '', errorTrace: '', message: '',
    currentTaskId: null, sessionId: null,
    progress: { current: 0, eta: 0 },
    metrics: null, hyperparameters: null, generalInfo: null,
    equityCurve: [], floatingPnlCurve: null, marginUsageCurve: null,
    trades: [], hedgeSessions: [], exposureTable: [],
    activeTab: 'summary', selectedRouteIdx: 0, tradesPage: 1, sessionsPage: 1, expandedSessions: {}, costTradesPage: 1,
    logs: null, backtestLogs: [], logFilter: 'all',
    btHyperParams: [], btHyperParamsDefaults: [], btCustomHPs: [],
    sessionStrategyCodes: null, selectedStrategyCodeKey: '',
    btChartCandles: [], btChartRawCandles: [], btChartOrders: [], btChartVisible: false,
    selectedSession: null, openTabs: [], tabCache: {},
  }
}

function addWorkspace() {
  if (running.value) return
  wsCounter++
  const id = `ws-${wsCounter}`
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  workspaceTabs.value.push({ id, label: `Backtest ${wsCounter}`, running: false, hasResults: false })
  activeWorkspaceId.value = id
  _restoreWs(_freshDefaults())
  if (btTradeChartRef.value) btTradeChartRef.value.destroy()
}

function switchWorkspace(id) {
  if (id === activeWorkspaceId.value || running.value) return
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  activeWorkspaceId.value = id
  const cached = workspaceCache.value[id]
  if (cached) { _restoreWs(cached); delete workspaceCache.value[id] }
  else _restoreWs(_freshDefaults())
  if (btTradeChartRef.value) btTradeChartRef.value.destroy()
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
    if (btTradeChartRef.value) btTradeChartRef.value.destroy()
  }
}

function _updateActiveWsTab(props) {
  const tab = workspaceTabs.value.find(t => t.id === activeWorkspaceId.value)
  if (tab) Object.assign(tab, props)
}

// ── WebSocket handler ──
useWebSocket((msg) => {
  const { event, id, data } = msg
  // Note: msg.id is os.getpid() (integer), not the session UUID.
  // The 'backtest.' event prefix already namespaces messages, so no id filtering needed.

  if (event === 'backtest.progressbar') {
    progress.value = {
      current: data?.current || 0,
      eta: data?.estimated_remaining_seconds || 0,
    }
  } else if (event === 'backtest.equity_curve') {
    // Receive equity curve directly from WebSocket (may be compressed)
    if (data) {
      equityCurve.value = data
      nextTick(() => renderSyncedCharts())
    }
  } else if (event === 'backtest.floating_pnl_curve') {
    if (data) {
      floatingPnlCurve.value = data
      nextTick(() => renderSyncedCharts())
    }
  } else if (event === 'backtest.margin_usage_curve') {
    if (data) {
      marginUsageCurve.value = data
      nextTick(() => renderSyncedCharts())
    }
  } else if (event === 'backtest.trades') {
    // Receive trades directly from WebSocket (may be compressed)
    if (data) {
      trades.value = Array.isArray(data) ? data : []
      tradesPage.value = 1
    }
  } else if (event === 'backtest.sessions') {
    if (data) {
      hedgeSessions.value = Array.isArray(data) ? data : []
      sessionsPage.value = 1
    }
  } else if (event === 'backtest.alert') {
    if (data?.type === 'error') {
      error.value = data?.message || 'Backtest encountered an error'
    } else {
      message.value = data?.message || ''
    }
  } else if (event === 'backtest.metrics') {
    metrics.value = data
    running.value = false
    if (!error.value) message.value = 'Backtest completed!'
    progress.value = { current: 100, eta: 0 }
    sessionId.value = currentTaskId.value
    _updateActiveWsTab({ running: false, hasResults: true })
    setTimeout(loadSessions, 1000)
    // Also fetch from DB as a fallback (DB is updated before WS now)
    loadSessionResults()
  } else if (event === 'backtest.backtest_logs') {
    if (data) {
      backtestLogs.value = Array.isArray(data) ? data : []
      logs.value = formatBacktestLogs(backtestLogs.value, logFilter.value)
    }
  } else if (event === 'backtest.hyperparameters') {
    hyperparameters.value = data
  } else if (event === 'backtest.general_info') {
    generalInfo.value = data
  } else if (event === 'backtest.exception') {
    error.value = data?.error || 'Backtest failed'
    errorTrace.value = data?.traceback || ''
    running.value = false
    progress.value = { current: 0, eta: 0 }
    _updateActiveWsTab({ running: false })
  } else if (event === 'backtest.termination') {
    running.value = false
    message.value = 'Backtest was terminated.'
    progress.value = { current: 0, eta: 0 }
    _updateActiveWsTab({ running: false })
  } else if (event === 'backtest.notification') {
    if (data?.type === 'error') {
      error.value = data?.message || ''
    }
  }
})

async function loadSessionResults() {
  if (!sessionId.value) return
  try {
    const res = await api.getBacktestSession(sessionId.value)
    const s = res.session
    if (s) {
      // Only update if we don't already have data from WebSocket
      // Handle bundled format from DB: { equity, floating_pnl, margin_usage }
      if (s.equity_curve && !equityCurve.value.length) {
        if (s.equity_curve.equity) {
          equityCurve.value = s.equity_curve.equity
          floatingPnlCurve.value = s.equity_curve.floating_pnl || null
          marginUsageCurve.value = s.equity_curve.margin_usage || null
        } else if (s.equity_curve.length) {
          equityCurve.value = s.equity_curve
        }
      }
      if (s.trades && s.trades.length && !trades.value.length) {
        trades.value = s.trades
        tradesPage.value = 1
        if (!hedgeSessions.value.length) {
          hedgeSessions.value = buildSessionsFromTrades(s.trades)
        }
      }
      if (s.hyperparameters && s.hyperparameters.length && !hyperparameters.value?.length) {
        hyperparameters.value = s.hyperparameters
      }
      await nextTick()
      if (activeTab.value === 'charts') {
        renderSyncedCharts()
      }
      // Auto-fetch chart data for the Chart tab
      if (!btChartVisible.value && sessionId.value) {
        loadBtChartData()
      }
    }
  } catch { /* ignore */ }
}

// ── Format helpers ──
function statusBadgeClass(status) {
  if (status === 'finished') return 'bg-green-500/20 text-green-400'
  if (status === 'running') return 'bg-yellow-500/20 text-yellow-400'
  if (status === 'cancelled' || status === 'failed') return 'bg-red-500/20 text-red-400'
  return 'bg-surface-700 text-surface-400'
}

function sessionLabel(s) {
  let state = s.state
  if (state) {
    if (typeof state === 'string') {
      try { state = JSON.parse(state) } catch { state = null }
    }
    const routes = state?.routes || []
    if (Array.isArray(routes) && routes.length) {
      const r = routes[0]
      return `${r.strategy || ''} ${r.symbol || ''}`.trim() || s.id?.slice(0, 8)
    }
  }
  return s.id?.slice(0, 8)
}

function formatSessionRoutes(state) {
  if (!state) return ''
  if (typeof state === 'string') {
    try { state = JSON.parse(state) } catch { return state }
  }
  const routes = state.routes || []
  if (Array.isArray(routes)) return routes.map(r => `${r.strategy || ''} ${r.symbol || ''} ${r.timeframe || ''}`).join(', ')
  return ''
}

function buildSessionsFromTrades(tradesList) {
  // Group trades by meta.session into hedge sessions (client-side fallback)
  const map = {}
  const standalone = []
  for (const t of tradesList) {
    const sn = t.meta?.session
    if (sn == null) { standalone.push(t); continue }
    if (!map[sn]) {
      map[sn] = {
        session: sn, trades: [], total_pnl: 0, total_fee: 0,
        opened_at: t.opened_at, closed_at: null, outcome: null, levels: 0, trade_count: 0,
      }
    }
    const s = map[sn]
    s.trades.push(t)
    s.total_pnl += (t.pnl || t.PNL || 0)
    s.total_fee += (t.fee || 0)
    s.levels = Math.max(s.levels, t.meta?.level || 0)
    s.closed_at = t.closed_at
    s.outcome = t.meta?.exit_reason || s.outcome
  }
  const result = Object.keys(map).sort((a, b) => a - b).map(k => {
    const s = map[k]
    s.trade_count = s.trades.length
    s.total_pnl = parseFloat(s.total_pnl.toFixed(6))
    s.total_fee = parseFloat(s.total_fee.toFixed(6))
    return s
  })
  standalone.forEach((t, i) => {
    result.push({
      session: `standalone-${i + 1}`, trades: [t], total_pnl: t.pnl || t.PNL || 0,
      total_fee: t.fee || 0, opened_at: t.opened_at, closed_at: t.closed_at,
      outcome: 'standalone', levels: 0, trade_count: 1,
    })
  })
  return result
}

function formatKey(key) {
  return key.replace(/_/g, ' ')
}

function formatMetric(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'number') {
    if (isNaN(val)) return '-'
    if (Number.isInteger(val)) return val.toLocaleString()
    return val.toFixed(2)
  }
  return val
}

function formatPrice(val) {
  if (val === null || val === undefined) return '-'
  return typeof val === 'number' ? val.toFixed(5) : val
}

function formatDate(d) {
  if (!d) return ''
  try { return new Date(d).toLocaleDateString() } catch { return d }
}

function formatTimestamp(ts) {
  if (!ts) return '-'
  try {
    const d = new Date(typeof ts === 'number' ? ts : ts)
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch { return ts }
}

function metricColor(key, val) {
  if (typeof val === 'boolean') return val ? 'text-red-400' : 'text-green-400'
  if (typeof val !== 'number') return 'text-surface-100'
  if (key.includes('profit') || key === 'gross_pnl' || key === 'net_profit' || key === 'annual_return' || key === 'net_profit_percentage') {
    return val >= 0 ? 'text-green-400' : 'text-red-400'
  }
  if (key.includes('drawdown') || key === 'worst_floating_pnl') return 'text-red-400'
  if (key === 'win_rate' || key === 'session_win_rate') return val >= 0.5 ? 'text-green-400' : 'text-amber-400'
  if (key === 'profit_factor') return val >= 1 ? 'text-green-400' : 'text-red-400'
  if (key === 'kelly_criterion') return val > 0 ? 'text-green-400' : 'text-red-400'
  if (key === 'ev_per_session' || key === 'avg_session_win') return val >= 0 ? 'text-green-400' : 'text-red-400'
  if (key === 'avg_session_loss') return 'text-red-400'
  if (key === 'var_95' || key === 'var_99' || key === 'cvar_95' || key === 'cvar_99') return 'text-amber-400'
  if (key === 'margin_closeouts') return val > 0 ? 'text-red-400' : 'text-green-400'
  return 'text-surface-100'
}

function downloadUrl(type) {
  const token = localStorage.getItem('te_token') || ''
  return `/download/backtest/${type}/${sessionId.value}?token=${token}`
}

// ── Chart data helpers ──
function extractEquityValues(data) {
  if (!data || !data.length) return []
  if (data[0] && typeof data[0] === 'object' && 'data' in data[0]) {
    return data[0].data.map(p => p.value ?? p.balance ?? 0)
  }
  if (typeof data[0] === 'number') return data
  return data.map(d => d.value ?? d.balance ?? d[1] ?? 0)
}

function extractSeriesData(curveData) {
  // Converts backend curve format to lightweight-charts [{time, value}]
  if (!curveData) return []
  // Single series object: { name, data: [{time, value}], color }
  if (curveData.data) {
    return curveData.data.map(p => ({
      time: typeof p.time === 'number' ? (p.time > 1e12 ? Math.floor(p.time / 1000) : p.time) : p.time,
      value: p.value ?? p.balance ?? 0,
    }))
  }
  // Array of series objects (equity_curve format)
  if (Array.isArray(curveData) && curveData[0]?.data) {
    return curveData[0].data.map(p => ({
      time: typeof p.time === 'number' ? (p.time > 1e12 ? Math.floor(p.time / 1000) : p.time) : p.time,
      value: p.value ?? p.balance ?? 0,
    }))
  }
  return []
}

// ── Synced Lightweight Charts ──
const lwCharts = { equity: null, pnl: null, margin: null }
const lwSeries = { equity: null, pnl: null, margin: null }
let syncingCharts = false

function chartTheme() {
  return {
    layout: {
      background: { type: ColorType.Solid, color: '#1a1b23' },
      textColor: '#666',
      fontSize: 10,
    },
    grid: {
      vertLines: { color: '#1e1f2b' },
      horzLines: { color: '#1e1f2b' },
    },
    crosshair: { mode: 0 },
    rightPriceScale: {
      borderColor: '#2a2b33',
      scaleMargins: { top: 0.1, bottom: 0.1 },
    },
    timeScale: {
      borderColor: '#2a2b33',
      timeVisible: false,
      secondsVisible: false,
    },
    handleScroll: { vertTouchDrag: false },
  }
}

function destroySyncedCharts() {
  for (const key of ['equity', 'pnl', 'margin']) {
    if (lwCharts[key]) {
      lwCharts[key].remove()
      lwCharts[key] = null
      lwSeries[key] = null
    }
  }
}

function createSyncedChart(el, opts = {}) {
  if (!el) return null
  const chart = createChart(el, {
    ...chartTheme(),
    width: el.clientWidth,
    height: el.clientHeight,
    ...opts,
  })
  return chart
}

function syncVisibleRange(sourceKey) {
  if (syncingCharts) return
  syncingCharts = true
  const source = lwCharts[sourceKey]
  if (!source) { syncingCharts = false; return }
  const range = source.timeScale().getVisibleLogicalRange()
  if (!range) { syncingCharts = false; return }
  for (const key of ['equity', 'pnl', 'margin']) {
    if (key !== sourceKey && lwCharts[key]) {
      lwCharts[key].timeScale().setVisibleLogicalRange(range)
    }
  }
  syncingCharts = false
}

function syncCrosshair(sourceKey, param) {
  if (syncingCharts) return
  syncingCharts = true
  for (const key of ['equity', 'pnl', 'margin']) {
    if (key !== sourceKey && lwCharts[key]) {
      if (param.time) {
        lwCharts[key].setCrosshairPosition(undefined, param.time, lwSeries[key])
      } else {
        lwCharts[key].clearCrosshairPosition()
      }
    }
  }
  syncingCharts = false
}

function renderSyncedCharts() {
  if (activeTab.value !== 'charts') return
  const eqData = extractSeriesData(equityCurve.value?.length ? equityCurve.value : null)
  if (!eqData.length) return

  destroySyncedCharts()

  // Equity chart
  if (equityChartEl.value) {
    lwCharts.equity = createSyncedChart(equityChartEl.value)
    const isPositive = eqData[eqData.length - 1].value >= eqData[0].value
    lwSeries.equity = lwCharts.equity.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: eqData[0].value },
      topLineColor: '#4ade80',
      topFillColor1: 'rgba(74,222,128,0.15)',
      topFillColor2: 'rgba(74,222,128,0.02)',
      bottomLineColor: '#f87171',
      bottomFillColor1: 'rgba(248,113,113,0.02)',
      bottomFillColor2: 'rgba(248,113,113,0.15)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    lwSeries.equity.setData(eqData)
    lwCharts.equity.timeScale().fitContent()
    lwCharts.equity.timeScale().subscribeVisibleLogicalRangeChange(() => syncVisibleRange('equity'))
    lwCharts.equity.subscribeCrosshairMove((p) => syncCrosshair('equity', p))
  }

  // Floating PnL chart
  const pnlData = extractSeriesData(floatingPnlCurve.value)
  if (floatingPnlChartEl.value && pnlData.length) {
    lwCharts.pnl = createSyncedChart(floatingPnlChartEl.value)
    lwSeries.pnl = lwCharts.pnl.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: 0 },
      topLineColor: '#fbbf24',
      topFillColor1: 'rgba(251,191,36,0.15)',
      topFillColor2: 'rgba(251,191,36,0.02)',
      bottomLineColor: '#f87171',
      bottomFillColor1: 'rgba(248,113,113,0.02)',
      bottomFillColor2: 'rgba(248,113,113,0.15)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    lwSeries.pnl.setData(pnlData)
    lwCharts.pnl.timeScale().fitContent()
    lwCharts.pnl.timeScale().subscribeVisibleLogicalRangeChange(() => syncVisibleRange('pnl'))
    lwCharts.pnl.subscribeCrosshairMove((p) => syncCrosshair('pnl', p))
  } else if (floatingPnlChartEl.value) {
    // No PnL data — show zero line matching equity timestamps
    lwCharts.pnl = createSyncedChart(floatingPnlChartEl.value)
    lwSeries.pnl = lwCharts.pnl.addSeries(LineSeries, {
      color: '#fbbf24', lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    lwSeries.pnl.setData(eqData.map(p => ({ time: p.time, value: 0 })))
    lwCharts.pnl.timeScale().fitContent()
    lwCharts.pnl.timeScale().subscribeVisibleLogicalRangeChange(() => syncVisibleRange('pnl'))
    lwCharts.pnl.subscribeCrosshairMove((p) => syncCrosshair('pnl', p))
  }

  // Margin Usage chart
  const marginData = extractSeriesData(marginUsageCurve.value)
  if (marginChartEl.value && marginData.length) {
    lwCharts.margin = createSyncedChart(marginChartEl.value)
    lwSeries.margin = lwCharts.margin.addSeries(AreaSeries, {
      lineColor: '#fb7185',
      topColor: 'rgba(251,113,133,0.25)',
      bottomColor: 'rgba(251,113,133,0.02)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    lwSeries.margin.setData(marginData)
    lwCharts.margin.timeScale().fitContent()
    lwCharts.margin.timeScale().subscribeVisibleLogicalRangeChange(() => syncVisibleRange('margin'))
    lwCharts.margin.subscribeCrosshairMove((p) => syncCrosshair('margin', p))
  } else if (marginChartEl.value) {
    lwCharts.margin = createSyncedChart(marginChartEl.value)
    lwSeries.margin = lwCharts.margin.addSeries(LineSeries, {
      color: '#fb7185', lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    lwSeries.margin.setData(eqData.map(p => ({ time: p.time, value: 0 })))
    lwCharts.margin.timeScale().fitContent()
    lwCharts.margin.timeScale().subscribeVisibleLogicalRangeChange(() => syncVisibleRange('margin'))
    lwCharts.margin.subscribeCrosshairMove((p) => syncCrosshair('margin', p))
  }
}

function fitAllCharts() {
  for (const key of ['equity', 'pnl', 'margin']) {
    if (lwCharts[key]) lwCharts[key].timeScale().fitContent()
  }
}

// Session detail still uses simple canvas for equity
function renderEquityChart(el, data) {
  if (!el || !data || !data.length) return
  // Handle bundled format from DB
  let curveData = data
  if (data.equity) curveData = data.equity
  const values = extractEquityValues(curveData)
  if (!values.length) return
  const timestamps = extractSeriesData(curveData)

  const canvas = document.createElement('canvas')
  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'
  el.innerHTML = ''
  el.appendChild(canvas)

  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const range = maxVal - minVal || 1
  const padding = 50
  const rightPad = 15

  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 5; i++) {
    const y = padding + (h - padding * 2) * (i / 5)
    ctx.strokeStyle = '#2a2b33'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(padding, y)
    ctx.lineTo(w - rightPad, y)
    ctx.stroke()
    ctx.fillStyle = '#666'
    const val = maxVal - range * (i / 5)
    ctx.fillText(val.toFixed(0), padding - 5, y + 4)
  }

  if (timestamps.length > 1) {
    ctx.textAlign = 'center'
    ctx.fillStyle = '#555'
    const labelCount = Math.min(6, timestamps.length)
    for (let i = 0; i < labelCount; i++) {
      const idx = Math.floor(i * (timestamps.length - 1) / (labelCount - 1))
      const x = padding + (w - padding - rightPad) * (idx / (values.length - 1))
      const t = timestamps[idx]
      if (t?.time) {
        const d = new Date(t.time * 1000)
        ctx.fillText(d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), x, h - 10)
      }
    }
  }

  const lineColor = values[values.length - 1] >= values[0] ? '#4ade80' : '#f87171'
  ctx.strokeStyle = lineColor
  ctx.lineWidth = 1.5
  ctx.lineJoin = 'round'
  ctx.beginPath()
  for (let i = 0; i < values.length; i++) {
    const x = padding + (w - padding - rightPad) * (i / Math.max(values.length - 1, 1))
    const y = padding + (h - padding * 2) * (1 - (values[i] - minVal) / range)
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()
  const lastX = padding + (w - padding - rightPad)
  const baseY = padding + (h - padding * 2)
  ctx.lineTo(lastX, baseY)
  ctx.lineTo(padding, baseY)
  ctx.closePath()
  ctx.fillStyle = lineColor + '14'
  ctx.fill()
}

// ── Actions ──
async function runBacktest() {
  const strategy = form.value.routes[0]?.strategy || 'Backtest'
  const symbol = form.value.routes[0]?.symbol || ''
  _updateActiveWsTab({ label: `${strategy} ${symbol}`.trim(), running: true, hasResults: false })
  error.value = ''
  errorTrace.value = ''
  message.value = ''
  metrics.value = null
  hyperparameters.value = null
  generalInfo.value = null
  equityCurve.value = []
  floatingPnlCurve.value = null
  marginUsageCurve.value = null
  trades.value = []
  hedgeSessions.value = []
  exposureTable.value = []
  logs.value = null
  backtestLogs.value = []
  logFilter.value = 'all'
  sessionStrategyCodes.value = null
  btChartCandles.value = []
  btChartRawCandles.value = []
  btChartOrders.value = []
  btChartVisible.value = false
  if (btTradeChartRef.value) btTradeChartRef.value.destroy()
  progress.value = { current: 0, eta: 0 }
  running.value = true
  activeTab.value = 'summary'
  tradesPage.value = 1
  sessionsPage.value = 1
  expandedSessions.value = {}

  const id = crypto.randomUUID()
  currentTaskId.value = id
  sessionId.value = null

  const routes = form.value.routes.map(r => ({
    exchange: form.value.exchange,
    symbol: r.symbol,
    timeframe: r.timeframe,
    strategy: r.strategy,
  }))

  const dataRoutes = form.value.data_routes.map(dr => ({
    exchange: form.value.exchange,
    symbol: dr.symbol,
    timeframe: dr.timeframe,
  }))

  try {
    await api.runBacktest({
      id,
      exchange: form.value.exchange,
      routes,
      data_routes: dataRoutes,
      config: {
        warm_up_candles: form.value.warmUpCandles,
        logging: {
          order_submission: true,
          order_cancellation: true,
          order_execution: true,
          position_opened: true,
          position_increased: true,
          position_reduced: true,
          position_closed: true,
          shorter_period_candles: false,
          trading_candles: false,
          balance_update: true,
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
      finish_date: form.value.endDate,
      debug_mode: form.value.debugMode,
      export_chart: form.value.exportChart,
      export_tradingview: form.value.exportTradingview,
      export_csv: form.value.exportCsv,
      export_json: form.value.exportJson,
      fast_mode: form.value.fastMode,
      benchmark: form.value.benchmark,
      cost_model: form.value.costModel,
      hyperparameters: buildBtHyperparamsPayload(),
    })
  } catch (e) {
    error.value = e.message
    running.value = false
  }
}

async function cancelBacktest() {
  if (!currentTaskId.value) return
  try {
    await api.cancelBacktest(currentTaskId.value)
    message.value = 'Cancellation requested...'
  } catch (e) {
    error.value = e.message
  }
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await api.getBacktestSessions({ limit: 50 })
    sessions.value = res.sessions || []
  } catch {
    sessions.value = []
  } finally {
    loadingSessions.value = false
  }
}

async function viewSession(s) {
  // Add to open tabs if not already there
  if (!openTabs.value.find(t => t.id === s.id)) {
    openTabs.value.push({ id: s.id, label: s.title || s.id?.slice(0, 8) })
  }
  // Cache current session before switching
  if (selectedSession.value && selectedSession.value.id !== s.id) {
    tabCache.value[selectedSession.value.id] = selectedSession.value
  }
  // Load from cache or API
  if (tabCache.value[s.id]) {
    selectedSession.value = tabCache.value[s.id]
  } else {
    try {
      const res = await api.getBacktestSession(s.id)
      selectedSession.value = res.session || s
      tabCache.value[s.id] = selectedSession.value
    } catch {
      selectedSession.value = s
    }
  }
  editingNotes.value = false
  await nextTick()
  const ec = selectedSession.value?.equity_curve
  if (ec && (ec.length || ec.equity)) {
    renderEquityChart(sessionEquityEl.value, ec)
  }
}

function switchToTab(id) {
  const s = tabCache.value[id] || sessions.value.find(x => x.id === id)
  if (s) viewSession(s)
}

function closeTab(id) {
  openTabs.value = openTabs.value.filter(t => t.id !== id)
  delete tabCache.value[id]
  if (selectedSession.value?.id === id) {
    if (openTabs.value.length > 0) {
      switchToTab(openTabs.value[openTabs.value.length - 1].id)
    } else {
      selectedSession.value = null
    }
  }
}

async function removeSession(s) {
  try {
    await api.removeBacktestSession(s.id)
    sessions.value = sessions.value.filter(x => x.id !== s.id)
    closeTab(s.id)
  } catch (e) {
    error.value = e.message
  }
}

async function purgeSessions() {
  try {
    await api.purgeBacktestSessions(purgeDays.value)
    showPurgeConfirm.value = false
    await loadSessions()
  } catch (e) {
    error.value = e.message
  }
}

function editSessionNotes() {
  if (!selectedSession.value) return
  noteTitle.value = selectedSession.value.title || ''
  noteDescription.value = selectedSession.value.description || ''
  editingNotes.value = true
}

async function saveNotes() {
  if (!selectedSession.value) return
  savingNotes.value = true
  try {
    await api.updateBacktestNotes(selectedSession.value.id, noteTitle.value, noteDescription.value)
    selectedSession.value.title = noteTitle.value
    selectedSession.value.description = noteDescription.value
    editingNotes.value = false
    await loadSessions()
  } catch (e) {
    error.value = e.message
  } finally {
    savingNotes.value = false
  }
}

function loadSessionAsForm() {
  if (!selectedSession.value?.state) return
  let state = selectedSession.value.state
  if (typeof state === 'string') {
    try { state = JSON.parse(state) } catch { return }
  }
  if (state.routes) {
    form.value.routes = state.routes.map(r => ({
      symbol: r.symbol || 'EUR-USD',
      timeframe: r.timeframe || '1h',
      strategy: r.strategy || '',
    }))
  }
  if (state.exchange) form.value.exchange = state.exchange
  if (state.start_date) form.value.startDate = state.start_date
  if (state.finish_date) form.value.endDate = state.finish_date
  selectedSession.value = null
}

function formatTimestampShort(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toISOString().replace('T', ' ').slice(0, 19)
}

function formatBacktestLogs(rawLogs, filter) {
  if (!rawLogs || !rawLogs.length) return null
  const filtered = filter === 'all' ? rawLogs : rawLogs.filter(l => l.type === filter)
  if (!filtered.length) return 'No logs matching filter.'
  return filtered.map(l => {
    const ts = formatTimestampShort(l.timestamp)
    const tag = (l.type || 'info').toUpperCase()
    return `[${ts}] [${tag}] ${l.message}`
  }).join('\n')
}

function onLogFilterChange() {
  logs.value = formatBacktestLogs(backtestLogs.value, logFilter.value)
}

async function loadLogs() {
  if (!sessionId.value) return
  loadingLogs.value = true
  try {
    // Try loading structured logs from DB first
    const res = await api.getBacktestSessionLogs(sessionId.value)
    if (res.logs && res.logs.length) {
      backtestLogs.value = res.logs
      logs.value = formatBacktestLogs(res.logs, logFilter.value)
    } else {
      // Fallback to file-based logs (debug mode)
      const fileRes = await api.getBacktestLogs(sessionId.value)
      logs.value = fileRes.content || 'No logs found.'
    }
  } catch (e) {
    logs.value = `Failed to load logs: ${e.message}`
  } finally {
    loadingLogs.value = false
  }
}

function copyLogs() {
  if (logs.value) navigator.clipboard.writeText(logs.value)
}

async function loadStrategyCode() {
  if (!sessionId.value) return
  loadingStrategyCode.value = true
  try {
    const res = await api.getBacktestStrategyCode(sessionId.value)
    sessionStrategyCodes.value = res.strategy_code || {}
    const keys = Object.keys(sessionStrategyCodes.value)
    if (keys.length) selectedStrategyCodeKey.value = keys[0]
  } catch (e) {
    sessionStrategyCodes.value = { error: `Failed: ${e.message}` }
  } finally {
    loadingStrategyCode.value = false
  }
}

function copyStrategyCode() {
  if (currentStrategyCode.value) navigator.clipboard.writeText(currentStrategyCode.value)
}

async function loadChartData() {
  if (!selectedSession.value) return
  loadingChart.value = true
  try {
    const res = await api.getBacktestChartData(selectedSession.value.id)
    if (res.chart_data) {
      selectedSession.value = { ...selectedSession.value, chart_data: res.chart_data }
    }
  } catch (e) {
    error.value = `Chart load failed: ${e.message}`
  } finally {
    loadingChart.value = false
  }
}

function renderCandleChart(el, route, routeIdx) {
  if (!el || el.dataset.rendered) return
  el.dataset.rendered = '1'
  const candles = route.candles
  if (!candles || !candles.length) return

  // Find matching orders
  const chartData = selectedSession.value?.chart_data
  const ordersRoute = chartData?.orders_chart?.[routeIdx]
  const orders = ordersRoute?.orders || []

  const canvas = document.createElement('canvas')
  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'
  el.innerHTML = ''
  el.appendChild(canvas)

  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const padding = { top: 20, right: 60, bottom: 30, left: 10 }
  const chartW = w - padding.left - padding.right
  const chartH = h - padding.top - padding.bottom

  // Find price range
  let minP = Infinity, maxP = -Infinity
  for (const c of candles) {
    if (c.low < minP) minP = c.low
    if (c.high > maxP) maxP = c.high
  }
  const priceRange = maxP - minP || 1
  minP -= priceRange * 0.02
  maxP += priceRange * 0.02
  const fullRange = maxP - minP

  const toY = (price) => padding.top + chartH * (1 - (price - minP) / fullRange)
  const barW = Math.max(1, (chartW / candles.length) * 0.7)
  const gap = chartW / candles.length

  // Background
  ctx.fillStyle = '#0f1117'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = '#1a1d2a'
  ctx.lineWidth = 0.5
  for (let i = 0; i <= 5; i++) {
    const y = padding.top + chartH * (i / 5)
    ctx.beginPath()
    ctx.moveTo(padding.left, y)
    ctx.lineTo(w - padding.right, y)
    ctx.stroke()
    ctx.fillStyle = '#555'
    ctx.font = '9px monospace'
    ctx.textAlign = 'left'
    const price = maxP - fullRange * (i / 5)
    ctx.fillText(price.toFixed(price > 100 ? 2 : 5), w - padding.right + 4, y + 3)
  }

  // Candles
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i]
    const x = padding.left + gap * i + gap / 2
    const isGreen = c.close >= c.open

    // Wick
    ctx.strokeStyle = isGreen ? '#4ade80' : '#f87171'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, toY(c.high))
    ctx.lineTo(x, toY(c.low))
    ctx.stroke()

    // Body
    const bodyTop = toY(Math.max(c.open, c.close))
    const bodyBot = toY(Math.min(c.open, c.close))
    const bodyH = Math.max(1, bodyBot - bodyTop)
    ctx.fillStyle = isGreen ? '#4ade8080' : '#f8717180'
    ctx.fillRect(x - barW / 2, bodyTop, barW, bodyH)
  }

  // Order markers — handles _executed_orders format {time, position, color, shape, text}
  if (orders.length) {
    const candleTimes = candles.map(c => c.time)
    for (const o of orders) {
      const oTime = o.time || (o.executed_at ? (typeof o.executed_at === 'number' ? Math.floor(o.executed_at / 1000) - 60 : o.executed_at) : null)
      if (!oTime) continue

      let idx = candleTimes.findIndex(t => t >= oTime)
      if (idx < 0) idx = candles.length - 1
      const x = padding.left + gap * idx + gap / 2
      const c2 = candles[idx]

      // Determine direction from marker format or raw order format
      const isBuy = o.shape === 'arrowUp' || o.position === 'belowBar' || o.side === 'buy'
      const markerY = o.price ? toY(o.price) : (isBuy ? toY(c2.low) : toY(c2.high))

      ctx.fillStyle = o.color || (isBuy ? '#4ade80' : '#f87171')
      ctx.beginPath()
      if (isBuy) {
        ctx.moveTo(x, markerY + 8)
        ctx.lineTo(x - 5, markerY + 14)
        ctx.lineTo(x + 5, markerY + 14)
      } else {
        ctx.moveTo(x, markerY - 8)
        ctx.lineTo(x - 5, markerY - 14)
        ctx.lineTo(x + 5, markerY - 14)
      }
      ctx.closePath()
      ctx.fill()

      if (o.text) {
        ctx.fillStyle = '#aaa'
        ctx.font = '8px monospace'
        ctx.textAlign = 'center'
        ctx.fillText(o.text, x, isBuy ? markerY + 22 : markerY - 18)
      }
    }
  }

  // X-axis dates
  ctx.fillStyle = '#555'
  ctx.font = '9px monospace'
  ctx.textAlign = 'center'
  const dateCount = Math.min(6, candles.length)
  for (let i = 0; i < dateCount; i++) {
    const idx = Math.floor(i * (candles.length - 1) / Math.max(dateCount - 1, 1))
    const x = padding.left + gap * idx + gap / 2
    const d = new Date(candles[idx].time * 1000)
    ctx.fillText(d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), x, h - 8)
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

// ── Strategy editor (same as before) ──
async function openStrategyEditor() {
  const name = form.value.routes[0]?.strategy
  if (!name) return
  try {
    const res = await api.getStrategy(name)
    strategyCode.value = res.data?.content || res.content || ''
    editingStrategy.value = name
    strategyMsg.value = ''
    strategyMsgErr.value = false
    strategyRefineInput.value = ''
  } catch (e) {
    strategyMsg.value = e.message
    strategyMsgErr.value = true
  }
}

async function saveStrategyCode() {
  strategySaving.value = true
  strategyMsg.value = ''
  try {
    await api.saveStrategy(editingStrategy.value, strategyCode.value)
    strategyMsg.value = 'Saved!'
    strategyMsgErr.value = false
  } catch (e) {
    strategyMsg.value = e.message
    strategyMsgErr.value = true
  } finally {
    strategySaving.value = false
  }
}

async function saveAndRetry() {
  strategySaving.value = true
  strategyMsg.value = ''
  try {
    await api.saveStrategy(editingStrategy.value, strategyCode.value)
    strategyMsg.value = 'Saved! Re-running backtest...'
    strategyMsgErr.value = false
    editingStrategy.value = null
    error.value = ''
    errorTrace.value = ''
    await runBacktest()
  } catch (e) {
    strategyMsg.value = e.message
    strategyMsgErr.value = true
  } finally {
    strategySaving.value = false
  }
}

async function refineFromBacktest() {
  strategyRefining.value = true
  strategyMsg.value = ''
  try {
    const feedback = strategyRefineInput.value + (error.value ? `\n\nBacktest error: ${error.value}` : '') + (errorTrace.value ? `\nTraceback: ${errorTrace.value}` : '')
    const res = await api.aiRefineStrategy({
      name: editingStrategy.value,
      feedback,
      backtest_results: metrics.value || null,
    })
    if (res.valid && res.code) {
      strategyCode.value = res.code
      strategyMsg.value = 'AI refined and saved!'
      strategyMsgErr.value = false
      strategyRefineInput.value = ''
    } else {
      strategyMsg.value = res.errors?.join(', ') || res.error || 'Refinement failed'
      strategyMsgErr.value = true
    }
  } catch (e) {
    strategyMsg.value = e.message
    strategyMsgErr.value = true
  } finally {
    strategyRefining.value = false
  }
}

async function loadBtChartData() {
  if (!sessionId.value) return
  try {
    const res = await api.getBacktestChartData(sessionId.value)
    if (res.chart_data?.candles_chart?.length) {
      const cd = res.chart_data.candles_chart[0]
      btChartCandles.value = cd.candles || []
      btChartRawCandles.value = cd.candles_1m || []
      btChartOrders.value = res.chart_data.orders_chart?.[0]?.orders || []
      btChartVisible.value = true
    }
  } catch { /* chart data not available */ }
}

// Chart re-render on tab switch
watch(activeTab, async (tab) => {
  if (tab === 'charts') {
    await nextTick()
    if (btChartVisible.value && btTradeChartRef.value) {
      btTradeChartRef.value.renderCandles()
      btTradeChartRef.value.renderEquity()
    }
    if (equityCurve.value.length) {
      renderSyncedCharts()
    }
  }
})

onBeforeUnmount(() => {
  destroySyncedCharts()
})

onMounted(async () => {
  try {
    const [bRes, sRes] = await Promise.all([
      api.getBacktestingBrokers(),
      api.getStrategies().catch(() => ({ data: [] })),
    ])
    brokers.value = bRes.data || []
    strategies.value = sRes.data || sRes.strategies || []
    form.value.exchange = defaultBrokerId(brokers.value)
    if (strategies.value.length > 0) form.value.routes[0].strategy = strategies.value[0]
  } catch (e) {
    console.error(e)
  }

  await loadExistingCandles()
  onExchangeChange()
  loadSessions()

  // Load hyperparameters for the initial strategy
  if (form.value.routes[0]?.strategy) {
    loadBacktestHyperparams(form.value.routes[0].strategy)
  }

  try {
    const llmRes = await api.llmStatus()
    llmConfigured.value = llmRes.configured
  } catch { /* ignore */ }
})
</script>
