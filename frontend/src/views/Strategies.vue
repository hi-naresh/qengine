<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Strategies</h1>
        <p class="text-xs text-surface-500 mt-0.5">Create, edit, and test trading strategies -- use AI Generate or write Python directly</p>
      </div>
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
          <button @click="closeStrategyWorkspace" title="Open another strategy"
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
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
    <div v-else-if="!playgroundActive && !editingStrat && !showGuide" class="space-y-3">
      <div class="flex items-center justify-between">
        <p v-if="openEditorTabs.length" class="text-xs text-surface-500">Select a strategy to open in a new tab:</p>
        <p v-else class="text-xs text-surface-500">{{ filteredStrategies.length }} strateg{{ filteredStrategies.length === 1 ? 'y' : 'ies' }} available</p>
        <button @click="showGuide = true" class="text-xs text-brand-400 hover:text-brand-300 flex items-center gap-1">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" /></svg>
          Strategy Guide
        </button>
      </div>

      <!-- Admin: owner tabs -->
      <div v-if="showAdminTabs && strategyOwnerTabs.length > 1" class="flex gap-1.5 flex-wrap">
        <button v-for="tab in strategyOwnerTabs" :key="tab.id" @click="strategyTab = tab.id"
          class="px-3 py-1.5 rounded-lg text-xs transition-colors"
          :class="strategyTab === tab.id ? 'bg-brand-600/20 text-brand-400 font-medium' : 'bg-surface-800/60 text-surface-500 hover:text-surface-300'">
          {{ tab.label }} <span class="text-[10px] ml-0.5 opacity-60">{{ tab.count }}</span>
        </button>
      </div>

      <div v-for="strat in filteredStrategies" :key="strat.name"
        class="card hover:border-surface-600 transition-colors cursor-pointer"
        @click="selectStrategy(strat.name)">
        <div class="flex items-start justify-between gap-4">
          <div class="flex items-start gap-3 min-w-0">
            <div class="w-9 h-9 rounded-lg flex-shrink-0 flex items-center justify-center text-xs font-mono font-bold"
              :class="getStratMeta(strat.name).iconClass || 'bg-surface-800 text-brand-400'">{{ strat.name.slice(0, 2) }}</div>
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-sm font-medium text-surface-100">{{ strat.name }}</span>
                <span v-if="strat.owner === 'shared'" class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-400">shared</span>
                <span v-else-if="strat.owner === 'admin'" class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-400">admin</span>
                <span v-else-if="strat.owner_username" class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-500/15 text-indigo-400">{{ strat.owner_username }}</span>
                <span v-for="label in getStratMeta(strat.name).labels" :key="label.text"
                  class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  :class="label.class">{{ label.text }}</span>
              </div>
              <p class="text-xs text-surface-500 mt-1 line-clamp-2">{{ getStratMeta(strat.name).description }}</p>
              <div v-if="getStratMeta(strat.name).params.length" class="flex flex-wrap gap-1.5 mt-2">
                <span v-for="p in getStratMeta(strat.name).params.slice(0, 6)" :key="p"
                  class="px-1.5 py-0.5 bg-surface-800/80 rounded text-[10px] text-surface-500 font-mono">{{ p }}</span>
                <span v-if="getStratMeta(strat.name).params.length > 6" class="text-[10px] text-surface-600">+{{ getStratMeta(strat.name).params.length - 6 }} more</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-1.5 flex-shrink-0 pt-1">
            <button @click.stop="openPlayground(strat.name)" class="px-2.5 py-1.5 rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors flex items-center gap-1.5 text-xs font-medium" title="Playground">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-1.47 4.41a2.25 2.25 0 01-2.133 1.59H8.603a2.25 2.25 0 01-2.133-1.59L5 14.5m14 0H5" /></svg>
              Playground
            </button>
            <button @click.stop="editStrategy(strat.name)" class="w-7 h-7 rounded-md bg-surface-800 text-surface-400 hover:text-brand-400 hover:bg-surface-700 transition-colors flex items-center justify-center" title="Edit">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
            </button>
            <button @click.stop="confirmDelete(strat.name)" class="w-7 h-7 rounded-md bg-surface-800 text-surface-400 hover:text-red-400 hover:bg-red-500/10 transition-colors flex items-center justify-center" title="Delete">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
            </button>
          </div>
        </div>
      </div>

      <!-- High-level process -->
      <div class="mt-6 card bg-surface-800/30 border-surface-700/50">
        <h3 class="text-xs font-semibold text-surface-400 mb-3">How It Works</h3>
        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div class="flex items-start gap-2.5">
            <span class="w-5 h-5 rounded-full bg-brand-600/20 text-brand-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">1</span>
            <div>
              <p class="text-xs font-medium text-surface-300">Create</p>
              <p class="text-[11px] text-surface-500">Write a strategy class or use AI Generate. Define entry/exit logic and hyperparameters.</p>
            </div>
          </div>
          <div class="flex items-start gap-2.5">
            <span class="w-5 h-5 rounded-full bg-brand-600/20 text-brand-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">2</span>
            <div>
              <p class="text-xs font-medium text-surface-300">Test</p>
              <p class="text-[11px] text-surface-500">Use Playground with synthetic data or run a full Backtest against historical candles.</p>
            </div>
          </div>
          <div class="flex items-start gap-2.5">
            <span class="w-5 h-5 rounded-full bg-brand-600/20 text-brand-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">3</span>
            <div>
              <p class="text-xs font-medium text-surface-300">Optimize</p>
              <p class="text-[11px] text-surface-500">Tune hyperparameters via the optimizer. Analyze Sharpe, drawdown, and win rate.</p>
            </div>
          </div>
          <div class="flex items-start gap-2.5">
            <span class="w-5 h-5 rounded-full bg-brand-600/20 text-brand-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">4</span>
            <div>
              <p class="text-xs font-medium text-surface-300">Deploy</p>
              <p class="text-[11px] text-surface-500">Paper trade first, then go live. Monitor via the Live Trade dashboard.</p>
            </div>
          </div>
        </div>
        <div class="mt-3 flex items-center gap-2 pt-2 border-t border-surface-700/50">
          <button @click="showGuide = true" class="text-[11px] text-brand-400 hover:text-brand-300 flex items-center gap-1">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" /></svg>
            Read the full Strategy Guide
          </button>
          <span class="text-[10px] text-surface-600">for methods, properties, indicators, and examples</span>
        </div>
      </div>
    </div>

    <!-- ═══════════════ STRATEGY GUIDE ═══════════════ -->
    <div v-if="showGuide && !playgroundActive && !editingStrat">
      <StrategyGuide :strategies="strategies" :get-strat-meta="getStratMeta" @close="showGuide = false" />
    </div>

    <!-- ═══════════════ STRATEGY WORKSPACE (Playground + Code) ═══════════════ -->
    <div v-if="playgroundActive" class="space-y-4">
      <div class="flex items-center gap-3">
        <button @click="closeStrategyWorkspace" class="btn-sm bg-surface-800 text-surface-400 hover:text-surface-200">
          <svg class="w-4 h-4 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"/></svg>
          Back
        </button>
        <h2 class="text-lg font-semibold text-surface-100">{{ playgroundStrategy }}</h2>
        <div class="flex items-center gap-1 p-0.5 bg-surface-800 rounded-lg ml-auto">
          <button @click="strategyViewTab = 'playground'"
            class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
            :class="strategyViewTab === 'playground' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            Playground
          </button>
          <button @click="strategyViewTab = 'code'"
            class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
            :class="strategyViewTab === 'code' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            Code
          </button>
        </div>
      </div>

      <!-- Sub-tab: Playground -->
      <div v-show="strategyViewTab === 'playground'">
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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

      <!-- Sub-tab: Code -->
      <div v-show="strategyViewTab === 'code'" class="space-y-3">
        <div class="card flex flex-col" style="min-height: 70vh;">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
              <span v-if="editingStrat" class="text-xs text-surface-500">{{ editingStrat }}</span>
            </div>
            <div class="flex items-center gap-2">
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
          <CodeEditor v-model="editCode" :editable="true" min-height="500px" class="flex-1" />
          <p v-if="editMsg" class="text-xs mt-2" :class="editErr ? 'text-red-400' : 'text-green-400'">{{ editMsg }}</p>
        </div>
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
import { useRoute } from 'vue-router'
import { api, isAdmin, isImpersonating } from '../api'
import { useWebSocket } from '../useWebSocket'
import ProgressBar from '../components/ProgressBar.vue'
import TradeChart from '../components/TradeChart.vue'
import StrategyGuide from '../components/StrategyGuide.vue'
import CodeEditor from '../components/CodeEditor.vue'

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
const showGuide = ref(false)

// Admin strategy tabs
const showAdminTabs = computed(() => isAdmin() && !isImpersonating())
const strategyTab = ref('all')
const strategyOwnerTabs = computed(() => {
  if (!showAdminTabs.value) return []
  const tabs = [{ id: 'all', label: 'All', count: strategies.value.length }]
  const shared = strategies.value.filter(s => s.owner === 'shared')
  if (shared.length) tabs.push({ id: 'shared', label: 'Shared', count: shared.length })
  const admin = strategies.value.filter(s => s.owner === 'admin')
  if (admin.length) tabs.push({ id: 'admin', label: 'Admin', count: admin.length })
  // Group by user
  const userMap = {}
  for (const s of strategies.value) {
    if (s.owner && s.owner !== 'shared' && s.owner !== 'admin') {
      const label = s.owner_username || s.owner.slice(0, 8)
      if (!userMap[label]) userMap[label] = { id: s.owner, label, count: 0 }
      userMap[label].count++
    }
  }
  for (const u of Object.values(userMap).sort((a, b) => a.label.localeCompare(b.label))) {
    tabs.push(u)
  }
  return tabs
})
const filteredStrategies = computed(() => {
  if (!showAdminTabs.value || strategyTab.value === 'all') return strategies.value
  if (strategyTab.value === 'shared') return strategies.value.filter(s => s.owner === 'shared')
  if (strategyTab.value === 'admin') return strategies.value.filter(s => s.owner === 'admin')
  return strategies.value.filter(s => s.owner === strategyTab.value)
})

// Editor tabs
const openEditorTabs = ref([])
const editorTabCache = ref({})

// ── Strategy workspace (sub-tabbed: playground + code) ──
const strategyViewTab = ref('playground') // 'playground' or 'code'
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

// ── Strategy metadata for descriptions & labels ──
const strategyMeta = {
  Surefire: {
    description: 'Recovery/martingale hedging strategy for CFD trading using broker-side orders (OANDA).',
    longDescription: 'Opens an initial ticket in a configurable direction with TP and hedge trigger. When price moves against, opens opposite-direction ticket with larger size. Continues adding hedged tickets until TP hit or max_levels reached. Uses broker orders for sub-second execution.',
    labels: [
      { text: 'CFD', class: 'bg-blue-500/20 text-blue-400' },
      { text: 'Hedging', class: 'bg-amber-500/20 text-amber-400' },
      { text: 'Live Ready', class: 'bg-green-500/20 text-green-400' },
    ],
    iconClass: 'bg-amber-900/50 text-amber-400',
    params: ['direction', 'initial_size', 'sizing_operator', 'sizing_factor', 'tp_distance', 'hedge_distance', 'max_levels'],
  },
  SurefireV2: {
    description: 'Enhanced hedging with indicator-based entries, bucket PnL exits, and circuit breakers.',
    longDescription: 'Indicator-driven entry signals (EMA, RSI, MACD, Supertrend, or combinations) with ATR-based hedge distances. Session closes when floating PnL reaches bucket_threshold. Circuit breakers for daily loss limits and consecutive bust protection. Supports London/NY/overlap session filtering.',
    labels: [
      { text: 'CFD', class: 'bg-blue-500/20 text-blue-400' },
      { text: 'Hedging', class: 'bg-amber-500/20 text-amber-400' },
      { text: 'Multi-Indicator', class: 'bg-purple-500/20 text-purple-400' },
    ],
    iconClass: 'bg-purple-900/50 text-purple-400',
    params: ['initial_size', 'sizing_operator', 'sizing_factor', 'max_levels', 'bucket_pct', 'signal_mode', 'atr_period', 'hedge_atr_mult', 'session_filter', 'cooldown_bars', 'max_daily_loss_pct', 'max_consec_busts', 'ema_fast', 'ema_slow', 'rsi_period', 'rsi_ob', 'rsi_os'],
  },
  ForexMA: {
    description: 'Simple SMA crossover strategy with session filtering and pip-based risk management.',
    longDescription: 'Educational example demonstrating forex-specific features. Enters long when fast SMA > slow SMA during London/NY/overlap sessions. Uses lot_size_for_risk() for pip-based position sizing and pips_to_price() for stop/TP calculation. Cancels entries before weekend close.',
    labels: [
      { text: 'Forex', class: 'bg-blue-500/20 text-blue-400' },
      { text: 'Trend', class: 'bg-emerald-500/20 text-emerald-400' },
      { text: 'Example', class: 'bg-surface-600/50 text-surface-400' },
    ],
    iconClass: 'bg-blue-900/50 text-blue-400',
    params: ['fast_period', 'slow_period', 'risk_pct', 'stop_pips', 'rr_ratio'],
  },
  ForexRSIReversal: {
    description: 'RSI mean-reversion strategy for GBP-JPY with session filtering and fixed risk/reward.',
    longDescription: 'Buys when RSI drops below oversold threshold during active sessions, sells when RSI exceeds overbought. Uses 2:1 risk-reward ratio with pip-based position sizing. Designed for volatile pairs like GBP-JPY where mean reversion signals work well.',
    labels: [
      { text: 'Forex', class: 'bg-blue-500/20 text-blue-400' },
      { text: 'Mean Reversion', class: 'bg-cyan-500/20 text-cyan-400' },
      { text: 'Example', class: 'bg-surface-600/50 text-surface-400' },
    ],
    iconClass: 'bg-cyan-900/50 text-cyan-400',
    params: ['rsi_period', 'oversold', 'overbought', 'risk_pct', 'stop_pips'],
  },
  GoldBreakout: {
    description: 'Donchian channel breakout strategy for XAU-USD with ATR-based volatility stops.',
    longDescription: 'Enters when price breaks above/below the Donchian channel (highest/lowest price over N periods). Uses ATR-multiplied stop-loss distances suitable for the wider volatility of commodities like gold. Position sized by risk percentage relative to stop distance.',
    labels: [
      { text: 'Commodity', class: 'bg-yellow-500/20 text-yellow-400' },
      { text: 'Breakout', class: 'bg-orange-500/20 text-orange-400' },
      { text: 'Example', class: 'bg-surface-600/50 text-surface-400' },
    ],
    iconClass: 'bg-yellow-900/50 text-yellow-400',
    params: ['channel_period', 'atr_period', 'atr_multiplier', 'risk_pct'],
  },
}
const defaultStratMeta = {
  description: 'Custom strategy',
  longDescription: 'Custom strategy - edit to view implementation details.',
  labels: [],
  iconClass: 'bg-surface-800 text-brand-400',
  params: [],
}
function getStratMeta(name) {
  return strategyMeta[name] || defaultStratMeta
}


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
async function editStrategy(name, silent = false) {
  editMsg.value = ''; editErr.value = false
  if (!silent) {
    strategyViewTab.value = 'code'
    // Activate workspace if not already in it
    if (!playgroundActive.value) {
      playgroundStrategy.value = name
      playgroundActive.value = true
      // Load scenarios + hyperparams in background for quick playground switching
      if (!scenarios.value.length) api.getPlaygroundScenarios().then(r => { scenarios.value = r.scenarios || [] }).catch(() => {})
      loadStrategyHyperparams(name)
    }
  }
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
      editStrategy(last.name, true)
    } else {
      editingStrat.value = null; editCode.value = ''
      // Switch to playground if workspace is open, else it stays cleared
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
  strategyViewTab.value = 'playground'
  pgError.value = ''; pgErrorTrace.value = ''; pgSuccessMsg.value = ''
  pgMetrics.value = null; pgEquityCurve.value = []; pgTrades.value = []; pgSessions.value = []; pgExpandedSessions.value = {}
  pgChartData.value = null; pgResultHyperparams.value = null
  pgCustomHPs.value = []
  destroyCharts()

  // Load scenarios + hyperparameters in parallel, also preload code for code tab
  const promises = []
  if (!scenarios.value.length) promises.push(api.getPlaygroundScenarios().then(r => { scenarios.value = r.scenarios || [] }).catch(() => {}))
  promises.push(loadStrategyHyperparams(name))
  if (!editingStrat.value || editingStrat.value !== name) {
    promises.push(editStrategy(name, true))
  }
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

function closeStrategyWorkspace() {
  if (pgRunning.value) cancelSim()
  playgroundActive.value = false
  playgroundStrategy.value = ''
  editingStrat.value = null
  editCode.value = ''
  destroyCharts()
}

// Keep old name as alias for any remaining references
const closePlayground = closeStrategyWorkspace

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
const route = useRoute()

onMounted(async () => {
  await loadStrategies()
  try { const res = await api.llmStatus(); llmConfigured.value = res.configured } catch {}
  // Auto-open strategy from ?edit=Name query param
  if (route.query.edit) {
    const name = route.query.edit
    const exists = strategies.value.find(s => s.name === name)
    if (exists) editStrategy(name)
  }
})
</script>
