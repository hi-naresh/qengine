<template>
  <div v-show="hasData" ref="wrapperEl" class="card" :class="expanded ? 'fixed inset-0 z-50 m-0 rounded-none overflow-auto bg-surface-900' : ''">
    <!-- Tab bar + toolbar -->
    <div class="flex items-center gap-1 border-b border-surface-700 mb-2 -mt-1 overflow-x-auto">
      <button v-for="tab in chartTabs" :key="tab.id" @click="activeTab = tab.id"
        class="px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors"
        :class="activeTab === tab.id ? 'border-brand-500 text-brand-400' : 'border-transparent text-surface-500 hover:text-surface-300'">
        {{ tab.label }}
      </button>
      <div class="ml-auto flex items-center gap-1 pr-1">
        <!-- Timeframe selector (candle tab only) -->
        <div v-if="activeTab === 'candles' && availableTimeframes.length > 1" class="flex items-center gap-0.5 mr-1">
          <button v-for="tf in availableTimeframes" :key="tf.value" @click="switchTimeframe(tf.value)"
            class="px-1.5 py-1 text-[10px] font-medium rounded transition-colors"
            :class="selectedTimeframe === tf.value
              ? 'bg-brand-600 text-white'
              : 'text-surface-400 hover:text-white hover:bg-surface-700'"
            :title="tf.label">
            {{ tf.value }}
          </button>
        </div>
        <div v-if="activeTab === 'candles' && availableTimeframes.length > 1" class="w-px h-4 bg-surface-700 mx-0.5"></div>
        <button @click="fitContent" class="p-2 sm:p-1.5 rounded text-surface-400 hover:text-white hover:bg-surface-700 transition-colors" title="Fit content">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg>
        </button>
        <button @click="zoomIn" class="p-2 sm:p-1.5 rounded text-surface-400 hover:text-white hover:bg-surface-700 transition-colors" title="Zoom in">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7"/></svg>
        </button>
        <button @click="zoomOut" class="p-2 sm:p-1.5 rounded text-surface-400 hover:text-white hover:bg-surface-700 transition-colors" title="Zoom out">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7"/></svg>
        </button>
        <button @click="autoScale" class="p-2 sm:p-1.5 rounded text-surface-400 hover:text-white hover:bg-surface-700 transition-colors" title="Auto scale price">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"/></svg>
        </button>
        <div class="w-px h-4 bg-surface-700 mx-0.5"></div>
        <button @click="toggleExpand" class="p-2 sm:p-1.5 rounded text-surface-400 hover:text-white hover:bg-surface-700 transition-colors" :title="expanded ? 'Exit fullscreen' : 'Expand chart'">
          <svg v-if="!expanded" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"/></svg>
        </button>
      </div>
    </div>
    <!-- Loading overlay for session lines -->
    <div v-if="activeTab === 'candles' && drawingProgress.total > 0 && drawingProgress.done < drawingProgress.total"
      class="flex items-center gap-2 px-3 py-1.5 text-xs text-surface-400">
      <svg class="animate-spin h-3.5 w-3.5 text-brand-400" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
      <span>Drawing sessions {{ drawingProgress.done }}/{{ drawingProgress.total }}...</span>
    </div>
    <div v-show="activeTab === 'candles'" ref="candleChartEl" class="w-full rounded" :class="expanded ? 'h-[calc(100vh-60px)]' : candleHeight"></div>
    <div v-show="activeTab === 'equity'" ref="equityChartEl" class="w-full rounded" :class="expanded ? 'h-[calc(100vh-60px)]' : equityHeight"></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { createChart, ColorType, CrosshairMode, LineStyle, CandlestickSeries, AreaSeries, BaselineSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts'

const props = defineProps({
  candles: { type: Array, default: () => [] },
  rawCandles: { type: Array, default: () => [] },
  routeTimeframe: { type: String, default: '1h' },
  orders: { type: Array, default: () => [] },
  trades: { type: Array, default: () => [] },
  equityCurve: { type: Array, default: () => [] },
  balance: { type: Number, default: 10000 },
  candleHeight: { type: String, default: 'h-[300px] sm:h-[450px]' },
  equityHeight: { type: String, default: 'h-[220px] sm:h-[300px]' },
  pricePrecision: { type: Number, default: 5 },
  priceMinMove: { type: Number, default: 0.00001 },
})

const wrapperEl = ref(null)
const candleChartEl = ref(null)
const equityChartEl = ref(null)
const expanded = ref(false)
const activeTab = ref('candles')
const selectedTimeframe = ref('')

let tvChart = null
let tvCandleSeries = null
let tvMarkers = []
let tvEquityChart = null
let tvEquitySeries = null
let candleRo = null
let equityRo = null
let drawAbortController = null  // to cancel progressive drawing on timeframe switch

const drawingProgress = ref({ done: 0, total: 0 })

// ── Timeframe constants ──
const TF_MINUTES = {
  '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30, '45m': 45,
  '1h': 60, '2h': 120, '3h': 180, '4h': 240, '6h': 360, '8h': 480,
  '12h': 720, '1D': 1440, '3D': 4320, '1W': 10080,
}

const ALL_TIMEFRAMES = ['1m','5m','15m','30m','1h','4h','1D','1W']

const hasData = computed(() => props.candles.length > 0 || props.equityCurve.length > 0)

const has1mData = computed(() => props.rawCandles.length > 0)

const availableTimeframes = computed(() => {
  const sourceCandles = has1mData.value ? props.rawCandles : props.candles
  if (!sourceCandles.length) return []

  const totalMinutes = sourceCandles.length * (has1mData.value ? 1 : (TF_MINUTES[props.routeTimeframe] || 1))
  const minCandles = 8

  const tfs = []
  for (const tf of ALL_TIMEFRAMES) {
    const mins = TF_MINUTES[tf]
    if (!has1mData.value && mins < (TF_MINUTES[props.routeTimeframe] || 1)) continue
    if (totalMinutes / mins >= minCandles) {
      tfs.push({ value: tf, label: tf, minutes: mins })
    }
  }
  return tfs
})

const chartTabs = computed(() => {
  const tabs = [{ id: 'candles', label: 'Candle Chart' }]
  if (props.equityCurve.length || props.trades.length) tabs.push({ id: 'equity', label: 'Equity Curve' })
  return tabs
})

const _priceFmt = computed(() => ({
  type: 'price',
  precision: props.pricePrecision,
  minMove: props.priceMinMove,
}))

// ── Candle aggregation ──
function aggregateCandles(candles1m, tfMinutes) {
  if (tfMinutes <= 1) return candles1m
  const bucketSeconds = tfMinutes * 60
  const result = []
  let currentBucket = null
  let current = null

  for (const c of candles1m) {
    const bucket = Math.floor(c.time / bucketSeconds) * bucketSeconds
    if (bucket !== currentBucket) {
      if (current) result.push(current)
      currentBucket = bucket
      current = { time: bucket, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume || 0 }
    } else {
      current.high = Math.max(current.high, c.high)
      current.low = Math.min(current.low, c.low)
      current.close = c.close
      current.volume += (c.volume || 0)
    }
  }
  if (current) result.push(current)
  return result
}

function getCandlesForTimeframe(tf) {
  const tfMinutes = TF_MINUTES[tf] || 1
  const routeMinutes = TF_MINUTES[props.routeTimeframe] || 1

  if (has1mData.value) {
    return aggregateCandles(props.rawCandles, tfMinutes)
  }
  if (tf === props.routeTimeframe) {
    return props.candles
  }
  if (tfMinutes >= routeMinutes) {
    return aggregateCandles(props.candles, tfMinutes / routeMinutes)
  }
  return props.candles
}

function switchTimeframe(tf) {
  if (tf === selectedTimeframe.value) return
  selectedTimeframe.value = tf
  renderCandles()
}

// ── Public API (exposed to parent) ──
function renderCandles() {
  if (!candleChartEl.value) return

  if (!selectedTimeframe.value) {
    selectedTimeframe.value = props.routeTimeframe || '1h'
  }

  const candleData = getCandlesForTimeframe(selectedTimeframe.value)
  if (!candleData.length) return

  destroyCandleChart()

  tvChart = createChart(candleChartEl.value, {
    width: candleChartEl.value.clientWidth,
    height: candleChartEl.value.clientHeight || 450,
    layout: {
      background: { type: ColorType.Solid, color: '#12131a' },
      textColor: '#888',
      fontSize: 11,
    },
    grid: {
      vertLines: { color: '#1e2030' },
      horzLines: { color: '#1e2030' },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#2a2d3a' },
    timeScale: {
      borderColor: '#2a2d3a',
      timeVisible: true,
      secondsVisible: false,
    },
  })

  tvCandleSeries = tvChart.addSeries(CandlestickSeries, {
    upColor: '#22c55e',
    downColor: '#ef4444',
    borderUpColor: '#22c55e',
    borderDownColor: '#ef4444',
    wickUpColor: '#22c55e',
    wickDownColor: '#ef4444',
    priceFormat: _priceFmt.value,
    lastValueVisible: false,
    priceLineVisible: false,
  })

  tvCandleSeries.setData(candleData.map(c => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })))

  // Draw session visualizations from trades, or fallback to order markers
  tvMarkers = []
  if (props.trades.length) {
    addTradeLines(props.trades)
  } else if (props.orders.length) {
    const allMarkers = []
    for (const o of props.orders) {
      if (o.time) {
        allMarkers.push({
          time: o.time,
          position: o.position || 'belowBar',
          color: o.color || '#2196F3',
          shape: o.shape || 'arrowUp',
          text: o.text || '',
        })
      }
    }
    if (allMarkers.length) {
      allMarkers.sort((a, b) => a.time - b.time)
      createSeriesMarkers(tvCandleSeries, allMarkers)
      tvMarkers = allMarkers
    }
  }

  tvChart.timeScale().fitContent()

  candleRo = new ResizeObserver(() => {
    if (tvChart && candleChartEl.value) {
      tvChart.applyOptions({ width: candleChartEl.value.clientWidth })
    }
  })
  candleRo.observe(candleChartEl.value)
}

function renderEquity() {
  if (!equityChartEl.value) return

  let seriesData = []
  const data = props.equityCurve
  if (data && data.length && data[0] && typeof data[0] === 'object' && data[0].data) {
    seriesData = data[0].data
      .filter(p => p.time)
      .map(p => ({ time: Math.floor(p.time), value: p.value ?? 0 }))
  } else if (data && data.length && typeof data[0] === 'number') {
    seriesData = data.map((v, i) => ({ time: i, value: v }))
  }

  // Build from trades if backend equity is empty
  if (seriesData.length < 2 && props.trades.length) {
    const bal = props.balance || 10000
    const points = [{ time: 0, value: bal }]
    let cumPnl = 0
    for (const t of props.trades) {
      cumPnl += (t.pnl || t.PNL || 0)
      const ts = t.closed_at ? Math.floor(t.closed_at / 1000) : points.length
      points.push({ time: ts, value: bal + cumPnl })
    }
    seriesData = points
  }

  if (seriesData.length < 2) return

  destroyEquityChart()

  tvEquityChart = createChart(equityChartEl.value, {
    width: equityChartEl.value.clientWidth,
    height: equityChartEl.value.clientHeight || 300,
    layout: {
      background: { type: ColorType.Solid, color: '#12131a' },
      textColor: '#888',
      fontSize: 11,
    },
    grid: {
      vertLines: { color: '#1e2030' },
      horzLines: { color: '#1e2030' },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#2a2d3a' },
    timeScale: {
      borderColor: '#2a2d3a',
      timeVisible: true,
      secondsVisible: false,
    },
  })

  const firstVal = seriesData[0].value
  const lastVal = seriesData[seriesData.length - 1].value
  const lineColor = lastVal >= firstVal ? '#4ade80' : '#f87171'
  tvEquitySeries = tvEquityChart.addSeries(AreaSeries, {
    lineColor,
    topColor: lineColor + '40',
    bottomColor: lineColor + '05',
    lineWidth: 2,
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  })

  tvEquitySeries.setData(seriesData)
  tvEquityChart.timeScale().fitContent()

  equityRo = new ResizeObserver(() => {
    if (tvEquityChart && equityChartEl.value) {
      tvEquityChart.applyOptions({ width: equityChartEl.value.clientWidth })
    }
  })
  equityRo.observe(equityChartEl.value)
}

// ── Session / Trade visualization (progressive, non-blocking) ──
// How many sessions to draw per animation frame batch
const BATCH_SIZE = 5

function addTradeLines(trades) {
  if (!tvChart || !tvCandleSeries) return

  const sessions = {}
  const noSessionTrades = []
  for (const t of trades) {
    const sn = t.meta?.session
    if (sn == null) { noSessionTrades.push(t); continue }
    if (!sessions[sn]) sessions[sn] = { trades: [], tMin: Infinity, tMax: 0, outcome: null }
    const s = sessions[sn]
    s.trades.push(t)
    if (t.opened_at) s.tMin = Math.min(s.tMin, t.opened_at)
    if (t.closed_at) s.tMax = Math.max(s.tMax, t.closed_at)
    if (t.meta?.exit_reason) s.outcome = t.meta.exit_reason
  }

  const sessionKeys = Object.keys(sessions).sort((a, b) => a - b)
  const totalWork = sessionKeys.length + noSessionTrades.length

  // For small workloads, draw synchronously (no flicker)
  if (totalWork <= 30) {
    const allMarkers = []
    for (const sn of sessionKeys) _drawSession(sessions[sn], sn, allMarkers)
    for (const t of noSessionTrades) _drawSimpleTrade(t, allMarkers)
    if (allMarkers.length) {
      allMarkers.sort((a, b) => a.time - b.time)
      createSeriesMarkers(tvCandleSeries, allMarkers)
      tvMarkers = allMarkers
    }
    drawingProgress.value = { done: 0, total: 0 }
    return
  }

  // Progressive drawing: yield to browser between batches
  if (drawAbortController) drawAbortController.abort()
  drawAbortController = new AbortController()
  const signal = drawAbortController.signal

  drawingProgress.value = { done: 0, total: sessionKeys.length }
  const allMarkers = []

  // Collect all markers for non-session trades first (lightweight)
  for (const t of noSessionTrades) _drawSimpleTrade(t, allMarkers)

  let idx = 0
  function drawBatch() {
    if (signal.aborted || !tvChart || !tvCandleSeries) {
      drawingProgress.value = { done: 0, total: 0 }
      return
    }
    const end = Math.min(idx + BATCH_SIZE, sessionKeys.length)
    for (let i = idx; i < end; i++) {
      _drawSession(sessions[sessionKeys[i]], sessionKeys[i], allMarkers)
    }
    idx = end
    drawingProgress.value = { done: idx, total: sessionKeys.length }

    if (idx < sessionKeys.length) {
      requestAnimationFrame(drawBatch)
    } else {
      // All done — apply markers once
      if (allMarkers.length && tvCandleSeries) {
        allMarkers.sort((a, b) => a.time - b.time)
        createSeriesMarkers(tvCandleSeries, allMarkers)
        tvMarkers = allMarkers
      }
      drawingProgress.value = { done: 0, total: 0 }
      drawAbortController = null
    }
  }

  requestAnimationFrame(drawBatch)
}

function _addLine(tOpen, tClose, price, color, label, style = LineStyle.Dashed, width = 1) {
  if (!price || !tOpen || !tClose) return
  const s = tvChart.addSeries(LineSeries, {
    color, lineWidth: width, lineStyle: style,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    title: label, priceFormat: _priceFmt.value,
  })
  s.setData([{ time: tOpen, value: price }, { time: tClose, value: price }])
}

function _drawSession(session, sessionNum, markers) {
  const { trades, tMin, tMax, outcome } = session
  if (!trades.length || tMin === Infinity || tMax === 0) return

  const tOpen = Math.floor(tMin / 1000)
  const tClose = Math.floor(tMax / 1000)
  const isWin = outcome === 'tp_hit'
  const zoneR = isWin ? '34, 197, 94' : '239, 68, 68'

  const firstTrade = trades[0]
  const refPrice = firstTrade.meta?.session_open_price || firstTrade.entry_price

  // TP_UPPER / TP_LOWER bounds
  let tpUpper = -Infinity, tpLower = Infinity
  for (const t of trades) {
    const tp = t.meta?.tp_price
    if (tp) { tpUpper = Math.max(tpUpper, tp); tpLower = Math.min(tpLower, tp) }
  }
  if (tpUpper === -Infinity || tpLower === Infinity) {
    for (const t of trades) {
      if (t.entry_price) { tpUpper = Math.max(tpUpper, t.entry_price); tpLower = Math.min(tpLower, t.entry_price) }
    }
  }
  if (tpUpper === -Infinity || tpLower === Infinity) return

  // 1. Bounded session zone (BaselineSeries)
  const zone = tvChart.addSeries(BaselineSeries, {
    baseValue: { type: 'price', price: tpLower },
    topLineColor: `rgba(${zoneR}, 0.4)`,
    topFillColor1: `rgba(${zoneR}, 0.12)`,
    topFillColor2: `rgba(${zoneR}, 0.04)`,
    bottomLineColor: `rgba(${zoneR}, 0.4)`,
    bottomFillColor1: `rgba(${zoneR}, 0.04)`,
    bottomFillColor2: `rgba(${zoneR}, 0.12)`,
    lineWidth: 1,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    priceFormat: _priceFmt.value,
  })
  zone.setData([{ time: tOpen, value: tpUpper }, { time: tClose, value: tpUpper }])

  // 2. S#N session reference line (teal solid)
  _addLine(tOpen, tClose, refPrice, '#14b8a6', `S#${sessionNum}`, LineStyle.Solid)

  // 3. BUY and SELL lines
  let buyPrice = null, sellPrice = null
  for (const t of trades) {
    if (t.type === 'long' && !buyPrice) buyPrice = t.entry_price
    if (t.type === 'short' && !sellPrice) sellPrice = t.entry_price
  }
  if (buyPrice) _addLine(tOpen, tClose, buyPrice, '#2196F3', 'BUY', LineStyle.Solid)
  if (sellPrice) _addLine(tOpen, tClose, sellPrice, '#f97316', 'SELL', LineStyle.Solid)

  // 4. ALL order markers
  for (const t of trades) {
    if (!t.opened_at || !t.entry_price) continue
    const isBuy = t.type === 'long'
    const oNum = t.meta?.order_in_session || '?'
    markers.push({
      time: Math.floor(t.opened_at / 1000) - 60,
      position: isBuy ? 'belowBar' : 'aboveBar',
      color: isBuy ? '#2196F3' : '#f97316',
      shape: isBuy ? 'arrowUp' : 'arrowDown',
      text: `S#${sessionNum} O#${oNum}`,
    })
  }

  // 5. Event marker at session close
  const lastTrade = trades[trades.length - 1]
  if (lastTrade.meta?.exit_reason && lastTrade.closed_at) {
    const reason = lastTrade.meta.exit_reason
    const isBuy = lastTrade.type === 'long'
    markers.push({
      time: Math.floor(lastTrade.closed_at / 1000) - 60,
      position: isBuy ? 'aboveBar' : 'belowBar',
      color: reason === 'tp_hit' ? '#22c55e' : '#f97316',
      shape: 'circle',
      text: reason,
    })
  }
}

function _drawSimpleTrade(trade, markers) {
  if (!trade.opened_at || !trade.closed_at || !trade.entry_price) return
  const to = Math.floor(trade.opened_at / 1000) - 60
  const tc = Math.floor(trade.closed_at / 1000) - 60
  const isBuy = trade.type === 'long'
  _addLine(to, tc, trade.entry_price, isBuy ? '#2196F3' : '#f97316', isBuy ? 'BUY' : 'SELL', LineStyle.Dashed)
  if (trade.exit_price) {
    _addLine(to, tc, trade.exit_price, (trade.pnl || 0) >= 0 ? '#22c55e' : '#ef4444', 'EXIT', LineStyle.Dotted)
  }
  markers.push({
    time: to, position: isBuy ? 'belowBar' : 'aboveBar',
    color: isBuy ? '#2196F3' : '#f97316', shape: isBuy ? 'arrowUp' : 'arrowDown',
    text: isBuy ? 'BUY' : 'SELL',
  })
}

// ── Toolbar ──
function fitContent() {
  const chart = activeTab.value === 'equity' ? tvEquityChart : tvChart
  if (chart) chart.timeScale().fitContent()
}

function zoomIn() {
  const chart = activeTab.value === 'equity' ? tvEquityChart : tvChart
  if (!chart) return
  const ts = chart.timeScale()
  const range = ts.getVisibleLogicalRange()
  if (range) {
    const mid = (range.from + range.to) / 2
    const span = (range.to - range.from) * 0.35
    ts.setVisibleLogicalRange({ from: mid - span, to: mid + span })
  }
}

function zoomOut() {
  const chart = activeTab.value === 'equity' ? tvEquityChart : tvChart
  if (!chart) return
  const ts = chart.timeScale()
  const range = ts.getVisibleLogicalRange()
  if (range) {
    const mid = (range.from + range.to) / 2
    const span = (range.to - range.from) * 0.75
    ts.setVisibleLogicalRange({ from: mid - span, to: mid + span })
  }
}

function autoScale() {
  const chart = activeTab.value === 'equity' ? tvEquityChart : tvChart
  if (chart) chart.priceScale('right').applyOptions({ autoScale: true })
}

function toggleExpand() {
  expanded.value = !expanded.value
  nextTick(() => {
    if (tvChart && candleChartEl.value) {
      tvChart.applyOptions({ width: candleChartEl.value.clientWidth, height: candleChartEl.value.clientHeight })
      tvChart.timeScale().fitContent()
    }
    if (tvEquityChart && equityChartEl.value) {
      tvEquityChart.applyOptions({ width: equityChartEl.value.clientWidth, height: equityChartEl.value.clientHeight })
    }
  })
}

// ── Cleanup ──
function destroyCandleChart() {
  if (drawAbortController) { drawAbortController.abort(); drawAbortController = null }
  drawingProgress.value = { done: 0, total: 0 }
  if (candleRo) { candleRo.disconnect(); candleRo = null }
  if (tvChart) { tvChart.remove(); tvChart = null; tvCandleSeries = null; tvMarkers = [] }
}

function destroyEquityChart() {
  if (equityRo) { equityRo.disconnect(); equityRo = null }
  if (tvEquityChart) { tvEquityChart.remove(); tvEquityChart = null; tvEquitySeries = null }
}

function destroy() {
  destroyCandleChart()
  destroyEquityChart()
  selectedTimeframe.value = ''
}

function _handleEsc(e) {
  if (e.key === 'Escape' && expanded.value) {
    expanded.value = false
    nextTick(() => {
      if (tvChart && candleChartEl.value) {
        tvChart.applyOptions({ width: candleChartEl.value.clientWidth, height: candleChartEl.value.clientHeight })
      }
    })
  }
}

onMounted(() => {
  document.addEventListener('keydown', _handleEsc)
})

onBeforeUnmount(() => {
  destroy()
  document.removeEventListener('keydown', _handleEsc)
})

// Expose methods for parent to call
defineExpose({
  renderCandles,
  renderEquity,
  destroy,
  fitContent,
})
</script>
