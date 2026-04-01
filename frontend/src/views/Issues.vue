<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
      <div>
        <h1 class="text-2xl font-bold text-center sm:text-left">Issues & Reports</h1>
        <p class="text-xs text-surface-500 mt-0.5">Track bugs, feature requests, and system error reports</p>
      </div>
      <button v-if="activeTab === 'issues'" @click="showCreate = true" class="btn-primary btn-sm flex items-center gap-1.5">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
        New Issue
      </button>
      <div v-else class="flex gap-2">
        <button v-if="errReports.length && errNewCount > 0" @click="errDismissAll" class="btn-sm bg-surface-800 text-surface-400 hover:text-surface-200 flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          Dismiss All
        </button>
        <button v-if="errReports.length" @click="showClear = true" class="btn-sm bg-surface-800 text-surface-500 hover:text-red-400 flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
          Clear
        </button>
      </div>
    </div>

    <!-- Subtabs -->
    <div class="flex gap-2 mb-5">
      <button @click="activeTab = 'issues'"
        class="btn-sm" :class="activeTab === 'issues' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        Issues & Feedback
      </button>
      <button @click="activeTab = 'errors'"
        class="btn-sm relative" :class="activeTab === 'errors' ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        Error Reports
        <span v-if="errNewCount > 0" class="ml-1.5 min-w-[16px] h-[16px] inline-flex items-center justify-center text-[9px] font-bold rounded-full px-1 leading-none"
          :class="activeTab === 'errors' ? 'bg-white/20 text-white' : 'bg-orange-500 text-white'">
          {{ errNewCount > 99 ? '99+' : errNewCount }}
        </span>
      </button>
    </div>

    <!-- ==================== ISSUES TAB ==================== -->
    <template v-if="activeTab === 'issues'">
      <!-- Status Filter -->
      <div class="flex gap-2 mb-4 flex-wrap">
        <button v-for="s in issueStatusFilters" :key="s.value" @click="issueFilterStatus = s.value"
          class="btn-sm text-xs" :class="issueFilterStatus === s.value ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
          {{ s.label }}
          <span v-if="issueStatusCounts[s.value] !== undefined" class="ml-1 opacity-60">({{ issueStatusCounts[s.value] }})</span>
        </button>
      </div>

      <!-- Issues List -->
      <div v-if="issueLoading" class="text-sm text-surface-500 py-8 text-center">Loading issues...</div>
      <div v-else-if="filteredIssues.length === 0" class="text-sm text-surface-500 py-8 text-center">
        No issues{{ issueFilterStatus ? ` with status "${issueFilterStatus}"` : '' }}. Create one to get started.
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
                <span v-if="issue.owner_username && isAdmin() && !isImpersonating()" class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 font-medium">{{ issue.owner_username }}</span>
                <span>&middot; {{ formatDate(issue.created_at) }}</span>
                <span v-if="issue.comment_count" class="inline-flex items-center gap-1 text-surface-400">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"/></svg>
                  {{ issue.comment_count }}
                </span>
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
      <div v-if="issueTotal > issueLimit" class="flex items-center justify-center gap-3 mt-4">
        <button @click="issuePrevPage" :disabled="issueOffset === 0" class="btn-sm bg-surface-800 text-surface-400 disabled:opacity-30">Prev</button>
        <span class="text-xs text-surface-500">{{ issueOffset + 1 }}-{{ Math.min(issueOffset + issueLimit, issueTotal) }} of {{ issueTotal }}</span>
        <button @click="issueNextPage" :disabled="issueOffset + issueLimit >= issueTotal" class="btn-sm bg-surface-800 text-surface-400 disabled:opacity-30">Next</button>
      </div>
    </template>

    <!-- ==================== ERROR REPORTS TAB ==================== -->
    <template v-if="activeTab === 'errors'">
      <!-- Filters -->
      <div class="flex gap-2 mb-4 flex-wrap">
        <button v-for="s in errStatusFilters" :key="s.value" @click="errFilterStatus = s.value"
          class="btn-sm text-xs" :class="errFilterStatus === s.value ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
          {{ s.label }}
          <span v-if="errStatusCounts[s.value] !== undefined" class="ml-1 opacity-60">({{ errStatusCounts[s.value] }})</span>
        </button>
        <div class="flex-1"></div>
        <select v-model="errFilterType" class="select text-xs w-auto px-2 py-1 bg-surface-800 border-surface-700">
          <option value="">All Sources</option>
          <option value="backtest">Backtest</option>
          <option value="live">Live</option>
          <option value="optimization">Optimization</option>
          <option value="monte-carlo">Monte Carlo</option>
          <option value="system">System</option>
        </select>
      </div>

      <!-- Reports List -->
      <div v-if="errLoading" class="text-sm text-surface-500 py-8 text-center">Loading error reports...</div>
      <div v-else-if="errReports.length === 0" class="text-sm text-surface-500 py-8 text-center">
        No error reports{{ errFilterStatus ? ` with status "${errFilterStatus}"` : '' }}. The system is running clean.
      </div>
      <div v-else class="space-y-2">
        <div v-for="report in errReports" :key="report.id"
          class="card p-4 hover:bg-surface-800/50 transition-colors cursor-pointer"
          :class="report.status === 'new' ? 'border-l-2 border-l-red-500/60' : ''"
          @click="errViewReport(report)">
          <div class="flex items-start justify-between gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="w-2 h-2 rounded-full flex-shrink-0" :class="errStatusColor(report.status)"></span>
                <span class="text-[10px] px-1.5 py-0.5 rounded capitalize flex-shrink-0"
                  :class="errSessionBadge(report.session_type)">{{ report.session_type || 'system' }}</span>
                <span v-if="report.error_type" class="text-[10px] font-mono px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded flex-shrink-0">{{ report.error_type }}</span>
                <span class="text-sm text-surface-200 truncate">{{ report.message }}</span>
              </div>
              <div class="flex items-center gap-3 text-xs text-surface-500">
                <span class="capitalize">{{ report.status }}</span>
                <span>&middot; {{ errFormatDate(report.created_at) }}</span>
                <span v-if="report.session_id">&middot; Session {{ report.session_id.slice(0, 8) }}...</span>
                <span v-if="report.issue_id" class="inline-flex items-center gap-1 text-brand-400">
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"/></svg>
                  Linked to issue
                </span>
              </div>
            </div>
            <div class="flex gap-1 flex-shrink-0">
              <button v-if="report.status === 'new'" @click.stop="errDismissReport(report)" class="p-1.5 rounded hover:bg-surface-700 text-surface-500 hover:text-surface-300" title="Dismiss">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </button>
              <button v-if="report.status !== 'submitted'" @click.stop="errOpenSubmitModal(report)" class="p-1.5 rounded hover:bg-brand-500/10 text-surface-500 hover:text-brand-400" title="Submit as Issue">
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="errTotal > errLimit" class="flex items-center justify-center gap-3 mt-4">
        <button @click="errPrevPage" :disabled="errOffset === 0" class="btn-sm bg-surface-800 text-surface-400 disabled:opacity-30">Prev</button>
        <span class="text-xs text-surface-500">{{ errOffset + 1 }}-{{ Math.min(errOffset + errLimit, errTotal) }} of {{ errTotal }}</span>
        <button @click="errNextPage" :disabled="errOffset + errLimit >= errTotal" class="btn-sm bg-surface-800 text-surface-400 disabled:opacity-30">Next</button>
      </div>
    </template>

    <!-- ==================== SHARED MODALS ==================== -->

    <!-- Create/Edit Issue Modal -->
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

    <!-- View Issue Modal -->
    <div v-if="viewingIssue" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="closeViewModal">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-2xl mx-4 p-5 max-h-[90vh] overflow-y-auto">
        <div class="flex items-start justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full" :class="statusColor(viewingIssue.status)"></span>
            <h2 class="text-sm font-semibold text-surface-200">{{ viewingIssue.title }}</h2>
          </div>
          <button @click="closeViewModal" class="text-surface-500 hover:text-surface-300">
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
        <div v-if="viewingIssue.description" class="text-sm text-surface-400 bg-surface-800 rounded-lg p-3 whitespace-pre-wrap max-h-[200px] overflow-auto">{{ viewingIssue.description }}</div>
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

        <!-- Comments Section -->
        <div class="mt-4 pt-4 border-t border-surface-700">
          <div class="flex items-center gap-2 mb-3">
            <svg class="w-4 h-4 text-surface-500" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"/></svg>
            <h3 class="text-xs font-semibold text-surface-300">Comments <span v-if="comments.length" class="text-surface-500 font-normal">({{ comments.length }})</span></h3>
          </div>

          <div v-if="commentsLoading" class="text-xs text-surface-600 py-2">Loading comments...</div>
          <div v-else class="space-y-3">
            <template v-for="comment in topLevelComments" :key="comment.id">
              <div class="bg-surface-800/50 rounded-lg p-3">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="text-xs font-medium text-surface-300">{{ comment.author || 'Anonymous' }}</span>
                      <span class="text-[10px] text-surface-600">{{ formatDateTime(comment.created_at) }}</span>
                    </div>
                    <p class="text-sm text-surface-400 whitespace-pre-wrap break-words">{{ comment.body }}</p>
                  </div>
                  <div class="flex gap-1 flex-shrink-0">
                    <button @click="startReply(comment.id)" class="p-1 rounded hover:bg-surface-700 text-surface-600 hover:text-surface-400" title="Reply">
                      <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3"/></svg>
                    </button>
                    <button @click="deleteComment(comment.id)" class="p-1 rounded hover:bg-red-500/10 text-surface-600 hover:text-red-400" title="Delete">
                      <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                  </div>
                </div>

                <!-- Replies -->
                <div v-if="getReplies(comment.id).length" class="mt-2 ml-4 space-y-2 border-l-2 border-surface-700 pl-3">
                  <div v-for="reply in getReplies(comment.id)" :key="reply.id" class="py-1">
                    <div class="flex items-start justify-between gap-2">
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-0.5">
                          <span class="text-xs font-medium text-surface-300">{{ reply.author || 'Anonymous' }}</span>
                          <span class="text-[10px] text-surface-600">{{ formatDateTime(reply.created_at) }}</span>
                        </div>
                        <p class="text-xs text-surface-400 whitespace-pre-wrap break-words">{{ reply.body }}</p>
                      </div>
                      <button @click="deleteComment(reply.id)" class="p-1 rounded hover:bg-red-500/10 text-surface-600 hover:text-red-400 flex-shrink-0" title="Delete">
                        <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Inline reply form -->
                <div v-if="replyingTo === comment.id" class="mt-2 ml-4 flex gap-2">
                  <input v-model="replyBody" class="input text-xs flex-1" placeholder="Write a reply..." @keyup.enter="submitReply(comment.id)" ref="replyInput" />
                  <button @click="submitReply(comment.id)" class="btn-primary btn-sm text-[10px]" :disabled="!replyBody.trim()">Reply</button>
                  <button @click="replyingTo = null; replyBody = ''" class="btn-sm text-[10px] bg-surface-700 text-surface-400">Cancel</button>
                </div>
              </div>
            </template>
          </div>

          <!-- Add comment form -->
          <div class="mt-3 flex gap-2">
            <input v-model="commentAuthor" class="input text-xs w-24 flex-shrink-0" placeholder="Name" />
            <input v-model="commentBody" class="input text-xs flex-1" placeholder="Write a comment..." @keyup.enter="submitComment" />
            <button @click="submitComment" class="btn-primary btn-sm text-[10px] flex-shrink-0" :disabled="!commentBody.trim()">Comment</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Issue Confirmation -->
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

    <!-- View Error Report Modal -->
    <div v-if="errSelected" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="errSelected = null">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-2xl mx-4 p-5 max-h-[90vh] overflow-y-auto">
        <div class="flex items-start justify-between mb-4">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full" :class="errStatusColor(errSelected.status)"></span>
              <span class="text-[10px] px-1.5 py-0.5 rounded capitalize"
                :class="errSessionBadge(errSelected.session_type)">{{ errSelected.session_type || 'system' }}</span>
              <span v-if="errSelected.error_type" class="text-[10px] font-mono px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded">{{ errSelected.error_type }}</span>
              <span class="text-xs text-surface-500 capitalize">{{ errSelected.status }}</span>
            </div>
            <p class="text-xs text-surface-500 mt-1">{{ errFormatDate(errSelected.created_at) }}</p>
          </div>
          <button @click="errSelected = null" class="p-1 rounded hover:bg-surface-700 text-surface-500">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <div class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Error Message</label>
          <div class="bg-surface-800 rounded-lg p-3 text-sm text-red-300 font-mono break-all whitespace-pre-wrap">{{ errSelected.message }}</div>
        </div>

        <div v-if="errSelected.traceback" class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Traceback</label>
          <div class="bg-surface-950 rounded-lg p-3 text-xs text-surface-400 font-mono overflow-x-auto max-h-64 overflow-y-auto whitespace-pre">{{ errSelected.traceback }}</div>
        </div>

        <div v-if="errSelected.context" class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Context</label>
          <div class="bg-surface-800 rounded-lg p-3 text-xs text-surface-400 font-mono overflow-x-auto whitespace-pre">{{ typeof errSelected.context === 'object' ? JSON.stringify(errSelected.context, null, 2) : errSelected.context }}</div>
        </div>

        <div v-if="errSelected.session_id" class="mb-4">
          <label class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1 block">Session</label>
          <p class="text-xs text-surface-400 font-mono">{{ errSelected.session_id }}</p>
        </div>

        <div class="flex gap-2 pt-2 border-t border-surface-700">
          <button v-if="errSelected.status !== 'submitted'" @click="errOpenSubmitModal(errSelected)" class="btn-primary btn-sm flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Submit as Issue
          </button>
          <button v-if="errSelected.status === 'submitted' && errSelected.issue_id" @click="errGoToIssue()" class="btn-sm bg-brand-600/20 text-brand-400 flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"/></svg>
            View Issue
          </button>
          <button v-if="errSelected.status === 'new'" @click="errDismissReport(errSelected); errSelected = null" class="btn-sm bg-surface-700 text-surface-400">
            Dismiss
          </button>
          <div class="flex-1"></div>
          <button @click="errSelected = null" class="btn-sm bg-surface-800 text-surface-500">Close</button>
        </div>
      </div>
    </div>

    <!-- Submit Error as Issue Modal -->
    <div v-if="errShowSubmit" class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" @click.self="errShowSubmit = false">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-lg mx-4 p-5">
        <h2 class="text-sm font-semibold mb-4 text-surface-200">Submit Error as Issue</h2>
        <div class="space-y-3">
          <div>
            <label class="label">Title</label>
            <input v-model="errSubmitForm.title" class="input" placeholder="Issue title" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="label">Priority</label>
              <select v-model="errSubmitForm.priority" class="select">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label class="label">Labels</label>
              <input v-model="errSubmitForm.labels" class="input" placeholder="bug, auto-reported" />
            </div>
          </div>
          <div class="bg-surface-800 rounded-lg p-3 text-xs text-surface-400">
            <p class="text-[10px] uppercase tracking-wider text-surface-500 font-medium mb-1">Error preview</p>
            <p class="font-mono text-red-300 truncate">{{ errSubmitReport?.message }}</p>
          </div>
          <div class="flex gap-2 pt-1">
            <button @click="errSubmitAsIssue" class="btn-primary flex-1" :disabled="errSubmitting">
              {{ errSubmitting ? 'Submitting...' : 'Create Issue from Error' }}
            </button>
            <button @click="errShowSubmit = false" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Clear Error Reports Confirmation -->
    <div v-if="showClear" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" @click.self="showClear = false">
      <div class="bg-surface-900 border border-surface-700 rounded-xl w-full max-w-sm mx-4 p-5">
        <h2 class="text-sm font-semibold mb-3 text-surface-200">Clear Error Reports</h2>
        <p class="text-xs text-surface-400 mb-4">This will delete all non-submitted error reports. Reports already submitted as issues will be kept.</p>
        <div class="flex gap-2">
          <button @click="errClearReports" class="btn-sm bg-red-600 text-white flex-1">Clear Reports</button>
          <button @click="showClear = false" class="btn-sm bg-surface-700 text-surface-400">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, isAdmin, isImpersonating } from '../api'

const route = useRoute()

// ==================== SUBTAB ====================
const activeTab = ref(route.query.tab === 'errors' ? 'errors' : 'issues')

// ==================== ISSUES STATE ====================
const issues = ref([])
const issueLoading = ref(true)
const issueTotal = ref(0)
const issueOffset = ref(0)
const issueLimit = 50
const issueFilterStatus = ref('')

const showCreate = ref(false)
const showEdit = ref(false)
const viewingIssue = ref(null)
const deleteTarget = ref(null)
const deleting = ref(false)
const saving = ref(false)
const formError = ref('')
const labelsInput = ref('')
const form = ref({ title: '', description: '', status: 'todo', priority: 'medium', author: '', labels: [] })

// Comments
const comments = ref([])
const commentsLoading = ref(false)
const commentBody = ref('')
const commentAuthor = ref('')
const replyingTo = ref(null)
const replyBody = ref('')

const issueStatusFilters = [
  { label: 'All', value: '' },
  { label: 'Todo', value: 'todo' },
  { label: 'In Progress', value: 'in-progress' },
  { label: 'In Review', value: 'in-review' },
  { label: 'Done', value: 'done' },
]

const issueStatusCounts = computed(() => {
  const counts = {}
  for (const i of issues.value) {
    counts[i.status] = (counts[i.status] || 0) + 1
  }
  return counts
})

const filteredIssues = computed(() => {
  if (!issueFilterStatus.value) return issues.value
  return issues.value.filter(i => i.status === issueFilterStatus.value)
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

function formatDateTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

async function loadIssues() {
  issueLoading.value = true
  try {
    const res = await api.getIssues({ limit: 500, offset: 0 })
    issues.value = res.issues || []
    issueTotal.value = res.total || 0
  } catch (e) {
    console.error('Failed to load issues:', e)
  } finally {
    issueLoading.value = false
  }
}

function issuePrevPage() { issueOffset.value = Math.max(0, issueOffset.value - issueLimit) }
function issueNextPage() { if (issueOffset.value + issueLimit < issueTotal.value) issueOffset.value += issueLimit }

function viewIssue(issue) {
  viewingIssue.value = issue
  loadComments(issue.id)
}

function closeViewModal() {
  viewingIssue.value = null
  comments.value = []
  replyingTo.value = null
  replyBody.value = ''
}

async function loadComments(issueId) {
  commentsLoading.value = true
  try {
    const res = await api.getComments(issueId)
    comments.value = res.comments || []
  } catch (e) {
    console.error('Failed to load comments:', e)
  } finally {
    commentsLoading.value = false
  }
}

const topLevelComments = computed(() => comments.value.filter(c => !c.parent_id))

function getReplies(commentId) {
  return comments.value.filter(c => c.parent_id === commentId)
}

function startReply(commentId) {
  replyingTo.value = commentId
  replyBody.value = ''
}

async function submitComment() {
  if (!commentBody.value.trim() || !viewingIssue.value) return
  const author = commentAuthor.value.trim() || null
  if (author) localStorage.setItem('te_issue_author', author)
  try {
    await api.createComment({ issue_id: viewingIssue.value.id, author, body: commentBody.value.trim() })
    commentBody.value = ''
    await loadComments(viewingIssue.value.id)
    await loadIssues()
  } catch (e) { console.error('Failed to create comment:', e) }
}

async function submitReply(parentId) {
  if (!replyBody.value.trim() || !viewingIssue.value) return
  const author = commentAuthor.value.trim() || null
  if (author) localStorage.setItem('te_issue_author', author)
  try {
    await api.createComment({ issue_id: viewingIssue.value.id, parent_id: parentId, author, body: replyBody.value.trim() })
    replyBody.value = ''
    replyingTo.value = null
    await loadComments(viewingIssue.value.id)
    await loadIssues()
  } catch (e) { console.error('Failed to create reply:', e) }
}

async function deleteComment(commentId) {
  if (!viewingIssue.value) return
  try {
    await api.deleteComment(commentId)
    await loadComments(viewingIssue.value.id)
    await loadIssues()
  } catch (e) { console.error('Failed to delete comment:', e) }
}

function editIssue(issue) {
  form.value = { id: issue.id, title: issue.title, description: issue.description || '', status: issue.status, priority: issue.priority, author: issue.author || '' }
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
  if (!form.value.title.trim()) { formError.value = 'Title is required'; return }
  saving.value = true
  formError.value = ''
  const labels = labelsInput.value ? labelsInput.value.split(',').map(l => l.trim()).filter(Boolean) : []
  try {
    if (showEdit.value) {
      await api.updateIssue({ ...form.value, labels })
    } else {
      const author = form.value.author.trim()
      if (author) localStorage.setItem('te_issue_author', author)
      await api.createIssue({ ...form.value, labels })
    }
    closeModal()
    await loadIssues()
  } catch (e) { formError.value = e.message }
  finally { saving.value = false }
}

function deleteIssueConfirm(issue) { deleteTarget.value = issue }

async function confirmDelete() {
  deleting.value = true
  try {
    await api.deleteIssue(deleteTarget.value.id)
    deleteTarget.value = null
    await loadIssues()
  } catch (e) { console.error(e) }
  finally { deleting.value = false }
}

async function quickStatusChange(issue, newStatus) {
  try {
    await api.updateIssue({ id: issue.id, status: newStatus })
    issue.status = newStatus
    viewingIssue.value = { ...issue, status: newStatus }
    await loadIssues()
  } catch (e) { console.error(e) }
}

// ==================== ERROR REPORTS STATE ====================
const errReports = ref([])
const errTotal = ref(0)
const errLoading = ref(true)
const errFilterStatus = ref('')
const errFilterType = ref('')
const errOffset = ref(0)
const errLimit = ref(50)
const errNewCount = ref(0)

const errSelected = ref(null)
const errShowSubmit = ref(false)
const showClear = ref(false)
const errSubmitReport = ref(null)
const errSubmitting = ref(false)

const errSubmitForm = ref({ title: '', priority: 'high', labels: 'bug,auto-reported' })

const errStatusFilters = [
  { value: '', label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'submitted', label: 'Submitted' },
]

const errStatusCounts = ref({})

async function errFetchReports() {
  errLoading.value = true
  try {
    const params = { limit: errLimit.value, offset: errOffset.value }
    if (errFilterStatus.value) params.status = errFilterStatus.value
    if (errFilterType.value) params.session_type = errFilterType.value
    const data = await api.getReports(params)
    errReports.value = data.reports
    errTotal.value = data.total
  } catch (e) { console.error('Failed to fetch reports:', e) }
  errLoading.value = false
}

async function errFetchCounts() {
  try {
    const [allRes, newRes, reviewedRes, submittedRes] = await Promise.all([
      api.getReports({ limit: 0 }),
      api.getReports({ status: 'new', limit: 0 }),
      api.getReports({ status: 'reviewed', limit: 0 }),
      api.getReports({ status: 'submitted', limit: 0 }),
    ])
    errStatusCounts.value = { '': allRes.total, 'new': newRes.total, 'reviewed': reviewedRes.total, 'submitted': submittedRes.total }
    errNewCount.value = newRes.total
  } catch (e) { console.error('Failed to fetch report counts:', e) }
}

function errViewReport(report) { errSelected.value = report }

async function errDismissReport(report) {
  try {
    await api.dismissReport(report.id)
    report.status = 'reviewed'
    errFetchCounts()
  } catch (e) { console.error('Failed to dismiss:', e) }
}

async function errDismissAll() {
  try {
    await api.bulkDismissReports()
    errReports.value.forEach(r => { if (r.status === 'new') r.status = 'reviewed' })
    errFetchCounts()
  } catch (e) { console.error('Failed to dismiss all:', e) }
}

function errOpenSubmitModal(report) {
  errSubmitReport.value = report
  errSubmitForm.value = {
    title: `[${report.error_type || 'Error'}] ${report.message.slice(0, 100)}`,
    priority: 'high',
    labels: `bug,auto-reported,${report.session_type || 'system'}`,
  }
  errShowSubmit.value = true
}

async function errSubmitAsIssue() {
  if (!errSubmitReport.value) return
  errSubmitting.value = true
  try {
    const res = await api.submitReportAsIssue({
      id: errSubmitReport.value.id,
      title: errSubmitForm.value.title,
      priority: errSubmitForm.value.priority,
      labels: errSubmitForm.value.labels,
    })
    errSubmitReport.value.status = 'submitted'
    errSubmitReport.value.issue_id = res.issue?.id
    errShowSubmit.value = false
    errSelected.value = null
    errFetchCounts()
    loadIssues() // refresh issues list since we just created one
  } catch (e) { console.error('Failed to submit as issue:', e) }
  errSubmitting.value = false
}

async function errClearReports() {
  try {
    await api.clearReports()
    showClear.value = false
    errFetchReports()
    errFetchCounts()
  } catch (e) { console.error('Failed to clear reports:', e) }
}

function errGoToIssue() {
  errSelected.value = null
  activeTab.value = 'issues'
}

function errFormatDate(ts) {
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

function errStatusColor(status) {
  return { 'new': 'bg-red-400', 'reviewed': 'bg-yellow-400', 'submitted': 'bg-brand-400' }[status] || 'bg-surface-500'
}

function errSessionBadge(type) {
  return {
    'backtest': 'bg-blue-500/15 text-blue-400',
    'live': 'bg-green-500/15 text-green-400',
    'optimization': 'bg-purple-500/15 text-purple-400',
    'monte-carlo': 'bg-orange-500/15 text-orange-400',
    'system': 'bg-surface-700 text-surface-400',
  }[type] || 'bg-surface-700 text-surface-400'
}

function errPrevPage() { errOffset.value = Math.max(0, errOffset.value - errLimit.value) }
function errNextPage() { if (errOffset.value + errLimit.value < errTotal.value) errOffset.value += errLimit.value }

watch([errFilterStatus, errFilterType], () => { errOffset.value = 0; errFetchReports() })
watch(errOffset, errFetchReports)

// ==================== INIT ====================
onMounted(() => {
  loadIssues()
  errFetchReports()
  errFetchCounts()
  const saved = localStorage.getItem('te_issue_author')
  if (saved) { form.value.author = saved; commentAuthor.value = saved }
})
</script>
