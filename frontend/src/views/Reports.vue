<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Error Reports</h1>
        <p class="text-xs text-surface-500 mt-0.5">System errors captured across all sessions. Submit any error as an issue ticket.</p>
      </div>
      <div class="flex gap-2">
        <button v-if="reports.length && newCount > 0" @click="dismissAll" class="btn-sm bg-surface-800 text-surface-400 hover:text-surface-200 flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          Dismiss All
        </button>
        <button v-if="reports.length" @click="showClear = true" class="btn-sm bg-surface-800 text-surface-500 hover:text-red-400 flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
          Clear
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex gap-2 mb-4 flex-wrap">
      <button v-for="s in statusFilters" :key="s.value" @click="filterStatus = s.value"
        class="btn-sm text-xs" :class="filterStatus === s.value ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        {{ s.label }}
        <span v-if="statusCounts[s.value] !== undefined" class="ml-1 opacity-60">({{ statusCounts[s.value] }})</span>
      </button>
      <div class="flex-1"></div>
      <select v-model="filterType" class="select text-xs w-auto px-2 py-1 bg-surface-800 border-surface-700">
        <option value="">All Sources</option>
        <option value="backtest">Backtest</option>
        <option value="live">Live</option>
        <option value="optimization">Optimization</option>
        <option value="monte-carlo">Monte Carlo</option>
        <option value="system">System</option>
      </select>
    </div>

    <!-- Reports List -->
    <div v-if="loading" class="text-sm text-surface-500 py-8 text-center">Loading error reports...</div>
    <div v-else-if="reports.length === 0" class="text-sm text-surface-500 py-8 text-center">
      No error reports{{ filterStatus ? ` with status "${filterStatus}"` : '' }}. The system is running clean.
    </div>
    <div v-else class="space-y-2">
      <div v-for="report in reports" :key="report.id"
        class="card p-4 hover:bg-surface-800/50 transition-colors cursor-pointer"
        :class="report.status === 'new' ? 'border-l-2 border-l-red-500/60' : ''"
        @click="viewReport(report)">
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full flex-shrink-0" :class="reportStatusColor(report.status)"></span>
              <span class="text-[10px] px-1.5 py-0.5 rounded capitalize flex-shrink-0"
                :class="sessionTypeBadge(report.session_type)">{{ report.session_type || 'system' }}</span>
              <span v-if="report.error_type" class="text-[10px] font-mono px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded flex-shrink-0">{{ report.error_type }}</span>
              <span class="text-sm text-surface-200 truncate">{{ report.message }}</span>
            </div>
            <div class="flex items-center gap-3 text-xs text-surface-500">
              <span class="capitalize">{{ report.status }}</span>
              <span>&middot; {{ formatDate(report.created_at) }}</span>
              <span v-if="report.session_id">&middot; Session {{ report.session_id.slice(0, 8) }}...</span>
              <span v-if="report.issue_id" class="inline-flex items-center gap-1 text-brand-400">
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"/></svg>
                Linked to issue
              </span>
            </div>
          </div>
          <div class="flex gap-1 flex-shrink-0">
            <button v-if="report.status === 'new'" @click.stop="dismissReport(report)" class="p-1.5 rounded hover:bg-surface-700 text-surface-500 hover:text-surface-300" title="Dismiss">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </button>
            <button v-if="report.status !== 'submitted'" @click.stop="openSubmitModal(report)" class="p-1.5 rounded hover:bg-brand-500/10 text-surface-500 hover:text-brand-400" title="Submit as Issue">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > limit" class="flex items-center justify-center gap-3 mt-4">
      <button @click="prevPage" :disabled="offset === 0" class="btn-sm bg-surface-800 text-surface-400 disabled:opacity-30">Prev</button>
      <span class="text-xs text-surface-500">{{ offset + 1 }}-{{ Math.min(offset + limit, total) }} of {{ total }}</span>
      <button @click="nextPage" :disabled="offset + limit >= total" class="btn-sm bg-surface-800 text-surface-400 disabled:opacity-30">Next</button>
    </div>

    <!-- View Report Modal -->
    <div v-if="selectedReport" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="selectedReport = null">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-2xl mx-4 p-5 max-h-[90vh] overflow-y-auto">
        <div class="flex items-start justify-between mb-4">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full" :class="reportStatusColor(selectedReport.status)"></span>
              <span class="text-[10px] px-1.5 py-0.5 rounded capitalize"
                :class="sessionTypeBadge(selectedReport.session_type)">{{ selectedReport.session_type || 'system' }}</span>
              <span v-if="selectedReport.error_type" class="text-[10px] font-mono px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded">{{ selectedReport.error_type }}</span>
              <span class="text-xs text-surface-500 capitalize">{{ selectedReport.status }}</span>
            </div>
            <p class="text-xs text-surface-500 mt-1">{{ formatDate(selectedReport.created_at) }}</p>
          </div>
          <button @click="selectedReport = null" class="p-1 rounded hover:bg-surface-700 text-surface-500">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- Error Message -->
        <div class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Error Message</label>
          <div class="bg-surface-800 rounded-lg p-3 text-sm text-red-300 font-mono break-all whitespace-pre-wrap">{{ selectedReport.message }}</div>
        </div>

        <!-- Traceback -->
        <div v-if="selectedReport.traceback" class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Traceback</label>
          <div class="bg-surface-950 rounded-lg p-3 text-xs text-surface-400 font-mono overflow-x-auto max-h-64 overflow-y-auto whitespace-pre">{{ selectedReport.traceback }}</div>
        </div>

        <!-- Context -->
        <div v-if="selectedReport.context" class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Context</label>
          <div class="bg-surface-800 rounded-lg p-3 text-xs text-surface-400 font-mono overflow-x-auto whitespace-pre">{{ typeof selectedReport.context === 'object' ? JSON.stringify(selectedReport.context, null, 2) : selectedReport.context }}</div>
        </div>

        <!-- Session Info -->
        <div v-if="selectedReport.session_id" class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Session</label>
          <p class="text-xs text-surface-400 font-mono">{{ selectedReport.session_id }}</p>
        </div>

        <!-- Actions -->
        <div class="flex gap-2 pt-2 border-t border-surface-700">
          <button v-if="selectedReport.status !== 'submitted'" @click="openSubmitModal(selectedReport)" class="btn-primary btn-sm flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Submit as Issue
          </button>
          <button v-if="selectedReport.status === 'submitted' && selectedReport.issue_id" @click="goToIssue(selectedReport.issue_id)" class="btn-sm bg-brand-600/20 text-brand-400 flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"/></svg>
            View Issue
          </button>
          <button v-if="selectedReport.status === 'new'" @click="dismissReport(selectedReport); selectedReport = null" class="btn-sm bg-surface-700 text-surface-400">
            Dismiss
          </button>
          <div class="flex-1"></div>
          <button @click="selectedReport = null" class="btn-sm bg-surface-800 text-surface-500">Close</button>
        </div>
      </div>
    </div>

    <!-- Submit as Issue Modal -->
    <div v-if="showSubmit" class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" @click.self="showSubmit = false">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-lg mx-4 p-5">
        <h2 class="text-sm font-semibold mb-4 text-surface-200">Submit Error as Issue</h2>
        <div class="space-y-3">
          <div>
            <label class="label">Title</label>
            <input v-model="submitForm.title" class="input" placeholder="Issue title" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="label">Priority</label>
              <select v-model="submitForm.priority" class="select">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label class="label">Labels</label>
              <input v-model="submitForm.labels" class="input" placeholder="bug, auto-reported" />
            </div>
          </div>
          <div class="bg-surface-800 rounded-lg p-3 text-xs text-surface-400">
            <p class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1">Error preview</p>
            <p class="font-mono text-red-300 truncate">{{ submitReport?.message }}</p>
          </div>
          <div class="flex gap-2 pt-1">
            <button @click="submitAsIssue" class="btn-primary flex-1" :disabled="submitting">
              {{ submitting ? 'Submitting...' : 'Create Issue from Error' }}
            </button>
            <button @click="showSubmit = false" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Clear Confirmation Modal -->
    <div v-if="showClear" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="showClear = false">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-sm mx-4 p-5">
        <h2 class="text-sm font-semibold mb-3 text-surface-200">Clear Error Reports</h2>
        <p class="text-xs text-surface-400 mb-4">This will delete all non-submitted error reports. Reports already submitted as issues will be kept.</p>
        <div class="flex gap-2">
          <button @click="clearReports" class="btn-sm bg-red-600 text-white flex-1">Clear Reports</button>
          <button @click="showClear = false" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api, isAdmin, isImpersonating } from '../api'
import { useRouter } from 'vue-router'

const router = useRouter()

const reports = ref([])
const total = ref(0)
const loading = ref(true)
const filterStatus = ref('')
const filterType = ref('')
const offset = ref(0)
const limit = ref(50)
const newCount = ref(0)

const selectedReport = ref(null)
const showSubmit = ref(false)
const showClear = ref(false)
const submitReport = ref(null)
const submitting = ref(false)

const submitForm = ref({
  title: '',
  priority: 'high',
  labels: 'bug,auto-reported',
})

const statusFilters = [
  { value: '', label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'submitted', label: 'Submitted' },
]

const statusCounts = ref({})

async function fetchReports() {
  loading.value = true
  try {
    const params = { limit: limit.value, offset: offset.value }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterType.value) params.session_type = filterType.value
    const data = await api.getReports(params)
    reports.value = data.reports
    total.value = data.total
  } catch (e) {
    console.error('Failed to fetch reports:', e)
  }
  loading.value = false
}

async function fetchCounts() {
  try {
    const [allRes, newRes, reviewedRes, submittedRes] = await Promise.all([
      api.getReports({ limit: 0 }),
      api.getReports({ status: 'new', limit: 0 }),
      api.getReports({ status: 'reviewed', limit: 0 }),
      api.getReports({ status: 'submitted', limit: 0 }),
    ])
    statusCounts.value = {
      '': allRes.total,
      'new': newRes.total,
      'reviewed': reviewedRes.total,
      'submitted': submittedRes.total,
    }
    newCount.value = newRes.total
  } catch (e) {
    console.error('Failed to fetch report counts:', e)
  }
}

function viewReport(report) {
  selectedReport.value = report
}

async function dismissReport(report) {
  try {
    await api.dismissReport(report.id)
    report.status = 'reviewed'
    fetchCounts()
  } catch (e) {
    console.error('Failed to dismiss:', e)
  }
}

async function dismissAll() {
  try {
    await api.bulkDismissReports()
    reports.value.forEach(r => { if (r.status === 'new') r.status = 'reviewed' })
    fetchCounts()
  } catch (e) {
    console.error('Failed to dismiss all:', e)
  }
}

function openSubmitModal(report) {
  submitReport.value = report
  submitForm.value = {
    title: `[${report.error_type || 'Error'}] ${report.message.slice(0, 100)}`,
    priority: 'high',
    labels: `bug,auto-reported,${report.session_type || 'system'}`,
  }
  showSubmit.value = true
}

async function submitAsIssue() {
  if (!submitReport.value) return
  submitting.value = true
  try {
    const res = await api.submitReportAsIssue({
      id: submitReport.value.id,
      title: submitForm.value.title,
      priority: submitForm.value.priority,
      labels: submitForm.value.labels,
    })
    // Update local state
    submitReport.value.status = 'submitted'
    submitReport.value.issue_id = res.issue?.id
    showSubmit.value = false
    selectedReport.value = null
    fetchCounts()
  } catch (e) {
    console.error('Failed to submit as issue:', e)
  }
  submitting.value = false
}

async function clearReports() {
  try {
    await api.clearReports()
    showClear.value = false
    fetchReports()
    fetchCounts()
  } catch (e) {
    console.error('Failed to clear reports:', e)
  }
}

function goToIssue(issueId) {
  selectedReport.value = null
  router.push('/issues')
}

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: d.getFullYear() !== now.getFullYear() ? 'numeric' : undefined })
}

function reportStatusColor(status) {
  return {
    'new': 'bg-red-400',
    'reviewed': 'bg-yellow-400',
    'submitted': 'bg-brand-400',
  }[status] || 'bg-surface-500'
}

function sessionTypeBadge(type) {
  return {
    'backtest': 'bg-blue-500/15 text-blue-400',
    'live': 'bg-green-500/15 text-green-400',
    'optimization': 'bg-purple-500/15 text-purple-400',
    'monte-carlo': 'bg-orange-500/15 text-orange-400',
    'system': 'bg-surface-700 text-surface-400',
  }[type] || 'bg-surface-700 text-surface-400'
}

function prevPage() {
  offset.value = Math.max(0, offset.value - limit.value)
}

function nextPage() {
  if (offset.value + limit.value < total.value) {
    offset.value += limit.value
  }
}

watch([filterStatus, filterType], () => {
  offset.value = 0
  fetchReports()
})

watch(offset, fetchReports)

onMounted(() => {
  fetchReports()
  fetchCounts()
})
</script>
