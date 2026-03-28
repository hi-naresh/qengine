<template>
  <div>
    <div class="flex items-center gap-3 mb-4">
      <button @click="$emit('close')" class="btn-sm bg-surface-800 text-surface-400 hover:text-surface-200">
        <svg class="w-4 h-4 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"/></svg>
        Back
      </button>
      <h2 class="text-lg font-semibold text-surface-100">Strategy Development Guide</h2>
    </div>

    <!-- Sub-tabs -->
    <div class="flex items-center gap-1 border-b border-surface-700 mb-4 overflow-x-auto">
      <button v-for="tab in tabs" :key="tab.id" @click="activeTab = tab.id"
        class="px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors"
        :class="activeTab === tab.id ? 'border-brand-500 text-brand-400' : 'border-transparent text-surface-500 hover:text-surface-300'">
        {{ tab.label }}
      </button>
    </div>

    <!-- TAB: Quick Start -->
    <div v-if="activeTab === 'quickstart'" class="space-y-4">
      <div class="card">
        <p class="text-xs text-surface-400 mb-3">Every strategy is a Python class that extends <code class="text-brand-400">Strategy</code>. Create one via the <span class="text-brand-400">New Strategy</span> button or <span class="text-brand-400">AI Generate</span>. Each strategy lives in <code class="text-surface-300">strategies/YourName/__init__.py</code>.</p>
        <div class="bg-surface-900 rounded-lg p-4 overflow-x-auto">
          <pre class="text-xs font-mono text-surface-300 whitespace-pre"><span class="text-surface-500"># strategies/ExampleStrategy/__init__.py</span>
<span class="text-purple-400">import</span> qengine.indicators <span class="text-purple-400">as</span> ta
<span class="text-purple-400">from</span> qengine.strategies <span class="text-purple-400">import</span> Strategy

<span class="text-purple-400">class</span> <span class="text-yellow-300">ExampleStrategy</span>(Strategy):
    <span class="text-surface-500">"""EMA crossover strategy with session filtering and ATR-based stops."""</span>

    <span class="text-purple-400">def</span> <span class="text-blue-300">hyperparameters</span>(self):
        <span class="text-purple-400">return</span> [
            {<span class="text-green-400">'name'</span>: <span class="text-green-400">'fast_ema'</span>,  <span class="text-green-400">'type'</span>: int,   <span class="text-green-400">'min'</span>: 5,   <span class="text-green-400">'max'</span>: 20,  <span class="text-green-400">'default'</span>: 8},
            {<span class="text-green-400">'name'</span>: <span class="text-green-400">'slow_ema'</span>,  <span class="text-green-400">'type'</span>: int,   <span class="text-green-400">'min'</span>: 15,  <span class="text-green-400">'max'</span>: 50,  <span class="text-green-400">'default'</span>: 21},
            {<span class="text-green-400">'name'</span>: <span class="text-green-400">'risk_pct'</span>,  <span class="text-green-400">'type'</span>: float, <span class="text-green-400">'min'</span>: 0.5, <span class="text-green-400">'max'</span>: 3.0, <span class="text-green-400">'default'</span>: 1.0},
            {<span class="text-green-400">'name'</span>: <span class="text-green-400">'stop_pips'</span>, <span class="text-green-400">'type'</span>: int,   <span class="text-green-400">'min'</span>: 20,  <span class="text-green-400">'max'</span>: 80,  <span class="text-green-400">'default'</span>: 40},
            {<span class="text-green-400">'name'</span>: <span class="text-green-400">'rr_ratio'</span>,  <span class="text-green-400">'type'</span>: float, <span class="text-green-400">'min'</span>: 1.0, <span class="text-green-400">'max'</span>: 4.0, <span class="text-green-400">'default'</span>: 2.0},
        ]

    <span class="text-purple-400">def</span> <span class="text-blue-300">before</span>(self):
        <span class="text-surface-500"># Runs before each candle's logic - compute indicators here</span>
        self.fast = ta.ema(self.candles, self.hp.get(<span class="text-green-400">'fast_ema'</span>, 8))
        self.slow = ta.ema(self.candles, self.hp.get(<span class="text-green-400">'slow_ema'</span>, 21))

    <span class="text-purple-400">def</span> <span class="text-blue-300">should_long</span>(self) -> bool:
        <span class="text-surface-500"># Only trade during active sessions</span>
        <span class="text-purple-400">if</span> self.session <span class="text-purple-400">not in</span> (<span class="text-green-400">'london'</span>, <span class="text-green-400">'new_york'</span>, <span class="text-green-400">'overlap'</span>):
            <span class="text-purple-400">return</span> False
        <span class="text-purple-400">return</span> self.fast > self.slow <span class="text-purple-400">and</span> self.price > self.fast

    <span class="text-purple-400">def</span> <span class="text-blue-300">go_long</span>(self):
        stop_pips = self.hp.get(<span class="text-green-400">'stop_pips'</span>, 40)
        rr = self.hp.get(<span class="text-green-400">'rr_ratio'</span>, 2.0)
        qty = self.lot_size_for_risk(self.hp.get(<span class="text-green-400">'risk_pct'</span>, 1.0), stop_pips)

        self.buy = qty, self.price
        self.stop_loss = qty, self.price - self.pips_to_price(stop_pips)
        self.take_profit = qty, self.price + self.pips_to_price(stop_pips * rr)

    <span class="text-purple-400">def</span> <span class="text-blue-300">should_short</span>(self) -> bool:
        <span class="text-purple-400">if</span> self.session <span class="text-purple-400">not in</span> (<span class="text-green-400">'london'</span>, <span class="text-green-400">'new_york'</span>, <span class="text-green-400">'overlap'</span>):
            <span class="text-purple-400">return</span> False
        <span class="text-purple-400">return</span> self.fast &lt; self.slow <span class="text-purple-400">and</span> self.price &lt; self.fast

    <span class="text-purple-400">def</span> <span class="text-blue-300">go_short</span>(self):
        stop_pips = self.hp.get(<span class="text-green-400">'stop_pips'</span>, 40)
        rr = self.hp.get(<span class="text-green-400">'rr_ratio'</span>, 2.0)
        qty = self.lot_size_for_risk(self.hp.get(<span class="text-green-400">'risk_pct'</span>, 1.0), stop_pips)

        self.sell = qty, self.price
        self.stop_loss = qty, self.price + self.pips_to_price(stop_pips)
        self.take_profit = qty, self.price - self.pips_to_price(stop_pips * rr)

    <span class="text-purple-400">def</span> <span class="text-blue-300">should_cancel_entry</span>(self) -> bool:
        <span class="text-surface-500"># Cancel pending entries before weekend</span>
        <span class="text-purple-400">if</span> self.minutes_to_close <span class="text-purple-400">is not</span> None <span class="text-purple-400">and</span> self.minutes_to_close &lt; 60:
            <span class="text-purple-400">return</span> True
        <span class="text-purple-400">return</span> False

    <span class="text-purple-400">def</span> <span class="text-blue-300">filters</span>(self):
        <span class="text-surface-500"># Additional entry conditions (all must pass)</span>
        <span class="text-purple-400">return</span> [self.filter_atr_above_minimum]

    <span class="text-purple-400">def</span> <span class="text-blue-300">filter_atr_above_minimum</span>(self):
        <span class="text-purple-400">return</span> ta.atr(self.candles, 14) > self.pips_to_price(5)</pre>
        </div>
      </div>
    </div>

    <!-- TAB: Methods & Orders -->
    <div v-if="activeTab === 'methods'" class="space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="card">
          <h3 class="text-sm font-semibold text-surface-200 mb-3 flex items-center gap-2">
            <span class="w-5 h-5 rounded bg-red-600 flex items-center justify-center text-[10px] font-bold text-white">!</span>
            Required Methods
          </h3>
          <div class="space-y-2">
            <div class="p-2 bg-surface-800/50 rounded">
              <code class="text-xs text-red-400 font-mono">should_long(self) -> bool</code>
              <p class="text-[11px] text-surface-500 mt-0.5">Return True when conditions are met to open a long position</p>
            </div>
            <div class="p-2 bg-surface-800/50 rounded">
              <code class="text-xs text-red-400 font-mono">go_long(self)</code>
              <p class="text-[11px] text-surface-500 mt-0.5">Set <code class="text-surface-400">self.buy</code>, <code class="text-surface-400">self.stop_loss</code>, <code class="text-surface-400">self.take_profit</code> as <code class="text-surface-400">(qty, price)</code> tuples</p>
            </div>
          </div>
        </div>
        <div class="card">
          <h3 class="text-sm font-semibold text-surface-200 mb-3 flex items-center gap-2">
            <span class="w-5 h-5 rounded bg-surface-600 flex items-center justify-center text-[10px] font-bold text-white">~</span>
            Optional Methods
          </h3>
          <div class="space-y-1.5">
            <div v-for="m in optionalMethods" :key="m.name" class="p-1.5 bg-surface-800/50 rounded">
              <code class="text-[11px] text-blue-400 font-mono">{{ m.name }}</code>
              <p class="text-[10px] text-surface-500 mt-0.5">{{ m.desc }}</p>
            </div>
          </div>
        </div>
      </div>
      <!-- Order Formats -->
      <div class="card">
        <h3 class="text-sm font-semibold text-surface-200 mb-3">Order Submission Format</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div class="p-3 bg-surface-800/50 rounded">
            <h4 class="text-xs font-semibold text-surface-300 mb-1.5">Market Order</h4>
            <pre class="text-[11px] font-mono text-surface-400">self.buy = qty, self.price
self.stop_loss = qty, stop_price
self.take_profit = qty, tp_price</pre>
          </div>
          <div class="p-3 bg-surface-800/50 rounded">
            <h4 class="text-xs font-semibold text-surface-300 mb-1.5">Limit / Stop Order</h4>
            <pre class="text-[11px] font-mono text-surface-400"><span class="text-surface-500"># Limit buy below current price</span>
self.buy = qty, limit_price
<span class="text-surface-500"># Stop buy above current price</span>
self.buy = qty, stop_price</pre>
          </div>
          <div class="p-3 bg-surface-800/50 rounded">
            <h4 class="text-xs font-semibold text-surface-300 mb-1.5">Multiple Orders</h4>
            <pre class="text-[11px] font-mono text-surface-400"><span class="text-surface-500"># Scale in at multiple levels</span>
self.buy = [
  (qty1, price1),
  (qty2, price2),
]</pre>
          </div>
        </div>
      </div>
      <!-- Filters + Chart Annotations -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="card">
          <h3 class="text-sm font-semibold text-surface-200 mb-3">Entry Filters</h3>
          <p class="text-xs text-surface-400 mb-2">Additional conditions that must <em>all</em> pass before an entry is taken.</p>
          <div class="bg-surface-900 rounded-lg p-3">
            <pre class="text-[11px] font-mono text-surface-300 whitespace-pre"><span class="text-purple-400">def</span> <span class="text-blue-300">filters</span>(self):
    <span class="text-purple-400">return</span> [
        self.is_volatile_enough,
        self.not_near_weekend,
    ]

<span class="text-purple-400">def</span> <span class="text-blue-300">is_volatile_enough</span>(self):
    <span class="text-purple-400">return</span> ta.atr(self.candles, 14) > 0.001

<span class="text-purple-400">def</span> <span class="text-blue-300">not_near_weekend</span>(self):
    <span class="text-purple-400">return</span> self.minutes_to_close <span class="text-purple-400">is</span> None \
        <span class="text-purple-400">or</span> self.minutes_to_close > 120</pre>
          </div>
        </div>
        <div class="card">
          <h3 class="text-sm font-semibold text-surface-200 mb-3">Chart Annotations</h3>
          <p class="text-xs text-surface-400 mb-2">Add custom lines and labels to backtest charts.</p>
          <div class="bg-surface-900 rounded-lg p-3">
            <pre class="text-[11px] font-mono text-surface-300 whitespace-pre"><span class="text-surface-500"># Label on order markers</span>
self.chart_label = <span class="text-green-400">"L0"</span>

<span class="text-surface-500"># Indicator line on candle chart</span>
self._add_line_to_candle_chart_values[
    <span class="text-green-400">'ema21'</span>] = ta.ema(self.candles, 21)

<span class="text-surface-500"># Horizontal line</span>
self._add_horizontal_line_to_candle_chart_values[
    <span class="text-green-400">'tp_line'</span>] = tp_price

<span class="text-surface-500"># Separate indicator pane</span>
self._add_extra_line_chart_values[
    <span class="text-green-400">'rsi'</span>] = ta.rsi(self.candles, 14)</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB: Properties -->
    <div v-if="activeTab === 'properties'" class="space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="card">
          <h3 class="text-sm font-semibold text-surface-200 mb-3">Price &amp; Candle</h3>
          <div class="grid grid-cols-2 gap-1.5">
            <div v-for="p in propsPrice" :key="p.name" class="p-1.5 bg-surface-800/50 rounded">
              <code class="text-[11px] text-emerald-400 font-mono">self.{{ p.name }}</code>
              <p class="text-[10px] text-surface-500">{{ p.desc }}</p>
            </div>
          </div>
        </div>
        <div class="card">
          <h3 class="text-sm font-semibold text-surface-200 mb-3">Position &amp; Balance</h3>
          <div class="grid grid-cols-2 gap-1.5">
            <div v-for="p in propsPosition" :key="p.name" class="p-1.5 bg-surface-800/50 rounded">
              <code class="text-[11px] text-emerald-400 font-mono">self.{{ p.name }}</code>
              <p class="text-[10px] text-surface-500">{{ p.desc }}</p>
            </div>
          </div>
        </div>
      </div>
      <div class="card">
        <h3 class="text-sm font-semibold text-surface-200 mb-3">Forex / CFD Helpers</h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-1.5">
          <div v-for="p in propsForex" :key="p.name" class="p-1.5 bg-surface-800/50 rounded">
            <code class="text-[11px] text-amber-400 font-mono">{{ p.name }}</code>
            <p class="text-[10px] text-surface-500">{{ p.desc }}</p>
          </div>
        </div>
      </div>
      <div class="card">
        <h3 class="text-sm font-semibold text-surface-200 mb-3">Hyperparameters</h3>
        <p class="text-xs text-surface-400 mb-3">Define tunable parameters for optimization. Access via <code class="text-brand-400">self.hp['name']</code> or <code class="text-brand-400">self.hp.get('name', default)</code>.</p>
        <div class="bg-surface-900 rounded-lg p-3 overflow-x-auto">
          <pre class="text-[11px] font-mono text-surface-300 whitespace-pre"><span class="text-purple-400">def</span> <span class="text-blue-300">hyperparameters</span>(self):
    <span class="text-purple-400">return</span> [
        {<span class="text-green-400">'name'</span>: <span class="text-green-400">'period'</span>,     <span class="text-green-400">'type'</span>: int,   <span class="text-green-400">'min'</span>: 5,   <span class="text-green-400">'max'</span>: 50,  <span class="text-green-400">'default'</span>: 14},
        {<span class="text-green-400">'name'</span>: <span class="text-green-400">'threshold'</span>,  <span class="text-green-400">'type'</span>: float, <span class="text-green-400">'min'</span>: 0.1, <span class="text-green-400">'max'</span>: 1.0, <span class="text-green-400">'default'</span>: 0.5},
        {<span class="text-green-400">'name'</span>: <span class="text-green-400">'mode'</span>,       <span class="text-green-400">'type'</span>: str,   <span class="text-green-400">'options'</span>: [<span class="text-green-400">'fast'</span>, <span class="text-green-400">'slow'</span>], <span class="text-green-400">'default'</span>: <span class="text-green-400">'fast'</span>},
    ]</pre>
        </div>
        <div class="grid grid-cols-3 gap-2 mt-3">
          <div class="p-2 bg-surface-800/50 rounded text-center">
            <div class="text-[10px] text-surface-500 mb-0.5">Supported Types</div>
            <code class="text-[11px] text-surface-300">int, float, str</code>
          </div>
          <div class="p-2 bg-surface-800/50 rounded text-center">
            <div class="text-[10px] text-surface-500 mb-0.5">For Strings</div>
            <code class="text-[11px] text-surface-300">options: [...]</code>
          </div>
          <div class="p-2 bg-surface-800/50 rounded text-center">
            <div class="text-[10px] text-surface-500 mb-0.5">Auto-loaded</div>
            <span class="text-[11px] text-surface-300">Playground reads these</span>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB: Modes & Caching -->
    <div v-if="activeTab === 'modes'" class="space-y-4">
      <div class="card">
        <h3 class="text-sm font-semibold text-surface-200 mb-3">Exchange Types</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div class="p-3 bg-surface-800/50 rounded border border-surface-700">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-[10px] font-bold">CFD</span>
              <span class="text-xs text-surface-300 font-medium">Forex / CFD</span>
            </div>
            <p class="text-[11px] text-surface-500">OANDA, IG Markets, IBKR. True hedging with independent tickets. Multiple positions in same symbol simultaneously.</p>
            <div class="mt-2 space-y-1">
              <code class="block text-[10px] text-surface-400 font-mono">self.hedge_mode = True</code>
              <code class="block text-[10px] text-surface-400 font-mono">self.close_all_tickets(price)</code>
              <code class="block text-[10px] text-surface-400 font-mono">self.close_ticket(id, price)</code>
            </div>
          </div>
          <div class="p-3 bg-surface-800/50 rounded border border-surface-700">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-[10px] font-bold">FUTURES</span>
              <span class="text-xs text-surface-300 font-medium">Crypto Futures</span>
            </div>
            <p class="text-[11px] text-surface-500">Netting mode. One position per symbol. Supports leverage and funding rates.</p>
            <div class="mt-2 space-y-1">
              <code class="block text-[10px] text-surface-400 font-mono">self.leverage</code>
              <code class="block text-[10px] text-surface-400 font-mono">self.mark_price</code>
              <code class="block text-[10px] text-surface-400 font-mono">self.funding_rate</code>
            </div>
          </div>
          <div class="p-3 bg-surface-800/50 rounded border border-surface-700">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-[10px] font-bold">SPOT</span>
              <span class="text-xs text-surface-300 font-medium">Crypto Spot</span>
            </div>
            <p class="text-[11px] text-surface-500">No leverage, no shorting. Buy and sell actual assets. Simplest exchange type.</p>
            <div class="mt-2 space-y-1">
              <code class="block text-[10px] text-surface-400 font-mono">self.is_spot_trading</code>
              <code class="block text-[10px] text-surface-400 font-mono">self.balance</code>
              <code class="block text-[10px] text-surface-400 font-mono">self.portfolio_value</code>
            </div>
          </div>
        </div>
        <div class="mt-3 p-2 bg-surface-800/50 rounded">
          <p class="text-[11px] text-surface-500"><span class="text-surface-300 font-medium">Detection:</span> Auto-detected from broker. Check with <code class="text-emerald-400">self.exchange_type</code> (<code class="text-surface-400">'cfd'</code>/<code class="text-surface-400">'futures'</code>/<code class="text-surface-400">'spot'</code>) or <code class="text-emerald-400">self.is_cfd_trading</code>, <code class="text-emerald-400">self.is_futures_trading</code>, <code class="text-emerald-400">self.is_spot_trading</code>.</p>
        </div>
      </div>
      <!-- @cached -->
      <div class="card">
        <h3 class="text-sm font-semibold text-surface-200 mb-3">Performance: @cached Decorator</h3>
        <p class="text-xs text-surface-400 mb-2">Cache expensive computations per candle. Resets automatically on new candle.</p>
        <div class="bg-surface-900 rounded-lg p-3">
          <pre class="text-[11px] font-mono text-surface-300 whitespace-pre"><span class="text-purple-400">from</span> qengine.services.cache <span class="text-purple-400">import</span> cached

<span class="text-purple-400">class</span> <span class="text-yellow-300">MyStrategy</span>(Strategy):
    @cached
    <span class="text-purple-400">def</span> <span class="text-blue-300">atr_value</span>(self):
        <span class="text-purple-400">return</span> ta.atr(self.candles, 14)

    <span class="text-purple-400">def</span> <span class="text-blue-300">should_long</span>(self):
        <span class="text-surface-500"># computed only once per candle thanks to @cached</span>
        <span class="text-purple-400">return</span> self.price > self.atr_value * 100</pre>
        </div>
      </div>
    </div>

    <!-- TAB: Indicators -->
    <div v-if="activeTab === 'indicators'" class="space-y-4">
      <div class="card">
        <p class="text-xs text-surface-400 mb-1">Import: <code class="text-brand-400">import qengine.indicators as ta</code></p>
        <p class="text-xs text-surface-500 mb-3">All indicators take <code class="text-surface-400">candles</code> as first arg. Returns <span class="text-amber-400">scalar by default</span>. Pass <code class="text-surface-400">sequential=True</code> to get full array.</p>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          <div v-for="cat in indicators" :key="cat.name">
            <h4 class="text-[11px] font-semibold text-surface-400 mb-1.5">{{ cat.name }}</h4>
            <div class="flex flex-wrap gap-1">
              <code v-for="ind in cat.items" :key="ind" class="px-1.5 py-0.5 bg-surface-800 rounded text-[10px] text-surface-400 font-mono hover:text-surface-200 transition-colors">{{ ind }}</code>
            </div>
          </div>
        </div>
        <div class="mt-4 p-3 bg-surface-900 rounded-lg">
          <h4 class="text-[11px] font-semibold text-surface-300 mb-1.5">Usage Examples</h4>
          <pre class="text-[11px] font-mono text-surface-400 whitespace-pre">ta.ema(self.candles, 21)                    <span class="text-surface-600"># scalar (latest value)</span>
ta.ema(self.candles, 21, sequential=True)   <span class="text-surface-600"># full array</span>
ta.rsi(self.candles, 14)                    <span class="text-surface-600"># RSI scalar</span>
ta.atr(self.candles, 14)                    <span class="text-surface-600"># ATR scalar</span>
ta.macd(self.candles, 12, 26, 9)            <span class="text-surface-600"># returns (macd, signal, hist)</span>
ta.bollinger_bands(self.candles, 20)        <span class="text-surface-600"># returns (upper, middle, lower)</span>
ta.supertrend(self.candles, 10, 3.0)        <span class="text-surface-600"># returns (trend, direction)</span></pre>
        </div>
      </div>
    </div>

    <!-- TAB: Imports -->
    <div v-if="activeTab === 'imports'" class="space-y-4">
      <div class="card">
        <h3 class="text-sm font-semibold text-surface-200 mb-3">Common Imports &amp; Utilities</h3>
        <div class="bg-surface-900 rounded-lg p-3 overflow-x-auto">
          <pre class="text-[11px] font-mono text-surface-300 whitespace-pre"><span class="text-surface-500"># Core imports</span>
<span class="text-purple-400">import</span> qengine.indicators <span class="text-purple-400">as</span> ta        <span class="text-surface-500"># 170+ indicators</span>
<span class="text-purple-400">from</span> qengine.strategies <span class="text-purple-400">import</span> Strategy  <span class="text-surface-500"># base class</span>
<span class="text-purple-400">import</span> qengine.helpers <span class="text-purple-400">as</span> jh            <span class="text-surface-500"># utility helpers</span>
<span class="text-purple-400">import</span> numpy <span class="text-purple-400">as</span> np                      <span class="text-surface-500"># arrays</span>

<span class="text-surface-500"># Caching (recompute once per candle, not per call)</span>
<span class="text-purple-400">from</span> qengine.services.cache <span class="text-purple-400">import</span> cached

<span class="text-surface-500"># Logging in strategies</span>
self.log(<span class="text-green-400">"Entry signal fired"</span>, <span class="text-green-400">"info"</span>)

<span class="text-surface-500"># Environment checks</span>
jh.is_live()         <span class="text-surface-500"># True in livetrade AND papertrade</span>
jh.is_livetrading()  <span class="text-surface-500"># True ONLY in livetrade mode</span>
jh.is_backtesting()  <span class="text-surface-500"># True in backtest mode</span></pre>
        </div>
      </div>
    </div>

    <!-- TAB: Installed -->
    <div v-if="activeTab === 'installed'" class="space-y-3">
      <div v-for="strat in strategies" :key="'guide-' + strat" class="card">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center text-[10px] font-mono font-bold"
            :class="getStratMeta?.(strat)?.iconClass || 'bg-surface-800 text-brand-400'">{{ strat.slice(0, 2) }}</div>
          <span class="text-sm font-semibold text-surface-100">{{ strat }}</span>
          <span v-for="label in (getStratMeta?.(strat)?.labels || [])" :key="label.text"
            class="px-1.5 py-0.5 rounded text-[10px] font-medium" :class="label.class">{{ label.text }}</span>
        </div>
        <p class="text-xs text-surface-400 mb-3">{{ getStratMeta?.(strat)?.longDescription || getStratMeta?.(strat)?.description || '' }}</p>
        <div v-if="getStratMeta?.(strat)?.params?.length">
          <h4 class="text-[11px] font-semibold text-surface-500 mb-1.5">Parameters</h4>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-1">
            <div v-for="p in getStratMeta(strat).params" :key="p" class="px-2 py-1 bg-surface-800/50 rounded">
              <code class="text-[10px] text-brand-400 font-mono">{{ p }}</code>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!strategies.length" class="text-surface-500 text-sm py-8 text-center">No strategies installed yet.</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  strategies: { type: Array, default: () => [] },
  getStratMeta: { type: Function, default: null },
})

defineEmits(['close'])

const activeTab = ref('quickstart')

const tabs = [
  { id: 'quickstart', label: 'Quick Start' },
  { id: 'methods', label: 'Methods & Orders' },
  { id: 'properties', label: 'Properties' },
  { id: 'modes', label: 'Modes & Caching' },
  { id: 'indicators', label: 'Indicators' },
  { id: 'imports', label: 'Imports' },
  { id: 'installed', label: 'Installed Strategies' },
]

// ── Data arrays (same as previously in Strategies.vue) ──

const optionalMethods = [
  { name: 'should_short(self) -> bool', desc: 'Return True to enter short (default: False)' },
  { name: 'go_short(self)', desc: 'Set self.sell, self.stop_loss, self.take_profit for short entry' },
  { name: 'before(self)', desc: 'Runs BEFORE each candle logic - precompute indicators here' },
  { name: 'after(self)', desc: 'Runs AFTER each candle logic' },
  { name: 'update_position(self)', desc: 'Called when position is open - update TP/SL dynamically' },
  { name: 'should_cancel_entry(self) -> bool', desc: 'Cancel pending orders on new candle (default: True)' },
  { name: 'on_open_position(self, order)', desc: 'Called when position opens' },
  { name: 'on_close_position(self, order, trade)', desc: 'Called when position closes with ClosedTrade' },
  { name: 'on_increased_position(self, order)', desc: 'Called when position size increases' },
  { name: 'on_reduced_position(self, order)', desc: 'Called when position size decreases' },
  { name: 'on_ticket_opened(self, order)', desc: 'CFD mode: called when a new ticket opens' },
  { name: 'on_ticket_closed(self, order)', desc: 'CFD mode: called when a ticket closes' },
  { name: 'on_cancel(self)', desc: 'Called after all orders are cancelled' },
  { name: 'filters(self) -> list', desc: 'Return list of filter methods for entry validation' },
  { name: 'hyperparameters(self) -> list', desc: 'Return list of HP dicts for optimization' },
  { name: 'watch_list(self) -> list', desc: 'Return [{key, value}] dicts for live monitoring' },
  { name: 'terminate(self)', desc: 'Called at backtest end / strategy termination' },
  { name: 'before_terminate(self)', desc: 'Called before termination' },
  { name: 'dna(self) -> str', desc: 'Return DNA string for strategy identification' },
]

const propsPrice = [
  { name: 'price', desc: 'Current price (close)' },
  { name: 'open', desc: 'Current candle open' },
  { name: 'close', desc: 'Current candle close' },
  { name: 'high', desc: 'Current candle high' },
  { name: 'low', desc: 'Current candle low' },
  { name: 'volume', desc: 'Current candle volume' },
  { name: 'candles', desc: 'All historical candles' },
  { name: 'current_candle', desc: 'Current candle array' },
  { name: 'index', desc: 'Current candle index' },
  { name: 'timeframe', desc: 'Strategy timeframe' },
]

const propsPosition = [
  { name: 'is_long', desc: 'Position is long' },
  { name: 'is_short', desc: 'Position is short' },
  { name: 'is_open', desc: 'Position is open' },
  { name: 'is_close', desc: 'Position is closed' },
  { name: 'balance', desc: 'Current wallet balance' },
  { name: 'available_margin', desc: 'Available margin' },
  { name: 'leverage', desc: 'Current leverage' },
  { name: 'fee_rate', desc: 'Exchange fee rate' },
  { name: 'portfolio_value', desc: 'Total portfolio value' },
  { name: 'position', desc: 'Position object' },
]

const propsForex = [
  { name: 'self.session', desc: "tokyo, london, new_york, overlap, off" },
  { name: 'self.spread', desc: 'Bid-ask spread' },
  { name: 'self.pip_size', desc: 'e.g. 0.0001 for EUR-USD' },
  { name: 'self.market_is_open', desc: 'Is market open?' },
  { name: 'self.minutes_to_close', desc: 'Minutes until close' },
  { name: 'self.swap_long', desc: 'Overnight swap (long)' },
  { name: 'self.swap_short', desc: 'Overnight swap (short)' },
  { name: 'self.contract_size', desc: 'e.g. 100000 for forex' },
  { name: 'self.pips_to_price(n)', desc: 'Convert pips to price' },
  { name: 'self.price_to_pips(d)', desc: 'Convert price to pips' },
  { name: 'self.lot_size_for_risk(%, pips)', desc: 'Qty for risk %' },
  { name: 'self.asset_class', desc: 'forex, commodity, index' },
]

const indicators = [
  { name: 'Moving Averages', items: ['sma', 'ema', 'dema', 'tema', 'wma', 'vwma', 'kama', 'alma', 'jma', 't3'] },
  { name: 'Momentum', items: ['rsi', 'macd', 'mom', 'apo', 'ppo', 'kst', 'tsi', 'stochastic', 'cci', 'rvi', 'williams'] },
  { name: 'Volatility', items: ['atr', 'natr', 'stddev', 'bollinger_bands', 'keltner', 'donchian'] },
  { name: 'Trend', items: ['adx', 'aroon', 'supertrend', 'ichimoku_cloud', 'trendline'] },
  { name: 'Volume', items: ['obv', 'adosc', 'mfi', 'kvo', 'vwap'] },
  { name: 'Utility', items: ['highestprice', 'lowestprice', 'correl', 'beta', 'heikin_ashi_candles'] },
]
</script>
