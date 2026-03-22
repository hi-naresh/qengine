import { ref, onUnmounted } from 'vue'
import { useToast } from './useToast'

/**
 * Composable for QEngine WebSocket connection.
 * Connects to /ws?token=... and dispatches real-time events.
 */

let sharedWs = null
let listeners = new Set()
let reconnectTimer = null
let reconnectAttempts = 0
let connectionErrorShown = false

/**
 * Decompress gzipped + base64-encoded data from backend.
 */
async function decompressData(base64Str) {
  const binaryStr = atob(base64Str)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i)
  }
  if (typeof DecompressionStream !== 'undefined') {
    const ds = new DecompressionStream('gzip')
    const writer = ds.writable.getWriter()
    writer.write(bytes)
    writer.close()
    const reader = ds.readable.getReader()
    const chunks = []
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
    }
    const totalLen = chunks.reduce((acc, c) => acc + c.length, 0)
    const result = new Uint8Array(totalLen)
    let offset = 0
    for (const chunk of chunks) {
      result.set(chunk, offset)
      offset += chunk.length
    }
    const text = new TextDecoder().decode(result)
    return JSON.parse(text)
  }
  throw new Error('DecompressionStream not available')
}

export const wsConnected = ref(false)

function getToken() {
  return localStorage.getItem('te_token') || ''
}

function connect() {
  if (sharedWs && (sharedWs.readyState === WebSocket.OPEN || sharedWs.readyState === WebSocket.CONNECTING)) {
    return
  }

  const token = getToken()
  if (!token) return

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/ws?token=${token}`

  try {
    sharedWs = new WebSocket(url)
  } catch (e) {
    console.warn('[WS] Failed to create WebSocket:', e.message)
    scheduleReconnect()
    return
  }

  sharedWs.onopen = () => {
    wsConnected.value = true
    reconnectAttempts = 0
    if (connectionErrorShown) {
      connectionErrorShown = false
      const { success } = useToast()
      success('Backend connection restored')
    }
  }

  sharedWs.onmessage = async (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      if (msg.event === 'ping') {
        sharedWs.send(JSON.stringify({ type: 'pong' }))
        return
      }
      if (msg.is_compressed && msg.data && typeof msg.data === 'string') {
        try {
          msg.data = await decompressData(msg.data)
          msg.is_compressed = false
        } catch (e) {
          console.warn('[WS] Failed to decompress message:', e)
        }
      }
      for (const cb of listeners) {
        cb(msg)
      }
    } catch {
      // ignore parse errors
    }
  }

  sharedWs.onclose = (evt) => {
    wsConnected.value = false
    sharedWs = null
    if (listeners.size > 0) {
      scheduleReconnect()
    }
  }

  sharedWs.onerror = (evt) => {
    // Show toast only once per disconnect cycle, not on every retry
    if (!connectionErrorShown && reconnectAttempts === 0) {
      connectionErrorShown = true
      const { warning } = useToast()
      warning('Backend server not reachable. Retrying...')
    }
    console.warn('[WS] Connection error (attempt ' + (reconnectAttempts + 1) + ')')
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer)
  reconnectAttempts++
  // Exponential backoff: 2s, 4s, 8s, 16s, max 30s
  const delay = Math.min(2000 * Math.pow(2, reconnectAttempts - 1), 30000)
  reconnectTimer = setTimeout(connect, delay)
}

function disconnect() {
  if (listeners.size === 0 && sharedWs) {
    clearTimeout(reconnectTimer)
    sharedWs.close()
    sharedWs = null
    wsConnected.value = false
  }
}

/**
 * useWebSocket composable.
 * @param {Function} handler - callback receiving { event, id, data, is_compressed }
 */
export function useWebSocket(handler) {
  listeners.add(handler)
  connect()

  onUnmounted(() => {
    listeners.delete(handler)
    disconnect()
  })

  return { connected: wsConnected }
}
