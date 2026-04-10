<template>
  <div class="space-y-6">
    <div v-for="(ps, route) in stats" :key="route">
      <!-- ═══ HEADER: Dynamic badges + Export ═══ -->
      <div class="flex items-center gap-2 mb-4" v-if="ui(ps)">
        <h3 class="text-sm font-semibold text-surface-300">Pipeline Intelligence</h3>
        <span class="text-surface-600 text-[10px] font-mono">{{ route }}</span>
        <div class="flex gap-1 ml-auto items-center">
          <!-- Load Full Report button (for lazy-loaded heavy data) -->
          <button v-if="ps._has_heavy && !heavyLoaded[route]"
                  @click="loadHeavyData(route)"
                  :disabled="heavyLoading[route]"
                  class="px-2 py-0.5 text-[9px] rounded font-mono bg-brand-600 hover:bg-brand-500 text-white border border-brand-500/50 transition-colors flex items-center gap-1 disabled:opacity-50"
                  title="Load charts, audit tables, and detailed analytics">
            <svg v-if="heavyLoading[route]" class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
            </svg>
            <svg v-else class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
            </svg>
            {{ heavyLoading[route] ? 'Loading...' : 'Load Full Report' }}
          </button>
          <span v-if="heavyLoaded[route]" class="px-1.5 py-0.5 text-[9px] rounded font-mono bg-green-500/10 text-green-400">Full Report Loaded</span>
          <button @click="exportReport(ps, route)"
                  class="px-2 py-0.5 text-[9px] rounded font-mono bg-surface-700 hover:bg-surface-600 text-surface-300 border border-surface-600/50 transition-colors flex items-center gap-1"
                  title="Export pipeline report as JSON">
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Export
          </button>
          <template v-for="(badge, bi) in ui(ps).badges" :key="bi">
            <span v-if="!badge.show_if || resolve(ps, badge.show_if)"
                  class="px-1.5 py-0.5 text-[9px] rounded font-mono"
                  :class="badgeClass(badge.color)">{{ badge.label }}</span>
          </template>
        </div>
      </div>

      <!-- ═══ METRIC CARDS ═══ -->
      <div v-if="ui(ps)?.metric_cards?.length"
           class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <div v-for="(mc, mi) in ui(ps).metric_cards" :key="mi"
             class="p-3 bg-surface-800 rounded-lg border border-surface-700/50" :title="mc.tooltip">
          <div class="flex items-center gap-2 mb-1">
            <svg class="w-3.5 h-3.5 text-surface-600" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" :d="iconPath(mc.icon)"/>
            </svg>
            <span class="text-[10px] text-surface-500 uppercase tracking-wider">{{ mc.label }}</span>
          </div>
          <div class="font-mono text-lg font-semibold" :class="metricColor(mc, ps)">{{ formatMetric(mc, ps) }}</div>
          <div v-if="metricSub(mc, ps)" class="text-[10px] text-surface-600 font-mono mt-0.5">{{ metricSub(mc, ps) }}</div>
        </div>
      </div>

      <!-- ═══ DYNAMIC SECTIONS ═══ -->
      <template v-for="(group, gi) in groupedSections(ps)" :key="gi">
        <!-- Half-width group (2-col grid for kv_pairs with grid:'half') -->
        <div v-if="group.type === 'half_group'" class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <template v-for="(section, hsi) in group.items" :key="hsi">
            <!-- KV PAIRS (half-width) rendered inline -->
            <div class="card">
              <h4 class="text-xs font-semibold text-surface-400 mb-3">{{ section.title }}</h4>
              <div class="space-y-2 text-xs">
                <template v-if="section.items">
                  <div v-for="(item, ii) in section.items" :key="ii" class="flex justify-between p-2 bg-surface-800/40 rounded">
                    <span class="text-surface-500">{{ item.label }}</span>
                    <span v-if="item.template" v-html="renderTemplate(item.template, ps)" class="font-mono"></span>
                    <span v-else class="font-mono" :class="kvValueColor(item, ps)">{{ formatKvValue(item, ps) }}</span>
                  </div>
                </template>
              </div>
            </div>
          </template>
        </div>
        <!-- Regular full-width section -->
        <template v-else>
          <template v-for="(section, _si) in [group.item]" :key="gi">
        <template v-if="!section.show_if || resolve(ps, section.show_if)">

          <!-- SCATTER CHART -->
          <div v-if="section.type === 'scatter'" class="card mb-6">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-xs font-semibold text-surface-400">{{ section.title }}</h4>
                <p v-if="section.subtitle" class="text-[10px] text-surface-600">{{ section.subtitle }}</p>
              </div>
              <div v-if="section.color_map" class="flex gap-1 text-[9px]">
                <span v-for="(cm, ck) in section.color_map" :key="ck" v-show="ck !== '_default'" class="flex items-center gap-1">
                  <span class="w-2 h-2 rounded-full" :style="{backgroundColor: cm.color}"></span> {{ cm.label }}
                </span>
              </div>
            </div>
            <div :ref="el => registerChartEl('scatter_' + gi + '_' + route, el)" class="w-full h-[300px]"></div>
            <!-- Scatter summary stats -->
            <div v-if="section.summary_stats && scatterSummary(ps, section)" class="grid grid-cols-4 gap-2 mt-2 text-[10px]">
              <div v-for="(ss, ssi) in computedSummaryStats(ps, section)" :key="ssi" class="p-1.5 bg-surface-800/60 rounded">
                <span class="text-surface-500">{{ ss.label }}:</span>
                <span class="font-mono ml-1" :class="ss.colorClass">{{ ss.display }}</span>
              </div>
            </div>
          </div>

          <!-- LINE CHART -->
          <div v-if="section.type === 'line_chart'" class="card mb-6">
            <template v-if="!resolve(ps, section.data_key)?.length && section.empty_message">
              <h4 class="text-xs font-semibold text-surface-400 mb-2">{{ section.title }}</h4>
              <p class="text-xs text-surface-500 text-center py-6">{{ section.empty_message }}</p>
            </template>
            <template v-else-if="resolve(ps, section.data_key)?.length">
              <div class="flex items-center justify-between mb-3">
                <div>
                  <h4 class="text-xs font-semibold text-surface-400">{{ section.title }}</h4>
                  <p v-if="section.subtitle" class="text-[10px] text-surface-600">{{ section.subtitle }}</p>
                </div>
                <div v-if="section.series" class="flex gap-2 text-[9px]">
                  <span v-for="s in section.series" :key="s.label" class="flex items-center gap-1">
                    <span class="w-3 h-0.5 inline-block" :style="{backgroundColor: s.color}" :class="{'border-dashed': s.dashed}"></span> {{ s.label }}
                  </span>
                </div>
              </div>
              <div :ref="el => registerChartEl('line_' + gi + '_' + route, el)" class="w-full h-[220px]"></div>
              <!-- Line chart summary stats -->
              <div v-if="section.summary_stats" class="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2 text-[10px]">
                <div v-for="(ss, ssi) in resolvedSummaryStats(ps, section.summary_stats)" :key="ssi" class="p-1.5 bg-surface-800/60 rounded">
                  <span class="text-surface-500">{{ ss.label }}:</span>
                  <span class="font-mono ml-1" :class="ss.colorClass || 'text-surface-300'">{{ ss.display }}</span>
                </div>
              </div>
            </template>
          </div>

          <!-- BAR BREAKDOWN -->
          <div v-if="section.type === 'bar_breakdown'" class="card mb-6">
            <template v-if="!resolve(ps, section.data_key) || !Object.keys(resolve(ps, section.data_key)).length">
              <h4 class="text-xs font-semibold text-surface-400 mb-2">{{ section.title }}</h4>
              <p class="text-xs text-surface-500 text-center py-6">{{ section.empty_message || 'No data available.' }}</p>
            </template>
            <template v-else>
              <h4 class="text-xs font-semibold text-surface-400 mb-3">
                {{ section.title }}
                <span v-if="section.max_items && Object.keys(resolve(ps, section.data_key)).length > section.max_items"
                      class="text-[10px] text-surface-600 font-normal ml-2">
                  (top {{ section.max_items }} of {{ Object.keys(resolve(ps, section.data_key)).length }})
                </span>
              </h4>
              <div class="space-y-1.5">
                <div v-for="[level, data] in processedBarData(ps, section)" :key="level"
                     class="flex items-center gap-3 p-2 bg-surface-800/40 rounded">
                  <span class="text-xs font-mono font-bold w-8"
                        :class="barLabelColor(level, section)">{{ section.label_prefix || '' }}{{ level }}</span>
                  <!-- Count-only mode (e.g. regime distribution) -->
                  <template v-if="section.mode === 'count_only'">
                    <div class="flex-1 h-5 bg-surface-900 rounded-sm overflow-hidden relative">
                      <div class="h-full bg-brand-500/50 transition-all" :style="{width: barWidth(data, processedBarData(ps, section))}"></div>
                      <span class="absolute inset-0 flex items-center justify-center text-[9px] font-mono text-white/70">
                        {{ typeof data === 'number' ? data : data.count || 0 }}
                      </span>
                    </div>
                  </template>
                  <!-- Win/loss mode -->
                  <template v-else>
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
                    <span v-if="section.show_danger && data.avg_danger != null" class="text-[10px] font-mono text-surface-500 w-14 text-right" :title="`Avg danger at entry: ${data.avg_danger}`">
                      d={{ data.avg_danger.toFixed(2) }}
                    </span>
                  </template>
                </div>
              </div>
            </template>
          </div>

          <!-- KV PAIRS -->
          <div v-if="section.type === 'kv_pairs'" class="card" :class="section.grid === 'half' ? '' : 'mb-6'">
            <template v-if="section.show_if && !resolve(ps, section.show_if)">
              <h4 class="text-xs font-semibold text-surface-400 mb-2">{{ section.title }}</h4>
              <p class="text-xs text-surface-500 text-center py-6">{{ section.empty_message || 'No data available.' }}</p>
            </template>
            <template v-else>
              <h4 class="text-xs font-semibold text-surface-400 mb-3">{{ section.title }}</h4>
              <div class="space-y-2 text-xs">
                <!-- Explicit items -->
                <template v-if="section.items">
                  <div v-for="(item, ii) in section.items" :key="ii" class="flex justify-between p-2 bg-surface-800/40 rounded">
                    <span class="text-surface-500">{{ item.label }}</span>
                    <span v-if="item.template" v-html="renderTemplate(item.template, ps)" class="font-mono"></span>
                    <span v-else class="font-mono" :class="kvValueColor(item, ps)">{{ formatKvValue(item, ps) }}</span>
                  </div>
                </template>
                <!-- Auto items from data_key (dict → key/value rows) -->
                <template v-else-if="section.auto_items && resolve(ps, section.data_key)">
                  <div v-for="(val, key) in resolve(ps, section.data_key)" :key="key" class="flex justify-between p-2 bg-surface-800/40 rounded">
                    <span class="text-surface-500">{{ humanize(key) }}</span>
                    <span class="font-mono text-surface-300">{{ formatAutoValue(val) }}</span>
                  </div>
                </template>
              </div>
            </template>
          </div>

          <!-- KV TABLE (tabular data with columns) -->
          <div v-if="section.type === 'kv_table'" class="card mb-6">
            <template v-if="section.show_if && !resolve(ps, section.show_if)">
              <h4 class="text-xs font-semibold text-surface-400 mb-2">{{ section.title }}</h4>
              <p class="text-xs text-surface-500 text-center py-6">{{ section.empty_message || 'No data available.' }}</p>
            </template>
            <template v-else-if="resolve(ps, section.data_key)">
              <h4 class="text-xs font-semibold text-surface-400 mb-3">
                {{ section.title }}
                <span v-if="section.max_items && tableRows(ps, section).length >= section.max_items"
                      class="text-[10px] text-surface-600 font-normal ml-2">(top {{ section.max_items }})</span>
              </h4>
              <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table class="w-full text-xs">
                  <thead>
                    <tr class="text-surface-500 border-b border-surface-700">
                      <th v-for="col in section.columns" :key="col.key" class="text-left py-2 px-3">{{ col.label }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, ri) in tableRows(ps, section)" :key="ri" class="border-b border-surface-800">
                      <td v-for="col in section.columns" :key="col.key" class="py-2 px-3 font-mono text-surface-300">
                        {{ formatTableCell(row[col.key], col) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>

          <!-- BUCKET TABLE -->
          <div v-if="section.type === 'bucket_table'" class="card mb-6">
            <h4 class="text-xs font-semibold text-surface-400 mb-3">{{ section.title }}</h4>
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
                  <tr v-for="(b, label) in resolve(ps, section.data_key)" :key="label"
                      class="border-b border-surface-800" :class="b.count === 0 ? 'opacity-30' : ''">
                    <td class="py-2 px-3 font-mono font-semibold" :class="bucketLabelColor(label, section)">{{ label }}</td>
                    <td class="text-right py-2 px-3 font-mono text-surface-300">{{ b.count }}</td>
                    <td class="text-right py-2 px-3 font-mono" :class="b.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (b.win_rate*100).toFixed(1) }}%</td>
                    <td class="text-right py-2 px-3 font-mono" :class="b.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ b.pnl.toFixed(2) }}</td>
                    <td class="text-right py-2 px-3 font-mono" :class="b.count > 0 ? (b.pnl/b.count >= 0 ? 'text-green-400' : 'text-red-400') : 'text-surface-600'">
                      {{ b.count > 0 ? (b.pnl/b.count).toFixed(2) : '-' }}
                    </td>
                    <td class="py-2 px-3">
                      <div class="h-3 bg-surface-900 rounded-full overflow-hidden">
                        <div class="h-full rounded-full transition-all" :class="bucketBarColorClass(label, section)"
                             :style="{width: bucketTotal(ps, section) > 0 ? (b.count/bucketTotal(ps, section)*100)+'%' : '0%'}"></div>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- Footer stats -->
            <div v-if="section.footer_stats" class="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-[10px]">
              <div v-for="(fs, fi) in section.footer_stats" :key="fi" class="p-1.5 bg-surface-800/60 rounded">
                <span class="text-surface-500">{{ fs.label }}:</span>
                <span class="font-mono ml-1" :class="fs.color ? `text-${fs.color}-400` : 'text-surface-300'">{{ formatFooterStat(fs, ps) }}</span>
              </div>
            </div>
            <!-- Peak danger window -->
            <div v-if="section.peak_danger && resolve(ps, section.peak_danger.key)" class="mt-2 p-2 bg-red-500/5 border border-red-500/10 rounded text-[10px]">
              <span class="text-surface-500">Most Dangerous Period:</span>
              <span class="font-mono text-red-400 ml-1">{{ formatTs(resolve(ps, section.peak_danger.key).start_ts) }} — {{ formatTs(resolve(ps, section.peak_danger.key).end_ts) }}</span>
              <span class="text-surface-500 ml-2">Avg Danger:</span>
              <span class="font-mono text-red-400 ml-1">{{ resolve(ps, section.peak_danger.key).avg_danger.toFixed(3) }}</span>
            </div>
          </div>

          <!-- AUDIT TABLE -->
          <div v-if="section.type === 'audit_table'" class="card mb-6">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-xs font-semibold text-surface-400">{{ section.title }}</h4>
                <p v-if="section.subtitle" class="text-[10px] text-surface-600">{{ section.subtitle }}</p>
              </div>
              <div class="flex gap-2">
                <select v-model="auditFilters[gi]" class="select text-[10px] py-1 px-2 w-auto bg-surface-800 border-surface-700">
                  <option v-for="f in section.filters" :key="f.value" :value="f.value">{{ f.label }}</option>
                </select>
              </div>
            </div>
            <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
              <table class="w-full text-[10px]">
                <thead class="sticky top-0 bg-surface-900">
                  <tr class="text-surface-500 border-b border-surface-700">
                    <th v-for="col in section.columns" :key="col.key"
                        class="py-1.5 px-2" :class="col.sortable ? 'cursor-pointer hover:text-surface-300' : ''"
                        :style="{textAlign: col.format === 'datetime' || col.format === 'badge' || col.format === 'decision_badge' ? 'left' : 'right'}"
                        @click="col.sortable && sortAuditCol(gi, col.key)">
                      {{ col.label }}
                      <span v-if="col.sortable && auditSorts[gi]?.key === col.key">{{ auditSorts[gi].dir > 0 ? '▲' : '▼' }}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in filteredAuditRows(ps, section, gi)" :key="ri"
                      class="border-b border-surface-800/50 hover:bg-surface-800/30">
                    <td v-for="col in section.columns" :key="col.key" class="py-1 px-2"
                        :style="{textAlign: col.format === 'datetime' || col.format === 'badge' || col.format === 'decision_badge' ? 'left' : 'right'}">
                      <!-- Datetime -->
                      <span v-if="col.format === 'datetime'" class="font-mono text-surface-400">{{ formatTs(row[col.key]) }}</span>
                      <!-- Badge (type) -->
                      <span v-else-if="col.format === 'badge'"
                            class="px-1.5 py-0.5 rounded text-[9px] font-medium"
                            :class="typeBadgeClass(row[col.key])">{{ row[col.key] }}</span>
                      <!-- Decision badge -->
                      <span v-else-if="col.format === 'decision_badge'"
                            class="px-1.5 py-0.5 rounded text-[9px] font-mono"
                            :class="decisionBadgeClass(row[col.key])">{{ row[col.key] }}</span>
                      <!-- Danger with color thresholds -->
                      <span v-else-if="col.color_thresholds" class="font-mono" :class="thresholdColor(row[col.key], col.color_thresholds)">
                        {{ row[col.key]?.toFixed(3) ?? '-' }}
                      </span>
                      <!-- Q-values -->
                      <span v-else-if="col.format === 'q_values'" class="font-mono text-surface-500">
                        <span v-if="row.q_continue != null">C:{{ row.q_continue.toFixed(3) }} A:{{ row.q_abort.toFixed(3) }}</span>
                        <span v-else>-</span>
                      </span>
                      <!-- Currency signed -->
                      <span v-else-if="col.format === 'currency_signed'" class="font-mono"
                            :class="row[col.key] != null ? (row[col.key] >= 0 ? 'text-green-400' : 'text-red-400') : 'text-surface-600'">
                        {{ row[col.key] != null ? row[col.key].toFixed(2) : '-' }}
                      </span>
                      <!-- Int -->
                      <span v-else-if="col.format === 'int'" class="font-mono text-surface-400">{{ row[col.key] ?? '-' }}</span>
                      <!-- Dec3 -->
                      <span v-else-if="col.format === 'dec3'" class="font-mono text-surface-500">{{ row[col.key]?.toFixed(3) ?? '-' }}</span>
                      <!-- Default -->
                      <span v-else class="font-mono text-surface-400">{{ row[col.key] ?? '-' }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="filteredAuditRows(ps, section, gi).length === 0" class="text-center py-4 text-surface-600 text-xs">No decisions match the current filter</div>
            <div v-if="totalAuditRows(ps, section) > (section.max_rows || 200)" class="text-center py-2 text-surface-500 text-[10px]">
              Showing {{ section.max_rows || 200 }} of {{ totalAuditRows(ps, section) }} decisions.
            </div>
          </div>

          <!-- EXIT REASONS -->
          <div v-if="section.type === 'exit_reasons' && resolve(ps, section.data_key) && Object.keys(resolve(ps, section.data_key)).length" class="card mb-6">
            <h4 class="text-xs font-semibold text-surface-400 mb-3">{{ section.title }}</h4>
            <div class="space-y-2">
              <div v-for="(ex, reason) in resolve(ps, section.data_key)" :key="reason"
                   class="flex items-center gap-3 p-2 bg-surface-800/40 rounded">
                <span class="px-2 py-0.5 rounded text-[10px] font-mono min-w-[100px] text-center"
                      :class="exitReasonClass(reason, section)">{{ reason }}</span>
                <span class="text-[10px] font-mono text-surface-400 w-10 text-right">{{ ex.count }}x</span>
                <div class="flex-1 h-4 bg-surface-900 rounded-sm overflow-hidden">
                  <div class="h-full transition-all rounded-sm" :class="ex.pnl >= 0 ? 'bg-green-500/40' : 'bg-red-500/40'"
                       :style="{width: maxExitPnl(ps, section) > 0 ? (Math.abs(ex.pnl)/maxExitPnl(ps, section)*100)+'%' : '0%'}"></div>
                </div>
                <span class="text-xs font-mono w-20 text-right" :class="ex.pnl >= 0 ? 'text-green-400' : 'text-red-400'">
                  {{ ex.pnl >= 0 ? '+' : '' }}{{ ex.pnl.toFixed(2) }}
                </span>
              </div>
            </div>
          </div>

        </template>
          </template>
        </template>
      </template>
    </div>

    <!-- Empty state -->
    <div v-if="!stats || Object.keys(stats).length === 0" class="text-center py-12 text-surface-500">
      <p class="text-sm">No pipeline data available</p>
      <p class="text-xs mt-1">Run a backtest with pipelines enabled to see intelligence analytics</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted, reactive, computed } from 'vue'

const props = defineProps({
  stats: { type: Object, default: null },
  sessionId: { type: String, default: null },
})

// ── Lazy loading for heavy data ──
const heavyLoading = reactive({})
const heavyLoaded = reactive({})

async function loadHeavyData(route) {
  if (heavyLoading[route] || heavyLoaded[route]) return
  heavyLoading[route] = true
  try {
    const id = props.sessionId
    if (!id) { heavyLoading[route] = false; return }
    const { default: api } = await import('../api.js')
    const res = await api.getBacktestPipelineStatsFull(id)
    const fullStats = res?.pipeline_stats || res?.data?.pipeline_stats
    if (fullStats && fullStats[route]) {
      // Merge heavy data into current stats — use Object.freeze to prevent Vue deep reactivity
      const heavy = fullStats[route]
      const ps = props.stats[route]
      if (ps) {
        // Freeze arrays before merging to prevent deep watcher from walking them
        const keysToMerge = [
          'danger_scores', 'cycle_outcomes', 'gate_decisions', 'abort_decisions',
          'gate_threshold_series', 'consultation_log', 'confidence_series',
          'size_adjustments', 'exit_suggestions', 'q_value_progression'
        ]
        for (const key of keysToMerge) {
          if (heavy[key] && Array.isArray(heavy[key])) {
            ps[key] = Object.freeze(heavy[key])
          }
        }
        // Also merge any _ui override from heavy data
        if (heavy._ui_full) {
          ps._ui = heavy._ui_full
        }
      }
    }
    heavyLoaded[route] = true
    await nextTick()
    drawAllCharts(props.stats)
  } catch (e) {
    console.error('Failed to load full pipeline stats:', e)
  }
  heavyLoading[route] = false
}

// ── Chart refs ──
const chartEls = reactive({})
let _pendingDraw = null
function registerChartEl(key, el) {
  if (el) {
    chartEls[key] = Array.isArray(el) ? el[0] : el
    // Canvas just appeared in DOM — schedule a redraw so charts render
    // (covers the case where component mounted while hidden in a v-if tab)
    if (!_pendingDraw) {
      _pendingDraw = setTimeout(() => {
        _pendingDraw = null
        drawAllCharts(props.stats)
      }, 50)
    }
  }
}

// ── Audit state ──
const auditFilters = reactive({})
const auditSorts = reactive({})

function sortAuditCol(gi, key) {
  if (!auditSorts[gi] || auditSorts[gi].key !== key) {
    auditSorts[gi] = { key, dir: key === 'ts' ? -1 : 1 }
  } else {
    auditSorts[gi].dir *= -1
  }
}

// ── Export ──

function exportReport(ps, route) {
  // Build a clean export object: strip _ui metadata, keep all analytics
  const exported = {}
  for (const [k, v] of Object.entries(ps)) {
    if (k === '_ui' || k === '_architecture') continue
    exported[k] = v
  }
  exported._route = route
  exported._exported_at = new Date().toISOString()

  const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const pipelineName = ps.pipeline_name || 'pipeline'
  const ts = new Date().toISOString().slice(0, 10)
  a.href = url
  a.download = `${pipelineName}_report_${route}_${ts}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ── Core helpers ──

function ui(ps) {
  if (ps && ps._ui) {
    console.log('[PipelineIntelligence] ui sections:', ps._ui.sections?.length, 'keys in ps:', Object.keys(ps).slice(0, 15))
    console.log('[PipelineIntelligence] signal_distribution:', ps.signal_distribution)
    console.log('[PipelineIntelligence] level_performance:', ps.level_performance)
    console.log('[PipelineIntelligence] cycles:', ps.cycles)
  }
  return ps?._ui || null
}

function groupedSections(ps) {
  const sections = ui(ps)?.sections || []
  const groups = []
  let halfBuf = []

  for (const section of sections) {
    if (section.type === 'kv_pairs' && section.grid === 'half') {
      halfBuf.push(section)
      // Flush when we have 2
      if (halfBuf.length === 2) {
        groups.push({ type: 'half_group', items: [...halfBuf] })
        halfBuf = []
      }
    } else {
      // Flush any pending half items
      if (halfBuf.length) {
        groups.push({ type: 'half_group', items: [...halfBuf] })
        halfBuf = []
      }
      groups.push({ type: 'single', item: section })
    }
  }
  // Flush remaining
  if (halfBuf.length) {
    groups.push({ type: 'half_group', items: [...halfBuf] })
  }
  return groups
}

function resolve(obj, path) {
  if (!path || !obj) return undefined
  return path.split('.').reduce((o, k) => o?.[k], obj)
}

function resolveNum(obj, path) {
  const v = resolve(obj, path)
  return typeof v === 'number' ? v : null
}

// ── Badge styling ──
function badgeClass(color) {
  const map = {
    brand: 'bg-brand-500/10 text-brand-400',
    green: 'bg-green-500/10 text-green-400',
    amber: 'bg-amber-500/10 text-amber-400',
    red: 'bg-red-500/10 text-red-400',
    surface: 'bg-surface-700 text-surface-400',
  }
  return map[color] || map.surface
}

// ── Icons ──
function iconPath(icon) {
  const icons = {
    shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
    filter: 'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
    block: 'M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636',
    abort: 'M10 15l-5.878 5.878M15 10l5.878-5.878M10 15l5.878 5.878M15 10L9.122 4.122',
    chart: 'M3 3v18h18M9 17V9m4 8V5m4 12v-4',
    danger: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
    layers: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  }
  return icons[icon] || icons.chart
}

// ── Metric formatting ──
function formatMetric(mc, ps) {
  const v = resolve(ps, mc.key)
  if (v == null) return '-'
  if (mc.format === 'pct') return ((v) * 100).toFixed(1) + '%'
  if (mc.format === 'currency') return (mc.prefix || '') + (typeof v === 'number' ? v.toFixed(2) : v)
  if (mc.format === 'dec3') return typeof v === 'number' ? v.toFixed(3) : v
  if (mc.format === 'dec4') return typeof v === 'number' ? v.toFixed(4) : v
  if (mc.format === 'int') return typeof v === 'number' ? Math.round(v).toLocaleString() : v
  if (mc.format === 'text') return String(v ?? '-')
  return String(v)
}

function metricColor(mc, ps) {
  const v = resolve(ps, mc.key)
  if (mc.color === 'green') return 'text-green-400'
  if (mc.color === 'amber') return 'text-amber-400'
  if (mc.color === 'red') return 'text-red-400'
  if (mc.threshold && v != null) {
    if (v >= mc.threshold[1]) return 'text-green-400'
    if (v >= mc.threshold[0]) return 'text-amber-400'
    return 'text-red-400'
  }
  if (mc.threshold_inv && v != null) {
    if (v <= mc.threshold_inv[0]) return 'text-green-400'
    if (v <= mc.threshold_inv[1]) return 'text-amber-400'
    return 'text-red-400'
  }
  return 'text-surface-100'
}

function metricSub(mc, ps) {
  if (!mc.sub_template) return null
  return mc.sub_template.replace(/\{([^}]+)\}/g, (_, path) => {
    const v = resolve(ps, path)
    if (v == null) return '-'
    if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(3)
    return String(v)
  })
}

// ── Template rendering (with color tags) ──
function renderTemplate(tmpl, ps) {
  let result = tmpl.replace(/\{([^}]+?)(?::\.(\d+)f)?\}/g, (_, path, decimals) => {
    const v = resolve(ps, path)
    if (v == null) return '-'
    if (decimals && typeof v === 'number') return v.toFixed(parseInt(decimals))
    if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(2)
    return String(v)
  })
  result = result.replace(/<green>(.*?)<\/green>/g, '<span class="text-green-400">$1</span>')
  result = result.replace(/<red>(.*?)<\/red>/g, '<span class="text-red-400">$1</span>')
  result = result.replace(/<amber>(.*?)<\/amber>/g, '<span class="text-amber-400">$1</span>')
  return result
}

// ── KV pairs formatting ──
function formatKvValue(item, ps) {
  const v = resolve(ps, item.key)
  if (v == null && item.fallback_key) {
    const fb = resolve(ps, item.fallback_key)
    return formatValue(fb, item.format, item.prefix)
  }
  return formatValue(v, item.format, item.prefix)
}

function formatValue(v, format, prefix) {
  if (v == null) return '-'
  if (format === 'pct') return ((v) * 100).toFixed(1) + '%'
  if (format === 'currency') return (prefix || '') + v.toFixed(2)
  if (format === 'currency_signed') return (v >= 0 ? '+' : '') + v.toFixed(2)
  if (format === 'dec1') return v.toFixed(1)
  if (format === 'dec3') return v.toFixed(3)
  if (format === 'dec4') return v.toFixed(4)
  if (format === 'int') return typeof v === 'number' ? Math.round(v).toLocaleString() : v
  return String(v)
}

function kvValueColor(item, ps) {
  if (item.color === 'green') return 'text-green-400'
  if (item.color === 'red') return 'text-red-400'
  if (item.threshold) {
    const v = resolve(ps, item.key)
    if (v != null && v >= item.threshold[1]) return 'text-green-400'
    if (v != null && v >= item.threshold[0]) return 'text-amber-400'
    if (v != null) return 'text-red-400'
  }
  const v = resolve(ps, item.key)
  if (item.format === 'currency_signed' && v != null) return v >= 0 ? 'text-green-400' : 'text-red-400'
  return 'text-surface-300'
}

function formatAutoValue(val) {
  if (val == null) return '-'
  if (typeof val === 'number') return Number.isInteger(val) ? val.toLocaleString() : val.toFixed(4)
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function humanize(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ── Bar breakdown helpers ──
function barLabelColor(level, section) {
  const lc = section.label_colors?.[String(level)]
  if (lc) return `text-${lc}-400`
  return `text-${section.default_label_color || 'surface'}-400`
}

function barWidth(data, allData) {
  const val = typeof data === 'number' ? data : data?.count || 0
  // allData can be an object or array of [key, val] entries
  const values = Array.isArray(allData)
    ? allData.map(([, d]) => typeof d === 'number' ? d : d?.count || 0)
    : Object.values(allData).map(d => typeof d === 'number' ? d : d?.count || 0)
  const max = Math.max(...values, 1)
  return (val / max * 100) + '%'
}

function processedBarData(ps, section) {
  const raw = resolve(ps, section.data_key)
  if (!raw) return []
  let entries = Object.entries(raw)
  // Sort by value desc if requested
  if (section.sort_by_value) {
    entries.sort((a, b) => {
      const va = typeof a[1] === 'number' ? a[1] : a[1]?.count || 0
      const vb = typeof b[1] === 'number' ? b[1] : b[1]?.count || 0
      return vb - va
    })
  }
  // Limit
  if (section.max_items && entries.length > section.max_items) {
    entries = entries.slice(0, section.max_items)
  }
  return entries
}

// ── Bucket table helpers ──
function bucketLabelColor(label, section) {
  const colorMap = section.bucket_colors || {}
  const c = colorMap[label]
  if (c === 'green-light') return 'text-green-300'
  if (c) return `text-${c}-400`
  return 'text-surface-400'
}

function bucketBarColorClass(label, section) {
  const colorMap = section.bucket_colors || {}
  const c = colorMap[label]
  if (c === 'green-light') return 'bg-green-400/60'
  if (c) return `bg-${c}-500/60`
  return 'bg-surface-500/60'
}

function bucketTotal(ps, section) {
  const data = resolve(ps, section.data_key)
  if (!data) return 1
  return Object.values(data).reduce((a, b) => a + (b.count || 0), 0) || 1
}

function formatFooterStat(fs, ps) {
  const v = resolve(ps, fs.key)
  if (v == null) return '-'
  if (fs.format === 'pct') return ((v) * 100).toFixed(1) + '%'
  if (fs.format === 'dec3') return v.toFixed(3)
  return String(v)
}

// ── Exit reasons ──
function exitReasonClass(reason, section) {
  const colorMap = section.reason_colors || {}
  const c = colorMap[reason]
  if (c === 'green') return 'bg-green-500/20 text-green-400'
  if (c === 'amber') return 'bg-amber-500/20 text-amber-400'
  if (c === 'red') return 'bg-red-500/20 text-red-400'
  // Check partial matches
  for (const [key, col] of Object.entries(colorMap)) {
    if (reason.includes(key)) {
      if (col === 'green') return 'bg-green-500/20 text-green-400'
      if (col === 'amber') return 'bg-amber-500/20 text-amber-400'
      if (col === 'red') return 'bg-red-500/20 text-red-400'
    }
  }
  return 'bg-surface-700 text-surface-400'
}

function maxExitPnl(ps, section) {
  const data = resolve(ps, section.data_key)
  if (!data) return 1
  return Math.max(...Object.values(data).map(e => Math.abs(e.pnl)), 1)
}

// ── Audit table ──
function buildAuditRows(ps, section) {
  const rows = []
  for (const source of (section.sources || [])) {
    const data = resolve(ps, source.data_key)
    if (!Array.isArray(data)) continue
    for (const rec of data) {
      const row = { type: source.type_label }
      for (const [outKey, mapping] of Object.entries(source.map)) {
        if (typeof mapping === 'string') {
          row[outKey] = rec[mapping]
        } else if (typeof mapping === 'object' && mapping.key) {
          const rawVal = rec[mapping.key]
          if (rawVal === true && mapping.true) row[outKey] = mapping.true
          else if (rawVal === false && mapping.false) row[outKey] = mapping.false
          else row[outKey] = mapping[String(rawVal)] ?? mapping._default ?? rawVal
        }
      }
      rows.push(row)
    }
  }
  return rows
}

function filteredAuditRows(ps, section, gi) {
  let rows = buildAuditRows(ps, section)
  const filterVal = auditFilters[gi] || 'all'
  if (filterVal !== 'all') {
    const filterDef = section.filters?.find(f => f.value === filterVal)
    if (filterDef?.match) {
      rows = rows.filter(r => {
        return Object.entries(filterDef.match).every(([k, v]) => r[k] === v)
      })
    }
  }
  const sort = auditSorts[gi] || { key: 'ts', dir: -1 }
  rows.sort((a, b) => {
    const va = a[sort.key] ?? -Infinity
    const vb = b[sort.key] ?? -Infinity
    return ((typeof va === 'number' ? va : 0) - (typeof vb === 'number' ? vb : 0)) * sort.dir
  })
  return rows.slice(0, section.max_rows || 200)
}

function totalAuditRows(ps, section) {
  let total = 0
  for (const source of (section.sources || [])) {
    const data = resolve(ps, source.data_key)
    if (Array.isArray(data)) total += data.length
  }
  return total
}

function typeBadgeClass(type) {
  if (type === 'gate') return 'bg-blue-500/15 text-blue-400'
  if (type === 'abort') return 'bg-purple-500/15 text-purple-400'
  return 'bg-surface-700 text-surface-400'
}

function decisionBadgeClass(decision) {
  if (decision === 'BLOCKED') return 'bg-red-500/20 text-red-400'
  if (decision === 'ALLOWED') return 'bg-green-500/20 text-green-400'
  if (decision === 'ABORT') return 'bg-amber-500/20 text-amber-400'
  return 'bg-surface-700 text-surface-400'
}

function thresholdColor(val, thresholds) {
  if (val == null) return 'text-surface-600'
  if (thresholds.red != null && val > thresholds.red) return 'text-red-400'
  if (thresholds.amber != null && val > thresholds.amber) return 'text-amber-400'
  return 'text-green-400'
}

// ── Table rows for kv_table ──
function tableRows(ps, section) {
  const data = resolve(ps, section.data_key)
  if (!data) return []
  let rows
  if (Array.isArray(data)) {
    rows = data
  } else {
    rows = Object.entries(data).map(([key, val]) => {
      if (typeof val === 'object' && val !== null) return { island: key, ...val }
      return { key, value: val }
    })
  }
  // Hide empty rows (all values null/0)
  if (section.hide_empty) {
    rows = rows.filter(row => {
      return section.columns.some(col => {
        if (col.key === 'island' || col.key === 'key') return false
        const v = row[col.key]
        return v != null && v !== 0
      })
    })
  }
  // Sort
  if (section.sort_key) {
    const desc = section.sort_desc ? -1 : 1
    rows.sort((a, b) => {
      const va = a[section.sort_key] ?? -Infinity
      const vb = b[section.sort_key] ?? -Infinity
      return (vb - va) * desc
    })
  }
  // Limit
  if (section.max_items && rows.length > section.max_items) {
    rows = rows.slice(0, section.max_items)
  }
  return rows
}

function formatTableCell(val, col) {
  if (val == null) return '-'
  if (col.format === 'dec4' && typeof val === 'number') return val.toFixed(4)
  if (col.format === 'int' && typeof val === 'number') return Math.round(val).toLocaleString()
  return String(val)
}

// ── Scatter chart ──
function scatterSummary(ps, section) {
  const data = resolve(ps, section.data_key)
  if (!data?.length) return null
  const withX = data.filter(c => c[section.x_key] != null)
  return withX.length >= 2
}

function computedSummaryStats(ps, section) {
  const data = resolve(ps, section.data_key)
  if (!data?.length) return []
  const withX = data.filter(c => c[section.x_key] != null)
  if (withX.length < 2) return []

  return (section.summary_stats || []).map(ss => {
    if (ss.compute === 'correlation') {
      const xs = withX.map(c => c[ss.x])
      const ys = withX.map(c => c[ss.y])
      const n = xs.length
      const mx = xs.reduce((a, b) => a + b, 0) / n
      const my = ys.reduce((a, b) => a + b, 0) / n
      let num = 0, dx2 = 0, dy2 = 0
      for (let i = 0; i < n; i++) {
        const dx = xs[i] - mx, dy = ys[i] - my
        num += dx * dy; dx2 += dx * dx; dy2 += dy * dy
      }
      const corr = (dx2 > 0 && dy2 > 0) ? num / Math.sqrt(dx2 * dy2) : 0
      return {
        label: ss.label,
        display: corr.toFixed(3),
        colorClass: Math.abs(corr) > 0.3 ? 'text-amber-400' : 'text-surface-300',
      }
    }
    if (ss.compute === 'sum_filtered') {
      // Parse simple filter like "danger_at_entry > 0.7"
      const match = ss.filter.match(/(\w+)\s*(>|<|>=|<=|==)\s*([\d.]+)/)
      if (!match) return { label: ss.label, display: '-', colorClass: 'text-surface-300' }
      const [, field, op, threshold] = match
      const th = parseFloat(threshold)
      const filtered = withX.filter(c => {
        const v = c[field]
        if (v == null) return false
        if (op === '>') return v > th
        if (op === '<') return v < th
        if (op === '>=') return v >= th
        if (op === '<=') return v <= th
        if (op === '==') return v === th
        return false
      })
      const sum = filtered.reduce((a, c) => a + (c[ss.key] || 0), 0)
      return {
        label: ss.label,
        display: sum.toFixed(2),
        colorClass: sum >= 0 ? 'text-green-400' : 'text-red-400',
      }
    }
    if (ss.key) {
      const v = resolve(ps, ss.key)
      return {
        label: ss.label,
        display: v != null ? (ss.format === 'dec3' ? v.toFixed(3) : String(v)) : '-',
        colorClass: ss.color ? `text-${ss.color}-400` : 'text-surface-300',
      }
    }
    return { label: ss.label, display: '-', colorClass: 'text-surface-300' }
  })
}

// ── Line chart summary stats ──
function resolvedSummaryStats(ps, summaryStats) {
  return (summaryStats || []).map(ss => {
    if (ss.template) {
      const display = ss.template.replace(/\{([^}]+)\}/g, (_, path) => {
        const v = resolve(ps, path)
        return v != null ? String(v) : '0'
      })
      return { label: ss.label, display, colorClass: ss.color ? `text-${ss.color}-400` : 'text-surface-300' }
    }
    if (ss.key) {
      const v = resolve(ps, ss.key)
      let display = '-'
      if (v != null) {
        if (ss.format === 'pct') display = ((v) * 100).toFixed(1) + '%'
        else if (ss.format === 'dec4') display = v.toFixed(4)
        else display = String(v)
      }
      return { label: ss.label, display, colorClass: ss.color ? `text-${ss.color}-400` : 'text-surface-300' }
    }
    return { label: ss.label, display: '-', colorClass: 'text-surface-300' }
  })
}

// ── Timestamp formatting ──
function formatTs(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}

// ══════════════════════════════════════════════
// CHART DRAWING (scatter + line)
// ══════════════════════════════════════════════

function drawAllCharts(stats) {
  if (!stats) return
  for (const [route, ps] of Object.entries(stats)) {
    const groups = groupedSections(ps)
    groups.forEach((group, gi) => {
      if (group.type !== 'single') return
      const section = group.item
      if (section.type === 'scatter') {
        const key = 'scatter_' + gi + '_' + route
        const el = chartEls[key]
        if (el) drawScatterChart(el, ps, section)
      }
      if (section.type === 'line_chart') {
        const data = resolve(ps, section.data_key)
        if (data?.length) {
          const key = 'line_' + gi + '_' + route
          const el = chartEls[key]
          if (el) drawLineChart(el, ps, section)
        }
      }
    })
  }
}

function drawScatterChart(el, ps, section) {
  const outcomes = resolve(ps, section.data_key)
  if (!outcomes?.length) return
  const filtered = outcomes.filter(c => c[section.x_key] != null)
  if (!filtered.length) return

  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight

  let canvas = el.querySelector('canvas')
  if (!canvas) { canvas = document.createElement('canvas'); el.innerHTML = ''; el.appendChild(canvas) }
  canvas.width = w * dpr; canvas.height = h * dpr
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px'

  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const pad = { top: 20, right: 20, bottom: 35, left: 55 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom

  const xs = filtered.map(c => c[section.x_key])
  const ys = filtered.map(c => c[section.y_key])
  const minX = 0, maxX = 1
  const minY = Math.min(...ys, 0), maxY = Math.max(...ys, 0)
  const rangeY = maxY - minY || 1

  // Background
  ctx.fillStyle = '#1a1b23'; ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = '#1e1f2b'; ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ph / 4) * i
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }
  for (let i = 0; i <= 4; i++) {
    const x = pad.left + (pw / 4) * i
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, h - pad.bottom); ctx.stroke()
  }

  // Reference lines
  for (const ref of (section.ref_lines || [])) {
    ctx.strokeStyle = ref.color || '#333'
    ctx.lineWidth = 1; ctx.setLineDash([4, 4])
    if (ref.axis === 'y') {
      const yPos = pad.top + ph * (1 - (ref.value - minY) / rangeY)
      if (yPos >= pad.top && yPos <= pad.top + ph) {
        ctx.beginPath(); ctx.moveTo(pad.left, yPos); ctx.lineTo(w - pad.right, yPos); ctx.stroke()
      }
    } else if (ref.axis === 'x') {
      const val = ref.value ?? resolve(ps, ref.key)
      if (val != null) {
        const xPos = pad.left + pw * ((val - minX) / (maxX - minX))
        ctx.beginPath(); ctx.moveTo(xPos, pad.top); ctx.lineTo(xPos, h - pad.bottom); ctx.stroke()
        if (ref.label) {
          ctx.setLineDash([]); ctx.fillStyle = ref.color || '#ef4444'
          ctx.font = '9px monospace'; ctx.fillText(ref.label, xPos + 3, pad.top + 10)
        }
      }
    }
    ctx.setLineDash([])
  }

  // Build color map
  const colorMap = section.color_map || {}
  const defaultColor = colorMap._default?.color || '#64748b'

  // Plot points
  for (const c of filtered) {
    const x = pad.left + pw * ((c[section.x_key] - minX) / (maxX - minX))
    const y = pad.top + ph * (1 - (c[section.y_key] - minY) / rangeY)
    const r = Math.min(2 + (c[section.size_key] || 0) * 1.5, 10)
    const cm = colorMap[c[section.color_key]] || colorMap._default
    const color = cm?.color || defaultColor

    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fillStyle = color + '99'; ctx.fill()
    ctx.strokeStyle = color; ctx.lineWidth = 0.5; ctx.stroke()
  }

  // Axes labels
  ctx.fillStyle = '#666'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText(section.x_label || '', pad.left + pw / 2, h - 5)
  for (let i = 0; i <= 4; i++) {
    const v = minX + (maxX - minX) * i / 4
    ctx.fillText(v.toFixed(2), pad.left + pw * i / 4, h - pad.bottom + 14)
  }

  ctx.save()
  ctx.translate(12, pad.top + ph / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'
  ctx.fillText(section.y_label || '', 0, 0); ctx.restore()

  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = minY + rangeY * (1 - i / 4)
    ctx.fillText(v.toFixed(1), pad.left - 5, pad.top + ph * i / 4 + 4)
  }
}

function drawLineChart(el, ps, section) {
  const data = resolve(ps, section.data_key)
  if (!data?.length) return

  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth, h = el.clientHeight

  let canvas = el.querySelector('canvas')
  if (!canvas) { canvas = document.createElement('canvas'); el.innerHTML = ''; el.appendChild(canvas) }
  canvas.width = w * dpr; canvas.height = h * dpr
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px'

  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const hasRightAxis = section.series?.some(s => s.axis === 'right')
  const pad = { top: 15, right: hasRightAxis ? 50 : 20, bottom: 30, left: 55 }
  const pw = w - pad.left - pad.right, ph = h - pad.top - pad.bottom
  const n = data.length

  // Background
  ctx.fillStyle = '#1a1b23'; ctx.fillRect(0, 0, w, h)

  // Compute ranges for left axis
  const leftSeries = section.series.filter(s => s.axis !== 'right')
  let minLeft = Infinity, maxLeft = -Infinity
  for (const s of leftSeries) {
    const vals = data.map(d => d[s.index])
    // For band_of, include band range
    if (s.band_of != null) {
      const mainSeries = section.series.find(ms => ms.index === s.band_of)
      if (mainSeries) {
        const mains = data.map(d => d[mainSeries.index])
        for (let i = 0; i < n; i++) {
          minLeft = Math.min(minLeft, mains[i] - vals[i])
          maxLeft = Math.max(maxLeft, mains[i] + vals[i])
        }
        continue
      }
    }
    for (const v of vals) {
      if (v < minLeft) minLeft = v
      if (v > maxLeft) maxLeft = v
    }
  }
  const rangeLeft = maxLeft - minLeft || 1

  // Grid
  ctx.strokeStyle = '#1e1f2b'; ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ph * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }

  // Draw series
  for (const s of section.series) {
    const vals = data.map(d => d[s.index])

    if (s.band_of != null) {
      // Band fill
      const mainSeries = section.series.find(ms => ms.index === s.band_of)
      if (!mainSeries) continue
      const mains = data.map(d => d[mainSeries.index])
      ctx.fillStyle = s.color.replace(')', ',0.08)').replace('rgb', 'rgba') || 'rgba(251,191,36,0.08)'
      ctx.beginPath()
      for (let i = 0; i < n; i++) {
        const x = pad.left + pw * i / (n - 1)
        const y = pad.top + ph * (1 - (mains[i] + vals[i] - minLeft) / rangeLeft)
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      }
      for (let i = n - 1; i >= 0; i--) {
        const x = pad.left + pw * i / (n - 1)
        const y = pad.top + ph * (1 - (mains[i] - vals[i] - minLeft) / rangeLeft)
        ctx.lineTo(x, y)
      }
      ctx.closePath(); ctx.fill()
      continue
    }

    const isRight = s.axis === 'right'
    ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 1.5
    if (s.dashed) ctx.setLineDash([3, 3])

    ctx.beginPath()
    for (let i = 0; i < n; i++) {
      const x = pad.left + pw * i / (n - 1)
      let y
      if (isRight) {
        y = pad.top + ph * (1 - vals[i])  // right axis is 0-1 (coverage)
      } else {
        y = pad.top + ph * (1 - (vals[i] - minLeft) / rangeLeft)
      }
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.stroke()
    ctx.setLineDash([])
  }

  // Labels
  ctx.fillStyle = '#666'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText(section.x_label || 'Cycle', pad.left + pw / 2, h - 5)

  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = minLeft + rangeLeft * (1 - i / 4)
    ctx.fillText(v.toFixed(4), pad.left - 5, pad.top + ph * i / 4 + 4)
  }

  if (hasRightAxis) {
    const rightSeries = section.series.find(s => s.axis === 'right')
    ctx.textAlign = 'left'
    ctx.fillStyle = rightSeries?.color || '#4ade80'
    for (let i = 0; i <= 4; i++) {
      const v = (1 - i / 4) * 100
      ctx.fillText(v.toFixed(0) + '%', w - pad.right + 5, pad.top + ph * i / 4 + 4)
    }
  }
}

// ── Redraw on data change ──
watch(() => props.stats, async () => {
  await nextTick()
  drawAllCharts(props.stats)
}, { immediate: true, deep: true })

// Resize handler
let resizeObserver = null
function setupResize() {
  if (resizeObserver) resizeObserver.disconnect()
  resizeObserver = new ResizeObserver(() => drawAllCharts(props.stats))
  for (const el of Object.values(chartEls)) {
    if (el) resizeObserver.observe(el)
  }
}

watch(chartEls, () => {
  setupResize()
  nextTick(() => drawAllCharts(props.stats))
}, { deep: true })

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
  if (_pendingDraw) { clearTimeout(_pendingDraw); _pendingDraw = null }
})
</script>
