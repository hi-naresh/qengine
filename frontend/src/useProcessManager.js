import { reactive, computed } from 'vue'

/**
 * Global process manager — tracks running background processes (backtest, MC, optimization)
 * so they can be displayed in a persistent bottom-right widget across all pages.
 *
 * Each process: { id, type, label, progress (0-100), eta, cancelFn, routePath, status, meta }
 * status: 'running' | 'completed' | 'error' | 'cancelled'
 */
const processes = reactive(new Map())

export function useProcessManager() {
  function register(id, { type, label, progress = 0, eta = 0, cancelFn = null, routePath = '/', meta = {} }) {
    processes.set(id, reactive({ id, type, label, progress, eta, cancelFn, routePath, status: 'running', meta }))
  }

  function update(id, fields) {
    const p = processes.get(id)
    if (!p) return
    Object.assign(p, fields)
  }

  function complete(id) {
    const p = processes.get(id)
    if (!p) return
    p.status = 'completed'
    p.progress = 100
  }

  function fail(id) {
    const p = processes.get(id)
    if (!p) return
    p.status = 'error'
  }

  function cancel(id) {
    const p = processes.get(id)
    if (!p) return
    p.status = 'cancelled'
  }

  function remove(id) {
    processes.delete(id)
  }

  function get(id) {
    return processes.get(id)
  }

  const list = computed(() => Array.from(processes.values()))
  const running = computed(() => list.value.filter(p => p.status === 'running'))
  const finished = computed(() => list.value.filter(p => p.status !== 'running'))

  return { processes, register, update, complete, fail, cancel, remove, get, list, running, finished }
}
