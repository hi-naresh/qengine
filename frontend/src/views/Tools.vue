<template>
  <div>
    <div class="text-center mb-6">
      <h1 class="text-2xl font-bold">Tools</h1>
      <p class="text-sm text-surface-500 mt-1">Instrument browser, pip value calculator, and trading utilities</p>
    </div>

    <!-- Tool Tabs -->
    <div class="flex gap-2 mb-5">
      <button v-for="tab in tabs" :key="tab" @click="activeTab = tab"
        class="btn-sm" :class="activeTab === tab ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        {{ tab }}
      </button>
    </div>

    <!-- Instruments Tab -->
    <div v-if="activeTab === 'Instruments'">
      <!-- Pip Calculator -->
      <div class="card mt-6 mb-6">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Pip Value Calculator</h2>
        <div class="flex flex-col sm:flex-row sm:items-end gap-3 sm:gap-4">
          <div class="flex-1">
            <label class="label">Symbol</label>
            <select v-model="calcSymbol" class="select">
              <option v-for="inst in instruments" :key="inst.symbol" :value="inst.symbol">{{ inst.symbol }}</option>
            </select>
          </div>
          <div class="w-full sm:w-32">
            <label class="label">Lot Size</label>
            <input v-model.number="calcLots" type="number" step="0.01" min="0.01" class="input" />
          </div>
          <button @click="calculatePip" class="btn-primary w-full sm:w-auto">Calculate</button>
        </div>
        <div v-if="pipResult" class="mt-4 p-3 bg-surface-800 rounded-lg text-sm">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <span class="text-surface-500 text-xs">Symbol</span>
              <div class="text-surface-100 font-medium">{{ pipResult.symbol }}</div>
            </div>
            <div>
              <span class="text-surface-500 text-xs">Pip Size</span>
              <div class="text-surface-200 font-mono">{{ pipResult.pip_size }}</div>
            </div>
            <div>
              <span class="text-surface-500 text-xs">Lot Size</span>
              <div class="text-surface-200 font-mono">{{ pipResult.lot_size }}</div>
            </div>
            <div>
              <span class="text-surface-500 text-xs">Pip Value</span>
              <div class="text-green-400 font-mono font-semibold">${{ pipResult.pip_value }}</div>
            </div>
          </div>
        </div>
      </div>
      <div class="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        <div class="flex gap-2 flex-wrap">
          <button v-for="tab in assetTabs" :key="tab.value" @click="assetFilter = tab.value"
            class="btn-sm" :class="assetFilter === tab.value ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400 hover:text-surface-200'">
            {{ tab.label }}
          </button>
        </div>
        <input v-model="search" type="text" class="input w-full sm:max-w-xs sm:ml-auto" placeholder="Search symbol..." />
      </div>

      <div v-if="loadingInstr" class="text-surface-500 text-sm">Loading...</div>

      <div v-else>
        <div class="card overflow-hidden p-0">
          <div class="overflow-x-auto">
          <table class="w-full text-sm min-w-[600px]">
            <thead>
              <tr class="text-surface-500 bg-surface-900 text-xs">
                <th class="text-left px-4 py-2.5 font-medium">Symbol</th>
                <th class="text-left px-4 py-2.5 font-medium">Class</th>
                <th class="text-right px-4 py-2.5 font-medium">Pip Size</th>
                <th class="text-right px-4 py-2.5 font-medium">Contract Size</th>
                <th class="text-left px-4 py-2.5 font-medium">Base</th>
                <th class="text-left px-4 py-2.5 font-medium">Quote</th>
                <th class="text-center px-4 py-2.5 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="inst in filtered" :key="inst.symbol"
                class="border-t border-surface-800 hover:bg-surface-800/50 transition-colors">
                <td class="px-4 py-2.5 font-mono text-surface-100 font-medium">{{ inst.symbol }}</td>
                <td class="px-4 py-2.5">
                  <span :class="classColor(inst.asset_class)" class="badge capitalize">{{ inst.asset_class }}</span>
                </td>
                <td class="px-4 py-2.5 text-right font-mono text-surface-300">{{ inst.pip_size }}</td>
                <td class="px-4 py-2.5 text-right font-mono text-surface-300">{{ inst.contract_size?.toLocaleString() }}</td>
                <td class="px-4 py-2.5 text-surface-400">{{ inst.base_currency }}</td>
                <td class="px-4 py-2.5 text-surface-400">{{ inst.quote_currency }}</td>
                <td class="px-4 py-2.5 text-center">
                  <button @click="showDetail(inst.symbol)" class="text-brand-400 hover:text-brand-300 text-xs">
                    Details
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>

      </div>
    </div>

    <!-- Trading Calculator Tab -->
    <div v-if="activeTab === 'Trading Calculator'">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Input -->
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Position & Risk Calculator</h2>
          <div class="space-y-3">
            <div>
              <label class="label">Broker</label>
              <select v-model="tc.broker_id" class="select" @change="runTradeCalc">
                <option v-for="b in brokers" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>
            <div>
              <label class="label">Symbol</label>
              <select v-model="tc.symbol" class="select" @change="runTradeCalc">
                <option v-for="s in tcSymbols" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Account Balance ($)</label>
                <input v-model.number="tc.account_balance" type="number" min="0" class="input" @change="runTradeCalc" />
              </div>
              <div>
                <label class="label">Lot Size</label>
                <input v-model.number="tc.lot_size" type="number" step="0.01" min="0.01" class="input" @change="runTradeCalc" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Risk %</label>
                <input v-model.number="tc.risk_percent" type="number" step="0.1" min="0" max="100" class="input" @change="runTradeCalc" />
              </div>
              <div>
                <label class="label">Stop Loss (pips)</label>
                <input v-model.number="tc.stop_loss_pips" type="number" step="1" min="1" class="input" @change="runTradeCalc" />
              </div>
            </div>
          </div>
        </div>

        <!-- Results -->
        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">Results</h2>
          <div v-if="tcResult" class="space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div class="p-3 bg-surface-800 rounded-lg">
                <div class="text-xs text-surface-500">Pip Value</div>
                <div class="text-lg font-mono text-surface-200">${{ tcResult.pip_value }}</div>
                <div class="text-[10px] text-surface-600">${{ tcResult.pip_value_per_lot }}/lot</div>
              </div>
              <div class="p-3 bg-surface-800 rounded-lg">
                <div class="text-xs text-surface-500">Margin Required</div>
                <div class="text-lg font-mono text-surface-200">${{ tcResult.margin_required?.toLocaleString() }}</div>
                <div class="text-[10px] text-surface-600">{{ tcResult.leverage }}x leverage</div>
              </div>
              <div class="p-3 bg-amber-500/5 rounded-lg border border-amber-500/20">
                <div class="text-xs text-surface-500">Risk Amount</div>
                <div class="text-lg font-mono text-amber-400">${{ tcResult.risk_amount }}</div>
                <div class="text-[10px] text-surface-600">{{ tc.risk_percent }}% of balance</div>
              </div>
              <div class="p-3 bg-brand-500/5 rounded-lg border border-brand-500/20">
                <div class="text-xs text-surface-500">Position Size (risk-based)</div>
                <div class="text-lg font-mono text-brand-400">{{ tcResult.position_size_lots }} lots</div>
                <div class="text-[10px] text-surface-600">for {{ tc.stop_loss_pips }} pip SL</div>
              </div>
              <div class="p-3 bg-surface-800 rounded-lg">
                <div class="text-xs text-surface-500">Max Lots (balance)</div>
                <div class="text-lg font-mono text-surface-200">{{ tcResult.max_lots }}</div>
              </div>
              <div class="p-3 bg-surface-800 rounded-lg">
                <div class="text-xs text-surface-500">Contract Size</div>
                <div class="text-lg font-mono text-surface-200">{{ tcResult.contract_size?.toLocaleString() }}</div>
              </div>
            </div>
            <div class="text-xs text-surface-600 pt-1">
              Pip size: {{ tcResult.pip_size }} &middot; Margin rate: {{ tcResult.margin_rate }}
            </div>
          </div>
          <div v-else class="text-sm text-surface-500 py-8 text-center">
            Select a broker and symbol to calculate.
          </div>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="detail" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="detail = null">
      <div class="card w-full max-w-md mx-3 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold font-mono">{{ detail.symbol }}</h2>
          <button @click="detail = null" class="text-surface-500 hover:text-surface-200 text-xl">&times;</button>
        </div>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div><span class="text-surface-500 text-xs">Asset Class</span><div class="text-surface-200 capitalize">{{ detail.asset_class }}</div></div>
          <div><span class="text-surface-500 text-xs">Pip Size</span><div class="text-surface-200 font-mono">{{ detail.pip_size }}</div></div>
          <div><span class="text-surface-500 text-xs">Contract Size</span><div class="text-surface-200 font-mono">{{ detail.contract_size?.toLocaleString() }}</div></div>
          <div><span class="text-surface-500 text-xs">Margin Rate</span><div class="text-surface-200 font-mono">{{ detail.margin_rate || 'N/A' }}</div></div>
          <div><span class="text-surface-500 text-xs">Min Lot</span><div class="text-surface-200 font-mono">{{ detail.min_lot || 'N/A' }}</div></div>
          <div><span class="text-surface-500 text-xs">Lot Step</span><div class="text-surface-200 font-mono">{{ detail.lot_step || 'N/A' }}</div></div>
          <div><span class="text-surface-500 text-xs">Swap Long</span><div class="text-surface-200 font-mono">{{ detail.swap_long ?? 'N/A' }}</div></div>
          <div><span class="text-surface-500 text-xs">Swap Short</span><div class="text-surface-200 font-mono">{{ detail.swap_short ?? 'N/A' }}</div></div>
          <div class="col-span-2"><span class="text-surface-500 text-xs">Trading Hours</span><div class="text-surface-200">{{ detail.trading_hours || 'Standard Forex Hours' }}</div></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, defaultBrokerId } from '../api'

const activeTab = ref('Instruments')
const tabs = ['Instruments', 'Trading Calculator']

// --- Instruments ---
const loadingInstr = ref(true)
const instruments = ref([])
const assetFilter = ref('all')
const search = ref('')
const detail = ref(null)
const calcSymbol = ref('EUR-USD')
const calcLots = ref(1)
const pipResult = ref(null)

const assetTabs = [
  { value: 'all', label: 'All' },
  { value: 'forex', label: 'Forex' },
  { value: 'commodity', label: 'Commodities' },
  { value: 'index', label: 'Indices' },
]

const filtered = computed(() => {
  let list = instruments.value
  if (assetFilter.value !== 'all') list = list.filter(i => i.asset_class === assetFilter.value)
  if (search.value) {
    const q = search.value.toUpperCase()
    list = list.filter(i => i.symbol.toUpperCase().includes(q))
  }
  return list
})

function classColor(cls) {
  if (cls === 'forex') return 'bg-blue-500/20 text-blue-400'
  if (cls === 'commodity') return 'bg-yellow-500/20 text-yellow-400'
  if (cls === 'index') return 'bg-purple-500/20 text-purple-400'
  return 'bg-surface-500/20 text-surface-400'
}

async function showDetail(symbol) {
  try {
    const res = await api.getInstrument(symbol)
    detail.value = res.data
  } catch (e) {
    console.error(e)
  }
}

async function calculatePip() {
  try {
    const res = await api.getPipValue(calcSymbol.value, calcLots.value)
    pipResult.value = res.data
  } catch (e) {
    console.error(e)
  }
}

// --- Trading Calculator ---
const brokers = ref([])
const tc = ref({
  symbol: 'EUR-USD',
  broker_id: '',
  account_balance: 10000,
  risk_percent: 1.0,
  stop_loss_pips: 50,
  lot_size: 1.0,
})
const tcResult = ref(null)

const tcSymbols = computed(() => {
  const common = ['EUR-USD', 'GBP-USD', 'USD-JPY', 'USD-CHF', 'AUD-USD', 'NZD-USD', 'USD-CAD', 'XAU-USD', 'XAG-USD']
  const fromInstr = instruments.value.map(i => i.symbol)
  return [...new Set([...common, ...fromInstr])]
})

let calcTimeout = null
function runTradeCalc() {
  if (!tc.value.broker_id || !tc.value.symbol) return
  clearTimeout(calcTimeout)
  calcTimeout = setTimeout(async () => {
    try {
      const res = await api.calculate(tc.value)
      tcResult.value = res.data
    } catch (e) {
      console.error('Calc error:', e)
    }
  }, 300)
}

// --- Init ---
onMounted(async () => {
  try {
    const [instrRes, brokersRes] = await Promise.all([
      api.getInstruments(),
      api.getBrokers(),
    ])
    instruments.value = instrRes.data
    brokers.value = brokersRes.data
    tc.value.broker_id = defaultBrokerId(brokers.value)
  } catch (e) {
    console.error(e)
  } finally {
    loadingInstr.value = false
  }
})
</script>
