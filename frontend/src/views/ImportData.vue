<template>
  <div>
    <div class="text-center mb-8">
      <h1 class="text-2xl font-bold">Import Candle Data</h1>
      <p class="text-sm text-surface-500 mt-1">Download historical OHLCV data from your broker for backtesting and research</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <!-- Import Form -->
      <div class="lg:col-span-1 space-y-4">
        <div class="card space-y-3">
          <h2 class="text-sm font-semibold text-surface-300 mb-1">Import Configuration</h2>
          <p class="text-[11px] text-surface-500 mb-2">Select a broker, symbol, and date range to fetch candle data into your local database</p>

          <div>
            <label class="label">Exchange / Broker</label>
            <select v-model="form.exchange" class="select">
              <option v-for="b in brokers" :key="b.id" :value="b.id">{{ b.name }}</option>
            </select>
          </div>

          <div>
            <label class="label">Symbol</label>
            <input v-model="form.symbol" class="input" placeholder="EUR-USD" />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="label">Start Date</label>
              <input v-model="form.start_date" type="date" class="input" />
            </div>
            <div>
              <label class="label">End Date (optional)</label>
              <input v-model="form.end_date" type="date" class="input" />
            </div>
          </div>

          <div>
            <label class="label">Import Granularity</label>
            <select v-model="form.granularity" class="select">
              <option value="1m">M1 — 1 Minute (default)</option>
              <option value="5s">S5 — 5 Seconds</option>
              <option value="10s">S10 — 10 Seconds</option>
              <option value="15s">S15 — 15 Seconds</option>
              <option value="30s">S30 — 30 Seconds</option>
            </select>
            <p v-if="form.granularity !== '1m'" class="text-xs text-yellow-400 mt-1">
              Sub-minute data is fetched at {{ form.granularity }} and aggregated to 1m for storage. Import will take longer.
            </p>
          </div>

          <button @click="startImport" class="btn-primary w-full" :disabled="importing || !form.exchange || !form.symbol">
            <span v-if="importing" class="flex items-center justify-center gap-2">
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              Importing...
            </span>
            <span v-else>Import Candles</span>
          </button>
          <button v-if="importing" @click="cancelImport" class="btn-secondary w-full text-sm">
            Cancel Import
          </button>

          <p v-if="importMsg" class="text-xs" :class="importError ? 'text-red-400' : 'text-green-400'">{{ importMsg }}</p>
        </div>

        <!-- Progress -->
        <ProgressBar
          :visible="importing"
          :percent="progress.current"
          :eta="progress.eta"
          label="Importing candles"
        />

        <!-- Import Info -->
        <div v-if="importing && importInfo" class="card text-xs space-y-1">
          <div v-if="importInfo.exchange" class="text-surface-500">Exchange: <span class="text-surface-300">{{ importInfo.exchange }}</span></div>
          <div v-if="importInfo.symbol" class="text-surface-500">Symbol: <span class="text-surface-300">{{ importInfo.symbol }}</span></div>
          <div v-if="importInfo.count" class="text-surface-500">Candles: <span class="text-surface-300 font-mono">{{ importInfo.count?.toLocaleString() }}</span></div>
        </div>

        <!-- Quick Presets -->
        <div class="card">
          <h2 class="text-sm font-semibold text-surface-300 mb-3">Quick Presets</h2>
          <div class="space-y-2">
            <button v-for="preset in presets" :key="preset.symbol"
              @click="applyPreset(preset)"
              class="w-full text-left p-2 rounded-lg bg-surface-800 hover:bg-surface-700 transition-colors text-sm">
              <div class="text-surface-200 font-medium">{{ preset.symbol }}</div>
              <div class="text-xs text-surface-500">{{ preset.exchange }} | {{ preset.start_date }} to {{ preset.end_date }}</div>
            </button>
          </div>
        </div>
      </div>

      <!-- Existing Data -->
      <div class="lg:col-span-2">
        <div class="card">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-surface-300">Available Candle Data</h2>
            <button @click="loadExisting" class="text-xs text-brand-400 hover:text-brand-300">Refresh</button>
          </div>

          <div v-if="loadingExisting" class="text-surface-500 text-sm">Loading...</div>

          <div v-else-if="existingData.length === 0" class="text-surface-500 text-sm text-center py-8">
            No candle data found. Import some data using the form.
          </div>

          <div v-else class="overflow-x-auto">
          <table class="w-full text-sm min-w-[600px]">
            <thead>
              <tr class="text-surface-500 text-xs border-b border-surface-700">
                <th class="text-left py-2">Exchange</th>
                <th class="text-left py-2">Symbol</th>
                <th class="text-left py-2">From</th>
                <th class="text-left py-2">To</th>
                <th class="text-left py-2">Timeframes</th>
                <th class="text-right py-2">Candles</th>
                <th class="text-right py-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(d, i) in existingData" :key="i" class="border-b border-surface-800 group">
                <td class="py-2 text-surface-300">{{ d.exchange }}</td>
                <td class="py-2 font-mono text-surface-100">{{ d.symbol }}</td>
                <td class="py-2 text-surface-400">{{ d.from || d.start_date || 'N/A' }}</td>
                <td class="py-2 text-surface-400">{{ d.to || d.end_date || 'N/A' }}</td>
                <td class="py-2">
                  <div class="flex flex-wrap gap-1">
                    <span v-for="tf in (d.timeframes || [])" :key="tf"
                      class="px-1.5 py-0.5 bg-surface-700 rounded text-xs font-mono text-surface-300">{{ tf }}</span>
                    <span v-if="!d.timeframes || d.timeframes.length === 0" class="text-surface-500 text-xs">-</span>
                  </div>
                </td>
                <td class="py-2 text-right font-mono text-surface-300">{{ d.count ? d.count.toLocaleString() : '-' }}</td>
                <td class="py-2 text-right space-x-2">
                  <button
                    @click="openDownload(d)"
                    class="text-xs text-brand-400 hover:text-brand-300 opacity-0 group-hover:opacity-100 transition-opacity">
                    Download
                  </button>
                  <button
                    @click="confirmDelete(d)"
                    class="text-xs text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition-opacity">
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Confirm Modal -->
    <div v-if="deletingItem" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="deletingItem = null">
      <div class="card w-full max-w-sm mx-4">
        <h2 class="text-base font-semibold mb-3">Delete Candle Data</h2>
        <p class="text-sm text-surface-400 mb-4">
          Delete all candle data for
          <span class="text-surface-100 font-medium">{{ deletingItem.exchange }} / {{ deletingItem.symbol }}</span>?
          <br/><span class="text-xs text-surface-500">{{ deletingItem.count ? deletingItem.count.toLocaleString() + ' candles' : '' }}</span>
        </p>
        <div class="flex gap-2">
          <button @click="doDelete" class="btn-danger flex-1" :disabled="deleting">
            {{ deleting ? 'Deleting...' : 'Delete' }}
          </button>
          <button @click="deletingItem = null" class="btn-secondary flex-1">Cancel</button>
        </div>
        <p v-if="deleteError" class="text-xs text-red-400 mt-2">{{ deleteError }}</p>
      </div>
    </div>
    <!-- Download Modal -->
    <div v-if="downloadItem" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="downloadItem = null">
      <div class="card w-full max-w-sm mx-4">
        <h2 class="text-base font-semibold mb-3">Download CSV</h2>
        <p class="text-sm text-surface-400 mb-4">
          <span class="text-surface-100 font-medium">{{ downloadItem.exchange }} / {{ downloadItem.symbol }}</span>
        </p>

        <div class="space-y-3">
          <div>
            <label class="label">Timeframe</label>
            <select v-model="downloadForm.timeframe" class="select">
              <option v-for="tf in (downloadItem.timeframes || [])" :key="tf" :value="tf">{{ tf }}</option>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="label">Start Date</label>
              <input v-model="downloadForm.start_date" type="date" class="input"
                :min="downloadItem.from || downloadItem.start_date"
                :max="downloadForm.end_date" />
            </div>
            <div>
              <label class="label">End Date</label>
              <input v-model="downloadForm.end_date" type="date" class="input"
                :min="downloadForm.start_date"
                :max="downloadItem.to || downloadItem.end_date" />
            </div>
          </div>
        </div>

        <div class="flex gap-2 mt-4">
          <button @click="doDownload" class="btn-primary flex-1" :disabled="downloading">
            {{ downloading ? 'Downloading...' : 'Download' }}
          </button>
          <button @click="downloadItem = null" class="btn-secondary flex-1">Cancel</button>
        </div>
        <p v-if="downloadError" class="text-xs text-red-400 mt-2">{{ downloadError }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, defaultBrokerId } from '../api'
import { useWebSocket } from '../useWebSocket'
import ProgressBar from '../components/ProgressBar.vue'
import { useProcessManager } from '../useProcessManager'

const pm = useProcessManager()

const brokers = ref([])
const importing = ref(false)
const importMsg = ref('')
const importError = ref(false)
const existingData = ref([])
const loadingExisting = ref(true)
const currentTaskId = ref(null)
const progress = ref({ current: 0, eta: 0 })
const importInfo = ref(null)

// Delete state
const deletingItem = ref(null)
const deleting = ref(false)
const deleteError = ref('')

// Download state
const downloadItem = ref(null)
const downloading = ref(false)
const downloadError = ref('')
const downloadForm = ref({ timeframe: '', start_date: '', end_date: '' })

const form = ref({
  exchange: '',
  symbol: 'EUR-USD',
  start_date: '2026-01-01',
  end_date: '',
  granularity: '1m',
})

const presets = [
  { exchange: 'OANDA', symbol: 'EUR-USD', start_date: '2026-01-01', end_date: '2026-03-20' },
  { exchange: 'OANDA', symbol: 'GBP-USD', start_date: '2024-01-01', end_date: '2024-12-31' },
  { exchange: 'OANDA', symbol: 'XAU-USD', start_date: '2024-01-01', end_date: '2024-12-31' },
  { exchange: 'OANDA', symbol: 'USD-JPY', start_date: '2024-01-01', end_date: '2024-12-31' },
]

// WebSocket handler
useWebSocket((msg) => {
  const { event, id, data } = msg
  // Note: msg.id is os.getpid() (integer), not the task UUID.
  // The event prefix already namespaces messages, so no id filtering needed.

  if (event === 'candles.progressbar') {
    progress.value = {
      current: data?.current || 0,
      eta: data?.estimated_remaining_seconds || 0,
    }
    if (currentTaskId.value) pm.update(currentTaskId.value, { progress: data?.current || 0, eta: data?.estimated_remaining_seconds || 0 })
    // Update import info from progress data
    if (data?.count !== undefined) {
      importInfo.value = { ...importInfo.value, count: data.count }
    }
  } else if (event === 'candles.general_info') {
    importInfo.value = data
  } else if (event === 'candles.alert') {
    if (data?.type === 'success') {
      importMsg.value = data?.message || 'Import completed!'
      importError.value = false
      importing.value = false
      progress.value = { current: 100, eta: 0 }
      pm.complete(currentTaskId.value)
      loadExisting()
    } else if (data?.type === 'error') {
      importMsg.value = data?.message || 'Import failed'
      importError.value = true
      importing.value = false
      pm.fail(currentTaskId.value)
    } else if (data?.type === 'info') {
      importMsg.value = data?.message || ''
      importError.value = false
    }
  } else if (event === 'candles.exception') {
    importMsg.value = data?.error || 'Import failed'
    importError.value = true
    importing.value = false
    progress.value = { current: 0, eta: 0 }
    pm.fail(currentTaskId.value)
  } else if (event === 'candles.termination') {
    importing.value = false
    importMsg.value = 'Import terminated.'
    importError.value = false
    progress.value = { current: 0, eta: 0 }
    pm.cancel(currentTaskId.value)
  } else if (event === 'candles.unexpectedTermination') {
    importing.value = false
    importMsg.value = data?.message || 'Import terminated unexpectedly.'
    importError.value = true
    progress.value = { current: 0, eta: 0 }
    pm.fail(currentTaskId.value)
  }
})

function applyPreset(preset) {
  form.value.exchange = preset.exchange
  form.value.symbol = preset.symbol
  form.value.start_date = preset.start_date
  form.value.end_date = preset.end_date
}

async function startImport() {
  importing.value = true
  importMsg.value = ''
  importError.value = false
  importInfo.value = null
  progress.value = { current: 0, eta: 0 }

  const id = crypto.randomUUID()
  currentTaskId.value = id

  const importLabel = `Import · ${form.value.symbol} · ${form.value.exchange}`
  pm.register(id, { type: 'import', label: importLabel, cancelFn: cancelImport, routePath: '/import' })

  try {
    await api.importCandles({
      id,
      exchange: form.value.exchange,
      symbol: form.value.symbol,
      start_date: form.value.start_date,
      granularity: form.value.granularity,
    })
    importMsg.value = 'Import started...'
  } catch (e) {
    importMsg.value = e.message
    importError.value = true
    importing.value = false
    pm.fail(id)
  }
}

async function cancelImport() {
  if (!currentTaskId.value) return
  try {
    await api.cancelImport(currentTaskId.value)
    importMsg.value = 'Cancellation requested...'
  } catch (e) {
    importMsg.value = e.message
    importError.value = true
  }
}

function confirmDelete(item) {
  deletingItem.value = item
  deleteError.value = ''
}

async function doDelete() {
  if (!deletingItem.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await api.deleteCandles(deletingItem.value.exchange, deletingItem.value.symbol)
    deletingItem.value = null
    await loadExisting()
  } catch (e) {
    deleteError.value = e.message
  } finally {
    deleting.value = false
  }
}

function openDownload(item) {
  downloadItem.value = item
  downloadError.value = ''
  downloadForm.value = {
    timeframe: item.timeframes?.[0] || '1m',
    start_date: item.from || item.start_date || '',
    end_date: item.to || item.end_date || '',
  }
}

async function doDownload() {
  downloading.value = true
  downloadError.value = ''
  try {
    await api.downloadCandles({
      exchange: downloadItem.value.exchange,
      symbol: downloadItem.value.symbol,
      timeframe: downloadForm.value.timeframe,
      start_date: downloadForm.value.start_date,
      end_date: downloadForm.value.end_date,
    })
    downloadItem.value = null
  } catch (e) {
    downloadError.value = e.message
  } finally {
    downloading.value = false
  }
}

async function loadExisting() {
  loadingExisting.value = true
  try {
    const res = await api.getExistingCandles({})
    existingData.value = res.data || []
  } catch {
    existingData.value = []
  } finally {
    loadingExisting.value = false
  }
}

onMounted(async () => {
  try {
    const res = await api.getBacktestingBrokers()
    brokers.value = res.data || []
    form.value.exchange = defaultBrokerId(brokers.value)
  } catch (e) {
    console.error(e)
  }
  await loadExisting()
})
</script>
