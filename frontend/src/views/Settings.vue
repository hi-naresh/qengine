<template>
  <div>
    <h1 class="text-2xl font-bold text-center mb-8">Settings</h1>

    <!-- Settings Tabs -->
    <div class="flex gap-2 mb-5 flex-wrap">
      <button v-for="tab in tabs" :key="tab" @click="activeTab = tab"
        class="btn-sm" :class="activeTab === tab ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        {{ tab }}
      </button>
    </div>

    <!-- LLM Configuration -->
    <div v-if="activeTab === 'LLM'" class="max-w-lg">
      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">LLM Provider</h2>

        <div v-if="llmSettings.configured" class="mb-4 p-3 rounded-lg"
          :class="llmConnectionStatus.connected === true ? 'bg-green-500/10' : llmConnectionStatus.connected === false ? 'bg-red-500/10' : 'bg-green-500/10'">
          <div class="flex items-center gap-2 text-sm"
            :class="llmConnectionStatus.connected === true ? 'text-green-400' : llmConnectionStatus.connected === false ? 'text-red-400' : 'text-green-400'">
            <span class="w-2 h-2 rounded-full"
              :class="llmConnectionStatus.connected === true ? 'bg-green-400' : llmConnectionStatus.connected === false ? 'bg-red-400' : 'bg-green-400'"></span>
            <span v-if="llmConnectionStatus.connected === true">Connected: {{ llmSettings.provider }} ({{ llmConnectionStatus.details?.model || llmSettings.model }})</span>
            <span v-else-if="llmConnectionStatus.connected === false">Connection Failed: {{ llmConnectionStatus.error }}</span>
            <span v-else>Configured: {{ llmSettings.provider }} ({{ llmSettings.model }})</span>
          </div>
          <div class="text-xs text-surface-500 mt-1">API Key: {{ llmSettings.api_key_masked }}</div>
          <div v-if="llmConnectionStatus.details?.response" class="text-xs text-surface-500 mt-1">
            Test response: {{ llmConnectionStatus.details.response }}
          </div>
        </div>

        <div class="space-y-3">
          <div>
            <label class="label">Provider</label>
            <select v-model="llmForm.provider" class="select">
              <option value="gemini">Google Gemini</option>
              <option value="anthropic">Anthropic Claude</option>
              <option value="openai">OpenAI GPT</option>
            </select>
          </div>
          <div>
            <label class="label">API Key</label>
            <input v-model="llmForm.api_key" type="password" class="input" placeholder="Enter API key" />
          </div>
          <div>
            <label class="label">Model (optional)</label>
            <input v-model="llmForm.model" class="input" :placeholder="defaultModel" />
          </div>
          <div>
            <label class="label">Temperature</label>
            <input v-model.number="llmForm.temperature" type="number" step="0.1" min="0" max="1" class="input" />
          </div>
          <div class="flex gap-2">
            <button @click="saveLLM" class="btn-primary flex-1" :disabled="savingLLM">
              {{ savingLLM ? 'Saving & Testing...' : 'Save & Test Connection' }}
            </button>
            <button v-if="llmSettings.configured" @click="deleteLLM" class="btn-danger">Remove</button>
          </div>
          <div v-if="testingLLM" class="flex items-center gap-2 text-xs text-surface-400">
            <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            Testing connection...
          </div>
          <p v-if="llmMessage" class="text-xs" :class="llmError ? 'text-red-400' : 'text-green-400'">{{ llmMessage }}</p>
        </div>
      </div>
    </div>

    <!-- Broker Keys -->
    <div v-if="activeTab === 'Broker Keys'" class="max-w-lg space-y-4">
      <div class="card">
        <p class="text-sm text-surface-400 mb-3">Broker API connections are managed from the Brokers page.</p>
        <a href="#/brokers" class="btn-primary inline-block px-4 py-2 text-sm">Go to Brokers</a>
      </div>

      <!-- Export -->
      <div class="card">
        <h2 class="text-sm font-semibold mb-3 text-surface-300">Export API Keys</h2>
        <p class="text-xs text-surface-500 mb-3">Download all broker API keys as a CSV file. Requires password confirmation.</p>
        <div class="flex items-center gap-3">
          <input v-model="exportPassword" type="password" class="input flex-1" placeholder="Enter password to confirm" />
          <button @click="exportApiKeys" class="btn-primary btn-sm" :disabled="exportingKeys || !exportPassword">
            {{ exportingKeys ? 'Exporting...' : 'Export CSV' }}
          </button>
        </div>
        <p v-if="exportMessage" class="text-xs mt-2" :class="exportError ? 'text-red-400' : 'text-green-400'">{{ exportMessage }}</p>
      </div>

      <!-- Import -->
      <div class="card">
        <h2 class="text-sm font-semibold mb-3 text-surface-300">Import API Keys</h2>
        <p class="text-xs text-surface-500 mb-3">Import broker API keys from a CSV file. Expected columns: Name, Exchange, API Key, API Secret.</p>
        <div class="space-y-3">
          <div>
            <input type="file" ref="importFileInput" accept=".csv" @change="onImportFileChange" class="text-xs text-surface-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:bg-surface-700 file:text-surface-300 hover:file:bg-surface-600" />
          </div>
          <div v-if="importPreview" class="bg-surface-800 rounded p-3 text-xs font-mono text-surface-400 max-h-[150px] overflow-auto whitespace-pre">{{ importPreview }}</div>
          <button @click="importApiKeys" class="btn-primary btn-sm" :disabled="importingKeys || !importCsvContent">
            {{ importingKeys ? 'Importing...' : 'Import' }}
          </button>
          <p v-if="importMessage" class="text-xs" :class="importError ? 'text-red-400' : 'text-green-400'">{{ importMessage }}</p>
        </div>
      </div>
    </div>

    <!-- Notifications -->
    <div v-if="activeTab === 'Notifications'" class="space-y-4 max-w-lg">
      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Notification Channels</h2>
        <p class="text-xs text-surface-500 mb-4">Configure notification channels for live trading alerts. Supports Telegram, Discord, and Slack.</p>

        <div v-if="notifKeys.length === 0" class="text-sm text-surface-500 py-4 text-center">
          No notification channels configured yet.
        </div>

        <div v-for="key in notifKeys" :key="key.id" class="flex items-center justify-between p-3 bg-surface-800 rounded-lg mb-2">
          <div>
            <div class="text-sm text-surface-200 font-medium">{{ key.name }}</div>
            <div class="text-xs text-surface-500 mt-0.5">
              <span class="capitalize">{{ key.driver }}</span>
              <template v-if="key.driver === 'telegram'"> &middot; Token: {{ key.bot_token }} &middot; Chat: {{ key.chat_id }}</template>
              <template v-else> &middot; Webhook: {{ key.webhook }}</template>
            </div>
          </div>
          <button @click="deleteNotifKey(key.id)" class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20">Delete</button>
        </div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Add Notification Channel</h2>

        <div class="space-y-3">
          <div>
            <label class="label">Name</label>
            <input v-model="notifForm.name" class="input" placeholder="e.g. My Telegram Bot" />
          </div>
          <div>
            <label class="label">Driver</label>
            <select v-model="notifForm.driver" class="select">
              <option value="telegram">Telegram</option>
              <option value="discord">Discord</option>
              <option value="slack">Slack</option>
            </select>
          </div>

          <template v-if="notifForm.driver === 'telegram'">
            <div>
              <label class="label">Bot Token</label>
              <input v-model="notifForm.fields.bot_token" class="input" placeholder="123456:ABC-DEF..." />
              <p class="text-xs text-surface-600 mt-1">Get from @BotFather on Telegram</p>
            </div>
            <div>
              <label class="label">Chat ID</label>
              <input v-model="notifForm.fields.chat_id" class="input" placeholder="-1001234567890" />
              <p class="text-xs text-surface-600 mt-1">Your chat or group ID</p>
            </div>
          </template>

          <template v-if="notifForm.driver === 'discord'">
            <div>
              <label class="label">Webhook URL</label>
              <input v-model="notifForm.fields.webhook" class="input" placeholder="https://discord.com/api/webhooks/..." />
              <p class="text-xs text-surface-600 mt-1">Server Settings > Integrations > Webhooks</p>
            </div>
          </template>

          <template v-if="notifForm.driver === 'slack'">
            <div>
              <label class="label">Webhook URL</label>
              <input v-model="notifForm.fields.webhook" class="input" placeholder="https://hooks.slack.com/services/..." />
              <p class="text-xs text-surface-600 mt-1">Create an Incoming Webhook in your Slack workspace</p>
            </div>
          </template>

          <div class="flex gap-2">
            <button @click="saveNotifKey" class="btn-primary flex-1" :disabled="savingNotif">
              {{ savingNotif ? 'Saving...' : 'Save Channel' }}
            </button>
            <button @click="testNotif" class="btn-sm bg-surface-700 text-surface-300" :disabled="testingNotif">
              {{ testingNotif ? 'Sending...' : 'Test' }}
            </button>
          </div>
          <p v-if="notifMessage" class="text-xs" :class="notifError ? 'text-red-400' : 'text-green-400'">{{ notifMessage }}</p>
        </div>
      </div>
    </div>

    <!-- Broker Cost & Randomness Model (per-broker) -->
    <div v-if="activeTab === 'Cost & Randomness'" class="space-y-4">
      <!-- Broker Selector -->
      <div class="card max-w-lg">
        <h2 class="text-sm font-semibold mb-2 text-surface-300">Broker Cost & Randomness Model</h2>
        <p class="text-xs text-surface-500 mb-4">Each broker has its own cost, spread, slippage, and swap settings for backtesting. Select a broker to configure.</p>

        <div>
          <label class="label">Select Broker</label>
          <select v-model="costBroker" @change="onBrokerChange" class="select">
            <option v-for="b in availableBrokers" :key="b.id" :value="b.id">{{ b.name }}</option>
          </select>
        </div>
      </div>

      <!-- Broker Cost Info (leverage, fee model) -->
      <div v-if="costModel" class="card max-w-lg">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">{{ selectedBrokerName }} - Broker Info</h2>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
          <div class="p-3 bg-surface-800 rounded-lg">
            <div class="text-xs text-surface-500">Fee Model</div>
            <div class="text-sm text-surface-200 capitalize">{{ costModel.fee_model }}</div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg">
            <div class="text-xs text-surface-500">Settlement</div>
            <div class="text-sm text-surface-200">{{ costModel.settlement_currency }}</div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg">
            <div class="text-xs text-surface-500">Default Leverage</div>
            <div class="flex items-center gap-2">
              <input v-model.number="costLeverage" type="number" min="1" max="500" class="input w-20 py-1 text-sm" />
              <span class="text-surface-400 text-xs">x</span>
            </div>
          </div>
        </div>

        <button @click="saveCostModel" class="btn-primary btn-sm" :disabled="savingCost">
          {{ savingCost ? 'Saving...' : 'Save Leverage' }}
        </button>
        <p v-if="costMessage" class="text-xs mt-2" :class="costError ? 'text-red-400' : 'text-green-400'">{{ costMessage }}</p>
      </div>

      <!-- Backtest Cost Settings (per-broker) -->
      <div v-if="costBroker" class="card max-w-lg">
        <h2 class="text-sm font-semibold mb-2 text-surface-300">{{ selectedBrokerName }} - Backtest Cost & Randomness</h2>
        <p class="text-xs text-surface-500 mb-4">These settings are applied when backtesting with this broker.</p>

        <div class="space-y-4">
          <!-- Spread -->
          <div>
            <h3 class="text-xs font-semibold text-surface-400 mb-2 uppercase tracking-wide">Spread</h3>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Spread (pips)</label>
                <input v-model.number="btForm.spread_pips" type="number" step="0.1" min="0" class="input" />
                <p class="text-xs text-surface-600 mt-1">Default spread for this broker. 0 = no spread cost.</p>
              </div>
              <div>
                <label class="label">Spread Randomness</label>
                <input v-model.number="btForm.spread_randomness" type="number" step="0.05" min="0" max="1" class="input" />
                <p class="text-xs text-surface-600 mt-1">0 = fixed spread. 0.5 = spread varies +/-50% each trade.</p>
              </div>
            </div>
          </div>

          <!-- Slippage -->
          <div>
            <h3 class="text-xs font-semibold text-surface-400 mb-2 uppercase tracking-wide">Slippage</h3>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Slippage (pips)</label>
                <input v-model.number="btForm.slippage_pips" type="number" step="0.1" min="0" class="input" />
                <p class="text-xs text-surface-600 mt-1">Average slippage per order. 0 = no slippage.</p>
              </div>
              <div>
                <label class="label">Slippage Randomness</label>
                <input v-model.number="btForm.slippage_randomness" type="number" step="0.05" min="0" max="1" class="input" />
                <p class="text-xs text-surface-600 mt-1">0 = fixed slippage. 1.0 = varies from 0 to 2x slippage.</p>
              </div>
            </div>
          </div>

          <!-- Swap & Commission -->
          <div>
            <h3 class="text-xs font-semibold text-surface-400 mb-2 uppercase tracking-wide">Swap & Commission</h3>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Commission per Lot ($)</label>
                <input v-model.number="btForm.commission_per_lot" type="number" step="0.5" min="0" class="input" />
                <p class="text-xs text-surface-600 mt-1">Fixed commission per standard lot (on top of spread).</p>
              </div>
              <div class="flex items-end pb-6">
                <label class="flex items-center gap-2 text-sm text-surface-400 cursor-pointer">
                  <input v-model="btForm.swap_enabled" type="checkbox" class="rounded bg-surface-700 border-surface-500" />
                  Enable Overnight Swap
                </label>
              </div>
            </div>
          </div>

          <div class="flex items-center gap-3 pt-1">
            <button @click="saveBacktestSettings" class="btn-primary btn-sm" :disabled="savingBt">
              {{ savingBt ? 'Saving...' : 'Save Settings' }}
            </button>
            <button @click="resetBacktestDefaults" class="btn-sm bg-surface-700 text-surface-400">Reset Defaults</button>
          </div>
          <p v-if="btMessage" class="text-xs" :class="btMsgErr ? 'text-red-400' : 'text-green-400'">{{ btMessage }}</p>
        </div>
      </div>

    </div>

    <!-- About -->
    <div v-if="activeTab === 'About'" class="max-w-lg space-y-4">
      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">System Information</h2>
        <div v-if="aboutInfo" class="space-y-2">
          <div class="flex justify-between p-2 bg-surface-800 rounded" v-for="item in aboutItems" :key="item.label">
            <span class="text-xs text-surface-500">{{ item.label }}</span>
            <span class="text-xs text-surface-200 font-mono">{{ item.value }}</span>
          </div>
        </div>
        <div v-else class="text-sm text-surface-500 py-4 text-center">Loading system info...</div>
      </div>

      <div v-if="aboutInfo && aboutInfo.update_info && aboutInfo.update_info.is_update_info_available" class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Updates</h2>
        <div class="space-y-2">
          <div class="flex justify-between p-2 bg-surface-800 rounded">
            <span class="text-xs text-surface-500">Latest Version (PyPI)</span>
            <span class="text-xs font-mono" :class="aboutInfo.update_info.latest_version !== aboutInfo.system_info.qengine_version ? 'text-amber-400' : 'text-green-400'">
              {{ aboutInfo.update_info.latest_version }}
            </span>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">About QEngine</h2>
        <p class="text-xs text-surface-400 leading-relaxed">
          QEngine is a multi-asset algorithmic trading platform. It supports Forex, Commodities, Indices, and Crypto trading with built-in broker integrations for OANDA, IG Markets, and Interactive Brokers.
        </p>
        <div class="mt-3 flex gap-2">
          <span class="text-xs px-2 py-1 bg-brand-600/20 text-brand-400 rounded">Forex</span>
          <span class="text-xs px-2 py-1 bg-brand-600/20 text-brand-400 rounded">Commodities</span>
          <span class="text-xs px-2 py-1 bg-brand-600/20 text-brand-400 rounded">Indices</span>
          <span class="text-xs px-2 py-1 bg-brand-600/20 text-brand-400 rounded">Crypto</span>
        </div>
      </div>
    </div>

    <!-- Maintenance -->
    <div v-if="activeTab === 'Maintenance'" class="max-w-lg space-y-4">
      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Storage Overview</h2>
        <div v-if="storageInfo" class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div class="p-3 bg-surface-800 rounded-lg">
            <div class="text-xs text-surface-500">Cache</div>
            <div class="text-sm text-surface-200">{{ formatBytes(storageInfo.cache_size_bytes) }}</div>
            <div class="text-xs text-surface-500">{{ storageInfo.cache_files }} files</div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg">
            <div class="text-xs text-surface-500">Logs</div>
            <div class="text-sm text-surface-200">{{ formatBytes(storageInfo.log_size_bytes) }}</div>
            <div class="text-xs text-surface-500">{{ storageInfo.log_files }} files</div>
          </div>
          <div class="p-3 bg-surface-800 rounded-lg">
            <div class="text-xs text-surface-500">Redis</div>
            <div class="text-sm text-surface-200">{{ storageInfo.redis_memory }}</div>
            <div class="text-xs text-surface-500">{{ storageInfo.redis_keys }} keys</div>
          </div>
        </div>
        <div v-else class="text-sm text-surface-500 py-4 text-center">Loading storage info...</div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Cache & Data Cleanup</h2>
        <div class="space-y-3">
          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Candle Cache</div>
              <div class="text-xs text-surface-500">Cached candle data used by backtests (pickle files)</div>
            </div>
            <button @click="doClearCache('candle')" class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
              :disabled="maintOps.candle">
              {{ maintOps.candle ? 'Clearing...' : 'Clear' }}
            </button>
          </div>

          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">General Cache</div>
              <div class="text-xs text-surface-500">All temporary pickle cache files in storage/temp</div>
            </div>
            <button @click="doClearCache('pickle')" class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
              :disabled="maintOps.pickle">
              {{ maintOps.pickle ? 'Clearing...' : 'Clear' }}
            </button>
          </div>

          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Redis Cache</div>
              <div class="text-xs text-surface-500">Flush the Redis database (pub/sub channels, active processes)</div>
            </div>
            <button @click="doClearCache('redis')" class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
              :disabled="maintOps.redis">
              {{ maintOps.redis ? 'Flushing...' : 'Flush' }}
            </button>
          </div>

          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Log Files</div>
              <div class="text-xs text-surface-500">Backtest, optimization, live trading, and other log files</div>
            </div>
            <button @click="doClearCache('logs')" class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
              :disabled="maintOps.logs">
              {{ maintOps.logs ? 'Clearing...' : 'Clear' }}
            </button>
          </div>

          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Imported Candle Data</div>
              <div class="text-xs text-surface-500">Delete ALL imported candle data from the database (irreversible)</div>
            </div>
            <button @click="doDeleteAllCandles" class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20"
              :disabled="maintOps.candles">
              {{ maintOps.candles ? 'Deleting...' : 'Delete All' }}
            </button>
          </div>

          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Issues / Tickets</div>
              <div class="text-xs text-surface-500">Clear all issue tickets from the database</div>
            </div>
            <div class="flex gap-2">
              <select v-model="clearIssueStatus" class="select text-xs py-1 px-2 w-28">
                <option value="">All Issues</option>
                <option value="done">Done only</option>
                <option value="todo">Todo only</option>
              </select>
              <button @click="doClearIssues" class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                :disabled="maintOps.issues">
                {{ maintOps.issues ? 'Clearing...' : 'Clear' }}
              </button>
            </div>
          </div>

          <div class="pt-2 border-t border-surface-700">
            <button @click="doClearAll" class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20 w-full"
              :disabled="maintOps.all">
              {{ maintOps.all ? 'Clearing Everything...' : 'Clear All Caches & Logs' }}
            </button>
          </div>
        </div>
        <p v-if="maintMessage" class="text-xs mt-3" :class="maintError ? 'text-red-400' : 'text-green-400'">{{ maintMessage }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, defaultBrokerId } from '../api'

const activeTab = ref('LLM')
const tabs = ['LLM', 'Broker Keys', 'Notifications', 'Cost & Randomness', 'Maintenance', 'About']

// LLM
const llmSettings = ref({})
const savingLLM = ref(false)
const testingLLM = ref(false)
const llmMessage = ref('')
const llmError = ref(false)
const llmForm = ref({ provider: 'gemini', api_key: '', model: '', temperature: 0.3 })
const llmConnectionStatus = ref({})

const defaultModel = computed(() => {
  const models = { gemini: 'gemini-2.0-flash', anthropic: 'claude-sonnet-4-6', openai: 'gpt-4o' }
  return models[llmForm.value.provider] || ''
})

// Broker
const availableBrokers = ref([])
const selectedBrokerName = computed(() => {
  const b = availableBrokers.value.find(x => x.id === costBroker.value)
  return b ? b.name : costBroker.value
})

// Cost Model (per-broker)
const costBroker = ref('')
const costModel = ref(null)
const costLeverage = ref(30)
const savingCost = ref(false)
const costMessage = ref('')
const costError = ref(false)
const exchangeTypes = ref([])

// Backtest Cost & Randomness (per-broker)
const btForm = ref({
  spread_pips: 2.0,
  spread_randomness: 0.0,
  slippage_pips: 0.0,
  slippage_randomness: 0.0,
  swap_enabled: true,
  commission_per_lot: 0.0,
})
const savingBt = ref(false)
const btMessage = ref('')
const btMsgErr = ref(false)

// API Key Import/Export
const exportPassword = ref('')
const exportingKeys = ref(false)
const exportMessage = ref('')
const exportError = ref(false)
const importFileInput = ref(null)
const importCsvContent = ref('')
const importPreview = ref('')
const importingKeys = ref(false)
const importMessage = ref('')
const importError = ref(false)

// Notifications
const notifKeys = ref([])
const notifForm = ref({ name: '', driver: 'telegram', fields: {} })
const savingNotif = ref(false)
const testingNotif = ref(false)
const notifMessage = ref('')
const notifError = ref(false)

// About
const aboutInfo = ref(null)
const aboutItems = computed(() => {
  if (!aboutInfo.value) return []
  const si = aboutInfo.value.system_info || {}
  const items = [
    { label: 'QEngine Version', value: si.qengine_version || 'N/A' },
    { label: 'Python Version', value: si.python_version || 'N/A' },
    { label: 'Operating System', value: si.operating_system || 'N/A' },
    { label: 'CPU Cores', value: si.cpu_cores || 'N/A' },
    { label: 'Docker', value: si.is_docker ? 'Yes' : 'No' },
    { label: 'Live Trading', value: aboutInfo.value.has_live_plugin_installed ? 'Available' : 'Not Available' },
    { label: 'Plan', value: aboutInfo.value.plan || 'N/A' },
  ]
  if (si.live_plugin_version) {
    items.splice(1, 0, { label: 'Live Plugin Version', value: si.live_plugin_version })
  }
  return items
})

// Maintenance
const storageInfo = ref(null)
const maintOps = ref({ candle: false, pickle: false, redis: false, logs: false, issues: false, candles: false, all: false })
const clearIssueStatus = ref('')
const maintMessage = ref('')
const maintError = ref(false)

// --- Broker change loads both cost model AND backtest settings ---

async function onBrokerChange() {
  await Promise.all([loadCostModel(), loadBacktestSettings()])
}

// --- Backtest Cost Methods (per-broker) ---

async function loadBacktestSettings() {
  if (!costBroker.value) return
  try {
    const res = await api.getBacktestSettings(costBroker.value)
    const d = res.data || {}
    btForm.value = {
      spread_pips: d.spread_pips ?? 2.0,
      spread_randomness: d.spread_randomness ?? 0.0,
      slippage_pips: d.slippage_pips ?? 0.0,
      slippage_randomness: d.slippage_randomness ?? 0.0,
      swap_enabled: d.swap_enabled ?? true,
      commission_per_lot: d.commission_per_lot ?? 0.0,
    }
  } catch {
    resetBacktestDefaults()
  }
}

async function saveBacktestSettings() {
  savingBt.value = true
  btMessage.value = ''
  try {
    await api.saveBacktestSettings({
      broker_id: costBroker.value,
      ...btForm.value,
    })
    btMessage.value = `Backtest settings saved for ${selectedBrokerName.value}`
    btMsgErr.value = false
  } catch (e) {
    btMessage.value = e.message
    btMsgErr.value = true
  } finally {
    savingBt.value = false
  }
}

function resetBacktestDefaults() {
  btForm.value = {
    spread_pips: 2.0,
    spread_randomness: 0.0,
    slippage_pips: 0.0,
    slippage_randomness: 0.0,
    swap_enabled: true,
    commission_per_lot: 0.0,
  }
  btMessage.value = 'Reset to defaults (not saved yet)'
  btMsgErr.value = false
}

// --- Cost Model Methods ---

async function loadCostModel() {
  if (!costBroker.value) return
  costMessage.value = ''
  try {
    const res = await api.getCostModel(costBroker.value)
    costModel.value = res.data
    costLeverage.value = res.data.default_leverage || 30
  } catch (e) {
    costModel.value = null
    console.error(e)
  }
}

async function saveCostModel() {
  savingCost.value = true
  costMessage.value = ''
  try {
    await api.updateCostModel({
      broker_id: costBroker.value,
      leverage: costLeverage.value,
    })
    costMessage.value = 'Leverage updated'
    costError.value = false
  } catch (e) {
    costMessage.value = e.message
    costError.value = true
  } finally {
    savingCost.value = false
  }
}

// --- Notification Methods ---

async function loadNotifKeys() {
  try {
    const res = await api.getNotificationKeys()
    notifKeys.value = res.data || []
  } catch (e) {
    console.error('Failed to load notification keys:', e)
  }
}

async function saveNotifKey() {
  if (!notifForm.value.name.trim()) {
    notifMessage.value = 'Name is required'
    notifError.value = true
    return
  }
  savingNotif.value = true
  notifMessage.value = ''
  try {
    await api.storeNotificationKey({
      name: notifForm.value.name,
      driver: notifForm.value.driver,
      fields: notifForm.value.fields,
    })
    notifMessage.value = 'Notification channel saved successfully'
    notifError.value = false
    notifForm.value = { name: '', driver: 'telegram', fields: {} }
    await loadNotifKeys()
  } catch (e) {
    notifMessage.value = e.message
    notifError.value = true
  } finally {
    savingNotif.value = false
  }
}

async function deleteNotifKey(id) {
  try {
    await api.deleteNotificationKey(id)
    await loadNotifKeys()
  } catch (e) {
    notifMessage.value = e.message
    notifError.value = true
  }
}

async function testNotif() {
  testingNotif.value = true
  notifMessage.value = ''
  try {
    const res = await api.testNotification({
      driver: notifForm.value.driver,
      fields: notifForm.value.fields,
    })
    notifMessage.value = res.message || 'Test notification sent!'
    notifError.value = false
  } catch (e) {
    notifMessage.value = e.message
    notifError.value = true
  } finally {
    testingNotif.value = false
  }
}

// --- Maintenance Methods ---

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

async function loadStorageInfo() {
  try {
    const res = await api.getStorageInfo()
    storageInfo.value = res.data
  } catch (e) {
    console.error('Failed to load storage info:', e)
  }
}

async function doClearCache(type) {
  maintOps.value[type] = true
  maintMessage.value = ''
  try {
    let res
    if (type === 'candle') res = await api.clearCandleCache()
    else if (type === 'pickle') res = await api.clearCache()
    else if (type === 'redis') res = await api.flushRedis()
    else if (type === 'logs') res = await api.clearLogs()
    maintMessage.value = res.message || 'Done'
    maintError.value = false
    await loadStorageInfo()
  } catch (e) {
    maintMessage.value = e.message
    maintError.value = true
  } finally {
    maintOps.value[type] = false
  }
}

async function doClearAll() {
  maintOps.value.all = true
  maintMessage.value = ''
  const results = []
  try {
    for (const fn of [api.clearCandleCache, api.clearCache, api.flushRedis, api.clearLogs]) {
      try {
        const r = await fn()
        results.push(r.message)
      } catch (e) {
        results.push(`Error: ${e.message}`)
      }
    }
    maintMessage.value = results.join(' | ')
    maintError.value = false
    await loadStorageInfo()
  } finally {
    maintOps.value.all = false
  }
}

async function doClearIssues() {
  maintOps.value.issues = true
  maintMessage.value = ''
  try {
    const res = await api.clearIssues(clearIssueStatus.value || null)
    maintMessage.value = `Cleared ${res.deleted || 0} issue(s)`
    maintError.value = false
  } catch (e) {
    maintMessage.value = e.message
    maintError.value = true
  } finally {
    maintOps.value.issues = false
  }
}

async function doDeleteAllCandles() {
  if (!confirm('Are you sure you want to delete ALL imported candle data? This cannot be undone.')) return
  maintOps.value.candles = true
  maintMessage.value = ''
  try {
    const res = await api.deleteAllCandles()
    maintMessage.value = res.message || 'All candle data deleted'
    maintError.value = false
    await loadStorageInfo()
  } catch (e) {
    maintMessage.value = e.message
    maintError.value = true
  } finally {
    maintOps.value.candles = false
  }
}

// --- API Key Import/Export Methods ---

async function exportApiKeys() {
  exportingKeys.value = true
  exportMessage.value = ''
  try {
    const token = localStorage.getItem('te_token') || ''
    const res = await fetch('/download/download-api-keys', {
      method: 'POST',
      headers: { 'Authorization': token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: exportPassword.value }),
    })
    if (res.status === 401) {
      exportMessage.value = 'Incorrect password'
      exportError.value = true
      return
    }
    if (!res.ok) {
      const t = await res.text()
      exportMessage.value = t || 'Export failed'
      exportError.value = true
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'api-keys.csv'
    a.click()
    URL.revokeObjectURL(url)
    exportMessage.value = 'API keys exported successfully'
    exportError.value = false
    exportPassword.value = ''
  } catch (e) {
    exportMessage.value = e.message
    exportError.value = true
  } finally {
    exportingKeys.value = false
  }
}

function onImportFileChange(e) {
  const file = e.target.files[0]
  if (!file) { importCsvContent.value = ''; importPreview.value = ''; return }
  const reader = new FileReader()
  reader.onload = (ev) => {
    importCsvContent.value = ev.target.result
    const lines = ev.target.result.split('\n').slice(0, 5)
    importPreview.value = lines.join('\n') + (lines.length < ev.target.result.split('\n').length ? '\n...' : '')
  }
  reader.readAsText(file)
}

async function importApiKeys() {
  importingKeys.value = true
  importMessage.value = ''
  try {
    const res = await api.importApiKeys(importCsvContent.value)
    if (res.success) {
      importMessage.value = `Imported ${res.imported_count || 0} key(s) successfully`
      importError.value = false
      importCsvContent.value = ''
      importPreview.value = ''
      if (importFileInput.value) importFileInput.value.value = ''
    } else {
      importMessage.value = res.error || 'Import failed'
      importError.value = true
    }
  } catch (e) {
    importMessage.value = e.message
    importError.value = true
  } finally {
    importingKeys.value = false
  }
}

// --- About Methods ---

async function loadAboutInfo() {
  try {
    const res = await api.getGeneralInfo()
    aboutInfo.value = res
  } catch (e) {
    console.error('Failed to load about info:', e)
  }
}

// --- LLM Methods ---

async function testLLMConnection(provider, apiKey, model, temperature) {
  testingLLM.value = true
  try {
    const res = await api.testLLMConnection({ provider, api_key: apiKey, model: model || null, temperature })
    llmConnectionStatus.value = res.data
    if (res.data.connected) {
      llmMessage.value = 'LLM saved and connected successfully'
      llmError.value = false
    } else {
      llmMessage.value = `Saved but connection failed: ${res.data.error}`
      llmError.value = true
    }
  } catch (e) {
    llmConnectionStatus.value = { connected: false, error: e.message }
    llmMessage.value = `Saved but connection test error: ${e.message}`
    llmError.value = true
  } finally {
    testingLLM.value = false
  }
}

async function saveLLM() {
  savingLLM.value = true
  llmMessage.value = ''
  const { provider, api_key, model, temperature } = llmForm.value
  try {
    await api.saveLLMSettings({ provider, api_key, model: model || null, temperature })
    llmMessage.value = 'Settings saved. Testing connection...'
    llmError.value = false
    await loadSettings()
    await testLLMConnection(provider, api_key, model, temperature)
    llmForm.value.api_key = ''
  } catch (e) {
    llmMessage.value = e.message
    llmError.value = true
  } finally {
    savingLLM.value = false
  }
}

async function deleteLLM() {
  try {
    await api.deleteLLMSettings()
    llmMessage.value = 'LLM configuration removed'
    llmError.value = false
    llmConnectionStatus.value = {}
    await loadSettings()
  } catch (e) {
    llmMessage.value = e.message
    llmError.value = true
  }
}

async function loadSettings() {
  try {
    const llmRes = await api.getLLMSettings()
    llmSettings.value = llmRes.data
  } catch (e) {
    console.error(e)
  }
}

onMounted(async () => {
  try {
    const [brokersRes, typesRes] = await Promise.all([
      api.getBrokers(),
      api.getExchangeTypes(),
    ])
    availableBrokers.value = brokersRes.data
    exchangeTypes.value = typesRes.data || []
    if (availableBrokers.value.length > 0) {
      costBroker.value = defaultBrokerId(availableBrokers.value)
      await onBrokerChange()
    }
  } catch (e) {
    console.error(e)
  }
  await Promise.all([loadSettings(), loadNotifKeys(), loadStorageInfo(), loadAboutInfo()])
})
</script>
