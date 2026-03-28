<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="fixed inset-0 z-[200] flex items-center justify-center p-4" @click.self="dismiss">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
        <div class="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl border border-white/[0.08] bg-surface-900 shadow-2xl">
          <!-- Header -->
          <div class="sticky top-0 z-10 bg-surface-900/95 backdrop-blur-sm border-b border-white/[0.06] px-6 py-5">
            <div class="flex items-center justify-between">
              <div>
                <h2 class="text-xl font-bold text-surface-100">Welcome to QEngine</h2>
                <p class="text-sm text-surface-500 mt-1">Multi-asset quant engine for analysis and production pipelines</p>
              </div>
              <button @click="dismiss" class="p-1.5 rounded-lg hover:bg-surface-800 text-surface-500 hover:text-surface-300 transition-colors">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
          </div>

          <!-- Content -->
          <div class="px-6 py-5 space-y-6">
            <!-- Mission -->
            <div class="p-4 rounded-xl bg-brand-600/10 border border-brand-500/20">
              <h3 class="text-sm font-semibold text-brand-400 mb-2">What We Need From You</h3>
              <p class="text-sm text-surface-300 leading-relaxed">
                QEngine is a multi-asset quant engine for analysis and production pipelines for trading systems with intelligence &mdash; built from scratch using quantitative techniques and methods, not just LLM-tuned.
                Currently in <strong class="text-surface-100">beta testing</strong>. Your job is to verify that the <strong class="text-surface-100">engine produces truthful, correct results</strong> &mdash;
                that strategies execute as intended, trades trigger at the right time and price, the cost model behaves sensibly, and reported metrics are mathematically accurate.
              </p>
            </div>

            <!-- Steps -->
            <div>
              <h3 class="text-sm font-semibold text-surface-200 mb-3">How to Test — Step by Step</h3>
              <div class="space-y-3">
                <div v-for="(step, i) in steps" :key="i" class="flex gap-3">
                  <div class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                    :class="step.color">{{ i + 1 }}</div>
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-surface-200">{{ step.title }}</div>
                    <p class="text-xs text-surface-400 mt-0.5 leading-relaxed">{{ step.desc }}</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- What to look for -->
            <div>
              <h3 class="text-sm font-semibold text-surface-200 mb-3">What to Scrutinize</h3>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div v-for="item in lookFor" :key="item.title" class="p-3 bg-surface-800 rounded-lg">
                  <div class="text-xs font-medium text-surface-300">{{ item.title }}</div>
                  <p class="text-[11px] text-surface-500 mt-0.5">{{ item.desc }}</p>
                </div>
              </div>
            </div>

            <!-- Important notes -->
            <div class="p-4 rounded-xl bg-amber-500/5 border border-amber-500/15">
              <h3 class="text-sm font-semibold text-amber-400 mb-2">Important Notes</h3>
              <div class="space-y-1.5 text-xs text-surface-400 leading-relaxed">
                <p>- This is deployed on <strong class="text-surface-300">minimal specs</strong> for beta. Avoid very large date ranges (years of 1-minute data) &mdash; keep it reasonable (a few months on 1h/4h/1D timeframes).</p>
                <p>- Report everything via <strong class="text-surface-300">Issues</strong> in the sidebar. Describe what you expected vs. what happened, and include the strategy, symbol, timeframe, and dates you used.</p>
                <p>- Focus on <strong class="text-surface-300">logic correctness</strong>, not visual polish. If something behaves in a fundamentally wrong way on the interface, report that too.</p>
              </div>
            </div>

            <!-- Tip -->
            <div class="p-3 rounded-lg bg-surface-800/50 border border-surface-700/50">
              <p class="text-xs text-surface-500 leading-relaxed">
                You can revisit this guide anytime from the <strong class="text-surface-400">Help</strong> section in the sidebar.
              </p>
            </div>
          </div>

          <!-- Footer -->
          <div class="sticky bottom-0 bg-surface-900/95 backdrop-blur-sm border-t border-white/[0.06] px-6 py-4">
            <button @click="dismiss" class="btn-primary w-full">Got it, let's go</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const visible = ref(false)
const route = useRoute()

const steps = [
  { title: 'Create a Strategy You Understand', desc: 'Go to Strategies and write (or generate via LLM Studio) a strategy whose logic you know well — EMA crossover, RSI mean-reversion, breakout, or any system where you can predict roughly how it should behave. This is critical: you need to be able to judge whether the engine did the right thing.', color: 'bg-brand-600/20 text-brand-400' },
  { title: 'Test It in the Playground', desc: 'Before running a full backtest, use the Playground to execute your strategy on a small, focused scenario. You can see exactly where trades start and end on the chart, verify entry/exit logic visually, and refine your strategy until it behaves as expected. This is the fastest way to validate and iterate before committing to a longer backtest.', color: 'bg-cyan-600/20 text-cyan-400' },
  { title: 'Run a Backtest', desc: 'Once your strategy behaves correctly in the Playground, run a proper backtest. Select a symbol (e.g. EUR-USD), a timeframe (1h or 4h recommended), and a reasonable date range (1–6 months). The simulator runs your strategy against historical candles with a full cost model (spread, slippage, swap).', color: 'bg-blue-600/20 text-blue-400' },
  { title: 'Review the Execution', desc: 'Open the trade log and check: Did entries and exits fire on the correct candle and at the expected price? Did stop-loss and take-profit orders trigger where they should? Were there any trades that should not have happened, or trades that were missed?', color: 'bg-purple-600/20 text-purple-400' },
  { title: 'Verify the Cost Model', desc: 'Check whether spread is applied correctly (buy at ask, sell at bid), slippage shifts fills realistically, and swap charges appear on overnight positions. Do the costs feel sensible for the broker and instrument, or are they absurdly high/low?', color: 'bg-green-600/20 text-green-400' },
  { title: 'Critique the Stats', desc: 'Use your own knowledge to validate the reported metrics — Sharpe ratio, profit factor, win rate, max drawdown, etc. Do quick mental or manual calculations. If a stat looks off, it probably is.', color: 'bg-amber-600/20 text-amber-400' },
  { title: 'Report via Issues', desc: 'Create a ticket for every finding — wrong execution, suspicious stats, unrealistic costs, broken logic, or anything that feels incorrect. Include strategy name, symbol, timeframe, date range, and what you expected vs. what happened.', color: 'bg-red-600/20 text-red-400' },
]

const lookFor = [
  { title: 'Execution Correctness', desc: 'Did the strategy enter and exit when it was supposed to? Were signals honoured on the right candle?' },
  { title: 'Cost Model Realism', desc: 'Is spread applied to the right side of fills? Do swap charges appear at the correct time? Are costs sensible?' },
  { title: 'Stat Accuracy', desc: 'Do Sharpe, profit factor, drawdown, and win rate match what you\'d calculate by hand from the trade log?' },
  { title: 'Session Behaviour', desc: 'Does the session produce the trades you expected? Any phantom trades, missed signals, or double entries?' },
  { title: 'Monte Carlo Validity', desc: 'Do the confidence intervals and distributions look statistically reasonable for the underlying trade set?' },
  { title: 'Determinism', desc: 'Same strategy + same params + same dates should produce identical results every time. Does it?' },
]

function dismiss() {
  visible.value = false
  localStorage.setItem('qe_welcome_seen', 'true')
}

function show() {
  visible.value = true
}

watch(() => route.name, (name) => {
  if (name !== 'Login' && localStorage.getItem('qe_show_welcome') === 'true') {
    localStorage.removeItem('qe_show_welcome')
    visible.value = true
  }
}, { immediate: true })

defineExpose({ show })
</script>

<style scoped>
.modal-enter-active { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.modal-leave-active { transition: all 0.15s ease-in; }
.modal-enter-from { opacity: 0; }
.modal-enter-from > div:last-child { transform: scale(0.95) translateY(10px); }
.modal-leave-to { opacity: 0; }
</style>
