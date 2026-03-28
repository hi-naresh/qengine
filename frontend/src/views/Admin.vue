<template>
  <div class="max-w-5xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-surface-100">User Management</h1>
        <p class="text-sm text-surface-500 mt-1">
          {{ activeUsers.length }} active user{{ activeUsers.length !== 1 ? 's' : '' }}
          <span v-if="deletedUsers.length" class="text-surface-600"> · {{ deletedUsers.length }} deleted</span>
        </p>
      </div>
      <button @click="showCreateForm = !showCreateForm"
        class="btn-primary btn-sm">
        {{ showCreateForm ? 'Cancel' : '+ Create User' }}
      </button>
    </div>

    <!-- Create User Form -->
    <div v-if="showCreateForm" class="card">
      <h2 class="text-sm font-semibold mb-4 text-surface-300">Create New User</h2>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label class="label">Username</label>
          <input v-model="createForm.username" class="input" placeholder="username" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="createForm.password" type="password" class="input" placeholder="min 6 chars" />
        </div>
        <div>
          <label class="label">Role</label>
          <select v-model="createForm.role" class="select">
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </div>
      </div>
      <div class="flex items-center gap-3 mt-4">
        <button @click="createUser" class="btn-primary btn-sm" :disabled="creatingUser">
          {{ creatingUser ? 'Creating...' : 'Create User' }}
        </button>
        <span v-if="createMsg" class="text-xs" :class="createErr ? 'text-red-400' : 'text-green-400'">{{ createMsg }}</span>
      </div>
    </div>

    <!-- Tabs: Active / History / Quota Requests -->
    <div class="flex gap-1.5">
      <button @click="viewTab = 'active'"
        class="px-4 py-2 rounded-lg text-sm transition-colors"
        :class="viewTab === 'active' ? 'bg-brand-600/20 text-brand-400 font-medium' : 'bg-surface-800/60 text-surface-500 hover:text-surface-300'">
        Active <span class="text-[10px] ml-1 opacity-60">{{ activeUsers.length }}</span>
      </button>
      <button @click="viewTab = 'history'"
        class="px-4 py-2 rounded-lg text-sm transition-colors"
        :class="viewTab === 'history' ? 'bg-brand-600/20 text-brand-400 font-medium' : 'bg-surface-800/60 text-surface-500 hover:text-surface-300'">
        History <span class="text-[10px] ml-1 opacity-60">{{ deletedUsers.length }}</span>
      </button>
      <button @click="viewTab = 'requests'; loadQuotaRequests()"
        class="px-4 py-2 rounded-lg text-sm transition-colors"
        :class="viewTab === 'requests' ? 'bg-brand-600/20 text-brand-400 font-medium' : 'bg-surface-800/60 text-surface-500 hover:text-surface-300'">
        Quota Requests <span v-if="quotaRequests.length" class="text-[10px] ml-1 text-amber-400 font-medium">{{ quotaRequests.length }}</span>
      </button>
    </div>

    <!-- Quota Requests Panel -->
    <div v-if="viewTab === 'requests'" class="space-y-3">
      <div v-if="quotaRequests.length === 0" class="card p-8 text-center text-surface-500 text-sm">
        No pending quota requests.
      </div>
      <div v-for="qr in quotaRequests" :key="qr.id" class="card">
        <div class="flex items-center gap-4">
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium text-surface-200">{{ qr.username || 'Unknown' }}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-400">{{ qr.feature }}</span>
            </div>
            <div class="text-xs text-surface-400 mt-1">
              Requesting <span class="text-surface-200 font-medium">{{ qr.requested_runs }} runs</span>
              <span v-if="qr.reason"> &mdash; "{{ qr.reason }}"</span>
            </div>
            <div class="text-[10px] text-surface-600 mt-0.5">{{ formatDate(qr.created_at) }}</div>
          </div>
          <div class="flex items-center gap-2">
            <input type="number" v-model.number="approvedRuns[qr.id]" :placeholder="qr.requested_runs" min="1"
              class="input w-20 text-xs py-1 px-2 text-center" title="Approved runs limit" />
            <button @click="reviewRequest(qr.id, 'approved')"
              class="px-3 py-1.5 text-xs rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 transition-colors"
              :disabled="reviewingId === qr.id">
              Approve
            </button>
            <button @click="reviewRequest(qr.id, 'denied')"
              class="px-3 py-1.5 text-xs rounded bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors"
              :disabled="reviewingId === qr.id">
              Deny
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="viewTab !== 'requests' && loading" class="card p-8 text-center text-surface-400">Loading users...</div>

    <!-- Error -->
    <div v-else-if="error && viewTab !== 'requests'" class="card p-8 text-center text-red-400">{{ error }}</div>

    <!-- Users List -->
    <div v-else-if="viewTab !== 'requests'" class="space-y-3">
      <div v-if="displayedUsers.length === 0" class="card p-8 text-center text-surface-500 text-sm">
        {{ viewTab === 'active' ? 'No active users.' : 'No deleted users in history.' }}
      </div>
      <div v-for="user in displayedUsers" :key="user.id" class="card overflow-hidden" :class="user.deleted_at ? 'opacity-60' : ''">
        <!-- User Summary Row -->
        <div class="flex items-center gap-4 cursor-pointer" @click="toggleExpand(user.id)">
          <!-- Avatar -->
          <div class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
            :class="user.deleted_at ? 'bg-surface-700 text-surface-500' : user.role === 'admin' ? 'bg-amber-500/20 text-amber-400' : 'bg-brand-500/20 text-brand-400'">
            {{ (user.name || user.username || '?').charAt(0).toUpperCase() }}
          </div>

          <!-- Name + Role -->
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium truncate" :class="user.deleted_at ? 'text-surface-500 line-through' : 'text-surface-200'">{{ user.name || user.username }}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                :class="user.deleted_at ? 'bg-red-500/10 text-red-400' : user.role === 'admin' ? 'bg-amber-500/10 text-amber-400' : 'bg-brand-500/10 text-brand-400'">
                {{ user.deleted_at ? 'deleted' : user.role }}
              </span>
              <span v-if="!user.deleted_at" class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="user.is_active ? 'bg-emerald-400' : 'bg-red-400'"></span>
            </div>
            <div class="text-[10px] text-surface-500">
              @{{ user.username }} · {{ formatDate(user.created_at) }}
              <span v-if="user.deleted_at" class="text-red-400"> · deleted {{ formatDate(user.deleted_at) }}</span>
            </div>
          </div>

          <!-- Quick Stats -->
          <div class="hidden sm:flex items-center gap-3 text-[10px] text-surface-500">
            <span v-if="user.stats" class="flex items-center gap-1" :title="'Sessions: ' + totalSessions(user.stats)">
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75z" /></svg>
              {{ totalSessions(user.stats) }}
            </span>
            <span v-if="user.stats" class="flex items-center gap-1" :title="user.stats.strategies + ' strategies'">
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" /></svg>
              {{ user.stats.strategies }}
            </span>
            <span v-if="user.stats && user.stats.llm_configured" class="text-green-400" title="LLM Connected">
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12" /></svg>
            </span>
            <span v-if="user.stats && user.stats.broker_keys > 0" class="text-green-400" :title="user.stats.broker_names.join(', ')">
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3" /></svg>
            </span>
          </div>

          <!-- Actions -->
          <div v-if="!user.deleted_at" class="flex items-center gap-2 flex-shrink-0" @click.stop>
            <button v-if="user.role !== 'admin'"
              @click="impersonateUser(user)"
              class="px-2.5 py-1 text-xs rounded bg-surface-700 hover:bg-surface-600 text-surface-300 hover:text-surface-100 transition-colors"
              :disabled="impersonatingId === user.id">
              {{ impersonatingId === user.id ? '...' : 'View as' }}
            </button>
            <button @click="toggleActive(user)"
              class="px-2.5 py-1 text-xs rounded transition-colors"
              :class="user.is_active ? 'bg-red-500/10 hover:bg-red-500/20 text-red-400' : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400'"
              :disabled="togglingId === user.id">
              {{ user.is_active ? 'Disable' : 'Enable' }}
            </button>
          </div>

          <!-- Expand arrow -->
          <svg class="w-4 h-4 text-surface-600 transition-transform flex-shrink-0" :class="expandedUser === user.id ? 'rotate-90' : ''"
            fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </div>

        <!-- Expanded Section -->
        <div v-if="expandedUser === user.id" class="mt-4 border-t border-white/[0.06] pt-4">
          <!-- Deleted user: show archived stats only -->
          <div v-if="user.deleted_at" class="space-y-4">
            <div class="flex items-center gap-2 mb-3">
              <svg class="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 13.875l2.25-2.25M12 13.875l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z"/></svg>
              <span class="text-xs text-surface-400">Archived usage at time of deletion</span>
            </div>
            <div v-if="user.stats" class="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div v-for="s in statCards(user.stats)" :key="s.label" class="p-3 bg-surface-800/60 rounded-lg">
                <div class="text-[10px] text-surface-500 uppercase tracking-wide">{{ s.label }}</div>
                <div class="text-lg font-bold text-surface-400 mt-0.5">{{ s.value }}</div>
              </div>
            </div>
            <div v-if="user.deletion_stats" class="space-y-2">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-500">Connections at Deletion</h4>
              <div class="flex flex-wrap gap-2">
                <div class="flex items-center gap-2 px-3 py-2 bg-surface-800/60 rounded-lg text-xs">
                  <span class="text-surface-400">LLM</span>
                  <span v-if="user.deletion_stats.llm_configured" class="text-surface-300">{{ user.deletion_stats.llm_provider }}</span>
                  <span v-else class="text-surface-600">Not configured</span>
                </div>
                <div class="flex items-center gap-2 px-3 py-2 bg-surface-800/60 rounded-lg text-xs">
                  <span class="text-surface-400">Brokers</span>
                  <span v-if="user.deletion_stats.broker_names?.length" class="text-surface-300">{{ user.deletion_stats.broker_names.join(', ') }}</span>
                  <span v-else class="text-surface-600">None</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Active user: full tabs -->
          <template v-else>
          <!-- Sub-tabs -->
          <div class="flex gap-1.5 mb-4">
            <button v-for="t in userTabs" :key="t" @click="userTab = t"
              class="px-3 py-1.5 rounded-lg text-xs transition-colors"
              :class="userTab === t ? 'bg-brand-600/20 text-brand-400 font-medium' : 'bg-surface-800/60 text-surface-500 hover:text-surface-300'">
              {{ t }}
            </button>
          </div>

          <!-- Overview Tab -->
          <div v-if="userTab === 'Overview'" class="space-y-4">
            <div v-if="user.stats" class="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div v-for="s in statCards(user.stats)" :key="s.label" class="p-3 bg-surface-800/60 rounded-lg">
                <div class="text-[10px] text-surface-500 uppercase tracking-wide">{{ s.label }}</div>
                <div class="text-lg font-bold text-surface-200 mt-0.5">{{ s.value }}</div>
              </div>
            </div>
            <!-- Connections -->
            <div class="space-y-2">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-500">Connections</h4>
              <div class="flex flex-wrap gap-2">
                <div class="flex items-center gap-2 px-3 py-2 bg-surface-800/60 rounded-lg text-xs">
                  <span class="w-2 h-2 rounded-full" :class="user.stats?.llm_configured ? 'bg-green-400' : 'bg-surface-600'"></span>
                  <span class="text-surface-400">LLM</span>
                  <span v-if="user.stats?.llm_configured" class="text-surface-200">{{ user.stats.llm_provider }}</span>
                  <span v-else class="text-surface-600">Not configured</span>
                </div>
                <div class="flex items-center gap-2 px-3 py-2 bg-surface-800/60 rounded-lg text-xs">
                  <span class="w-2 h-2 rounded-full" :class="user.stats?.broker_keys > 0 ? 'bg-green-400' : 'bg-surface-600'"></span>
                  <span class="text-surface-400">Brokers</span>
                  <span v-if="user.stats?.broker_names?.length" class="text-surface-200">{{ user.stats.broker_names.join(', ') }}</span>
                  <span v-else class="text-surface-600">None</span>
                </div>
                <div class="flex items-center gap-2 px-3 py-2 bg-surface-800/60 rounded-lg text-xs">
                  <span class="w-2 h-2 rounded-full" :class="user.stats?.notification_keys > 0 ? 'bg-green-400' : 'bg-surface-600'"></span>
                  <span class="text-surface-400">Notifications</span>
                  <span class="text-surface-200">{{ user.stats?.notification_keys || 0 }} channel{{ user.stats?.notification_keys !== 1 ? 's' : '' }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Features & Quotas Tab -->
          <div v-if="userTab === 'Features & Quotas'" class="space-y-5">
            <!-- Features (non-admin only) -->
            <div v-if="user.role !== 'admin'" class="space-y-3">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-500">Allowed Features</h4>
              <div class="flex flex-wrap gap-2">
                <button v-for="f in allFeatures" :key="f"
                  @click.stop="toggleFeature(user, f)"
                  class="px-2.5 py-1 text-xs rounded-lg transition-colors"
                  :class="(user.allowed_features || []).includes(f)
                    ? 'bg-brand-500/20 text-brand-400 hover:bg-brand-500/30'
                    : 'bg-surface-800 text-surface-500 hover:bg-surface-700'">
                  {{ featureLabels[f] || f }}
                </button>
              </div>
            </div>
            <div v-else class="text-xs text-surface-500 italic">Admin has access to all features.</div>

            <!-- Quotas -->
            <div class="space-y-3">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-500">Quotas</h4>
              <div v-if="!user.quotas || user.quotas.length === 0" class="text-xs text-surface-600">No quotas configured.</div>
              <div v-else class="grid gap-2">
                <div v-for="q in user.quotas" :key="q.feature"
                  class="flex items-center gap-4 bg-surface-800/60 rounded-lg px-3 py-2">
                  <span class="text-surface-300 text-xs font-medium w-32">{{ q.feature }}</span>
                  <div class="flex-1">
                    <div class="flex items-center gap-2">
                      <div class="flex-1 h-1.5 bg-surface-700 rounded-full overflow-hidden">
                        <div class="h-full rounded-full transition-all"
                          :class="quotaPercent(q) > 80 ? 'bg-red-400' : quotaPercent(q) > 50 ? 'bg-amber-400' : 'bg-brand-400'"
                          :style="{ width: quotaPercent(q) + '%' }"></div>
                      </div>
                      <span class="text-xs text-surface-400 w-16 text-right">{{ q.used_runs }}/{{ q.max_runs }}</span>
                    </div>
                  </div>
                  <span class="text-[10px] text-surface-600 w-16">{{ q.period }}</span>
                  <input type="number" :value="q.max_runs" min="0"
                    class="input w-20 text-xs py-1 px-2 text-center"
                    @change="updateQuota(user.id, q.feature, $event.target.value)"
                    @click.stop />
                </div>
              </div>
            </div>
          </div>

          <!-- Role & Security Tab -->
          <div v-if="userTab === 'Role & Security'" class="space-y-4">
            <!-- Role -->
            <div class="flex items-center gap-3">
              <label class="text-xs text-surface-400 w-16">Role</label>
              <select :value="user.role" @change="changeRole(user, $event.target.value)" class="select w-32 text-xs py-1">
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <!-- Reset Password -->
            <div class="space-y-2">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-surface-500">Reset Password</h4>
              <div class="flex items-center gap-3">
                <input v-model="resetPasswordForm[user.id]" type="password" class="input flex-1 text-xs" placeholder="New password (min 6 chars)" @click.stop />
                <button @click.stop="resetPassword(user)" class="btn-sm bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                  :disabled="resettingPassword === user.id">
                  {{ resettingPassword === user.id ? '...' : 'Reset' }}
                </button>
              </div>
              <p v-if="resetMsg[user.id]" class="text-xs" :class="resetErr[user.id] ? 'text-red-400' : 'text-green-400'">{{ resetMsg[user.id] }}</p>
            </div>
          </div>

          <!-- Danger Zone Tab -->
          <div v-if="userTab === 'Danger Zone'" class="space-y-3">
            <div v-if="user.role === 'admin'" class="text-xs text-surface-500 italic">Admin account cannot be deleted.</div>
            <template v-else>
              <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
                <div>
                  <div class="text-sm text-surface-200">Delete User + Data</div>
                  <div class="text-xs text-surface-500">Permanently delete account, data, strategies. Issues preserved.</div>
                </div>
                <button @click.stop="deleteUser(user, true)"
                  class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20"
                  :disabled="deletingUser === user.id">
                  {{ deletingUser === user.id ? '...' : 'Delete All' }}
                </button>
              </div>
              <div class="flex items-center justify-between p-3 bg-surface-800 rounded-lg">
                <div>
                  <div class="text-sm text-surface-200">Delete Account Only</div>
                  <div class="text-xs text-surface-500">Remove account but keep data (admin can reassign).</div>
                </div>
                <button @click.stop="deleteUser(user, false)"
                  class="btn-sm bg-red-500/10 text-red-400 hover:bg-red-500/20"
                  :disabled="deletingUser === user.id">
                  {{ deletingUser === user.id ? '...' : 'Delete Account' }}
                </button>
              </div>
            </template>
            <p v-if="deleteMsg" class="text-xs" :class="deleteErr ? 'text-red-400' : 'text-green-400'">{{ deleteMsg }}</p>
          </div>
          </template>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, setAuth, getCurrentUser } from '../api'

const router = useRouter()
const users = ref([])
const loading = ref(true)
const error = ref('')
const viewTab = ref('active')
const expandedUser = ref(null)
const userTab = ref('Overview')
const userTabs = ['Overview', 'Features & Quotas', 'Role & Security', 'Danger Zone']
const impersonatingId = ref(null)
const togglingId = ref(null)

// Create user
const showCreateForm = ref(false)
const createForm = ref({ username: '', password: '', role: 'user' })
const creatingUser = ref(false)
const createMsg = ref('')
const createErr = ref(false)

// Reset password
const resetPasswordForm = reactive({})
const resettingPassword = ref(null)
const resetMsg = reactive({})
const resetErr = reactive({})

// Delete
const deletingUser = ref(null)
const deleteMsg = ref('')
const deleteErr = ref(false)

// Quota Requests
const quotaRequests = ref([])
const approvedRuns = reactive({})
const reviewingId = ref(null)

const allFeatures = [
  'dashboard', 'brokers', 'strategies', 'backtest', 'optimization',
  'monte_carlo', 'live', 'import_data', 'tools', 'llm_studio',
  'issues', 'settings'
]

const featureLabels = {
  dashboard: 'Dashboard', brokers: 'Brokers', strategies: 'Strategies',
  backtest: 'Backtest', optimization: 'Optimization', monte_carlo: 'Monte Carlo',
  live: 'Live/Paper', import_data: 'Import Data', tools: 'Tools',
  llm_studio: 'LLM Studio', issues: 'Issues', settings: 'Settings'
}

const activeUsers = computed(() => users.value.filter(u => !u.deleted_at))
const deletedUsers = computed(() => users.value.filter(u => u.deleted_at))
const displayedUsers = computed(() => viewTab.value === 'active' ? activeUsers.value : deletedUsers.value)

onMounted(async () => { await loadUsers() })

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.getUsers()
    users.value = res.users || res || []
  } catch (e) {
    error.value = e.message || 'Failed to load users'
  } finally {
    loading.value = false
  }
}

function toggleExpand(id) {
  if (expandedUser.value === id) {
    expandedUser.value = null
  } else {
    expandedUser.value = id
    userTab.value = 'Overview'
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function quotaPercent(q) {
  if (!q.max_runs || q.max_runs <= 0) return 0
  return Math.min(100, Math.round((q.used_runs / q.max_runs) * 100))
}

function totalSessions(stats) {
  if (!stats) return 0
  return (stats.backtest_sessions || 0) + (stats.live_sessions || 0) + (stats.optimization_sessions || 0) + (stats.monte_carlo_sessions || 0)
}

function statCards(stats) {
  if (!stats) return []
  return [
    { label: 'Backtests', value: stats.backtest_sessions || 0 },
    { label: 'Live Sessions', value: stats.live_sessions || 0 },
    { label: 'Optimizations', value: stats.optimization_sessions || 0 },
    { label: 'Monte Carlo', value: stats.monte_carlo_sessions || 0 },
    { label: 'Strategies', value: stats.strategies || 0 },
    { label: 'Issues', value: stats.issues || 0 },
    { label: 'Broker Keys', value: stats.broker_keys || 0 },
    { label: 'Notifications', value: stats.notification_keys || 0 },
  ]
}

// --- Quota Requests ---

async function loadQuotaRequests() {
  try {
    const res = await api.getQuotaRequests()
    quotaRequests.value = res.requests || []
  } catch (e) {
    console.error('Failed to load quota requests', e)
  }
}

async function reviewRequest(requestId, status) {
  reviewingId.value = requestId
  try {
    const runs = approvedRuns[requestId]
    await api.reviewQuotaRequest({
      request_id: requestId,
      status,
      approved_runs: status === 'approved' && runs ? runs : undefined,
    })
    // Remove from list
    quotaRequests.value = quotaRequests.value.filter(r => r.id !== requestId)
    delete approvedRuns[requestId]
    // Reload users to update quota display
    await loadUsers()
  } catch (e) {
    error.value = e.message || 'Failed to review request'
  } finally {
    reviewingId.value = null
  }
}

// Load quota requests on mount
onMounted(async () => { loadQuotaRequests() })

// --- CRUD ---

async function createUser() {
  creatingUser.value = true
  createMsg.value = ''
  try {
    await api.adminCreateUser(createForm.value)
    createMsg.value = 'User created'
    createErr.value = false
    createForm.value = { username: '', password: '', role: 'user' }
    showCreateForm.value = false
    await loadUsers()
  } catch (e) {
    createMsg.value = e.message || 'Failed'
    createErr.value = true
  } finally {
    creatingUser.value = false
  }
}

async function impersonateUser(user) {
  impersonatingId.value = user.id
  try {
    const res = await api.impersonate(user.id)
    setAuth(res.auth_token, res.user || getCurrentUser())
    router.push('/')
    location.reload()
  } catch (e) {
    error.value = e.message || 'Failed to impersonate user'
  } finally {
    impersonatingId.value = null
  }
}

async function toggleActive(user) {
  togglingId.value = user.id
  try {
    await api.updateUser({ user_id: user.id, is_active: !user.is_active })
    user.is_active = !user.is_active
  } catch (e) {
    error.value = e.message || 'Failed to update user'
  } finally {
    togglingId.value = null
  }
}

async function toggleFeature(user, feature) {
  const current = user.allowed_features || []
  const newFeatures = current.includes(feature)
    ? current.filter(f => f !== feature)
    : [...current, feature]
  try {
    await api.updateUser({ user_id: user.id, allowed_features: newFeatures })
    user.allowed_features = newFeatures
  } catch (e) {
    error.value = e.message || 'Failed to update features'
  }
}

async function updateQuota(userId, feature, maxRuns) {
  const val = parseInt(maxRuns, 10)
  if (isNaN(val) || val < 0) return
  try {
    await api.updateUserQuota({ user_id: userId, feature, max_runs: val })
    const user = users.value.find(u => u.id === userId)
    if (user && user.quotas) {
      const q = user.quotas.find(q => q.feature === feature)
      if (q) q.max_runs = val
    }
  } catch (e) {
    error.value = e.message || 'Failed to update quota'
  }
}

async function changeRole(user, newRole) {
  try {
    await api.updateUser({ user_id: user.id, role: newRole })
    user.role = newRole
  } catch (e) {
    error.value = e.message || 'Failed to update role'
  }
}

async function resetPassword(user) {
  const pw = resetPasswordForm[user.id]
  if (!pw || pw.length < 6) {
    resetMsg[user.id] = 'Min 6 characters'
    resetErr[user.id] = true
    return
  }
  resettingPassword.value = user.id
  try {
    const res = await api.adminResetPassword(user.id, pw)
    resetMsg[user.id] = res.message || 'Password reset'
    resetErr[user.id] = false
    resetPasswordForm[user.id] = ''
  } catch (e) {
    resetMsg[user.id] = e.message || 'Failed'
    resetErr[user.id] = true
  } finally {
    resettingPassword.value = null
  }
}

async function deleteUser(user, deleteData) {
  const action = deleteData ? 'delete account AND all data' : 'delete account only (keep data)'
  if (!confirm(`${action} for ${user.username}? This cannot be undone.`)) return
  deletingUser.value = user.id
  deleteMsg.value = ''
  try {
    const res = await api.adminDeleteUser(user.id, deleteData)
    deleteMsg.value = res.message || 'User deleted'
    deleteErr.value = false
    await loadUsers()
  } catch (e) {
    deleteMsg.value = e.message || 'Failed'
    deleteErr.value = true
  } finally {
    deletingUser.value = null
  }
}
</script>
