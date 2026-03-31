<template>
  <div class="space-y-6">
    <!-- ═══ HEADER: Pipeline overview badges ═══ -->
    <div v-for="(ps, route) in stats" :key="route">
      <div class="flex items-center gap-2 mb-4">
        <h3 class="text-sm font-semibold text-surface-300">Pipeline Intelligence</h3>
        <span class="text-surface-600 text-[10px] font-mono">{{ route }}</span>
        <div class="flex gap-1 ml-auto">
          <span class="px-1.5 py-0.5 bg-brand-500/10 text-brand-400 text-[9px] rounded font-mono">{{ ps.config?.pipeline || 'Pipeline' }}</span>
          <span v-if="ps.gate?.percentile" class="px-1.5 py-0.5 bg-surface-700 text-surface-400 text-[9px] rounded font-mono">Gate p{{ ps.gate.percentile }}</span>
          <span v-if="ps.abort?.enabled !== false" class="px-1.5 py-0.5 bg-surface-700 text-surface-400 text-[9px] rounded font-mono">Q-Abort</span>
          <span class="px-1.5 py-0.5 bg-surface-700 text-[9px] rounded font-mono" :class="ps.scorer?.warmed_up ? 'text-green-400' : 'text-amber-400'">{{ ps.scorer?.warmed_up ? 'Scorer active' : 'Warming up' }}</span>
        </div>
      </div>

      <!-- ═══ SECTION 1: Key Metrics Row (visual gauges) ═══ -->
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <MetricCard label="Protection Value" :value="ps.protection?.total_protection_value" prefix="+" format="currency" color="green" icon="shield" title="Estimated PnL saved by gate blocks + abort early-exits combined" />
        <MetricCard label="Gate Accuracy" :value="ps.gate?.allow_accuracy" format="pct" :threshold="[0.5, 0.7]" icon="filter" title="% of allowed entries that were profitable (correct allows / total allows)" />
        <MetricCard label="Entries Blocked" :value="ps.block_rate" format="pct" color="amber" :sub="`${ps.entries_blocked || 0} / ${ps.total_gate_checks || 0}`" icon="block" title="% of entry signals rejected by the danger gate" />
        <MetricCard label="Abort Rate" :value="ps.abort_rate" format="pct" color="red" :sub="`${ps.aborts_triggered || 0} aborts`" icon="abort" title="% of active cycles terminated early by Q-learning abort" />
        <MetricCard label="Win Rate" :value="ps.cycles?.win_rate" format="pct" :threshold="[0.4, 0.6]" :sub="`${ps.cycles?.wins || 0}W / ${ps.cycles?.losses || 0}L`" icon="chart" title="% of completed cycles that ended in profit (TP hit or bucket hit)" />
        <MetricCard label="Avg Danger" :value="ps.danger?.mean" format="dec3" :threshold-inv="[0.5, 0.7]" :sub="`std ${ps.danger?.std?.toFixed(3) || '-'}`" icon="danger" title="Mean danger score across all observations (0=safe, 1=extreme risk)" />
      </div>

      <!-- ═══ SECTION 2: Cycle Scatter Plot ═══ -->
      <div class="card mb-6">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h4 class="text-xs font-semibold text-surface-400">Cycle Scatter: Danger at Entry vs PnL</h4>
            <p class="text-[10px] text-surface-600">Each dot = one cycle. Color = exit reason, size = level reached</p>
          </div>
          <div class="flex gap-1 text-[9px]">
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-green-400"></span> TP Hit</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-amber-400"></span> Aborted</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-red-400"></span> Max Level</span>
            <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-surface-400"></span> Other</span>
          </div>
        </div>
        <div ref="scatterEl" class="w-full h-[300px]"></div>
        <!-- Scatter stats summary -->
        <div v-if="scatterStats(ps)" class="grid grid-cols-4 gap-2 mt-2 text-[10px]">
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">Correlation:</span>
            <span class="font-mono ml-1" :class="Math.abs(scatterStats(ps).correlation) > 0.3 ? 'text-amber-400' : 'text-surface-300'">{{ scatterStats(ps).correlation.toFixed(3) }}</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">High-Danger PnL:</span>
            <span class="font-mono ml-1" :class="(scatterStats(ps).highDangerPnl||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ scatterStats(ps).highDangerPnl.toFixed(2) }}</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">Low-Danger PnL:</span>
            <span class="font-mono ml-1" :class="(scatterStats(ps).lowDangerPnl||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ scatterStats(ps).lowDangerPnl.toFixed(2) }}</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">Gate Threshold:</span>
            <span class="font-mono text-red-400 ml-1">{{ ps.gate?.avg_danger_at_block?.toFixed(3) ?? '-' }}</span>
          </div>
        </div>
      </div>

      <!-- ═══ SECTION 3: Q-Learning Convergence ═══ -->
      <div v-if="ps.abort?.enabled !== false && !ps.abort?.q_progression?.length" class="card mb-6">
        <h4 class="text-xs font-semibold text-surface-400 mb-2">Q-Learning Convergence</h4>
        <p class="text-xs text-surface-500 text-center py-6">No Q-learning data recorded. The abort module may still be warming up, or no abort decisions were needed during this run.</p>
      </div>
      <div v-if="ps.abort?.q_progression?.length" class="card mb-6">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h4 class="text-xs font-semibold text-surface-400">Q-Learning Convergence</h4>
            <p class="text-[10px] text-surface-600">Mean Q-value, volatility, and state coverage over cycles</p>
          </div>
          <div class="flex gap-2 text-[9px]">
            <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-brand-400 inline-block"></span> Mean Q</span>
            <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-amber-400 inline-block"></span> Std Q</span>
            <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-green-400 inline-block"></span> Coverage</span>
          </div>
        </div>
        <div ref="qChartEl" class="w-full h-[220px]"></div>
        <!-- Q-Learning stats row -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2 text-[10px]">
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">States Visited:</span>
            <span class="font-mono text-surface-300 ml-1">{{ ps.abort?.states_visited || 0 }}/{{ ps.abort?.total_states || 0 }}</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">Coverage:</span>
            <span class="font-mono text-surface-300 ml-1">{{ ((ps.abort?.coverage||0)*100).toFixed(1) }}%</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">Abort-preferred:</span>
            <span class="font-mono text-red-400 ml-1">{{ ps.abort?.abort_preferred_states || 0 }}</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500">Continue-preferred:</span>
            <span class="font-mono text-green-400 ml-1">{{ ps.abort?.continue_preferred_states || 0 }}</span>
          </div>
          <div class="p-1.5 bg-surface-800/60 rounded">
            <span class="text-surface-500" title="Average difference between Q(abort) and Q(continue) when abort was chosen — larger = more confident">Q-Margin @ Abort:</span>
            <span class="font-mono text-surface-300 ml-1">{{ ps.abort?.q_margin_at_abort?.toFixed(4) ?? '-' }}</span>
          </div>
        </div>
      </div>

      <!-- ═══ SECTION 4: Level Performance Breakdown ═══ -->
      <div v-if="!ps.level_performance || !Object.keys(ps.level_performance).length" class="card mb-6">
        <h4 class="text-xs font-semibold text-surface-400 mb-2">Per-Level Performance</h4>
        <p class="text-xs text-surface-500 text-center py-6">No level data recorded. Cycles may not have completed yet, or the strategy does not use multi-level entries.</p>
      </div>
      <div v-if="ps.level_performance && Object.keys(ps.level_performance).length" class="card mb-6">
        <h4 class="text-xs font-semibold text-surface-400 mb-3">Per-Level Performance</h4>
        <div class="space-y-1.5">
          <div v-for="(data, level) in ps.level_performance" :key="level"
               class="flex items-center gap-3 p-2 bg-surface-800/40 rounded">
            <span class="text-xs font-mono font-bold w-8" :class="levelColor(level)">L{{ level }}</span>
            <!-- Win/Loss bar -->
            <div class="flex-1 h-5 bg-surface-900 rounded-sm overflow-hidden flex relative">
              <div class="h-full bg-green-500/50 transition-all" :style="{width: data.count > 0 ? (data.wins/data.count*100)+'%' : '0%'}"></div>
              <div class="h-full bg-red-500/50 transition-all" :style="{width: data.count > 0 ? ((data.count-data.wins)/data.count*100)+'%' : '0%'}"></div>
              <span class="absolute inset-0 flex items-center justify-center text-[9px] font-mono text-white/70">
                {{ data.wins }}W / {{ data.count - data.wins }}L
              </span>
            </div>
            <span class="text-[10px] font-mono text-surface-400 w-8 text-right">{{ data.count }}x</span>
            <span class="text-[10px] font-mono w-12 text-right" :class="(data.win_rate||0) >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ ((data.win_rate||0)*100).toFixed(0) }}%</span>
            <span class="text-[10px] font-mono w-16 text-right" :class="data.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ data.pnl >= 0 ? '+' : '' }}{{ data.pnl.toFixed(2) }}</span>
            <span v-if="data.avg_danger != null" class="text-[10px] font-mono text-surface-500 w-14 text-right" :title="`Avg danger at entry: ${data.avg_danger}`">
              d={{ data.avg_danger.toFixed(2) }}
            </span>
          </div>
        </div>
      </div>

      <!-- ═══ SECTION 5: Gate & Abort Decision Quality ═══ -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <!-- Entry Gate Analysis -->
        <div class="card">
          <h4 class="text-xs font-semibold text-surface-400 mb-3">Entry Gate Analysis</h4>
          <div class="space-y-2 text-xs">
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Allow Accuracy</span>
              <span class="font-mono" :class="(ps.gate?.allow_accuracy||0) >= 0.6 ? 'text-green-400' : 'text-amber-400'">{{ ((ps.gate?.allow_accuracy||0)*100).toFixed(1) }}%</span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Correct / Wrong Allows</span>
              <span><span class="font-mono text-green-400">{{ ps.gate?.correct_allows || 0 }}</span> / <span class="font-mono text-red-400">{{ ps.gate?.wrong_allows || 0 }}</span></span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">PnL of Allowed Entries</span>
              <span class="font-mono" :class="(ps.gate?.pnl_of_allowed||0) >= 0 ? 'text-green-400' : 'text-red-400'">{{ (ps.gate?.pnl_of_allowed||0).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Est. Saved by Blocks</span>
              <span class="font-mono text-green-400">+{{ (ps.gate?.est_pnl_saved_by_blocks||0).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Avg Danger @ Block / Allow</span>
              <span>
                <span class="font-mono text-red-400">{{ ps.gate?.avg_danger_at_block?.toFixed(3) ?? '-' }}</span>
                <span class="text-surface-600"> / </span>
                <span class="font-mono text-green-400">{{ ps.gate?.avg_danger_at_allow?.toFixed(3) ?? '-' }}</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Q-Abort Analysis -->
        <div class="card">
          <h4 class="text-xs font-semibold text-surface-400 mb-3">Q-Abort Analysis</h4>
          <div class="space-y-2 text-xs">
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Avg Level @ Abort</span>
              <span class="font-mono text-surface-300">{{ ps.abort?.avg_level_at_abort?.toFixed(1) ?? '-' }}</span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Cut Losses / Cut Profits</span>
              <span><span class="font-mono text-green-400">{{ ps.abort?.aborts_at_loss || 0 }}</span> / <span class="font-mono text-red-400">{{ ps.abort?.aborts_at_profit || 0 }}</span></span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Avg PnL @ Abort</span>
              <span class="font-mono" :class="(ps.abort?.avg_pnl_at_abort||0) < 0 ? 'text-red-400' : 'text-green-400'">{{ ps.abort?.avg_pnl_at_abort?.toFixed(2) ?? '-' }}</span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">PnL Saved by Aborts</span>
              <span class="font-mono text-green-400">+{{ (ps.abort?.pnl_saved_by_aborts||0).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between p-2 bg-surface-800/40 rounded">
              <span class="text-surface-500">Total Decisions</span>
              <span class="font-mono text-surface-300">{{ ps.abort?.total_visits?.toLocaleString() ?? (ps.abort_checks || 0) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ SECTION 6: Risk Intelligence Table ═══ -->
      <div v-if="ps.risk_intel?.danger_buckets" class="card mb-6">
        <h4 class="text-xs font-semibold text-surface-400 mb-3">Risk Intelligence: Danger Buckets</h4>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-surface-500 border-b border-surface-700">
                <th class="text-left py-2 px-3">Danger Bucket</th>
                <th class="text-right py-2 px-3">Count</th>
                <th class="text-right py-2 px-3">Win Rate</th>
                <th class="text-right py-2 px-3">Total PnL</th>
                <th class="text-right py-2 px-3">Avg PnL</th>
                <th class="text-left py-2 px-3 w-32">Distribution</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(b, label) in ps.risk_intel.danger_buckets" :key="label"
                  class="border-b border-surface-800" :class="b.count === 0 ? 'opacity-30' : ''">
                <td class="py-2 px-3 font-mono font-semibold" :class="bucketColor(label)">{{ label }}</td>
                <td class="text-right py-2 px-3 font-mono text-surface-300">{{ b.count }}</td>
                <td class="text-right py-2 px-3 font-mono" :class="b.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (b.win_rate*100).toFixed(1) }}%</td>
                <td class="text-right py-2 px-3 font-mono" :class="b.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ b.pnl.toFixed(2) }}</td>
                <td class="text-right py-2 px-3 font-mono" :class="b.count > 0 ? (b.pnl/b.count >= 0 ? 'text-green-400' : 'text-red-400') : 'text-surface-600'">
                  {{ b.count > 0 ? (b.pnl/b.count).toFixed(2) : '-' }}
                </td>
                <td class="py-2 px-3">
                  <div class="h-3 bg-surface-900 rounded-full overflow-hidden">
                    <div class="h-full rounded-full transition-all" :class="bucketBarColor(label)"
                         :style="{width: totalCycles(ps) > 0 ? (b.count/totalCycles(ps)*100)+'%' : '0%'}"></div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Peak danger + bust info -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-[10px]">
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
        <div v-if="ps.risk_intel.peak_danger_window" class="mt-2 p-2 bg-red-500/5 border border-red-500/10 rounded text-[10px]">
          <span class="text-surface-500">Most Dangerous Period:</span>
          <span class="font-mono text-red-400 ml-1">{{ formatTs(ps.risk_intel.peak_danger_window.start_ts) }} — {{ formatTs(ps.risk_intel.peak_danger_window.end_ts) }}</span>
          <span class="text-surface-500 ml-2">Avg Danger:</span>
          <span class="font-mono text-red-400 ml-1">{{ ps.risk_intel.peak_danger_window.avg_danger.toFixed(3) }}</span>
        </div>
      </div>

      <!-- ═══ SECTION 7: Decision Audit Table ═══ -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h4 class="text-xs font-semibold text-surface-400">Decision Audit Log</h4>
            <p class="text-[10px] text-surface-600">Every gate and abort decision with outcome linkage</p>
          </div>
          <div class="flex gap-2">
            <select v-model="auditFilter" class="select text-[10px] py-1 px-2 w-auto bg-surface-800 border-surface-700">
              <option value="all">All Decisions</option>
              <option value="gate_blocked">Gate: Blocked</option>
              <option value="gate_allowed">Gate: Allowed</option>
              <option value="abort_triggered">Abort: Triggered</option>
              <option value="abort_continued">Abort: Continued</option>
            </select>
          </div>
        </div>
        <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table class="w-full text-[10px]">
            <thead class="sticky top-0 bg-surface-900">
              <tr class="text-surface-500 border-b border-surface-700">
                <th class="text-left py-1.5 px-2 cursor-pointer hover:text-surface-300" @click="sortAudit('ts')">Time {{ auditSort === 'ts' ? (auditSortDir > 0 ? '&#9650;' : '&#9660;') : '' }}</th>
                <th class="text-left py-1.5 px-2">Type</th>
                <th class="text-right py-1.5 px-2 cursor-pointer hover:text-surface-300" @click="sortAudit('danger')">Danger {{ auditSort === 'danger' ? (auditSortDir > 0 ? '&#9650;' : '&#9660;') : '' }}</th>
                <th class="text-right py-1.5 px-2">Threshold</th>
                <th class="text-left py-1.5 px-2">Decision</th>
                <th class="text-right py-1.5 px-2">Level</th>
                <th class="text-right py-1.5 px-2">Q-Values</th>
                <th class="text-right py-1.5 px-2 cursor-pointer hover:text-surface-300" @click="sortAudit('pnl')">Outcome PnL {{ auditSort === 'pnl' ? (auditSortDir > 0 ? '&#9650;' : '&#9660;') : '' }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(d, i) in filteredAuditRows(ps)" :key="i"
                  class="border-b border-surface-800/50 hover:bg-surface-800/30">
                <td class="py-1 px-2 font-mono text-surface-400">{{ formatTs(d.ts) }}</td>
                <td class="py-1 px-2">
                  <span class="px-1.5 py-0.5 rounded text-[9px] font-medium"
                        :class="d.type === 'gate' ? 'bg-blue-500/15 text-blue-400' : 'bg-purple-500/15 text-purple-400'">{{ d.type }}</span>
                </td>
                <td class="py-1 px-2 text-right font-mono" :class="d.danger > 0.7 ? 'text-red-400' : d.danger > 0.5 ? 'text-amber-400' : 'text-green-400'">{{ d.danger?.toFixed(3) }}</td>
                <td class="py-1 px-2 text-right font-mono text-surface-500">{{ d.threshold?.toFixed(3) ?? '-' }}</td>
                <td class="py-1 px-2">
                  <span class="px-1.5 py-0.5 rounded text-[9px] font-mono"
                        :class="decisionClass(d)">{{ d.decision }}</span>
                </td>
                <td class="py-1 px-2 text-right font-mono text-surface-400">{{ d.level ?? '-' }}</td>
                <td class="py-1 px-2 text-right font-mono text-surface-500">
                  <span v-if="d.q_continue != null">C:{{ d.q_continue.toFixed(3) }} A:{{ d.q_abort.toFixed(3) }}</span>
                  <span v-else>-</span>
                </td>
                <td class="py-1 px-2 text-right font-mono" :class="d.outcome_pnl != null ? (d.outcome_pnl >= 0 ? 'text-green-400' : 'text-red-400') : 'text-surface-600'">
                  {{ d.outcome_pnl != null ? d.outcome_pnl.toFixed(2) : '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="filteredAuditRows(ps).length === 0" class="text-center py-4 text-surface-600 text-xs">No decisions match the current filter</div>
        <div v-if="totalAuditRows(ps) > 200" class="text-center py-2 text-surface-500 text-[10px]">Showing 200 of {{ totalAuditRows(ps) }} decisions. {{ totalAuditRows(ps) - 200 }} rows hidden.</div>
      </div>

      <!-- ═══ SECTION 8: Cycle Outcomes by Exit Reason ═══ -->
      <div v-if="ps.cycles?.pnl_by_exit && Object.keys(ps.cycles.pnl_by_exit).length" class="card mt-6">
        <h4 class="text-xs font-semibold text-surface-400 mb-3">Outcome Breakdown by Exit Reason</h4>
        <div class="space-y-2">
          <div v-for="(ex, reason) in ps.cycles.pnl_by_exit" :key="reason"
               class="flex items-center gap-3 p-2 bg-surface-800/40 rounded">
            <span class="px-2 py-0.5 rounded text-[10px] font-mono min-w-[100px] text-center"
                  :class="exitReasonClass(reason)">{{ reason }}</span>
            <span class="text-[10px] font-mono text-surface-400 w-10 text-right">{{ ex.count }}x</span>
            <div class="flex-1 h-4 bg-surface-900 rounded-sm overflow-hidden">
              <div class="h-full transition-all rounded-sm" :class="ex.pnl >= 0 ? 'bg-green-500/40' : 'bg-red-500/40'"
                   :style="{width: maxExitPnl(ps) > 0 ? (Math.abs(ex.pnl)/maxExitPnl(ps)*100)+'%' : '0%'}"></div>
            </div>
            <span class="text-xs font-mono w-20 text-right" :class="ex.pnl >= 0 ? 'text-green-400' : 'text-red-400'">
              {{ ex.pnl >= 0 ? '+' : '' }}{{ ex.pnl.toFixed(2) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!stats || Object.keys(stats).length === 0" class="text-center py-12 text-surface-500">
      <p class="text-sm">No pipeline data available</p>
      <p class="text-xs mt-1">Run a backtest with pipelines enabled to see intelligence analytics</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted, computed } from 'vue'

const props = defineProps({
  stats: { type: Object, default: null },
})

// ── Inline MetricCard ──
const MetricCard = {
  props: ['label', 'value', 'prefix', 'format', 'color', 'threshold', 'thresholdInv', 'sub', 'icon', 'title'],
  setup(p) {
    const formatted = computed(() => {
      if (p.value == null) return '-'
      if (p.format === 'pct') return ((p.value) * 100).toFixed(1) + '%'
      if (p.format === 'currency') return (p.prefix || '') + p.value.toFixed(2)
      if (p.format === 'dec3') return p.value.toFixed(3)
      return String(p.value)
    })
    const colorClass = computed(() => {
      if (p.color === 'green') return 'text-green-400'
      if (p.color === 'amber') return 'text-amber-400'
      if (p.color === 'red') return 'text-red-400'
      if (p.threshold && p.value != null) {
        if (p.value >= p.threshold[1]) return 'text-green-400'
        if (p.value >= p.threshold[0]) return 'text-amber-400'
        return 'text-red-400'
      }
      if (p.thresholdInv && p.value != null) {
        if (p.value <= p.thresholdInv[0]) return 'text-green-400'
        if (p.value <= p.thresholdInv[1]) return 'text-amber-400'
        return 'text-red-400'
      }
      return 'text-surface-100'
    })
    const iconSvg = computed(() => {
      const icons = {
        shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
        filter: 'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
        block: 'M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636',
        abort: 'M10 15l-5.878 5.878M15 10l5.878-5.878M10 15l5.878 5.878M15 10L9.122 4.122',
        chart: 'M3 3v18h18M9 17V9m4 8V5m4 12v-4',
        danger: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
      }
      return icons[p.icon] || icons.chart
    })
    return { formatted, colorClass, iconSvg }
  },
  template: `
    <div class="p-3 bg-surface-800 rounded-lg border border-surface-700/50" :title="title">
      <div class="flex items-center gap-2 mb-1">
        <svg class="w-3.5 h-3.5 text-surface-600" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" :d="iconSvg"/></svg>
        <span class="text-[10px] text-surface-500 uppercase tracking-wider">{{ label }}</span>
      </div>
      <div class="font-mono text-lg font-semibold" :class="colorClass">{{ formatted }}</div>
      <div v-if="sub" class="text-[10px] text-surface-600 font-mono mt-0.5">{{ sub }}</div>
    </div>
  `,
}

// ── Scatter chart ──
const scatterEl = ref(null)
const qChartEl = ref(null)
let scatterCanvas = null
let qChartInstances = {}

function scatterStats(ps) {
  const outcomes = ps.cycle_outcomes
  if (!outcomes?.length) return null
  const withDanger = outcomes.filter(c => c.danger_at_entry != null)
  if (withDanger.length < 2) return null

  const xs = withDanger.map(c => c.danger_at_entry)
  const ys = withDanger.map(c => c.pnl)
  const n = xs.length
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  let num = 0, dx2 = 0, dy2 = 0
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx, dy = ys[i] - my
    num += dx * dy; dx2 += dx * dx; dy2 += dy * dy
  }
  const corr = (dx2 > 0 && dy2 > 0) ? num / Math.sqrt(dx2 * dy2) : 0

  const high = withDanger.filter(c => c.danger_at_entry > 0.7)
  const low = withDanger.filter(c => c.danger_at_entry <= 0.3)

  return {
    correlation: corr,
    highDangerPnl: high.reduce((a, c) => a + c.pnl, 0),
    lowDangerPnl: low.reduce((a, c) => a + c.pnl, 0),
  }
}

function drawScatter(ps) {
  const raw = scatterEl.value
  const el = Array.isArray(raw) ? raw[0] : raw
  if (!el || !ps?.cycle_outcomes?.length) return

  const outcomes = ps.cycle_outcomes.filter(c => c.danger_at_entry != null)
  if (!outcomes.length) return

  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight

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
  scatterCanvas = canvas

  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const pad = { top: 20, right: 20, bottom: 35, left: 55 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom

  // Data ranges
  const dangers = outcomes.map(c => c.danger_at_entry)
  const pnls = outcomes.map(c => c.pnl)
  const minD = 0, maxD = 1
  const minP = Math.min(...pnls, 0)
  const maxP = Math.max(...pnls, 0)
  const rangeP = maxP - minP || 1

  // Background
  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = '#1e1f2b'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ph / 4) * i
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }
  for (let i = 0; i <= 4; i++) {
    const x = pad.left + (pw / 4) * i
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, h - pad.bottom); ctx.stroke()
  }

  // Zero line
  const zeroY = pad.top + ph * (1 - (0 - minP) / rangeP)
  if (zeroY >= pad.top && zeroY <= pad.top + ph) {
    ctx.strokeStyle = '#333'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.beginPath(); ctx.moveTo(pad.left, zeroY); ctx.lineTo(w - pad.right, zeroY); ctx.stroke()
    ctx.setLineDash([])
  }

  // Gate threshold line (vertical)
  const threshold = ps.gate?.avg_danger_at_block
  if (threshold != null) {
    const tx = pad.left + pw * ((threshold - minD) / (maxD - minD))
    ctx.strokeStyle = 'rgba(239, 68, 68, 0.4)'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.beginPath(); ctx.moveTo(tx, pad.top); ctx.lineTo(tx, h - pad.bottom); ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = '#ef4444'
    ctx.font = '9px monospace'
    ctx.fillText('gate', tx + 3, pad.top + 10)
  }

  // Color map
  const colorMap = {
    'bucket_hit': '#4ade80', 'tp_hit': '#4ade80',
    'pipeline_abort': '#fbbf24',
    'max_levels': '#f87171', 'max_level_sl': '#f87171',
  }

  // Plot points
  for (const c of outcomes) {
    const x = pad.left + pw * ((c.danger_at_entry - minD) / (maxD - minD))
    const y = pad.top + ph * (1 - (c.pnl - minP) / rangeP)
    const r = Math.min(2 + (c.level || 0) * 1.5, 10)
    const color = colorMap[c.exit_reason] || '#64748b'

    ctx.beginPath()
    ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fillStyle = color + '99'
    ctx.fill()
    ctx.strokeStyle = color
    ctx.lineWidth = 0.5
    ctx.stroke()
  }

  // Axes labels
  ctx.fillStyle = '#666'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('Danger at Entry', pad.left + pw / 2, h - 5)
  for (let i = 0; i <= 4; i++) {
    const v = minD + (maxD - minD) * i / 4
    ctx.fillText(v.toFixed(2), pad.left + pw * i / 4, h - pad.bottom + 14)
  }

  ctx.save()
  ctx.translate(12, pad.top + ph / 2)
  ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'
  ctx.fillText('PnL', 0, 0)
  ctx.restore()

  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = minP + rangeP * (1 - i / 4)
    ctx.fillText(v.toFixed(1), pad.left - 5, pad.top + ph * i / 4 + 4)
  }
}

function drawQChart(ps) {
  const raw = qChartEl.value
  const el = Array.isArray(raw) ? raw[0] : raw
  if (!el || !ps?.abort?.q_progression?.length) return

  const data = ps.abort.q_progression
  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight

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

  const pad = { top: 15, right: 50, bottom: 30, left: 55 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom

  // Background
  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  const n = data.length
  // [ts, mean_q, std_q, coverage]
  const meanQs = data.map(d => d[1])
  const stdQs = data.map(d => d[2])
  const covs = data.map(d => d[3])

  const minQ = Math.min(...meanQs.map((m, i) => m - stdQs[i]))
  const maxQ = Math.max(...meanQs.map((m, i) => m + stdQs[i]))
  const rangeQ = maxQ - minQ || 1

  // Grid
  ctx.strokeStyle = '#1e1f2b'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ph * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }

  // Std Q band (fill)
  ctx.fillStyle = 'rgba(251, 191, 36, 0.08)'
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + pw * i / (n - 1)
    const y = pad.top + ph * (1 - (meanQs[i] + stdQs[i] - minQ) / rangeQ)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  for (let i = n - 1; i >= 0; i--) {
    const x = pad.left + pw * i / (n - 1)
    const y = pad.top + ph * (1 - (meanQs[i] - stdQs[i] - minQ) / rangeQ)
    ctx.lineTo(x, y)
  }
  ctx.closePath()
  ctx.fill()

  // Mean Q line
  ctx.strokeStyle = '#818cf8'
  ctx.lineWidth = 2
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + pw * i / (n - 1)
    const y = pad.top + ph * (1 - (meanQs[i] - minQ) / rangeQ)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()

  // Coverage line (right axis, 0-100%)
  ctx.strokeStyle = '#4ade80'
  ctx.lineWidth = 1.5
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + pw * i / (n - 1)
    const y = pad.top + ph * (1 - covs[i])
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()
  ctx.setLineDash([])

  // Labels
  ctx.fillStyle = '#666'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('Cycle', pad.left + pw / 2, h - 5)

  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = minQ + rangeQ * (1 - i / 4)
    ctx.fillText(v.toFixed(4), pad.left - 5, pad.top + ph * i / 4 + 4)
  }

  // Right axis (coverage)
  ctx.textAlign = 'left'
  ctx.fillStyle = '#4ade80'
  for (let i = 0; i <= 4; i++) {
    const v = (1 - i / 4) * 100
    ctx.fillText(v.toFixed(0) + '%', w - pad.right + 5, pad.top + ph * i / 4 + 4)
  }
}

// ── Audit table ──
const auditFilter = ref('all')
const auditSort = ref('ts')
const auditSortDir = ref(-1)

function sortAudit(key) {
  if (auditSort.value === key) {
    auditSortDir.value *= -1
  } else {
    auditSort.value = key
    auditSortDir.value = key === 'ts' ? -1 : 1
  }
}

function filteredAuditRows(ps) {
  const rows = buildAuditRows(ps)
  let filtered = rows
  if (auditFilter.value === 'gate_blocked') filtered = rows.filter(r => r.type === 'gate' && r.decision === 'BLOCKED')
  else if (auditFilter.value === 'gate_allowed') filtered = rows.filter(r => r.type === 'gate' && r.decision === 'ALLOWED')
  else if (auditFilter.value === 'abort_triggered') filtered = rows.filter(r => r.type === 'abort' && r.decision === 'ABORT')
  else if (auditFilter.value === 'abort_continued') filtered = rows.filter(r => r.type === 'abort' && r.decision === 'continue')

  const key = auditSort.value
  const dir = auditSortDir.value
  filtered.sort((a, b) => {
    const va = key === 'pnl' ? (a.outcome_pnl ?? -Infinity) : key === 'danger' ? (a.danger ?? 0) : (a.ts ?? 0)
    const vb = key === 'pnl' ? (b.outcome_pnl ?? -Infinity) : key === 'danger' ? (b.danger ?? 0) : (b.ts ?? 0)
    return (va - vb) * dir
  })
  return filtered.slice(0, 200)
}

function buildAuditRows(ps) {
  const rows = []
  for (const gd of (ps.gate_decisions || [])) {
    rows.push({
      ts: gd.ts, type: 'gate', danger: gd.danger, threshold: gd.threshold,
      decision: gd.allowed ? 'ALLOWED' : 'BLOCKED',
      level: null, q_continue: null, q_abort: null,
      outcome_pnl: gd.outcome_pnl,
    })
  }
  for (const ad of (ps.abort_decisions || [])) {
    rows.push({
      ts: ad.ts, type: 'abort', danger: ad.danger, threshold: null,
      decision: ad.action === 'abort' ? 'ABORT' : 'continue',
      level: ad.level, q_continue: ad.q_continue, q_abort: ad.q_abort,
      outcome_pnl: ad.pnl_at_abort,
    })
  }
  return rows
}

function totalAuditRows(ps) {
  return (ps.gate_decisions?.length || 0) + (ps.abort_decisions?.length || 0)
}

// ── Helpers ──
function formatTs(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

function levelColor(level) {
  const l = parseInt(level)
  if (l === 0) return 'text-green-400'
  if (l <= 2) return 'text-brand-400'
  if (l <= 5) return 'text-amber-400'
  return 'text-red-400'
}

function bucketColor(label) {
  const map = { extreme: 'text-red-400', high: 'text-orange-400', medium: 'text-amber-400', low: 'text-green-400', very_low: 'text-green-300' }
  return map[label] || 'text-surface-400'
}

function bucketBarColor(label) {
  const map = { extreme: 'bg-red-500/60', high: 'bg-orange-500/60', medium: 'bg-amber-500/60', low: 'bg-green-500/60', very_low: 'bg-green-400/60' }
  return map[label] || 'bg-surface-500/60'
}

function totalCycles(ps) {
  if (!ps.risk_intel?.danger_buckets) return 1
  return Object.values(ps.risk_intel.danger_buckets).reduce((a, b) => a + b.count, 0) || 1
}

function decisionClass(d) {
  if (d.decision === 'BLOCKED') return 'bg-red-500/20 text-red-400'
  if (d.decision === 'ALLOWED') return 'bg-green-500/20 text-green-400'
  if (d.decision === 'ABORT') return 'bg-amber-500/20 text-amber-400'
  return 'bg-surface-700 text-surface-400'
}

function exitReasonClass(reason) {
  if (reason === 'bucket_hit' || reason === 'tp_hit') return 'bg-green-500/20 text-green-400'
  if (reason === 'pipeline_abort') return 'bg-amber-500/20 text-amber-400'
  if (reason.includes('max_level')) return 'bg-red-500/20 text-red-400'
  return 'bg-surface-700 text-surface-400'
}

function maxExitPnl(ps) {
  if (!ps.cycles?.pnl_by_exit) return 1
  return Math.max(...Object.values(ps.cycles.pnl_by_exit).map(e => Math.abs(e.pnl)), 1)
}

// ── Redraw on data change ──
watch(() => props.stats, async () => {
  await nextTick()
  if (!props.stats) return
  for (const ps of Object.values(props.stats)) {
    drawScatter(ps)
    drawQChart(ps)
    break // single route for now
  }
}, { immediate: true, deep: true })

// Resize handler
let resizeObserver = null
function setupResize() {
  resizeObserver = new ResizeObserver(() => {
    if (!props.stats) return
    for (const ps of Object.values(props.stats)) {
      drawScatter(ps)
      drawQChart(ps)
      break
    }
  })
  const se = Array.isArray(scatterEl.value) ? scatterEl.value[0] : scatterEl.value
  const qe = Array.isArray(qChartEl.value) ? qChartEl.value[0] : qChartEl.value
  if (se) resizeObserver.observe(se)
  if (qe) resizeObserver.observe(qe)
}

watch([scatterEl, qChartEl], () => {
  if (resizeObserver) resizeObserver.disconnect()
  setupResize()
  // Draw immediately when elements mount (tab switch)
  if (props.stats) {
    nextTick(() => {
      for (const ps of Object.values(props.stats)) {
        drawScatter(ps)
        drawQChart(ps)
        break
      }
    })
  }
})

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
})
</script>
