<template>
  <div>
    <div class="text-center mb-6">
      <h1 class="text-2xl font-bold">Settings</h1>
      <p class="text-sm text-surface-500 mt-1">Engine configuration, broker connectivity, AI providers, and system preferences</p>
    </div>

    <!-- Settings Tabs -->
    <div class="flex gap-2 mb-5 flex-wrap">
      <button v-for="tab in tabs" :key="tab" @click="activeTab = tab"
        class="btn-sm" :class="activeTab === tab ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        {{ tab }}
      </button>
    </div>


    <!-- My Profile -->
    <div v-if="activeTab === 'My Profile'" class="max-w-lg space-y-4">
      <!-- Profile Info -->
      <div class="card">
        <div class="flex items-center gap-4 mb-5">
          <div class="w-14 h-14 rounded-full bg-primary-500/20 text-primary-400 flex items-center justify-center text-xl font-bold flex-shrink-0">
            {{ (profileUser.name || profileUser.username || '?').charAt(0).toUpperCase() }}
          </div>
          <div>
            <div class="text-base font-semibold text-surface-100">{{ profileUser.name || profileUser.username }}</div>
            <div class="text-xs text-surface-500">@{{ profileUser.username }}</div>
            <div class="flex items-center gap-2 mt-1">
              <span class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                :class="profileUser.role === 'admin' ? 'bg-amber-500/10 text-amber-400' : 'bg-brand-500/10 text-brand-400'">
                {{ profileUser.role }}
              </span>
            </div>
          </div>
        </div>

        <h2 class="text-sm font-semibold mb-3 text-surface-300">Edit Profile</h2>
        <div class="space-y-3">
          <div>
            <label class="label">Display Name</label>
            <input v-model="profileForm.name" type="text" class="input" placeholder="Your name" />
          </div>
          <div class="border-t border-surface-700 pt-3">
            <label class="label">Current Password</label>
            <input v-model="profileForm.currentPassword" type="password" class="input" placeholder="Required to change password" />
          </div>
          <div>
            <label class="label">New Password</label>
            <input v-model="profileForm.newPassword" type="password" class="input" placeholder="Leave blank to keep current" />
          </div>
          <div v-if="profileForm.newPassword">
            <label class="label">Confirm New Password</label>
            <input v-model="profileForm.confirmPassword" type="password" class="input" placeholder="Confirm new password" />
          </div>
        </div>
        <div class="flex items-center gap-3 mt-4">
          <button @click="saveProfile" class="btn-primary" :disabled="savingProfile">
            {{ savingProfile ? 'Saving...' : 'Save Changes' }}
          </button>
          <span v-if="profileMsg" class="text-xs" :class="profileErr ? 'text-red-400' : 'text-green-400'">{{ profileMsg }}</span>
        </div>
      </div>

      <!-- Danger Zone -->
      <div class="card border border-red-500/20">
        <h2 class="text-sm font-semibold mb-1 text-red-400">Danger Zone</h2>
        <p class="text-xs text-surface-500 mb-4">These actions are irreversible. Issues and comments are always preserved.</p>

        <div class="space-y-3">
          <!-- Delete My Data -->
          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Delete My Data</div>
              <div class="text-xs text-surface-500">Remove all sessions, trades, orders, settings. Keep account.</div>
            </div>
            <button @click="deleteAccountMode = deleteAccountMode === 'data-only' ? null : 'data-only'"
              class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20">
              {{ deleteAccountMode === 'data-only' ? 'Cancel' : 'Delete Data' }}
            </button>
          </div>

          <!-- Delete Account -->
          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Delete Account + Data</div>
              <div class="text-xs text-surface-500">Permanently delete your account and all associated data.</div>
            </div>
            <button @click="deleteAccountMode = deleteAccountMode === 'with-data' ? null : 'with-data'"
              class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20"
              :disabled="profileUser.role === 'admin'">
              {{ deleteAccountMode === 'with-data' ? 'Cancel' : 'Delete All' }}
            </button>
          </div>

          <!-- Delete Account Only -->
          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Delete Account Only</div>
              <div class="text-xs text-surface-500">Remove your account but keep data (admin can reassign).</div>
            </div>
            <button @click="deleteAccountMode = deleteAccountMode === 'without-data' ? null : 'without-data'"
              class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20"
              :disabled="profileUser.role === 'admin'">
              {{ deleteAccountMode === 'without-data' ? 'Cancel' : 'Delete Account' }}
            </button>
          </div>
        </div>

        <!-- Confirmation panel -->
        <div v-if="deleteAccountMode" class="mt-4 p-4 bg-red-500/5 border border-red-500/20 rounded-lg">
          <p class="text-xs text-red-300 mb-3">
            <template v-if="deleteAccountMode === 'data-only'">
              This will delete all your sessions, trades, orders, broker keys, and settings. Your account and issues will remain.
            </template>
            <template v-else-if="deleteAccountMode === 'with-data'">
              This will permanently delete your account and ALL data (sessions, trades, orders, strategies, settings). Issues are preserved.
            </template>
            <template v-else>
              This will delete your account but keep your data in the system. An admin can reassign it later.
            </template>
            Enter your password to confirm.
          </p>
          <div class="flex items-center gap-2">
            <input v-model="deletePassword" type="password" class="input flex-1" placeholder="Your password" />
            <button v-if="deleteAccountMode === 'data-only'" @click="doDeleteData"
              class="btn-sm bg-amber-600 text-white hover:bg-amber-500 whitespace-nowrap"
              :disabled="deletingData">
              {{ deletingData ? 'Deleting...' : 'Confirm Delete Data' }}
            </button>
            <button v-else @click="doDeleteAccount(deleteAccountMode === 'with-data')"
              class="btn-sm bg-red-600 text-white hover:bg-red-500 whitespace-nowrap"
              :disabled="deletingAccount">
              {{ deletingAccount ? 'Deleting...' : 'Confirm Delete' }}
            </button>
          </div>
          <p v-if="deleteMsg" class="text-xs mt-2" :class="deleteErr ? 'text-red-400' : 'text-green-400'">{{ deleteMsg }}</p>
        </div>
      </div>
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
            <select v-model="llmForm.provider" class="select" :disabled="llmLocked">
              <option value="gemini">Google Gemini</option>
              <option value="anthropic">Anthropic Claude</option>
              <option value="openai">OpenAI GPT</option>
            </select>
          </div>
          <div>
            <div class="flex items-center justify-between">
              <label class="label">API Key</label>
              <button v-if="!llmLocked" @click="showLlmGuide = !showLlmGuide" class="text-[10px] text-brand-400 hover:underline mb-1">
                {{ showLlmGuide ? 'Hide guide' : 'How to get a key?' }}
              </button>
            </div>
            <div v-if="!llmLocked && showLlmGuide && llmGuides[llmForm.provider]" class="mb-2 p-3 bg-surface-800 rounded-lg">
              <ol class="space-y-1.5">
                <li v-for="(step, i) in llmGuides[llmForm.provider].steps" :key="i" class="flex gap-2 text-xs text-surface-400">
                  <span class="text-brand-400/60 shrink-0">{{ i + 1 }}.</span>
                  <span v-html="step"></span>
                </li>
              </ol>
              <p class="text-[11px] text-surface-500 mt-2 italic">{{ llmGuides[llmForm.provider].note }}</p>
            </div>
            <input v-model="llmForm.api_key" type="password" class="input" placeholder="Enter API key" :disabled="llmLocked" />
          </div>
          <div>
            <label class="label">Model (optional)</label>
            <input v-model="llmForm.model" class="input font-mono" :placeholder="defaultModel" :disabled="llmLocked" />
            <div v-if="!llmLocked" class="flex items-center justify-between mt-1.5">
              <p class="text-[10px] text-surface-600">e.g. <code class="bg-surface-800 px-1 rounded">{{ modelOptions[0]?.id || defaultModel }}</code></p>
              <button @click="showModelGuide = !showModelGuide" class="text-[10px] text-brand-400 hover:underline">
                {{ showModelGuide ? 'Hide models' : 'Which model should I use?' }}
              </button>
            </div>
            <div v-if="!llmLocked && showModelGuide" class="mt-2 p-2.5 bg-surface-800 rounded-lg space-y-1.5">
              <div v-for="m in modelOptions" :key="m.id"
                class="flex items-start gap-2 text-[11px] px-2 py-1.5 rounded cursor-pointer transition-colors hover:bg-surface-700"
                :class="(llmForm.model === m.id || (!llmForm.model && m.recommended)) ? 'bg-brand-600/10' : ''"
                @click="llmForm.model = m.id">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <code class="text-brand-400 text-[10px]">{{ m.id }}</code>
                    <span v-if="m.recommended" class="text-[9px] px-1 py-0.5 rounded bg-brand-600/20 text-brand-400 shrink-0">recommended</span>
                  </div>
                  <p class="text-surface-500 mt-0.5">{{ m.desc }}</p>
                </div>
              </div>
              <p class="text-[10px] text-surface-600 pt-1">Click a model to use it, or type any model ID in the field above.</p>
            </div>
          </div>
          <div>
            <label class="label">Temperature</label>
            <input v-model.number="llmForm.temperature" type="number" step="0.1" min="0" max="1" class="input" :disabled="llmLocked" />
            <p class="text-xs text-surface-600 mt-1.5 leading-relaxed">
              Controls randomness in AI responses. <strong class="text-surface-400">0.0</strong> = deterministic (same input gives same output).
              <strong class="text-surface-400">1.0</strong> = maximum creativity.
            </p>
            <p class="text-[11px] text-surface-500 mt-1">
              Recommended: <strong class="text-brand-400">0.2–0.4</strong> for strategy generation (consistent, reliable code).
              Use 0.6+ only if you want more varied/experimental outputs.
            </p>
          </div>
          <div class="flex gap-2">
            <button v-if="llmLocked" @click="llmEditing = true" class="btn-secondary flex-1">Update</button>
            <template v-else>
              <button @click="saveLLM" class="btn-primary flex-1" :disabled="savingLLM">
                {{ savingLLM ? 'Saving & Testing...' : 'Save & Test Connection' }}
              </button>
              <button v-if="llmEditing" @click="llmEditing = false" class="btn-secondary">Cancel</button>
            </template>
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

    <!-- Brokers -->
    <div v-if="activeTab === 'Brokers'">
      <!-- Filter tabs -->
      <div class="flex gap-2 mb-5">
        <button @click="brokerTab = 'all'"
          class="btn-sm" :class="brokerTab === 'all' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400 hover:text-surface-200'">
          All
        </button>
        <button @click="brokerTab = 'active'"
          class="btn-sm" :class="brokerTab === 'active' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400 hover:text-surface-200'">
          Active
        </button>
      </div>

      <div v-if="brokerLoading" class="text-surface-500 text-sm">Loading...</div>
      <div v-else class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <div v-for="broker in filteredBrokerList" :key="broker.id"
          class="card transition-colors"
          :class="broker.active ? 'border-brand-600/30' : 'border-surface-700 opacity-70'">
          <div class="flex items-start justify-between mb-3">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full" :class="broker.active ? 'bg-green-400' : 'bg-surface-600'"></span>
              <h3 class="text-sm font-semibold text-surface-100">{{ broker.name }}</h3>
            </div>
            <span class="badge-blue text-[10px]">{{ broker.type }}</span>
          </div>
          <div class="grid grid-cols-3 gap-2 text-xs mb-4">
            <div><span class="text-surface-500">Fee</span><div class="text-surface-300 capitalize">{{ broker.fee_model }}</div></div>
            <div><span class="text-surface-500">Leverage</span><div class="text-surface-300">{{ broker.default_leverage }}x</div></div>
            <div><span class="text-surface-500">Currency</span><div class="text-surface-300">{{ broker.settlement_currency }}</div></div>
          </div>
          <div class="flex flex-wrap gap-1 mb-4">
            <span v-for="ac in broker.asset_classes" :key="ac"
              class="px-1.5 py-0.5 text-[10px] rounded bg-surface-800 text-surface-400 capitalize">{{ ac }}</span>
          </div>
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
                <template v-if="brokerConnStatuses[env.id]?.testing">
                  <svg class="animate-spin h-3 w-3 text-surface-400" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                </template>
                <template v-else-if="brokerConnStatuses[env.id]?.connected === true">
                  <span class="text-[10px] text-green-400">Connected</span>
                  <span v-if="brokerConnStatuses[env.id]?.details?.balance" class="text-[10px] text-surface-400">
                    {{ brokerConnStatuses[env.id].details.balance }} {{ brokerConnStatuses[env.id].details.currency }}
                  </span>
                </template>
                <template v-else-if="brokerConnStatuses[env.id]?.connected === false">
                  <span class="text-[10px] text-red-400">Failed</span>
                </template>
                <template v-else>
                  <span class="text-[10px] text-surface-500">{{ env.configured ? 'Configured' : 'Not connected' }}</span>
                </template>
              </div>
            </div>
          </div>
          <button @click="openBrokerModal(broker)"
            class="w-full text-xs py-2 rounded-lg font-medium transition-colors"
            :class="broker.active ? 'bg-surface-800 text-surface-300 hover:text-surface-100 hover:bg-surface-700' : 'bg-brand-600 text-white hover:bg-brand-500'">
            {{ broker.active ? 'Manage' : 'Connect' }}
          </button>
        </div>
      </div>

      <!-- Export / Import (collapsible) -->
      <details class="mt-6">
        <summary class="text-xs text-surface-500 cursor-pointer hover:text-surface-300">Export / Import API Keys</summary>
        <div class="mt-3 space-y-4 max-w-lg">
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
      </details>
    </div>

    <!-- Broker Config Modal -->
    <div v-if="brokerModal" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="closeBrokerModal">
      <div class="card w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-5">
          <div>
            <h2 class="text-base font-semibold">{{ brokerModal.name }}</h2>
            <span class="text-xs text-surface-500">{{ brokerModal.type }} &middot; {{ brokerModal.api_type }}</span>
          </div>
          <button @click="closeBrokerModal" class="text-surface-500 hover:text-surface-200 text-xl leading-none">&times;</button>
        </div>

        <!-- Environment tabs -->
        <div class="flex gap-1 mb-4 p-1 bg-surface-800 rounded-lg">
          <button @click="brokerModalEnv = 'demo'"
            class="flex-1 text-xs py-1.5 rounded-md font-medium transition-colors"
            :class="brokerModalEnv === 'demo' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            {{ brokerModal.environments.demo.label || 'Demo' }}
          </button>
          <button @click="brokerModalEnv = 'live'"
            class="flex-1 text-xs py-1.5 rounded-md font-medium transition-colors"
            :class="brokerModalEnv === 'live' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
            Live
          </button>
        </div>

        <!-- Current environment status -->
        <div v-if="currentBrokerEnvConfig?.configured" class="mb-4 p-3 rounded-lg"
          :class="currentBrokerEnvStatus?.connected === true ? 'bg-green-500/10' : currentBrokerEnvStatus?.connected === false ? 'bg-red-500/10' : 'bg-surface-800'">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full"
                :class="currentBrokerEnvStatus?.connected === true ? 'bg-green-400' : currentBrokerEnvStatus?.connected === false ? 'bg-red-400' : 'bg-surface-500'"></span>
              <span class="text-sm"
                :class="currentBrokerEnvStatus?.connected === true ? 'text-green-400' : currentBrokerEnvStatus?.connected === false ? 'text-red-400' : 'text-surface-300'">
                <template v-if="currentBrokerEnvStatus?.connected === true">Connected</template>
                <template v-else-if="currentBrokerEnvStatus?.connected === false">Connection Failed</template>
                <template v-else>Configured</template>
              </span>
            </div>
            <div class="flex gap-2">
              <button @click="brokerRetest" class="text-xs text-surface-400 hover:text-surface-200">Retest</button>
              <button @click="brokerDisconnect" class="text-xs text-red-400 hover:text-red-300">Disconnect</button>
            </div>
          </div>
          <div v-if="currentBrokerEnvStatus?.connected === true && currentBrokerEnvStatus?.details" class="mt-2 text-xs text-surface-400">
            <span v-if="currentBrokerEnvStatus.details.balance">
              Balance: {{ currentBrokerEnvStatus.details.balance }} {{ currentBrokerEnvStatus.details.currency }}
            </span>
            <span v-if="currentBrokerEnvStatus.details.account_id" class="ml-3">
              Account: {{ currentBrokerEnvStatus.details.account_id }}
              <span v-if="currentBrokerEnvStatus.details.account_type" class="text-surface-500">({{ currentBrokerEnvStatus.details.account_type }})</span>
            </span>
          </div>
          <div v-if="currentBrokerEnvStatus?.connected === false && currentBrokerEnvStatus?.error" class="mt-1 text-xs text-red-400/80">
            {{ currentBrokerEnvStatus.error }}
          </div>
          <div class="text-xs text-surface-500 mt-1">Key: {{ savedBrokerConfigs[currentBrokerEnvId]?.api_key_masked || '****' }}</div>
        </div>

        <!-- API credentials form -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-xs text-surface-500 font-medium uppercase tracking-wide">
              {{ currentBrokerEnvConfig?.configured ? 'Update Credentials' : 'Connect API' }}
            </h3>
            <button @click="showBrokerGuide = !showBrokerGuide" class="text-[10px] text-brand-400 hover:underline">
              {{ showBrokerGuide ? 'Hide guide' : 'How to get credentials?' }}
            </button>
          </div>

          <!-- Inline setup guide -->
          <div v-if="showBrokerGuide" class="p-3 rounded-lg bg-brand-600/5 border border-brand-600/10 space-y-3">
            <template v-if="brokerGuideKey">
              <div class="flex gap-1 p-0.5 bg-surface-800 rounded-md">
                <button @click="brokerGuideTab = 'have_account'"
                  class="flex-1 text-[10px] py-1.5 rounded font-medium transition-colors"
                  :class="brokerGuideTab === 'have_account' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
                  I have an account
                </button>
                <button @click="brokerGuideTab = 'need_account'"
                  class="flex-1 text-[10px] py-1.5 rounded font-medium transition-colors"
                  :class="brokerGuideTab === 'need_account' ? 'bg-surface-700 text-surface-100' : 'text-surface-500 hover:text-surface-300'">
                  I need an account
                </button>
              </div>
              <ol v-if="brokerGuideTab === 'have_account'" class="space-y-1.5">
                <li v-for="(step, i) in brokerGuides[brokerGuideKey].login" :key="'l'+i" class="flex gap-2 text-[11px] text-surface-400">
                  <span class="text-brand-400/60 shrink-0">{{ i + 1 }}.</span>
                  <span v-html="step"></span>
                </li>
              </ol>
              <ol v-else class="space-y-1.5">
                <li v-for="(step, i) in brokerGuides[brokerGuideKey].signup" :key="'s'+i" class="flex gap-2 text-[11px] text-surface-400">
                  <span class="text-brand-400/60 shrink-0">{{ i + 1 }}.</span>
                  <span v-html="step"></span>
                </li>
              </ol>
              <p class="text-[10px] text-surface-500 italic">{{ brokerGuides[brokerGuideKey].note }}</p>
            </template>
            <p v-else class="text-xs text-surface-500">Setup guide not available for this broker yet.</p>
          </div>

          <div v-if="brokerModal.name === 'Interactive Brokers'" class="p-3 rounded-lg bg-surface-800 text-xs text-surface-400">
            IBKR connects to local TWS/IB Gateway. Ensure it's running on port {{ brokerModalEnv === 'demo' ? '7497' : '7496' }}.
          </div>

          <div>
            <label class="label">{{ brokerModal.name === 'IG Markets' ? 'API Key' : 'API Key / Token' }}</label>
            <input v-model="brokerForm.api_key" type="password" class="input" placeholder="Enter API key" />
            <p v-if="brokerGuideKey && brokerGuides[brokerGuideKey].fields?.api_key" class="text-[10px] text-surface-600 mt-1">{{ brokerGuides[brokerGuideKey].fields.api_key }}</p>
          </div>
          <div v-if="brokerModal.name === 'IG Markets'">
            <label class="label">Password</label>
            <input v-model="brokerForm.api_secret" type="password" class="input" placeholder="IG account password" />
            <p v-if="brokerGuideKey && brokerGuides[brokerGuideKey].fields?.api_secret" class="text-[10px] text-surface-600 mt-1">{{ brokerGuides[brokerGuideKey].fields.api_secret }}</p>
          </div>
          <div>
            <label class="label">{{ brokerModal.name === 'IG Markets' ? 'Username' : 'Account ID' }}</label>
            <input v-model="brokerForm.account_id" class="input"
              :placeholder="brokerModal.name === 'IG Markets' ? 'IG username' : 'Account ID'" />
            <p v-if="brokerGuideKey && brokerGuides[brokerGuideKey].fields?.account_id" class="text-[10px] text-surface-600 mt-1">{{ brokerGuides[brokerGuideKey].fields.account_id }}</p>
          </div>
          <div v-if="brokerModal.name === 'IG Markets'">
            <label class="label">Account ID <span class="text-surface-500 font-normal">(optional — auto-detects CFD account if empty)</span></label>
            <input v-model="brokerForm.ig_account_id" class="input" placeholder="e.g. ABCDE" />
          </div>

          <button @click="brokerSaveAndTest" class="btn-primary w-full" :disabled="brokerSaving">
            {{ brokerSaving ? 'Saving & Testing...' : (currentBrokerEnvConfig?.configured ? 'Update & Test' : 'Connect & Test') }}
          </button>
          <p v-if="brokerFormMsg" class="text-xs" :class="brokerFormErr ? 'text-red-400' : 'text-green-400'">{{ brokerFormMsg }}</p>
        </div>

        <!-- Supported modes -->
        <div class="mt-5 pt-4 border-t border-surface-700">
          <span class="text-xs text-surface-500">Supported Modes</span>
          <div class="flex gap-1 mt-1">
            <span v-if="currentBrokerEnvModes?.backtesting" class="badge-green text-[10px]">Backtesting</span>
            <span v-if="currentBrokerEnvModes?.live_trading" class="badge-yellow text-[10px]">Live Trading</span>
            <span v-if="currentBrokerEnvModes?.paper_trading" class="badge-gray text-[10px]">Paper Trading</span>
          </div>
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

    <!-- Usage & Quotas (non-admin only) -->
    <div v-if="activeTab === 'Usage & Quotas'" class="max-w-lg space-y-4">
      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Your Usage Limits</h2>
        <div v-if="!userQuotas.length" class="text-xs text-surface-500">No quotas configured.</div>
        <div v-else class="space-y-3">
          <div v-for="q in userQuotas" :key="q.feature" class="bg-surface-800/60 rounded-lg px-4 py-3">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-surface-200 capitalize">{{ q.feature.replace('_', ' ') }}</span>
              <span class="text-xs text-surface-400">{{ q.used_runs }}/{{ q.max_runs }} <span class="text-surface-600">per {{ q.period }}</span></span>
            </div>
            <div class="h-1.5 bg-surface-700 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all"
                :class="quotaUsagePercent(q) > 80 ? 'bg-red-400' : quotaUsagePercent(q) > 50 ? 'bg-amber-400' : 'bg-brand-400'"
                :style="{ width: quotaUsagePercent(q) + '%' }"></div>
            </div>
            <div class="flex items-center justify-between mt-2">
              <span class="text-[10px] text-surface-600">
                {{ q.max_runs - q.used_runs > 0 ? (q.max_runs - q.used_runs) + ' remaining' : 'Limit reached' }}
              </span>
              <button v-if="!hasPendingQuotaRequest(q.feature)"
                @click="openQuotaRequestModal(q)"
                class="text-[10px] text-brand-400 hover:text-brand-300 transition-colors">
                Request more
              </button>
              <span v-else class="text-[10px] text-amber-400">Request pending</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Requests -->
      <div v-if="userQuotaRequests.length" class="card">
        <h2 class="text-sm font-semibold mb-3 text-surface-300">Your Requests</h2>
        <div class="space-y-2">
          <div v-for="r in userQuotaRequests" :key="r.id" class="flex items-center gap-3 bg-surface-800/60 rounded-lg px-3 py-2">
            <span class="text-xs font-medium text-surface-300 capitalize w-24">{{ r.feature.replace('_', ' ') }}</span>
            <span class="text-xs text-surface-400 flex-1">{{ r.requested_runs }} runs</span>
            <span class="px-1.5 py-0.5 rounded text-[10px] font-medium"
              :class="r.status === 'approved' ? 'bg-emerald-500/10 text-emerald-400' : r.status === 'denied' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'">
              {{ r.status }}
            </span>
          </div>
        </div>
      </div>

      <!-- Request Modal -->
      <div v-if="showQuotaRequestModal" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="showQuotaRequestModal = false">
        <div class="card w-full max-w-sm mx-4">
          <h2 class="text-base font-semibold mb-4">Request More Quota</h2>
          <div class="space-y-3">
            <div>
              <label class="label">Feature</label>
              <input :value="quotaRequestForm.feature.replace('_', ' ')" disabled class="input capitalize opacity-60" />
            </div>
            <div>
              <label class="label">Current Limit</label>
              <input :value="quotaRequestForm.currentLimit + ' per ' + quotaRequestForm.period" disabled class="input opacity-60" />
            </div>
            <div>
              <label class="label">Requested Runs</label>
              <input v-model.number="quotaRequestForm.requestedRuns" type="number" min="1" class="input" placeholder="e.g. 20" />
            </div>
            <div>
              <label class="label">Reason (optional)</label>
              <textarea v-model="quotaRequestForm.reason" class="input" rows="2" placeholder="Why do you need more?"></textarea>
            </div>
          </div>
          <div class="flex items-center gap-3 mt-4">
            <button @click="submitQuotaRequest" class="btn-primary btn-sm" :disabled="submittingQuotaRequest">
              {{ submittingQuotaRequest ? 'Submitting...' : 'Submit Request' }}
            </button>
            <button @click="showQuotaRequestModal = false" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
            <span v-if="quotaRequestMsg" class="text-xs" :class="quotaRequestErr ? 'text-red-400' : 'text-green-400'">{{ quotaRequestMsg }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- About -->
    <div v-if="activeTab === 'About'" class="max-w-2xl">
      <!-- About Sub-tabs -->
      <div class="flex gap-1.5 mb-5 flex-wrap">
        <button v-for="st in aboutSubTabs" :key="st" @click="aboutSubTab = st"
          class="px-3 py-1.5 rounded-lg text-xs transition-colors"
          :class="aboutSubTab === st ? 'bg-brand-600/20 text-brand-400 font-medium' : 'bg-surface-800/60 text-surface-500 hover:text-surface-300'">
          {{ st }}
        </button>
      </div>

      <!-- Sub-tab: Overview -->
      <div v-if="aboutSubTab === 'Overview'" class="space-y-4">
        <div class="card">
          <h2 class="text-sm font-semibold mb-3 text-surface-300">About QEngine</h2>
          <p class="text-xs text-surface-400 leading-relaxed mb-3">
            QEngine is a multi-asset quant engine for analysis and production pipelines for trading systems with intelligence. Built from scratch using quantitative techniques and methods designed to create AI-driven trading systems &mdash; not just LLM-tuned, but engineered from first principles. Supports Forex, Commodities, Indices, and CFDs with realistic cost modelling, true hedging, and native broker connectivity.
          </p>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="tag in ['Quant Engine','Multi-Asset','Forex','Commodities','Indices','CFDs','Production Pipelines','AI Intelligence','Live Trading']" :key="tag"
              class="text-[10px] px-2 py-0.5 bg-brand-600/15 text-brand-400 rounded-full">{{ tag }}</span>
          </div>
        </div>

        <div class="card">
          <h2 class="text-sm font-semibold mb-4 text-surface-300">System Information</h2>
          <div v-if="aboutInfo" class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <div class="p-2.5 bg-surface-800 rounded-lg" v-for="item in aboutItems" :key="item.label">
              <div class="text-[10px] text-surface-500 uppercase tracking-wide">{{ item.label }}</div>
              <div class="text-xs text-surface-200 font-mono mt-0.5">{{ item.value }}</div>
            </div>
          </div>
          <div v-else class="text-sm text-surface-500 py-4 text-center">Loading system info...</div>
        </div>

        <div v-if="aboutInfo && aboutInfo.update_info && aboutInfo.update_info.is_update_info_available" class="card">
          <div class="flex justify-between items-center">
            <h2 class="text-sm font-semibold text-surface-300">Updates</h2>
            <span class="text-xs font-mono px-2 py-0.5 rounded"
              :class="aboutInfo.update_info.latest_version !== aboutInfo.system_info.qengine_version ? 'bg-amber-500/10 text-amber-400' : 'bg-green-500/10 text-green-400'">
              {{ aboutInfo.update_info.latest_version }}
            </span>
          </div>
        </div>

        <div class="card">
          <h2 class="text-sm font-semibold mb-2 text-surface-300">License</h2>
          <p class="text-xs text-surface-400 leading-relaxed">
            MIT License. Original Jesse framework copyright acknowledged. The <code class="text-[10px] bg-surface-800 px-1 rounded">jesse_rust</code> indicator library is used as-is from the upstream project.
          </p>
        </div>
      </div>

      <!-- Sub-tab: Origin -->
      <div v-if="aboutSubTab === 'Origin'" class="space-y-4">
        <div class="card">
          <h2 class="text-sm font-semibold mb-3 text-surface-300">Forked from Jesse</h2>
          <p class="text-xs text-surface-400 leading-relaxed mb-4">
            <a href="https://github.com/jesse-ai/jesse" target="_blank" class="text-brand-400 hover:underline">Jesse</a> (by jesse-ai) provided the original foundation: an event-driven backtesting engine, a strategy base class with order management, 170+ technical indicators via a Rust backend, crypto exchange support, and a basic Flask API with Nuxt 3 dashboard.
          </p>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <h3 class="text-xs font-semibold text-green-400 mb-2">Kept from Jesse</h3>
              <div class="space-y-1.5">
                <div v-for="item in jesseKept" :key="item" class="flex items-start gap-2 text-[11px] text-surface-400">
                  <span class="text-green-500/60 mt-0.5 shrink-0">+</span>
                  <span>{{ item }}</span>
                </div>
              </div>
            </div>
            <div>
              <h3 class="text-xs font-semibold text-red-400 mb-2">Removed / Replaced</h3>
              <div class="space-y-1.5">
                <div v-for="item in jesseRemoved" :key="item" class="flex items-start gap-2 text-[11px] text-surface-400">
                  <span class="text-red-500/60 mt-0.5 shrink-0">-</span>
                  <span>{{ item }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        
      </div>

      <!-- Sub-tab: What's New -->
      <div v-if="aboutSubTab === 'What\'s New'" class="space-y-4">
        <div v-for="feature in newFeatures" :key="feature.title" class="card">
          <div class="flex items-center gap-2 mb-2">
            <span class="w-2 h-2 rounded-full" :class="feature.color"></span>
            <h2 class="text-sm font-semibold text-surface-200">{{ feature.title }}</h2>
          </div>
          <div class="space-y-1.5 text-[11px] text-surface-400 leading-relaxed">
            <p v-for="(line, i) in feature.lines" :key="i" v-html="line"></p>
          </div>
        </div>
      </div>

      <!-- Sub-tab: Changelog (from docs/CHANGELOG.md) -->
      <div v-if="aboutSubTab === 'Changelog'" class="space-y-4">
        <div v-for="(ver, vi) in changelogVersions" :key="ver.version" class="card">
          <div class="flex items-center gap-2 mb-3">
            <span class="text-sm font-bold text-surface-200">v{{ ver.version }}</span>
            <span class="text-[10px] text-surface-500">{{ ver.date }}</span>
            <span v-if="vi === 0" class="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-400 rounded-full">Latest</span>
          </div>

          <!-- Expandable sections -->
          <div class="space-y-3">
            <div v-for="section in ver.sections" :key="section.title">
              <button @click="toggleSection(ver.version, section.title)"
                class="flex items-center gap-2 w-full text-left group">
                <svg class="w-3 h-3 text-surface-500 transition-transform" :class="isSectionOpen(ver.version, section.title) ? 'rotate-90' : ''" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd" />
                </svg>
                <span class="text-xs font-medium text-surface-300 group-hover:text-surface-100">{{ section.title }}</span>
                <span class="text-[9px] text-surface-600">{{ section.items.length }} items</span>
              </button>
              <div v-if="isSectionOpen(ver.version, section.title)" class="pl-5 mt-1.5 space-y-1 border-l border-surface-700/50">
                <p v-for="(item, ii) in section.items" :key="ii" class="text-[11px] text-surface-400 leading-relaxed" v-html="formatItem(item)"></p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sub-tab: Engine Changes -->
      <div v-if="aboutSubTab === 'Engine Changes'" class="space-y-4">
        <div class="card">
          <h2 class="text-sm font-semibold mb-2 text-surface-300">Modified from Jesse</h2>
          <p class="text-xs text-surface-400 leading-relaxed mb-4">Core files significantly modified or added to support CFD trading, real cost models, and live broker connectivity.</p>

          <!-- Filter buttons -->
          <div class="flex gap-1.5 mb-4">
            <button v-for="f in ['All', 'NEW', 'MAJOR', 'MODIFIED']" :key="f" @click="modFilter = f"
              class="px-2 py-1 rounded text-[10px] transition-colors"
              :class="modFilter === f ? 'bg-surface-700 text-surface-200' : 'text-surface-500 hover:text-surface-300'">
              {{ f }} <span class="text-surface-600">({{ f === 'All' ? coreModifications.length : coreModifications.filter(m => modFilterMap[f] === m.level).length }})</span>
            </button>
          </div>

          <div class="space-y-2">
            <div v-for="mod in filteredModifications" :key="mod.file" class="p-2.5 bg-surface-800 rounded-lg">
              <div class="flex items-center justify-between mb-1">
                <code class="text-[10px] text-brand-400">{{ mod.file }}</code>
                <span class="text-[9px] px-1.5 py-0.5 rounded-full" :class="mod.level === 'major' ? 'bg-amber-500/10 text-amber-400' : mod.level === 'new' ? 'bg-green-500/10 text-green-400' : 'bg-blue-500/10 text-blue-400'">{{ mod.level === 'new' ? 'NEW' : mod.level === 'major' ? 'MAJOR' : 'MODIFIED' }}</span>
              </div>
              <p class="text-[10px] text-surface-500 leading-relaxed">{{ mod.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Maintenance -->
    <!-- Preferences -->
    <div v-if="activeTab === 'Preferences'" class="max-w-lg space-y-4">
      <div class="card">
        <h2 class="text-sm font-semibold mb-4 text-surface-300">Metric Guides &amp; Hints</h2>
        <p class="text-xs text-surface-500 mb-4">Control whether explanatory tooltips and guides appear alongside backtest and Monte Carlo results. Useful for learning what each metric means. Experts who already know the stats can turn these off for a cleaner UI.</p>
        <div class="space-y-3">
          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Hover Tooltips</div>
              <div class="text-xs text-surface-500">Show metric descriptions when hovering over stat labels</div>
            </div>
            <button @click="showTooltips = !showTooltips"
              class="relative w-10 h-5 rounded-full transition-colors"
              :class="showTooltips ? 'bg-brand-500' : 'bg-surface-600'">
              <div class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform"
                :class="showTooltips ? 'left-5' : 'left-0.5'"></div>
            </button>
          </div>
          <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
            <div>
              <div class="text-sm text-surface-200">Section Guides</div>
              <div class="text-xs text-surface-500">Show collapsible "How to read these stats" blocks in result sections</div>
            </div>
            <button @click="showSectionGuides = !showSectionGuides"
              class="relative w-10 h-5 rounded-full transition-colors"
              :class="showSectionGuides ? 'bg-brand-500' : 'bg-surface-600'">
              <div class="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform"
                :class="showSectionGuides ? 'left-5' : 'left-0.5'"></div>
            </button>
          </div>
        </div>
      </div>
    </div>

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
import { useRouter, useRoute } from 'vue-router'
import { api, defaultBrokerId, isAdmin, getCurrentUser, setAuth, logout } from '../api'
import { changelog as parsedChangelog } from '../changelog-parser'
import { useGuides } from '../useGuides'

const { showTooltips, showSectionGuides } = useGuides()
const router = useRouter()

const route = useRoute()
const activeTab = ref(route.query.tab || 'My Profile')
const allTabs = ['My Profile', 'Preferences', 'LLM', 'Brokers', 'Notifications', 'Cost & Randomness', 'Usage & Quotas', 'Maintenance', 'About']
const adminOnlyTabs = ['Maintenance']

// Profile
const profileUser = ref(getCurrentUser() || {})
const profileForm = ref({ name: '', currentPassword: '', newPassword: '', confirmPassword: '' })
const savingProfile = ref(false)
const profileMsg = ref('')
const profileErr = ref(false)
const deletePassword = ref('')
const deletingData = ref(false)
const deletingAccount = ref(false)
const deleteMsg = ref('')
const deleteErr = ref(false)
const deleteAccountMode = ref(null) // null, 'data-only', 'with-data', 'without-data'

function initProfileForm() {
  const u = getCurrentUser() || {}
  profileForm.value = { name: u.name || '', currentPassword: '', newPassword: '', confirmPassword: '' }
  profileUser.value = u
}

async function saveProfile() {
  profileMsg.value = ''; profileErr.value = false
  const data = {}
  if (profileForm.value.name !== (profileUser.value.name || '')) {
    data.name = profileForm.value.name
  }
  if (profileForm.value.newPassword) {
    if (profileForm.value.newPassword !== profileForm.value.confirmPassword) {
      profileMsg.value = 'New passwords do not match'; profileErr.value = true; return
    }
    if (!profileForm.value.currentPassword) {
      profileMsg.value = 'Current password is required to change password'; profileErr.value = true; return
    }
    data.password = profileForm.value.newPassword
    data.current_password = profileForm.value.currentPassword
  }
  if (!Object.keys(data).length) { profileMsg.value = 'No changes to save'; return }
  savingProfile.value = true
  try {
    const res = await api.updateProfile(data)
    if (res.auth_token) setAuth(res.auth_token, res.user)
    profileUser.value = res.user || getCurrentUser()
    profileForm.value.currentPassword = ''; profileForm.value.newPassword = ''; profileForm.value.confirmPassword = ''
    profileMsg.value = 'Profile updated'
  } catch (e) { profileMsg.value = e.message; profileErr.value = true }
  finally { savingProfile.value = false }
}

async function doDeleteData() {
  deleteMsg.value = ''; deleteErr.value = false
  if (!deletePassword.value) { deleteMsg.value = 'Password required'; deleteErr.value = true; return }
  deletingData.value = true
  try {
    const res = await api.deleteMyData(deletePassword.value)
    deleteMsg.value = res.message || 'Data deleted'
    deletePassword.value = ''; deleteAccountMode.value = null
  } catch (e) { deleteMsg.value = e.message; deleteErr.value = true }
  finally { deletingData.value = false }
}

async function doDeleteAccount(withData) {
  deleteMsg.value = ''; deleteErr.value = false
  if (!deletePassword.value) { deleteMsg.value = 'Password required'; deleteErr.value = true; return }
  deletingAccount.value = true
  try {
    await api.deleteAccount(deletePassword.value, withData)
    logout()
    router.push('/login')
  } catch (e) { deleteMsg.value = e.message; deleteErr.value = true }
  finally { deletingAccount.value = false }
}
const userOnlyTabs = ['Usage & Quotas']
const tabs = computed(() => {
  let filtered = allTabs
  if (isAdmin()) filtered = filtered.filter(t => !userOnlyTabs.includes(t))
  else filtered = filtered.filter(t => !adminOnlyTabs.includes(t))
  return filtered
})

// LLM
const llmSettings = ref({})
const savingLLM = ref(false)
const testingLLM = ref(false)
const llmMessage = ref('')
const llmError = ref(false)
const llmForm = ref({ provider: 'gemini', api_key: '', model: '', temperature: 0.3 })
const llmConnectionStatus = ref({})
const llmEditing = ref(false)

const llmLocked = computed(() => llmSettings.value.configured && !llmEditing.value)

const defaultModel = computed(() => {
  const models = { gemini: 'gemini-2.5-flash', anthropic: 'claude-sonnet-4-6', openai: 'gpt-4o' }
  return models[llmForm.value.provider] || ''
})

const modelOptions = computed(() => {
  const opts = {
    gemini: [
      { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', desc: 'Fast & free-tier friendly. Best for most use cases.', recommended: true },
      { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', desc: 'Highest quality. Best for difficult strategy generation. Higher cost.' },
    ],
    anthropic: [
      { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6', desc: 'Balanced speed and quality. Best for most use cases.', recommended: true },
      { id: 'claude-haiku-4-5', name: 'Claude Haiku 4.5', desc: 'Fastest and cheapest. Good for quick iterations.' },
      { id: 'claude-opus-4-6', name: 'Claude Opus 4.6', desc: 'Most capable. Best for complex strategy logic. Highest cost.' },
    ],
    openai: [
      { id: 'gpt-4o', name: 'GPT-4o', desc: 'Best overall quality and speed balance.', recommended: true },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini', desc: 'Faster and cheaper. Good for simple tasks.' },
      { id: 'o3-mini', name: 'o3-mini', desc: 'Reasoning model. Best for complex logic but slower.' },
    ],
  }
  return opts[llmForm.value.provider] || []
})

// Broker
const availableBrokers = ref([])
const selectedBrokerName = computed(() => {
  const b = availableBrokers.value.find(x => x.id === costBroker.value)
  return b ? b.name : costBroker.value
})

// Broker Management (inline from Brokers page)
const brokerList = ref([])
const brokerLoading = ref(true)
const brokerTab = ref('all')
const savedBrokerConfigs = ref({})
const brokerConnStatuses = ref({})
const brokerModal = ref(null)
const brokerModalEnv = ref('demo')
const brokerForm = ref({ api_key: '', api_secret: '', account_id: '', ig_account_id: '' })
const brokerSaving = ref(false)
const brokerFormMsg = ref('')
const brokerFormErr = ref(false)
const showBrokerGuide = ref(false)
const brokerGuideTab = ref('have_account')

const brokerGuides = {
  oanda: {
    signup: [
      'Go to <a href="https://hub.oanda.com/apply/demo/" target="_blank" class="text-brand-400 hover:underline">OANDA Demo Signup</a> for a free practice account, or <a href="https://www.oanda.com/apply/" target="_blank" class="text-brand-400 hover:underline">OANDA Live</a> for real trading',
      'Complete the registration form and verify your email',
      'For live accounts: complete identity verification (KYC) and fund your account',
      'Once registered, switch to <strong>"I have an account"</strong> to get your API token',
    ],
    login: [
      'Go to <a href="https://hub.oanda.com/tpa/personal_token" target="_blank" class="text-brand-400 hover:underline">OANDA Personal Token</a> page (log in if prompted)',
      'Click <strong>"Generate"</strong> to create a new API token',
      'Copy the token — paste it as <strong>API Key</strong> below',
      'Your <strong>Account ID</strong> is shown on the same page (format: xxx-xxx-xxxxxxx-xxx)',
    ],
    note: 'Demo accounts are free and don\'t expire.',
    fields: { api_key: 'API Token from Personal Token page', account_id: 'e.g. 001-004-1234567-001' },
  },
  ig: {
    signup: [
      'Go to <a href="https://www.ig.com/uk/demo-account" target="_blank" class="text-brand-400 hover:underline">IG Demo Account</a> for practice, or <a href="https://www.ig.com/en/create-account" target="_blank" class="text-brand-400 hover:underline">IG Live</a> for real trading',
      'Complete the application form and verify your email',
      'For live: complete identity verification and fund your account',
      'Once registered, switch to <strong>"I have an account"</strong> to get your API key',
    ],
    login: [
      'Go to <a href="https://www.ig.com/uk/myig/settings/api-keys" target="_blank" class="text-brand-400 hover:underline">IG API Keys</a> page (log in if prompted)',
      'For demo: switch to your <strong>Demo account</strong> at the top of the page',
      'Click <strong>"Create Web API Demo Credentials"</strong> (demo) or <strong>"Create API key"</strong> (live)',
      'Copy the <strong>API key</strong> — make sure its status shows <strong class="text-green-400">Enabled</strong>',
      'Your <strong>Username</strong> = your IG login username',
      'Your <strong>Password</strong> = your IG login password',
    ],
    note: 'IG requires API Key + Username + Password. Account ID is optional (auto-detects CFD). Ensure API key status is Enabled.',
    fields: { api_key: 'API Key from IG API Keys page', api_secret: 'Your IG login password', account_id: 'Your IG login username' },
  },
  ibkr: {
    signup: [
      'Go to <a href="https://www.interactivebrokers.com/en/trading/individual.php" target="_blank" class="text-brand-400 hover:underline">Interactive Brokers</a> and open an account',
      'Complete the application and fund your account',
      'Download and install <strong>Trader Workstation (TWS)</strong> or <strong>IB Gateway</strong>',
      'Once installed, follow the <strong>"I have an account"</strong> steps to enable API access',
    ],
    login: [
      'Open <strong>TWS</strong> or <strong>IB Gateway</strong> and log in',
      'Go to <strong>Edit > Global Configuration > API > Settings</strong>',
      'Check <strong>"Enable ActiveX and Socket Clients"</strong>',
      'Set Socket port: <strong>7497</strong> (paper) or <strong>7496</strong> (live)',
      'Uncheck "Read-Only API" if you want to place orders',
      'Your <strong>Account ID</strong> is in the top-right of TWS (e.g. U1234567) — paste it below',
    ],
    note: 'IBKR uses a local socket connection (no API key). TWS or IB Gateway must be running.',
    fields: { account_id: 'Account ID from TWS (e.g. U1234567)' },
  },
}

const brokerGuideKey = computed(() => {
  if (!brokerModal.value) return null
  const name = brokerModal.value.name.toLowerCase()
  if (name.includes('oanda')) return 'oanda'
  if (name.includes('ig')) return 'ig'
  if (name.includes('interactive')) return 'ibkr'
  return null
})

const filteredBrokerList = computed(() => {
  if (brokerTab.value === 'active') return brokerList.value.filter(b => b.active)
  return brokerList.value
})

const currentBrokerEnvId = computed(() => brokerModal.value?.environments[brokerModalEnv.value]?.id || '')
const currentBrokerEnvConfig = computed(() => brokerModal.value?.environments[brokerModalEnv.value] || null)
const currentBrokerEnvModes = computed(() => currentBrokerEnvConfig.value?.modes || {})
const currentBrokerEnvStatus = computed(() => brokerConnStatuses.value[currentBrokerEnvId.value] || null)

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

const showLlmGuide = ref(false)
const showModelGuide = ref(false)

const llmGuides = {
  gemini: {
    name: 'Google Gemini',
    url: 'https://aistudio.google.com/apikey',
    signupUrl: 'https://accounts.google.com/signup',
    steps: [
      'Go to <a href="https://aistudio.google.com/apikey" target="_blank" class="text-brand-400 hover:underline">Google AI Studio</a> and sign in with your Google account',
      'Click <strong>"Create API Key"</strong>',
      'Select a Google Cloud project (or create one — it\'s free)',
      'Copy the generated API key and paste it below',
    ],
    note: 'Gemini offers a generous free tier. No credit card required for basic usage.',
    models: 'Gemini 2.5 Flash Lite (recommended, free tier), Gemini 2.5 Flash (smarter), Gemini 2.5 Pro (best quality)',
  },
  anthropic: {
    name: 'Anthropic Claude',
    url: 'https://console.anthropic.com/settings/keys',
    signupUrl: 'https://console.anthropic.com/',
    steps: [
      'Go to <a href="https://console.anthropic.com/" target="_blank" class="text-brand-400 hover:underline">console.anthropic.com</a> and create an account',
      'Add a payment method (Settings > Billing)',
      'Go to <a href="https://console.anthropic.com/settings/keys" target="_blank" class="text-brand-400 hover:underline">API Keys</a>',
      'Click <strong>"Create Key"</strong>, name it, and copy the key',
    ],
    note: 'Requires a paid account. Claude is excellent for complex strategy generation.',
    models: 'claude-sonnet-4-6 (default, balanced), claude-haiku-4-5 (fast & cheap)',
  },
  openai: {
    name: 'OpenAI GPT',
    url: 'https://platform.openai.com/api-keys',
    signupUrl: 'https://platform.openai.com/signup',
    steps: [
      'Go to <a href="https://platform.openai.com/signup" target="_blank" class="text-brand-400 hover:underline">platform.openai.com</a> and create an account',
      'Add a payment method (Settings > Billing)',
      'Go to <a href="https://platform.openai.com/api-keys" target="_blank" class="text-brand-400 hover:underline">API Keys</a>',
      'Click <strong>"Create new secret key"</strong>, name it, and copy it immediately (shown only once)',
    ],
    note: 'Requires a paid account. GPT-4o provides strong general-purpose performance.',
    models: 'gpt-4o (default, best), gpt-4o-mini (faster & cheaper)',
  },
}


// About
const aboutInfo = ref(null)
const allAboutSubTabs = ['Overview', 'Origin', "What's New", 'Changelog', 'Engine Changes']
const aboutSubTabs = computed(() => isAdmin() ? allAboutSubTabs : ['Overview', "What's New"])
const aboutSubTab = ref('Overview')
const modFilter = ref('All')
const modFilterMap = { NEW: 'new', MAJOR: 'major', MODIFIED: 'mod' }
const filteredModifications = computed(() => {
  if (modFilter.value === 'All') return coreModifications
  return coreModifications.filter(m => m.level === modFilterMap[modFilter.value])
})

const jesseKept = [
  'Core event-driven backtesting engine loop',
  'Strategy base class lifecycle (should_long, go_long, update_position)',
  '170+ technical indicators via jesse_rust',
  'Crypto exchange support (Binance, Bybit, etc.)',
  'MIT License with original copyright',
]
const jesseRemoved = [
  'Nuxt 3 dashboard (16MB, 438 files) \u2192 Vue 3 + Vite',
  'Flask API server \u2192 FastAPI',
  'SQLite support \u2192 PostgreSQL only',
  'External live-trading plugin \u2192 native drivers',
  'Crypto-only exchange configs and fee models',
]
const renames = [
  { from: 'from jesse.*', to: 'from qengine.*' },
  { from: 'jesse_db', to: 'qengine_db' },
  { from: 'jesse run', to: 'qengine run' },
  { from: 'jesse_submitted', to: 'engine_submitted' },
  { from: '/jesse-trade/*', to: '/marketplace/*' },
  { from: 'jesse_trade.py', to: 'upstream_api.py' },
]

const newFeatures = [
  { title: 'CFD Hedging Engine', color: 'bg-blue-400', lines: [
    'MT4/MT5-style independent ticket system \u2014 multiple long and short sub-positions within a single position, each with its own entry price and P&L tracking.',
    '<code class="text-[10px] bg-surface-800 px-1 rounded">CFDTicket</code> class, <code class="text-[10px] bg-surface-800 px-1 rounded">open_ticket()</code>, <code class="text-[10px] bg-surface-800 px-1 rounded">close_ticket()</code>, <code class="text-[10px] bg-surface-800 px-1 rounded">close_all_tickets()</code> with per-ticket P&L and gross exposure margin calculation.',
    'Unified exchange type <code class="text-[10px] bg-surface-800 px-1 rounded">cfd</code> replacing crypto-only futures/spot modes.',
  ]},
  { title: 'Realistic Cost Model', color: 'bg-green-400', lines: [
    'Spread shifts fill price (buy at ask, sell at bid) instead of flat fee deduction \u2014 how real brokers work.',
    'Configurable per-broker: spread (pips + randomness), slippage (pips + randomness), commission per lot, overnight swap charges at 5pm NY rollover. Weekend gap handling for stop/limit orders.',
    'Margin call simulation with stop-out at configurable margin level.',
  ]},
  { title: 'Native Broker Connectors', color: 'bg-purple-400', lines: [
    '<strong>OANDA</strong> \u2014 REST API with per-trade TP/SL, trade ID tracking, hedging mode, trade sync every 3s, order enrichment from transaction history.',
    '<strong>IG Markets</strong> \u2014 Lightstreamer real-time streaming (no rate limit cost), CFD account auto-detection, deal confirmation flow, exponential backoff rate limiting.',
    '<strong>Interactive Brokers</strong> \u2014 TWS socket API via ib_insync.',
    'All built on a unified <code class="text-[10px] bg-surface-800 px-1 rounded">ForexLiveDriver</code> base class. Multi-tier sync (orders, trades, positions, account) with independent intervals and backoff.',
  ]},
  { title: 'Live Trading Infrastructure', color: 'bg-amber-400', lines: [
    'Native live/paper trading mode (no external plugin) with graceful shutdown, session reports, and real-time Redis state publishing.',
    'Position, order, ticket, account, and strategy state broadcast to dashboard every tick. Session reports with win rate, drawdown, and full trade history.',
  ]},
  { title: 'Strategy Framework Extensions', color: 'bg-cyan-400', lines: [
    '<strong>Hedge mode</strong> \u2014 simultaneous long+short. <strong>CFD callbacks</strong> \u2014 <code class="text-[10px] bg-surface-800 px-1 rounded">on_ticket_opened</code>, <code class="text-[10px] bg-surface-800 px-1 rounded">on_ticket_closed</code>. <strong>Enhanced close</strong> \u2014 <code class="text-[10px] bg-surface-800 px-1 rounded">on_close_position(order, closed_trade)</code> now receives the trade object.',
    'Forex properties: spread, pip_size, session, market_is_open, swap_long/short, contract_size, minutes_to_close.',
    'Helpers: pips_to_price(), price_to_pips(), lot_size_for_risk(), liquidate(), shared_vars, chart_label.',
  ]},
  { title: 'Backtest Engine Upgrades', color: 'bg-rose-400', lines: [
    'Floating P&L curve and margin usage tracking alongside equity curve. Market hours awareness \u2014 skips execution when forex markets are closed.',
    'Overnight swap charges at 5pm NY rollover. Margin call handling with stop-out. Weekend gap slippage. Per-session stats for hedge strategies.',
    'Session persistence in PostgreSQL with strategy source code, execution logs, charts, and full HTML report generation.',
  ]},
  { title: 'Dashboard (Completely New)', color: 'bg-pink-400', lines: [
    'Entire UI rebuilt with Vue 3 + Vite + Tailwind CSS. Mobile-first responsive with glassmorphism bottom navigation, adaptive grids, and touch-optimised controls.',
    '13 views: Dashboard, Brokers, Tools, Strategies, Backtest, Optimization, Monte Carlo, Live Trade, Import Data, LLM Studio, Issues, Settings, Login.',
    'Multi-workspace tabs for backtests. Multi-session tabs for live trading with expandable ticket tables, filterable logs, and 10 account metric cards.',
    'Lightweight Charts with 8 timeframes, progressive rendering, full-screen mode. Real-time WebSocket with GZIP compression and auto-reconnection.',
  ]},
  { title: 'AI Strategy Engine', color: 'bg-violet-400', lines: [
    'LLM-powered strategy generation, refinement, and validation. Supports Anthropic Claude, OpenAI GPT, and Google Gemini.',
    'In-dashboard LLM Studio for interactive development. AI-assisted strategy fixing in the backtest view with inline editor.',
  ]},
  { title: 'Optimization & Monte Carlo', color: 'bg-teal-400', lines: [
    '<strong>Optimization</strong> \u2014 Optuna + Ray distributed computing. 7 objective functions (Sharpe, Calmar, Sortino, Omega, Serenity, Smart Sharpe, Smart Sortino). Training/testing split.',
    '<strong>Monte Carlo</strong> \u2014 Trade shuffling and candle perturbation. Gaussian noise and Moving Block Bootstrap pipelines. Confidence intervals and p-values.',
  ]},
  { title: 'Infrastructure', color: 'bg-orange-400', lines: [
    'FastAPI backend (22 controllers), Redis pub/sub, WebSocket manager with heartbeat and pattern subscriptions.',
    'PostgreSQL-only with comprehensive migrations. Pyright LSP for in-browser code intelligence. Docker multi-stage builds. Railway deployment.',
    'Instrument registry with pip sizes, contract sizes, margin rates, swap rates per symbol. Market hours per asset class with DST handling.',
  ]},
]

// Changelog from docs/CHANGELOG.md (parsed at build time)
const changelogVersions = parsedChangelog
const openSections = ref({})
function toggleSection(version, title) {
  const key = `${version}::${title}`
  openSections.value[key] = !openSections.value[key]
}
function isSectionOpen(version, title) {
  return !!openSections.value[`${version}::${title}`]
}
function formatItem(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-surface-300">$1</strong>')
    .replace(/`(.+?)`/g, '<code class="text-[10px] bg-surface-800 px-1 rounded">$1</code>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" class="text-brand-400 hover:underline">$1</a>')
}
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
  ]
  if (si.live_plugin_version) {
    items.splice(1, 0, { label: 'Live Plugin Version', value: si.live_plugin_version })
  }
  return items
})

const coreModifications = [
  { file: 'models/CFDExchange.py', level: 'new', desc: 'Entire new exchange model: spread-based fees, overnight swaps, margin calculation, leverage, cost settings, order lifecycle management.' },
  { file: 'models/Position.py', level: 'major', desc: 'CFDTicket class added. Ticket management (open/close/sync). PnL, margin, is_open, is_close, to_dict all modified for multi-ticket CFD mode. Gross exposure tracking.' },
  { file: 'strategies/Strategy.py', level: 'major', desc: '20+ new properties (forex/CFD), 7 new methods (pip helpers, ticket management, liquidate), hedge mode, modified callbacks (on_close_position signature), price caching, execution deadlock fix.' },
  { file: 'models/Order.py', level: 'mod', desc: 'New fields: ticket_id (CFD ticket link), vars (exchange metadata JSON), fee (per-order fee tracking).' },
  { file: 'services/order_service.py', level: 'major', desc: 'Spread & slippage application on fill price for CFD. Fee calculation at execution. CFD trade tracking skip for ticket mode.' },
  { file: 'services/position_service.py', level: 'major', desc: 'New _handle_cfd_order() for independent ticket management. CFD branch in order execution routing. Per-ticket trade recording.' },
  { file: 'services/closed_trade_service.py', level: 'mod', desc: 'New record_ticket_close() for per-ticket ClosedTrade creation with metadata.' },
  { file: 'services/exchange_service.py', level: 'mod', desc: 'CFD exchange creation branch. _apply_backtest_cost_settings() for per-broker spread/slippage config.' },
  { file: 'services/candle_service.py', level: 'mod', desc: 'Import optimization: eliminated per-batch DB queries and O(n^2) gap fill. Eager tuple materialization. Timestamp range validation.' },
  { file: 'modes/backtest_mode.py', level: 'major', desc: 'Floating PnL & margin tracking, market hours integration, overnight swaps, margin call stop-out, gap handling, session stats, HTML reports.' },
  { file: 'modes/live_mode.py', level: 'new', desc: 'Native live trading orchestration (1,352 lines): multi-tier broker sync, Redis state publishing, graceful shutdown, session reports.' },
  { file: 'live_drivers/base.py', level: 'new', desc: 'ForexLiveDriver abstract base class: unified interface for all broker drivers with abstract + optional methods.' },
  { file: 'live_drivers/OANDA/', level: 'new', desc: 'OANDA driver: market/limit/stop orders, per-trade TP/SL, trade sync, order enrichment, symbol conversion.' },
  { file: 'live_drivers/IG/', level: 'new', desc: 'IG Markets driver: Lightstreamer streaming, CFD account detection, deal confirmation, rate limit backoff.' },
  { file: 'core/instruments.py', level: 'new', desc: 'Instrument registry: pip sizes, contract sizes, margin rates, swap rates, asset class inference per symbol.' },
  { file: 'core/market_hours.py', level: 'new', desc: 'Market hours: forex/commodity/index schedules, session detection, rollover times, DST handling.' },
  { file: 'services/llm_engine.py', level: 'new', desc: 'AI strategy generation/refinement: Anthropic, OpenAI, Gemini providers with auto-config and prompt engineering.' },
  { file: 'services/ws_manager.py', level: 'new', desc: 'WebSocket connection manager: Redis pub/sub, heartbeat, pattern subscriptions, multi-client handling.' },
  { file: 'services/safety_sizing.py', level: 'new', desc: 'Risk calculator: worst-case loss, max safe size, affordability check, dynamic levels, exposure ratio.' },
]

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

// --- Broker Management Methods ---

function openBrokerModal(broker) {
  brokerModal.value = broker
  if (broker.environments.live.configured && !broker.environments.demo.configured) {
    brokerModalEnv.value = 'live'
  } else {
    brokerModalEnv.value = 'demo'
  }
  brokerForm.value = { api_key: '', api_secret: '', account_id: '', ig_account_id: '' }
  brokerFormMsg.value = ''
}

function closeBrokerModal() {
  brokerModal.value = null
  brokerFormMsg.value = ''
}

async function brokerSaveAndTest() {
  const envId = currentBrokerEnvId.value
  if (!envId) return
  brokerSaving.value = true
  brokerFormMsg.value = ''
  brokerFormErr.value = false
  try {
    const additionalFields = {}
    if (brokerForm.value.ig_account_id) additionalFields.ig_account_id = brokerForm.value.ig_account_id
    await api.saveBrokerSettings({
      broker: envId,
      api_key: brokerForm.value.api_key,
      api_secret: brokerForm.value.api_secret,
      account_id: brokerForm.value.account_id,
      additional_fields: Object.keys(additionalFields).length ? additionalFields : undefined,
    })
    brokerFormMsg.value = 'Saved. Testing connection...'
    brokerConnStatuses.value[envId] = { testing: true }
    const res = await api.testBrokerConnection({
      broker: envId,
      api_key: brokerForm.value.api_key,
      api_secret: brokerForm.value.api_secret,
      account_id: brokerForm.value.account_id,
      additional_fields: Object.keys(additionalFields).length ? additionalFields : undefined,
    })
    brokerConnStatuses.value[envId] = res.data
    if (res.data.connected) {
      brokerFormMsg.value = 'Connected successfully'
      brokerFormErr.value = false
    } else {
      brokerFormMsg.value = `Saved but connection failed: ${res.data.error}`
      brokerFormErr.value = true
    }
    await refreshBrokerData()
    brokerForm.value = { api_key: '', api_secret: '', account_id: '', ig_account_id: '' }
  } catch (e) {
    brokerFormMsg.value = e.message
    brokerFormErr.value = true
  } finally {
    brokerSaving.value = false
  }
}

async function brokerRetest() {
  const envId = currentBrokerEnvId.value
  if (!envId) return
  brokerFormMsg.value = ''
  brokerConnStatuses.value[envId] = { testing: true }
  try {
    const res = await api.testBrokerConnection({ broker: envId, api_key: '', api_secret: '', account_id: '' })
    brokerConnStatuses.value[envId] = res.data
  } catch (e) {
    brokerConnStatuses.value[envId] = { connected: false, error: e.message }
  }
}

async function brokerDisconnect() {
  const envId = currentBrokerEnvId.value
  if (!envId) return
  try {
    await api.deleteBrokerSettings(envId)
    delete brokerConnStatuses.value[envId]
    brokerFormMsg.value = 'Disconnected'
    brokerFormErr.value = false
    await refreshBrokerData()
  } catch (e) {
    brokerFormMsg.value = e.message
    brokerFormErr.value = true
  }
}

async function refreshBrokerData() {
  try {
    const [groupedRes, settingsRes] = await Promise.all([
      api.getBrokersGrouped(),
      api.getBrokerSettings(),
    ])
    brokerList.value = groupedRes.data
    savedBrokerConfigs.value = settingsRes.data
    if (brokerModal.value) {
      const updated = brokerList.value.find(b => b.id === brokerModal.value.id)
      if (updated) brokerModal.value = updated
    }
    // Auto-test configured broker connections
    const configuredIds = Object.keys(settingsRes.data || {}).filter(id => settingsRes.data[id]?.configured)
    const tests = configuredIds.map(async (envId) => {
      if (brokerConnStatuses.value[envId]?.connected !== undefined) return
      brokerConnStatuses.value[envId] = { testing: true }
      try {
        const res = await api.testBrokerConnection({ broker: envId, api_key: '', api_secret: '', account_id: '' })
        brokerConnStatuses.value[envId] = res.data
      } catch (e) {
        brokerConnStatuses.value[envId] = { connected: false, error: e.message }
      }
    })
    await Promise.all(tests)
  } catch (e) { console.error(e) }
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
    llmEditing.value = false
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
    llmEditing.value = false
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
    // Auto-test LLM connection if configured
    if (llmRes.data.configured && !llmConnectionStatus.value.connected) {
      try {
        const res = await api.testLLMConnection({
          provider: llmRes.data.provider,
          api_key: '',
          model: llmRes.data.model || null,
          temperature: llmRes.data.temperature,
        })
        llmConnectionStatus.value = res.data
      } catch (e) {
        llmConnectionStatus.value = { connected: false, error: e.message }
      }
    }
  } catch (e) {
    console.error(e)
  }
}

// Usage & Quotas
const userQuotas = ref([])
const userQuotaRequests = ref([])
const showQuotaRequestModal = ref(false)
const submittingQuotaRequest = ref(false)
const quotaRequestMsg = ref('')
const quotaRequestErr = ref(false)
const quotaRequestForm = ref({ feature: '', currentLimit: 0, period: '', requestedRuns: 10, reason: '' })

function quotaUsagePercent(q) {
  if (!q.max_runs || q.max_runs <= 0) return 0
  return Math.min(100, Math.round((q.used_runs / q.max_runs) * 100))
}

function hasPendingQuotaRequest(feature) {
  return userQuotaRequests.value.some(r => r.feature === feature && r.status === 'pending')
}

function openQuotaRequestModal(q) {
  quotaRequestForm.value = {
    feature: q.feature,
    currentLimit: q.max_runs,
    period: q.period,
    requestedRuns: q.max_runs * 2,
    reason: '',
  }
  quotaRequestMsg.value = ''
  showQuotaRequestModal.value = true
}

async function loadUserQuotas() {
  try {
    const me = await api.getMe()
    userQuotas.value = me.quotas || []
  } catch (e) { console.error(e) }
  try {
    const res = await api.getQuotaRequests()
    userQuotaRequests.value = res.requests || []
  } catch (e) { console.error(e) }
}

async function submitQuotaRequest() {
  quotaRequestMsg.value = ''; quotaRequestErr.value = false
  if (!quotaRequestForm.value.requestedRuns || quotaRequestForm.value.requestedRuns < 1) {
    quotaRequestMsg.value = 'Enter a valid number'; quotaRequestErr.value = true; return
  }
  submittingQuotaRequest.value = true
  try {
    await api.submitQuotaRequest({
      feature: quotaRequestForm.value.feature,
      requested_runs: quotaRequestForm.value.requestedRuns,
      reason: quotaRequestForm.value.reason,
    })
    showQuotaRequestModal.value = false
    await loadUserQuotas()
  } catch (e) {
    quotaRequestMsg.value = e.message || 'Failed'; quotaRequestErr.value = true
  } finally {
    submittingQuotaRequest.value = false
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
  initProfileForm()
  const loads = [loadSettings(), loadNotifKeys(), loadAboutInfo(), refreshBrokerData()]
  if (isAdmin()) loads.push(loadStorageInfo())
  else loads.push(loadUserQuotas())
  await Promise.all(loads)
  brokerLoading.value = false
})
</script>
