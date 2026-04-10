<template>
  <div>
    <!-- Header + Page Tabs -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Backtest</h1>
        <p class="text-xs text-surface-500 mt-0.5">Run strategies against historical data to measure performance and validate logic</p>
      </div>
      <div class="flex items-center gap-3">
        <!-- Page-level tabs: New Run / History -->
        <div class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg">
          <button @click="pageTab = 'run'" class="px-3 py-1.5 text-xs rounded-md transition-colors"
            :class="pageTab === 'run' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            <span class="flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 010 1.972l-11.54 6.347a1.125 1.125 0 01-1.667-.986V5.653z"/></svg>
              New Run
            </span>
          </button>
          <button @click="pageTab = 'history'; loadSessions()" class="px-3 py-1.5 text-xs rounded-md transition-colors"
            :class="pageTab === 'history' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            <span class="flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              History
              <span v-if="runningSessions.length" class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
              <span v-if="sessions.length" class="text-[10px] text-surface-600">({{ sessions.length }})</span>
            </span>
          </button>
        </div>
        <!-- Workspace tabs (only in run mode) -->
        <div v-if="pageTab === 'run'" class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg overflow-x-auto">
          <div v-for="wt in workspaceTabs" :key="wt.id"
            @click="switchWorkspace(wt.id)"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer group rounded-md transition-colors"
            :class="wt.id === activeWorkspaceId ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="wt.running ? 'bg-green-400 animate-pulse' : wt.hasResults ? 'bg-brand-400' : 'bg-surface-600'"></span>
            <span class="truncate max-w-[140px]">{{ wt.label }}</span>
            <button v-if="workspaceTabs.length > 1 && !wt.running" @click.stop="closeWorkspace(wt.id)"
              class="text-surface-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">&times;</button>
          </div>
          <button @click="addWorkspace"
            class="w-6 h-6 flex items-center justify-center text-surface-500 hover:text-brand-400 rounded text-sm transition-colors"
            title="New workspace">+</button>
        </div>
      </div>
    </div>

    <!-- ═══ NEW RUN TAB ═══ -->
    <div v-show="pageTab === 'run'" class="gap-6" :class="configCollapsed ? 'block' : 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3'">
      <!-- Config Panel (Left) -->
      <div v-show="!configCollapsed" class="md:col-span-1 lg:col-span-1 space-y-4">
        <div class="card">
          <div class="flex items-center justify-between mb-1">
            <h2 class="text-sm font-semibold text-surface-300">Configuration</h2>
            <button @click="configCollapsed = true"
              class="text-[10px] text-surface-500 hover:text-surface-300 flex items-center gap-1 transition-colors"
              title="Hide config panel">
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M18.75 19.5l-7.5-7.5 7.5-7.5m-6 15L5.25 12l7.5-7.5"/></svg>
              Hide
            </button>
          </div>
          <p class="text-[11px] text-surface-500 mb-4">Select a broker, symbol, timeframe, strategy, and date range to simulate</p>

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
                  <div class="flex items-center gap-1">
                    <select v-if="strategies.length" v-model="route.strategy" class="select text-xs py-1.5 flex-1">
                      <option v-for="s in strategies" :key="s.name" :value="s.name">{{ s.name }}</option>
                    </select>
                    <input v-else v-model="route.strategy" class="input text-xs py-1.5 flex-1" placeholder="Strategy" />
                    <router-link v-if="route.strategy" :to="'/strategies?edit=' + encodeURIComponent(route.strategy)"
                      class="w-7 h-7 rounded-md bg-surface-800 text-surface-400 hover:text-brand-400 hover:bg-surface-700 transition-colors flex items-center justify-center flex-shrink-0" title="Edit strategy code">
                      <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Z" /></svg>
                    </router-link>
                  </div>
                </div>
                <button v-if="form.routes.length > 1" @click="removeRoute(idx)" class="text-surface-500 hover:text-red-400 text-lg mt-1">&times;</button>
              </div>
            </div>

            <!-- Data Routes (Extra) - collapsible -->
            <div>
              <button @click="showDataRoutes = !showDataRoutes" class="flex items-center justify-between w-full text-left mb-1">
                <div>
                  <label class="label mb-0 cursor-pointer">Data Routes <span class="text-surface-600">(optional)</span></label>
                  <p v-if="!showDataRoutes" class="text-[10px] text-surface-600 mt-0.5">Extra timeframes for multi-timeframe strategies</p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <span v-if="form.data_routes.length" class="text-[10px] text-surface-500">{{ form.data_routes.length }} route{{ form.data_routes.length > 1 ? 's' : '' }}</span>
                  <svg class="w-3 h-3 text-surface-500 transition-transform" :class="showDataRoutes ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                </div>
              </button>
              <div v-show="showDataRoutes">
                <div class="flex justify-end mb-1">
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
                <div v-if="!form.data_routes.length" class="text-xs text-surface-600 py-1">No extra data routes. Click + Add to include additional timeframes.</div>
              </div>
            </div>

            <!-- Date range -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
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

            <!-- Options - collapsible -->
            <div class="pt-2">
              <button @click="showOptions = !showOptions" class="flex items-center justify-between w-full text-left mb-1">
                <div>
                  <h3 class="text-xs font-semibold text-surface-400">Options</h3>
                  <p v-if="!showOptions" class="text-[10px] text-surface-600 mt-0.5">Debug logging, chart export, cost simulation, and output formats</p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <span class="text-[10px] text-surface-500">{{ optionsSummary }}</span>
                  <svg class="w-3 h-3 text-surface-500 transition-transform" :class="showOptions ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                </div>
              </button>
            <div v-show="showOptions" class="space-y-2">
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
            </div>

            <!-- Backtest Mode Toggle -->
            <div class="pt-3">
              <div class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg">
                <button @click="form.backtestMode = 'normal'" class="flex-1 px-3 py-1.5 text-xs rounded-md transition-colors text-center"
                  :class="form.backtestMode === 'normal' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
                  Normal
                </button>
                <button @click="form.backtestMode = 'pipeline'" class="flex-1 px-3 py-1.5 text-xs rounded-md transition-colors text-center"
                  :class="form.backtestMode === 'pipeline' ? 'bg-brand-500/20 text-brand-400' : 'text-surface-500 hover:text-surface-300'">
                  Pipeline
                </button>
              </div>
              <p class="text-[10px] text-surface-600 mt-1">
                {{ form.backtestMode === 'normal' ? 'Standard backtest with strategy hyperparameters' : 'Intelligent layers — danger scoring, entry gating, Q-learning abort' }}
              </p>
            </div>

            <!-- ═ NORMAL MODE: Preset Selector ═ -->
            <div v-if="form.backtestMode === 'normal' && btPreset" class="pt-2">
              <h3 class="text-xs font-semibold text-surface-400 mb-1">Preset</h3>
              <p class="text-[10px] text-surface-600 mb-1.5">Pre-configured strategy mode — selects which parameters are tunable</p>
              <select v-model="btPreset.value" @change="onPresetChange" class="select text-xs py-1.5 w-full">
                <option v-for="opt in btPreset.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>
            </div>

            <!-- ═ NORMAL MODE: Hyperparameters ═ -->
            <div v-if="form.backtestMode === 'normal' && visibleBtHPs.length" class="pt-2">
              <button @click="showHyperparams = !showHyperparams" class="flex items-center justify-between w-full text-left mb-1">
                <div>
                  <h3 class="text-xs font-semibold text-surface-400">Hyperparameters</h3>
                  <p v-if="!showHyperparams" class="text-[10px] text-surface-600 mt-0.5">Strategy-specific tuning values — multipliers, levels, thresholds</p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <span class="text-[10px] text-surface-500">{{ visibleBtHPs.length }} param{{ visibleBtHPs.length > 1 ? 's' : '' }}</span>
                  <svg class="w-3 h-3 text-surface-500 transition-transform" :class="showHyperparams ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                </div>
              </button>
              <div v-show="showHyperparams">
                <div class="flex justify-end mb-1">
                  <button @click="resetBtHyperParams" class="text-xs text-surface-500 hover:text-surface-300">Reset Defaults</button>
                </div>
              <template v-for="group in btHpGroups" :key="group.name">
                <div v-if="group.hps.length" class="mb-3">
                  <div class="text-[10px] font-semibold text-surface-500 uppercase tracking-wider mb-1.5 mt-2 border-b border-surface-800 pb-1">{{ group.name }}</div>
                  <div v-for="hp in group.hps" :key="hp.name" class="mb-2">
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
              </template>
              </div>
            </div>

            <!-- ═ PIPELINE MODE: Pipeline selection ═ -->
            <div v-if="form.backtestMode === 'pipeline'" class="pt-2 space-y-2">
              <div v-if="availablePipelines.length" class="space-y-2">
                <div v-for="(pc, idx) in form.pipelineConfigs" :key="idx" class="p-2 bg-surface-800 rounded space-y-1.5">
                  <div class="flex items-center justify-between">
                    <select v-model="pc.name" class="select text-xs py-1" @change="onPipelineSelect(idx)">
                      <option v-for="p in availablePipelines" :key="p.name" :value="p.name">{{ p.name }}</option>
                    </select>
                    <button v-if="form.pipelineConfigs.length > 1" @click="removePipeline(idx)" class="text-surface-500 hover:text-red-400 text-sm">&times;</button>
                  </div>
                  <div v-if="pc.name" class="text-[10px] text-surface-600">
                    {{ availablePipelines.find(p => p.name === pc.name)?.description || '' }}
                  </div>
                </div>
                <button @click="addPipeline" class="text-xs text-brand-400 hover:text-brand-300">+ Add Pipeline</button>
              </div>
              <div v-else class="text-[10px] text-surface-600 py-2">No pipelines registered. Create one from the Pipelines page.</div>
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
              <span v-else>{{ form.backtestMode === 'pipeline' ? 'Run Pipeline' : 'Run Backtest' }}</span>
            </button>
            <button v-if="running" @click="cancelBacktest" class="btn-secondary w-full text-sm">
              Cancel
            </button>
          </div>
        </div>

        <!-- General Info during run -->
        <div v-if="running && generalInfo" class="card text-xs space-y-1">
          <div v-for="(val, key) in generalInfo" :key="key" class="text-surface-500">
            {{ key }}: <span class="text-surface-300">{{ val }}</span>
          </div>
        </div>
      </div>

      <!-- Results Panel (Right) -->
      <div :class="configCollapsed ? 'w-full' : 'md:col-span-1 lg:col-span-2'" class="space-y-4 relative">
        <!-- Show Config toggle -->
        <div v-if="configCollapsed" class="flex items-center justify-end mb-2">
          <button @click="configCollapsed = false"
            class="btn-sm bg-surface-800 hover:bg-surface-700 text-surface-400 text-xs flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            Show Config
          </button>
        </div>

        <!-- Rich Progress Card -->
        <div v-if="running || (progress.current === 100 && message)" class="card p-5 space-y-4">
          <div class="flex items-center gap-5">
            <!-- Circular gauge -->
            <div class="relative w-24 h-24 flex-shrink-0">
              <svg class="w-24 h-24 -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="8" class="text-surface-800" />
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="8"
                  :class="progress.current === 100 ? 'text-green-500' : 'text-brand-500'"
                  class="transition-all duration-500 ease-out"
                  stroke-linecap="round"
                  :stroke-dasharray="2 * Math.PI * 52"
                  :stroke-dashoffset="2 * Math.PI * 52 * (1 - progress.current / 100)" />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center">
                <svg v-if="progress.current === 100 && !running" class="w-8 h-8 text-green-400" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/></svg>
                <span v-else class="text-xl font-bold text-surface-100 tabular-nums">{{ Math.round(progress.current) }}%</span>
              </div>
            </div>
            <!-- Info -->
            <div class="flex-1 min-w-0 space-y-2">
              <div class="flex items-center gap-2">
                <span v-if="running" class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
                <span v-else class="w-2 h-2 rounded-full bg-green-400"></span>
                <span class="text-sm font-medium text-surface-200">{{ running ? 'Backtesting' : 'Completed' }}</span>
                <span class="text-xs text-surface-500">{{ form.routes[0]?.strategy || '' }} &middot; {{ form.routes[0]?.symbol || '' }}</span>
              </div>
              <!-- Date progress bar -->
              <div v-if="progress.currentDate || progress.current === 100" class="space-y-1">
                <div class="flex items-center justify-between text-[11px] text-surface-500">
                  <span>{{ form.startDate }}</span>
                  <span v-if="running && progress.currentDate" class="text-surface-300 font-medium">{{ formatProgressDate(progress.currentDate) }}</span>
                  <span>{{ form.endDate }}</span>
                </div>
                <div class="w-full h-1.5 bg-surface-800 rounded-full overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500 ease-out"
                    :class="progress.current === 100 ? 'bg-green-500/60' : 'bg-brand-500/60'"
                    :style="{ width: progress.current + '%' }"></div>
                </div>
              </div>
              <!-- Time stats row -->
              <div class="flex items-center gap-4 text-xs text-surface-500">
                <span v-if="running && progress.eta > 0" class="flex items-center gap-1">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  ~{{ formatEta(progress.eta) }} remaining
                </span>
                <span v-if="runStartedAt" class="flex items-center gap-1">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"/></svg>
                  {{ elapsedTime }}
                </span>
                <span v-if="generalInfo?.session_id" class="text-surface-600 truncate">ID: {{ generalInfo.session_id.slice(0, 8) }}</span>
              </div>
            </div>
          </div>

          <!-- Live Stats Grid -->
          <div v-if="running && (progress.equity !== null || progress.session !== null)" class="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div v-if="progress.session !== null" class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Session</div>
              <div class="text-sm font-semibold text-surface-200 tabular-nums">#{{ progress.session }}</div>
            </div>
            <div v-if="progress.equity !== null" class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Equity</div>
              <div class="text-sm font-semibold tabular-nums" :class="progress.equity >= form.balance ? 'text-green-400' : 'text-red-400'">
                ${{ progress.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
              </div>
            </div>
            <div v-if="progress.floatingPnl !== null" class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Floating P&amp;L</div>
              <div class="text-sm font-semibold tabular-nums" :class="progress.floatingPnl >= 0 ? 'text-green-400' : 'text-red-400'">
                {{ progress.floatingPnl >= 0 ? '+' : '' }}${{ progress.floatingPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
              </div>
            </div>
            <div v-if="progress.marginUsed !== null && progress.equity" class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Margin Free</div>
              <div class="text-sm font-semibold tabular-nums" :class="marginFreePercent > 50 ? 'text-green-400' : marginFreePercent > 20 ? 'text-amber-400' : 'text-red-400'">
                {{ marginFreePercent.toFixed(1) }}%
              </div>
            </div>
            <div class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Trades</div>
              <div class="text-sm font-semibold text-surface-200 tabular-nums">{{ progress.trades }}</div>
            </div>
          </div>

          <!-- Live Pipeline Stats (during execution) -->
          <div v-if="running && progress.pipelineDanger !== null" class="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Danger Score</div>
              <div class="flex items-center gap-2">
                <div class="text-sm font-semibold tabular-nums font-mono"
                     :class="progress.pipelineDanger > 0.7 ? 'text-red-400' : progress.pipelineDanger > 0.5 ? 'text-amber-400' : 'text-green-400'">
                  {{ progress.pipelineDanger?.toFixed(3) }}
                </div>
                <!-- Mini gauge bar -->
                <div class="flex-1 h-1.5 bg-surface-900 rounded-full overflow-hidden">
                  <div class="h-full rounded-full transition-all duration-500"
                       :class="progress.pipelineDanger > 0.7 ? 'bg-red-500' : progress.pipelineDanger > 0.5 ? 'bg-amber-500' : 'bg-green-500'"
                       :style="{width: (progress.pipelineDanger * 100) + '%'}"></div>
                </div>
              </div>
              <div class="text-[9px] text-surface-600 mt-0.5">mean: {{ progress.pipelineDangerMean?.toFixed(3) ?? '-' }}</div>
            </div>
            <div class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Entries Blocked</div>
              <div class="text-sm font-semibold text-amber-400 tabular-nums">{{ progress.pipelineBlocks || 0 }}</div>
            </div>
            <div class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Aborts</div>
              <div class="text-sm font-semibold text-red-400 tabular-nums">{{ progress.pipelineAborts || 0 }}</div>
            </div>
            <div class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Cycles</div>
              <div class="text-sm font-semibold text-surface-200 tabular-nums">{{ progress.pipelineCycles || 0 }}</div>
            </div>
            <div class="bg-surface-800/60 rounded-lg px-3 py-2">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider">Pipeline Status</div>
              <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full" :class="progress.pipelineDanger > 0.7 ? 'bg-red-400 animate-pulse' : 'bg-green-400'"></span>
                <span class="text-xs" :class="progress.pipelineDanger > 0.7 ? 'text-red-400' : 'text-green-400'">
                  {{ progress.pipelineDanger > 0.7 ? 'High Risk' : progress.pipelineDanger > 0.5 ? 'Elevated' : 'Normal' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Live Mini Chart: Equity + Danger overlay -->
          <div v-if="running && liveEquityHistory.length > 2 && progress.pipelineDangerHistory" class="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div>
              <div class="text-[10px] text-surface-600 mb-0.5 px-1">Live Equity</div>
              <div class="w-full h-[100px] bg-surface-800/60 rounded overflow-hidden">
                <canvas ref="liveMiniChartEl" class="w-full h-full"></canvas>
              </div>
            </div>
            <div>
              <div class="text-[10px] text-surface-600 mb-0.5 px-1">Live Danger Score</div>
              <div class="w-full h-[100px] bg-surface-800/60 rounded overflow-hidden">
                <canvas ref="liveDangerMiniEl" class="w-full h-full"></canvas>
              </div>
            </div>
          </div>

          <!-- Live Decision Feed -->
          <div v-if="running && livePipelineDecisions.length > 0" class="bg-surface-800/40 rounded-lg p-2 max-h-[120px] overflow-y-auto">
            <div class="text-[10px] text-surface-600 mb-1 px-1 flex items-center gap-1.5">
              <span class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span>
              Pipeline Decision Feed
            </div>
            <div v-for="(d, i) in [...livePipelineDecisions].reverse().slice(0, 15)" :key="i"
                 class="flex items-center gap-2 py-0.5 px-1 text-[10px] font-mono">
              <span class="text-surface-600 w-28 shrink-0">{{ formatLiveTs(d.ts) }}</span>
              <span class="px-1 py-0.5 rounded text-[9px] shrink-0"
                    :class="d.decision === 'BLOCKED' ? 'bg-red-500/20 text-red-400' :
                            d.decision === 'ABORT' ? 'bg-amber-500/20 text-amber-400' :
                            'bg-green-500/20 text-green-400'">{{ d.decision }}</span>
              <span class="text-surface-500">danger</span>
              <span :class="d.danger > 0.7 ? 'text-red-400' : d.danger > 0.5 ? 'text-amber-400' : 'text-surface-300'">{{ d.danger?.toFixed(3) }}</span>
              <span v-if="d.threshold" class="text-surface-600">thr {{ d.threshold.toFixed(3) }}</span>
              <span v-if="d.level != null" class="text-surface-500">L{{ d.level }}</span>
            </div>
          </div>

          <!-- Live Logs (collapsible, during execution) -->
          <div v-if="running && backtestLogs.length > 0">
            <button @click="liveLogsExpanded = !liveLogsExpanded"
                    class="flex items-center gap-1.5 text-[10px] text-surface-500 hover:text-surface-300 transition-colors w-full py-1">
              <svg class="w-3 h-3 transition-transform" :class="liveLogsExpanded ? 'rotate-90' : ''" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
              <span class="uppercase tracking-wider font-semibold">Logs</span>
              <span class="text-surface-600">({{ backtestLogs.length }})</span>
              <span v-if="!liveLogsExpanded" class="ml-auto font-mono text-surface-600 truncate max-w-[60%]">{{ backtestLogs[backtestLogs.length - 1]?.message || '' }}</span>
            </button>
            <div v-if="liveLogsExpanded" class="bg-surface-900/80 rounded p-2 max-h-[200px] overflow-y-auto mt-1" ref="liveLogsEl">
              <div v-for="(log, i) in backtestLogs.slice(-100)" :key="i"
                   class="flex gap-2 py-0.5 text-[10px] font-mono leading-tight">
                <span class="text-surface-600 shrink-0 w-[140px]">{{ log.timestamp || '' }}</span>
                <span class="shrink-0 w-[52px]"
                      :class="log.type === 'error' ? 'text-red-400' : log.type === 'order' ? 'text-amber-400' : log.type === 'position' ? 'text-blue-400' : log.type === 'market' ? 'text-purple-400' : 'text-surface-500'">{{ log.type || '' }}</span>
                <span class="text-surface-300 break-all">{{ log.message }}</span>
              </div>
            </div>
          </div>

          <!-- Completed: View Results button -->
          <div v-if="!running && progress.current === 100 && metrics" class="flex items-center gap-3 pt-1">
            <button @click="activeTab = 'summary'" class="btn-primary btn-sm flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/></svg>
              View Results
            </button>
            <span class="text-xs text-surface-500">{{ message }}</span>
          </div>
        </div>
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
          <CodeEditor v-model="strategyCode" :editable="true" min-height="350px" />
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
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2">Won</th>
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2" title="Bust: close all at hedge trigger (opposite at 0)">Bust (Flat)</th>
                  <th v-if="exposureHasTpSl" class="text-right py-2 px-2" title="Bust: close losers, let opposite legs hit their TP">Bust (TP)</th>
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
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono" :class="row.won >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(row.won) }}</td>
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono text-red-400">{{ formatMetric(row.bust_close) }}</td>
                  <td v-if="exposureHasTpSl" class="py-1.5 px-2 text-right font-mono" :class="row.bust_opp_tp >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(row.bust_opp_tp) }}</td>
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

            <!-- ═══ Martingale Mode ═══ -->
            <template v-if="isMartingale">
              <!-- Session Performance -->
              <div class="mb-4">
                <div class="flex items-center justify-between mb-1"><h3 class="text-xs font-semibold text-surface-500">Session Performance</h3><button @click="showTooltips = !showTooltips" class="text-[10px] px-2 py-0.5 rounded transition-colors" :class="showTooltips ? 'bg-brand-500/20 text-brand-400' : 'bg-surface-700 text-surface-500'">{{ showTooltips ? 'Hints On' : 'Hints Off' }}</button></div>
                <SectionGuide category="martingale" />
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in mSessionPerf" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Survival & Ruin -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-red-400/70 mb-1">Survival &amp; Ruin</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in mSurvival" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Structural Diagnostics -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Structural Diagnostics</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in mStructural" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>

                <!-- Level Transition Matrix -->
                <div v-if="metrics.level_transitions?.length" class="mt-3">
                  <h4 class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">Level Transition Matrix</h4>
                  <div class="overflow-x-auto">
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="border-b border-surface-700">
                          <th class="text-left py-1 px-2 text-surface-500">Level</th>
                          <th class="text-right py-1 px-2 text-surface-500">Entries</th>
                          <th class="text-right py-1 px-2 text-surface-500">Wins</th>
                          <th class="text-right py-1 px-2 text-surface-500">Escalated</th>
                          <th class="text-right py-1 px-2 text-surface-500">P(Win)</th>
                          <th class="text-right py-1 px-2 text-surface-500">P(Esc)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="lt in metrics.level_transitions" :key="lt.level" class="border-b border-surface-800/50">
                          <td class="py-1 px-2 font-mono text-surface-300">L{{ lt.level }}</td>
                          <td class="py-1 px-2 text-right font-mono text-surface-300">{{ lt.entries }}</td>
                          <td class="py-1 px-2 text-right font-mono text-green-400">{{ lt.wins }}</td>
                          <td class="py-1 px-2 text-right font-mono text-amber-400">{{ lt.escalations }}</td>
                          <td class="py-1 px-2 text-right font-mono" :class="lt.p_win >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (lt.p_win * 100).toFixed(1) }}%</td>
                          <td class="py-1 px-2 text-right font-mono" :class="lt.p_escalate > 0.5 ? 'text-red-400' : 'text-amber-400'">{{ (lt.p_escalate * 100).toFixed(1) }}%</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- EV by Depth -->
                <div v-if="metrics.ev_by_depth && Object.keys(metrics.ev_by_depth).length" class="mt-3">
                  <h4 class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">EV Decomposition by Depth</h4>
                  <div class="overflow-x-auto">
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="border-b border-surface-700">
                          <th class="text-left py-1 px-2 text-surface-500">Depth</th>
                          <th class="text-right py-1 px-2 text-surface-500">Count</th>
                          <th class="text-right py-1 px-2 text-surface-500">Win Rate</th>
                          <th class="text-right py-1 px-2 text-surface-500">Total PnL</th>
                          <th class="text-right py-1 px-2 text-surface-500">Avg PnL</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(d, depth) in metrics.ev_by_depth" :key="depth" class="border-b border-surface-800/50">
                          <td class="py-1 px-2 font-mono text-surface-300">L{{ depth }}</td>
                          <td class="py-1 px-2 text-right font-mono text-surface-300">{{ d.count }}</td>
                          <td class="py-1 px-2 text-right font-mono" :class="d.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (d.win_rate * 100).toFixed(1) }}%</td>
                          <td class="py-1 px-2 text-right font-mono" :class="d.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(d.total_pnl) }}</td>
                          <td class="py-1 px-2 text-right font-mono" :class="d.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(d.avg_pnl) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Depth Distribution -->
                <div v-if="metrics.depth_breakdown?.length" class="mt-3">
                  <h4 class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">Depth Distribution</h4>
                  <div class="space-y-1">
                    <div v-for="d in metrics.depth_breakdown" :key="d.depth" class="flex items-center gap-2 text-xs">
                      <span class="w-8 text-surface-500 font-mono text-right">L{{ d.depth }}</span>
                      <div class="flex-1 h-4 bg-surface-800 rounded overflow-hidden relative">
                        <div class="h-full rounded"
                          :class="d.pnl >= 0 ? 'bg-green-500/30' : 'bg-red-500/30'"
                          :style="{ width: Math.max((d.count / metrics.total_sessions) * 100, 2) + '%' }">
                        </div>
                        <span class="absolute inset-0 flex items-center px-2 font-mono text-[10px] text-surface-300">
                          {{ d.count }} ({{ ((d.count / metrics.total_sessions) * 100).toFixed(1) }}%)
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Capital & Costs -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Capital &amp; Costs</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in mCapital" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Raw Trade Data (collapsed) -->
              <details class="mb-4">
                <summary class="text-xs text-surface-600 cursor-pointer hover:text-surface-400 select-none">
                  Raw Trade Data (debug)
                </summary>
                <div v-if="metrics.raw_trade_stats" class="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                  <div v-for="(val, key) in metrics.raw_trade_stats" :key="key" class="p-2 bg-surface-900 rounded">
                    <div class="text-surface-600 text-xs">{{ formatKey(key) }}</div>
                    <div class="font-mono text-surface-400">{{ formatMetric(val) }}</div>
                  </div>
                </div>
              </details>
            </template>

            <!-- ═══ Generic Mode (existing) ═══ -->
            <template v-else>
              <!-- Performance metrics -->
              <div class="mb-4">
                <div class="flex items-center justify-between mb-1"><h3 class="text-xs font-semibold text-surface-500">Performance</h3><button @click="showTooltips = !showTooltips" class="text-[10px] px-2 py-0.5 rounded transition-colors" :class="showTooltips ? 'bg-brand-500/20 text-brand-400' : 'bg-surface-700 text-surface-500'">{{ showTooltips ? 'Hints On' : 'Hints Off' }}</button></div>
                <SectionGuide category="performance" />
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in performanceMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div v-if="hedgeSessionMetrics.length" class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Hedge Session Stats</h3>
                <SectionGuide category="hedge" />
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in hedgeSessionMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Risk &amp; Ratios</h3>
                <SectionGuide category="risk" />
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in riskMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Trade Statistics</h3>
                <SectionGuide category="trades" />
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in tradeStatsMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
              <div v-if="forexMetrics.length" class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Forex / CFD Costs</h3>
                <SectionGuide category="forex" />
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div v-for="m in forexMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
            </template>
            
            <!-- Pipeline Analytics -->
            <div v-if="pipelineStats" class="mb-4 space-y-4">
              <div v-for="(ps, route) in pipelineStats" :key="route">
                <!-- Config badge + title -->
                <div class="flex items-center gap-2 mb-2">
                  <h3 class="text-xs font-semibold text-surface-500">Pipeline Analytics</h3>
                  <span class="text-surface-600 text-[10px]">{{ route }}</span>
                  <div v-if="ps.config" class="flex gap-1 ml-auto">
                    <span class="px-1.5 py-0.5 bg-brand-500/10 text-brand-400 text-[9px] rounded font-mono">{{ ps.config.pipeline || ps.pipeline_name || 'Pipeline' }}</span>
                    <span v-if="ps.gate?.percentile" class="px-1.5 py-0.5 bg-surface-700 text-surface-400 text-[9px] rounded font-mono">Gate p{{ ps.gate.percentile }}</span>
                    <span v-if="ps.abort?.enabled" class="px-1.5 py-0.5 bg-surface-700 text-surface-400 text-[9px] rounded font-mono">Q-Abort</span>
                    <span class="px-1.5 py-0.5 bg-surface-700 text-[9px] rounded font-mono" :class="ps.scorer?.warmed_up ? 'text-green-400' : 'text-amber-400'">{{ ps.scorer?.warmed_up ? 'Scorer active' : 'Warming up' }}</span>
                  </div>
                </div>

                <!-- Overview row -->
                <div class="grid grid-cols-2 md:grid-cols-6 gap-2 text-sm mb-3">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-[10px]">Cycles</div>
                    <div class="font-mono text-surface-100">{{ ps.cycles?.total || ps.cycles_completed || 0 }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-[10px]">Win Rate</div>
                    <div class="font-mono" :class="(ps.cycles?.win_rate||0) >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ ((ps.cycles?.win_rate||0)*100).toFixed(1) }}%</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-[10px]">Entries Blocked</div>
                    <div class="font-mono text-amber-400">{{ ps.entries_blocked || 0 }} <span class="text-surface-600 text-[10px]">({{ ((ps.block_rate||0)*100).toFixed(1) }}%)</span></div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-[10px]">Aborts</div>
                    <div class="font-mono text-red-400">{{ ps.aborts_triggered || 0 }} <span class="text-surface-600 text-[10px]">({{ ((ps.abort_rate||0)*100).toFixed(1) }}%)</span></div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-[10px]">Avg Danger</div>
                    <div class="font-mono text-surface-100">{{ ps.danger?.mean != null ? ps.danger.mean.toFixed(3) : '-' }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-[10px]">Protection</div>
                    <div class="font-mono text-green-400">{{ ps.protection?.total_protection_value ? '+' + ps.protection.total_protection_value.toFixed(2) : '-' }}</div>
                  </div>
                </div>

                <!-- Entry Gate Intelligence -->
                <details v-if="ps.gate" class="mb-3 group" open>
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">Entry Gate</summary>
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Allow Accuracy:</span>
                      <span class="font-mono ml-1" :class="(ps.gate.allow_accuracy||0) >= 0.6 ? 'text-green-400' : 'text-amber-400'">{{ ((ps.gate.allow_accuracy||0)*100).toFixed(1) }}%</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Correct:</span>
                      <span class="font-mono text-green-400 ml-1">{{ ps.gate.correct_allows || 0 }}</span>
                      <span class="text-surface-600"> / Wrong: </span>
                      <span class="font-mono text-red-400">{{ ps.gate.wrong_allows || 0 }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg Danger @ Block:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.gate.avg_danger_at_block?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">PnL of Allowed:</span>
                      <span class="font-mono ml-1" :class="(ps.gate.pnl_of_allowed||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ (ps.gate.pnl_of_allowed||0).toFixed(2) }}</span>
                    </div>
                  </div>
                  <!-- Decision quality row -->
                  <div class="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Wrong Allow Avg Danger:</span>
                      <span class="font-mono text-red-400 ml-1">{{ ps.gate.wrong_allow_avg_danger?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Correct Allow Avg Danger:</span>
                      <span class="font-mono text-green-400 ml-1">{{ ps.gate.correct_allow_avg_danger?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Wrong Allow Loss:</span>
                      <span class="font-mono text-red-400 ml-1">{{ (ps.gate.wrong_allow_total_loss||0).toFixed(2) }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Est. Saved by Blocks:</span>
                      <span class="font-mono text-green-400 ml-1">+{{ (ps.gate.est_pnl_saved_by_blocks||0).toFixed(2) }}</span>
                    </div>
                  </div>
                </details>

                <!-- Q-Abort Intelligence -->
                <details v-if="ps.abort" class="mb-3 group" open>
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">
                    Q-Learning Abort
                    <span v-if="ps.abort.pretrained" class="ml-1 px-1 py-0.5 rounded text-[8px] font-mono bg-blue-900/50 text-blue-300">PRE-TRAINED</span>
                    <span v-if="ps.abort.mode" class="ml-1 px-1 py-0.5 rounded text-[8px] font-mono bg-surface-700 text-surface-400">{{ ps.abort.mode }}</span>
                  </summary>
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg Level @ Abort:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.abort.avg_level_at_abort?.toFixed(1) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg Danger @ Abort:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.abort.avg_danger_at_abort?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Q-Margin:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.abort.q_margin_at_abort?.toFixed(4) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">States:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.abort.states_visited || 0 }}/{{ ps.abort.total_states || 0 }}</span>
                      <span class="text-surface-600 ml-1">({{ ((ps.abort.coverage||0)*100).toFixed(1) }}%)</span>
                    </div>
                  </div>
                  <!-- Abort quality -->
                  <div class="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg PnL @ Abort:</span>
                      <span class="font-mono ml-1" :class="(ps.abort.avg_pnl_at_abort||0) < 0 ? 'text-red-400' : 'text-green-400'">{{ ps.abort.avg_pnl_at_abort?.toFixed(2) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Cut Losses:</span>
                      <span class="font-mono text-green-400 ml-1">{{ ps.abort.aborts_at_loss || 0 }}</span>
                      <span class="text-surface-600"> / Cut Profits: </span>
                      <span class="font-mono text-red-400">{{ ps.abort.aborts_at_profit || 0 }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Aborted Cycle PnL:</span>
                      <span class="font-mono ml-1" :class="(ps.abort.aborted_cycle_total_pnl||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ (ps.abort.aborted_cycle_total_pnl||0).toFixed(2) }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Saved by Aborts:</span>
                      <span class="font-mono text-green-400 ml-1">+{{ (ps.abort.pnl_saved_by_aborts||0).toFixed(2) }}</span>
                    </div>
                  </div>
                  <!-- Policy summary -->
                  <div v-if="ps.abort.abort_preferred_states != null" class="mt-1 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Abort-preferred:</span>
                      <span class="font-mono text-red-400 ml-1">{{ ps.abort.abort_preferred_states }}</span>
                      <span class="text-surface-600"> states</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Continue-preferred:</span>
                      <span class="font-mono text-green-400 ml-1">{{ ps.abort.continue_preferred_states }}</span>
                      <span class="text-surface-600"> states</span>
                    </div>
                    <div v-if="ps.abort.q_mean != null" class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Q range:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.abort.q_min?.toFixed(4) }} ~ {{ ps.abort.q_max?.toFixed(4) }}</span>
                    </div>
                    <div v-if="ps.abort.total_visits" class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Total decisions:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.abort.total_visits?.toLocaleString() }}</span>
                    </div>
                  </div>
                </details>

                <!-- Risk Intelligence -->
                <details v-if="ps.risk_intel" class="mb-3 group">
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">Risk Intelligence</summary>
                  <!-- Danger → Outcome buckets table -->
                  <div v-if="ps.risk_intel.danger_buckets" class="mb-2">
                    <table class="w-full text-[10px]">
                      <thead>
                        <tr class="text-surface-500 border-b border-surface-700">
                          <th class="text-left py-1 px-2">Danger Bucket</th>
                          <th class="text-right py-1 px-2">Count</th>
                          <th class="text-right py-1 px-2">Win Rate</th>
                          <th class="text-right py-1 px-2">PnL</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(b, label) in ps.risk_intel.danger_buckets" :key="label"
                            class="border-b border-surface-800"
                            :class="b.count === 0 ? 'opacity-30' : ''">
                          <td class="py-1 px-2 font-mono"
                              :class="label === 'extreme' ? 'text-red-400' : label === 'high' ? 'text-orange-400' : label === 'medium' ? 'text-amber-400' : label === 'low' ? 'text-green-400' : 'text-green-300'">{{ label }}</td>
                          <td class="text-right py-1 px-2 font-mono text-surface-300">{{ b.count }}</td>
                          <td class="text-right py-1 px-2 font-mono" :class="b.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (b.win_rate*100).toFixed(1) }}%</td>
                          <td class="text-right py-1 px-2 font-mono" :class="b.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ b.pnl.toFixed(2) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <!-- High-danger + bust analysis -->
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">High-Danger Entries:</span>
                      <span class="font-mono text-red-400 ml-1">{{ ps.risk_intel.high_danger_entries || 0 }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">High-Danger Win Rate:</span>
                      <span class="font-mono ml-1" :class="(ps.risk_intel.high_danger_entry_winrate||0) >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ ((ps.risk_intel.high_danger_entry_winrate||0)*100).toFixed(1) }}%</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg Danger Before Bust:</span>
                      <span class="font-mono text-red-400 ml-1">{{ ps.risk_intel.avg_danger_before_bust?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Max Danger During Bust:</span>
                      <span class="font-mono text-red-400 ml-1">{{ ps.risk_intel.avg_max_danger_during_bust?.toFixed(3) ?? '-' }}</span>
                    </div>
                  </div>
                  <!-- Peak danger window -->
                  <div v-if="ps.risk_intel.peak_danger_window" class="mt-1 p-1.5 bg-red-500/5 border border-red-500/10 rounded text-[10px]">
                    <span class="text-surface-500">Most Dangerous Period:</span>
                    <span class="font-mono text-red-400 ml-1">{{ formatTimestamp(ps.risk_intel.peak_danger_window.start_ts) }} — {{ formatTimestamp(ps.risk_intel.peak_danger_window.end_ts) }}</span>
                    <span class="text-surface-500 ml-2">Avg Danger:</span>
                    <span class="font-mono text-red-400 ml-1">{{ ps.risk_intel.peak_danger_window.avg_danger.toFixed(3) }}</span>
                  </div>
                </details>

                <!-- Per-Level Performance -->
                <details v-if="ps.level_performance && Object.keys(ps.level_performance).length" class="mb-3 group">
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">Per-Level Performance</summary>
                  <div class="space-y-1">
                    <div v-for="(data, level) in ps.level_performance" :key="level" class="flex items-center gap-2">
                      <span class="text-[10px] font-mono text-surface-400 w-6">L{{ level }}</span>
                      <div class="flex-1 h-4 bg-surface-900 rounded-sm overflow-hidden flex">
                        <div class="h-full bg-green-500/60 transition-all" :style="{width: data.count > 0 ? (data.wins/data.count*100)+'%' : '0%'}"></div>
                        <div class="h-full bg-red-500/60 transition-all" :style="{width: data.count > 0 ? ((data.count-data.wins)/data.count*100)+'%' : '0%'}"></div>
                      </div>
                      <span class="text-[10px] font-mono text-surface-400 w-8 text-right">{{ data.count }}x</span>
                      <span class="text-[10px] font-mono w-12 text-right" :class="(data.win_rate||0) >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ ((data.win_rate||0)*100).toFixed(0) }}%</span>
                      <span class="text-[10px] font-mono w-16 text-right" :class="data.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ data.pnl.toFixed(2) }}</span>
                      <span v-if="data.avg_danger != null" class="text-[10px] font-mono text-surface-500 w-10 text-right">d{{ data.avg_danger.toFixed(2) }}</span>
                    </div>
                  </div>
                </details>

                <!-- Danger Distribution -->
                <details v-if="ps.danger" class="mb-3 group">
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">Danger Score Distribution</summary>
                  <div class="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Current:</span>
                      <span class="font-mono ml-1" :class="(ps.danger.current||0) > 0.7 ? 'text-red-400' : (ps.danger.current||0) > 0.5 ? 'text-amber-400' : 'text-green-400'">{{ ps.danger.current?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Mean / Std:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.danger.mean?.toFixed(3) ?? '-' }} / {{ ps.danger.std?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">@ Entry:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.danger.avg_at_entry?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">@ Exit:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.danger.avg_at_exit?.toFixed(3) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">High Danger:</span>
                      <span class="font-mono text-red-400 ml-1">{{ ((ps.danger.high_danger_pct||0)*100).toFixed(1) }}%</span>
                    </div>
                  </div>
                  <!-- Quartiles bar -->
                  <div v-if="ps.danger.quartiles" class="mt-1.5 flex items-center gap-2 text-[10px] text-surface-500">
                    <span>{{ ps.danger.quartiles.min.toFixed(2) }}</span>
                    <div class="flex-1 h-2 bg-surface-800 rounded-full overflow-hidden flex">
                      <div class="h-full bg-green-500/30" :style="{width: ps.danger.quartiles.p25*100+'%'}"></div>
                      <div class="h-full bg-amber-500/30" :style="{width: (ps.danger.quartiles.p50-ps.danger.quartiles.p25)*100+'%'}"></div>
                      <div class="h-full bg-orange-500/30" :style="{width: (ps.danger.quartiles.p75-ps.danger.quartiles.p50)*100+'%'}"></div>
                      <div class="h-full bg-red-500/30" :style="{width: (ps.danger.quartiles.max-ps.danger.quartiles.p75)*100+'%'}"></div>
                    </div>
                    <span>{{ ps.danger.quartiles.max.toFixed(2) }}</span>
                  </div>
                </details>

                <!-- Cycle Outcomes by Exit Reason -->
                <details v-if="ps.cycles?.pnl_by_exit && Object.keys(ps.cycles.pnl_by_exit).length" class="mb-3 group">
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">Cycle Outcomes</summary>
                  <div class="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg PnL:</span>
                      <span class="font-mono ml-1" :class="(ps.cycles.avg_pnl||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ ps.cycles.avg_pnl?.toFixed(2) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg Win / Loss:</span>
                      <span class="font-mono text-green-400 ml-1">{{ ps.cycles.avg_win?.toFixed(2) ?? '-' }}</span>
                      <span class="text-surface-600"> / </span>
                      <span class="font-mono text-red-400">{{ ps.cycles.avg_loss?.toFixed(2) ?? '-' }}</span>
                    </div>
                    <div class="p-1.5 bg-surface-800/60 rounded">
                      <span class="text-surface-500">Avg Level / Duration:</span>
                      <span class="font-mono text-surface-300 ml-1">{{ ps.cycles.avg_level?.toFixed(1) ?? '-' }} / {{ ps.cycles.avg_duration?.toFixed(0) ?? '-' }} bars</span>
                    </div>
                  </div>
                  <div class="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                    <div v-for="(ex, reason) in ps.cycles.pnl_by_exit" :key="reason"
                         class="px-2 py-1 bg-surface-800 rounded flex items-center gap-1.5">
                      <span class="px-1 py-0.5 rounded text-[9px] font-mono"
                            :class="reason === 'bucket_hit' ? 'bg-green-500/20 text-green-400' :
                                    reason === 'pipeline_abort' ? 'bg-amber-500/20 text-amber-400' :
                                    reason.includes('max_level') ? 'bg-red-500/20 text-red-400' :
                                    'bg-surface-700 text-surface-400'">{{ reason }}</span>
                      <span class="text-surface-500">{{ ex.count }}x</span>
                      <span class="font-mono" :class="ex.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ ex.pnl.toFixed(2) }}</span>
                    </div>
                  </div>
                </details>

                <!-- Scorer Features Health -->
                <details v-if="ps.scorer?.features" class="mb-3 group">
                  <summary class="text-[10px] font-semibold text-surface-500 mb-1 cursor-pointer hover:text-surface-400">
                    Scorer Features
                    <span v-if="ps.scorer.seeded" class="ml-1 px-1 py-0.5 rounded text-[8px] font-mono bg-blue-900/50 text-blue-300">SEEDED</span>
                    <span class="text-surface-600 font-normal">({{ ps.scorer.warmed_up ? 'active' : 'warming up' }})</span>
                  </summary>
                  <div class="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1 text-[10px]">
                    <div v-for="(f, key) in ps.scorer.features" :key="key"
                         class="flex items-center justify-between px-2 py-1 bg-surface-800/40 rounded">
                      <span class="text-surface-400 font-mono">{{ key }}</span>
                      <div class="flex items-center gap-3 text-surface-500">
                        <span>w={{ f.weight }}</span>
                        <span v-if="f.inverted" class="text-amber-500">inv</span>
                        <span>n={{ f.observations }}</span>
                        <span class="font-mono text-surface-300">{{ f.mean.toFixed(3) }} +/- {{ f.std.toFixed(3) }}</span>
                      </div>
                    </div>
                  </div>
                </details>

              </div>
            </div>

            <!-- Hyperparameters -->
            <div v-if="hyperparameters && hyperparameters.length" class="mt-4">
              <button @click="showResultHP = !showResultHP" class="flex items-center gap-2 mb-2 text-left w-full">
                <h3 class="text-xs font-semibold text-surface-500">
                  {{ pipelineStats ? 'Pipeline-Controlled Hyperparameters' : 'Hyperparameters' }}
                </h3>
                <span class="text-[10px] text-surface-600 font-mono">{{ hyperparameters.length }} params</span>
                <svg class="w-3 h-3 text-surface-500 transition-transform ml-auto" :class="{ 'rotate-180': showResultHP }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
              </button>
              <div v-if="showResultHP" class="flex flex-wrap gap-2">
                <div v-for="(hp, idx) in hyperparameters" :key="idx" class="px-3 py-1.5 bg-surface-800 rounded-lg text-xs">
                  <span class="text-surface-500">{{ Array.isArray(hp) ? hp[0] : hp.name }}:</span>
                  <span class="text-surface-200 font-mono ml-1">{{ Array.isArray(hp) ? hp[1] : hp.value }}</span>
                </div>
              </div>
              <p v-if="pipelineStats && !showResultHP" class="text-[10px] text-surface-600">
                HP values managed by pipeline — expand sessions to see per-session HP
              </p>
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
              <div v-if="dangerChartData.length">
                <div class="text-[10px] text-surface-500 mb-0.5 px-1">Danger Score (Pipeline)</div>
                <div ref="dangerChartEl" class="w-full h-[180px] bg-surface-800 rounded"></div>
              </div>
            </div>
          </div>

          <!-- Pipeline Intelligence Tab -->
          <div v-if="activeTab === 'pipeline'">
            <PipelineIntelligence :stats="pipelineStats" :session-id="generalInfo?.session_id" />
            <!-- A/B Comparison -->
            <div class="mt-8 border-t border-surface-700/50 pt-6">
              <div class="flex items-center justify-between mb-4">
                <div>
                  <h3 class="text-sm font-semibold text-surface-300">A/B Comparison</h3>
                  <p class="text-[10px] text-surface-500">Compare current run against <span class="text-brand-400 font-semibold">preset=original</span> without pipelines</p>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="comparisonRunning" class="flex items-center gap-1.5 text-xs text-amber-400"><span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span> Running baseline... {{ comparisonProgress }}%</span>
                  <button v-if="!comparisonRunning && !baselineMetrics" @click="runBaselineComparison" :disabled="running" class="btn-sm bg-surface-700 hover:bg-surface-600 text-surface-200 flex items-center gap-1.5"><svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/></svg> Compare without Pipeline</button>
                  <button v-if="baselineMetrics && !comparisonRunning" @click="runBaselineComparison" class="btn-sm bg-surface-800 hover:bg-surface-700 text-surface-400 text-[10px]">Re-run</button>
                </div>
              </div>
              <!-- Baseline config preview -->
              <div v-if="baselineHPsPreview.length" class="mb-4 p-3 bg-surface-800/50 border border-surface-700/30 rounded-lg">
                <div class="flex items-center gap-2 mb-2">
                  <span class="text-[10px] font-semibold text-surface-400 uppercase tracking-wider">Baseline Config</span>
                  <span class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-400 font-mono">preset=original</span>
                  <span class="text-[10px] text-surface-600">no pipeline</span>
                </div>
                <div class="flex flex-wrap gap-x-4 gap-y-1">
                  <span v-for="hp in baselineHPsPreview" :key="hp.name" class="text-[10px] font-mono">
                    <span :class="hp.isPreset ? 'text-surface-400' : 'text-surface-600'">{{ hp.name }}:</span>
                    <span :class="hp.isPreset ? 'text-surface-200' : 'text-surface-500'" class="ml-0.5">{{ hp.value }}</span>
                  </span>
                </div>
              </div>
              <!-- Comparison progress bar -->
              <div v-if="comparisonRunning" class="mb-4">
                <div class="w-full h-1.5 bg-surface-800 rounded-full overflow-hidden">
                  <div class="h-full bg-amber-500 transition-all duration-300 rounded-full" :style="{width: comparisonProgress + '%'}"></div>
                </div>
              </div>
              <!-- Comparison error -->
              <div v-if="comparisonError" class="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">{{ comparisonError }}</div>
              <div v-if="baselineMetrics && metrics" class="space-y-4">
                <!-- Legend -->
                <div class="flex items-center gap-4 text-[10px]">
                  <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-brand-400"></span> <span class="text-surface-400 font-semibold">Your Run</span> <span class="text-surface-600">(with pipeline)</span></span>
                  <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-surface-500"></span> <span class="text-surface-400 font-semibold">Baseline</span> <span class="text-surface-600">(preset=original, no pipeline)</span></span>
                </div>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  <div v-for="m in comparisonDeltas" :key="m.key" class="p-3 bg-surface-800 rounded-lg border border-surface-700/50">
                    <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">{{ m.label }}</div>
                    <div class="flex items-end gap-2">
                      <span class="font-mono text-sm" :class="m.pipeline >= m.baseline ? 'text-green-400' : 'text-red-400'">{{ m.pipelineFormatted }}</span>
                      <span class="font-mono text-[10px] text-surface-600">vs {{ m.baselineFormatted }}</span>
                    </div>
                    <div class="mt-1"><span class="font-mono text-xs px-1.5 py-0.5 rounded" :class="m.deltaPositive ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'">{{ m.deltaPositive ? '+' : '' }}{{ m.deltaFormatted }}</span></div>
                  </div>
                </div>
                <!-- Depth Comparison Table -->
                <div v-if="depthComparison.length" class="bg-surface-800/50 rounded-lg border border-surface-700/30 p-4">
                  <h4 class="text-xs font-semibold text-surface-400 mb-3 uppercase tracking-wider">Depth Breakdown</h4>
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="text-surface-500 border-b border-surface-700/50">
                        <th class="py-1.5 px-2 text-left">Depth</th>
                        <th class="py-1.5 px-2 text-center" colspan="3">Your Run</th>
                        <th class="py-1.5 px-2 text-center" colspan="3">Baseline</th>
                      </tr>
                      <tr class="text-[10px] text-surface-600">
                        <th class="py-1 px-2 text-left">Level</th>
                        <th class="py-1 px-2 text-center">Count</th>
                        <th class="py-1 px-2 text-center">W/L</th>
                        <th class="py-1 px-2 text-right">PnL</th>
                        <th class="py-1 px-2 text-center">Count</th>
                        <th class="py-1 px-2 text-center">W/L</th>
                        <th class="py-1 px-2 text-right">PnL</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="d in depthComparison" :key="d.depth" class="border-b border-surface-800/50">
                        <td class="py-1.5 px-2 font-mono font-semibold text-surface-300">L{{ d.depth }}</td>
                        <td class="py-1.5 px-2 text-center font-mono text-surface-300">{{ d.pipeline.count }}</td>
                        <td class="py-1.5 px-2 text-center font-mono">
                          <span class="text-green-400">{{ d.pipeline.wins }}</span><span class="text-surface-600">/</span><span class="text-red-400">{{ d.pipeline.losses }}</span>
                        </td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="d.pipeline.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ d.pipeline.pnl.toFixed(2) }}</td>
                        <td class="py-1.5 px-2 text-center font-mono text-surface-300">{{ d.baseline.count }}</td>
                        <td class="py-1.5 px-2 text-center font-mono">
                          <span class="text-green-400">{{ d.baseline.wins }}</span><span class="text-surface-600">/</span><span class="text-red-400">{{ d.baseline.losses }}</span>
                        </td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="d.baseline.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ d.baseline.pnl.toFixed(2) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="baselineEquityCurve?.length && equityCurve?.length" class="card">
                  <h4 class="text-xs font-semibold text-surface-400 mb-3">Equity Curve Overlay</h4>
                  <div ref="comparisonEquityEl" class="w-full h-[300px]"></div>
                </div>
                <div class="p-4 rounded-lg border" :class="pipelineWins ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'">
                  <div class="flex items-center gap-2 mb-2">
                    <svg v-if="pipelineWins" class="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <svg v-else class="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                    <span class="text-sm font-semibold" :class="pipelineWins ? 'text-green-400' : 'text-red-400'">{{ pipelineWins ? 'Pipeline improves performance' : 'Pipeline reduces performance' }}</span>
                  </div>
                  <p class="text-xs text-surface-400">Net profit {{ pipelineWins ? 'increased' : 'decreased' }} by <span class="font-mono font-semibold" :class="pipelineWins ? 'text-green-400' : 'text-red-400'">{{ Math.abs(pipelineNetDelta).toFixed(2) }}%</span> with pipeline. Max drawdown: <span class="font-mono text-surface-300">{{ (baselineMetrics.max_drawdown || 0).toFixed(2) }}%</span> to <span class="font-mono text-surface-300">{{ (metrics.max_drawdown || 0).toFixed(2) }}%</span>.</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Sessions Tab (hedge session grouping) -->
          <div v-if="activeTab === 'sessions'">
            <div v-if="!hedgeSessions.length" class="text-surface-500 text-sm py-8 text-center">No sessions recorded.</div>
            <div v-if="hedgeSessions.length">
              <!-- Session summary stats (martingale) -->
              <div v-if="isMartingale && sessionAnalytics" class="space-y-3 mb-4">
                <!-- Row 1: Outcome Breakdown -->
                <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Total Sessions</div>
                    <div class="font-mono text-surface-100">{{ sessionAnalytics.total }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Wins</div>
                    <div class="font-mono text-green-400">{{ sessionAnalytics.wins }} <span class="text-surface-500 text-xs">({{ sessionAnalytics.winPct.toFixed(1) }}%)</span></div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Busts</div>
                    <div class="font-mono text-red-400">{{ sessionAnalytics.busts }} <span class="text-xs">({{ sessionAnalytics.bustTotalPnl.toFixed(2) }})</span></div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Aborts</div>
                    <div class="font-mono" :class="sessionAnalytics.aborts > 0 ? 'text-amber-400' : 'text-surface-400'">
                      {{ sessionAnalytics.aborts }} <span v-if="sessionAnalytics.aborts" class="text-xs">({{ sessionAnalytics.abortTotalPnl.toFixed(2) }})</span>
                    </div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Current Streak</div>
                    <div class="font-mono" :class="sessionAnalytics.streak >= 0 ? 'text-green-400' : 'text-red-400'">
                      {{ Math.abs(sessionAnalytics.streak) }} {{ sessionAnalytics.streak >= 0 ? 'W' : 'L' }}
                    </div>
                  </div>
                </div>
                <!-- Row 2: Session Economics -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Total PnL</div>
                    <div class="font-mono" :class="sessionAnalytics.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ sessionAnalytics.totalPnl.toFixed(2) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Avg Win PnL</div>
                    <div class="font-mono text-green-400">{{ sessionAnalytics.avgWinPnl.toFixed(2) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Avg Bust Loss</div>
                    <div class="font-mono text-red-400">{{ sessionAnalytics.avgBustLoss.toFixed(2) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Bust Recovery</div>
                    <div v-if="!sessionAnalytics.hasBusts" class="font-mono text-green-400 text-xs">No busts</div>
                    <div v-else>
                      <div class="font-mono text-xs" :class="sessionAnalytics.winsSinceLastBust >= sessionAnalytics.wtr ? 'text-green-400' : 'text-amber-400'">
                        {{ sessionAnalytics.winsSinceLastBust }} / {{ sessionAnalytics.wtr }} wins
                      </div>
                      <div class="mt-1 h-1.5 bg-surface-700 rounded-full overflow-hidden">
                        <div class="h-full rounded-full transition-all" :class="sessionAnalytics.winsSinceLastBust >= sessionAnalytics.wtr ? 'bg-green-500' : 'bg-amber-500'" :style="{ width: Math.min(100, sessionAnalytics.wtr > 0 ? (sessionAnalytics.winsSinceLastBust / sessionAnalytics.wtr * 100) : 0) + '%' }"></div>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- Row 3: Risk & Capital -->
                <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Worst Session Float</div>
                    <div class="font-mono text-red-400">{{ sessionAnalytics.worstFloat.toFixed(2) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Peak Equity Used</div>
                    <div class="font-mono" :class="sessionAnalytics.peakEquityPct > 80 ? 'text-red-400' : 'text-amber-400'">{{ sessionAnalytics.peakEquityPct.toFixed(1) }}%</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Avg Equity Used</div>
                    <div class="font-mono text-surface-100">{{ sessionAnalytics.avgEquityPct.toFixed(1) }}%</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Margin Blocks</div>
                    <div class="font-mono" :class="sessionAnalytics.marginBlocks > 0 ? 'text-red-400 font-bold' : 'text-green-400'">{{ sessionAnalytics.marginBlocks }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Avg Duration</div>
                    <div class="font-mono text-surface-100">{{ formatDuration(sessionAnalytics.avgDurationSec) }}</div>
                  </div>
                </div>
              </div>

              <!-- Session summary stats (non-martingale) -->
              <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
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
                      <span v-if="s.pipeline?.danger_at_entry != null" class="w-2 h-2 rounded-full inline-block"
                            :class="s.pipeline.danger_at_entry > 0.7 ? 'bg-red-400' : s.pipeline.danger_at_entry > 0.5 ? 'bg-amber-400' : 'bg-green-400'"
                            :title="`Danger: ${s.pipeline.danger_at_entry.toFixed(3)}`"></span>
                      <span v-if="s.pipeline?.abort_triggers > 0" class="text-[10px] px-1 py-0.5 rounded bg-amber-500/20 text-amber-400 font-mono">{{ s.pipeline.abort_triggers }} abort</span>
                      <span v-if="s.pipeline?.regime != null" class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/15 text-brand-400 font-mono" :title="'Regime ' + s.pipeline.regime + (s.pipeline.confidence ? ' (' + (s.pipeline.confidence*100).toFixed(0) + '%)' : '')">R{{ s.pipeline.regime }}</span>
                      <span v-if="sessionHP(s)" class="text-[10px] px-1 py-0.5 rounded bg-surface-700 text-surface-400 font-mono" :title="Object.keys(sessionHP(s)).length + ' params'">
                        {{ s.pipeline?.genes ? 'DNA' : 'HP' }}
                      </span>
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
                    <!-- Pipeline context row -->
                    <div v-if="s.pipeline" class="flex flex-wrap gap-4 px-3 py-2 bg-surface-850 border-b border-surface-700 text-[10px]">
                      <div>
                        <span class="text-surface-500">Danger @ Entry:</span>
                        <span class="font-mono ml-1" :class="(s.pipeline.danger_at_entry||0) > 0.7 ? 'text-red-400' : (s.pipeline.danger_at_entry||0) > 0.5 ? 'text-amber-400' : 'text-green-400'">{{ s.pipeline.danger_at_entry?.toFixed(3) ?? '-' }}</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Max Danger:</span>
                        <span class="font-mono ml-1" :class="(s.pipeline.max_danger||0) > 0.7 ? 'text-red-400' : 'text-surface-300'">{{ s.pipeline.max_danger?.toFixed(3) ?? '-' }}</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Danger @ Exit:</span>
                        <span class="font-mono text-surface-300 ml-1">{{ s.pipeline.danger_at_exit?.toFixed(3) ?? '-' }}</span>
                      </div>
                      <div>
                        <span class="text-surface-500">Abort Checks:</span>
                        <span class="font-mono text-surface-300 ml-1">{{ s.pipeline.abort_checks }}</span>
                      </div>
                      <div v-if="s.pipeline.abort_triggers > 0">
                        <span class="text-amber-400 font-bold">{{ s.pipeline.abort_triggers }} abort(s) triggered</span>
                      </div>
                      <div v-if="s.pipeline.gate_blocks_before_entry > 0">
                        <span class="text-surface-500">Gate Blocks Before Entry:</span>
                        <span class="font-mono text-amber-400 ml-1">{{ s.pipeline.gate_blocks_before_entry }}</span>
                      </div>
                      <div v-if="s.pipeline.regime != null">
                        <span class="text-surface-500">Regime:</span>
                        <span class="font-mono text-brand-400 ml-1">R{{ s.pipeline.regime }}</span>
                      </div>
                      <div v-if="s.pipeline.confidence != null">
                        <span class="text-surface-500">Confidence:</span>
                        <span class="font-mono text-surface-300 ml-1">{{ (s.pipeline.confidence * 100).toFixed(1) }}%</span>
                      </div>
                    </div>
                    <!-- Pipeline HP / DNA for this session -->
                    <div v-if="sessionHP(s)" class="px-3 py-2 bg-surface-850/50 border-b border-surface-700">
                      <div class="flex items-center gap-2 mb-1.5">
                        <span class="text-[10px] text-surface-500 font-semibold uppercase tracking-wider">
                          {{ s.pipeline?.genes ? 'Evolved DNA' : 'Active Hyperparameters' }}
                        </span>
                        <span class="text-[9px] text-surface-600 font-mono">{{ Object.keys(sessionHP(s)).length }} params</span>
                        <button @click="s._showAllHP = !s._showAllHP" class="text-[9px] text-brand-400 hover:text-brand-300 ml-auto">
                          {{ s._showAllHP ? 'Show Key Only' : 'Show All' }}
                        </button>
                      </div>
                      <div class="flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
                        <template v-for="(val, key) in sessionHP(s)" :key="key">
                          <div v-if="s._showAllHP || isKeyGene(key)">
                            <span class="text-surface-500">{{ key }}:</span>
                            <span class="font-mono text-surface-300 ml-0.5">{{ formatHPVal(val) }}</span>
                          </div>
                        </template>
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
                            {{ sessionOutcomeLabel(t.meta?.exit_reason) }}
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

            <!-- Martingale Costs -->
            <div v-else-if="isMartingale && sessionAnalytics" class="space-y-6">

              <!-- Section 1: Cost Summary (session-focused) -->
              <div>
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Cost Summary</h3>
                <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Total All Costs</div>
                    <div class="font-mono text-red-400 font-bold">{{ fmtCost(totalCosts) }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Cost / Session</div>
                    <div class="font-mono text-surface-100">{{ sessionAnalytics.total ? fmtCost(totalCosts / sessionAnalytics.total) : '-' }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Cost / Win</div>
                    <div class="font-mono text-surface-100">{{ sessionAnalytics.wins ? fmtCost(totalCosts / sessionAnalytics.wins) : '-' }}</div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Cost Drag %</div>
                    <div class="font-mono" :class="(metrics.cost_drag_pct || 0) > 30 ? 'text-red-400' : (metrics.cost_drag_pct || 0) > 15 ? 'text-amber-400' : 'text-green-400'">
                      {{ metrics.cost_drag_pct != null ? metrics.cost_drag_pct.toFixed(1) + '%' : costProfitRatio != null ? costProfitRatio.toFixed(1) + '%' : '-' }}
                    </div>
                  </div>
                  <div class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs">Cost / Avg Win</div>
                    <div class="font-mono" :class="sessionAnalytics.avgWinPnl > 0 && (totalCosts / sessionAnalytics.total) / sessionAnalytics.avgWinPnl > 0.5 ? 'text-red-400' : 'text-green-400'">
                      {{ sessionAnalytics.avgWinPnl > 0 && sessionAnalytics.total ? ((totalCosts / sessionAnalytics.total) / sessionAnalytics.avgWinPnl * 100).toFixed(1) + '%' : '-' }}
                    </div>
                  </div>
                </div>
              </div>

              <!-- Section 2: Cost by Depth Level -->
              <div v-if="costByDepth.length">
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Cost by Depth Level</h3>
                <div class="overflow-x-auto">
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="text-surface-500 border-b border-surface-700">
                        <th class="text-left py-2 px-2">Level</th>
                        <th class="text-right py-2 px-2">Sessions</th>
                        <th class="text-right py-2 px-2">Total Cost</th>
                        <th class="text-right py-2 px-2">Avg Cost/Session</th>
                        <th class="text-right py-2 px-2">Total PnL</th>
                        <th class="text-right py-2 px-2">Cost % of PnL</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="d in costByDepth" :key="d.depth" class="border-b border-surface-800 hover:bg-surface-800/50">
                        <td class="py-1.5 px-2 font-mono text-surface-200">L{{ d.depth }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ d.count }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ fmtCost(d.totalCost) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ fmtCost(d.avgCost) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="d.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ d.totalPnl.toFixed(2) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="d.costPct > 50 ? 'text-red-400' : d.costPct > 25 ? 'text-amber-400' : 'text-surface-400'">
                          {{ d.totalPnl > 0 ? d.costPct.toFixed(1) + '%' : '-' }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Section 3: Margin & Capital Efficiency -->
              <div>
                <h3 class="text-xs font-semibold text-surface-500 mb-2">Margin &amp; Capital Efficiency</h3>
                <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
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
                </div>
              </div>

              <!-- Section 4: Margin Events (same for both modes) -->
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
            </div>

            <!-- Non-martingale Costs (original) -->
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
            <div v-if="currentStrategyCode" class="max-h-[500px] overflow-auto">
              <CodeEditor :model-value="currentStrategyCode" :editable="false" min-height="200px" />
            </div>
            <div v-else class="text-surface-500 text-sm py-8 text-center">
              {{ sessionId ? 'Click "Load Code" to fetch strategy code.' : 'No strategy code available.' }}
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- ═══ HISTORY TAB ═══ -->
    <div v-show="pageTab === 'history'" class="space-y-4">
      <div class="card">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-sm font-semibold text-surface-300">Session History</h2>
            <p class="text-[11px] text-surface-500 mt-0.5">Browse, compare, and manage past backtest runs</p>
          </div>
          <div class="flex items-center gap-2">
            <button @click="loadSessions" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
            <button v-if="sessions.length > 0" @click="showPurgeConfirm = true" class="text-xs text-red-400 hover:text-red-300">Purge</button>
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
            <button @click="purgeSessions" class="text-xs bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600">Purge</button>
            <button @click="showPurgeConfirm = false" class="text-xs text-surface-400 hover:text-surface-200">Cancel</button>
          </div>
        </div>

        <div v-if="sessions.length > 3" class="flex gap-2 mb-3">
          <input v-model="sessionSearch" class="input text-xs flex-1" placeholder="Search by title, strategy, or symbol..." />
          <select v-model="sessionStatusFilter" class="select text-xs w-auto">
            <option value="">All</option>
            <option value="finished">Finished</option>
            <option value="stopped">Stopped</option>
            <option value="cancelled">Cancelled</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        <!-- Running Backtests -->
        <div v-if="runningSessions.length" class="mb-4">
          <div class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-2">Running</div>
          <div v-for="rs in runningSessions" :key="rs.id"
            class="flex items-center gap-4 p-3 rounded-lg bg-surface-800/60 border border-green-500/20 cursor-pointer hover:bg-surface-800 transition-colors mb-2"
            @click="resumeRunningSession(rs)">
            <div class="relative w-10 h-10 flex-shrink-0">
              <svg class="w-10 h-10 -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="8" class="text-surface-700" />
                <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="8"
                  class="text-green-500 transition-all duration-500"
                  stroke-linecap="round"
                  :stroke-dasharray="2 * Math.PI * 52"
                  :stroke-dashoffset="2 * Math.PI * 52 * (1 - (progress.current || 0) / 100)" />
              </svg>
              <div class="absolute inset-0 flex items-center justify-center">
                <span class="text-[10px] font-bold text-surface-200 tabular-nums">{{ Math.round(progress.current || 0) }}%</span>
              </div>
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
                <span class="text-sm font-medium text-surface-200 truncate">{{ sessionLabel(rs) }}</span>
              </div>
              <div class="text-[11px] text-surface-500 mt-0.5">{{ formatSessionRoutes(rs.state) }}</div>
              <div v-if="progress.current > 0" class="mt-1.5">
                <div class="w-full h-1 bg-surface-700 rounded-full overflow-hidden">
                  <div class="h-full bg-green-500/60 rounded-full transition-all duration-500" :style="{ width: (progress.current || 0) + '%' }"></div>
                </div>
              </div>
            </div>
            <div class="text-right flex-shrink-0">
              <div v-if="progress.eta > 0" class="text-[11px] text-surface-500">~{{ formatEta(progress.eta) }}</div>
              <div class="text-[11px] text-brand-400 mt-0.5">View</div>
            </div>
          </div>
        </div>

        <div v-if="loadingSessions" class="text-surface-500 text-sm">Loading...</div>
        <div v-else-if="filteredSessions.length === 0 && !runningSessions.length" class="text-surface-500 text-sm text-center py-8">
          No backtest sessions yet. Run a backtest to see results here.
        </div>

        <div v-else-if="filteredSessions.length > 0">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-surface-500 text-xs border-b border-surface-700">
                  <th class="text-left py-2">Status</th>
                  <th class="text-left py-2">Strategy / Config</th>
                  <th v-if="showOwnerColumn" class="text-left py-2">Owner</th>
                  <th class="text-right py-2">Return</th>
                  <th class="text-left py-2">Ran At</th>
                  <th class="text-left py-2">Duration</th>
                  <th class="text-right py-2"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in filteredSessions" :key="s.id"
                  class="border-b border-surface-800 hover:bg-surface-800/50 cursor-pointer transition-colors"
                  :class="selectedSession?.id === s.id ? 'bg-surface-800/70 border-l-2 border-l-brand-500' : ''"
                  @click="viewSessionFromHistory(s)">
                  <td class="py-2.5">
                    <span class="text-xs px-2 py-0.5 rounded-full font-medium"
                      :class="statusBadgeClass(s.status)">{{ s.status }}</span>
                  </td>
                  <td class="py-2.5">
                    <div class="text-surface-200 text-sm font-medium flex items-center gap-1.5">
                      {{ s.title || sessionLabel(s) }}
                      <span v-if="s.has_pipeline" class="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 font-semibold uppercase tracking-wider">Pipeline</span>
                    </div>
                    <div class="text-[11px] text-surface-500 mt-0.5">{{ formatSessionRoutes(s.state) }}</div>
                    <div v-if="s.hyperparameters && s.hyperparameters.length" class="flex flex-wrap gap-1 mt-1">
                      <span v-for="(hp, idx) in s.hyperparameters.slice(0, 4)" :key="idx" class="text-[10px] px-1.5 py-0.5 bg-surface-700 rounded text-surface-400 font-mono">
                        {{ Array.isArray(hp) ? hp[0] : hp.name }}={{ Array.isArray(hp) ? hp[1] : hp.value }}
                      </span>
                      <span v-if="s.hyperparameters.length > 4" class="text-[10px] text-surface-600">+{{ s.hyperparameters.length - 4 }}</span>
                    </div>
                  </td>
                  <td v-if="showOwnerColumn" class="py-2.5">
                    <span v-if="s.owner_username" class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 font-medium">{{ s.owner_username }}</span>
                  </td>
                  <td class="py-2.5 text-right">
                    <span v-if="s.net_profit_percentage != null" class="text-xs font-mono" :class="s.net_profit_percentage >= 0 ? 'text-green-400' : 'text-red-400'">
                      {{ s.net_profit_percentage >= 0 ? '+' : '' }}{{ s.net_profit_percentage.toFixed(2) }}%
                    </span>
                    <span v-else class="text-xs text-surface-600">-</span>
                  </td>
                  <td class="py-2.5 text-xs text-surface-500">{{ formatTimestamp(s.created_at || s.updated_at) }}</td>
                  <td class="py-2.5 text-xs text-surface-500 font-mono">{{ computeSessionDuration(s) }}</td>
                  <td class="py-2.5 text-right">
                    <div class="flex items-center gap-2 justify-end">
                      <button @click.stop="loadSessionAsFormFromHistory(s)"
                        class="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-brand-600/20 text-brand-400 hover:bg-brand-600/30 transition-colors" title="Re-run with same config">
                        <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182"/></svg>
                        Re-run
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

      <!-- Selected Session Detail (history) -->
      <div v-if="selectedSession" class="card">
        <div class="flex items-center justify-between mb-2">
          <div>
            <h2 class="text-sm font-semibold text-surface-200 flex items-center gap-2">
              {{ historySessionTitle }}
              <span v-if="selectedSession.has_pipeline" class="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 font-semibold uppercase tracking-wider">Pipeline</span>
            </h2>
            <div class="flex items-center gap-3 mt-1 text-[11px] text-surface-500">
              <span v-if="selectedSession.created_at">
                <svg class="w-3 h-3 inline mr-0.5 -mt-px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                {{ formatTimestamp(selectedSession.created_at) }}
              </span>
              <span v-if="historySessionDuration">
                <svg class="w-3 h-3 inline mr-0.5 -mt-px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"/></svg>
                {{ historySessionDuration }}
              </span>
              <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="statusBadgeClass(selectedSession.status)">{{ selectedSession.status }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button @click="editSessionNotes" class="text-xs text-brand-400 hover:text-brand-300">Edit Notes</button>
            <button v-if="selectedSession.has_chart_data && !selectedSession.chart_data" @click="loadChartData" class="text-xs text-brand-400 hover:text-brand-300" :disabled="loadingChart">
              {{ loadingChart ? 'Loading...' : 'Load Chart' }}
            </button>
            <button @click="loadSessionAsForm" class="text-xs text-brand-400 hover:text-brand-300">Re-run</button>
            <button @click="selectedSession = null" class="text-surface-500 hover:text-surface-200 text-xs">Close</button>
          </div>
        </div>

        <div v-if="selectedSession.hyperparameters && selectedSession.hyperparameters.length" class="flex flex-wrap gap-1.5 mb-4">
          <div v-for="(hp, idx) in selectedSession.hyperparameters" :key="idx" class="px-2 py-1 bg-surface-800 rounded text-[11px]">
            <span class="text-surface-500">{{ Array.isArray(hp) ? hp[0] : hp.name }}:</span>
            <span class="text-surface-200 font-mono ml-0.5">{{ Array.isArray(hp) ? hp[1] : hp.value }}</span>
          </div>
        </div>

        <div v-if="editingNotes" class="mb-4 space-y-2">
          <input v-model="noteTitle" class="input text-xs" placeholder="Session title" />
          <textarea v-model="noteDescription" class="input text-xs resize-none h-16" placeholder="Description (optional)"></textarea>
          <div class="flex gap-2">
            <button @click="saveNotes" class="btn-sm bg-brand-600 text-white" :disabled="savingNotes">{{ savingNotes ? 'Saving...' : 'Save' }}</button>
            <button @click="editingNotes = false" class="btn-sm bg-surface-700 text-surface-300">Cancel</button>
          </div>
        </div>

        <!-- Tabbed detail view -->
        <div class="flex items-center gap-1 border-b border-surface-700 mb-4 overflow-x-auto">
          <button v-for="tab in historyDetailTabs" :key="tab.id"
            @click="historyTab = tab.id"
            class="px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors"
            :class="historyTab === tab.id ? 'border-brand-500 text-brand-400' : 'border-transparent text-surface-500 hover:text-surface-300'">
            {{ tab.label }}
          </button>
        </div>

        <!-- Summary tab -->
        <div v-if="historyTab === 'summary'">
          <div v-if="selectedSession.metrics">
            <div v-if="hPerf.length" class="mb-4">
              <div class="flex items-center justify-between mb-1"><h3 class="text-xs font-semibold text-surface-500">Performance</h3><button @click="showTooltips = !showTooltips" class="text-[10px] px-2 py-0.5 rounded transition-colors" :class="showTooltips ? 'bg-brand-500/20 text-brand-400' : 'bg-surface-700 text-surface-500'">{{ showTooltips ? 'Hints On' : 'Hints Off' }}</button></div>
              <SectionGuide category="performance" />
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in hPerf" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                  <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>
            <div v-if="hHedge.length" class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-1">Hedge Session Stats</h3>
              <SectionGuide category="hedge" />
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in hHedge" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                  <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>
            <div v-if="hRisk.length" class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-1">Risk &amp; Ratios</h3>
              <SectionGuide category="risk" />
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in hRisk" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                  <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>
            <div v-if="hTrade.length" class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-1">Trade Statistics</h3>
              <SectionGuide category="trades" />
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in hTrade" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                  <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>
            <div v-if="hForex.length" class="mb-4">
              <h3 class="text-xs font-semibold text-surface-500 mb-1">Forex / CFD Costs</h3>
              <SectionGuide category="forex" />
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div v-for="m in hForex" :key="m.key" class="p-2 bg-surface-800 rounded">
                  <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                  <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                </div>
              </div>
            </div>
            <div v-if="selectedSession.id" class="mt-4 flex flex-wrap gap-2">
              <a v-if="selectedSession.export_paths?.tradingview" :href="downloadUrl('tradingview', selectedSession.id)" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                TradingView
              </a>
              <a v-if="selectedSession.export_paths?.csv" :href="downloadUrl('csv', selectedSession.id)" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                CSV
              </a>
              <a v-if="selectedSession.export_paths?.json" :href="downloadUrl('json', selectedSession.id)" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                JSON
              </a>
              <a :href="downloadUrl('full-reports', selectedSession.id)" target="_blank" class="btn-sm bg-surface-700 text-surface-300 hover:bg-surface-600 inline-flex items-center gap-1">
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                Full Report
              </a>
            </div>
          </div>
          <div v-else class="text-surface-500 text-sm py-8 text-center">No metrics available for this session.</div>
        </div>

        <!-- Charts tab -->
        <div v-if="historyTab === 'charts'">
          <!-- Interactive Trade Chart (same component as run results) -->
          <div v-if="hChartVisible || hChartCandles.length" class="mb-6">
            <h3 class="text-xs font-semibold text-surface-500 mb-2">Price Chart &amp; Orders</h3>
            <TradeChart
              v-show="hChartVisible"
              ref="hTradeChartRef"
              :candles="hChartCandles"
              :raw-candles="hChartRawCandles"
              :route-timeframe="parseStateRoutes(selectedSession.state)?.[0]?.timeframe || '1h'"
              :orders="hChartOrders"
              :trades="selectedSession.trades || []"
              :equity-curve="historyEquityData.equity || []"
              :balance="selectedSession.metrics?.starting_balance || 10000"
            />
          </div>
          <div v-else-if="selectedSession.has_chart_data" class="mb-4">
            <button @click="loadChartData" class="btn-sm bg-surface-700 text-surface-300" :disabled="loadingChart">
              {{ loadingChart ? 'Loading...' : 'Load Price Charts' }}
            </button>
          </div>
          <div v-else-if="!hChartVisible && !selectedSession.has_chart_data" class="text-surface-500 text-sm py-4 text-center mb-4">
            No chart data stored for this session.
          </div>

          <!-- Equity / Floating PnL / Margin Usage synced charts -->
          <div v-if="historyEquityData.equity" class="space-y-1">
            <span class="text-xs text-surface-500">Synced charts — scroll to zoom, drag to pan</span>
            <div>
              <div class="text-[10px] text-surface-500 mb-0.5 px-1">Equity Curve</div>
              <div ref="hEquityChartEl" class="w-full h-[220px] bg-surface-800 rounded"></div>
            </div>
            <div v-if="historyEquityData.floatingPnl">
              <div class="text-[10px] text-surface-500 mb-0.5 px-1">Floating PnL</div>
              <div ref="hFloatingPnlChartEl" class="w-full h-[180px] bg-surface-800 rounded"></div>
            </div>
            <div v-if="historyEquityData.marginUsage">
              <div class="text-[10px] text-surface-500 mb-0.5 px-1">Margin Usage</div>
              <div ref="hMarginChartEl" class="w-full h-[180px] bg-surface-800 rounded"></div>
            </div>
          </div>
        </div>

        <!-- Sessions tab (hedge sessions) — identical layout to run results -->
        <div v-if="historyTab === 'sessions'">
          <div v-if="!historyHedgeSessions.length" class="text-surface-500 text-sm py-8 text-center">No sessions recorded.</div>
          <div v-if="historyHedgeSessions.length">
            <!-- Session summary stats -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Total Sessions</div>
                <div class="font-mono text-surface-100">{{ historyHedgeSessions.length }}</div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Wins</div>
                <div class="font-mono text-green-400">{{ historyHedgeSessions.filter(s => s.outcome === 'tp_hit' || s.outcome === 'bucket_hit').length }}</div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Max Levels</div>
                <div class="font-mono text-red-400">{{ historyHedgeSessions.filter(s => s.outcome === 'max_levels').length }}</div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Total PnL</div>
                <div class="font-mono" :class="historyHedgeSessions.reduce((a, s) => a + (s.total_pnl || 0), 0) >= 0 ? 'text-green-400' : 'text-red-400'">
                  {{ historyHedgeSessions.reduce((a, s) => a + (s.total_pnl || 0), 0).toFixed(2) }}
                </div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Worst Session Float</div>
                <div class="font-mono text-red-400">{{ Math.min(...historyHedgeSessions.map(s => s.min_float || 0)).toFixed(2) }}</div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Peak Equity Used</div>
                <div class="font-mono" :class="Math.max(...historyHedgeSessions.map(s => s.peak_equity_pct || 0)) > 80 ? 'text-red-400' : 'text-amber-400'">
                  {{ Math.max(...historyHedgeSessions.map(s => s.peak_equity_pct || 0)).toFixed(1) }}%
                </div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Margin Blocks</div>
                <div class="font-mono" :class="historyHedgeSessions.filter(s => s.margin_block_leg != null).length > 0 ? 'text-red-400 font-bold' : 'text-green-400'">
                  {{ historyHedgeSessions.filter(s => s.margin_block_leg != null).length }}
                </div>
              </div>
              <div class="p-2 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Total Fees</div>
                <div class="font-mono text-red-400">{{ historyHedgeSessions.reduce((a, s) => a + (s.total_fee || 0), 0).toFixed(2) }}</div>
              </div>
            </div>

            <!-- Sessions list (expandable) -->
            <div class="space-y-2">
              <div v-for="s in historyPaginatedSessions" :key="s.session" class="bg-surface-800 rounded overflow-hidden">
                <!-- Session header (clickable) -->
                <div
                  @click="historyExpandedSessions[s.session] = !historyExpandedSessions[s.session]"
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
                    <span class="text-xs font-mono" :class="(s.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'">
                      {{ (s.total_pnl || 0) >= 0 ? '+' : '' }}{{ (s.total_pnl || 0).toFixed(2) }}
                    </span>
                    <span class="text-xs text-surface-500">{{ formatTimestamp(s.opened_at) }}</span>
                    <svg
                      class="w-3.5 h-3.5 text-surface-500 transition-transform"
                      :class="{ 'rotate-180': historyExpandedSessions[s.session] }"
                      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                    >
                      <path d="M6 9l6 6 6-6"/>
                    </svg>
                  </div>
                </div>

                <!-- Expanded: session stats + trades -->
                <div v-if="historyExpandedSessions[s.session]" class="border-t border-surface-700">
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
                  <!-- Trades for this session (from stored trades matching session number) -->
                  <div v-if="s.trades && s.trades.length">
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
                            {{ sessionOutcomeLabel(t.meta?.exit_reason) }}
                          </td>
                          <td class="py-1.5 px-2 text-surface-500">{{ t.holding_period || '-' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-else class="px-3 py-2 text-xs text-surface-500">
                    {{ s.trade_count }} trade{{ s.trade_count !== 1 ? 's' : '' }} (expand from Trades tab for details)
                  </div>
                </div>
              </div>
            </div>

            <!-- Pagination -->
            <div v-if="historyHedgeSessions.length > 10" class="flex items-center justify-between mt-3 text-xs text-surface-500">
              <span>{{ historyHedgeSessions.length }} sessions</span>
              <div class="flex items-center gap-2">
                <button @click="historySessionsPage = Math.max(1, historySessionsPage - 1)" :disabled="historySessionsPage <= 1" class="btn-sm bg-surface-700 text-surface-300">Prev</button>
                <span>{{ historySessionsPage }} / {{ Math.ceil(historyHedgeSessions.length / 10) }}</span>
                <button @click="historySessionsPage = Math.min(Math.ceil(historyHedgeSessions.length / 10), historySessionsPage + 1)" :disabled="historySessionsPage >= Math.ceil(historyHedgeSessions.length / 10)" class="btn-sm bg-surface-700 text-surface-300">Next</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Trades tab -->
        <div v-if="historyTab === 'trades'">
          <div v-if="selectedSession.trades && selectedSession.trades.length">
            <div class="text-xs text-surface-500 mb-2">{{ selectedSession.trades.length }} trade{{ selectedSession.trades.length !== 1 ? 's' : '' }}</div>
            <div class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-xs">
                <thead class="sticky top-0 bg-surface-850">
                  <tr class="text-surface-500 border-b border-surface-700">
                    <th class="text-left py-2 px-2">#</th>
                    <th v-if="selectedSession.trades.some(t => t.meta?.session != null)" class="text-left py-2 px-2">Session</th>
                    <th class="text-left py-2 px-2">Type</th>
                    <th class="text-left py-2 px-2">Symbol</th>
                    <th class="text-right py-2 px-2">Entry</th>
                    <th class="text-right py-2 px-2">Exit</th>
                    <th class="text-right py-2 px-2">Qty</th>
                    <th class="text-right py-2 px-2">PnL</th>
                    <th class="text-right py-2 px-2">PnL %</th>
                    <th class="text-right py-2 px-2">Fee</th>
                    <th class="text-left py-2 px-2">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(t, i) in historyPaginatedTrades" :key="i" class="border-b border-surface-800 hover:bg-surface-800/50">
                    <td class="py-1.5 px-2 text-surface-500">{{ (historyTradesPage - 1) * 25 + i + 1 }}</td>
                    <td v-if="selectedSession.trades.some(t2 => t2.meta?.session != null)" class="py-1.5 px-2 font-mono text-brand-400 text-xs">{{ t.meta?.label || (t.meta?.session != null ? `S${t.meta.session}.L${t.meta.leg_index ?? '?'}` : '-') }}</td>
                    <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                    <td class="py-1.5 px-2 text-surface-300">{{ t.symbol || '-' }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.entry_price) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ formatPrice(t.exit_price) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ formatMetric(t.qty) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(t.pnl) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono" :class="(t.pnl_percentage || 0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ t.pnl_percentage != null ? t.pnl_percentage.toFixed(2) + '%' : '-' }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ t.fee ? formatMetric(t.fee) : '-' }}</td>
                    <td class="py-1.5 px-2 text-surface-500">{{ t.holding_period || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="selectedSession.trades.length > 25" class="flex items-center justify-between mt-3 text-xs text-surface-500">
              <span>{{ selectedSession.trades.length }} trades</span>
              <div class="flex items-center gap-2">
                <button @click="historyTradesPage = Math.max(1, historyTradesPage - 1)" :disabled="historyTradesPage <= 1" class="btn-sm bg-surface-700 text-surface-300">Prev</button>
                <span>{{ historyTradesPage }} / {{ Math.ceil(selectedSession.trades.length / 25) }}</span>
                <button @click="historyTradesPage = Math.min(Math.ceil(selectedSession.trades.length / 25), historyTradesPage + 1)" :disabled="historyTradesPage >= Math.ceil(selectedSession.trades.length / 25)" class="btn-sm bg-surface-700 text-surface-300">Next</button>
              </div>
            </div>
          </div>
          <div v-else class="text-surface-500 text-sm py-8 text-center">No trade data stored for this session.</div>
        </div>

        <!-- Costs tab -->
        <div v-if="historyTab === 'costs'">
          <div v-if="selectedSession.metrics">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <div class="p-3 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Total Costs</div>
                <div class="font-mono text-red-400 text-lg">{{ fmtCost(historyCostTotal) }}</div>
              </div>
              <div class="p-3 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Spread Cost</div>
                <div class="font-mono text-surface-100">{{ fmtCost(selectedSession.metrics.total_spread_cost) }}</div>
              </div>
              <div class="p-3 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Swap / Financing</div>
                <div class="font-mono text-surface-100">{{ fmtCost(selectedSession.metrics.total_swap_cost) }}</div>
              </div>
              <div class="p-3 bg-surface-800 rounded">
                <div class="text-surface-500 text-xs">Commissions / Fees</div>
                <div class="font-mono text-surface-100">{{ fmtCost(selectedSession.metrics.fee) }}</div>
              </div>
            </div>
            <div v-if="selectedSession.trades && selectedSession.trades.length" class="overflow-x-auto max-h-[400px]">
              <table class="w-full text-xs">
                <thead class="sticky top-0 bg-surface-850">
                  <tr class="text-surface-500 border-b border-surface-700">
                    <th class="text-left py-2 px-2">#</th>
                    <th class="text-left py-2 px-2">Type</th>
                    <th class="text-left py-2 px-2">Symbol</th>
                    <th class="text-right py-2 px-2">Qty</th>
                    <th class="text-right py-2 px-2">Fee</th>
                    <th class="text-right py-2 px-2">Spread</th>
                    <th class="text-right py-2 px-2">Swap</th>
                    <th class="text-right py-2 px-2">Total</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(t, i) in selectedSession.trades" :key="i" class="border-b border-surface-800">
                    <td class="py-1.5 px-2 text-surface-500">{{ i + 1 }}</td>
                    <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type }}</td>
                    <td class="py-1.5 px-2 text-surface-300">{{ t.symbol || '-' }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ formatMetric(t.qty) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ t.fee ? fmtCost(t.fee) : '-' }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ t.spread_cost ? fmtCost(t.spread_cost) : '-' }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ t.swap_cost ? fmtCost(t.swap_cost) : '-' }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ fmtCost((t.fee || 0) + (t.spread_cost || 0) + (t.swap_cost || 0)) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="text-surface-500 text-sm py-8 text-center">No cost data available for this session.</div>
        </div>

        <!-- Pipeline tab (history) -->
        <div v-if="historyTab === 'pipeline'">
          <PipelineIntelligence v-if="selectedSession.pipeline_stats && Object.keys(selectedSession.pipeline_stats).length" :stats="selectedSession.pipeline_stats" :session-id="selectedSession.id" />
          <div v-else class="text-surface-500 text-sm py-8 text-center">Pipeline data not available. Re-run this backtest with a pipeline to capture stats.</div>
        </div>

        <!-- Logs tab -->
        <div v-if="historyTab === 'logs'">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs text-surface-500">Backtest Logs</span>
            <div class="flex items-center gap-2">
              <a v-if="selectedSession.id" :href="api.getBacktestLogDownloadUrl(selectedSession.id)" target="_blank" class="btn-sm bg-surface-700 text-surface-300">Download</a>
              <button v-if="!historyLogs && selectedSession.id" @click="loadHistoryLogs" class="btn-sm bg-surface-700 text-surface-300" :disabled="loadingHistoryLogs">
                {{ loadingHistoryLogs ? 'Loading...' : 'Load Logs' }}
              </button>
            </div>
          </div>
          <div v-if="historyLogs" class="bg-surface-900 rounded p-3 max-h-[500px] overflow-auto">
            <pre class="text-xs text-surface-400 whitespace-pre-wrap font-mono">{{ historyLogs }}</pre>
          </div>
          <div v-else class="text-surface-500 text-sm py-8 text-center">
            {{ selectedSession.id ? 'Click "Load Logs" to fetch logs.' : 'No logs available.' }}
          </div>
        </div>

        <!-- Strategy Code tab -->
        <div v-if="historyTab === 'code'">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs text-surface-500">Strategy Code Snapshot</span>
            <div class="flex items-center gap-2">
              <button v-if="historyStratCode" @click="copyToClipboard(historyStratCode)" class="btn-sm bg-surface-700 text-surface-300">Copy</button>
              <button v-if="!historyStratCodes && selectedSession.id" @click="loadHistoryStratCode" class="btn-sm bg-surface-700 text-surface-300" :disabled="loadingHistoryStratCode">
                {{ loadingHistoryStratCode ? 'Loading...' : 'Load Code' }}
              </button>
            </div>
          </div>
          <div v-if="historyStratCodes && Object.keys(historyStratCodes).length > 1" class="mb-3">
            <select v-model="historyStratCodeKey" class="select text-xs w-auto inline-block">
              <option v-for="k in Object.keys(historyStratCodes)" :key="k" :value="k">{{ k }}</option>
            </select>
          </div>
          <div v-if="historyStratCode" class="bg-surface-900 rounded p-3 max-h-[500px] overflow-auto">
            <pre class="text-xs text-surface-400 whitespace-pre-wrap font-mono">{{ historyStratCode }}</pre>
          </div>
          <div v-else class="text-surface-500 text-sm py-8 text-center">
            {{ selectedSession.id ? 'Click "Load Code" to fetch strategy code snapshot.' : 'No code available.' }}
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { api, defaultBrokerId, isAdmin, isImpersonating } from '../api'
import { useWebSocket } from '../useWebSocket'
import { createChart, ColorType, LineSeries, AreaSeries, BaselineSeries } from 'lightweight-charts'
import TradeChart from '../components/TradeChart.vue'
import CodeEditor from '../components/CodeEditor.vue'
import { useProcessManager } from '../useProcessManager'
import { useGuides } from '../useGuides'
import MetricTooltip from '../components/MetricTooltip.vue'
import SectionGuide from '../components/SectionGuide.vue'
import PipelineIntelligence from '../components/PipelineIntelligence.vue'

const pm = useProcessManager()
const currentRoute = useRoute()
const { showTooltips } = useGuides()

const pageTab = ref('run')  // 'run' or 'history'

const brokers = ref([])
const strategies = ref([])
const sessions = ref([])
const selectedSession = ref(null)
const openTabs = ref([])
const tabCache = ref({})
const running = ref(false)
const configCollapsed = ref(false)

// Workspace tabs
const workspaceTabs = ref([{ id: 'ws-1', label: 'Backtest 1', running: false, hasResults: false }])
const activeWorkspaceId = ref('ws-1')
const workspaceCache = ref({})
const taskToWorkspace = ref({}) // taskId → workspaceId — survives workspace switches
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
const progress = ref({ current: 0, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 })
const liveLogsExpanded = ref(false)
const liveLogsEl = ref(null)
const marginFreePercent = computed(() => {
  const eq = progress.value.equity
  const mu = progress.value.marginUsed
  if (!eq || eq <= 0) return 100
  return Math.max(0, ((eq - mu) / eq) * 100)
})
const runStartedAt = ref(null)
const elapsedNow = ref(Date.now())
let elapsedTimer = null
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
const pipelineStats = ref(null)
const availablePipelines = ref([])
const livePipelineDecisions = ref([])
const liveEquityHistory = ref([])
const _seenDecisions = new Set()
const liveMiniChartEl = ref(null)
const liveDangerMiniEl = ref(null)

// A/B Comparison (pipeline vs no-pipeline)
const comparisonTaskId = ref(null)
const comparisonRunning = ref(false)
const comparisonProgress = ref(0)
const baselineMetrics = ref(null)
const baselineEquityCurve = ref(null)
const comparisonError = ref('')
const comparisonEquityEl = ref(null)

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
const btPreset = ref(null)
const btPresetData = ref({})

const visibleBtHPs = computed(() =>
  btHyperParams.value.filter(hp => hp.name !== 'preset' && isHpVisible(hp))
)

const btHpGroups = computed(() => {
  const groups = []
  const seen = new Set()
  for (const hp of visibleBtHPs.value) {
    const g = hp.group || 'Other'
    if (!seen.has(g)) { seen.add(g); groups.push({ name: g, hps: [] }) }
    groups.find(x => x.name === g).hps.push(hp)
  }
  return groups
})

// Strategy code
const sessionStrategyCodes = ref(null)
const selectedStrategyCodeKey = ref('')
const loadingStrategyCode = ref(false)

// Chart
const loadingChart = ref(false)
const equityChartEl = ref(null)
const floatingPnlChartEl = ref(null)
const marginChartEl = ref(null)
const dangerChartEl = ref(null)
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

// Collapsible config sections
const showDataRoutes = ref(false)
const showOptions = ref(false)
const showHyperparams = ref(false)
const showResultHP = ref(false)

// History detail tabs
const historyTab = ref('summary')
const historyTradesPage = ref(1)
const historyLogs = ref(null)
const loadingHistoryLogs = ref(false)
const historyStratCodes = ref(null)
const historyStratCodeKey = ref('')
const loadingHistoryStratCode = ref(false)
const historySessionsPage = ref(1)

// History session expansion state
const historyExpandedSessions = ref({})

// History chart refs
const hTradeChartRef = ref(null)
const hChartCandles = ref([])
const hChartRawCandles = ref([])
const hChartOrders = ref([])
const hChartVisible = ref(false)
const hEquityChartEl = ref(null)
const hFloatingPnlChartEl = ref(null)
const hMarginChartEl = ref(null)

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
  backtestMode: 'normal',   // 'normal' or 'pipeline'
  pipelineConfigs: [],      // [{name, ...config}]
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

// Pipeline management
function addPipeline() {
  const first = availablePipelines.value[0]
  form.value.pipelineConfigs.push({ name: first?.name || '' })
}
function removePipeline(idx) {
  form.value.pipelineConfigs.splice(idx, 1)
}
function onPipelineSelect(idx) {
  // Reset config when pipeline type changes (keep name)
  const name = form.value.pipelineConfigs[idx].name
  form.value.pipelineConfigs[idx] = { name }
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
  if (!name) { btHyperParams.value = []; btHyperParamsDefaults.value = []; btPreset.value = null; return }
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
      group: hp.group || undefined,
      options: hp.options || undefined,
      depends_on: hp.depends_on || undefined,
      presets: hp.presets || undefined,
    }))
    btHyperParams.value = hps

    // Extract preset selector (separate from HPs)
    const presetHp = hps.find(h => h.name === 'preset')
    if (presetHp) {
      btPreset.value = presetHp
      btPresetData.value = presetHp.presets || {}
      // Apply default preset values on initial load (not just on user change)
      if (presetHp.value && presetHp.value !== 'custom') {
        onPresetChange()
      }
    } else {
      btPreset.value = null
      btPresetData.value = {}
    }

    // Snapshot defaults AFTER preset application so "Reset" restores preset values
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

function onPresetChange() {
  const presetName = btPreset.value?.value
  if (!presetName || presetName === 'custom') return

  const presetValues = btPresetData.value[presetName]
  if (!presetValues) return

  // Apply preset defaults to HPs
  for (const hp of btHyperParams.value) {
    if (hp.name === 'preset') continue
    if (presetValues[hp.name] !== undefined) {
      hp.value = presetValues[hp.name]
    }
  }
}

function resetBtHyperParams() {
  btHyperParams.value = JSON.parse(JSON.stringify(btHyperParamsDefaults.value))
  // Re-extract preset ref
  const presetHp = btHyperParams.value.find(h => h.name === 'preset')
  if (presetHp) btPreset.value = presetHp
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

// Elapsed timer for running backtest
watch(running, (isRunning) => {
  if (isRunning) {
    elapsedNow.value = Date.now()
    elapsedTimer = setInterval(() => { elapsedNow.value = Date.now() }, 1000)
  } else {
    if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
  }
})

// Watch first route's strategy to auto-load hyperparameters
watch(() => form.value.routes[0]?.strategy, (newStrat, oldStrat) => {
  if (newStrat && newStrat !== oldStrat) {
    loadBacktestHyperparams(newStrat)
  }
})
watch(() => form.value.backtestMode, (mode) => {
  if (mode === 'pipeline' && form.value.pipelineConfigs.length === 0 && availablePipelines.value.length) {
    form.value.pipelineConfigs.push({ name: availablePipelines.value[0].name })
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
  if (pipelineStats.value && Object.keys(pipelineStats.value).length) {
    tabs.push({ id: 'pipeline', label: 'Pipeline Intelligence' })
  }
  tabs.push({ id: 'trades', label: 'Trades', count: trades.value.length })
  tabs.push({ id: 'costs', label: 'Costs' })
  tabs.push({ id: 'logs', label: 'Logs', count: backtestLogs.value.length || undefined })
  tabs.push({ id: 'strategy', label: 'Strategy Code' })
  return tabs
})

function pickMetrics(keys) {
  if (!metrics.value) return []
  return pickMetricsFrom(metrics.value, keys)
}

function pickMetricsFrom(src, keys) {
  if (!src) return []
  return keys
    .filter(([key]) => key in src)
    .map(([key, label]) => ({ key, label, value: src[key] }))
}

// ── A/B Comparison computed ──
const baselineHPsPreview = computed(() => {
  if (!btHyperParams.value.length) return []
  const originalValues = btPresetData.value?.['original'] || {}
  return btHyperParams.value
    .filter(hp => hp.name !== 'preset')
    .map(hp => {
      const val = originalValues[hp.name] !== undefined
        ? originalValues[hp.name]
        : (hp.default !== undefined ? hp.default : hp.value)
      const isPreset = originalValues[hp.name] !== undefined
      return { name: hp.name, value: val, isPreset }
    })
})

const comparisonDeltas = computed(() => {
  if (!metrics.value || !baselineMetrics.value) return []
  const keys = [
    { key: 'net_profit_percentage', label: 'Net Profit %', fmt: v => v.toFixed(2) + '%', higherBetter: true },
    { key: 'total_sessions', label: 'Sessions', fmt: v => String(Math.round(v)), higherBetter: null },
    { key: 'session_win_rate', label: 'Session Win Rate', fmt: v => (v * 100).toFixed(1) + '%', higherBetter: true },
    { key: 'total_losing_sessions', label: 'Lost Sessions', fmt: v => String(Math.round(v)), higherBetter: false },
    { key: 'profit_factor', label: 'Profit Factor', fmt: v => v.toFixed(2), higherBetter: true },
    { key: 'max_drawdown', label: 'Max Drawdown %', fmt: v => v.toFixed(2) + '%', higherBetter: false },
    { key: 'worst_floating_pnl', label: 'Worst Float', fmt: v => v.toFixed(2), higherBetter: false },
    { key: 'total_busts', label: 'Busts', fmt: v => String(Math.round(v)), higherBetter: false },
    { key: 'worst_bust_pnl', label: 'Worst Bust', fmt: v => v.toFixed(2), higherBetter: false },
    { key: 'sharpe_ratio', label: 'Sharpe Ratio', fmt: v => v.toFixed(2), higherBetter: true },
  ]
  return keys.map(k => {
    const p = metrics.value[k.key] ?? 0
    const b = baselineMetrics.value[k.key] ?? 0
    const delta = p - b
    const positive = k.higherBetter === null ? delta >= 0 : (k.higherBetter ? delta >= 0 : delta <= 0)
    return {
      key: k.key, label: k.label,
      pipeline: p, baseline: b,
      pipelineFormatted: k.fmt(p), baselineFormatted: k.fmt(b),
      deltaFormatted: k.fmt(delta), deltaPositive: positive,
    }
  })
})

const depthComparison = computed(() => {
  if (!metrics.value || !baselineMetrics.value) return []
  const pDepths = metrics.value.depth_breakdown || []
  const bDepths = baselineMetrics.value.depth_breakdown || []
  if (!pDepths.length && !bDepths.length) return []

  // Merge all depths from both runs
  const allDepths = new Set([
    ...pDepths.map(d => d.depth),
    ...bDepths.map(d => d.depth),
  ])
  const empty = { count: 0, wins: 0, losses: 0, pnl: 0 }
  const pMap = Object.fromEntries(pDepths.map(d => [d.depth, d]))
  const bMap = Object.fromEntries(bDepths.map(d => [d.depth, d]))

  return [...allDepths].sort((a, b) => a - b).map(depth => ({
    depth,
    pipeline: pMap[depth] || { ...empty },
    baseline: bMap[depth] || { ...empty },
  }))
})

const pipelineNetDelta = computed(() => {
  if (!metrics.value || !baselineMetrics.value) return 0
  return (metrics.value.net_profit_percentage || 0) - (baselineMetrics.value.net_profit_percentage || 0)
})

const pipelineWins = computed(() => pipelineNetDelta.value >= 0)

// Metric key lists (reused for both run results and history detail)
const perfKeys = [
  ['gross_pnl', 'Gross PnL (Trades)'], ['net_profit', 'Net Profit'], ['net_profit_percentage', 'Net Profit %'],
  ['annual_return', 'Annual Return'], ['win_rate', 'Win Rate'], ['profit_factor', 'Profit Factor'],
  ['expectancy', 'Expectancy'], ['starting_balance', 'Starting Balance'], ['finishing_balance', 'Finishing Balance'],
]
const tradeKeys = [
  ['total', 'Total Trades'], ['total_completed_trades', 'Completed Trades'],
  ['total_winning_trades', 'Winning Trades'], ['total_losing_trades', 'Losing Trades'],
  ['total_open_trades', 'Open Trades'], ['longs_count', 'Longs'], ['shorts_count', 'Shorts'],
  ['longs_percentage', 'Longs %'], ['shorts_percentage', 'Shorts %'],
  ['largest_winning_trade', 'Largest Win'], ['largest_losing_trade', 'Largest Loss'],
  ['winning_streak', 'Win Streak'], ['losing_streak', 'Lose Streak'],
  ['average_win', 'Avg Win'], ['average_loss', 'Avg Loss'],
  ['average_win_loss', 'Win/Loss Ratio'], ['fee', 'Total Fees'], ['open_pl', 'Open P&L'],
]
const riskKeys = [
  ['max_drawdown', 'Max Drawdown %'],
  ['sharpe_ratio', 'Sharpe Ratio'], ['smart_sharpe', 'Smart Sharpe'],
  ['sortino_ratio', 'Sortino Ratio'], ['smart_sortino', 'Smart Sortino'],
  ['calmar_ratio', 'Calmar Ratio'], ['omega_ratio', 'Omega Ratio'],
  ['serenity_index', 'Serenity Index'], ['kelly_criterion', 'Kelly Criterion'],
  ['var_95', 'VaR 95%'], ['var_99', 'VaR 99%'],
  ['cvar_95', 'CVaR 95% (Tail Risk)'], ['cvar_99', 'CVaR 99% (Tail Risk)'],
  ['worst_floating_pnl', 'Worst Floating Loss'], ['peak_margin_used', 'Peak Margin Used'],
  ['peak_equity_usage_pct', 'Peak Equity Used %'], ['margin_closeouts', 'Margin Close-outs'],
  ['account_blown', 'Account Blown'],
]
const forexKeys = [
  ['total_pips', 'Total Pips'], ['avg_pips_per_trade', 'Avg Pips/Trade'],
  ['total_spread_cost', 'Total Spread Cost'], ['total_swap_cost', 'Total Swap Cost'],
]
const hedgeKeys = [
  ['total_sessions', 'Total Sessions'], ['session_win_rate', 'Session Win Rate'],
  ['total_losing_sessions', 'Lost Sessions'],
  ['avg_session_win', 'Avg Session Win'], ['avg_session_loss', 'Avg Session Loss'],
  ['ev_per_session', 'EV / Session'], ['avg_legs_per_session', 'Avg Legs / Session'],
  ['max_legs_in_session', 'Max Legs in Session'], ['sessions_with_1_leg', 'Sessions with 1 Leg'],
  ['max_consecutive_session_wins', 'Max Consec. Session Wins'], ['max_consecutive_session_losses', 'Max Consec. Session Losses'],
  ['total_busts', 'Busts'], ['worst_bust_pnl', 'Worst Bust PnL'],
]

const performanceMetrics = computed(() => pickMetrics(perfKeys))
const tradeStatsMetrics = computed(() => pickMetrics(tradeKeys))
const riskMetrics = computed(() => pickMetrics(riskKeys))
const forexMetrics = computed(() => pickMetrics(forexKeys))
const hedgeSessionMetrics = computed(() => pickMetrics(hedgeKeys))

// ── Martingale-mode key arrays ──
const isMartingale = computed(() => metrics.value?.is_martingale === true)

const sessionPerfKeys = [
  ['total_sessions', 'Sessions'], ['session_win_rate', 'Session Win Rate'],
  ['session_profit_factor', 'Session Profit Factor'], ['ev_per_session', 'EV / Session'],
  ['median_session_pnl', 'Median Session PnL'],
  ['net_profit', 'Net Profit'], ['net_profit_percentage', 'Net Profit %'],
  ['annual_return', 'Annual Return'], ['starting_balance', 'Starting Balance'],
  ['finishing_balance', 'Finishing Balance'],
]
const survivalKeys = [
  ['bust_rate', 'Bust Rate'], ['bust_count', 'Busts'],
  ['wins_to_recover', 'Wins to Recover'], ['geometric_growth_rate', 'Geometric Growth Rate'],
  ['survival_100', 'P(Survive 100)'], ['survival_500', 'P(Survive 500)'],
  ['survival_half_life', 'Half-Life (sessions)'],
  ['worst_bust_pnl', 'Worst Bust PnL'], ['avg_bust_loss', 'Avg Bust Loss'],
  ['bust_severity_std', 'Bust Severity Spread'],
  ['max_drawdown', 'Max Drawdown %'], ['max_consecutive_session_losses', 'Max Consec. Losses'],
  ['margin_closeouts', 'Margin Close-outs'], ['account_blown', 'Account Blown'],
]
const structuralKeys = [
  ['l0_win_rate', 'L0 Win Rate'], ['avg_legs_per_session', 'Avg Legs / Session'],
  ['max_legs_in_session', 'Max Legs in Session'], ['sessions_with_1_leg', 'L0 Wins (1-leg)'],
]
const capitalKeys = [
  ['peak_margin_used', 'Peak Margin Used'], ['peak_equity_usage_pct', 'Peak Equity Used %'],
  ['worst_floating_pnl', 'Worst Floating Loss'], ['profit_factor', 'Profit Factor'],
  ['fee', 'Total Fees'], ['total_spread_cost', 'Total Spread Cost'],
  ['total_swap_cost', 'Total Swap Cost'], ['total_pips', 'Total Pips'],
  ['avg_pips_per_trade', 'Avg Pips / Trade'], ['cost_drag_pct', 'Cost Drag %'],
]

const mSessionPerf = computed(() => pickMetrics(sessionPerfKeys))
const mSurvival = computed(() => pickMetrics(survivalKeys))
const mStructural = computed(() => pickMetrics(structuralKeys))
const mCapital = computed(() => pickMetrics(capitalKeys))

// History session detail metrics (from selectedSession.metrics)
const hPerf = computed(() => pickMetricsFrom(selectedSession.value?.metrics, perfKeys))
const hTrade = computed(() => pickMetricsFrom(selectedSession.value?.metrics, tradeKeys))
const hRisk = computed(() => pickMetricsFrom(selectedSession.value?.metrics, riskKeys))
const hForex = computed(() => pickMetricsFrom(selectedSession.value?.metrics, forexKeys))
const hHedge = computed(() => pickMetricsFrom(selectedSession.value?.metrics, hedgeKeys))

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

// Session analytics (martingale-aware)
const sessionAnalytics = computed(() => {
  const sessions = hedgeSessions.value
  if (!sessions.length) return null

  const wins = sessions.filter(s => s.outcome === 'tp_hit' || s.outcome === 'bucket_hit')
  const busts = sessions.filter(s => s.outcome === 'max_levels' || s.outcome === 'max_level_sl')
  const aborts = sessions.filter(s => s.outcome === 'abort' || s.outcome === 'pipeline_abort')

  const winPnls = wins.map(s => s.total_pnl)
  const bustPnls = busts.map(s => s.total_pnl)
  const abortPnls = aborts.map(s => s.total_pnl)

  // Current streak from end
  let streak = 0
  let streakType = null
  for (let i = sessions.length - 1; i >= 0; i--) {
    const isWin = sessions[i].outcome === 'tp_hit' || sessions[i].outcome === 'bucket_hit'
    if (streakType === null) streakType = isWin
    if (isWin === streakType) streak++
    else break
  }

  // Wins since last bust
  let winsSinceLastBust = 0
  for (let i = sessions.length - 1; i >= 0; i--) {
    if (sessions[i].outcome === 'max_levels' || sessions[i].outcome === 'max_level_sl') break
    if (sessions[i].outcome === 'tp_hit' || sessions[i].outcome === 'bucket_hit') winsSinceLastBust++
  }

  // Avg session duration
  const durations = sessions
    .filter(s => s.opened_at && s.closed_at)
    .map(s => (s.closed_at - s.opened_at) / 1000)
  const avgDurationSec = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : 0

  // Avg equity usage
  const equityPcts = sessions.map(s => s.peak_equity_pct || 0).filter(v => v > 0)
  const avgEquityPct = equityPcts.length ? equityPcts.reduce((a, b) => a + b, 0) / equityPcts.length : 0

  return {
    total: sessions.length,
    wins: wins.length,
    winPct: sessions.length ? (wins.length / sessions.length * 100) : 0,
    busts: busts.length,
    bustTotalPnl: bustPnls.reduce((a, b) => a + b, 0),
    aborts: aborts.length,
    abortTotalPnl: abortPnls.reduce((a, b) => a + b, 0),
    totalPnl: sessions.reduce((a, s) => a + s.total_pnl, 0),
    avgWinPnl: winPnls.length ? winPnls.reduce((a, b) => a + b, 0) / winPnls.length : 0,
    avgBustLoss: bustPnls.length ? bustPnls.reduce((a, b) => a + b, 0) / bustPnls.length : 0,
    streak: streak * (streakType ? 1 : -1),
    winsSinceLastBust,
    wtr: metrics.value?.wins_to_recover || 0,
    hasBusts: busts.length > 0,
    worstFloat: Math.min(...sessions.map(s => s.min_float || 0)),
    peakEquityPct: Math.max(...sessions.map(s => s.peak_equity_pct || 0)),
    avgEquityPct,
    marginBlocks: sessions.filter(s => s.margin_block_leg != null).length,
    avgDurationSec,
    totalFees: sessions.reduce((a, s) => a + (s.total_fee || 0), 0),
  }
})

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '-'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

// Cost by depth level (martingale)
const costByDepth = computed(() => {
  if (!hedgeSessions.value.length) return []
  const map = {}
  for (const s of hedgeSessions.value) {
    const d = s.levels || 0
    if (!map[d]) map[d] = { depth: d, count: 0, totalCost: 0, totalPnl: 0 }
    map[d].count++
    map[d].totalCost += s.total_fee || 0
    map[d].totalPnl += s.total_pnl
  }
  return Object.values(map).sort((a, b) => a.depth - b.depth).map(d => ({
    ...d,
    avgCost: d.count ? d.totalCost / d.count : 0,
    netAfterCost: d.totalPnl,
    costPct: d.totalPnl > 0 ? (d.totalCost / d.totalPnl * 100) : 0,
  }))
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

// History tab computed properties
const optionsSummary = computed(() => {
  const opts = []
  if (form.value.debugMode) opts.push('Debug')
  if (form.value.exportChart) opts.push('Charts')
  if (form.value.costModel) opts.push('Costs')
  if (form.value.exportCsv) opts.push('CSV')
  if (form.value.exportTradingview) opts.push('TV')
  if (form.value.exportJson) opts.push('JSON')
  return opts.length ? opts.join(', ') : 'None'
})

const historyDetailTabs = computed(() => {
  const tabs = [{ id: 'summary', label: 'Summary' }]
  const s = selectedSession.value
  if (s) {
    tabs.push({ id: 'charts', label: 'Charts' })
    const hs = historyHedgeSessions.value
    if (hs.length) tabs.push({ id: 'sessions', label: `Sessions (${hs.length})` })
    tabs.push({ id: 'trades', label: `Trades${s.trades?.length ? ` (${s.trades.length})` : ''}` })
    tabs.push({ id: 'costs', label: 'Costs' })
    if (s.has_pipeline || s.pipeline_stats) tabs.push({ id: 'pipeline', label: 'Pipeline' })
    tabs.push({ id: 'logs', label: 'Logs' })
    tabs.push({ id: 'code', label: 'Strategy Code' })
  }
  return tabs
})

const historySessionTitle = computed(() => {
  const s = selectedSession.value
  if (!s) return ''
  if (s.title) return s.title
  return sessionLabel(s)
})

const historySessionDuration = computed(() => {
  return computeSessionDuration(selectedSession.value)
})

const historyPaginatedTrades = computed(() => {
  const trades = selectedSession.value?.trades || []
  const start = (historyTradesPage.value - 1) * 25
  return trades.slice(start, start + 25)
})

const historyStratCode = computed(() => {
  if (!historyStratCodes.value) return null
  const keys = Object.keys(historyStratCodes.value)
  const key = historyStratCodeKey.value || keys[0]
  return historyStratCodes.value[key] || null
})

// History hedge sessions — use stored sessions (with full stats) when available, fall back to rebuilding from trades
const historyHedgeSessions = computed(() => {
  const stored = selectedSession.value?.sessions
  const allTrades = selectedSession.value?.trades || []
  if (stored && stored.length) {
    // Stored sessions have stats but trades were stripped to save DB space.
    // Re-attach trades from the stored trades array by matching meta.session.
    const tradesBySession = {}
    for (const t of allTrades) {
      const sn = t.meta?.session
      if (sn != null) {
        if (!tradesBySession[sn]) tradesBySession[sn] = []
        tradesBySession[sn].push(t)
      }
    }
    return stored.map(s => ({
      ...s,
      trades: tradesBySession[s.session] || [],
      trade_count: s.trade_count || (tradesBySession[s.session] || []).length,
    }))
  }
  if (!allTrades.length) return []
  return buildSessionsFromTrades(allTrades)
})

const historyPaginatedSessions = computed(() => {
  const start = (historySessionsPage.value - 1) * 10
  return historyHedgeSessions.value.slice(start, start + 10)
})

// History equity bundle parsing
const historyEquityData = computed(() => {
  const ec = selectedSession.value?.equity_curve
  if (!ec) return { equity: null, floatingPnl: null, marginUsage: null }
  // Bundled format: { equity, floating_pnl, margin_usage }
  if (ec.equity) return { equity: ec.equity, floatingPnl: ec.floating_pnl || null, marginUsage: ec.margin_usage || null }
  // Raw array format
  return { equity: ec, floatingPnl: null, marginUsage: null }
})

const historyCostTotal = computed(() => {
  const m = selectedSession.value?.metrics
  if (!m) return 0
  return Math.abs(m.fee || 0) + Math.abs(m.total_spread_cost || 0) + Math.abs(m.total_swap_cost || 0)
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
  if (outcome === 'max_levels' || outcome === 'max_level_sl') return 'text-red-400'
  if (outcome === 'abort' || outcome === 'pipeline_abort') return 'text-amber-400'
  return 'text-surface-400'
}

const KEY_GENES = new Set([
  'gate_confidence_min', 'abort_aggressiveness', 'base_size_pct', 'max_levels',
  'signal_mode', 'direction_bias', 'entry_on_crossover',
  'ema_fast', 'ema_slow', 'hedge_mode', 'hedge_value', 'tp_mode', 'tp_value',
  'sizing_curve', 'sizing_factor', 'hysteresis_margin', 'confidence_sensitivity',
  // Strategy HP keys (GridPilot mode)
  'preset', 'multiplier', 'tp_pips', 'hedge_pips', 'lot_size', 'cooldown_mode',
  'cooldown_value', 'bust_protection', 'max_level', 'entry_signal',
])
function isKeyGene(key) {
  return KEY_GENES.has(key)
}

function sessionHP(s) {
  // Return genes (IslandPilot evolved) or hp (GridPilot strategy HP), or null
  const genes = s.pipeline?.genes
  if (genes && Object.keys(genes).length) return genes
  const hp = s.pipeline?.hp
  if (hp && Object.keys(hp).length) return hp
  return null
}

function formatHPVal(val) {
  if (val == null) return '-'
  if (typeof val === 'boolean') return val ? 'yes' : 'no'
  if (typeof val === 'number') return Number.isInteger(val) ? String(val) : val.toFixed(4)
  return String(val)
}

function sessionOutcomeLabel(outcome) {
  if (outcome === 'tp_hit') return 'TP Hit'
  if (outcome === 'bucket_hit') return 'Bucket Hit'
  if (outcome === 'max_levels') return 'Max Levels'
  if (outcome === 'max_level_sl') return 'Max Level SL'
  if (outcome === 'sl_hit') return 'SL Hit'
  if (outcome === 'abort') return 'Abort'
  if (outcome === 'terminated' || outcome === 'terminate') return 'Terminated'
  if (outcome === 'pipeline_abort') return 'Pipeline Abort'
  if (outcome === 'standalone') return 'Single'
  return outcome || '-'
}

const currentStrategyCode = computed(() => {
  if (!sessionStrategyCodes.value) return null
  const keys = Object.keys(sessionStrategyCodes.value)
  const key = selectedStrategyCodeKey.value || keys[0]
  return sessionStrategyCodes.value[key] || null
})

const showOwnerColumn = computed(() => isAdmin() && !isImpersonating())
const runningSessions = computed(() => sessions.value.filter(s => s.is_active))

const filteredSessions = computed(() => {
  let list = sessions.value.filter(s => !s.is_active) // exclude running from main list
  if (sessionSearch.value) {
    const q = sessionSearch.value.toLowerCase()
    list = list.filter(s => {
      const label = sessionLabel(s).toLowerCase()
      return label.includes(q) || (s.id || '').toLowerCase().includes(q)
    })
  }
  if (sessionStatusFilter.value) {
    list = list.filter(s => s.status === sessionStatusFilter.value)
  }
  return list
})

const runningWorkspaceCount = computed(() => workspaceTabs.value.filter(t => t.running).length)

// ── Workspace management ──
const _wsRefs = {
  form, running, error, errorTrace, message, currentTaskId, sessionId, runStartedAt,
  progress, metrics, hyperparameters, generalInfo,
  equityCurve, floatingPnlCurve, marginUsageCurve,
  trades, hedgeSessions, exposureTable, exposureHasTpSl, exposureMeta, exposureSizeDisplay,
  activeTab, selectedRouteIdx, tradesPage, sessionsPage, expandedSessions, costTradesPage,
  logs, backtestLogs, logFilter,
  btHyperParams, btHyperParamsDefaults, btCustomHPs, btPreset, btPresetData, visibleBtHPs, btHpGroups, onPresetChange,
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
      routes: [{ symbol: 'EUR-USD', timeframe: '1m', strategy: strategies.value[0]?.name || 'ForexMA' }],
      data_routes: [], startDate: '2024-01-01', endDate: '2024-06-01', balance: 10000, warmUpCandles: 240,
      debugMode: true, exportChart: true, exportTradingview: true, exportCsv: true, exportJson: false,
      fastMode: false, benchmark: false, costModel: true,
    },
    running: false, error: '', errorTrace: '', message: '',
    currentTaskId: null, sessionId: null, runStartedAt: null,
    progress: { current: 0, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 },
    metrics: null, hyperparameters: null, generalInfo: null,
    equityCurve: [], floatingPnlCurve: null, marginUsageCurve: null,
    trades: [], hedgeSessions: [], exposureTable: [],
    activeTab: 'summary', selectedRouteIdx: 0, tradesPage: 1, sessionsPage: 1, expandedSessions: {}, costTradesPage: 1,
    logs: null, backtestLogs: [], logFilter: 'all',
    btHyperParams: [], btHyperParamsDefaults: [], btCustomHPs: [], btPreset: null, btPresetData: {},
    sessionStrategyCodes: null, selectedStrategyCodeKey: '',
    btChartCandles: [], btChartRawCandles: [], btChartOrders: [], btChartVisible: false,
    selectedSession: null, openTabs: [], tabCache: {},
  }
}

function addWorkspace() {
  wsCounter++
  const id = `ws-${wsCounter}`
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  workspaceTabs.value.push({ id, label: `Backtest ${wsCounter}`, running: false, hasResults: false })
  activeWorkspaceId.value = id
  _restoreWs(_freshDefaults())
  if (btTradeChartRef.value) btTradeChartRef.value.destroy()
}

function switchWorkspace(id) {
  if (id === activeWorkspaceId.value) return
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  activeWorkspaceId.value = id
  const cached = workspaceCache.value[id]
  if (cached) { _restoreWs(cached); delete workspaceCache.value[id] }
  else _restoreWs(_freshDefaults())
  if (btTradeChartRef.value) btTradeChartRef.value.destroy()
}

function closeWorkspace(id) {
  if (workspaceTabs.value.length <= 1) return
  // Prevent closing a workspace with a running backtest
  const tab = workspaceTabs.value.find(t => t.id === id)
  if (tab?.running) return
  const wasActive = id === activeWorkspaceId.value
  workspaceTabs.value = workspaceTabs.value.filter(t => t.id !== id)
  // Clean up task mapping for this workspace
  for (const [tid, wsId] of Object.entries(taskToWorkspace.value)) {
    if (wsId === id) delete taskToWorkspace.value[tid]
  }
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

function _updateWsTab(wsId, props) {
  const tab = workspaceTabs.value.find(t => t.id === wsId)
  if (tab) Object.assign(tab, props)
}

function _findWorkspaceForTask(taskId) {
  // Check explicit mapping first
  if (taskToWorkspace.value[taskId]) return taskToWorkspace.value[taskId]
  // Check active workspace
  if (currentTaskId.value === taskId) return activeWorkspaceId.value
  // Check cached workspaces
  for (const [wsId, snap] of Object.entries(workspaceCache.value)) {
    if (snap.currentTaskId === taskId) return wsId
  }
  return null
}

function _updateCachedWorkspace(wsId, updates) {
  const snap = workspaceCache.value[wsId]
  if (!snap) return
  Object.assign(snap, updates)
}

// ── WebSocket handler ──
useWebSocket((msg) => {
  const { event, id, data } = msg
  // msg.id is the session UUID (ws_manager converts PID → client_id before broadcast).
  if (!event?.startsWith('backtest.')) return

  // Handle A/B comparison backtest events (must be checked before workspace routing)
  if (id && id === comparisonTaskId.value) {
    if (event === 'backtest.progressbar') {
      comparisonProgress.value = data?.current || 0
    } else if (event === 'backtest.metrics') {
      baselineMetrics.value = data
      comparisonRunning.value = false
      comparisonProgress.value = 100
    } else if (event === 'backtest.equity_curve') {
      baselineEquityCurve.value = data
      nextTick(() => drawComparisonEquity())
    } else if (event === 'backtest.exception') {
      comparisonRunning.value = false
      comparisonProgress.value = 0
      comparisonError.value = cleanErrorMessage(data?.error || 'Baseline comparison failed')
    } else if (event === 'backtest.termination') {
      comparisonRunning.value = false
      comparisonProgress.value = 0
      comparisonError.value = 'Baseline comparison was terminated'
    }
    return
  }

  // Determine which workspace this event belongs to
  const targetWsId = id ? _findWorkspaceForTask(id) : null
  const isActiveWs = !targetWsId || targetWsId === activeWorkspaceId.value

  // Auto-adopt: page refreshed, unknown task sending progress — assign to a free workspace
  if (!targetWsId && id && event === 'backtest.progressbar') {
    // Check if any workspace already has this task (shouldn't happen, but guard)
    if (!_findWorkspaceForTask(id)) {
      // Assign to active workspace if it's idle, otherwise create a new one
      if (!currentTaskId.value) {
        currentTaskId.value = id
        running.value = true
        runStartedAt.value = Date.now()
        taskToWorkspace.value[id] = activeWorkspaceId.value
        _updateActiveWsTab({ running: true })
        pageTab.value = 'run'
        if (!pm.get(id)) pm.register(id, { type: 'backtest', label: 'Backtest (resumed)', cancelFn: cancelBacktest, routePath: '/backtest' })
      } else {
        // Active workspace busy — create a new workspace for this orphan task
        wsCounter++
        const newWsId = `ws-${wsCounter}`
        const defaults = _freshDefaults()
        defaults.currentTaskId = id
        defaults.running = true
        workspaceTabs.value.push({ id: newWsId, label: `Backtest ${wsCounter}`, running: true, hasResults: false })
        workspaceCache.value[newWsId] = defaults
        taskToWorkspace.value[id] = newWsId
        if (!pm.get(id)) pm.register(id, { type: 'backtest', label: `Backtest ${wsCounter}`, cancelFn: cancelBacktest, routePath: '/backtest' })
      }
      // Re-resolve after adoption
      return
    }
  }

  // If event is for a different (cached) workspace, update the cache
  if (!isActiveWs && targetWsId) {
    _handleCachedWsEvent(targetWsId, event, data, id)
    return
  }

  // If event has an id but doesn't match any workspace, ignore it
  if (id && currentTaskId.value && id !== currentTaskId.value) return

  // ── Handle events for the active workspace ──
  if (event === 'backtest.progressbar') {
    progress.value = {
      current: data?.current || 0,
      eta: data?.estimated_remaining_seconds || 0,
      currentDate: data?.current_date || null,
      equity: data?.equity ?? null,
      floatingPnl: data?.floating_pnl ?? null,
      marginUsed: data?.margin_used ?? null,
      session: data?.session ?? null,
      trades: data?.trades ?? 0,
      pipelineDanger: data?.pipeline_danger ?? null,
      pipelineDangerMean: data?.pipeline_danger_mean ?? null,
      pipelineBlocks: data?.pipeline_blocks ?? null,
      pipelineAborts: data?.pipeline_aborts ?? null,
      pipelineCycles: data?.pipeline_cycles ?? null,
      pipelineDangerHistory: data?.pipeline_danger_history ?? null,
      pipelineDecisions: data?.pipeline_decisions ?? null,
    }
    // Accumulate live logs from progress updates
    if (data?.recent_logs?.length) {
      for (const log of data.recent_logs) {
        backtestLogs.value.push(log)
      }
      // Cap at 500 entries to avoid memory bloat
      if (backtestLogs.value.length > 500) {
        backtestLogs.value = backtestLogs.value.slice(-500)
      }
      // Auto-scroll if expanded
      if (liveLogsExpanded.value && liveLogsEl.value) {
        nextTick(() => {
          if (liveLogsEl.value) liveLogsEl.value.scrollTop = liveLogsEl.value.scrollHeight
        })
      }
    }
    // Accumulate pipeline decisions for live feed
    if (data?.pipeline_decisions?.length) {
      for (const d of data.pipeline_decisions) {
        const key = `${d.type}-${d.ts}-${d.decision}`
        if (!_seenDecisions.has(key)) {
          _seenDecisions.add(key)
          livePipelineDecisions.value.push(d)
          if (livePipelineDecisions.value.length > 50) livePipelineDecisions.value.shift()
        }
      }
    }
    // Accumulate equity history for live mini-chart
    if (data?.equity != null) {
      liveEquityHistory.value.push({ ts: data.current_date || Date.now(), equity: data.equity })
      if (liveEquityHistory.value.length > 120) liveEquityHistory.value.shift()
    }
    if (currentTaskId.value) pm.update(currentTaskId.value, { progress: data?.current || 0, eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'backtest.equity_curve') {
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
    progress.value = { current: 100, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 }
    sessionId.value = currentTaskId.value
    pm.complete(currentTaskId.value)
    delete taskToWorkspace.value[currentTaskId.value]
    _updateActiveWsTab({ running: false, hasResults: true })
    setTimeout(loadSessions, 1000)
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
  } else if (event === 'backtest.pipeline_stats') {
    pipelineStats.value = data
  } else if (event === 'backtest.exception') {
    error.value = cleanErrorMessage(data?.error || 'Backtest failed')
    errorTrace.value = data?.traceback || ''
    running.value = false
    progress.value = { current: 0, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 }
    pm.fail(currentTaskId.value)
    delete taskToWorkspace.value[currentTaskId.value]
    _updateActiveWsTab({ running: false })
  } else if (event === 'backtest.termination') {
    running.value = false
    message.value = 'Backtest was terminated.'
    progress.value = { current: 0, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 }
    pm.cancel(currentTaskId.value)
    delete taskToWorkspace.value[currentTaskId.value]
    _updateActiveWsTab({ running: false })
  } else if (event === 'backtest.notification') {
    if (data?.type === 'error') {
      error.value = data?.message || ''
    }
  }
})

function _handleCachedWsEvent(wsId, event, data, taskId) {
  const snap = workspaceCache.value[wsId]
  if (!snap) return
  const emptyProgress = { current: 0, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 }

  if (event === 'backtest.progressbar') {
    snap.progress = {
      current: data?.current || 0,
      eta: data?.estimated_remaining_seconds || 0,
      currentDate: data?.current_date || null,
      equity: data?.equity ?? null,
      floatingPnl: data?.floating_pnl ?? null,
      marginUsed: data?.margin_used ?? null,
      session: data?.session ?? null,
      trades: data?.trades ?? 0,
    }
    if (taskId) pm.update(taskId, { progress: data?.current || 0, eta: data?.estimated_remaining_seconds || 0 })
  } else if (event === 'backtest.equity_curve') {
    if (data) snap.equityCurve = data
  } else if (event === 'backtest.floating_pnl_curve') {
    if (data) snap.floatingPnlCurve = data
  } else if (event === 'backtest.margin_usage_curve') {
    if (data) snap.marginUsageCurve = data
  } else if (event === 'backtest.trades') {
    if (data) { snap.trades = Array.isArray(data) ? data : []; snap.tradesPage = 1 }
  } else if (event === 'backtest.sessions') {
    if (data) { snap.hedgeSessions = Array.isArray(data) ? data : []; snap.sessionsPage = 1 }
  } else if (event === 'backtest.metrics') {
    snap.metrics = data
    snap.running = false
    snap.message = 'Backtest completed!'
    snap.progress = { current: 100, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 }
    snap.sessionId = snap.currentTaskId
    pm.complete(taskId)
    delete taskToWorkspace.value[taskId]
    _updateWsTab(wsId, { running: false, hasResults: true })
    setTimeout(loadSessions, 1000)
  } else if (event === 'backtest.backtest_logs') {
    if (data) snap.backtestLogs = Array.isArray(data) ? data : []
  } else if (event === 'backtest.hyperparameters') {
    snap.hyperparameters = data
  } else if (event === 'backtest.general_info') {
    snap.generalInfo = data
  } else if (event === 'backtest.exception') {
    snap.error = cleanErrorMessage(data?.error || 'Backtest failed')
    snap.errorTrace = data?.traceback || ''
    snap.running = false
    snap.progress = { ...emptyProgress }
    pm.fail(taskId)
    delete taskToWorkspace.value[taskId]
    _updateWsTab(wsId, { running: false })
  } else if (event === 'backtest.termination') {
    snap.running = false
    snap.message = 'Backtest was terminated.'
    snap.progress = { ...emptyProgress }
    pm.cancel(taskId)
    delete taskToWorkspace.value[taskId]
    _updateWsTab(wsId, { running: false })
  }
}

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
  if (status === 'stopped') return 'bg-orange-500/20 text-orange-400'
  if (status === 'cancelled' || status === 'failed') return 'bg-red-500/20 text-red-400'
  return 'bg-surface-700 text-surface-400'
}

function parseStateRoutes(state) {
  if (!state) return []
  if (typeof state === 'string') {
    try { state = JSON.parse(state) } catch { return [] }
  }
  const routes = state.routes || state.form?.routes || []
  return Array.isArray(routes) ? routes : []
}

function parseStateExchange(state) {
  if (!state) return ''
  if (typeof state === 'string') {
    try { state = JSON.parse(state) } catch { return '' }
  }
  return state.exchange || state.form?.exchange || ''
}

function parseStateDates(state) {
  if (!state) return { start: '', end: '' }
  if (typeof state === 'string') {
    try { state = JSON.parse(state) } catch { return { start: '', end: '' } }
  }
  const src = state.form || state
  return {
    start: src.start_date || src.startDate || '',
    end: src.finish_date || src.endDate || '',
  }
}

function sessionLabel(s) {
  if (s.title) return s.title
  const routes = parseStateRoutes(s.state)
  if (routes.length) {
    const r = routes[0]
    const parts = [r.strategy, r.symbol, r.timeframe].filter(Boolean)
    if (parts.length) {
      let label = parts.join(' — ')
      const dates = parseStateDates(s.state)
      if (dates.start && dates.end) {
        label += ` (${dates.start} to ${dates.end})`
      }
      return label
    }
  }
  // Fallback: extract strategy name from strategy_codes keys
  const codes = s.strategy_codes
  if (codes && typeof codes === 'object') {
    const names = Object.keys(codes)
    if (names.length) return names.join(', ')
  }
  return s.id?.slice(0, 8) || 'Untitled'
}

function formatSessionRoutes(state) {
  const routes = parseStateRoutes(state)
  if (!routes.length) return ''
  const exchange = parseStateExchange(state)
  const dates = parseStateDates(state)
  const routeStr = routes.map(r => `${exchange ? exchange + ' / ' : ''}${r.symbol || ''} ${r.timeframe || ''}`).join(', ')
  if (dates.start && dates.end) return `${routeStr} · ${dates.start} → ${dates.end}`
  return routeStr
}

function computeSessionDuration(s) {
  if (!s) return '-'
  const start = s.created_at
  const end = s.updated_at
  if (!start || !end) return '-'
  const ms = new Date(end) - new Date(start)
  if (ms < 0 || isNaN(ms)) return '-'
  if (ms < 1000) return '<1s'
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const remSecs = secs % 60
  if (mins < 60) return `${mins}m ${remSecs}s`
  const hrs = Math.floor(mins / 60)
  const remMins = mins % 60
  return `${hrs}h ${remMins}m`
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
    s.outcome = t.meta?.session_exit_reason || t.meta?.exit_reason || s.outcome
  }
  const result = Object.keys(map).sort((a, b) => a - b).map(k => {
    const s = map[k]
    // Sort trades by leg_index so L0, L1, L2... appear in order
    s.trades.sort((a, b) => (a.meta?.leg_index ?? 999) - (b.meta?.leg_index ?? 999))
    s.trade_count = s.trades.length
    s.total_pnl = parseFloat(s.total_pnl.toFixed(6))
    s.total_fee = parseFloat(s.total_fee.toFixed(6))
    return s
  })
  standalone.forEach((t, i) => {
    const exitReason = t.meta?.exit_reason || 'standalone'
    result.push({
      session: `standalone-${i + 1}`, trades: [t], total_pnl: t.pnl || t.PNL || 0,
      total_fee: t.fee || 0, opened_at: t.opened_at, closed_at: t.closed_at,
      outcome: exitReason, levels: 0, trade_count: 1,
    })
  })
  return result
}

function cleanErrorMessage(raw) {
  if (!raw) return 'Backtest failed'
  // Strip exception class prefix like "CandlesNotFound: " or "ParserMatchError: "
  let msg = raw.replace(/^\w+Error:\s*|^Candles\w+:\s*/i, '')
  // If message is a Python dict repr like "{'message': '...'}", extract the message value
  const dictMatch = msg.match(/['"]message['"]\s*:\s*['"](.+?)['"]/)
  if (dictMatch) msg = dictMatch[1]
  return msg
}

function formatKey(key) {
  return key.replace(/_/g, ' ')
}

function formatMetric(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'number') {
    if (isNaN(val)) return '-'
    if (!isFinite(val)) return val > 0 ? '\u221E' : '-\u221E'
    if (Number.isInteger(val)) return val.toLocaleString()
    if (Math.abs(val) > 0 && Math.abs(val) < 0.01) return val.toFixed(6)
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

function formatEta(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

function formatProgressDate(ts) {
  if (!ts) return ''
  const d = new Date(typeof ts === 'number' ? ts : ts)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatLiveTs(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function drawLiveMiniChart(canvasEl, data, color, label) {
  if (!canvasEl || !data.length) return
  const dpr = window.devicePixelRatio || 1
  const w = canvasEl.clientWidth
  const h = canvasEl.clientHeight
  canvasEl.width = w * dpr
  canvasEl.height = h * dpr
  const ctx = canvasEl.getContext('2d')
  ctx.scale(dpr, dpr)

  const pad = { top: 8, right: 8, bottom: 4, left: 8 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom
  const n = data.length
  const vals = data.map(d => d.value)
  const minV = Math.min(...vals)
  const maxV = Math.max(...vals)
  const range = maxV - minV || 1

  ctx.clearRect(0, 0, w, h)

  // Gradient fill
  const grad = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom)
  grad.addColorStop(0, color + '30')
  grad.addColorStop(1, color + '05')
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.moveTo(pad.left, pad.top + ph)
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - (vals[i] - minV) / range)
    ctx.lineTo(x, y)
  }
  ctx.lineTo(pad.left + pw, pad.top + ph)
  ctx.closePath()
  ctx.fill()

  // Line
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - (vals[i] - minV) / range)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()

  // Current value label
  ctx.fillStyle = color
  ctx.font = '10px monospace'
  ctx.textAlign = 'right'
  ctx.fillText(vals[n - 1].toFixed(label === 'danger' ? 3 : 2), w - pad.right, pad.top + 10)
}

const elapsedTime = computed(() => {
  if (!runStartedAt.value) return ''
  const diff = Math.floor((elapsedNow.value - runStartedAt.value) / 1000)
  if (diff < 60) return `${diff}s elapsed`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s elapsed`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m elapsed`
})

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
  if (key === 'bust_rate') return val > 0.02 ? 'text-red-400' : val > 0 ? 'text-amber-400' : 'text-green-400'
  if (key === 'geometric_growth_rate') return val >= 0 ? 'text-green-400' : 'text-red-400'
  if (key === 'survival_100' || key === 'survival_500') return val >= 0.5 ? 'text-green-400' : val >= 0.1 ? 'text-amber-400' : 'text-red-400'
  if (key === 'wins_to_recover') return val > 100 ? 'text-red-400' : val > 50 ? 'text-amber-400' : 'text-green-400'
  if (key === 'session_profit_factor') return val >= 1 ? 'text-green-400' : 'text-red-400'
  if (key === 'median_session_pnl') return val >= 0 ? 'text-green-400' : 'text-red-400'
  if (key === 'l0_win_rate') return val >= 0.5 ? 'text-green-400' : 'text-amber-400'
  if (key === 'cost_drag_pct') return val > 30 ? 'text-red-400' : val > 15 ? 'text-amber-400' : 'text-green-400'
  if (key === 'avg_bust_loss' || key === 'worst_bust_pnl') return 'text-red-400'
  if (key === 'bust_count') return val > 0 ? 'text-red-400' : 'text-green-400'
  if (key === 'survival_half_life') return val === Infinity ? 'text-green-400' : val > 200 ? 'text-green-400' : val > 50 ? 'text-amber-400' : 'text-red-400'
  return 'text-surface-100'
}

function downloadUrl(type, sid) {
  const token = localStorage.getItem('te_token') || ''
  const id = sid || sessionId.value
  return `/download/backtest/${type}/${id}?token=${token}`
}

const dangerChartData = computed(() => {
  if (!pipelineStats.value) return []
  // Aggregate danger scores from all routes
  for (const route of Object.values(pipelineStats.value)) {
    if (route.danger_scores?.length) {
      return route.danger_scores.map(d => ({ time: d[0] / 1000, value: d[1] }))
    }
  }
  return []
})

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
const lwCharts = { equity: null, pnl: null, margin: null, danger: null }
const lwSeries = { equity: null, pnl: null, margin: null, danger: null }
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

// History detail synced charts (separate instances from run charts)
const hLwCharts = { equity: null, pnl: null, margin: null }
const hLwSeries = { equity: null, pnl: null, margin: null }

function destroyHistoryCharts() {
  if (hTradeChartRef.value?.destroy) hTradeChartRef.value.destroy()
  for (const key of ['equity', 'pnl', 'margin']) {
    if (hLwCharts[key]) { hLwCharts[key].remove(); hLwCharts[key] = null; hLwSeries[key] = null }
  }
}

function renderHistoryCharts() {
  if (historyTab.value !== 'charts') return
  const { equity, floatingPnl, marginUsage } = historyEquityData.value
  const eqData = extractSeriesData(equity)
  if (!eqData.length) return

  destroyHistoryCharts()

  if (hEquityChartEl.value) {
    hLwCharts.equity = createSyncedChart(hEquityChartEl.value)
    hLwSeries.equity = hLwCharts.equity.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: eqData[0].value },
      topLineColor: '#4ade80', topFillColor1: 'rgba(74,222,128,0.15)', topFillColor2: 'rgba(74,222,128,0.02)',
      bottomLineColor: '#f87171', bottomFillColor1: 'rgba(248,113,113,0.02)', bottomFillColor2: 'rgba(248,113,113,0.15)',
      lineWidth: 2, priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    hLwSeries.equity.setData(eqData)
    hLwCharts.equity.timeScale().fitContent()
  }

  const pnlData = extractSeriesData(floatingPnl)
  if (hFloatingPnlChartEl.value && pnlData.length) {
    hLwCharts.pnl = createSyncedChart(hFloatingPnlChartEl.value)
    hLwSeries.pnl = hLwCharts.pnl.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: 0 },
      topLineColor: '#fbbf24', topFillColor1: 'rgba(251,191,36,0.15)', topFillColor2: 'rgba(251,191,36,0.02)',
      bottomLineColor: '#f87171', bottomFillColor1: 'rgba(248,113,113,0.02)', bottomFillColor2: 'rgba(248,113,113,0.15)',
      lineWidth: 2, priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    hLwSeries.pnl.setData(pnlData)
    hLwCharts.pnl.timeScale().fitContent()
  }

  const marginData = extractSeriesData(marginUsage)
  if (hMarginChartEl.value && marginData.length) {
    hLwCharts.margin = createSyncedChart(hMarginChartEl.value)
    hLwSeries.margin = hLwCharts.margin.addSeries(AreaSeries, {
      lineColor: '#fb7185', topColor: 'rgba(251,113,133,0.25)', bottomColor: 'rgba(251,113,133,0.02)',
      lineWidth: 2, priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    hLwSeries.margin.setData(marginData)
    hLwCharts.margin.timeScale().fitContent()
  }
}

function destroySyncedCharts() {
  for (const key of ['equity', 'pnl', 'margin', 'danger']) {
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
  for (const key of ['equity', 'pnl', 'margin', 'danger']) {
    if (key !== sourceKey && lwCharts[key]) {
      lwCharts[key].timeScale().setVisibleLogicalRange(range)
    }
  }
  syncingCharts = false
}

function syncCrosshair(sourceKey, param) {
  if (syncingCharts) return
  syncingCharts = true
  for (const key of ['equity', 'pnl', 'margin', 'danger']) {
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

    // Abort markers on equity curve
    if (pipelineStats.value) {
      const abortMarkers = []
      for (const ps of Object.values(pipelineStats.value)) {
        for (const ad of (ps.abort_decisions || [])) {
          if (ad.action === 'abort') {
            abortMarkers.push({
              time: ad.ts / 1000,
              position: 'aboveBar',
              color: '#f59e0b',
              shape: 'arrowDown',
              text: `Abort L${ad.level}`,
            })
          }
        }
      }
      if (abortMarkers.length) {
        lwSeries.equity.setMarkers(abortMarkers.sort((a, b) => a.time - b.time))
      }
    }

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

  // Danger score chart (pipeline)
  if (dangerChartEl.value && dangerChartData.value.length) {
    lwCharts.danger = createSyncedChart(dangerChartEl.value)
    lwSeries.danger = lwCharts.danger.addSeries(AreaSeries, {
      lineColor: '#f59e0b',
      topColor: 'rgba(245,158,11,0.25)',
      bottomColor: 'rgba(245,158,11,0.02)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 3, minMove: 0.001 },
    })
    lwSeries.danger.setData(dangerChartData.value)

    // Gate threshold overlay (dashed red line)
    if (pipelineStats.value) {
      for (const ps of Object.values(pipelineStats.value)) {
        if (ps.gate_threshold_series?.length) {
          lwSeries.dangerThreshold = lwCharts.danger.addSeries(LineSeries, {
            color: '#ef4444',
            lineWidth: 1,
            lineStyle: 2,
            priceFormat: { type: 'price', precision: 3, minMove: 0.001 },
          })
          lwSeries.dangerThreshold.setData(
            ps.gate_threshold_series.map(d => ({ time: d[0] / 1000, value: d[1] }))
          )
          break
        }
      }
      // Decision markers on danger chart
      const markers = []
      for (const ps of Object.values(pipelineStats.value)) {
        for (const gd of (ps.gate_decisions || [])) {
          if (!gd.allowed) {
            markers.push({ time: gd.ts / 1000, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'BLK' })
          }
        }
        for (const ad of (ps.abort_decisions || [])) {
          if (ad.action === 'abort') {
            markers.push({ time: ad.ts / 1000, position: 'belowBar', color: '#f59e0b', shape: 'arrowUp', text: `ABT L${ad.level}` })
          }
        }
      }
      if (markers.length) {
        lwSeries.danger.setMarkers(markers.sort((a, b) => a.time - b.time))
      }
    }

    lwCharts.danger.timeScale().fitContent()
    lwCharts.danger.timeScale().subscribeVisibleLogicalRangeChange(() => syncVisibleRange('danger'))
    lwCharts.danger.subscribeCrosshairMove((p) => syncCrosshair('danger', p))
  }
}

function fitAllCharts() {
  for (const key of ['equity', 'pnl', 'margin', 'danger']) {
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
  // Validate dates before submitting
  if (!form.value.startDate || !form.value.endDate) {
    error.value = 'Both start date and end date are required.'
    return
  }
  if (form.value.startDate >= form.value.endDate) {
    error.value = 'End date must be after start date.'
    return
  }

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
  liveLogsExpanded.value = false
  logFilter.value = 'all'
  sessionStrategyCodes.value = null
  btChartCandles.value = []
  btChartRawCandles.value = []
  btChartOrders.value = []
  pipelineStats.value = null
  livePipelineDecisions.value = []
  liveEquityHistory.value = []
  _seenDecisions.clear()
  baselineMetrics.value = null
  baselineEquityCurve.value = null
  comparisonTaskId.value = null
  comparisonRunning.value = false
  comparisonProgress.value = 0
  comparisonError.value = ''
  btChartVisible.value = false
  if (btTradeChartRef.value) btTradeChartRef.value.destroy()
  progress.value = { current: 0, eta: 0, currentDate: null, equity: null, floatingPnl: null, marginUsed: null, session: null, trades: 0 }
  runStartedAt.value = Date.now()
  running.value = true
  configCollapsed.value = true
  activeTab.value = 'summary'
  tradesPage.value = 1
  sessionsPage.value = 1
  expandedSessions.value = {}

  const id = crypto.randomUUID()
  currentTaskId.value = id
  sessionId.value = null
  taskToWorkspace.value[id] = activeWorkspaceId.value

  const label = `${form.value.routes[0]?.strategy || 'Backtest'} · ${form.value.routes[0]?.symbol || ''}`
  pm.register(id, { type: 'backtest', label, cancelFn: cancelBacktest, routePath: '/backtest' })

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

  // Save form state to DB so history can display proper session labels
  api.updateBacktestState(id, {
    exchange: form.value.exchange,
    routes: form.value.routes,
    data_routes: form.value.data_routes,
    start_date: form.value.startDate,
    finish_date: form.value.endDate,
    balance: form.value.balance,
    warmUpCandles: form.value.warmUpCandles,
  }).catch(() => {})

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
      hyperparameters: form.value.backtestMode === 'normal' ? buildBtHyperparamsPayload() : null,
      ...(form.value.backtestMode === 'pipeline' && form.value.pipelineConfigs.length ? {
        pipelines: form.value.pipelineConfigs.filter(p => p.name),
      } : {}),
    })
  } catch (e) {
    error.value = e.message
    running.value = false
  }
}

async function runBaselineComparison() {
  if (comparisonRunning.value || running.value) return
  comparisonRunning.value = true
  comparisonProgress.value = 0
  comparisonError.value = ''
  baselineMetrics.value = null
  baselineEquityCurve.value = null

  const id = crypto.randomUUID()
  comparisonTaskId.value = id

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

  // Build hyperparameters from 'original' preset — always compare against baseline config
  // Send ALL HPs: use original preset value where defined, code default for the rest
  const baselineHPs = {}
  const originalPresetValues = btPresetData.value?.['original'] || {}
  for (const hp of btHyperParams.value) {
    if (hp.name === 'preset') {
      baselineHPs['preset'] = 'original'
      continue
    }
    // Preset value takes priority, then fall back to strategy code default
    const rawVal = originalPresetValues[hp.name] !== undefined
      ? originalPresetValues[hp.name]
      : (hp.default !== undefined ? hp.default : hp.value)
    baselineHPs[hp.name] = hp.type === 'int' ? parseInt(rawVal)
      : hp.type === 'float' ? parseFloat(rawVal)
      : String(rawVal)
  }

  try {
    await api.runBacktest({
      id,
      exchange: form.value.exchange,
      routes,
      data_routes: dataRoutes,
      config: {
        warm_up_candles: form.value.warmUpCandles,
        logging: { order_submission: false, order_cancellation: false, order_execution: false, position_opened: false, position_increased: false, position_reduced: false, position_closed: false, shorter_period_candles: false, trading_candles: false, balance_update: false },
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
      debug_mode: false,
      export_chart: false,
      export_tradingview: false,
      export_csv: false,
      export_json: false,
      fast_mode: false,
      benchmark: false,
      cost_model: form.value.costModel,
      hyperparameters: Object.keys(baselineHPs).length ? baselineHPs : null,
      // No pipelines — baseline run with preset=original
    })
  } catch (e) {
    comparisonRunning.value = false
    comparisonError.value = 'Baseline comparison failed: ' + e.message
  }
}

function drawComparisonEquity() {
  const el = comparisonEquityEl.value
  if (!el) return

  // Extract [{time, value}] from backend curve format
  const pipeline = extractSeriesData(equityCurve.value)
  const baseline = extractSeriesData(baselineEquityCurve.value)
  if (!pipeline.length || !baseline.length) return

  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight
  if (!w || !h) return

  let canvas = el.querySelector('canvas')
  if (!canvas) {
    canvas = document.createElement('canvas')
    el.innerHTML = ''
    el.appendChild(canvas)
  }
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'

  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const pad = { top: 30, right: 20, bottom: 35, left: 65 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom

  const allVals = [...pipeline.map(d => d.value), ...baseline.map(d => d.value)]
  const minV = Math.min(...allVals)
  const maxV = Math.max(...allVals)
  const range = maxV - minV || 1

  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = '#1e1f2b'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ph * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }

  function drawLine(data, color, lw) {
    const n = data.length
    ctx.strokeStyle = color
    ctx.lineWidth = lw
    ctx.beginPath()
    for (let i = 0; i < n; i++) {
      const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
      const y = pad.top + ph * (1 - (data[i].value - minV) / range)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.stroke()
  }

  // Draw baseline first (dimmer)
  drawLine(baseline, '#64748b', 1.5)
  // Draw pipeline on top (brighter)
  drawLine(pipeline, '#4ade80', 2)

  // Y-axis labels
  ctx.fillStyle = '#666'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = minV + range * (1 - i / 4)
    ctx.fillText(v.toFixed(0), pad.left - 5, pad.top + ph * i / 4 + 4)
  }

  // X-axis label
  ctx.textAlign = 'center'
  ctx.fillText('Time', pad.left + pw / 2, h - 5)

  // Legend
  ctx.textAlign = 'left'
  const lx = pad.left + 10
  ctx.fillStyle = '#4ade80'
  ctx.fillRect(lx, pad.top + 5, 16, 3)
  ctx.fillStyle = '#aaa'
  ctx.fillText('With Pipeline', lx + 22, pad.top + 10)
  ctx.fillStyle = '#64748b'
  ctx.fillRect(lx, pad.top + 18, 16, 3)
  ctx.fillStyle = '#aaa'
  ctx.fillText('Without Pipeline', lx + 22, pad.top + 23)
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

function resumeRunningSession(s) {
  // If this task already has a workspace, switch to it
  const existingWs = _findWorkspaceForTask(s.id)
  if (existingWs) {
    switchWorkspace(existingWs)
    pageTab.value = 'run'
    return
  }
  // Otherwise adopt into the active workspace (if idle) or create one
  if (currentTaskId.value) {
    // Active workspace is busy — create a new one
    wsCounter++
    const wsId = `ws-${wsCounter}`
    workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
    const defaults = _freshDefaults()
    defaults.currentTaskId = s.id
    defaults.running = true
    if (s.state) {
      const st = typeof s.state === 'string' ? JSON.parse(s.state) : s.state
      const src = st.form || st
      if (src.routes?.length) defaults.form.routes = src.routes.map(r => ({ symbol: r.symbol || 'EUR-USD', timeframe: r.timeframe || '1h', strategy: r.strategy || '' }))
      if (src.exchange) defaults.form.exchange = src.exchange
      if (src.start_date || src.startDate) defaults.form.startDate = src.start_date || src.startDate
      if (src.finish_date || src.endDate) defaults.form.endDate = src.finish_date || src.endDate
    }
    const label = `${defaults.form.routes[0]?.strategy || ''} ${defaults.form.routes[0]?.symbol || ''}`.trim() || 'Backtest'
    workspaceTabs.value.push({ id: wsId, label, running: true, hasResults: false })
    workspaceCache.value[wsId] = defaults
    taskToWorkspace.value[s.id] = wsId
    activeWorkspaceId.value = wsId
    _restoreWs(defaults)
    delete workspaceCache.value[wsId]
    if (!pm.get(s.id)) pm.register(s.id, { type: 'backtest', label, cancelFn: cancelBacktest, routePath: '/backtest' })
  } else {
    currentTaskId.value = s.id
    running.value = true
    runStartedAt.value = s.created_at ? new Date(s.created_at).getTime() : Date.now()
    if (s.state) restoreFormFromState(s.state)
    taskToWorkspace.value[s.id] = activeWorkspaceId.value
    const resumeLabel = `${form.value.routes[0]?.strategy || ''} ${form.value.routes[0]?.symbol || ''}`.trim() || 'Backtest'
    _updateActiveWsTab({
      label: resumeLabel,
      running: true,
    })
    if (!pm.get(s.id)) pm.register(s.id, { type: 'backtest', label: resumeLabel, cancelFn: cancelBacktest, routePath: '/backtest' })
  }
  pageTab.value = 'run'
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

function restoreFormFromState(rawState) {
  if (!rawState) return false
  let state = rawState
  if (typeof state === 'string') {
    try { state = JSON.parse(state) } catch { return false }
  }
  const src = state.form || state
  const routes = src.routes || []
  if (routes.length) {
    form.value.routes = routes.map(r => ({
      symbol: r.symbol || 'EUR-USD',
      timeframe: r.timeframe || '1h',
      strategy: r.strategy || '',
    }))
  }
  if (src.exchange) form.value.exchange = src.exchange
  if (src.start_date || src.startDate) form.value.startDate = src.start_date || src.startDate
  if (src.finish_date || src.endDate) form.value.endDate = src.finish_date || src.endDate
  if (src.balance) form.value.balance = src.balance
  if (src.warmUpCandles != null) form.value.warmUpCandles = src.warmUpCandles
  return true
}

function loadSessionAsForm() {
  if (!selectedSession.value?.state) return
  restoreFormFromState(selectedSession.value.state)
  selectedSession.value = null
}

async function viewSessionFromHistory(s) {
  historyTab.value = 'summary'
  historyTradesPage.value = 1
  historySessionsPage.value = 1
  historyExpandedSessions.value = {}
  hChartCandles.value = []
  hChartRawCandles.value = []
  hChartOrders.value = []
  hChartVisible.value = false
  historyLogs.value = null
  historyStratCodes.value = null
  historyStratCodeKey.value = ''
  destroyHistoryCharts()
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
  // If chart_data is already cached, extract candle data for TradeChart
  const cd = selectedSession.value?.chart_data
  if (cd?.candles_chart?.length) {
    const c = cd.candles_chart[0]
    hChartCandles.value = c.candles || []
    hChartRawCandles.value = c.candles_1m || []
    hChartOrders.value = cd.orders_chart?.[0]?.orders || []
    hChartVisible.value = true
  }
}

function loadSessionAsFormFromHistory(s) {
  if (!s?.state) return
  restoreFormFromState(s.state)
  pageTab.value = 'run'
}

async function loadHistoryLogs() {
  if (!selectedSession.value?.id) return
  loadingHistoryLogs.value = true
  try {
    const res = await api.getBacktestSessionLogs(selectedSession.value.id)
    if (res.logs && Array.isArray(res.logs)) {
      historyLogs.value = formatBacktestLogs(res.logs, 'all') || 'No logs found.'
    } else if (res.logs) {
      historyLogs.value = res.logs
    } else {
      // Try file-based logs
      const fileRes = await api.getBacktestLogs(selectedSession.value.id)
      historyLogs.value = fileRes.content || 'No logs found.'
    }
  } catch {
    historyLogs.value = 'Failed to load logs.'
  } finally {
    loadingHistoryLogs.value = false
  }
}

async function loadHistoryStratCode() {
  if (!selectedSession.value?.id) return
  loadingHistoryStratCode.value = true
  try {
    const res = await api.getBacktestStrategyCode(selectedSession.value.id)
    historyStratCodes.value = res.strategy_code || res.strategy_codes || null
    const keys = Object.keys(historyStratCodes.value || {})
    historyStratCodeKey.value = keys[0] || ''
  } catch {
    historyStratCodes.value = null
  } finally {
    loadingHistoryStratCode.value = false
  }
}

function copyToClipboard(text) {
  if (!text) return
  navigator.clipboard.writeText(text)
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
      // Also update the cache so the chart persists across tab switches
      if (selectedSession.value.id) {
        tabCache.value[selectedSession.value.id] = selectedSession.value
      }
      // Extract candle data for TradeChart component
      if (res.chart_data.candles_chart?.length) {
        const cd = res.chart_data.candles_chart[0]
        hChartCandles.value = cd.candles || []
        hChartRawCandles.value = cd.candles_1m || []
        hChartOrders.value = res.chart_data.orders_chart?.[0]?.orders || []
        hChartVisible.value = true
      }
      // Render equity/pnl/margin synced charts
      if (historyTab.value === 'charts') {
        await nextTick()
        if (hTradeChartRef.value) {
          hTradeChartRef.value.renderCandles()
          hTradeChartRef.value.renderEquity()
        }
        renderHistoryCharts()
      }
    }
  } catch (e) {
    error.value = `Chart load failed: ${e.message}`
  } finally {
    loadingChart.value = false
  }
}

function renderCandleChart(el, route, routeIdx) {
  if (!el || el.dataset.rendered) return
  const candles = route.candles
  if (!candles || !candles.length) return

  const w = el.clientWidth
  const h = el.clientHeight
  if (w === 0 || h === 0) {
    // Element not laid out yet — retry after browser paint
    requestAnimationFrame(() => renderCandleChart(el, route, routeIdx))
    return
  }
  el.dataset.rendered = '1'

  // Find matching orders
  const chartData = selectedSession.value?.chart_data
  const ordersRoute = chartData?.orders_chart?.[routeIdx]
  const orders = ordersRoute?.orders || []

  const canvas = document.createElement('canvas')
  const dpr = window.devicePixelRatio || 1
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

// Live mini chart updates
watch(() => liveEquityHistory.value.length, () => {
  if (liveMiniChartEl.value && liveEquityHistory.value.length > 2) {
    drawLiveMiniChart(liveMiniChartEl.value, liveEquityHistory.value.map(d => ({ value: d.equity })), '#818cf8', 'equity')
  }
  if (liveDangerMiniEl.value && progress.value.pipelineDangerHistory?.length) {
    drawLiveMiniChart(liveDangerMiniEl.value, progress.value.pipelineDangerHistory.map(d => ({ value: d[1] })), '#f59e0b', 'danger')
  }
})

// Draw comparison equity when element mounts or baseline data arrives
watch([comparisonEquityEl, baselineEquityCurve], () => {
  nextTick(() => setTimeout(drawComparisonEquity, 50))
})

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
  if (tab === 'pipeline' && baselineEquityCurve.value) {
    await nextTick()
    setTimeout(drawComparisonEquity, 50)
  }
})

watch(historyTab, async (tab) => {
  if (tab === 'charts' && selectedSession.value) {
    await nextTick()
    if (hChartVisible.value && hTradeChartRef.value) {
      hTradeChartRef.value.renderCandles()
      hTradeChartRef.value.renderEquity()
    }
    renderHistoryCharts()
  }
})

onBeforeUnmount(() => {
  destroySyncedCharts()
  destroyHistoryCharts()
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
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
    if (strategies.value.length > 0) form.value.routes[0].strategy = strategies.value[0].name
  } catch (e) {
    console.error(e)
  }

  await loadExistingCandles()
  onExchangeChange()
  await loadSessions()

  // Load available pipelines (non-blocking — ok if endpoint not available)
  api.getRegisteredPipelines().then(pRes => {
    availablePipelines.value = Array.isArray(pRes) ? pRes : (pRes.data || [])
  }).catch(() => {})

  // Auto-detect running backtests and resume progress display
  const activeSessions = sessions.value.filter(s => s.is_active)
  if (activeSessions.length > 0) {
    // First running session goes to the current workspace
    const first = activeSessions[0]
    currentTaskId.value = first.id
    running.value = true
    runStartedAt.value = first.created_at ? new Date(first.created_at).getTime() : Date.now()
    pageTab.value = 'run'
    if (first.state) restoreFormFromState(first.state)
    const label1 = `${form.value.routes[0]?.strategy || ''} ${form.value.routes[0]?.symbol || ''}`.trim() || 'Backtest'
    _updateActiveWsTab({ label: label1, running: true })
    taskToWorkspace.value[first.id] = activeWorkspaceId.value
    if (!pm.get(first.id)) pm.register(first.id, { type: 'backtest', label: label1, cancelFn: cancelBacktest, routePath: '/backtest' })

    // Additional running sessions get their own workspaces
    for (let i = 1; i < activeSessions.length; i++) {
      const s = activeSessions[i]
      wsCounter++
      const wsId = `ws-${wsCounter}`
      const defaults = _freshDefaults()
      defaults.currentTaskId = s.id
      defaults.running = true
      defaults.runStartedAt = s.created_at ? new Date(s.created_at).getTime() : Date.now()
      // Populate form from state
      if (s.state) {
        const st = typeof s.state === 'string' ? JSON.parse(s.state) : s.state
        const src = st.form || st
        if (src.routes?.length) {
          defaults.form.routes = src.routes.map(r => ({ symbol: r.symbol || 'EUR-USD', timeframe: r.timeframe || '1h', strategy: r.strategy || '' }))
        }
        if (src.exchange) defaults.form.exchange = src.exchange
        if (src.start_date || src.startDate) defaults.form.startDate = src.start_date || src.startDate
        if (src.finish_date || src.endDate) defaults.form.endDate = src.finish_date || src.endDate
      }
      const label = `${defaults.form.routes[0]?.strategy || ''} ${defaults.form.routes[0]?.symbol || ''}`.trim() || `Backtest ${wsCounter}`
      workspaceTabs.value.push({ id: wsId, label, running: true, hasResults: false })
      workspaceCache.value[wsId] = defaults
      taskToWorkspace.value[s.id] = wsId
      if (!pm.get(s.id)) pm.register(s.id, { type: 'backtest', label, cancelFn: cancelBacktest, routePath: '/backtest' })
    }
  }

  // Load hyperparameters for the initial strategy
  if (form.value.routes[0]?.strategy) {
    loadBacktestHyperparams(form.value.routes[0].strategy)
  }

  try {
    const llmRes = await api.llmStatus()
    llmConfigured.value = llmRes.configured
  } catch { /* ignore */ }

  // Handle ?hp=<json> query param (from Autopilot "Load into Backtest")
  const qHp = currentRoute.query.hp
  if (qHp) {
    try {
      const hpValues = JSON.parse(qHp)
      // Wait for btHyperParams to be loaded, then override values
      const applyHp = () => {
        if (btHyperParams.value.length) {
          for (const [key, val] of Object.entries(hpValues)) {
            const hp = btHyperParams.value.find(h => h.name === key)
            if (hp) hp.value = val
          }
        }
      }
      // Try immediately, and also watch for delayed load
      applyHp()
      const stopWatch = watch(btHyperParams, () => { applyHp(); stopWatch() }, { deep: true })
      setTimeout(() => stopWatch(), 5000) // cleanup after 5s
    } catch { /* ignore invalid JSON */ }
  }

  // Handle ?session=<id> query param (from process manager "view results")
  const qSession = currentRoute.query.session
  if (qSession && !running.value) {
    pageTab.value = 'history'
    await loadSessions()
    const s = sessions.value.find(x => x.id === qSession)
    if (s) viewSession(s)
  }
})
</script>
