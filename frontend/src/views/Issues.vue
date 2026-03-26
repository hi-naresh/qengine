<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-8">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Issues & Feedback</h1>
        <p class="text-xs text-surface-500 mt-0.5">Track bugs, feature requests, and notes about your trading system</p>
      </div>
      <button @click="showCreate = true" class="btn-primary btn-sm flex items-center gap-1.5">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
        New Issue
      </button>
    </div>

    <!-- Status Filter -->
    <div class="flex gap-2 mb-4 flex-wrap">
      <button v-for="s in statusFilters" :key="s.value" @click="filterStatus = s.value"
        class="btn-sm text-xs" :class="filterStatus === s.value ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        {{ s.label }}
        <span v-if="statusCounts[s.value] !== undefined" class="ml-1 opacity-60">({{ statusCounts[s.value] }})</span>
      </button>
    </div>

    <!-- Issues List -->
    <div v-if="loading" class="text-sm text-surface-500 py-8 text-center">Loading issues...</div>
    <div v-else-if="filteredIssues.length === 0" class="text-sm text-surface-500 py-8 text-center">
      No issues{{ filterStatus ? ` with status "${filterStatus}"` : '' }}. Create one to get started.
    </div>
    <div v-else class="space-y-2">
      <div v-for="issue in filteredIssues" :key="issue.id"
        class="card p-4 hover:bg-surface-800/50 transition-colors cursor-pointer"
        @click="viewIssue(issue)">
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full flex-shrink-0" :class="statusColor(issue.status)"></span>
              <span class="text-sm font-medium text-surface-200 truncate">{{ issue.title }}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded capitalize flex-shrink-0"
                :class="priorityBadge(issue.priority)">{{ issue.priority }}</span>
            </div>
            <div class="flex items-center gap-3 text-xs text-surface-500">
              <span class="capitalize">{{ issue.status.replace('-', ' ') }}</span>
              <span v-if="issue.author">&middot; {{ issue.author }}</span>
              <span>&middot; {{ formatDate(issue.created_at) }}</span>
            </div>
            <div v-if="issue.labels && issue.labels.length" class="flex gap-1 mt-1.5">
              <span v-for="l in issue.labels" :key="l"
                class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-surface-400 rounded">{{ l }}</span>
            </div>
          </div>
          <div class="flex gap-1 flex-shrink-0">
            <button @click.stop="editIssue(issue)" class="p-1.5 rounded hover:bg-surface-700 text-surface-500 hover:text-surface-300">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z"/></svg>
            </button>
            <button @click.stop="deleteIssueConfirm(issue)" class="p-1.5 rounded hover:bg-red-500/10 text-surface-500 hover:text-red-400">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
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

    <!-- Create/Edit Modal -->
    <div v-if="showCreate || showEdit" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="closeModal">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-lg mx-4 p-5 max-h-[90vh] overflow-y-auto">
        <h2 class="text-sm font-semibold mb-4 text-surface-200">{{ showEdit ? 'Edit Issue' : 'New Issue' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="label">Title *</label>
            <input v-model="form.title" class="input" placeholder="Brief summary of the issue" />
          </div>
          <div>
            <label class="label">Description / Log</label>
            <textarea v-model="form.description" class="input min-h-[120px] resize-y" placeholder="Detailed description, steps to reproduce, error logs..."></textarea>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label class="label">Status</label>
              <select v-model="form.status" class="select">
                <option value="todo">Todo</option>
                <option value="in-progress">In Progress</option>
                <option value="in-review">In Review</option>
                <option value="done">Done</option>
              </select>
            </div>
            <div>
              <label class="label">Priority</label>
              <select v-model="form.priority" class="select">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label class="label">Author</label>
              <input v-model="form.author" class="input" placeholder="Your name" />
            </div>
          </div>
          <div>
            <label class="label">Labels (comma-separated)</label>
            <input v-model="labelsInput" class="input" placeholder="bug, frontend, urgent" />
          </div>
          <div class="flex gap-2 pt-1">
            <button @click="submitForm" class="btn-primary flex-1" :disabled="saving">
              {{ saving ? 'Saving...' : (showEdit ? 'Update Issue' : 'Create Issue') }}
            </button>
            <button @click="closeModal" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
          </div>
          <p v-if="formError" class="text-xs text-red-400">{{ formError }}</p>
        </div>
      </div>
    </div>

    <!-- View Modal -->
    <div v-if="viewingIssue" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="viewingIssue = null">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-lg mx-4 p-5">
        <div class="flex items-start justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full" :class="statusColor(viewingIssue.status)"></span>
            <h2 class="text-sm font-semibold text-surface-200">{{ viewingIssue.title }}</h2>
          </div>
          <button @click="viewingIssue = null" class="text-surface-500 hover:text-surface-300">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex items-center gap-3 text-xs text-surface-500 mb-3">
          <span class="capitalize px-1.5 py-0.5 rounded" :class="statusBadge(viewingIssue.status)">{{ viewingIssue.status.replace('-', ' ') }}</span>
          <span class="capitalize px-1.5 py-0.5 rounded" :class="priorityBadge(viewingIssue.priority)">{{ viewingIssue.priority }}</span>
          <span v-if="viewingIssue.author">&middot; {{ viewingIssue.author }}</span>
          <span>&middot; {{ formatDate(viewingIssue.created_at) }}</span>
        </div>
        <div v-if="viewingIssue.labels && viewingIssue.labels.length" class="flex gap-1 mb-3">
          <span v-for="l in viewingIssue.labels" :key="l"
            class="text-[10px] px-1.5 py-0.5 bg-surface-700 text-surface-400 rounded">{{ l }}</span>
        </div>
        <div v-if="viewingIssue.description" class="text-sm text-surface-400 bg-surface-800 rounded-lg p-3 whitespace-pre-wrap max-h-[300px] overflow-auto">{{ viewingIssue.description }}</div>
        <div v-else class="text-sm text-surface-600 italic">No description provided.</div>

        <!-- Quick status change -->
        <div class="flex gap-2 mt-4 pt-3 border-t border-surface-700">
          <span class="text-xs text-surface-500 py-1">Move to:</span>
          <button v-for="s in ['todo','in-progress','in-review','done']" :key="s"
            v-show="s !== viewingIssue.status"
            @click="quickStatusChange(viewingIssue, s)"
            class="btn-sm text-[10px] bg-surface-800 text-surface-400 hover:text-surface-200 capitalize">
            {{ s.replace('-', ' ') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="deleteTarget" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="deleteTarget = null">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-sm mx-4 p-5">
        <h2 class="text-sm font-semibold mb-2 text-surface-200">Delete Issue</h2>
        <p class="text-xs text-surface-400 mb-4">Are you sure you want to delete "{{ deleteTarget.title }}"? This cannot be undone.</p>
        <div class="flex gap-2">
          <button @click="confirmDelete" class="btn-danger flex-1" :disabled="deleting">{{ deleting ? 'Deleting...' : 'Delete' }}</button>
          <button @click="deleteTarget = null" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const issues = ref([])
const loading = ref(true)
const total = ref(0)
const offset = ref(0)
const limit = 50
const filterStatus = ref('')

const showCreate = ref(false)
const showEdit = ref(false)
const viewingIssue = ref(null)
const deleteTarget = ref(null)
const deleting = ref(false)
const saving = ref(false)
const formError = ref('')
const labelsInput = ref('')

const form = ref({ title: '', description: '', status: 'todo', priority: 'medium', author: '', labels: [] })

const statusFilters = [
  { label: 'All', value: '' },
  { label: 'Todo', value: 'todo' },
  { label: 'In Progress', value: 'in-progress' },
  { label: 'In Review', value: 'in-review' },
  { label: 'Done', value: 'done' },
]

const statusCounts = computed(() => {
  const counts = {}
  for (const i of issues.value) {
    counts[i.status] = (counts[i.status] || 0) + 1
  }
  return counts
})

const filteredIssues = computed(() => {
  if (!filterStatus.value) return issues.value
  return issues.value.filter(i => i.status === filterStatus.value)
})

function statusColor(s) {
  const m = { 'todo': 'bg-surface-500', 'in-progress': 'bg-blue-400', 'in-review': 'bg-amber-400', 'done': 'bg-green-400' }
  return m[s] || 'bg-surface-500'
}

function statusBadge(s) {
  const m = { 'todo': 'bg-surface-700 text-surface-400', 'in-progress': 'bg-blue-500/10 text-blue-400', 'in-review': 'bg-amber-500/10 text-amber-400', 'done': 'bg-green-500/10 text-green-400' }
  return m[s] || 'bg-surface-700 text-surface-400'
}

function priorityBadge(p) {
  const m = { 'low': 'bg-surface-700 text-surface-500', 'medium': 'bg-surface-700 text-surface-400', 'high': 'bg-amber-500/10 text-amber-400', 'critical': 'bg-red-500/10 text-red-400' }
  return m[p] || 'bg-surface-700 text-surface-400'
}

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function loadIssues() {
  loading.value = true
  try {
    const res = await api.getIssues({ limit: 500, offset: 0 })
    issues.value = res.issues || []
    total.value = res.total || 0
  } catch (e) {
    console.error('Failed to load issues:', e)
  } finally {
    loading.value = false
  }
}

function prevPage() { offset.value = Math.max(0, offset.value - limit) }
function nextPage() { if (offset.value + limit < total.value) offset.value += limit }

function viewIssue(issue) { viewingIssue.value = issue }

function editIssue(issue) {
  form.value = {
    id: issue.id,
    title: issue.title,
    description: issue.description || '',
    status: issue.status,
    priority: issue.priority,
    author: issue.author || '',
  }
  labelsInput.value = (issue.labels || []).join(', ')
  showEdit.value = true
}

function closeModal() {
  showCreate.value = false
  showEdit.value = false
  form.value = { title: '', description: '', status: 'todo', priority: 'medium', author: '' }
  labelsInput.value = ''
  formError.value = ''
}

async function submitForm() {
  if (!form.value.title.trim()) {
    formError.value = 'Title is required'
    return
  }
  saving.value = true
  formError.value = ''
  const labels = labelsInput.value ? labelsInput.value.split(',').map(l => l.trim()).filter(Boolean) : []

  try {
    if (showEdit.value) {
      await api.updateIssue({ ...form.value, labels })
    } else {
      // Remember author for next time
      const author = form.value.author.trim()
      if (author) localStorage.setItem('te_issue_author', author)
      await api.createIssue({ ...form.value, labels })
    }
    closeModal()
    await loadIssues()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

function deleteIssueConfirm(issue) { deleteTarget.value = issue }

async function confirmDelete() {
  deleting.value = true
  try {
    await api.deleteIssue(deleteTarget.value.id)
    deleteTarget.value = null
    await loadIssues()
  } catch (e) {
    console.error(e)
  } finally {
    deleting.value = false
  }
}

async function quickStatusChange(issue, newStatus) {
  try {
    await api.updateIssue({ id: issue.id, status: newStatus })
    issue.status = newStatus
    viewingIssue.value = { ...issue, status: newStatus }
    await loadIssues()
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  loadIssues()
  // Pre-fill author from last time
  const saved = localStorage.getItem('te_issue_author')
  if (saved) form.value.author = saved
})
</script>
