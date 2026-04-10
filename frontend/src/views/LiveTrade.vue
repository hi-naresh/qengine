<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Live Trading</h1>
        <p class="text-xs text-surface-500 mt-0.5">Run strategies live or in paper mode -- monitor positions, orders, and session performance</p>
      </div>
      <button @click="openStartModal" class="btn-primary btn-sm">New Session</button>
    </div>

    <!-- ════════════ Start Session Modal ════════════ -->
    <div v-if="showStart" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="showStart = false">
      <div class="card w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold">Start Trading Session</h2>
          <p class="text-[11px] text-surface-500 mt-0.5">Choose a broker, strategy, and mode to begin live or paper trading</p>
          <button @click="showStart = false" class="text-surface-500 hover:text-surface-200 text-xl">&times;</button>
        </div>
        <div class="space-y-3">
          <div>
            <label class="label">Broker Account</label>
            <select v-model="form.exchange" class="select" :disabled="brokers.length === 0">
              <option v-if="brokers.length === 0" value="" disabled>No connected brokers</option>
              <option v-for="b in brokers" :key="b.id" :value="b.id">{{ b.name }}{{ b.is_demo ? ' (Demo)' : ' (Live)' }}</option>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="label">Symbol</label>
              <select v-model="form.symbol" class="select">
                <option v-for="inst in instruments" :key="inst.symbol" :value="inst.symbol">{{ inst.symbol }} ({{ inst.asset_class }})</option>
              </select>
            </div>
            <div>
              <label class="label">Strategy</label>
              <div class="flex items-center gap-1">
                <select v-if="strategies.length" v-model="form.strategy" class="select flex-1">
                  <option v-for="s in strategies" :key="s.name" :value="s.name">{{ s.name }}</option>
                </select>
                <input v-else v-model="form.strategy" class="input flex-1" placeholder="ForexMA" />
                <router-link v-if="form.strategy" :to="'/strategies?edit=' + encodeURIComponent(form.strategy)" class="p-1.5 text-surface-400 hover:text-indigo-400 transition-colors" title="Edit strategy">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                </router-link>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
              <input v-model="form.debug_mode" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
              Debug Mode
            </label>
          </div>
          <!-- Pipeline selector -->
          <div v-if="availablePipelines.length" class="pt-1">
            <div class="flex items-center justify-between mb-1">
              <h3 class="text-xs font-semibold text-surface-400">Pipeline</h3>
              <label class="flex items-center gap-1.5 text-[10px] text-surface-500 cursor-pointer">
                <input v-model="pipelineEnabled" type="checkbox" class="rounded bg-surface-700 border-surface-500 w-3 h-3" />
                Enable
              </label>
            </div>
            <div v-if="pipelineEnabled" class="space-y-1.5">
              <div v-for="(pc, idx) in livePipelineConfigs" :key="idx" class="flex items-center gap-2">
                <select v-model="pc.name" class="select text-xs py-1.5 flex-1">
                  <option value="">Select pipeline...</option>
                  <option v-for="p in availablePipelines" :key="p.name" :value="p.name">{{ p.name }}</option>
                </select>
                <button v-if="livePipelineConfigs.length > 1" @click="livePipelineConfigs.splice(idx, 1)" class="text-surface-500 hover:text-red-400 text-sm">&times;</button>
              </div>
              <button @click="livePipelineConfigs.push({ name: '' })" class="text-[10px] text-brand-400 hover:text-brand-300">+ Add Pipeline</button>
            </div>
          </div>
          <!-- Hyperparameters (auto-loaded from strategy, collapsible) -->
          <div v-if="liveHyperParams.length" class="pt-1">
            <div class="flex items-center justify-between mb-2">
              <button @click="hpExpanded = !hpExpanded" class="flex items-center gap-1.5 text-xs font-semibold text-surface-400 hover:text-surface-300">
                <svg class="w-3 h-3 transition-transform" :class="hpExpanded ? 'rotate-90' : ''" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
                Hyperparameters <span class="text-surface-600 font-normal">({{ liveHyperParams.length }})</span>
              </button>
              <button v-if="hpExpanded" @click="resetLiveHyperParams" class="text-xs text-surface-500 hover:text-surface-300">Reset Defaults</button>
            </div>
            <div v-show="hpExpanded" class="max-h-60 overflow-y-auto space-y-2 pr-1">
              <div v-for="(hp, idx) in liveHyperParams" :key="idx" v-show="isLiveHpVisible(hp)">
                <div class="flex gap-2 items-center">
                  <span class="text-xs text-surface-400 w-28 truncate" :title="hp.name">{{ hp.name }}</span>
                  <select v-if="hp.options" v-model="hp.value" class="select text-xs py-1.5 flex-1">
                    <option v-for="opt in hp.options" :key="opt" :value="opt">{{ opt }}</option>
                  </select>
                  <input v-else-if="hp.type === 'str'" v-model="hp.value" class="input text-xs py-1.5 flex-1" />
                  <input v-else v-model.number="hp.value" type="number" :step="hp.type === 'int' ? 1 : 'any'"
                    :min="hp.min" :max="hp.max" class="input text-xs py-1.5 flex-1" />
                  <span v-if="hp.min !== undefined" class="text-[10px] text-surface-600 whitespace-nowrap">{{ hp.min }}-{{ hp.max }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="brokers.length === 0" class="p-3 bg-red-500/10 rounded-lg text-red-400 text-xs">
            No brokers connected. <a href="#/brokers" class="underline text-red-300">Connect a broker</a> first.
          </div>
          <div v-else-if="selectedBrokerIsDemo" class="p-3 bg-blue-500/10 rounded-lg text-blue-400 text-xs">
            Demo account — orders are simulated using real-time prices from your broker's practice environment.
          </div>
          <div v-else class="p-3 bg-yellow-500/10 rounded-lg text-yellow-400 text-xs">
            Live account — real orders will be submitted to your broker. Use with caution.
          </div>
          <button @click="startSession" class="btn-primary w-full" :disabled="starting || brokers.length === 0">
            {{ starting ? 'Starting...' : (selectedBrokerIsDemo ? 'Start Demo Trading' : 'Start Live Trading') }}
          </button>
          <p v-if="startError" class="text-xs text-red-400">{{ startError }}</p>
        </div>
      </div>
    </div>

    <!-- ════════════ Active Session Dashboard ════════════ -->
    <div v-if="activeView" class="space-y-4">
      <!-- Session Tabs Bar -->
      <div v-if="openTabs.length > 1" class="flex items-center gap-1 overflow-x-auto pb-1 -mb-2">
        <div v-for="tab in openTabs" :key="tab.id"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs cursor-pointer whitespace-nowrap group border border-b-0 transition-colors"
          :class="tab.id === activeView ? 'bg-surface-800 text-surface-100 border-surface-600' : 'bg-surface-900 text-surface-500 border-surface-800 hover:text-surface-300'"
          @click="switchToTab(tab.id)">
          <span class="w-1.5 h-1.5 rounded-full" :class="tab.status === 'running' ? 'bg-green-400' : 'bg-surface-500'"></span>
          <span>{{ tab.label }}</span>
          <button @click.stop="closeTab(tab.id)" class="ml-1 text-surface-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">&times;</button>
        </div>
      </div>
      <button @click="closeTab(activeView)" class="text-surface-400 hover:text-surface-200 text-sm">&larr; All Sessions</button>

      <!-- Header -->
      <div class="card py-3">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div class="flex items-center gap-3 flex-wrap">
            <span class="w-2.5 h-2.5 rounded-full" :class="activeMeta.status === 'running' ? 'bg-green-400 animate-pulse' : activeMeta.status === 'stopping' ? 'bg-yellow-400 animate-pulse' : activeMeta.status === 'error' ? 'bg-red-400' : 'bg-surface-500'"></span>
            <span class="text-sm font-semibold uppercase" :class="activeMeta.status === 'running' ? 'text-green-400' : activeMeta.status === 'stopping' ? 'text-yellow-400' : activeMeta.status === 'error' ? 'text-red-400' : 'text-surface-400'">{{ activeMeta.status }}</span>
            <span class="badge" :class="activeMeta.mode === 'livetrade' ? 'badge-yellow' : 'badge-blue'">
              {{ activeMeta.mode === 'livetrade' ? 'LIVE' : 'DEMO' }}
            </span>
            <span class="text-xs text-surface-400">{{ activeMeta.exchange }}</span>
            <span v-if="acct.account_id" class="text-xs text-surface-500 font-mono">{{ acct.account_id }}</span>
            <span v-if="acct.currency" class="text-[10px] badge-gray">{{ acct.currency }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span v-if="acct.session_duration" class="text-xs text-surface-500">{{ formatDuration(acct.session_duration) }}</span>
            <button v-if="activeMeta.status === 'running'" @click="stopSession(activeMeta.id)"
              class="btn-sm bg-red-500/20 text-red-400 hover:bg-red-500/30">Stop</button>
            <span v-else-if="activeMeta.status === 'stopping'" class="text-xs text-yellow-400">Shutting down...</span>
          </div>
        </div>
      </div>

      <!-- Account Overview - OANDA style -->
      <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
        <div class="card py-3 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Balance</div>
          <div class="text-lg font-bold text-surface-100 font-mono">{{ fmtCcy(acct.balance) }}</div>
        </div>
        <div class="card py-3 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">NAV</div>
          <div class="text-lg font-bold font-mono" :class="cmpColor(acct.nav, acct.balance)">{{ fmtCcy(acct.nav) }}</div>
        </div>
        <div class="card py-3 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Unrealized P&L</div>
          <div class="text-lg font-bold font-mono" :class="plColor(acct.unrealized_pnl)">{{ fmtPl(acct.unrealized_pnl) }}</div>
        </div>
        <div class="card py-3 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Realized P&L</div>
          <div class="text-lg font-bold font-mono" :class="plColor(acct.realized_pnl)">{{ fmtPl(acct.realized_pnl) }}</div>
        </div>
        <div class="card py-3 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Position Value</div>
          <div class="text-lg font-bold text-surface-100 font-mono">{{ fmtCcy(acct.position_value) }}</div>
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
        <div class="card py-2.5 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-0.5">Margin Used</div>
          <div class="text-sm font-semibold text-surface-200 font-mono">{{ fmtCcy(acct.margin_used) }}</div>
          <div v-if="marginPct !== null" class="text-[10px] mt-0.5" :class="marginPct < 50 ? 'text-green-400' : marginPct < 80 ? 'text-yellow-400' : 'text-red-400'">{{ marginPct.toFixed(1) }}%</div>
        </div>
        <div class="card py-2.5 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-0.5">Margin Available</div>
          <div class="text-sm font-semibold text-surface-200 font-mono">{{ fmtCcy(acct.available_margin) }}</div>
        </div>
        <div class="card py-2.5 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-0.5">Leverage</div>
          <div class="text-sm font-semibold text-surface-200">{{ acct.leverage || '-' }}:1</div>
        </div>
        <div class="card py-2.5 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-0.5">Trades</div>
          <div class="text-sm font-semibold text-surface-200">
            {{ acct.total_trades || 0 }}
            <span v-if="acct.winning_trades || acct.losing_trades" class="text-[10px] text-surface-400">
              (W:{{ acct.winning_trades || 0 }} / L:{{ acct.losing_trades || 0 }})
            </span>
          </div>
        </div>
        <div class="card py-2.5 text-center">
          <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-0.5">Open Trades</div>
          <div class="text-sm font-semibold text-surface-200">{{ acct.open_trade_count || liveState.open_positions_count || 0 }}</div>
        </div>
      </div>

      <!-- Strategy Cards -->
      <div v-if="liveState.strategies?.length" class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div v-for="strat in liveState.strategies" :key="strat.symbol" class="card py-3">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <span class="text-sm font-semibold text-brand-400">{{ strat.name }}</span>
              <span class="text-xs text-surface-500">{{ strat.symbol }} {{ strat.timeframe }}</span>
            </div>
            <span v-if="strat.has_position" class="badge text-[10px]"
              :class="strat.position_type === 'long' ? 'badge-green' : 'badge-red'">
              {{ strat.position_type?.toUpperCase() }} {{ strat.position_qty }}
            </span>
            <span v-else class="text-[10px] text-surface-500">FLAT</span>
          </div>
          <div v-if="strat.has_position" class="flex gap-4 text-xs">
            <span class="text-surface-500">P&L: <span class="font-mono" :class="plColor(strat.position_pnl)">{{ fmtPl(strat.position_pnl) }}</span></span>
          </div>
          <div v-if="strat.hyperparameters && Object.keys(strat.hyperparameters).length" class="mt-2 pt-2 border-t border-surface-700">
            <div class="flex flex-wrap gap-x-3 gap-y-1">
              <span v-for="(val, key) in strat.hyperparameters" :key="key" class="text-[10px] text-surface-500">
                <span class="text-surface-600">{{ key }}:</span> <span class="font-mono text-surface-400">{{ val }}</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Detail Tabs -->
      <div class="flex gap-1 p-1 bg-surface-800 rounded-lg w-full sm:w-fit overflow-x-auto">
        <button v-for="tab in availableTabs" :key="tab" @click="detailTab = tab"
          class="px-3 py-1.5 text-xs rounded-md font-medium transition-colors whitespace-nowrap"
          :class="detailTab === tab ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
          {{ tab }}
          <span v-if="tab === 'Orders' && liveState.orders_summary" class="ml-1 text-[10px] text-surface-500">({{ liveState.orders_summary.total }})</span>
          <span v-if="tab === 'Closed Trades' && liveClosedTrades.length" class="ml-1 text-[10px] text-surface-500">({{ liveClosedTrades.length }})</span>
          <span v-if="tab === 'Report' && report.total_trades" class="ml-1 text-[10px] text-surface-500">({{ report.total_trades }})</span>
        </button>
      </div>

      <!-- Positions Tab -->
      <div v-if="detailTab === 'Positions'" class="card">
        <div v-if="openPositions.length === 0" class="text-center py-8 text-surface-500 text-sm">No open positions</div>
        <div v-else class="overflow-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-surface-500 text-[11px] uppercase tracking-wider border-b border-surface-700">
                <th class="w-6"></th>
                <th class="text-left py-2.5 px-3">Symbol</th><th class="text-left py-2.5 px-3">Side</th>
                <th class="text-right py-2.5 px-3">Size</th><th class="text-right py-2.5 px-3">Entry</th>
                <th class="text-right py-2.5 px-3">Current</th><th class="text-right py-2.5 px-3">P&L</th>
                <th class="text-right py-2.5 px-3">P&L %</th><th class="text-right py-2.5 px-3">Value</th>
                <th class="text-right py-2.5 px-3">Tickets</th><th class="text-right py-2.5 px-3">Opened</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="p in openPositions" :key="p.symbol">
                <tr class="border-b border-surface-800/50 hover:bg-surface-800/30 cursor-pointer"
                    @click="p.tickets?.length && togglePositionExpand(p.symbol)">
                  <td class="py-2.5 pl-2">
                    <svg v-if="p.tickets?.length" class="w-3 h-3 text-surface-500 transition-transform"
                      :class="{ 'rotate-90': expandedPositions[p.symbol] }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>
                  </td>
                  <td class="py-2.5 px-3 font-mono font-medium text-surface-100">{{ p.symbol }}</td>
                  <td class="py-2.5 px-3"><span class="badge text-[10px]" :class="p.type === 'long' ? 'badge-green' : 'badge-red'">{{ p.type?.toUpperCase() }}</span></td>
                  <td class="py-2.5 px-3 text-right font-mono text-surface-200">{{ p.qty }}</td>
                  <td class="py-2.5 px-3 text-right font-mono text-surface-300">{{ fmtPrice(p.entry_price) }}</td>
                  <td class="py-2.5 px-3 text-right font-mono text-surface-200">{{ fmtPrice(p.current_price) }}</td>
                  <td class="py-2.5 px-3 text-right font-mono font-medium" :class="plColor(p.pnl)">{{ fmtPl(p.pnl) }}</td>
                  <td class="py-2.5 px-3 text-right font-mono" :class="plColor(p.pnl_percentage)">{{ p.pnl_percentage ? p.pnl_percentage.toFixed(2) + '%' : '-' }}</td>
                  <td class="py-2.5 px-3 text-right font-mono text-surface-300">{{ fmtCcy(p.value) }}</td>
                  <td class="py-2.5 px-3 text-right text-surface-400">{{ p.tickets?.length || 0 }}</td>
                  <td class="py-2.5 px-3 text-right text-surface-500 text-xs">{{ formatTime(p.opened_at) }}</td>
                </tr>
                <!-- Expanded tickets sub-table -->
                <tr v-if="expandedPositions[p.symbol] && p.tickets?.length">
                  <td :colspan="11" class="p-0">
                    <div class="bg-surface-850/80 border-l-2 border-brand-500/40 ml-4 mr-2 mb-2 rounded">
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="text-surface-500 text-[10px] uppercase tracking-wider border-b border-surface-700/50">
                            <th class="text-left py-1.5 px-3">Ticket</th>
                            <th class="text-left py-1.5 px-2">Side</th>
                            <th class="text-right py-1.5 px-2">Qty</th>
                            <th class="text-right py-1.5 px-2">Entry</th>
                            <th class="text-right py-1.5 px-2">P&L</th>
                            <th class="text-right py-1.5 px-2">Pips</th>
                            <th class="text-left py-1.5 px-2">Trade ID</th>
                            <th class="text-right py-1.5 px-2">Opened</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="tk in p.tickets" :key="tk.id" class="border-b border-surface-800/30 hover:bg-surface-700/20">
                            <td class="py-1.5 px-3 font-mono text-brand-400">{{ tk.id?.slice(0, 8) }}</td>
                            <td class="py-1.5 px-2"><span :class="tk.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ tk.type?.toUpperCase() }}</span></td>
                            <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ Math.abs(tk.qty) }}</td>
                            <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ fmtPrice(tk.entry_price) }}</td>
                            <td class="py-1.5 px-2 text-right font-mono" :class="plColor(tk.pnl)">{{ fmtPl(tk.pnl) }}</td>
                            <td class="py-1.5 px-2 text-right font-mono" :class="plColor(tk.pips)">{{ tk.pips != null ? tk.pips.toFixed(1) : '-' }}</td>
                            <td class="py-1.5 px-2 font-mono text-surface-500">{{ tk.trade_id || '-' }}</td>
                            <td class="py-1.5 px-2 text-right text-surface-500">{{ formatTime(tk.opened_at) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Orders Tab -->
      <div v-if="detailTab === 'Orders'" class="card">
        <div v-if="liveState.orders_summary" class="flex gap-4 mb-3 text-xs">
          <span class="text-surface-400">Total: <span class="text-surface-200">{{ liveState.orders_summary.total }}</span></span>
          <span class="text-green-400">Executed: {{ liveState.orders_summary.executed }}</span>
          <span class="text-yellow-400">Active: {{ liveState.orders_summary.active }}</span>
          <span class="text-surface-500">Canceled: {{ liveState.orders_summary.canceled }}</span>
        </div>
        <div v-if="allOrders.length === 0" class="text-center py-8 text-surface-500 text-sm">No orders yet</div>
        <div v-else class="overflow-auto max-h-[400px]">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-surface-850">
              <tr class="text-surface-500 text-[11px] uppercase tracking-wider border-b border-surface-700">
                <th class="text-left py-2 px-3">Symbol</th><th class="text-left py-2 px-3">Side</th>
                <th class="text-left py-2 px-3">Type</th><th class="text-right py-2 px-3">Qty</th>
                <th class="text-right py-2 px-3">Price</th><th class="text-left py-2 px-3">Status</th>
                <th class="text-right py-2 px-3">Time</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(o, i) in sortedOrders" :key="i" class="border-b border-surface-800/50 hover:bg-surface-800/30">
                <td class="py-2 px-3 font-mono text-surface-200">{{ o.symbol }}</td>
                <td class="py-2 px-3"><span class="font-medium" :class="o.side === 'buy' ? 'text-green-400' : 'text-red-400'">{{ o.side?.toUpperCase() }}</span></td>
                <td class="py-2 px-3 text-surface-400 capitalize">{{ o.type }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-200">{{ o.qty }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-200">{{ fmtPrice(o.price) }}</td>
                <td class="py-2 px-3"><span class="badge text-[10px]" :class="orderStatusClass(o.status)">{{ o.status }}</span></td>
                <td class="py-2 px-3 text-right text-surface-500 text-xs">{{ formatTime(o.executed_at || o.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Logs Tab -->
      <div v-if="detailTab === 'Logs'" class="card">
        <div class="flex items-center justify-between mb-3">
          <div class="flex gap-1">
            <button v-for="lt in logTypes" :key="lt" @click="logFilter = lt"
              class="px-2 py-1 text-[10px] rounded"
              :class="logFilter === lt ? 'bg-surface-700 text-surface-200' : 'text-surface-500 hover:text-surface-300'">
              {{ lt }}
            </button>
          </div>
          <button @click="loadLogs" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
        </div>
        <div v-if="filteredLogs.length === 0" class="text-center py-8 text-surface-500 text-sm">No logs</div>
        <div v-else class="overflow-auto max-h-[500px] space-y-0.5 font-mono text-xs">
          <div v-for="(log, i) in filteredLogs" :key="i"
            class="flex gap-3 py-1.5 px-2 rounded hover:bg-surface-800/30"
            :class="log.level === 'error' ? 'bg-red-500/5' : log.level === 'warning' ? 'bg-yellow-500/5' : ''">
            <span class="text-surface-600 whitespace-nowrap shrink-0">{{ formatTime(log.time) }}</span>
            <span v-if="log.level !== 'info'" class="shrink-0 w-14 text-right"
              :class="log.level === 'error' ? 'text-red-400' : 'text-yellow-400'">[{{ log.level }}]</span>
            <span :class="log.level === 'error' ? 'text-red-300' : log.level === 'warning' ? 'text-yellow-300' : 'text-surface-300'" class="break-all">{{ log.message }}</span>
          </div>
        </div>
      </div>

      <!-- Session Tab (Live Surefire State) -->
      <div v-if="detailTab === 'Session'" class="space-y-3">
        <div v-if="!currentSession" class="card text-center py-8 text-surface-500 text-sm">No active strategy session data.</div>
        <template v-else>
          <!-- Session status card -->
          <div class="card py-3">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <span class="text-sm font-semibold text-brand-400">Session #{{ currentSession.session_number || '-' }}</span>
                <span class="badge text-[10px]" :class="currentSession.cycle_active ? 'badge-green' : 'badge-gray'">
                  {{ currentSession.cycle_active ? 'ACTIVE' : 'IDLE' }}
                </span>
                <span v-if="currentSession.direction" class="badge text-[10px]"
                  :class="currentSession.direction === 'long' ? 'badge-green' : 'badge-red'">
                  {{ currentSession.direction?.toUpperCase() }}
                </span>
              </div>
              <span class="text-xs text-surface-500">Level {{ currentSession.level || 0 }}</span>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
              <div>
                <div class="text-[10px] text-surface-500 uppercase">TP Price</div>
                <div class="text-sm font-mono text-green-400">{{ fmtPrice(currentSession.tp_price) }}</div>
              </div>
              <div>
                <div class="text-[10px] text-surface-500 uppercase">Hedge Price</div>
                <div class="text-sm font-mono text-yellow-400">{{ fmtPrice(currentSession.hedge_price) }}</div>
              </div>
              <div>
                <div class="text-[10px] text-surface-500 uppercase">Net Qty</div>
                <div class="text-sm font-mono text-surface-200">{{ currentSession.net_qty || 0 }}</div>
              </div>
              <div>
                <div class="text-[10px] text-surface-500 uppercase">Open Tickets</div>
                <div class="text-sm font-mono text-surface-200">{{ currentSession.ticket_count || 0 }}</div>
              </div>
            </div>
          </div>

          <!-- Legs table -->
          <div v-if="currentSession.legs?.length" class="card">
            <h3 class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-2">
              Legs ({{ currentSession.legs.length }})
            </h3>
            <div class="overflow-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-surface-500 text-[10px] uppercase tracking-wider border-b border-surface-700">
                    <th class="text-left py-1.5 px-3">Level</th>
                    <th class="text-left py-1.5 px-2">Side</th>
                    <th class="text-right py-1.5 px-2">Qty</th>
                    <th class="text-right py-1.5 px-2">Entry</th>
                    <th class="text-right py-1.5 px-2">P&L</th>
                    <th class="text-left py-1.5 px-2">Trade ID</th>
                    <th class="text-left py-1.5 px-2">Ticket</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(leg, i) in currentSession.legs" :key="i" class="border-b border-surface-800/30 hover:bg-surface-800/30">
                    <td class="py-1.5 px-3 font-mono font-bold text-brand-400">L{{ leg.level ?? i }}</td>
                    <td class="py-1.5 px-2"><span :class="leg.side === 'buy' || leg.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ (leg.side || leg.type)?.toUpperCase() }}</span></td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ Math.abs(leg.qty) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ fmtPrice(leg.entry_price) }}</td>
                    <td class="py-1.5 px-2 text-right font-mono" :class="plColor(leg.pnl)">{{ leg.pnl != null ? fmtPl(leg.pnl) : '-' }}</td>
                    <td class="py-1.5 px-2 font-mono text-surface-500">{{ leg.trade_id || '-' }}</td>
                    <td class="py-1.5 px-2 font-mono text-surface-500">{{ leg.ticket_id ? leg.ticket_id.slice(0, 8) : '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Session history (past sessions in this run) -->
          <div v-if="strategySessions.length > 1" class="card">
            <h3 class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-2">
              Past Sessions ({{ strategySessions.length - (currentSession.cycle_active ? 1 : 0) }})
            </h3>
            <div class="space-y-1 max-h-[300px] overflow-auto">
              <div v-for="ss in strategySessions" :key="ss.session_number"
                class="flex items-center justify-between px-3 py-1.5 rounded hover:bg-surface-800/30 text-xs"
                :class="ss.session_number === currentSession.session_number ? 'bg-surface-800/50' : ''">
                <div class="flex items-center gap-3">
                  <span class="font-mono font-bold text-brand-400">S{{ ss.session_number }}</span>
                  <span class="text-surface-400">L{{ ss.max_level || 0 }}</span>
                  <span :class="sessionOutcomeClass(ss.outcome)">{{ sessionOutcomeLabel(ss.outcome) }}</span>
                </div>
                <span class="font-mono" :class="plColor(ss.pnl)">{{ ss.pnl != null ? fmtPl(ss.pnl) : '-' }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Closed Trades Tab (Real-time during session) -->
      <div v-if="detailTab === 'Closed Trades'" class="card">
        <div v-if="liveClosedTrades.length === 0" class="text-center py-8 text-surface-500 text-sm">No closed trades yet.</div>
        <div v-else class="overflow-auto max-h-[500px]">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-surface-850">
              <tr class="text-surface-500 text-[11px] uppercase tracking-wider border-b border-surface-700">
                <th class="text-left py-2 px-3">Symbol</th>
                <th class="text-left py-2 px-3">Side</th>
                <th class="text-right py-2 px-3">Qty</th>
                <th class="text-right py-2 px-3">Entry</th>
                <th class="text-right py-2 px-3">Exit</th>
                <th class="text-right py-2 px-3">P&L</th>
                <th class="text-left py-2 px-3">Label</th>
                <th class="text-right py-2 px-3">Closed</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(t, i) in liveClosedTrades" :key="i" class="border-b border-surface-800/50 hover:bg-surface-800/30">
                <td class="py-2 px-3 font-mono text-surface-200">{{ t.symbol }}</td>
                <td class="py-2 px-3"><span :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type?.toUpperCase() }}</span></td>
                <td class="py-2 px-3 text-right font-mono text-surface-200">{{ t.qty }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-300">{{ fmtPrice(t.entry_price) }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-300">{{ fmtPrice(t.exit_price) }}</td>
                <td class="py-2 px-3 text-right font-mono font-medium" :class="plColor(t.pnl || t.PNL)">{{ fmtPl(t.pnl || t.PNL) }}</td>
                <td class="py-2 px-3 text-xs"><span class="font-mono text-brand-400">{{ t.meta?.label || '-' }}</span></td>
                <td class="py-2 px-3 text-right text-surface-500 text-xs">{{ formatTime(t.closed_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Report Tab (Post-Execution Analysis) -->
      <div v-if="detailTab === 'Report'" class="space-y-4">
        <div v-if="!report.total_trades && activeMeta.status === 'running'" class="card text-center py-8">
          <p class="text-surface-500 text-sm">Report will be generated when session stops.</p>
        </div>
        <div v-else-if="!report.total_trades" class="card text-center py-8">
          <p class="text-surface-500 text-sm">No trades were executed during this session.</p>
        </div>
        <template v-else>
          <!-- Summary cards -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase mb-1">Total P&L</div>
              <div class="text-xl font-bold font-mono" :class="plColor(report.total_pnl)">{{ fmtPl(report.total_pnl) }}</div>
              <div class="text-[10px] mt-0.5" :class="plColor(report.total_pnl_pct)">{{ report.total_pnl_pct?.toFixed(2) }}%</div>
            </div>
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase mb-1">Win Rate</div>
              <div class="text-xl font-bold" :class="report.win_rate >= 50 ? 'text-green-400' : 'text-red-400'">{{ report.win_rate?.toFixed(1) }}%</div>
              <div class="text-[10px] text-surface-400 mt-0.5">{{ report.winning_trades }}W / {{ report.losing_trades }}L</div>
            </div>
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase mb-1">Max Drawdown</div>
              <div class="text-xl font-bold text-red-400 font-mono">{{ fmtCcy(report.max_drawdown) }}</div>
            </div>
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase mb-1">Total Trades</div>
              <div class="text-xl font-bold text-surface-100">{{ report.total_trades }}</div>
              <div class="text-[10px] text-surface-400 mt-0.5">{{ formatDuration(report.session_duration) }}</div>
            </div>
          </div>

          <!-- Detailed metrics -->
          <div class="card">
            <h3 class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-3">Performance Metrics</h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-y-3 gap-x-6 text-sm">
              <div><span class="text-surface-500 text-xs">Starting Balance</span><div class="text-surface-200 font-mono">{{ fmtCcy(report.starting_balance) }}</div></div>
              <div><span class="text-surface-500 text-xs">Ending Balance</span><div class="font-mono" :class="cmpColor(report.ending_balance, report.starting_balance)">{{ fmtCcy(report.ending_balance) }}</div></div>
              <div><span class="text-surface-500 text-xs">Avg Win</span><div class="text-green-400 font-mono">{{ fmtPl(report.avg_win) }}</div></div>
              <div><span class="text-surface-500 text-xs">Avg Loss</span><div class="text-red-400 font-mono">{{ fmtPl(report.avg_loss) }}</div></div>
              <div><span class="text-surface-500 text-xs">Largest Win</span><div class="text-green-400 font-mono">{{ fmtPl(report.largest_win) }}</div></div>
              <div><span class="text-surface-500 text-xs">Largest Loss</span><div class="text-red-400 font-mono">{{ fmtPl(report.largest_loss) }}</div></div>
              <div><span class="text-surface-500 text-xs">Win Streak</span><div class="text-surface-200">{{ report.winning_streak }}</div></div>
              <div><span class="text-surface-500 text-xs">Loss Streak</span><div class="text-surface-200">{{ report.losing_streak }}</div></div>
              <div><span class="text-surface-500 text-xs">Total Fees</span><div class="text-surface-300 font-mono">{{ fmtCcy(report.total_fees) }}</div></div>
              <div><span class="text-surface-500 text-xs">Avg Holding</span><div class="text-surface-200">{{ formatHoldingPeriod(report.avg_holding_period) }}</div></div>
            </div>
          </div>

          <!-- Sessions view (when hedge sessions exist) -->
          <div v-if="reportSessions.length" class="card">
            <h3 class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-3">
              Hedge Sessions ({{ reportSessions.length }})
              <span class="ml-2 text-surface-500 normal-case font-normal">
                {{ reportSessions.filter(s => s.outcome === 'tp_hit').length }} TP Hit,
                {{ reportSessions.filter(s => s.outcome === 'max_levels').length }} Max Levels
              </span>
            </h3>
            <div class="space-y-2 max-h-[500px] overflow-auto">
              <div v-for="s in reportSessions" :key="s.session" class="bg-surface-800/60 rounded overflow-hidden">
                <!-- Session header -->
                <div @click="toggleReportSession(s.session)" class="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-surface-700/50 transition-colors">
                  <div class="flex items-center gap-3">
                    <span class="text-xs font-mono font-bold text-brand-400">S{{ s.session }}</span>
                    <span class="text-xs text-surface-400">{{ s.trade_count }} trade{{ s.trade_count !== 1 ? 's' : '' }}</span>
                    <span class="text-xs" :class="sessionOutcomeClass(s.outcome)">{{ sessionOutcomeLabel(s.outcome) }}</span>
                    <span v-if="s.levels > 0" class="text-[10px] text-surface-500 font-mono">L{{ s.levels }}</span>
                  </div>
                  <div class="flex items-center gap-4">
                    <span class="text-xs font-mono" :class="s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'">
                      {{ s.total_pnl >= 0 ? '+' : '' }}{{ s.total_pnl.toFixed(2) }}
                    </span>
                    <svg class="w-3 h-3 text-surface-500 transition-transform" :class="{ 'rotate-180': expandedReportSessions[s.session] }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                  </div>
                </div>
                <!-- Expanded trades -->
                <div v-if="expandedReportSessions[s.session]" class="border-t border-surface-700">
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="text-surface-500 border-b border-surface-700">
                        <th class="text-left py-1.5 px-3">Label</th><th class="text-left py-1.5 px-2">Side</th>
                        <th class="text-right py-1.5 px-2">Qty</th><th class="text-right py-1.5 px-2">Entry</th>
                        <th class="text-right py-1.5 px-2">Exit</th><th class="text-right py-1.5 px-2">P&L</th>
                        <th class="text-left py-1.5 px-2">Exit</th><th class="text-right py-1.5 px-2">Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(t, i) in s.trades" :key="i" class="border-b border-surface-800/30 hover:bg-surface-700/30">
                        <td class="py-1.5 px-3 font-mono font-bold" :class="t.meta?.exit_reason === 'tp_hit' ? 'text-green-400' : 'text-surface-300'">{{ t.meta?.label || `O${i+1}` }}</td>
                        <td class="py-1.5 px-2" :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type?.toUpperCase() }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-200">{{ t.qty }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ fmtPrice(t.entry_price) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ fmtPrice(t.exit_price) }}</td>
                        <td class="py-1.5 px-2 text-right font-mono" :class="plColor(t.PNL || t.pnl)">{{ fmtPl(t.PNL || t.pnl) }}</td>
                        <td class="py-1.5 px-2" :class="sessionOutcomeClass(t.meta?.exit_reason)">{{ t.meta?.exit_reason === 'tp_hit' ? 'TP' : t.meta?.exit_reason === 'sl_hit' ? 'SL' : '-' }}</td>
                        <td class="py-1.5 px-2 text-right text-surface-500">{{ formatHoldingPeriod(t.holding_period) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <!-- Flat trade list (when no sessions / fallback) -->
          <div v-if="report.trades?.length" class="card">
            <h3 class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-3">
              {{ reportSessions.length ? 'All Trades' : 'Trade History' }}
            </h3>
            <div class="overflow-auto max-h-[400px]">
              <table class="w-full text-sm">
                <thead class="sticky top-0 bg-surface-850">
                  <tr class="text-surface-500 text-[11px] uppercase tracking-wider border-b border-surface-700">
                    <th v-if="reportSessions.length" class="text-left py-2 px-3">Label</th>
                    <th class="text-left py-2 px-3">Symbol</th><th class="text-left py-2 px-3">Side</th>
                    <th class="text-right py-2 px-3">Qty</th><th class="text-right py-2 px-3">Entry</th>
                    <th class="text-right py-2 px-3">Exit</th><th class="text-right py-2 px-3">P&L</th>
                    <th class="text-right py-2 px-3">P&L %</th><th class="text-right py-2 px-3">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(t, i) in report.trades" :key="i" class="border-b border-surface-800/50">
                    <td v-if="reportSessions.length" class="py-2 px-3 font-mono text-brand-400 text-xs">{{ t.meta?.label || '-' }}</td>
                    <td class="py-2 px-3 font-mono text-surface-200">{{ t.symbol }}</td>
                    <td class="py-2 px-3"><span :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type?.toUpperCase() }}</span></td>
                    <td class="py-2 px-3 text-right font-mono text-surface-200">{{ t.qty }}</td>
                    <td class="py-2 px-3 text-right font-mono text-surface-300">{{ fmtPrice(t.entry_price) }}</td>
                    <td class="py-2 px-3 text-right font-mono text-surface-300">{{ fmtPrice(t.exit_price) }}</td>
                    <td class="py-2 px-3 text-right font-mono font-medium" :class="plColor(t.PNL)">{{ fmtPl(t.PNL) }}</td>
                    <td class="py-2 px-3 text-right font-mono" :class="plColor(t.PNL_percentage)">{{ t.PNL_percentage?.toFixed(2) }}%</td>
                    <td class="py-2 px-3 text-right text-surface-500 text-xs">{{ formatHoldingPeriod(t.holding_period) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ════════════ Main Panel (no active session) ════════════ -->
    <div v-else class="space-y-4">
      <!-- Top-level tabs -->
      <div class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg w-full sm:w-fit overflow-x-auto">
        <button v-for="tab in mainTabs" :key="tab" @click="mainTab = tab"
          class="px-3 py-1.5 text-xs rounded-md font-medium transition-colors whitespace-nowrap"
          :class="mainTab === tab ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
          {{ tab }}
        </button>
      </div>

      <!-- ──── Sessions Tab ──── -->
      <template v-if="mainTab === 'Sessions'">
        <div class="flex items-center gap-3 mb-2">
          <button v-for="tab in statusTabs" :key="tab.value" @click="statusFilter = tab.value"
            class="btn-sm" :class="statusFilter === tab.value ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
            {{ tab.label }}
          </button>
          <div class="ml-auto flex items-center gap-2">
            <button v-if="sessions.length" @click="showPurgeConfirm = true" class="text-xs text-red-400 hover:text-red-300">Purge</button>
            <button @click="loadSessions" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
          </div>
        </div>
        <!-- Purge confirm -->
        <div v-if="showPurgeConfirm" class="card border-red-500/30">
          <h3 class="text-sm font-semibold text-red-400 mb-2">Purge Old Sessions</h3>
          <div class="flex items-center gap-3">
            <span class="text-xs text-surface-400">Delete stopped sessions older than</span>
            <select v-model.number="purgeDays" class="select text-xs w-auto">
              <option :value="7">7 days</option><option :value="14">14 days</option>
              <option :value="30">30 days</option><option :value="60">60 days</option><option :value="90">90 days</option>
            </select>
            <button @click="purgeSessions" class="btn-sm bg-red-500/20 text-red-400 hover:bg-red-500/30">Purge</button>
            <button @click="showPurgeConfirm = false" class="btn-sm bg-surface-700 text-surface-300">Cancel</button>
          </div>
        </div>
        <div v-if="loadingSessions" class="text-surface-500 text-sm">Loading sessions...</div>
        <div v-else-if="filteredSessions.length === 0" class="card text-center py-12">
          <p class="text-surface-500 mb-3">No trading sessions found.</p>
          <button @click="openStartModal" class="btn-primary btn-sm">Start Your First Session</button>
        </div>
        <div v-else class="space-y-2">
          <div v-for="s in filteredSessions" :key="s.id"
            class="card py-3 hover:border-surface-600 transition-colors cursor-pointer" @click="viewSession(s)">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <span class="w-2 h-2 rounded-full" :class="s.status === 'running' ? 'bg-green-400 animate-pulse' : s.status === 'error' ? 'bg-red-400' : 'bg-surface-500'"></span>
                <span :class="statusClass(s.status)" class="badge text-[10px]">{{ s.status }}</span>
                <span class="badge text-[10px]" :class="s.session_mode === 'livetrade' ? 'badge-yellow' : 'badge-blue'">
                  {{ s.session_mode === 'livetrade' ? 'LIVE' : 'DEMO' }}
                </span>
                <span class="text-sm text-surface-200">{{ s.title || s.exchange }}</span>
                <span class="text-xs text-surface-500">{{ routeSummary(s) }}</span>
                <span v-if="s.owner_username && showOwnerLabel" class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 font-medium">{{ s.owner_username }}</span>
              </div>
              <div class="flex items-center gap-2" @click.stop>
                <button v-if="s.status === 'running'" @click="stopSession(s.id)"
                  class="btn-sm bg-red-500/20 text-red-400 hover:bg-red-500/30 text-xs">Stop</button>
                <button @click="removeSession(s.id)" class="text-xs text-surface-500 hover:text-red-400">Remove</button>
              </div>
            </div>
            <div class="flex items-center gap-4 mt-2 text-xs text-surface-500">
              <span>{{ s.exchange }}</span>
              <span v-if="s.created_at">{{ formatDate(s.created_at) }}</span>
              <span class="font-mono">{{ s.id?.slice(0, 8) }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- ──── Overview Tab ──── -->
      <template v-if="mainTab === 'Overview'">
        <div v-if="runningSessions.length === 0" class="card text-center py-12">
          <p class="text-surface-500 mb-3">No running sessions.</p>
          <button @click="openStartModal" class="btn-primary btn-sm">Start a Session</button>
        </div>
        <template v-else>
          <!-- Aggregate stats -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Running Sessions</div>
              <div class="text-2xl font-bold text-green-400">{{ runningSessions.length }}</div>
            </div>
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Total Balance</div>
              <div class="text-lg font-bold text-surface-100 font-mono">{{ fmtUsd(overviewAgg.balance) }}</div>
            </div>
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Total Unrealized P&L</div>
              <div class="text-lg font-bold font-mono" :class="plColor(overviewAgg.unrealized_pnl)">{{ fmtPlUsd(overviewAgg.unrealized_pnl) }}</div>
            </div>
            <div class="card py-3 text-center">
              <div class="text-[10px] text-surface-500 uppercase tracking-wider mb-1">Total Open Positions</div>
              <div class="text-2xl font-bold text-surface-100">{{ overviewAgg.open_positions }}</div>
            </div>
          </div>

          <!-- Per-session cards -->
          <div class="space-y-3">
            <div v-for="os in overviewSessions" :key="os.id" class="card py-3 hover:border-surface-600 cursor-pointer transition-colors"
              @click="viewSessionById(os.id)">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-3">
                  <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
                  <span class="badge badge-green text-[10px]">running</span>
                  <span class="badge text-[10px]" :class="os.mode === 'livetrade' ? 'badge-yellow' : 'badge-blue'">
                    {{ os.mode === 'livetrade' ? 'LIVE' : 'DEMO' }}
                  </span>
                  <span class="text-sm font-semibold text-surface-200">{{ os.exchange }}</span>
                  <span class="text-xs text-surface-500">{{ os.routes }}</span>
                </div>
                <span v-if="os.duration" class="text-xs text-surface-500">{{ formatDuration(os.duration) }}</span>
              </div>
              <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
                <div>
                  <div class="text-[10px] text-surface-500">Balance</div>
                  <div class="text-sm font-mono text-surface-200">{{ fmtUsd(os.balance) }}</div>
                </div>
                <div>
                  <div class="text-[10px] text-surface-500">NAV</div>
                  <div class="text-sm font-mono" :class="cmpColor(os.nav, os.balance)">{{ fmtUsd(os.nav) }}</div>
                </div>
                <div>
                  <div class="text-[10px] text-surface-500">Unrealized P&L</div>
                  <div class="text-sm font-mono" :class="plColor(os.unrealized_pnl)">{{ fmtPlUsd(os.unrealized_pnl) }}</div>
                </div>
                <div>
                  <div class="text-[10px] text-surface-500">Positions</div>
                  <div class="text-sm text-surface-200">{{ os.open_positions }}</div>
                </div>
                <div>
                  <div class="text-[10px] text-surface-500">Trades</div>
                  <div class="text-sm text-surface-200">{{ os.total_trades }}</div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </template>

      <!-- ──── Orders History Tab ──── -->
      <template v-if="mainTab === 'Orders History'">
        <div class="flex items-center gap-3 mb-2 flex-wrap">
          <input v-model="ordersFilter.symbol" class="input w-32 text-xs" placeholder="Symbol..." />
          <select v-model="ordersFilter.status" class="select w-32 text-xs">
            <option value="">All Status</option>
            <option value="EXECUTED">Executed</option><option value="ACTIVE">Active</option><option value="CANCELED">Canceled</option>
          </select>
          <select v-model="ordersFilter.side" class="select w-28 text-xs">
            <option value="">All Sides</option><option value="buy">Buy</option><option value="sell">Sell</option>
          </select>
          <button @click="loadOrdersHistory" class="btn-sm bg-brand-600 text-white">Search</button>
          <span class="text-xs text-surface-500 ml-auto">{{ historyOrders.length }} order(s)</span>
        </div>
        <div v-if="loadingOrdersHistory" class="text-surface-500 text-sm">Loading...</div>
        <div v-else-if="historyOrders.length === 0" class="card text-center py-8 text-surface-500 text-sm">No orders found.</div>
        <div v-else class="card overflow-auto">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-surface-850">
              <tr class="text-surface-500 text-[11px] uppercase tracking-wider border-b border-surface-700">
                <th class="text-left py-2 px-3">Symbol</th><th class="text-left py-2 px-3">Side</th>
                <th class="text-left py-2 px-3">Type</th><th class="text-right py-2 px-3">Qty</th>
                <th class="text-right py-2 px-3">Price</th><th class="text-left py-2 px-3">Status</th>
                <th class="text-left py-2 px-3">Exchange</th><th class="text-right py-2 px-3">Time</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in historyOrders" :key="o.id" class="border-b border-surface-800/50 hover:bg-surface-800/30">
                <td class="py-2 px-3 font-mono text-surface-200">{{ o.symbol }}</td>
                <td class="py-2 px-3"><span class="font-medium" :class="o.side === 'buy' ? 'text-green-400' : 'text-red-400'">{{ o.side?.toUpperCase() }}</span></td>
                <td class="py-2 px-3 text-surface-400 capitalize">{{ o.type }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-200">{{ o.qty }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-200">{{ fmtPrice(o.price) }}</td>
                <td class="py-2 px-3"><span class="badge text-[10px]" :class="orderStatusClass(o.status)">{{ o.status }}</span></td>
                <td class="py-2 px-3 text-surface-400 text-xs">{{ o.exchange }}</td>
                <td class="py-2 px-3 text-right text-surface-500 text-xs">{{ formatDate(o.executed_at || o.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- ──── Trades History Tab ──── -->
      <template v-if="mainTab === 'Trades History'">
        <div class="flex items-center gap-3 mb-2 flex-wrap">
          <input v-model="tradesFilter.symbol" class="input w-32 text-xs" placeholder="Symbol..." />
          <select v-model="tradesFilter.type" class="select w-28 text-xs">
            <option value="">All Types</option><option value="long">Long</option><option value="short">Short</option>
          </select>
          <button @click="loadTradesHistory" class="btn-sm bg-brand-600 text-white">Search</button>
          <span class="text-xs text-surface-500 ml-auto">{{ historyTrades.length }} trade(s)</span>
        </div>
        <div v-if="loadingTradesHistory" class="text-surface-500 text-sm">Loading...</div>
        <div v-else-if="historyTrades.length === 0" class="card text-center py-8 text-surface-500 text-sm">No closed trades found.</div>
        <div v-else class="card overflow-auto">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-surface-850">
              <tr class="text-surface-500 text-[11px] uppercase tracking-wider border-b border-surface-700">
                <th class="text-left py-2 px-3">Symbol</th><th class="text-left py-2 px-3">Side</th>
                <th class="text-right py-2 px-3">Qty</th><th class="text-right py-2 px-3">Entry</th>
                <th class="text-right py-2 px-3">Exit</th><th class="text-right py-2 px-3">P&L</th>
                <th class="text-right py-2 px-3">P&L %</th><th class="text-left py-2 px-3">Exchange</th>
                <th class="text-right py-2 px-3">Opened</th><th class="text-right py-2 px-3">Closed</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in historyTrades" :key="t.id" class="border-b border-surface-800/50 hover:bg-surface-800/30">
                <td class="py-2 px-3 font-mono text-surface-200">{{ t.symbol }}</td>
                <td class="py-2 px-3"><span :class="t.type === 'long' ? 'text-green-400' : 'text-red-400'">{{ t.type?.toUpperCase() }}</span></td>
                <td class="py-2 px-3 text-right font-mono text-surface-200">{{ t.qty }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-300">{{ fmtPrice(t.entry_price) }}</td>
                <td class="py-2 px-3 text-right font-mono text-surface-300">{{ fmtPrice(t.exit_price) }}</td>
                <td class="py-2 px-3 text-right font-mono font-medium" :class="plColor(t.pnl)">{{ fmtPlUsd(t.pnl) }}</td>
                <td class="py-2 px-3 text-right font-mono" :class="plColor(t.pnl_percentage)">{{ t.pnl_percentage != null ? t.pnl_percentage.toFixed(2) + '%' : '-' }}</td>
                <td class="py-2 px-3 text-surface-400 text-xs">{{ t.exchange }}</td>
                <td class="py-2 px-3 text-right text-surface-500 text-xs">{{ formatDate(t.opened_at) }}</td>
                <td class="py-2 px-3 text-right text-surface-500 text-xs">{{ formatDate(t.closed_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { api, defaultBrokerId, isAdmin, isImpersonating } from '../api'

const showStart = ref(false)
const starting = ref(false)
const startError = ref('')
const brokers = ref([])
const strategies = ref([])
const instruments = ref([])
const sessions = ref([])
const loadingSessions = ref(true)
const statusFilter = ref('all')

const mainTab = ref('Sessions')
const mainTabs = ['Sessions', 'Overview', 'Orders History', 'Trades History']
const showPurgeConfirm = ref(false)
const purgeDays = ref(30)

const activeView = ref(null)
const activeMeta = ref({})
const liveState = ref({})
const allOrders = ref([])
const logs = ref([])
const report = ref({})
const detailTab = ref('Positions')
const logFilter = ref('all')
let pollTimer = null

// Session tabs
const openTabs = ref([])
const tabCache = ref({})

// Overview
const overviewSessions = ref([])
let overviewTimer = null

// Orders History
const historyOrders = ref([])
const loadingOrdersHistory = ref(false)
const ordersFilter = ref({ symbol: '', status: '', side: '' })

// Trades History
const historyTrades = ref([])
const loadingTradesHistory = ref(false)
const tradesFilter = ref({ symbol: '', type: '' })

const form = ref({
  exchange: '', symbol: 'EUR-USD', strategy: '', debug_mode: false,
})
const availablePipelines = ref([])
const pipelineEnabled = ref(false)
const livePipelineConfigs = ref([{ name: '' }])
const hpExpanded = ref(false)

// Hyperparameters (loaded from strategy code)
const liveHyperParams = ref([])
const liveHyperParamsDefaults = ref([])

async function loadLiveHyperparams(name) {
  if (!name) { liveHyperParams.value = []; liveHyperParamsDefaults.value = []; return }
  try {
    const res = await api.getStrategyHyperparams(name)
    const hps = (res.hyperparameters || []).map(hp => ({
      name: hp.name,
      type: hp.type === 'categorical' ? 'categorical' : hp.type === 'int' ? 'int' : hp.type === 'float' ? 'float' : hp.type === 'str' ? 'str' : 'float',
      value: hp.default !== undefined ? hp.default : '',
      default: hp.default,
      min: hp.min,
      max: hp.max,
      options: hp.options || undefined,
      depends_on: hp.depends_on || undefined,
    }))
    liveHyperParams.value = hps
    liveHyperParamsDefaults.value = JSON.parse(JSON.stringify(hps))
  } catch {
    liveHyperParams.value = []
    liveHyperParamsDefaults.value = []
  }
}

function isLiveHpVisible(hp) {
  if (!hp.depends_on) return true
  for (const [key, allowedValues] of Object.entries(hp.depends_on)) {
    const parent = liveHyperParams.value.find(p => p.name === key)
    if (parent && !allowedValues.includes(parent.value)) return false
  }
  return true
}

function resetLiveHyperParams() {
  liveHyperParams.value = JSON.parse(JSON.stringify(liveHyperParamsDefaults.value))
}

function buildLiveHyperparamsPayload() {
  const hp = {}
  for (const p of liveHyperParams.value) {
    if (p.name && p.value !== '' && p.value !== undefined) {
      hp[p.name] = p.type === 'int' ? parseInt(p.value) : p.type === 'float' ? parseFloat(p.value) : String(p.value)
    }
  }
  return Object.keys(hp).length ? hp : null
}

watch(() => form.value.strategy, (newStrat, oldStrat) => {
  if (newStrat && newStrat !== oldStrat) loadLiveHyperparams(newStrat)
})

const selectedBrokerIsDemo = computed(() => {
  const b = brokers.value.find(x => x.id === form.value.exchange)
  return b ? b.is_demo : true
})

const statusTabs = [
  { value: 'all', label: 'All' }, { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' }, { value: 'error', label: 'Errors' },
]
const logTypes = ['all', 'info', 'warning', 'error']

const acct = computed(() => liveState.value.account || {})
const marginPct = computed(() => {
  const a = acct.value
  if (!a.balance || !a.margin_used) return null
  return (a.margin_used / a.balance) * 100
})
const availableTabs = computed(() => {
  const tabs = ['Positions', 'Orders']
  if (currentSession.value) tabs.push('Session')
  tabs.push('Closed Trades')
  tabs.push('Logs')
  if (activeMeta.value.status !== 'running' || report.value.total_trades) tabs.push('Report')
  return tabs
})
function togglePositionExpand(symbol) { expandedPositions.value[symbol] = !expandedPositions.value[symbol] }
const showOwnerLabel = computed(() => isAdmin() && !isImpersonating())
const filteredSessions = computed(() => {
  if (statusFilter.value === 'all') return sessions.value
  return sessions.value.filter(s => s.status === statusFilter.value)
})
const runningSessions = computed(() => sessions.value.filter(s => s.status === 'running'))
const overviewAgg = computed(() => {
  let balance = 0, unrealized_pnl = 0, open_positions = 0
  for (const os of overviewSessions.value) {
    balance += os.balance || 0
    unrealized_pnl += os.unrealized_pnl || 0
    open_positions += os.open_positions || 0
  }
  return { balance, unrealized_pnl, open_positions }
})
const openPositions = computed(() => (liveState.value.positions || []).filter(p => p.type !== 'close'))
const expandedPositions = ref({})
const liveClosedTrades = computed(() => liveState.value.closed_trades || [])
const currentSession = computed(() => {
  const strats = liveState.value.strategies || []
  for (const s of strats) {
    if (s.current_session) return s.current_session
  }
  return null
})
const strategySessions = computed(() => {
  const strats = liveState.value.strategies || []
  for (const s of strats) {
    if (s.sessions?.length) return s.sessions
  }
  return []
})
const sortedOrders = computed(() => [...allOrders.value].sort((a, b) => (b.created_at || 0) - (a.created_at || 0)))
const filteredLogs = computed(() => {
  const arr = logFilter.value === 'all' ? logs.value : logs.value.filter(l => l.level === logFilter.value)
  return [...arr].reverse()
})

// Helpers
function plColor(v) { return v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-surface-400' }
function cmpColor(a, b) { return a > b ? 'text-green-400' : a < b ? 'text-red-400' : 'text-surface-100' }
function fmtCcy(v) {
  if (v == null) return '-'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: acct.value?.currency || 'USD', minimumFractionDigits: 2 }).format(v)
}
function fmtPl(v) {
  if (v == null) return '$0.00'
  const s = v >= 0 ? '+' : ''
  return s + new Intl.NumberFormat('en-US', { style: 'currency', currency: acct.value?.currency || 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(v)
}
function fmtPrice(v) { return v == null ? '-' : Number(v).toFixed(5) }
function formatDate(ts) { return ts ? new Date(ts).toLocaleString() : '' }
function formatTime(ts) { return ts ? new Date(ts).toLocaleTimeString() : '' }
function formatDuration(ms) {
  if (!ms) return '-'
  const s = Math.floor(ms / 1000); const m = Math.floor(s / 60); const h = Math.floor(m / 60)
  if (h > 0) return `${h}h ${m % 60}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}
function formatHoldingPeriod(seconds) {
  if (!seconds) return '-'
  const m = Math.floor(seconds / 60); const h = Math.floor(m / 60)
  if (h > 0) return `${h}h ${m % 60}m`
  if (m > 0) return `${m}m`
  return `${Math.round(seconds)}s`
}
function statusClass(s) {
  return s === 'running' ? 'badge-green' : s === 'starting' || s === 'stopping' ? 'badge-yellow' : s === 'error' ? 'badge-red' : 'badge-gray'
}
function orderStatusClass(s) {
  return s === 'EXECUTED' ? 'badge-green' : s === 'ACTIVE' ? 'badge-yellow' : 'badge-gray'
}
function routeSummary(s) {
  const routes = s.state?.form?.routes || []
  return routes.map(r => `${r.symbol} ${r.timeframe} ${r.strategy}`).join(', ')
}
function fmtUsd(v) {
  if (v == null) return '-'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(v)
}
function fmtPlUsd(v) {
  if (v == null) return '$0.00'
  const s = v >= 0 ? '+' : ''
  return s + new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(v)
}

// Session helpers for hedge strategies
const expandedReportSessions = ref({})

const reportSessions = computed(() => {
  if (!report.value.sessions?.length && !report.value.trades?.length) return []
  // Use server-provided sessions if available
  if (report.value.sessions?.length) return report.value.sessions
  // Otherwise build from trade meta
  return buildSessionsFromTrades(report.value.trades || [])
})

function buildSessionsFromTrades(tradesList) {
  const map = {}
  const standalone = []
  for (const t of tradesList) {
    const sn = t.meta?.session
    if (sn == null) { standalone.push(t); continue }
    if (!map[sn]) {
      map[sn] = { session: sn, trades: [], total_pnl: 0, total_fee: 0, opened_at: t.opened_at, closed_at: null, outcome: null, levels: 0, trade_count: 0 }
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
    s.trades.sort((a, b) => (a.meta?.leg_index ?? 999) - (b.meta?.leg_index ?? 999))
    s.trade_count = s.trades.length
    s.total_pnl = parseFloat(s.total_pnl.toFixed(6))
    s.total_fee = parseFloat(s.total_fee.toFixed(6))
    return s
  })
  standalone.forEach((t, i) => {
    const exitReason = t.meta?.exit_reason || 'standalone'
    result.push({ session: `standalone-${i + 1}`, trades: [t], total_pnl: t.pnl || t.PNL || 0, total_fee: t.fee || 0, opened_at: t.opened_at, closed_at: t.closed_at, outcome: exitReason, levels: 0, trade_count: 1 })
  })
  return result
}

function toggleReportSession(sessionNum) {
  expandedReportSessions.value[sessionNum] = !expandedReportSessions.value[sessionNum]
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
  if (outcome === 'max_level_sl') return 'Max Level SL'
  if (outcome === 'terminated') return 'Terminated'
  if (outcome === 'pipeline_abort') return 'Pipeline Abort'
  if (outcome === 'standalone') return 'Single'
  return outcome || '-'
}

// Actions
function openStartModal() { showStart.value = true; startError.value = '' }

async function startSession() {
  starting.value = true; startError.value = ''
  try {
    const id = crypto.randomUUID()
    const pipelineConfigs = pipelineEnabled.value
      ? livePipelineConfigs.value.filter(pc => pc.name)
      : null
    await api.startLive({
      id, exchange: form.value.exchange,
      exchange_api_key_id: '', notification_api_key_id: '', debug_mode: form.value.debug_mode,
      config: {
        warm_up_candles: 240,
        logging: { strategy_execution: true, order_submission: true, order_cancellation: true, order_execution: true, position_opened: true, position_increased: true, position_reduced: true, position_closed: true, shorter_period_candles: false, trading_candles: true, balance_update: true, exchange_ws_reconnection: true },
        exchanges: { '0': { name: form.value.exchange, fee: 0, balance: 0, type: '' } },
        notifications: {}, persistency: true, generate_candles_from_1m: false,
      },
      routes: [{ exchange: form.value.exchange, symbol: form.value.symbol, timeframe: '1m', strategy: form.value.strategy }],
      data_routes: [],
      hyperparameters: buildLiveHyperparamsPayload(),
      ...(pipelineConfigs?.length ? { pipelines: pipelineConfigs } : {}),
    })
    showStart.value = false
    setTimeout(async () => { await loadSessions(); const f = sessions.value.find(s => s.id === id); if (f) viewSession(f) }, 2000)
  } catch (e) { startError.value = e.message } finally { starting.value = false }
}

async function loadSessions() {
  loadingSessions.value = true
  try { const r = await api.getLiveSessions({ limit: 50 }); sessions.value = r.sessions || [] }
  catch { sessions.value = [] }
  finally { loadingSessions.value = false }
}

async function viewSession(s) {
  // Cache current session before switching
  if (activeView.value && activeView.value !== s.id) {
    tabCache.value[activeView.value] = { meta: { ...activeMeta.value }, state: { ...liveState.value }, orders: [...allOrders.value], logs: [...logs.value], report: { ...report.value }, detailTab: detailTab.value }
  }
  // Add tab if not already open
  if (!openTabs.value.find(t => t.id === s.id)) {
    const routes = s.state?.form?.routes || []
    const label = routes.length ? `${routes[0].symbol} ${routes[0].strategy}` : (s.title || s.exchange || s.id.slice(0, 8))
    openTabs.value.push({ id: s.id, label, status: s.status })
  }
  activeView.value = s.id
  // Restore from cache if available
  const cached = tabCache.value[s.id]
  if (cached) {
    activeMeta.value = cached.meta; liveState.value = cached.state; allOrders.value = cached.orders; logs.value = cached.logs; report.value = cached.report; detailTab.value = cached.detailTab
    delete tabCache.value[s.id]
    startPolling()
    return
  }
  activeMeta.value = { id: s.id, status: s.status, mode: s.session_mode, exchange: s.exchange, created_at: s.created_at, title: s.title, routes: s.state?.form?.routes || [] }
  detailTab.value = 'Positions'; logFilter.value = 'all'; report.value = {}
  await pollSessionState()
  await loadLogs()
  if (s.status !== 'running' && s.status !== 'starting') await loadReport()
  startPolling()
}

function switchToTab(id) {
  if (id === activeView.value) return
  const s = sessions.value.find(x => x.id === id)
  if (s) viewSession(s)
}

function closeTab(id) {
  openTabs.value = openTabs.value.filter(t => t.id !== id)
  delete tabCache.value[id]
  if (activeView.value === id) {
    stopPolling()
    if (openTabs.value.length > 0) {
      const last = openTabs.value[openTabs.value.length - 1]
      const s = sessions.value.find(x => x.id === last.id)
      if (s) { viewSession(s); return }
    }
    activeView.value = null; liveState.value = {}; allOrders.value = []; logs.value = []; report.value = {}; loadSessions()
  }
}

function closeActiveView() { closeTab(activeView.value) }
function startPolling() { stopPolling(); pollTimer = setInterval(async () => { await pollSessionState(); if (detailTab.value === 'Logs') await loadLogs() }, 2000) }
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

async function pollSessionState() {
  if (!activeView.value) return
  try {
    const res = await api.getLiveState(activeView.value)
    if (res.state && Object.keys(res.state).length > 0) liveState.value = res.state
    if (res.meta) {
      const wasActive = activeMeta.value.status === 'running' || activeMeta.value.status === 'stopping'
      activeMeta.value = { ...activeMeta.value, ...res.meta }
      // Session just stopped - load report
      if (wasActive && res.meta.status === 'stopped') {
        stopPolling()
        setTimeout(loadReport, 1000) // slight delay for report to be written
      }
    }
    const ordersRes = await api.getLiveOrders(activeView.value, activeView.value)
    allOrders.value = ordersRes.data || []
  } catch { /* ignore polling errors */ }
}

async function loadLogs() {
  if (!activeView.value) return
  try { const r = await api.getLiveLogs(activeView.value, 'all', 0); logs.value = r.data || [] } catch {}
}

async function loadReport() {
  if (!activeView.value) return
  try { const r = await api.getLiveReport(activeView.value); report.value = r.data || {} } catch {}
}

async function stopSession(id) {
  try {
    await api.cancelLive(id)
    if (activeView.value === id) activeMeta.value = { ...activeMeta.value, status: 'stopping' }
  } catch (e) { console.error(e) }
}

async function removeSession(id) {
  try { await api.removeLiveSession(id); closeTab(id); await loadSessions() } catch {}
}

// Overview methods
async function loadOverview() {
  const running = runningSessions.value
  const results = []
  for (const s of running) {
    try {
      const res = await api.getLiveState(s.id)
      const acct = res.state?.account || {}
      const routes = s.state?.form?.routes || []
      results.push({
        id: s.id, exchange: s.exchange, mode: s.session_mode,
        routes: routes.map(r => `${r.symbol} ${r.strategy}`).join(', '),
        balance: acct.balance, nav: acct.nav, unrealized_pnl: acct.unrealized_pnl,
        open_positions: acct.open_trade_count || (res.state?.positions || []).filter(p => p.type !== 'close').length,
        total_trades: acct.total_trades || 0,
        duration: acct.session_duration,
      })
    } catch { results.push({ id: s.id, exchange: s.exchange, mode: s.session_mode, routes: '', balance: 0, nav: 0, unrealized_pnl: 0, open_positions: 0, total_trades: 0, duration: 0 }) }
  }
  overviewSessions.value = results
}
function startOverviewPolling() { stopOverviewPolling(); loadOverview(); overviewTimer = setInterval(loadOverview, 3000) }
function stopOverviewPolling() { if (overviewTimer) { clearInterval(overviewTimer); overviewTimer = null } }

async function viewSessionById(id) {
  const s = sessions.value.find(x => x.id === id)
  if (s) viewSession(s)
}

// History methods
async function loadOrdersHistory() {
  loadingOrdersHistory.value = true
  try {
    const params = { limit: 100 }
    if (ordersFilter.value.symbol) params.symbol_filter = ordersFilter.value.symbol
    if (ordersFilter.value.status) params.status_filter = ordersFilter.value.status
    if (ordersFilter.value.side) params.side_filter = ordersFilter.value.side
    const res = await api.getOrdersHistory(params)
    historyOrders.value = res.orders || []
  } catch { historyOrders.value = [] }
  finally { loadingOrdersHistory.value = false }
}

async function loadTradesHistory() {
  loadingTradesHistory.value = true
  try {
    const params = { limit: 100 }
    if (tradesFilter.value.symbol) params.symbol_filter = tradesFilter.value.symbol
    if (tradesFilter.value.type) params.type_filter = tradesFilter.value.type
    const res = await api.getTradesHistory(params)
    historyTrades.value = res.trades || []
  } catch { historyTrades.value = [] }
  finally { loadingTradesHistory.value = false }
}

async function purgeSessions() {
  try {
    await api.purgeLiveSessions(purgeDays.value)
    showPurgeConfirm.value = false
    await loadSessions()
  } catch (e) { console.error(e) }
}

// Tab watcher
watch(mainTab, (tab) => {
  if (tab === 'Overview') startOverviewPolling()
  else stopOverviewPolling()
  if (tab === 'Orders History' && historyOrders.value.length === 0) loadOrdersHistory()
  if (tab === 'Trades History' && historyTrades.value.length === 0) loadTradesHistory()
})

watch(activeView, v => { if (!v) stopPolling() })

onMounted(async () => {
  try {
    const [bRes, sRes, iRes, pRes] = await Promise.all([
      api.getConnectedBrokers(),
      api.getStrategies().catch(() => ({ data: [] })),
      api.getInstruments().catch(() => ({ data: [] })),
      api.getRegisteredPipelines().catch(() => []),
    ])
    brokers.value = bRes.data || []; strategies.value = sRes.data || sRes.strategies || []
    instruments.value = iRes.data || []
    availablePipelines.value = Array.isArray(pRes) ? pRes : (pRes.pipelines || pRes.data || [])
    form.value.exchange = defaultBrokerId(brokers.value)
    if (strategies.value.length > 0) form.value.strategy = strategies.value[0].name
    if (instruments.value.length > 0) {
      const match = instruments.value.find(i => i.symbol === form.value.symbol)
      if (!match) form.value.symbol = instruments.value[0].symbol
    }
  } catch {}
  await loadSessions()
})
onUnmounted(() => { stopPolling(); stopOverviewPolling() })
</script>
