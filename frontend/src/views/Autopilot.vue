<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-center sm:text-left">Pipelines</h1>
      <p class="text-xs text-surface-500 mt-0.5">Registered pipelines available for use in backtests</p>
    </div>

    <!-- Loading state -->
    <div v-if="loadingPipelines" class="card text-center py-8">
      <div class="inline-block w-5 h-5 border-2 border-surface-600 border-t-brand-400 rounded-full animate-spin"></div>
      <p class="text-xs text-surface-500 mt-2">Loading pipeline registry...</p>
    </div>

    <!-- No pipelines -->
    <div v-else-if="!registeredPipelines.length" class="card text-center py-8">
      <svg class="w-10 h-10 text-surface-700 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"/></svg>
      <p class="text-surface-500 text-sm">No pipelines registered</p>
    </div>

    <!-- Pipeline Cards -->
    <div v-else class="space-y-6">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div v-for="pipeline in registeredPipelines" :key="pipeline.name"
             class="card cursor-pointer hover:border-surface-600 transition-colors"
             :class="expandedPipeline === pipeline.name ? 'border-brand-500/30 lg:col-span-2' : ''"
             @click="toggleExpand(pipeline.name)">

          <!-- Compact Card -->
          <div class="flex items-start justify-between gap-3">
            <div class="flex-1 min-w-0">
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

              <p class="text-[11px] text-surface-400 leading-relaxed mb-2.5">{{ pipeline.architecture?.summary || pipeline.description }}</p>

              <div v-if="pipeline.architecture?.layers?.length" class="flex items-center flex-wrap gap-1 mb-2">
                <template v-for="(layer, li) in pipeline.architecture.layers" :key="layer.name">
                  <span class="px-1.5 py-0.5 rounded text-[9px] font-mono border" :class="layerTypeColor(layer.type) + ' border-transparent'">{{ layer.name }}</span>
                  <svg v-if="li < pipeline.architecture.layers.length - 1" class="w-3 h-3 text-surface-700 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
                </template>
              </div>

              <div class="flex items-center gap-2 flex-wrap">
                <span v-for="target in (pipeline.architecture?.designed_for || [])" :key="target"
                      class="px-1.5 py-0.5 bg-surface-800 rounded text-[9px] text-surface-500">{{ target }}</span>
                <span v-if="pipeline.architecture?.research_basis" class="text-[9px] text-surface-600">{{ pipeline.architecture.research_basis }}</span>
              </div>
            </div>

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

          <!-- Expanded Detail -->
          <div v-if="expandedPipeline === pipeline.name" class="mt-4 pt-4 border-t border-surface-800 space-y-4" @click.stop>

            <div v-if="pipeline.architecture?.training_description" class="p-3 bg-surface-850 rounded">
              <div class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">Training</div>
              <p class="text-xs text-surface-400 mb-2">{{ pipeline.architecture.training_description }}</p>
              <ol v-if="pipeline.architecture?.training_steps?.length" class="ml-4 space-y-0.5">
                <li v-for="(step, si) in pipeline.architecture.training_steps" :key="si" class="text-[10px] text-surface-500 list-decimal">{{ step }}</li>
              </ol>
            </div>

            <div v-if="pipeline.architecture?.layers?.length">
              <div class="flex items-center gap-2 mb-3">
                <h3 class="text-xs font-semibold text-surface-500 uppercase tracking-wider">Pipeline Layers</h3>
                <div class="flex-1 border-b border-surface-800"></div>
              </div>

              <div class="relative">
                <div v-for="(layer, li) in pipeline.architecture.layers" :key="layer.name" class="relative">
                  <div v-if="li > 0" class="flex justify-center py-1">
                    <div class="flex flex-col items-center">
                      <div class="w-px h-3 bg-surface-700"></div>
                      <svg class="w-3 h-3 text-surface-600 -mt-0.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
                    </div>
                  </div>

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
                        <div v-if="layer.genome_params?.length" class="p-2 bg-surface-900 rounded">
                          <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Evolved Parameters</div>
                          <div class="flex flex-wrap gap-1">
                            <code v-for="p in layer.genome_params" :key="p" class="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 px-1 py-0.5 rounded">{{ p }}</code>
                          </div>
                        </div>
                        <div v-if="layer.factors?.length" class="p-2 bg-surface-900 rounded">
                          <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Sizing Factors</div>
                          <ul class="space-y-0.5">
                            <li v-for="f in layer.factors" :key="f" class="text-[10px] text-surface-400 flex items-start gap-1.5">
                              <span class="text-orange-400 mt-0.5">*</span> {{ f }}
                            </li>
                          </ul>
                        </div>
                      </div>

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

                    <div v-if="layer.pretrained" class="mt-2">
                      <div class="text-[9px] text-surface-600 uppercase tracking-wider mb-1">Pre-trained</div>
                      <div class="grid grid-cols-2 sm:grid-cols-5 gap-1.5">
                        <div v-for="(val, key) in layer.pretrained" :key="key" class="p-1.5 bg-surface-900 rounded text-center">
                          <div class="text-[8px] text-surface-600">{{ key.replace(/_/g, ' ') }}</div>
                          <div class="text-xs font-mono" :class="String(val).startsWith('-') ? 'text-green-400' : 'text-surface-200'">{{ val }}</div>
                        </div>
                      </div>
                    </div>

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
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

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
    const poll = setInterval(async () => {
      await fetchPipelines()
      const p = registeredPipelines.value.find(pp => pp.name === name)
      if (p?.architecture?.training_status === 'trained') {
        clearInterval(poll)
        trainingInProgress.value[name] = false
      }
    }, 10000)
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

function copyConfig(config) {
  navigator.clipboard.writeText(JSON.stringify(config, null, 2)).catch(() => {})
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
</script>
