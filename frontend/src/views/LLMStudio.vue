<template>
  <div>
    <div class="text-center mb-6">
      <h1 class="text-2xl font-bold">LLM Strategy Studio</h1>
      <p class="text-sm text-surface-500 mt-1">Generate, refine, and validate trading strategies using AI -- requires an LLM provider in Settings</p>
    </div>

    <!-- Status Bar -->
    <div class="card mb-5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
      <div class="flex items-center gap-3">
        <span class="w-2 h-2 rounded-full" :class="llmStatus.configured ? 'bg-green-400' : 'bg-red-400'"></span>
        <span class="text-sm text-surface-300">
          {{ llmStatus.configured ? `${llmStatus.provider} - ${llmStatus.model}` : 'LLM not configured' }}
        </span>
      </div>
      <router-link v-if="!llmStatus.configured" to="/settings?tab=LLM" class="btn-sm btn-primary">Configure</router-link>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Generate Panel -->
      <div class="space-y-4">
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Generate Strategy</h2>
          <div class="space-y-3">
            <div>
              <label class="label">Description</label>
              <textarea v-model="genForm.description" class="input min-h-[100px] resize-y"
                placeholder="Buy EUR-USD when RSI is oversold during London session, use 1% risk per trade with 2:1 reward ratio"></textarea>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label class="label">Asset Class</label>
                <select v-model="genForm.asset_class" class="select">
                  <option value="forex">Forex</option>
                  <option value="commodity">Commodity</option>
                  <option value="index">Index</option>
                  <option value="crypto">Crypto</option>
                </select>
              </div>
              <div>
                <label class="label">Symbol</label>
                <input v-model="genForm.symbol" class="input" placeholder="EUR-USD" />
              </div>
            </div>
            <button @click="generate" class="btn-primary w-full" :disabled="generating || !llmStatus.configured || !genForm.description">
              <span v-if="generating" class="flex items-center justify-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Generating...
              </span>
              <span v-else>Generate Strategy</span>
            </button>
          </div>
        </div>

        <!-- Refine Panel -->
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Refine Strategy</h2>
          <div class="space-y-3">
            <div>
              <label class="label">Feedback</label>
              <textarea v-model="refineFeedback" class="input min-h-[60px] resize-y"
                placeholder="Add a trailing stop loss, only trade during high volume..."></textarea>
            </div>
            <button @click="refine" class="btn-secondary w-full"
              :disabled="refining || !code || !llmStatus.configured || !refineFeedback">
              <span v-if="refining" class="flex items-center justify-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Refining...
              </span>
              <span v-else>Refine Code</span>
            </button>
          </div>
        </div>

        <!-- Validate -->
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Validate</h2>
          <button @click="validate" class="btn-secondary w-full" :disabled="!code || validating">
            {{ validating ? 'Validating...' : 'Validate Strategy Code' }}
          </button>
          <div v-if="validation" class="mt-3 p-2 rounded text-sm"
            :class="validation.valid ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'">
            <div class="font-medium">{{ validation.valid ? 'Valid' : 'Invalid' }}</div>
            <ul v-if="validation.errors?.length" class="mt-1 space-y-0.5 text-xs">
              <li v-for="(err, i) in validation.errors" :key="i">{{ err }}</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Code Output -->
      <div class="card h-fit">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-surface-300">Generated Code</h2>
          <button v-if="code" @click="copyCode" class="text-xs text-brand-400 hover:text-brand-300">
            {{ copied ? 'Copied!' : 'Copy' }}
          </button>
        </div>

        <div v-if="genError" class="p-3 bg-red-500/10 rounded-lg text-red-400 text-sm mb-3">{{ genError }}</div>

        <!-- Loading placeholder -->
        <div v-if="generating || refining" class="bg-surface-900 rounded-lg p-8 text-center">
          <svg class="animate-spin h-8 w-8 mx-auto text-brand-400 mb-3" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
          <p class="text-surface-400 text-sm">{{ generating ? 'Generating strategy with AI...' : 'Refining strategy...' }}</p>
          <p class="text-surface-600 text-xs mt-1">This may take 10-30 seconds</p>
        </div>

        <CodeEditor v-else-if="code" :model-value="code" :editable="false" min-height="300px" style="max-height: 600px;" />
        <div v-else class="text-surface-500 text-sm text-center py-12">
          Generated strategy code will appear here.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import CodeEditor from '../components/CodeEditor.vue'

const llmStatus = ref({ configured: false, provider: '', model: '' })
const code = ref('')
const genError = ref('')
const validation = ref(null)
const generating = ref(false)
const refining = ref(false)
const validating = ref(false)
const copied = ref(false)
const refineFeedback = ref('')

const genForm = ref({
  description: '',
  asset_class: 'forex',
  symbol: 'EUR-USD',
})

async function generate() {
  generating.value = true
  genError.value = ''
  validation.value = null
  try {
    const res = await api.generateStrategy(genForm.value)
    if (res.valid && res.code) {
      code.value = res.code
    } else {
      genError.value = res.errors?.join(', ') || 'Generation failed'
    }
  } catch (e) {
    genError.value = e.message
  } finally {
    generating.value = false
  }
}

async function refine() {
  refining.value = true
  genError.value = ''
  try {
    const res = await api.refineStrategy({ code: code.value, feedback: refineFeedback.value })
    if (res.valid && res.code) {
      code.value = res.code
      refineFeedback.value = ''
    } else {
      genError.value = res.errors?.join(', ') || 'Refinement failed'
    }
  } catch (e) {
    genError.value = e.message
  } finally {
    refining.value = false
  }
}

async function validate() {
  validating.value = true
  try {
    validation.value = await api.validateStrategy(code.value)
  } catch (e) {
    validation.value = { valid: false, errors: [e.message] }
  } finally {
    validating.value = false
  }
}

function copyCode() {
  navigator.clipboard.writeText(code.value)
  copied.value = true
  setTimeout(() => copied.value = false, 2000)
}

onMounted(async () => {
  try {
    llmStatus.value = await api.llmStatus()
  } catch (e) {
    console.error(e)
  }
})
</script>
