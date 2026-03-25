<template>
  <div>
    <!-- Workspace Tabs -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold">Optimization</h1>
      <div class="flex items-center gap-1 p-1 bg-surface-800 rounded-lg">
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

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- Left: Config Panel -->
      <div class="lg:col-span-1 space-y-4" v-show="!running || showConfig">
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Configuration</h2>

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
              <select v-if="strategies.length" v-model="form.strategy" class="select">
                <option v-for="s in strategies" :key="s" :value="s">{{ s }}</option>
              </select>
              <input v-else v-model="form.strategy" class="input" placeholder="ForexMA" />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Training Start</label>
                <input v-model="form.trainingStartDate" type="date" class="input" />
              </div>
              <div>
                <label class="label">Training End</label>
                <input v-model="form.trainingFinishDate" type="date" class="input" />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Testing Start</label>
                <input v-model="form.testingStartDate" type="date" class="input" />
              </div>
              <div>
                <label class="label">Testing End</label>
                <input v-model="form.testingFinishDate" type="date" class="input" />
              </div>
            </div>

            <div>
              <label class="label">Starting Balance</label>
              <input v-model.number="form.balance" type="number" class="input" />
            </div>

            <div>
              <label class="label">Objective Function</label>
              <select v-model="form.objectiveFunction" class="select">
                <option value="sharpe">Sharpe Ratio</option>
                <option value="calmar">Calmar Ratio</option>
                <option value="sortino">Sortino Ratio</option>
                <option value="omega">Omega Ratio</option>
                <option value="serenity">Serenity Index</option>
                <option value="smart sharpe">Smart Sharpe</option>
                <option value="smart sortino">Smart Sortino</option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Warm-up Candles</label>
                <input v-model.number="form.warmUpCandles" type="number" class="input" min="0" />
              </div>
              <div>
                <label class="label">Trials / Param</label>
                <input v-model.number="form.trials" type="number" class="input" min="10" />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Optimal Trades</label>
                <input v-model.number="form.optimalTotal" type="number" class="input" />
              </div>
              <div>
                <label class="label">Best Candidates</label>
                <input v-model.number="form.bestCandidatesCount" type="number" class="input" min="1" max="100" />
              </div>
            </div>

            <div>
              <label class="label">CPU Cores</label>
              <input v-model.number="form.cpuCores" type="number" class="input" :max="maxCpuCores" min="1" />
              <div class="text-xs text-surface-500 mt-1">Available: {{ maxCpuCores }}</div>
            </div>
<!-- for future use when we add fastMode option in backend -->
<!--            <div class="pt-2">-->
<!--              <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">-->
<!--                <input v-model="form.fastMode" type="checkbox" class="rounded bg-surface-700 border-surface-500" />-->
<!--                Fast Mode-->
<!--              </label>-->
<!--            </div>-->

            <div v-if="!dataRange && form.exchange" class="p-2 bg-amber-500/10 rounded text-xs text-amber-400">
              No candle data found for {{ form.exchange }} / {{ form.symbol }}.
              <router-link to="/import" class="underline">Import data first</router-link>.
            </div>

            <button @click="startOptimization" class="btn-primary w-full mt-2" :disabled="running">
              <span v-if="running" class="flex items-center justify-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Optimizing...
              </span>
              <span v-else>Start Optimization</span>
            </button>
            <button v-if="running" @click="cancelOptimization" class="btn-secondary w-full text-sm">
              Cancel
            </button>
          </div>
        </div>
      </div>

      <!-- Center: Results Panel -->
      <div :class="running && !showConfig ? 'lg:col-span-3' : 'lg:col-span-2'" class="space-y-4">
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
            <button @click="error = ''; errorTrace = ''" class="ml-auto text-surface-500 text-xs">Dismiss</button>
          </div>
          <p class="text-red-400 text-sm">{{ error }}</p>
          <pre v-if="errorTrace" class="text-xs text-red-300/70 mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap">{{ errorTrace }}</pre>
        </div>

        <!-- Alert message -->
        <div v-if="alertMessage" class="card" :class="alertType === 'success' ? 'border-green-500/30' : 'border-amber-500/30'">
          <p :class="alertType === 'success' ? 'text-green-400' : 'text-amber-400'" class="text-sm">{{ alertMessage }}</p>
        </div>

        <!-- Objective Progress Chart -->
        <div v-if="allCurveData.length > 0" class="card">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-surface-300">Objective Progress</h2>
            <div class="flex items-center gap-2">
              <div class="flex items-center gap-3 text-[10px] mr-4">
                <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-blue-400 inline-block"></span> Training</span>
                <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-red-400 inline-block"></span> Testing</span>
              </div>
              <label class="text-xs text-surface-500">Metric:</label>
              <select v-model="chartMetric" class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300">
                <option v-for="m in chartMetricOptions" :key="m.value" :value="m.value">{{ m.label }}</option>
              </select>
            </div>
          </div>
          <div class="relative h-56 select-none">
            <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="w-full h-full" preserveAspectRatio="none">
              <!-- Grid lines -->
              <line v-for="i in 5" :key="'grid-' + i"
                :x1="chartPad.left" :x2="chartWidth - chartPad.right"
                :y1="chartPad.top + (i - 1) * ((chartHeight - chartPad.top - chartPad.bottom) / 4)"
                :y2="chartPad.top + (i - 1) * ((chartHeight - chartPad.top - chartPad.bottom) / 4)"
                stroke="#333" stroke-width="0.5" stroke-dasharray="4,4" />
              <!-- Training line -->
              <polyline :points="trainingLinePath" fill="none" stroke="#60a5fa" stroke-width="1.5" />
              <!-- Testing line -->
              <polyline :points="testingLinePath" fill="none" stroke="#f87171" stroke-width="1.5" />
            </svg>
            <!-- Y-axis labels -->
            <div class="absolute top-0 right-0 h-full flex flex-col justify-between text-[10px] text-surface-500 font-mono pr-1 py-2">
              <span>{{ chartYMax.toFixed(2) }}</span>
              <span>{{ ((chartYMax + chartYMin) / 2).toFixed(2) }}</span>
              <span>{{ chartYMin.toFixed(2) }}</span>
            </div>
            <!-- X-axis labels -->
            <div class="absolute bottom-0 left-0 w-full flex justify-between text-[10px] text-surface-500 font-mono px-1">
              <span>{{ allCurveData[0]?.trial || 1 }}</span>
              <span>{{ allCurveData[allCurveData.length - 1]?.trial || '' }}</span>
            </div>
          </div>
        </div>

        <!-- Best Trials Table -->
        <div v-if="bestCandidates.length" class="card">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-surface-300">Best Trials</h2>
            <span class="text-xs text-surface-500">Showing {{ bestCandidates.length }} trials sorted by fitness score</span>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-surface-700">
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Rank</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Trial</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Training/Testing {{ objectiveFnLabel }}</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Fitness</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Actions</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Select</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(c, idx) in bestCandidates" :key="idx"
                  class="border-b border-surface-800 hover:bg-surface-800/50 cursor-pointer"
                  :class="{ 'bg-surface-800/30': selectedCandidate === c }">
                  <td class="py-2 px-2 text-surface-300 font-mono">{{ c.rank || `#${idx + 1}` }}</td>
                  <td class="py-2 px-2 text-surface-400">{{ c.trial }}</td>
                  <td class="py-2 px-2 text-surface-400 font-mono">{{ c.objective_metric || formatObjMetric(c) }}</td>
                  <td class="py-2 px-2 font-mono" :class="c.fitness > 0 ? 'text-green-400' : 'text-red-400'">
                    {{ typeof c.fitness === 'number' ? c.fitness.toFixed(4) : c.fitness }}
                  </td>
                  <td class="py-2 px-2">
                    <div class="flex items-center gap-2">
                      <button @click.stop="openCandidateModal(c)" class="text-brand-400 hover:text-brand-300" title="View details">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                      </button>
                      <button @click.stop="copyDna(c.dna)" class="text-brand-400 hover:text-brand-300" title="Copy DNA">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                      </button>
                    </div>
                  </td>
                  <td class="py-2 px-2">
                    <input type="radio" :checked="selectedCandidate === c" @click.stop="selectedCandidate = selectedCandidate === c ? null : c"
                      class="rounded-full bg-surface-700 border-surface-500" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Recent Sessions / History -->
        <div class="card">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-surface-300">Optimization History</h2>
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
          <div v-if="sessions.length || sessionsStatusFilter !== 'all'" class="flex items-center gap-3 mb-3">
            <input v-model="sessionsSearch" placeholder="Search by title..." class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300 flex-1" />
            <select v-model="sessionsStatusFilter" class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300">
              <option value="all">All Statuses</option>
              <option value="finished">Finished</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
              <option value="terminated">Terminated</option>
            </select>
          </div>

          <div v-if="loadingSessions" class="text-surface-500 text-sm">Loading...</div>

          <div v-else-if="sessions.length === 0" class="text-surface-500 text-sm">
            No optimization sessions yet. Run an optimization to see results here.
          </div>

          <div v-else class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-surface-700">
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Strategy</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Progress</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Status</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Best Score</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Date</th>
                  <th class="text-left py-2 px-2 text-surface-500 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in filteredSessions" :key="s.id"
                  class="border-b border-surface-800 hover:bg-surface-800/50 cursor-pointer"
                  :class="{ 'bg-surface-800/30': selectedSession?.id === s.id }"
                  @click="viewSession(s)">
                  <td class="py-2 px-2">
                    <div class="text-surface-200">{{ sessionStrategy(s) }}</div>
                    <div class="text-surface-500 text-[10px]">{{ sessionExchange(s) }}</div>
                  </td>
                  <td class="py-2 px-2 text-surface-400 font-mono">
                    {{ s.completed_trials || 0 }} / {{ s.total_trials || 0 }}
                    <div class="text-[10px] text-surface-500">trials</div>
                  </td>
                  <td class="py-2 px-2">
                    <span class="text-xs px-2 py-0.5 rounded-full font-medium" :class="statusBadgeClass(s.status)">{{ s.status }}</span>
                  </td>
                  <td class="py-2 px-2 font-mono" :class="s.best_score > 0 ? 'text-green-400' : 'text-surface-400'">
                    {{ s.best_score != null ? Number(s.best_score).toFixed(2) : '-' }}
                  </td>
                  <td class="py-2 px-2 text-surface-400">{{ formatDateTime(s.updated_at) }}</td>
                  <td class="py-2 px-2">
                    <div class="flex items-center gap-2">
                      <button @click.stop="viewSession(s)" class="text-brand-400 hover:text-brand-300" title="View">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                      </button>
                      <button v-if="s.status === 'stopped' || s.status === 'terminated'" @click.stop="resumeSession(s)" class="text-green-400 hover:text-green-300" title="Resume">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/></svg>
                      </button>
                      <button @click.stop="removeSession(s)" class="text-red-400 hover:text-red-300" title="Delete">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Right Sidebar: Progress + Info (visible during run or when viewing session) -->
      <div class="lg:col-span-1 space-y-4" v-if="running || selectedSession">
        <!-- Action Buttons -->
        <div class="space-y-2" v-if="running">
          <button @click="cancelOptimization" class="w-full px-4 py-2 text-sm border border-red-500/30 text-red-400 rounded-lg hover:bg-red-500/10 flex items-center justify-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Terminate
          </button>
          <button @click="viewLogs" class="w-full px-4 py-2 text-sm border border-surface-600 text-surface-300 rounded-lg hover:bg-surface-800 flex items-center justify-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            Logs
          </button>
          <button @click="showConfig = !showConfig" class="w-full px-4 py-2 text-sm border border-surface-600 text-surface-300 rounded-lg hover:bg-surface-800 flex items-center justify-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            {{ showConfig ? 'Hide Config' : 'Show Config' }}
          </button>
        </div>

        <!-- Buttons for selected session -->
        <div class="space-y-2" v-if="selectedSession && !running">
          <button @click="startNewSession" class="w-full px-4 py-2 text-sm bg-brand-500 text-white rounded-lg hover:bg-brand-600 flex items-center justify-center gap-2">
            New Session
          </button>
          <button @click="viewSessionLogs(selectedSession)" class="w-full px-4 py-2 text-sm border border-surface-600 text-surface-300 rounded-lg hover:bg-surface-800 flex items-center justify-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            Logs
          </button>
          <button v-if="selectedSession.status === 'stopped' || selectedSession.status === 'terminated'"
            @click="resumeSession(selectedSession)" class="w-full px-4 py-2 text-sm border border-green-500/30 text-green-400 rounded-lg hover:bg-green-500/10 flex items-center justify-center gap-2">
            Resume
          </button>
          <button @click="closeTab(selectedSession.id)" class="w-full px-4 py-2 text-sm border border-surface-600 text-surface-300 rounded-lg hover:bg-surface-800 flex items-center justify-center gap-2">
            Close
          </button>
        </div>

        <!-- Circular Progress -->
        <div v-if="running" class="flex justify-center py-4">
          <div class="relative w-32 h-32">
            <svg class="w-32 h-32 transform -rotate-90" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="52" stroke="#374151" stroke-width="8" fill="none" />
              <circle cx="60" cy="60" r="52" stroke="#8b5cf6" stroke-width="8" fill="none"
                :stroke-dasharray="2 * Math.PI * 52"
                :stroke-dashoffset="2 * Math.PI * 52 * (1 - progress.current / 100)"
                stroke-linecap="round" class="transition-all duration-500" />
            </svg>
            <div class="absolute inset-0 flex items-center justify-center">
              <span class="text-2xl font-bold text-surface-200">{{ Math.round(progress.current) }}%</span>
            </div>
          </div>
        </div>

        <!-- Info Panel -->
        <div class="card" v-if="running && generalInfo">
          <h3 class="text-xs font-semibold text-surface-400 mb-3 border-b border-surface-700 pb-2">Info</h3>
          <div class="space-y-2 text-xs">
            <div class="flex justify-between">
              <span class="text-surface-500">Started at</span>
              <span class="text-surface-200">{{ generalInfo.started_at }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Progress</span>
              <span class="text-surface-200 font-mono">{{ generalInfo.trial }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Objective Function</span>
              <span class="text-surface-200">{{ generalInfo.objective_function }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Exchange Type</span>
              <span class="text-surface-200">{{ generalInfo.exchange_type }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Leverage Mode</span>
              <span class="text-surface-200">{{ generalInfo.leverage_mode }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Leverage</span>
              <span class="text-surface-200">{{ generalInfo.leverage }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">CPU Cores</span>
              <span class="text-surface-200">{{ generalInfo.cpu_cores }}</span>
            </div>
            <div v-if="progress.eta > 0" class="flex justify-between">
              <span class="text-surface-500">ETA</span>
              <span class="text-surface-200">{{ formatEta(progress.eta) }}</span>
            </div>
          </div>
        </div>

        <!-- Session Info Panel -->
        <div class="card" v-if="selectedSession && !running">
          <h3 class="text-xs font-semibold text-surface-400 mb-3 border-b border-surface-700 pb-2">Info</h3>
          <div class="space-y-2 text-xs">
            <div class="flex justify-between">
              <span class="text-surface-500">Status</span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-medium" :class="statusBadgeClass(selectedSession.status)">{{ selectedSession.status }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Progress</span>
              <span class="text-surface-200 font-mono">{{ selectedSession.completed_trials }}/{{ selectedSession.total_trials }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Best Score</span>
              <span class="font-mono" :class="selectedSession.best_score > 0 ? 'text-green-400' : 'text-surface-300'">
                {{ selectedSession.best_score != null ? Number(selectedSession.best_score).toFixed(4) : 'N/A' }}
              </span>
            </div>
            <div v-if="selectedSession.state" class="flex justify-between">
              <span class="text-surface-500">Strategy</span>
              <span class="text-surface-200">{{ selectedSession.state.strategy || '-' }}</span>
            </div>
            <div v-if="selectedSession.state" class="flex justify-between">
              <span class="text-surface-500">Exchange</span>
              <span class="text-surface-200">{{ selectedSession.state.exchange || '-' }}</span>
            </div>
            <div v-if="selectedSession.state" class="flex justify-between">
              <span class="text-surface-500">Symbol</span>
              <span class="text-surface-200">{{ selectedSession.state.symbol || '-' }}</span>
            </div>
            <div v-if="selectedSession.state" class="flex justify-between">
              <span class="text-surface-500">Objective</span>
              <span class="text-surface-200">{{ selectedSession.state.objectiveFunction || '-' }}</span>
            </div>
            <div v-if="selectedSession.state" class="flex justify-between">
              <span class="text-surface-500">Training</span>
              <span class="text-surface-200 text-[10px]">{{ selectedSession.state.trainingStartDate }} - {{ selectedSession.state.trainingFinishDate }}</span>
            </div>
            <div v-if="selectedSession.state" class="flex justify-between">
              <span class="text-surface-500">Testing</span>
              <span class="text-surface-200 text-[10px]">{{ selectedSession.state.testingStartDate }} - {{ selectedSession.state.testingFinishDate }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-surface-500">Created</span>
              <span class="text-surface-200">{{ formatDateTime(selectedSession.created_at) }}</span>
            </div>
          </div>

          <!-- Session exception -->
          <div v-if="selectedSession.exception" class="mt-3 p-3 bg-red-500/10 rounded">
            <div class="text-red-400 text-xs font-semibold mb-1">Exception</div>
            <p class="text-red-300 text-xs">{{ selectedSession.exception }}</p>
            <pre v-if="selectedSession.traceback" class="text-[10px] text-red-300/70 mt-1 max-h-[150px] overflow-auto whitespace-pre-wrap">{{ selectedSession.traceback }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Candidate Info Modal -->
    <div v-if="candidateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="candidateModal = null">
      <div class="bg-surface-900 border border-surface-700 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[85vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-lg font-semibold text-surface-200">Candidate Info</h2>
            <button @click="candidateModal = null" class="text-surface-500 hover:text-surface-200">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>

          <!-- Top info -->
          <div class="grid grid-cols-4 gap-4 mb-6">
            <div class="text-center">
              <div class="text-xs text-surface-500 mb-1">Rank</div>
              <div class="text-lg font-bold text-surface-200">{{ candidateModal.rank || '#1' }}</div>
            </div>
            <div class="text-center">
              <div class="text-xs text-surface-500 mb-1">Trial</div>
              <div class="text-lg font-bold text-surface-200">{{ candidateModal.trial }}</div>
            </div>
            <div class="text-center">
              <div class="text-xs text-surface-500 mb-1">Fitness</div>
              <div class="text-lg font-bold" :class="candidateModal.fitness > 0 ? 'text-green-400' : 'text-red-400'">
                {{ typeof candidateModal.fitness === 'number' ? candidateModal.fitness.toFixed(4) : candidateModal.fitness }}
              </div>
            </div>
            <div class="text-center">
              <div class="text-xs text-surface-500 mb-1">DNA</div>
              <button @click="copyDna(candidateModal.dna)" class="px-3 py-1 bg-brand-500 text-white rounded text-xs hover:bg-brand-600">Copy DNA</button>
            </div>
          </div>

          <!-- Parameters -->
          <h3 class="text-sm font-semibold text-surface-300 mb-3">Parameters</h3>
          <div class="overflow-x-auto mb-6">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-surface-700">
                  <th class="text-left py-2 px-3 text-surface-500 font-medium">Parameter</th>
                  <th class="text-right py-2 px-3 text-surface-500 font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(val, key) in candidateModal.params" :key="key" class="border-b border-surface-800">
                  <td class="py-2 px-3 text-surface-400">{{ key }}</td>
                  <td class="py-2 px-3 text-surface-200 font-mono text-right">{{ formatParamValue(val) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Metrics Comparison -->
          <h3 class="text-sm font-semibold text-surface-300 mb-3">Metrics Comparison</h3>
          <div class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-surface-700">
                  <th class="text-left py-2 px-3 text-surface-500 font-medium">Metric</th>
                  <th class="text-right py-2 px-3 text-surface-500 font-medium">Training</th>
                  <th class="text-right py-2 px-3 text-surface-500 font-medium">Testing</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="mk in metricsComparisonKeys" :key="mk.key" class="border-b border-surface-800">
                  <td class="py-2 px-3 text-surface-400">{{ mk.label }}</td>
                  <td class="py-2 px-3 text-surface-200 font-mono text-right">
                    {{ formatMetricVal(candidateModal.training_metrics?.[mk.key], mk) }}
                  </td>
                  <td class="py-2 px-3 text-surface-200 font-mono text-right">
                    {{ formatMetricVal(candidateModal.testing_metrics?.[mk.key], mk) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Logs Modal -->
    <div v-if="showLogsModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showLogsModal = false">
      <div class="bg-surface-900 border border-surface-700 rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[85vh] flex flex-col">
        <div class="flex items-center justify-between p-4 border-b border-surface-700">
          <h2 class="text-sm font-semibold text-surface-200">Optimization Logs</h2>
          <button @click="showLogsModal = false" class="text-surface-500 hover:text-surface-200">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-4">
          <pre v-if="logsContent" class="text-xs text-surface-300 font-mono whitespace-pre-wrap">{{ logsContent }}</pre>
          <div v-else class="text-surface-500 text-sm">{{ logsLoading ? 'Loading logs...' : 'No logs available.' }}</div>
        </div>
      </div>
    </div>

    <!-- Session Objective Curve (when viewing a finished session) -->
    <div v-if="selectedSession && sessionCurveData.length > 0 && !running" class="mt-4">
      <div class="card">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold text-surface-300">Session Objective Progress</h2>
          <div class="flex items-center gap-2">
            <div class="flex items-center gap-3 text-[10px] mr-4">
              <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-blue-400 inline-block"></span> Training</span>
              <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-red-400 inline-block"></span> Testing</span>
            </div>
            <select v-model="chartMetric" class="text-xs bg-surface-800 border border-surface-700 rounded px-2 py-1 text-surface-300">
              <option v-for="m in chartMetricOptions" :key="m.value" :value="m.value">{{ m.label }}</option>
            </select>
          </div>
        </div>
        <div class="relative h-56 select-none">
          <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="w-full h-full" preserveAspectRatio="none">
            <line v-for="i in 5" :key="'sgrid-' + i"
              :x1="chartPad.left" :x2="chartWidth - chartPad.right"
              :y1="chartPad.top + (i - 1) * ((chartHeight - chartPad.top - chartPad.bottom) / 4)"
              :y2="chartPad.top + (i - 1) * ((chartHeight - chartPad.top - chartPad.bottom) / 4)"
              stroke="#333" stroke-width="0.5" stroke-dasharray="4,4" />
            <polyline :points="sessionTrainingLinePath" fill="none" stroke="#60a5fa" stroke-width="1.5" />
            <polyline :points="sessionTestingLinePath" fill="none" stroke="#f87171" stroke-width="1.5" />
          </svg>
          <div class="absolute top-0 right-0 h-full flex flex-col justify-between text-[10px] text-surface-500 font-mono pr-1 py-2">
            <span>{{ sessionChartYMax.toFixed(2) }}</span>
            <span>{{ ((sessionChartYMax + sessionChartYMin) / 2).toFixed(2) }}</span>
            <span>{{ sessionChartYMin.toFixed(2) }}</span>
          </div>
          <div class="absolute bottom-0 left-0 w-full flex justify-between text-[10px] text-surface-500 font-mono px-1">
            <span>{{ sessionCurveData[0]?.trial || 1 }}</span>
            <span>{{ sessionCurveData[sessionCurveData.length - 1]?.trial || '' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Session Best Candidates (when viewing a finished session) -->
    <div v-if="selectedSession && selectedSession.best_candidates && selectedSession.best_candidates.length && !running" class="mt-4">
      <div class="card">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold text-surface-300">Session Best Trials</h2>
          <span class="text-xs text-surface-500">{{ selectedSession.best_candidates.length }} candidates</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-surface-700">
                <th class="text-left py-2 px-2 text-surface-500 font-medium">Rank</th>
                <th class="text-left py-2 px-2 text-surface-500 font-medium">Trial</th>
                <th class="text-left py-2 px-2 text-surface-500 font-medium">Training/Testing</th>
                <th class="text-left py-2 px-2 text-surface-500 font-medium">Fitness</th>
                <th class="text-left py-2 px-2 text-surface-500 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, idx) in selectedSession.best_candidates" :key="idx"
                class="border-b border-surface-800 hover:bg-surface-800/50 cursor-pointer">
                <td class="py-2 px-2 text-surface-300 font-mono">{{ c.rank }}</td>
                <td class="py-2 px-2 text-surface-400">{{ c.trial }}</td>
                <td class="py-2 px-2 text-surface-400 font-mono">{{ c.objective_metric || '-' }}</td>
                <td class="py-2 px-2 font-mono" :class="c.fitness > 0 ? 'text-green-400' : 'text-red-400'">
                  {{ typeof c.fitness === 'number' ? c.fitness.toFixed(4) : c.fitness }}
                </td>
                <td class="py-2 px-2">
                  <div class="flex items-center gap-2">
                    <button @click.stop="openCandidateModal(c)" class="text-brand-400 hover:text-brand-300" title="View details">
                      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    </button>
                    <button @click.stop="copyDna(c.dna)" class="text-brand-400 hover:text-brand-300" title="Copy DNA">
                      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
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
import { ref, computed, onMounted } from 'vue'
import { api, defaultBrokerId } from '../api'
import { useWebSocket } from '../useWebSocket'
import ProgressBar from '../components/ProgressBar.vue'

const brokers = ref([])
const strategies = ref([])
const sessions = ref([])
const selectedSession = ref(null)
const openTabs = ref([])
const tabCache = ref({})

// Workspace tabs
const workspaceTabs = ref([{ id: 'ws-1', label: 'Optimization 1', running: false, hasResults: false }])
const activeWorkspaceId = ref('ws-1')
const workspaceCache = ref({})
let wsCounter = 1

const selectedCandidate = ref(null)
const candidateModal = ref(null)
const running = ref(false)
const showConfig = ref(false)
const loadingSessions = ref(false)
const error = ref('')
const errorTrace = ref('')
const alertMessage = ref('')
const alertType = ref('success')
const currentTaskId = ref(null)
const maxCpuCores = ref(12)
const showLogsModal = ref(false)
const logsContent = ref('')
const logsLoading = ref(false)
const showPurgeConfirm = ref(false)
const purgeDays = ref(30)
const sessionsSearch = ref('')
const sessionsStatusFilter = ref('all')

const existingCandles = ref([])

// WebSocket-driven state
const progress = ref({ current: 0, eta: 0 })
const generalInfo = ref(null)
const bestCandidates = ref([])
const allCurveData = ref([])
const chartMetric = ref('sharpe_ratio')

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

const chartMetricOptions = [
  { value: 'sharpe_ratio', label: 'SHARPE RATIO' },
  { value: 'calmar_ratio', label: 'CALMAR RATIO' },
  { value: 'sortino_ratio', label: 'SORTINO RATIO' },
  { value: 'omega_ratio', label: 'OMEGA RATIO' },
  { value: 'serenity_index', label: 'SERENITY INDEX' },
  { value: 'net_profit_percentage', label: 'NET PROFIT %' },
  { value: 'win_rate', label: 'WIN RATE' },
  { value: 'total', label: 'TOTAL TRADES' },
  { value: 'max_drawdown', label: 'MAX DRAWDOWN' },
  { value: 'annual_return', label: 'ANNUAL RETURN' },
  { value: 'expectancy', label: 'EXPECTANCY' },
  { value: 'average_win', label: 'AVERAGE WIN' },
  { value: 'average_loss', label: 'AVERAGE LOSS' },
  { value: 'gross_profit', label: 'GROSS PROFIT' },
  { value: 'gross_loss', label: 'GROSS LOSS' },
  { value: 'open_pl', label: 'OPEN PL' },
  { value: 'smart_sharpe', label: 'SMART SHARPE' },
  { value: 'smart_sortino', label: 'SMART SORTINO' },
]

const metricsComparisonKeys = [
  { key: 'total', label: 'Total Closed Trades' },
  { key: 'net_profit_percentage', label: 'Total Net Profit', suffix: '%' },
  { key: 'starting_balance', label: 'Starting Balance', prefix: '$' },
  { key: 'finishing_balance', label: 'Finishing Balance', prefix: '$' },
  { key: 'open_pl', label: 'Open PL', prefix: '$' },
  { key: 'total_paid_fees', label: 'Total Paid Fees', prefix: '$' },
  { key: 'max_drawdown', label: 'Max Drawdown', suffix: '%' },
  { key: 'annual_return', label: 'Annual Return', suffix: '%' },
  { key: 'win_rate', label: 'Win Rate', suffix: '%' },
  { key: 'sharpe_ratio', label: 'Sharpe Ratio' },
  { key: 'calmar_ratio', label: 'Calmar Ratio' },
  { key: 'sortino_ratio', label: 'Sortino Ratio' },
  { key: 'omega_ratio', label: 'Omega Ratio' },
  { key: 'serenity_index', label: 'Serenity Index' },
  { key: 'smart_sharpe', label: 'Smart Sharpe' },
  { key: 'smart_sortino', label: 'Smart Sortino' },
  { key: 'total_winning_trades', label: 'Total Winning Trades' },
  { key: 'total_losing_trades', label: 'Total Losing Trades' },
  { key: 'average_win', label: 'Average Win', prefix: '$' },
  { key: 'average_loss', label: 'Average Loss', prefix: '$' },
  { key: 'expectancy', label: 'Expectancy', prefix: '$' },
  { key: 'average_holding_period', label: 'Average Holding Period' },
  { key: 'winning_streak', label: 'Winning Streak' },
  { key: 'losing_streak', label: 'Losing Streak' },
  { key: 'gross_profit', label: 'Gross Profit', prefix: '$' },
  { key: 'gross_loss', label: 'Gross Loss', prefix: '$' },
  { key: 'longs_count', label: 'Longs Count' },
  { key: 'shorts_count', label: 'Shorts Count' },
]

const objectiveFnLabel = computed(() => {
  const map = {
    'sharpe': 'sharpe',
    'calmar': 'calmar',
    'sortino': 'sortino',
    'omega': 'omega',
    'serenity': 'serenity',
    'smart sharpe': 'smart sharpe',
    'smart sortino': 'smart sortino',
  }
  return map[form.value.objectiveFunction] || form.value.objectiveFunction
})

const form = ref({
  exchange: '',
  symbol: 'EUR-USD',
  timeframe: '1h',
  strategy: 'ForexMA',
  trainingStartDate: '2024-01-01',
  trainingFinishDate: '2024-06-01',
  testingStartDate: '2024-06-01',
  testingFinishDate: '2024-09-01',
  balance: 10000,
  objectiveFunction: 'sharpe',
  warmUpCandles: 240,
  trials: 200,
  optimalTotal: 100,
  bestCandidatesCount: 20,
  cpuCores: 6,
  fastMode: true,
})

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

// Chart computation
const chartWidth = 800
const chartHeight = 200
const chartPad = { top: 10, right: 50, bottom: 20, left: 10 }

function extractChartValues(data) {
  const trainVals = []
  const testVals = []
  for (const pt of data) {
    const tv = pt.training?.[chartMetric.value]
    const sv = pt.testing?.[chartMetric.value]
    trainVals.push(typeof tv === 'number' && isFinite(tv) ? tv : null)
    testVals.push(typeof sv === 'number' && isFinite(sv) ? sv : null)
  }
  return { trainVals, testVals }
}

function computeLinePath(values, data, yMin, yMax) {
  const n = data.length
  if (n === 0) return ''
  const xRange = chartWidth - chartPad.left - chartPad.right
  const yRange = chartHeight - chartPad.top - chartPad.bottom
  const points = []
  for (let i = 0; i < n; i++) {
    const v = values[i]
    if (v === null) continue
    const x = chartPad.left + (i / Math.max(n - 1, 1)) * xRange
    const y = yMax === yMin
      ? chartPad.top + yRange / 2
      : chartPad.top + yRange - ((v - yMin) / (yMax - yMin)) * yRange
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return points.join(' ')
}

function getYBounds(trainVals, testVals) {
  const all = [...trainVals, ...testVals].filter(v => v !== null)
  if (all.length === 0) return { yMin: 0, yMax: 1 }
  let yMin = Math.min(...all)
  let yMax = Math.max(...all)
  if (yMin === yMax) { yMin -= 1; yMax += 1 }
  const pad = (yMax - yMin) * 0.05
  return { yMin: yMin - pad, yMax: yMax + pad }
}

// Live chart paths
const trainingLinePath = computed(() => {
  const { trainVals, testVals } = extractChartValues(allCurveData.value)
  const { yMin, yMax } = getYBounds(trainVals, testVals)
  return computeLinePath(trainVals, allCurveData.value, yMin, yMax)
})
const testingLinePath = computed(() => {
  const { trainVals, testVals } = extractChartValues(allCurveData.value)
  const { yMin, yMax } = getYBounds(trainVals, testVals)
  return computeLinePath(testVals, allCurveData.value, yMin, yMax)
})
const chartYMax = computed(() => {
  const { trainVals, testVals } = extractChartValues(allCurveData.value)
  return getYBounds(trainVals, testVals).yMax
})
const chartYMin = computed(() => {
  const { trainVals, testVals } = extractChartValues(allCurveData.value)
  return getYBounds(trainVals, testVals).yMin
})

// Session chart paths
const sessionCurveData = computed(() => {
  if (!selectedSession.value?.objective_curve) return []
  return selectedSession.value.objective_curve
})
const sessionTrainingLinePath = computed(() => {
  const data = sessionCurveData.value
  const { trainVals, testVals } = extractChartValues(data)
  const { yMin, yMax } = getYBounds(trainVals, testVals)
  return computeLinePath(trainVals, data, yMin, yMax)
})
const sessionTestingLinePath = computed(() => {
  const data = sessionCurveData.value
  const { trainVals, testVals } = extractChartValues(data)
  const { yMin, yMax } = getYBounds(trainVals, testVals)
  return computeLinePath(testVals, data, yMin, yMax)
})
const sessionChartYMax = computed(() => {
  const data = sessionCurveData.value
  const { trainVals, testVals } = extractChartValues(data)
  return getYBounds(trainVals, testVals).yMax
})
const sessionChartYMin = computed(() => {
  const data = sessionCurveData.value
  const { trainVals, testVals } = extractChartValues(data)
  return getYBounds(trainVals, testVals).yMin
})

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
    form.value.trainingStartDate = range.start
    const start = new Date(range.start)
    const end = new Date(range.end)
    const totalDays = (end - start) / (1000 * 60 * 60 * 24)
    const trainDays = Math.floor(totalDays * 0.7)
    const trainEnd = new Date(start.getTime() + trainDays * 24 * 60 * 60 * 1000)
    form.value.trainingFinishDate = trainEnd.toISOString().split('T')[0]
    form.value.testingStartDate = trainEnd.toISOString().split('T')[0]
    form.value.testingFinishDate = range.end
  }
}

// ── Workspace management ──
const _wsRefs = {
  form, running, showConfig, error, errorTrace, alertMessage, alertType, currentTaskId,
  progress, generalInfo, bestCandidates, allCurveData, chartMetric,
  selectedCandidate, candidateModal,
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
      exchange: form.value.exchange, symbol: 'EUR-USD', timeframe: '1h',
      strategy: strategies.value[0] || 'ForexMA',
      trainingStartDate: '2024-01-01', trainingFinishDate: '2024-06-01',
      testingStartDate: '2024-06-01', testingFinishDate: '2024-09-01',
      balance: 10000, objectiveFunction: 'sharpe', warmUpCandles: 240,
      trials: 200, optimalTotal: 100, bestCandidatesCount: 20,
      cpuCores: Math.min(6, maxCpuCores.value), fastMode: true,
    },
    running: false, showConfig: false, error: '', errorTrace: '',
    alertMessage: '', alertType: 'success', currentTaskId: null,
    progress: { current: 0, eta: 0 }, generalInfo: null,
    bestCandidates: [], allCurveData: [], chartMetric: 'sharpe_ratio',
    selectedCandidate: null, candidateModal: null,
    selectedSession: null, openTabs: [], tabCache: {},
  }
}

function addWorkspace() {
  if (running.value) return
  wsCounter++
  const id = `ws-${wsCounter}`
  workspaceCache.value[activeWorkspaceId.value] = _snapshotWs()
  workspaceTabs.value.push({ id, label: `Optimization ${wsCounter}`, running: false, hasResults: false })
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
  const { event, id, data } = msg
  // Note: msg.id is os.getpid() (integer), not the session UUID.
  // The 'optimize.' event prefix already namespaces messages, so no id filtering needed.

  if (event === 'optimize.progressbar') {
    progress.value = {
      current: data?.current || 0,
      eta: data?.estimated_remaining_seconds || 0,
    }
  } else if (event === 'optimize.general_info') {
    generalInfo.value = data
  } else if (event === 'optimize.best_candidates') {
    bestCandidates.value = data || []
  } else if (event === 'optimize.objective_curve') {
    // Backend sends batches - APPEND to existing data, deduplicating by trial number
    if (Array.isArray(data) && data.length > 0) {
      const existingTrials = new Set(allCurveData.value.map(p => p.trial))
      const newPoints = data.filter(p => !existingTrials.has(p.trial))
      if (newPoints.length > 0) {
        allCurveData.value = [...allCurveData.value, ...newPoints].sort((a, b) => a.trial - b.trial)
      }
    }
  } else if (event === 'optimize.alert') {
    alertMessage.value = data?.message || ''
    alertType.value = data?.type || 'success'
    if (data?.type === 'success') {
      running.value = false
      showConfig.value = false
      progress.value = { current: 100, eta: 0 }
      _updateActiveWsTab({ running: false, hasResults: true })
      setTimeout(loadSessions, 1000)
    }
  } else if (event === 'optimize.exception') {
    error.value = data?.error || 'Optimization failed'
    errorTrace.value = data?.traceback || ''
    running.value = false
    showConfig.value = false
    progress.value = { current: 0, eta: 0 }
    _updateActiveWsTab({ running: false })
  } else if (event === 'optimize.termination') {
    running.value = false
    showConfig.value = false
    alertMessage.value = 'Optimization was terminated.'
    alertType.value = 'warning'
    progress.value = { current: 0, eta: 0 }
    _updateActiveWsTab({ running: false })
  } else if (event === 'optimize.unexpectedTermination') {
    running.value = false
    showConfig.value = false
    error.value = data?.message || 'Optimization terminated unexpectedly'
    progress.value = { current: 0, eta: 0 }
    _updateActiveWsTab({ running: false })
  }
})

function statusBadgeClass(status) {
  if (status === 'finished') return 'bg-green-500/20 text-green-400'
  if (status === 'running') return 'bg-yellow-500/20 text-yellow-400'
  if (status === 'stopped' || status === 'terminated' || status === 'failed') return 'bg-red-500/20 text-red-400'
  if (status === 'paused') return 'bg-amber-500/20 text-amber-400'
  return 'bg-surface-700 text-surface-400'
}

function formatKey(key) {
  return key.replace(/_/g, ' ')
}

function formatMetric(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toLocaleString()
    return val.toFixed(2)
  }
  return val
}

function formatMetricVal(val, mk) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'number') {
    const prefix = mk?.prefix || ''
    const suffix = mk?.suffix || ''
    if (Number.isInteger(val)) return `${prefix}${val.toLocaleString()}${suffix}`
    return `${prefix}${val.toFixed(2)}${suffix}`
  }
  return val
}

function formatPct(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'number') return val.toFixed(2) + '%'
  return val
}

function formatParamValue(val) {
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val
    return val.toFixed(4)
  }
  return val
}

function formatObjMetric(c) {
  const mapping = {
    'sharpe': 'sharpe_ratio',
    'calmar': 'calmar_ratio',
    'sortino': 'sortino_ratio',
    'omega': 'omega_ratio',
    'serenity': 'serenity_index',
    'smart sharpe': 'smart_sharpe',
    'smart sortino': 'smart_sortino',
  }
  const key = mapping[form.value.objectiveFunction] || form.value.objectiveFunction
  const tv = c.training_metrics?.[key]
  const sv = c.testing_metrics?.[key]
  const tvStr = typeof tv === 'number' ? tv.toFixed(2) : 'N/A'
  const svStr = typeof sv === 'number' ? sv.toFixed(2) : 'N/A'
  return `${tvStr} / ${svStr}`
}

function formatDate(d) {
  if (!d) return ''
  try {
    const date = typeof d === 'number' ? new Date(d) : new Date(d)
    return date.toLocaleDateString()
  } catch { return d }
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

function copyDna(dna) {
  if (!dna) return
  navigator.clipboard.writeText(dna).then(() => {
    alertMessage.value = 'DNA copied to clipboard!'
    alertType.value = 'success'
    setTimeout(() => { if (alertMessage.value === 'DNA copied to clipboard!') alertMessage.value = '' }, 2000)
  })
}

function openCandidateModal(c) {
  candidateModal.value = c
}

function sessionStrategy(s) {
  if (s.state?.strategy) return s.state.strategy
  if (s.title) return s.title
  return s.id?.slice(0, 8) || '-'
}

function sessionExchange(s) {
  if (s.state?.exchange) return s.state.exchange
  return ''
}

function startNewSession() {
  selectedSession.value = null
}

function buildState() {
  return {
    exchange: form.value.exchange,
    symbol: form.value.symbol,
    timeframe: form.value.timeframe,
    strategy: form.value.strategy,
    trainingStartDate: form.value.trainingStartDate,
    trainingFinishDate: form.value.trainingFinishDate,
    testingStartDate: form.value.testingStartDate,
    testingFinishDate: form.value.testingFinishDate,
    balance: form.value.balance,
    objectiveFunction: form.value.objectiveFunction,
    warmUpCandles: form.value.warmUpCandles,
    trials: form.value.trials,
    optimalTotal: form.value.optimalTotal,
    bestCandidatesCount: form.value.bestCandidatesCount,
    cpuCores: form.value.cpuCores,
    fastMode: form.value.fastMode,
  }
}

async function startOptimization() {
  _updateActiveWsTab({ label: `${form.value.strategy} ${form.value.symbol}`, running: true, hasResults: false })
  error.value = ''
  errorTrace.value = ''
  alertMessage.value = ''
  bestCandidates.value = []
  allCurveData.value = []
  generalInfo.value = null
  progress.value = { current: 0, eta: 0 }
  selectedCandidate.value = null
  candidateModal.value = null
  selectedSession.value = null
  running.value = true
  showConfig.value = false

  const id = crypto.randomUUID()
  currentTaskId.value = id

  try {
    await api.runOptimization({
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
        warm_up_candles: form.value.warmUpCandles,
        objective_function: form.value.objectiveFunction,
        trials: form.value.trials,
        best_candidates_count: form.value.bestCandidatesCount,
        logging: { order_submission: true, order_cancellation: true, order_execution: true, position_opened: true, position_increased: true, position_reduced: true, position_closed: true, shorter_period_candles: false, trading_candles: false, balance_update: true },
        exchanges: {
          [form.value.exchange]: {
            name: form.value.exchange,
            type: '',
            fee: 0,
            balance: form.value.balance,
          }
        },
      },
      training_start_date: form.value.trainingStartDate,
      training_finish_date: form.value.trainingFinishDate,
      testing_start_date: form.value.testingStartDate,
      testing_finish_date: form.value.testingFinishDate,
      optimal_total: form.value.optimalTotal,
      fast_mode: form.value.fastMode,
      cpu_cores: form.value.cpuCores,
      state: buildState(),
    })
  } catch (e) {
    error.value = e.message
    running.value = false
  }
}

async function cancelOptimization() {
  if (!currentTaskId.value) return
  try {
    await api.terminateOptimization(currentTaskId.value)
    alertMessage.value = 'Termination requested...'
    alertType.value = 'warning'
  } catch (e) {
    error.value = e.message
  }
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await api.getOptimizationSessions({ limit: 50 })
    sessions.value = res.sessions || []
  } catch {
    sessions.value = []
  } finally {
    loadingSessions.value = false
  }
}

async function viewSession(s) {
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
      const res = await api.getOptimizationSession(s.id)
      selectedSession.value = res.session || s
      tabCache.value[s.id] = selectedSession.value
    } catch {
      selectedSession.value = s
    }
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
    await api.removeOptimizationSession(s.id)
    closeTab(s.id)
    loadSessions()
  } catch (e) {
    error.value = e.message
  }
}

async function resumeSession(s) {
  if (!s.state) {
    error.value = 'Cannot resume: session state is missing'
    return
  }

  error.value = ''
  errorTrace.value = ''
  alertMessage.value = ''
  bestCandidates.value = []
  allCurveData.value = []
  generalInfo.value = null
  progress.value = { current: 0, eta: 0 }
  running.value = true
  showConfig.value = false
  currentTaskId.value = s.id
  selectedSession.value = null

  const st = s.state
  if (st.exchange) form.value.exchange = st.exchange
  if (st.symbol) form.value.symbol = st.symbol
  if (st.timeframe) form.value.timeframe = st.timeframe
  if (st.strategy) form.value.strategy = st.strategy

  try {
    await api.resumeOptimization({
      id: s.id,
      exchange: st.exchange || form.value.exchange,
      routes: [{
        exchange: st.exchange || form.value.exchange,
        symbol: st.symbol || form.value.symbol,
        timeframe: st.timeframe || form.value.timeframe,
        strategy: st.strategy || form.value.strategy,
      }],
      data_routes: [],
      config: {
        warm_up_candles: st.warmUpCandles || form.value.warmUpCandles,
        objective_function: st.objectiveFunction || form.value.objectiveFunction,
        trials: st.trials || form.value.trials,
        best_candidates_count: st.bestCandidatesCount || form.value.bestCandidatesCount,
        logging: { order_submission: true, order_cancellation: true, order_execution: true, position_opened: true, position_increased: true, position_reduced: true, position_closed: true, shorter_period_candles: false, trading_candles: false, balance_update: true },
        exchanges: {
          [st.exchange || form.value.exchange]: {
            name: st.exchange || form.value.exchange,
            type: '',
            fee: 0,
            balance: st.balance || form.value.balance,
          }
        },
      },
      training_start_date: st.trainingStartDate || form.value.trainingStartDate,
      training_finish_date: st.trainingFinishDate || form.value.trainingFinishDate,
      testing_start_date: st.testingStartDate || form.value.testingStartDate,
      testing_finish_date: st.testingFinishDate || form.value.testingFinishDate,
      optimal_total: st.optimalTotal || form.value.optimalTotal,
      fast_mode: st.fastMode !== undefined ? st.fastMode : form.value.fastMode,
      cpu_cores: st.cpuCores || form.value.cpuCores,
      state: st,
    })
  } catch (e) {
    error.value = e.message
    running.value = false
  }
}

async function viewLogs() {
  if (!currentTaskId.value) return
  showLogsModal.value = true
  logsLoading.value = true
  logsContent.value = ''
  try {
    const res = await api.getOptimizationLogs(currentTaskId.value)
    logsContent.value = res.logs || ''
  } catch {
    logsContent.value = ''
  } finally {
    logsLoading.value = false
  }
}

async function viewSessionLogs(s) {
  showLogsModal.value = true
  logsLoading.value = true
  logsContent.value = ''
  try {
    const res = await api.getOptimizationLogs(s.id)
    logsContent.value = res.logs || ''
  } catch {
    logsContent.value = ''
  } finally {
    logsLoading.value = false
  }
}

async function purge() {
  try {
    await api.purgeOptimizationSessions(purgeDays.value)
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
    const res = await api.getRunningOptimizationSession()
    if (res.session_id) {
      running.value = true
      currentTaskId.value = res.session_id
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
    if (strategies.value.length > 0) form.value.strategy = strategies.value[0]
    form.value.cpuCores = Math.max(1, Math.min(form.value.cpuCores, maxCpuCores.value))
  } catch (e) {
    console.error(e)
  }

  await loadExistingCandles()
  onExchangeChange()
  loadSessions()
  checkRunningSession()
})
</script>
