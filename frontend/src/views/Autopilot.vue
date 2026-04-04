<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Autopilot</h1>
        <p class="text-xs text-surface-500 mt-0.5">Automated hyperparameter tuning with pipeline learning across repeated backtests</p>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="running" class="flex items-center gap-1.5 text-xs text-green-400">
          <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          Running iteration {{ currentIteration + 1 }}/{{ maxIterations }}
        </span>
        <button v-if="running" @click="cancelRun" class="btn-sm bg-red-500/20 text-red-400 hover:bg-red-500/30">Cancel</button>
      </div>
    </div>

    <!-- ═══ Pipeline Registry + Launch (when not running + no results) ═══ -->
    <div v-if="!running && !hasResults" class="space-y-6">

      <!-- Loading state -->
      <div v-if="loadingPipelines" class="card text-center py-8">
        <div class="inline-block w-5 h-5 border-2 border-surface-600 border-t-brand-400 rounded-full animate-spin"></div>
        <p class="text-xs text-surface-500 mt-2">Loading pipeline registry...</p>
      </div>

      <!-- No pipelines -->
      <div v-else-if="!registeredPipelines.length" class="card text-center py-8">
        <svg class="w-10 h-10 text-surface-700 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"/></svg>
        <p class="text-surface-500 text-sm">No pipelines registered</p>
        <p class="text-xs text-surface-600 mt-1">Create a pipeline in the Pipelines page to get started.</p>
      </div>

      <!-- Pipeline Cards — 2-column grid on large screens -->
      <template v-else>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div v-for="pipeline in registeredPipelines" :key="pipeline.name"
               class="card cursor-pointer hover:border-surface-600 transition-colors"
               :class="expandedPipeline === pipeline.name ? 'border-brand-500/30 lg:col-span-2' : ''"
               @click="toggleExpand(pipeline.name)">

            <!-- ── Compact Card (always visible) ── -->
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1 min-w-0">
                <!-- Header row: icon + name + status -->
                <div class="flex items-center gap-2 mb-2">
                  <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                       :class="pipeline.architecture?.training_status === 'ready' || pipeline.architecture?.training_status === 'trained' ? 'bg-green-500/15' : 'bg-amber-500/15'">
                    <svg class="w-4 h-4" :class="pipeline.architecture?.training_status === 'ready' || pipeline.architecture?.training_status === 'trained' ? 'text-green-400' : 'text-amber-400'" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25a2.25 2.25 0 01-2.25-2.25v-2.25z"/></svg>
                  </div>
                  <h2 class="text-base font-bold text-surface-100">{{ pipeline.name }}</h2>
                  <span v-if="pipeline.architecture?.training_status === 'ready'" class="px-1.5 py-0.5 rounded text-[9px] font-medium bg-green-500/15 text-green-400">Ready</span>
                  <span v-else-if="pipeline.architecture?.training_status === 'trained'" class="px-1.5 py-0.5 rounded text-[9px] font-medium bg-blue-500/15 text-blue-400">Trained</span>
                  <span v-else-if="pipeline.architecture?.requires_training" class="px-1.5 py-0.5 rounded text-[9px] font-medium bg-amber-500/15 text-amber-400">Needs training</span>
                  <span v-if="trainingInProgress[pipeline.name]" class="px-1.5 py-0.5 rounded text-[9px] font-medium bg-purple-500/15 text-purple-400 flex items-center gap-1">
                    <svg class="w-2.5 h-2.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
                    Training
                  </span>
                </div>

                <!-- Summary -->
                <p class="text-[11px] text-surface-400 leading-relaxed mb-2.5">{{ pipeline.architecture?.summary || pipeline.description }}</p>

                <!-- High-level layer flow: name1 → name2 → name3 -->
                <div v-if="pipeline.architecture?.layers?.length" class="flex items-center flex-wrap gap-1 mb-2">
                  <template v-for="(layer, li) in pipeline.architecture.layers" :key="layer.name">
                    <span class="px-1.5 py-0.5 rounded text-[9px] font-mono border" :class="layerTypeColor(layer.type) + ' border-transparent'">{{ layer.name }}</span>
                    <svg v-if="li < pipeline.architecture.layers.length - 1" class="w-3 h-3 text-surface-700 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
                  </template>
                </div>

                <!-- Strategy tags + research -->
                <div class="flex items-center gap-2 flex-wrap">
                  <span v-for="target in (pipeline.architecture?.designed_for || [])" :key="target"
                        class="px-1.5 py-0.5 bg-surface-800 rounded text-[9px] text-surface-500">{{ target }}</span>
                  <span v-if="pipeline.architecture?.research_basis" class="text-[9px] text-surface-600">{{ pipeline.architecture.research_basis }}</span>
                </div>
              </div>

              <!-- Action buttons (stop propagation to prevent card toggle) -->
              <div class="flex flex-col gap-1.5 shrink-0" @click.stop>
                <button v-if="pipeline.architecture?.requires_training && pipeline.architecture?.training_status !== 'trained' && !trainingInProgress[pipeline.name]"
                        @click="trainPipeline(pipeline.name)"
                        class="btn-sm text-[11px] bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 flex items-center gap-1">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.964m11.49-9.642l1.149-.964M7.501 19.795l.75-1.3m7.5-12.99l.75-1.3m-6.063 16.658l.26-1.477m2.605-14.772l.26-1.477m0 17.726l-.26-1.477M10.698 4.614l-.26-1.477M16.5 19.794l-.75-1.299M7.5 4.205L12 12"/></svg>
                  Train
                </button>
                <router-link to="/backtest" @click.stop
                             :class="['btn-sm text-[11px] flex items-center gap-1', (!pipeline.architecture?.requires_training || pipeline.architecture?.training_status === 'trained') ? 'bg-brand-500/20 text-brand-400 hover:bg-brand-500/30' : 'bg-surface-800 text-surface-600 pointer-events-none']">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z"/></svg>
                  Backtest
                </router-link>
              </div>
            </div>

            <!-- ── Expanded Detail (shown on click) ── -->
            <div v-if="expandedPipeline === pipeline.name" class="mt-4 pt-4 border-t border-surface-800 space-y-4" @click.stop>

              <!-- Training info -->
              <div v-if="pipeline.architecture?.training_description" class="p-3 bg-surface-850 rounded">
                <div class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">Training</div>
                <p class="text-xs text-surface-400 mb-2">{{ pipeline.architecture.training_description }}</p>
                <ol v-if="pipeline.architecture?.training_steps?.length" class="ml-4 space-y-0.5">
                  <li v-for="(step, si) in pipeline.architecture.training_steps" :key="si" class="text-[10px] text-surface-500 list-decimal">{{ step }}</li>
                </ol>
              </div>

              <!-- Layer Architecture -->
              <div v-if="pipeline.architecture?.layers?.length">
                <div class="flex items-center gap-2 mb-3">
                  <h3 class="text-xs font-semibold text-surface-500 uppercase tracking-wider">Pipeline Layers</h3>
                  <div class="flex-1 border-b border-surface-800"></div>
                </div>

                <div class="relative">
                  <div v-for="(layer, li) in pipeline.architecture.layers" :key="layer.name" class="relative">
                    <!-- Connector -->
                    <div v-if="li > 0" class="flex justify-center py-1">
                      <div class="flex flex-col items-center">
                        <div class="w-px h-3 bg-surface-700"></div>
                        <svg class="w-3 h-3 text-surface-600 -mt-0.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
                      </div>
                    </div>

                    <!-- Layer card -->
                    <div class="p-3 bg-surface-850 rounded border-l-2" :class="layerBorderColor(layer.type)">
                      <div class="flex items-start justify-between gap-3 mb-2">
                        <div class="flex items-center gap-2">
                          <div class="w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold" :class="layerBadgeColor(layer.type)">{{ layer.order }}</div>
                          <div>
                            <h4 class="text-xs font-semibold text-surface-200">{{ layer.name }}</h4>
                            <span class="text-[9px] font-mono px-1 py-0.5 rounded" :class="layerTypeColor(layer.type)">{{ layer.type }}</span>
                          </div>
                        </div>
                        <code class="text-[9px] font-mono text-surface-500 bg-surface-800 px-1.5 py-0.5 rounded shrink-0">{{ layer.hook }}</code>
                      </div>

                      <p class="text-[11px] text-surface-400 mb-2">{{ layer.description }}</p>

                      <div class="grid grid-cols-1 lg:grid-cols-2 gap-2">
                        <div class="space-y-1.5">
                          <div v-if="layer.algorithm" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-0.5">Algorithm</div>
                            <div class="text-[11px] text-surface-300">{{ layer.algorithm }}</div>
                          </div>
                          <div v-if="layer.output" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-0.5">Output</div>
                            <div class="text-[11px] text-surface-300 font-mono">{{ layer.output }}</div>
                          </div>
                          <div v-if="layer.mechanism" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-0.5">Mechanism</div>
                            <div class="text-[11px] text-surface-300">{{ layer.mechanism }}</div>
                          </div>
                          <div v-if="layer.normalization" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-0.5">Normalization</div>
                            <div class="text-[11px] text-surface-300">{{ layer.normalization }}</div>
                          </div>
                          <!-- Genome params (IslandEvolver) -->
                          <div v-if="layer.genome_params?.length" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Evolved Parameters</div>
                            <div class="flex flex-wrap gap-1">
                              <code v-for="p in layer.genome_params" :key="p" class="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 px-1 py-0.5 rounded">{{ p }}</code>
                            </div>
                          </div>
                          <!-- Factors (AdaptiveSizer) -->
                          <div v-if="layer.factors?.length" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Sizing Factors</div>
                            <ul class="space-y-0.5">
                              <li v-for="f in layer.factors" :key="f" class="text-[10px] text-surface-400 flex items-start gap-1.5">
                                <span class="text-orange-400 mt-0.5">*</span> {{ f }}
                              </li>
                            </ul>
                          </div>
                        </div>

                        <!-- Config keys -->
                        <div v-if="layer.config_keys" class="space-y-1.5">
                          <div class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Configuration</div>
                            <div class="space-y-1">
                              <div v-for="(desc, key) in layer.config_keys" :key="key" class="flex items-start gap-1.5">
                                <code class="text-[9px] font-mono text-brand-400 bg-brand-500/10 px-1 py-0.5 rounded shrink-0">{{ key }}</code>
                                <span class="text-[9px] text-surface-400">{{ desc }}</span>
                              </div>
                            </div>
                          </div>
                          <div v-if="layer.stats_tracked" class="p-2 bg-surface-900 rounded">
                            <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Stats Tracked</div>
                            <div class="flex flex-wrap gap-1">
                              <code v-for="s in layer.stats_tracked" :key="s" class="text-[9px] font-mono text-surface-400 bg-surface-800 px-1 py-0.5 rounded">{{ s }}</code>
                            </div>
                          </div>
                        </div>
                      </div>

                      <!-- Features table -->
                      <div v-if="layer.features?.length" class="mt-2 overflow-x-auto">
                        <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Input Features</div>
                        <table class="w-full text-[10px]">
                          <thead><tr class="text-surface-600 border-b border-surface-800"><th class="text-left py-1 px-1.5">Feature</th><th class="text-right py-1 px-1.5">Weight</th><th class="text-center py-1 px-1.5">Inv</th><th class="text-left py-1 px-1.5">Description</th></tr></thead>
                          <tbody>
                            <tr v-for="f in layer.features" :key="f.key" class="border-b border-surface-900">
                              <td class="py-1 px-1.5 font-mono text-brand-400">{{ f.key }}</td>
                              <td class="py-1 px-1.5 text-right font-mono text-surface-300">{{ (f.weight*100).toFixed(0) }}%</td>
                              <td class="py-1 px-1.5 text-center"><span :class="f.inverted ? 'text-amber-400' : 'text-surface-700'">{{ f.inverted ? 'Y' : '-' }}</span></td>
                              <td class="py-1 px-1.5 text-surface-400">{{ f.description }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>

                      <!-- State space -->
                      <div v-if="layer.state_space" class="mt-2">
                        <div class="flex items-center justify-between mb-1"><div class="text-[9px] text-surface-600 uppercase tracking-wider">State Space</div><span class="text-[9px] font-mono text-surface-500">{{ layer.state_space.total_states.toLocaleString() }} states</span></div>
                        <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 mb-1.5">
                          <div v-for="dim in layer.state_space.dimensions" :key="dim.name" class="p-1.5 bg-surface-900 rounded text-center">
                            <div class="text-[10px] font-mono text-surface-300">{{ dim.name }}</div>
                            <div class="text-sm font-bold text-surface-200">{{ dim.bins }}</div>
                            <div class="text-[8px] text-surface-600"><span v-if="dim.edges">{{ dim.edges.join(', ') }}</span><span v-else-if="dim.range">{{ dim.range }}</span></div>
                          </div>
                        </div>
                        <div class="flex items-center gap-2 text-[9px]">
                          <span class="text-surface-600">Actions:</span>
                          <span v-for="(label, key) in layer.state_space.actions" :key="key" class="px-1 py-0.5 rounded font-mono" :class="label === 'abort' ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'">{{ key }}:{{ label }}</span>
                        </div>
                      </div>

                      <!-- Pretrained stats -->
                      <div v-if="layer.pretrained" class="mt-2">
                        <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Pre-trained</div>
                        <div class="grid grid-cols-2 sm:grid-cols-5 gap-1.5">
                          <div v-for="(val, key) in layer.pretrained" :key="key" class="p-1.5 bg-surface-900 rounded text-center">
                            <div class="text-[8px] text-surface-600">{{ key.replace(/_/g, ' ') }}</div>
                            <div class="text-xs font-mono" :class="String(val).startsWith('-') ? 'text-green-400' : 'text-surface-200'">{{ val }}</div>
                          </div>
                        </div>
                      </div>

                      <!-- Modes -->
                      <div v-if="layer.modes?.length" class="mt-2">
                        <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Modes</div>
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-1.5">
                          <div v-for="m in layer.modes" :key="m.name" class="p-1.5 bg-surface-900 rounded">
                            <code class="text-[9px] font-mono font-bold" :class="m.name === 'eval' ? 'text-green-400' : m.name === 'train' ? 'text-amber-400' : 'text-surface-500'">{{ m.name }}</code>
                            <div class="text-[9px] text-surface-400 mt-0.5">{{ m.description }}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Lifecycle & Composition -->
              <div v-if="pipeline.architecture?.lifecycle?.length || pipeline.architecture?.composition_rules" class="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <div v-if="pipeline.architecture?.lifecycle?.length" class="p-3 bg-surface-850 rounded">
                  <h3 class="text-[10px] font-semibold text-surface-500 uppercase tracking-wider mb-2">Hook Lifecycle</h3>
                  <div class="space-y-0">
                    <div v-for="(hook, hi) in pipeline.architecture.lifecycle" :key="hook.hook"
                         class="flex items-start gap-2 py-1.5" :class="hi < pipeline.architecture.lifecycle.length - 1 ? 'border-b border-surface-800' : ''">
                      <div class="flex flex-col items-center shrink-0 mt-0.5">
                        <div class="w-1.5 h-1.5 rounded-full" :class="hookDotColor(hook.hook)"></div>
                        <div v-if="hi < pipeline.architecture.lifecycle.length - 1" class="w-px h-full min-h-[12px] bg-surface-800 mt-0.5"></div>
                      </div>
                      <div>
                        <code class="text-[9px] font-mono text-surface-400">{{ hook.hook }}</code>
                        <div class="text-[10px] text-surface-300 mt-0.5">{{ hook.description }}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="pipeline.architecture?.composition_rules" class="p-3 bg-surface-850 rounded">
                  <h3 class="text-[10px] font-semibold text-surface-500 uppercase tracking-wider mb-2">Composition Rules</h3>
                  <div class="space-y-1.5">
                    <div v-for="(rule, hook) in pipeline.architecture.composition_rules" :key="hook" class="p-2 bg-surface-900 rounded">
                      <code class="text-[9px] font-mono text-brand-400">{{ hook }}</code>
                      <div class="text-[10px] text-surface-300 mt-0.5">{{ rule }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Default config -->
              <div v-if="pipeline.default_config && Object.keys(pipeline.default_config).length" class="p-3 bg-surface-850 rounded">
                <div class="flex items-center justify-between mb-2">
                  <h3 class="text-[10px] font-semibold text-surface-500 uppercase tracking-wider">Default Configuration</h3>
                  <button @click.stop="copyConfig(pipeline.default_config)" class="text-[9px] text-surface-500 hover:text-surface-300 flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"/></svg>
                    Copy
                  </button>
                </div>
                <pre class="text-[10px] font-mono text-surface-400 bg-surface-900 rounded p-2 overflow-x-auto leading-relaxed max-h-[300px]">{{ JSON.stringify(pipeline.default_config, null, 2) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Launch CTA -->
      <div v-if="registeredPipelines.length" class="card bg-surface-850 border border-surface-700">
        <div class="flex items-center gap-3">
          <svg class="w-5 h-5 text-surface-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M11.25 4.5l7.5 7.5-7.5 7.5m-6-15l7.5 7.5-7.5 7.5"/></svg>
          <div class="flex-1">
            <p class="text-xs text-surface-300">Ready to run?</p>
            <p class="text-[10px] text-surface-600">Select "Pipeline" mode in Backtest, configure your strategy, and click "Run Autopilot" to start iterative tuning.</p>
          </div>
          <router-link to="/backtest" class="btn-primary btn-sm flex items-center gap-1.5 shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4.5h14.25M3 9h9.75M3 13.5h9.75m4.5-4.5v12m0 0l-3.75-3.75M17.25 21L21 17.25"/></svg>
            Go to Backtest
          </router-link>
        </div>
      </div>
    </div>

    <!-- ═══ Live Dashboard (during + after run) ═══ -->
    <div v-if="running || hasResults" class="space-y-6">

      <!-- Progress bar -->
      <div v-if="running" class="card">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs text-surface-500">Progress</span>
          <span class="text-xs font-mono text-surface-400">{{ currentIteration }}/{{ maxIterations }} iterations</span>
        </div>
        <div class="w-full h-2 bg-surface-800 rounded-full overflow-hidden">
          <div class="h-full bg-brand-500 transition-all duration-300 rounded-full" :style="{width: (currentIteration/maxIterations*100)+'%'}"></div>
        </div>
        <div class="flex justify-between mt-1 text-[10px] text-surface-600">
          <span v-if="elapsedTotal">Elapsed: {{ formatDuration(elapsedTotal) }}</span>
          <span v-if="avgIterTime">~{{ formatDuration(avgIterTime) }}/iter</span>
          <span v-if="avgIterTime && maxIterations > currentIteration">ETA: {{ formatDuration(avgIterTime * (maxIterations - currentIteration)) }}</span>
        </div>
      </div>

      <!-- Best Config Card -->
      <div v-if="bestResult" class="card border-green-500/20">
        <div class="flex items-center gap-2 mb-3">
          <svg class="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"/></svg>
          <h3 class="text-sm font-semibold text-green-400">Best Configuration</h3>
          <span class="text-[10px] text-surface-600 ml-auto">Iteration #{{ bestResult.iteration + 1 }}</span>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
          <div class="p-2 bg-surface-800 rounded">
            <div class="text-surface-500 text-[10px]">{{ objectiveKey }}</div>
            <div class="font-mono text-green-400 text-lg">{{ formatVal(bestResult.objective) }}</div>
          </div>
          <div v-for="(v, k) in bestResult.metrics" :key="k" class="p-2 bg-surface-800 rounded">
            <div class="text-surface-500 text-[10px]">{{ k }}</div>
            <div class="font-mono text-surface-200">{{ formatVal(v) }}</div>
          </div>
        </div>
        <div class="flex items-center justify-between">
          <div v-if="bestResult.hp && Object.keys(bestResult.hp).length" class="flex flex-wrap gap-2">
            <div v-for="(v, k) in bestResult.hp" :key="k" class="px-2 py-1 bg-green-500/10 border border-green-500/20 rounded text-xs">
              <span class="text-surface-500">{{ k }}:</span>
              <span class="text-green-400 font-mono ml-1">{{ formatVal(v) }}</span>
            </div>
          </div>
          <router-link v-if="bestResult.hp && Object.keys(bestResult.hp).length"
                       :to="{ path: '/backtest', query: { hp: JSON.stringify(bestResult.hp) } }"
                       class="btn-sm bg-brand-500/20 text-brand-400 hover:bg-brand-500/30 flex items-center gap-1.5 shrink-0 ml-3">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>
            Load into Backtest
          </router-link>
        </div>
      </div>

      <!-- Convergence Plot -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-xs font-semibold text-surface-400">Objective Convergence</h3>
          <span v-if="plateauInfo" class="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded" :class="plateauInfo.stale ? 'bg-amber-500/10 text-amber-400' : 'bg-green-500/10 text-green-400'">
            <svg v-if="plateauInfo.stale" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
            {{ plateauInfo.stale ? `No improvement in ${plateauInfo.sinceBest} iterations — consider stopping` : `Improving (best at iter #${plateauInfo.bestAt + 1})` }}
          </span>
        </div>
        <div ref="convergenceEl" class="w-full h-[280px]"></div>
      </div>

      <!-- Pipeline Learning Curve -->
      <div v-if="pipelineCoverage.length" class="card">
        <h3 class="text-xs font-semibold text-surface-400 mb-3">Pipeline Learning Progress</h3>
        <div ref="learningEl" class="w-full h-[220px]"></div>
      </div>

      <!-- HP Parallel Coordinates -->
      <div v-if="hpAxes.length >= 2" class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h3 class="text-xs font-semibold text-surface-400">Hyperparameter Space</h3>
            <p class="text-[10px] text-surface-600">Each line = one iteration. Color = objective value (green = better).</p>
          </div>
        </div>
        <div ref="parallelEl" class="w-full h-[280px]"></div>
      </div>

      <!-- Iteration History Table -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-xs font-semibold text-surface-400">Iteration History</h3>
          <span class="text-[10px] text-surface-600">{{ iterations.length }} iterations</span>
        </div>
        <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table class="w-full text-xs">
            <thead class="sticky top-0 bg-surface-900">
              <tr class="text-surface-500 border-b border-surface-700">
                <th class="text-left py-2 px-2">#</th>
                <th class="text-right py-2 px-2">{{ objectiveKey }}</th>
                <th class="text-right py-2 px-2">Win Rate</th>
                <th class="text-right py-2 px-2">Profit Factor</th>
                <th class="text-right py-2 px-2">Max DD%</th>
                <th class="text-right py-2 px-2">Trades</th>
                <th class="text-right py-2 px-2">Block Rate</th>
                <th class="text-right py-2 px-2">Abort Rate</th>
                <th class="text-right py-2 px-2">Coverage</th>
                <th class="text-right py-2 px-2">Time</th>
                <th class="text-left py-2 px-2">HP</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(it, i) in iterations" :key="i"
                  class="border-b border-surface-800/50 hover:bg-surface-800/30"
                  :class="bestResult && bestResult.iteration === i ? 'bg-green-500/5' : ''">
                <td class="py-1.5 px-2 font-mono" :class="bestResult && bestResult.iteration === i ? 'text-green-400 font-bold' : 'text-surface-400'">{{ i + 1 }}</td>
                <td class="py-1.5 px-2 text-right font-mono" :class="objColor(it.objective)">{{ formatVal(it.objective) }}</td>
                <td class="py-1.5 px-2 text-right font-mono" :class="(it.metrics?.win_rate||0) >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ ((it.metrics?.win_rate||0)*100).toFixed(1) }}%</td>
                <td class="py-1.5 px-2 text-right font-mono" :class="(it.metrics?.profit_factor||0) >= 1 ? 'text-green-400' : 'text-red-400'">{{ (it.metrics?.profit_factor||0).toFixed(2) }}</td>
                <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ ((it.metrics?.max_drawdown_percentage||0)).toFixed(1) }}%</td>
                <td class="py-1.5 px-2 text-right font-mono text-surface-300">{{ it.metrics?.total || '-' }}</td>
                <td class="py-1.5 px-2 text-right font-mono text-amber-400">{{ it.blockRate != null ? (it.blockRate*100).toFixed(1)+'%' : '-' }}</td>
                <td class="py-1.5 px-2 text-right font-mono text-red-400">{{ it.abortRate != null ? (it.abortRate*100).toFixed(1)+'%' : '-' }}</td>
                <td class="py-1.5 px-2 text-right font-mono text-surface-400">{{ it.coverage != null ? (it.coverage*100).toFixed(1)+'%' : '-' }}</td>
                <td class="py-1.5 px-2 text-right font-mono text-surface-500">{{ it.elapsed ? it.elapsed.toFixed(1)+'s' : '-' }}</td>
                <td class="py-1.5 px-2 text-left">
                  <div class="flex flex-wrap gap-1">
                    <span v-for="(v, k) in (it.hp || {})" :key="k" class="px-1 py-0.5 bg-surface-800 rounded text-[9px] font-mono text-surface-500">{{ k }}={{ formatVal(v) }}</span>
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
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '../useWebSocket'
import { api } from '../api'

// ── Pipeline Registry ──
const registeredPipelines = ref([])
const loadingPipelines = ref(false)
const trainingInProgress = ref({})
const expandedPipeline = ref(null)

async function fetchPipelines() {
  loadingPipelines.value = true
  try {
    const data = await api.getRegisteredPipelines()
    registeredPipelines.value = data
  } catch (e) {
    console.error('Failed to load pipelines:', e)
  } finally {
    loadingPipelines.value = false
  }
}

function toggleExpand(name) {
  expandedPipeline.value = expandedPipeline.value === name ? null : name
}

async function trainPipeline(name) {
  trainingInProgress.value[name] = true
  try {
    await api.trainPipeline(name)
    // Poll for completion every 10s
    const poll = setInterval(async () => {
      await fetchPipelines()
      const p = registeredPipelines.value.find(pp => pp.name === name)
      if (p?.architecture?.training_status === 'trained') {
        clearInterval(poll)
        trainingInProgress.value[name] = false
      }
    }, 10000)
    // Safety timeout after 20 minutes
    setTimeout(() => {
      clearInterval(poll)
      trainingInProgress.value[name] = false
      fetchPipelines()
    }, 1200000)
  } catch (e) {
    console.error('Training failed:', e)
    trainingInProgress.value[name] = false
  }
}

onMounted(fetchPipelines)

function layerBorderColor(type) {
  if (type === 'observation') return 'border-l-blue-500/50'
  if (type === 'entry_control') return 'border-l-amber-500/50'
  if (type === 'exit_control') return 'border-l-red-500/50'
  if (type === 'feature_extractor') return 'border-l-cyan-500/50'
  if (type === 'classifier') return 'border-l-violet-500/50'
  if (type === 'optimizer') return 'border-l-emerald-500/50'
  if (type === 'inferencer') return 'border-l-sky-500/50'
  if (type === 'sizer') return 'border-l-orange-500/50'
  return 'border-l-surface-600'
}

function layerBadgeColor(type) {
  if (type === 'observation') return 'bg-blue-500/20 text-blue-400'
  if (type === 'entry_control') return 'bg-amber-500/20 text-amber-400'
  if (type === 'exit_control') return 'bg-red-500/20 text-red-400'
  if (type === 'feature_extractor') return 'bg-cyan-500/20 text-cyan-400'
  if (type === 'classifier') return 'bg-violet-500/20 text-violet-400'
  if (type === 'optimizer') return 'bg-emerald-500/20 text-emerald-400'
  if (type === 'inferencer') return 'bg-sky-500/20 text-sky-400'
  if (type === 'sizer') return 'bg-orange-500/20 text-orange-400'
  return 'bg-surface-700 text-surface-400'
}

function layerTypeColor(type) {
  if (type === 'observation') return 'bg-blue-500/10 text-blue-400'
  if (type === 'entry_control') return 'bg-amber-500/10 text-amber-400'
  if (type === 'exit_control') return 'bg-red-500/10 text-red-400'
  if (type === 'feature_extractor') return 'bg-cyan-500/10 text-cyan-400'
  if (type === 'classifier') return 'bg-violet-500/10 text-violet-400'
  if (type === 'optimizer') return 'bg-emerald-500/10 text-emerald-400'
  if (type === 'inferencer') return 'bg-sky-500/10 text-sky-400'
  if (type === 'sizer') return 'bg-orange-500/10 text-orange-400'
  return 'bg-surface-800 text-surface-500'
}

function hookDotColor(hook) {
  if (hook.includes('before')) return 'bg-blue-400'
  if (hook.includes('gate')) return 'bg-amber-400'
  if (hook.includes('open_position')) return 'bg-green-400'
  if (hook.includes('exit') || hook.includes('abort')) return 'bg-red-400'
  if (hook.includes('cycle_end')) return 'bg-purple-400'
  return 'bg-surface-500'
}

function copyConfig(config) {
  navigator.clipboard.writeText(JSON.stringify(config, null, 2)).catch(() => {})
}

// ── Autopilot State ──
const running = ref(false)
const currentIteration = ref(0)
const maxIterations = ref(100)
const objectiveKey = ref('net_profit_percentage')
const iterations = ref([])
const bestResult = ref(null)
const sessionId = ref(null)
const elapsedTotal = ref(0)
const avgIterTime = ref(0)

const convergenceEl = ref(null)
const learningEl = ref(null)
const parallelEl = ref(null)

const hasResults = computed(() => iterations.value.length > 0)

const pipelineCoverage = computed(() => {
  return iterations.value
    .map((it, i) => ({ iteration: i, coverage: it.coverage }))
    .filter(d => d.coverage != null)
})

const plateauInfo = computed(() => {
  const n = iterations.value.length
  if (n < 5) return null
  const vals = iterations.value.map(d => d.objective)
  let bestIdx = 0
  for (let i = 1; i < n; i++) {
    if (vals[i] > vals[bestIdx]) bestIdx = i
  }
  const sinceBest = n - 1 - bestIdx
  const threshold = Math.max(5, Math.round(n * 0.3))
  return { bestAt: bestIdx, sinceBest, stale: sinceBest >= threshold }
})

const hpAxes = computed(() => {
  if (!iterations.value.length) return []
  const allKeys = new Set()
  for (const it of iterations.value) {
    if (it.hp) Object.keys(it.hp).forEach(k => allKeys.add(k))
  }
  return [...allKeys]
})

// ── WebSocket handler ──
function handleWsMessage(msg) {
  const { event, data } = msg
  if (!data) return

  if (event === 'autopilot.started') {
    running.value = true
    maxIterations.value = data.max_iterations || 100
    currentIteration.value = data.resumed_from || 0
    sessionId.value = data.client_id
    iterations.value = []
    bestResult.value = null
    elapsedTotal.value = 0
  }

  if (event === 'autopilot.iteration_start') {
    currentIteration.value = data.iteration
  }

  if (event === 'autopilot.iteration_end') {
    const metrics = data.metrics || {}
    const hp = data.hp || {}
    const ps = extractPipelineStats(data.pipeline_stats)
    const elapsed = data.elapsed_seconds || 0

    elapsedTotal.value += elapsed

    iterations.value.push({
      objective: metrics[objectiveKey.value] || 0,
      metrics,
      hp,
      blockRate: ps.blockRate,
      abortRate: ps.abortRate,
      coverage: ps.coverage,
      elapsed,
    })

    avgIterTime.value = elapsedTotal.value / iterations.value.length

    if (data.best) {
      bestResult.value = {
        iteration: data.best.best_iteration ?? iterations.value.length - 1,
        objective: data.best.best_metric ?? 0,
        metrics: data.best.best_metrics || metrics,
        hp: data.best.best_config || hp,
      }
    }

    currentIteration.value = data.iteration + 1
    nextTick(() => {
      drawConvergence()
      drawLearning()
      drawParallel()
    })
  }

  if (event === 'autopilot.finished') {
    running.value = false
    if (data.best_metric != null) {
      bestResult.value = {
        iteration: data.best_iteration ?? 0,
        objective: data.best_metric,
        metrics: data.best_metrics || {},
        hp: data.best_config || {},
      }
    }
  }

  if (event === 'autopilot.error') {
    running.value = false
  }
}

useWebSocket(handleWsMessage)

function extractPipelineStats(ps) {
  if (!ps) return {}
  for (const route of Object.values(ps)) {
    return {
      blockRate: route.block_rate ?? null,
      abortRate: route.abort_rate ?? null,
      coverage: route.abort?.coverage ?? null,
    }
  }
  return {}
}

async function cancelRun() {
  if (!sessionId.value) return
  try {
    await api.cancelAutopilot(sessionId.value)
  } catch (e) {
    console.error('Failed to cancel:', e)
  }
}

// ── Charts ──
function drawConvergence() {
  const el = convergenceEl.value
  if (!el || !iterations.value.length) return

  const data = iterations.value
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

  const pad = { top: 20, right: 20, bottom: 35, left: 60 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom

  const vals = data.map(d => d.objective)
  const minV = Math.min(...vals)
  const maxV = Math.max(...vals)
  const range = maxV - minV || 1
  const n = vals.length

  // Build running best
  let runBest = []
  let best = -Infinity
  for (const v of vals) {
    best = Math.max(best, v)
    runBest.push(best)
  }

  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = '#1e1f2b'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ph * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }

  // Per-iteration dots + line
  ctx.strokeStyle = '#818cf8'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - (vals[i] - minV) / range)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()

  // Dots
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - (vals[i] - minV) / range)
    ctx.beginPath()
    ctx.arc(x, y, 3, 0, Math.PI * 2)
    const isBest = bestResult.value && bestResult.value.iteration === i
    ctx.fillStyle = isBest ? '#4ade80' : '#818cf8'
    ctx.fill()
    if (isBest) {
      ctx.strokeStyle = '#4ade80'
      ctx.lineWidth = 2
      ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.stroke()
    }
  }

  // Running best line
  ctx.strokeStyle = '#4ade80'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - (runBest[i] - minV) / range)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()
  ctx.setLineDash([])

  // Axis labels
  ctx.fillStyle = '#666'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('Iteration', pad.left + pw / 2, h - 5)

  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = minV + range * (1 - i / 4)
    ctx.fillText(v.toFixed(2), pad.left - 5, pad.top + ph * i / 4 + 4)
  }

  // Legend
  ctx.textAlign = 'right'
  ctx.fillStyle = '#818cf8'
  ctx.fillRect(w - pad.right - 80, pad.top, 10, 2)
  ctx.fillStyle = '#666'
  ctx.fillText('Per-iter', w - pad.right - 5, pad.top + 5)
  ctx.fillStyle = '#4ade80'
  ctx.fillRect(w - pad.right - 80, pad.top + 12, 10, 2)
  ctx.fillStyle = '#666'
  ctx.fillText('Best so far', w - pad.right - 5, pad.top + 17)
}

function drawLearning() {
  const el = learningEl.value
  if (!el || !pipelineCoverage.value.length) return

  const data = pipelineCoverage.value
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

  const pad = { top: 15, right: 20, bottom: 30, left: 55 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom
  const n = data.length

  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = '#1e1f2b'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ph * i / 4
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke()
  }

  // Area fill
  ctx.fillStyle = 'rgba(74, 222, 128, 0.1)'
  ctx.beginPath()
  ctx.moveTo(pad.left, pad.top + ph)
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - data[i].coverage)
    ctx.lineTo(x, y)
  }
  ctx.lineTo(pad.left + pw, pad.top + ph)
  ctx.closePath()
  ctx.fill()

  // Line
  ctx.strokeStyle = '#4ade80'
  ctx.lineWidth = 2
  ctx.beginPath()
  for (let i = 0; i < n; i++) {
    const x = pad.left + (n > 1 ? pw * i / (n - 1) : pw / 2)
    const y = pad.top + ph * (1 - data[i].coverage)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.stroke()

  // Labels
  ctx.fillStyle = '#666'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('Iteration', pad.left + pw / 2, h - 5)

  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    ctx.fillText(((1 - i / 4) * 100).toFixed(0) + '%', pad.left - 5, pad.top + ph * i / 4 + 4)
  }

  ctx.save()
  ctx.translate(12, pad.top + ph / 2)
  ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'
  ctx.fillText('State Coverage', 0, 0)
  ctx.restore()
}

// ── Parallel Coordinates ──
function drawParallel() {
  const el = parallelEl.value
  if (!el || !iterations.value.length || hpAxes.value.length < 2) return

  const axes = hpAxes.value
  const data = iterations.value
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

  const pad = { top: 30, right: 30, bottom: 25, left: 30 }
  const pw = w - pad.left - pad.right
  const ph = h - pad.top - pad.bottom
  const nAxes = axes.length

  // Compute ranges per axis
  const ranges = axes.map(key => {
    const vals = data.map(d => d.hp?.[key]).filter(v => v != null && typeof v === 'number')
    if (!vals.length) return { min: 0, max: 1 }
    const mi = Math.min(...vals)
    const ma = Math.max(...vals)
    return { min: mi, max: ma === mi ? mi + 1 : ma }
  })

  // Objective range for coloring
  const objs = data.map(d => d.objective)
  const minObj = Math.min(...objs)
  const maxObj = Math.max(...objs)
  const objRange = maxObj - minObj || 1

  ctx.fillStyle = '#1a1b23'
  ctx.fillRect(0, 0, w, h)

  // Draw axes
  ctx.strokeStyle = '#2a2b33'
  ctx.lineWidth = 1
  for (let a = 0; a < nAxes; a++) {
    const x = pad.left + (nAxes > 1 ? pw * a / (nAxes - 1) : pw / 2)
    ctx.beginPath()
    ctx.moveTo(x, pad.top)
    ctx.lineTo(x, pad.top + ph)
    ctx.stroke()

    // Axis label
    ctx.fillStyle = '#888'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(axes[a], x, pad.top - 8)

    // Min/max labels
    ctx.fillStyle = '#555'
    ctx.font = '9px monospace'
    ctx.fillText(formatVal(ranges[a].max), x, pad.top - 0)
    ctx.fillText(formatVal(ranges[a].min), x, pad.top + ph + 14)
  }

  // Draw lines (one per iteration)
  for (let i = 0; i < data.length; i++) {
    const it = data[i]
    const t = (it.objective - minObj) / objRange // 0 = worst, 1 = best

    // Color: red (bad) → green (good)
    const r = Math.round(239 * (1 - t) + 74 * t)
    const g = Math.round(68 * (1 - t) + 222 * t)
    const b = Math.round(68 * (1 - t) + 128 * t)
    ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${bestResult.value && bestResult.value.iteration === i ? 0.9 : 0.25})`
    ctx.lineWidth = bestResult.value && bestResult.value.iteration === i ? 2.5 : 1

    ctx.beginPath()
    let started = false
    for (let a = 0; a < nAxes; a++) {
      const x = pad.left + (nAxes > 1 ? pw * a / (nAxes - 1) : pw / 2)
      const v = it.hp?.[axes[a]]
      if (v == null || typeof v !== 'number') continue
      const { min, max } = ranges[a]
      const y = pad.top + ph * (1 - (v - min) / (max - min))
      if (!started) { ctx.moveTo(x, y); started = true }
      else ctx.lineTo(x, y)
    }
    ctx.stroke()
  }

  // Draw best line on top
  if (bestResult.value) {
    const it = data[bestResult.value.iteration]
    if (it) {
      ctx.strokeStyle = '#4ade80'
      ctx.lineWidth = 2.5
      ctx.beginPath()
      let started = false
      for (let a = 0; a < nAxes; a++) {
        const x = pad.left + (nAxes > 1 ? pw * a / (nAxes - 1) : pw / 2)
        const v = it.hp?.[axes[a]]
        if (v == null || typeof v !== 'number') continue
        const { min, max } = ranges[a]
        const y = pad.top + ph * (1 - (v - min) / (max - min))
        if (!started) { ctx.moveTo(x, y); started = true }
        else ctx.lineTo(x, y)
      }
      ctx.stroke()
    }
  }
}

// ── Helpers ──
function formatVal(v) {
  if (v == null) return '-'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  return String(v)
}

function formatDuration(seconds) {
  if (seconds < 60) return seconds.toFixed(0) + 's'
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm ' + (seconds % 60).toFixed(0) + 's'
  return Math.floor(seconds / 3600) + 'h ' + Math.floor((seconds % 3600) / 60) + 'm'
}

function objColor(v) {
  if (v == null) return 'text-surface-400'
  return v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-surface-300'
}

// Resize observer
let resizeObserver = null
watch([convergenceEl, learningEl, parallelEl], () => {
  if (resizeObserver) resizeObserver.disconnect()
  resizeObserver = new ResizeObserver(() => {
    drawConvergence()
    drawLearning()
    drawParallel()
  })
  if (convergenceEl.value) resizeObserver.observe(convergenceEl.value)
  if (learningEl.value) resizeObserver.observe(learningEl.value)
  if (parallelEl.value) resizeObserver.observe(parallelEl.value)
})

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
})
</script>
