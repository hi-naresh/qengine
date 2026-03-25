<template>
  <div>
    <h1 class="text-xl font-semibold mb-6">Brokers</h1>

    <!-- Filter tabs -->
    <div class="flex gap-2 mb-5">
      <button @click="activeTab = 'all'"
        class="btn-sm" :class="activeTab === 'all' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400 hover:text-surface-200'">
        All
      </button>
      <button @click="activeTab = 'active'"
        class="btn-sm" :class="activeTab === 'active' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400 hover:text-surface-200'">
        Active
      </button>
    </div>

    <div v-if="loading" class="text-surface-500 text-sm">Loading...</div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
      <div v-for="broker in filteredBrokers" :key="broker.id"
        class="card transition-colors"
        :class="broker.active ? 'border-brand-600/30' : 'border-surface-700 opacity-70'">

        <!-- Header -->
        <div class="flex items-start justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full" :class="broker.active ? 'bg-green-400' : 'bg-surface-600'"></span>
            <h3 class="text-sm font-semibold text-surface-100">{{ broker.name }}</h3>
          </div>
          <span class="badge-blue text-[10px]">{{ broker.type }}</span>
        </div>

        <!-- Info grid -->
        <div class="grid grid-cols-3 gap-2 text-xs mb-4">
          <div>
            <span class="text-surface-500">Fee</span>
            <div class="text-surface-300 capitalize">{{ broker.fee_model }}</div>
          </div>
          <div>
            <span class="text-surface-500">Leverage</span>
            <div class="text-surface-300">{{ broker.default_leverage }}x</div>
          </div>
          <div>
            <span class="text-surface-500">Currency</span>
            <div class="text-surface-300">{{ broker.settlement_currency }}</div>
          </div>
        </div>

        <!-- Asset classes -->
        <div class="flex flex-wrap gap-1 mb-4">
          <span v-for="ac in broker.asset_classes" :key="ac"
            class="px-1.5 py-0.5 text-[10px] rounded bg-surface-800 text-surface-400 capitalize">{{ ac }}</span>
        </div>

        <!-- Environment status -->
        <div class="space-y-2 mb-4">
          <div v-for="(env, envKey) in broker.environments" :key="envKey"
            class="flex items-center justify-between p-2 rounded-lg"
            :class="env.configured ? 'bg-green-500/10' : 'bg-surface-800'">
            <div class="flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full" :class="env.configured ? 'bg-green-400' : 'bg-surface-600'"></span>
              <span class="text-xs font-medium" :class="env.configured ? 'text-green-400' : 'text-surface-500'">
                {{ envKey === 'demo' ? (env.label || 'Demo') : 'Live' }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <template v-if="connectionStatuses[env.id]?.testing">
                <svg class="animate-spin h-3 w-3 text-surface-400" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              </template>
              <template v-else-if="connectionStatuses[env.id]?.connected === true">
                <span class="text-[10px] text-green-400">Connected</span>
                <span v-if="connectionStatuses[env.id]?.details?.balance" class="text-[10px] text-surface-400">
                  {{ connectionStatuses[env.id].details.balance }} {{ connectionStatuses[env.id].details.currency }}
                </span>
              </template>
              <template v-else-if="connectionStatuses[env.id]?.connected === false">
                <span class="text-[10px] text-red-400">Failed</span>
              </template>
              <template v-else>
                <span class="text-[10px] text-surface-500">{{ env.configured ? 'Configured' : 'Not connected' }}</span>
              </template>
            </div>
          </div>
        </div>

        <!-- Action button -->
        <button @click="openModal(broker)"
          class="w-full text-xs py-2 rounded-lg font-medium transition-colors"
          :class="broker.active
            ? 'bg-surface-800 text-surface-300 hover:text-surface-100 hover:bg-surface-700'
            : 'bg-brand-600 text-white hover:bg-brand-500'">
          {{ broker.active ? 'Manage' : 'Connect' }}
        </button>
      </div>
    </div>

    <!-- Broker Config Modal -->
    <div v-if="modalBroker" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="closeModal">
      <div class="card w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-5">
          <div>
            <h2 class="text-base font-semibold">{{ modalBroker.name }}</h2>
            <span class="text-xs text-surface-500">{{ modalBroker.type }} &middot; {{ modalBroker.api_type }}</span>
          </div>
          <button @click="closeModal" class="text-surface-500 hover:text-surface-200 text-xl leading-none">&times;</button>
        </div>

        <!-- Environment tabs -->
        <div class="flex gap-1 mb-4 p-1 bg-surface-800 rounded-lg">
          <button @click="modalEnv = 'demo'"
            class="flex-1 text-xs py-1.5 rounded-md font-medium transition-colors"
            :class="modalEnv === 'demo' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            {{ modalBroker.environments.demo.label || 'Demo' }}
          </button>
          <button @click="modalEnv = 'live'"
            class="flex-1 text-xs py-1.5 rounded-md font-medium transition-colors"
            :class="modalEnv === 'live' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            Live
          </button>
        </div>

        <!-- Current environment status -->
        <div v-if="currentEnvConfig?.configured" class="mb-4 p-3 rounded-lg"
          :class="currentEnvStatus?.connected === true ? 'bg-green-500/10' : currentEnvStatus?.connected === false ? 'bg-red-500/10' : 'bg-surface-800'">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full"
                :class="currentEnvStatus?.connected === true ? 'bg-green-400' : currentEnvStatus?.connected === false ? 'bg-red-400' : 'bg-surface-500'"></span>
              <span class="text-sm"
                :class="currentEnvStatus?.connected === true ? 'text-green-400' : currentEnvStatus?.connected === false ? 'text-red-400' : 'text-surface-300'">
                <template v-if="currentEnvStatus?.connected === true">Connected</template>
                <template v-else-if="currentEnvStatus?.connected === false">Connection Failed</template>
                <template v-else>Configured</template>
              </span>
            </div>
            <div class="flex gap-2">
              <button @click="retestEnv" class="text-xs text-surface-400 hover:text-surface-200">Retest</button>
              <button @click="disconnectEnv" class="text-xs text-red-400 hover:text-red-300">Disconnect</button>
            </div>
          </div>
          <div v-if="currentEnvStatus?.connected === true && currentEnvStatus?.details" class="mt-2 text-xs text-surface-400">
            <span v-if="currentEnvStatus.details.balance">
              Balance: {{ currentEnvStatus.details.balance }} {{ currentEnvStatus.details.currency }}
            </span>
            <span v-if="currentEnvStatus.details.account_id" class="ml-3">
              Account: {{ currentEnvStatus.details.account_id }}
              <span v-if="currentEnvStatus.details.account_type" class="text-surface-500">({{ currentEnvStatus.details.account_type }})</span>
            </span>
          </div>
          <div v-if="currentEnvStatus?.connected === false && currentEnvStatus?.error" class="mt-1 text-xs text-red-400/80">
            {{ currentEnvStatus.error }}
          </div>
          <div class="text-xs text-surface-500 mt-1">Key: {{ savedBrokers[currentEnvId]?.api_key_masked || '****' }}</div>
        </div>

        <!-- API credentials form -->
        <div class="space-y-3">
          <h3 class="text-xs text-surface-500 font-medium uppercase tracking-wide">
            {{ currentEnvConfig?.configured ? 'Update Credentials' : 'Connect API' }}
          </h3>

          <div v-if="modalBroker.name === 'Interactive Brokers'" class="p-3 rounded-lg bg-surface-800 text-xs text-surface-400">
            IBKR connects to local TWS/IB Gateway. Ensure it's running on port {{ modalEnv === 'demo' ? '7497' : '7496' }}.
          </div>

          <div>
            <label class="label">{{ modalBroker.name === 'IG Markets' ? 'API Key' : 'API Key / Token' }}</label>
            <input v-model="form.api_key" type="password" class="input" placeholder="Enter API key" />
          </div>
          <div v-if="modalBroker.name === 'IG Markets'">
            <label class="label">Password</label>
            <input v-model="form.api_secret" type="password" class="input" placeholder="IG account password" />
          </div>
          <div>
            <label class="label">{{ modalBroker.name === 'IG Markets' ? 'Username' : 'Account ID' }}</label>
            <input v-model="form.account_id" class="input"
              :placeholder="modalBroker.name === 'IG Markets' ? 'IG username' : 'Account ID'" />
          </div>
          <div v-if="modalBroker.name === 'IG Markets'">
            <label class="label">Account ID <span class="text-surface-500 font-normal">(optional — auto-detects CFD account if empty)</span></label>
            <input v-model="form.ig_account_id" class="input" placeholder="e.g. ABCDE" />
          </div>

          <button @click="saveAndTest" class="btn-primary w-full" :disabled="saving">
            {{ saving ? 'Saving & Testing...' : (currentEnvConfig?.configured ? 'Update & Test' : 'Connect & Test') }}
          </button>
          <p v-if="formMessage" class="text-xs" :class="formError ? 'text-red-400' : 'text-green-400'">{{ formMessage }}</p>
        </div>

        <!-- Supported modes -->
        <div class="mt-5 pt-4 border-t border-surface-700">
          <span class="text-xs text-surface-500">Supported Modes</span>
          <div class="flex gap-1 mt-1">
            <span v-if="currentEnvModes?.backtesting" class="badge-green text-[10px]">Backtesting</span>
            <span v-if="currentEnvModes?.live_trading" class="badge-yellow text-[10px]">Live Trading</span>
            <span v-if="currentEnvModes?.paper_trading" class="badge-gray text-[10px]">Paper Trading</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const loading = ref(true)
const brokers = ref([])
const activeTab = ref('all')
const savedBrokers = ref({})
const connectionStatuses = ref({})

// Modal state
const modalBroker = ref(null)
const modalEnv = ref('demo')
const form = ref({ api_key: '', api_secret: '', account_id: '', ig_account_id: '' })
const saving = ref(false)
const formMessage = ref('')
const formError = ref(false)

const filteredBrokers = computed(() => {
  if (activeTab.value === 'active') return brokers.value.filter(b => b.active)
  return brokers.value
})

const currentEnvId = computed(() => {
  if (!modalBroker.value) return ''
  return modalBroker.value.environments[modalEnv.value]?.id || ''
})

const currentEnvConfig = computed(() => {
  if (!modalBroker.value) return null
  return modalBroker.value.environments[modalEnv.value]
})

const currentEnvModes = computed(() => {
  return currentEnvConfig.value?.modes || {}
})

const currentEnvStatus = computed(() => {
  return connectionStatuses.value[currentEnvId.value] || null
})

function openModal(broker) {
  modalBroker.value = broker
  // Default to demo tab, or live if only live is configured
  if (broker.environments.live.configured && !broker.environments.demo.configured) {
    modalEnv.value = 'live'
  } else {
    modalEnv.value = 'demo'
  }
  form.value = { api_key: '', api_secret: '', account_id: '', ig_account_id: '' }
  formMessage.value = ''
}

function closeModal() {
  modalBroker.value = null
  formMessage.value = ''
}

async function saveAndTest() {
  const envId = currentEnvId.value
  if (!envId) return

  saving.value = true
  formMessage.value = ''
  formError.value = false

  try {
    // Save credentials
    const additionalFields = {}
    if (form.value.ig_account_id) additionalFields.ig_account_id = form.value.ig_account_id

    await api.saveBrokerSettings({
      broker: envId,
      api_key: form.value.api_key,
      api_secret: form.value.api_secret,
      account_id: form.value.account_id,
      additional_fields: Object.keys(additionalFields).length ? additionalFields : undefined,
    })

    formMessage.value = 'Saved. Testing connection...'

    // Test connection
    connectionStatuses.value[envId] = { testing: true }
    const res = await api.testBrokerConnection({
      broker: envId,
      api_key: form.value.api_key,
      api_secret: form.value.api_secret,
      account_id: form.value.account_id,
      additional_fields: Object.keys(additionalFields).length ? additionalFields : undefined,
    })
    connectionStatuses.value[envId] = res.data

    if (res.data.connected) {
      formMessage.value = 'Connected successfully'
      formError.value = false
    } else {
      formMessage.value = `Saved but connection failed: ${res.data.error}`
      formError.value = true
    }

    // Refresh broker list + saved settings
    await refreshData()
    form.value = { api_key: '', api_secret: '', account_id: '', ig_account_id: '' }
  } catch (e) {
    formMessage.value = e.message
    formError.value = true
  } finally {
    saving.value = false
  }
}

async function retestEnv() {
  const envId = currentEnvId.value
  if (!envId) return

  formMessage.value = ''
  connectionStatuses.value[envId] = { testing: true }

  try {
    const res = await api.testBrokerConnection({
      broker: envId,
      api_key: '',
      api_secret: '',
      account_id: '',
    })
    connectionStatuses.value[envId] = res.data
  } catch (e) {
    connectionStatuses.value[envId] = { connected: false, error: e.message }
  }
}

async function disconnectEnv() {
  const envId = currentEnvId.value
  if (!envId) return

  try {
    await api.deleteBrokerSettings(envId)
    delete connectionStatuses.value[envId]
    formMessage.value = 'Disconnected'
    formError.value = false
    await refreshData()
  } catch (e) {
    formMessage.value = e.message
    formError.value = true
  }
}

async function refreshData() {
  try {
    const [groupedRes, settingsRes] = await Promise.all([
      api.getBrokersGrouped(),
      api.getBrokerSettings(),
    ])
    brokers.value = groupedRes.data
    savedBrokers.value = settingsRes.data

    // Update modalBroker if open
    if (modalBroker.value) {
      const updated = brokers.value.find(b => b.id === modalBroker.value.id)
      if (updated) modalBroker.value = updated
    }
  } catch (e) {
    console.error(e)
  }
}

onMounted(async () => {
  try {
    await refreshData()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>
