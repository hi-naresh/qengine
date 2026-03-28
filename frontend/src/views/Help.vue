<template xmlns="http://www.w3.org/1999/html">
  <div>
    <div class="text-center mb-6">
      <h1 class="text-2xl font-bold">Help & Testing Guide</h1>
      <p class="text-sm text-surface-500 mt-1">How to verify that QEngine's analysis engine produces truthful results</p>
    </div>

    <!-- Sub-tabs -->
    <div class="flex gap-2 mb-5 flex-wrap">
      <button v-for="tab in tabs" :key="tab" @click="activeTab = tab"
        class="btn-sm" :class="activeTab === tab ? 'bg-brand-600 text-white' : 'bg-surface-800 text-surface-400'">
        {{ tab }}
      </button>
    </div>

    <!-- Quick Start -->
    <div v-if="activeTab === 'Quick Start'" class="max-w-3xl space-y-5">
      <div class="card">
        <div class="p-4 rounded-xl bg-brand-600/10 border border-brand-500/20 mb-5">
          <h2 class="text-sm font-semibold text-brand-400 mb-2">Your Role</h2>
          <p class="text-sm text-surface-300 leading-relaxed">
            QEngine is a multi-asset quant engine for analysis and production pipelines for trading systems with intelligence &mdash; built from scratch using quantitative techniques and methods, not just LLM-tuned.
            Currently in <strong class="text-surface-100">beta testing</strong>. Your goal is to verify the <strong class="text-surface-100">correctness of the engine</strong> &mdash;
            whether strategies execute as intended, trades fire at the right time and price, the cost model produces sensible results,
            and the reported statistics are mathematically accurate. You are testing the <em>engine logic</em>, not the interface.
          </p>
        </div>

        <!-- Important constraints -->
        <div class="p-3 rounded-lg bg-amber-500/5 border border-amber-500/15 mb-5">
          <p class="text-xs text-amber-300/80 leading-relaxed">
            <strong class="text-amber-400">Resource note:</strong> This deployment runs on minimal specs for beta.
            Use <strong> reasonable date ranges and timeframes</strong> is ideal.
            Avoid way too ranges as they will take excessive time to get results.
          </p>
        </div>

        <h2 class="text-sm font-semibold text-surface-200 mb-4">Step-by-Step Testing Workflow</h2>
        <div class="space-y-4">
          <div v-for="(step, i) in steps" :key="i" class="flex gap-4">
            <div class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold" :class="step.color">{{ i + 1 }}</div>
            <div class="flex-1 min-w-0">
              <h3 class="text-sm font-semibold text-surface-200">{{ step.title }}</h3>
              <p class="text-xs text-surface-400 mt-1 leading-relaxed">{{ step.desc }}</p>
              <div v-if="step.details" class="mt-2 space-y-1">
                <p v-for="(d, j) in step.details" :key="j" class="text-[11px] text-surface-500 flex items-start gap-2">
                  <span class="text-brand-500/60 mt-0.5 shrink-0">-</span>
                  <span v-html="d"></span>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Execution Review -->
    <div v-if="activeTab === 'Execution Review'" class="max-w-3xl space-y-5">
      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-2">Reviewing Strategy Execution</h2>
        <p class="text-xs text-surface-400 mb-4 leading-relaxed">
          The most important thing to verify is whether the engine <strong class="text-surface-300">executes your strategy
          the way it should be executed</strong>. This means checking that entries, exits, stop-losses, and take-profits
          all trigger at the correct time, on the correct candle, and at the correct price.
        </p>

        <div class="space-y-4">
          <div v-for="area in executionAreas" :key="area.title" class="p-4 bg-surface-800 rounded-xl">
            <h3 class="text-sm font-semibold text-surface-200 mb-2">{{ area.title }}</h3>
            <p class="text-xs text-surface-400 leading-relaxed mb-2">{{ area.desc }}</p>
            <div class="space-y-1">
              <p v-for="(q, i) in area.checks" :key="i" class="text-[11px] text-surface-500 flex items-start gap-2">
                <span class="text-surface-600 shrink-0">?</span>
                <span>{{ q }}</span>
              </p>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-3">How a Strategy Should Execute</h2>
        <p class="text-xs text-surface-400 mb-3 leading-relaxed">
          The engine processes candles one at a time. On each new candle, it evaluates your strategy methods in this order:
        </p>
        <div class="space-y-2">
          <div v-for="(phase, i) in executionFlow" :key="i" class="flex items-start gap-3 p-3 bg-surface-800 rounded-lg">
            <span class="text-[10px] font-bold text-brand-400/60 mt-0.5 shrink-0">{{ i + 1 }}.</span>
            <div>
              <code class="text-[11px] text-brand-400">{{ phase.method }}</code>
              <p class="text-[11px] text-surface-500 mt-0.5">{{ phase.desc }}</p>
            </div>
          </div>
        </div>
        <p class="text-xs text-surface-500 mt-3 leading-relaxed">
          If you understand this lifecycle, you can predict what your strategy should do on any given candle.
          When the backtest results differ from that prediction, you've found a potential bug.
        </p>
      </div>
    </div>

    <!-- Cost Model -->
    <div v-if="activeTab === 'Cost Model'" class="max-w-3xl space-y-5">
      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-2">Validating the Cost Model</h2>
        <p class="text-xs text-surface-400 mb-4 leading-relaxed">
          QEngine applies a realistic cost model during backtesting: <strong class="text-surface-300">spread</strong> (bid-ask),
          <strong class="text-surface-300">slippage</strong> (execution delay), and <strong class="text-surface-300">swap</strong>
          (overnight financing charges). Your task is to verify these are applied correctly and produce sensible results.
        </p>

        <div class="space-y-4">
          <div v-for="cost in costAreas" :key="cost.title" class="p-4 bg-surface-800 rounded-xl">
            <h3 class="text-sm font-semibold text-surface-200 mb-1">{{ cost.title }}</h3>
            <p class="text-xs text-surface-400 leading-relaxed mb-2">{{ cost.how }}</p>
            <div class="space-y-1">
              <p v-for="(c, i) in cost.checks" :key="i" class="text-[11px] text-surface-500 flex items-start gap-2">
                <span class="text-surface-600 shrink-0">?</span>
                <span>{{ c }}</span>
              </p>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-3">How to Check</h2>
        <div class="space-y-2 text-xs text-surface-400 leading-relaxed">
          <p>1. Run a backtest with <strong class="text-surface-300">zero spread, zero slippage, swap disabled</strong>. Note the results.</p>
          <p>2. Re-run with <strong class="text-surface-300">realistic spread</strong> (e.g. 1-2 pips for EUR-USD). The profit should decrease proportionally to the number of trades times the spread cost.</p>
          <p>3. Add <strong class="text-surface-300">slippage</strong> (e.g. 0.5 pips). Profit should decrease further.</p>
          <p>4. Enable <strong class="text-surface-300">swap</strong>. Positions held overnight should show additional charges or credits depending on the direction.</p>
          <p>5. Compare the total cost impact against a rough manual estimate. If 100 round-trip trades on EUR-USD with 2-pip spread should cost ~$2,000 on 1 lot, does the backtest reflect that?</p>
        </div>
      </div>
    </div>

    <!-- Stats Validation -->
    <div v-if="activeTab === 'Stats & Metrics'" class="max-w-3xl space-y-5">
      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-2">Verifying Reported Statistics</h2>
        <p class="text-xs text-surface-400 mb-4 leading-relaxed">
          After every backtest, QEngine reports 20+ performance metrics. These must be <strong class="text-surface-300">mathematically
          correct</strong>. Use your knowledge of quantitative finance to cross-check them. If a number looks suspicious,
          try to calculate it by hand from the trade log.
        </p>

        <div class="space-y-3">
          <div v-for="stat in statChecks" :key="stat.name" class="p-3 bg-surface-800 rounded-lg">
            <div class="flex items-center gap-2 mb-1">
              <code class="text-[11px] text-brand-400">{{ stat.name }}</code>
            </div>
            <p class="text-[11px] text-surface-500">{{ stat.formula }}</p>
            <p class="text-[11px] text-surface-600 mt-0.5 italic">{{ stat.check }}</p>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-3">Quick Sanity Checks</h2>
        <div class="space-y-1.5 text-xs text-surface-400 leading-relaxed">
          <p>- If the strategy has <strong class="text-surface-300">0 losing trades</strong>, profit factor should not be "Infinity" — it should handle the edge case gracefully.</p>
          <p>- If <strong class="text-surface-300">no trades</strong> were taken, all metrics should be zeroed or marked N/A — not NaN or broken.</p>
          <p>- The sum of individual trade P&Ls in the trade log should <strong class="text-surface-300">match the total net profit</strong> exactly.</p>
          <p>- Max drawdown should never exceed <strong class="text-surface-300">100%</strong>, and it should match the deepest valley visible in the equity curve.</p>
          <p>- Win rate should be <strong class="text-surface-300">winning trades / total trades</strong>. If the trade log shows 30 wins out of 50, the win rate must be 60%.</p>
          <p>- Running the <strong class="text-surface-300">exact same</strong> backtest twice with the same parameters should produce <strong class="text-surface-300">identical</strong> numbers.</p>
        </div>
      </div>
    </div>

    <!-- Monte Carlo -->
    <div v-if="activeTab === 'Monte Carlo'" class="max-w-3xl space-y-5">
      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-2">Reviewing Monte Carlo Results</h2>
        <p class="text-xs text-surface-400 mb-4 leading-relaxed">
          Monte Carlo simulation stress-tests a strategy by randomizing trade order or perturbing candle data.
          The results show how robust the strategy's performance is under variation. Your job is to check whether
          the simulation logic and reported distributions make statistical sense.
        </p>

        <div class="space-y-3">
          <div v-for="mc in mcChecks" :key="mc.title" class="p-4 bg-surface-800 rounded-xl">
            <h3 class="text-sm font-semibold text-surface-200 mb-1">{{ mc.title }}</h3>
            <p class="text-xs text-surface-400 leading-relaxed">{{ mc.desc }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- How to Report -->
    <div v-if="activeTab === 'How to Report'" class="max-w-3xl space-y-5">
      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-4">Submitting Feedback</h2>
        <p class="text-xs text-surface-400 mb-5 leading-relaxed">
          All findings go through the <strong class="text-surface-300">Issues</strong> section in the sidebar.
          Good reports are specific and reproducible. Here's what to include:
        </p>

        <div class="space-y-4">
          <div v-for="(tip, i) in reportTips" :key="i" class="flex gap-3">
            <div class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-amber-600/20 text-amber-400">{{ i + 1 }}</div>
            <div class="flex-1">
              <h3 class="text-sm font-medium text-surface-200">{{ tip.title }}</h3>
              <p class="text-xs text-surface-400 mt-0.5 leading-relaxed">{{ tip.desc }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-3">Example Issue</h2>
        <div class="p-4 bg-surface-800 rounded-xl text-xs font-mono text-surface-400 leading-relaxed whitespace-pre-wrap">{{ exampleIssue }}</div>
      </div>

      <div class="card">
        <h2 class="text-sm font-semibold text-surface-200 mb-3">Priority Guide</h2>
        <div class="space-y-2">
          <div v-for="p in priorities" :key="p.level" class="flex items-start gap-3 p-3 bg-surface-800 rounded-lg">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0" :class="p.badge">{{ p.level }}</span>
            <p class="text-xs text-surface-400">{{ p.desc }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- FAQ -->
    <div v-if="activeTab === 'FAQ'" class="max-w-3xl space-y-3">
      <div v-for="(faq, i) in faqs" :key="i" class="card">
        <button @click="openFaq = openFaq === i ? -1 : i" class="flex items-center justify-between w-full text-left">
          <h3 class="text-sm font-medium text-surface-200">{{ faq.q }}</h3>
          <svg class="w-4 h-4 text-surface-500 transition-transform" :class="openFaq === i ? 'rotate-180' : ''" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
          </svg>
        </button>
        <p v-if="openFaq === i" class="text-xs text-surface-400 mt-3 leading-relaxed">{{ faq.a }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const tabs = ['Quick Start', 'Execution Review', 'Cost Model', 'Stats & Metrics', 'Monte Carlo', 'How to Report', 'FAQ']
const activeTab = ref('Quick Start')
const openFaq = ref(-1)

const steps = [
  {
    title: 'Write a Strategy You Can Reason About',
    desc: 'Go to Strategies and create one — or generate one via LLM Studio. The key requirement: you must understand the logic well enough to predict how it should behave. If you can\'t judge whether the engine did the right thing, the test is useless.',
    details: [
      'EMA crossover, RSI overbought/oversold, Bollinger band breakout — anything you know well',
      'Implement your logic in <code class="text-[10px] bg-surface-800 px-1 rounded">should_long()</code>, <code class="text-[10px] bg-surface-800 px-1 rounded">go_long()</code>, <code class="text-[10px] bg-surface-800 px-1 rounded">update_position()</code>, etc.',
      'If you prefer AI-assisted coding, describe your strategy in plain English in <strong class="text-surface-300">LLM Studio</strong>',
    ],
    color: 'bg-brand-600/20 text-brand-400',
  },
  {
    title: 'Test It in the Playground First',
    desc: 'Before running a full backtest, use the Playground to execute your strategy on a small, focused date range. The Playground lets you see trade entries and exits directly on the chart, so you can visually verify that your strategy opens and closes positions where it should.',
    details: [
      'Pick a short date range (a few days to a couple of weeks) where you know what your strategy should do',
      'Run the strategy and inspect the chart — are entries and exits on the candles you expected?',
      'Refine your strategy logic iteratively until execution matches your intent',
      'This is the fastest way to catch logic errors before committing to a longer backtest',
    ],
    color: 'bg-cyan-600/20 text-cyan-400',
  },
  {
    title: 'Run a Backtest on a Reasonable Date Range',
    desc: 'Once your strategy behaves correctly in the Playground, run a proper backtest. Select a symbol (e.g. EUR-USD), a timeframe (1h or 4h recommended), and a 1–6 month date range. This deployment runs on minimal specs — avoid multi-year ranges on sub-hourly timeframes.',
    details: [
      'The engine processes candles sequentially and evaluates your strategy on each one',
      'Spread, slippage, and swap are applied automatically based on the cost settings',
      'Cost settings can be adjusted in <strong class="text-surface-300">Settings > Cost & Randomness</strong> per broker',
    ],
    color: 'bg-blue-600/20 text-blue-400',
  },
  {
    title: 'Review How Trades Were Executed',
    desc: 'This is the core of your review. Open the trade log and check every aspect of execution against your expectations:',
    details: [
      'Did entries trigger on the candle where your entry condition was true?',
      'Did the entry price reflect the expected fill (considering spread)?',
      'Did stop-loss and take-profit orders fire at the correct price level?',
      'Were there any phantom trades (trades that should not have happened)?',
      'Were there any missed signals (conditions were met but no trade was opened)?',
    ],
    color: 'bg-purple-600/20 text-purple-400',
  },
  {
    title: 'Check Whether the Cost Model is Sensible',
    desc: 'Verify that the cost model produces realistic results. Spread should shift fill prices, slippage should cause minor deviations, and swap should appear on overnight positions.',
    details: [
      'Compare a zero-cost run vs. a realistic-cost run — the difference should be proportional to trade count and cost settings',
      'Check individual trades: buy fills should be at ask (price + half spread), sell fills at bid (price - half spread)',
      'Overnight positions should show swap charges at 5 PM New York rollover',
    ],
    color: 'bg-green-600/20 text-green-400',
  },
  {
    title: 'Critique the Reported Statistics',
    desc: 'Apply your quant knowledge. The engine reports Sharpe ratio, profit factor, max drawdown, win rate, Sortino, Calmar, and more. Cross-check them:',
    details: [
      'Sum the individual trade P&Ls from the trade log — does it match "total net profit"?',
      'Count wins and losses manually — does it match the reported win rate?',
      'Estimate profit factor (gross profit / gross loss) from the trade log — does it match?',
      'Look at the equity curve\'s deepest valley — does it match the reported max drawdown?',
    ],
    color: 'bg-amber-600/20 text-amber-400',
  },
  {
    title: 'Report Everything via Issues',
    desc: 'Create a ticket for every finding. Include the strategy name, symbol, timeframe, date range, and a clear description of what you expected vs. what actually happened. One issue per ticket.',
    color: 'bg-red-600/20 text-red-400',
  },
]

const executionAreas = [
  {
    title: 'Entry Signal Correctness',
    desc: 'The engine should open a trade when and only when your entry condition returns True.',
    checks: [
      'Did the entry happen on the candle where should_long() or should_short() returned True?',
      'Was the entry delayed by one candle (common in event-driven engines) — and if so, is that documented?',
      'If using limit or stop entry orders, did they fill at the correct trigger price?',
      'Were there any entries that fired when the condition was clearly False?',
    ],
  },
  {
    title: 'Exit and Stop/TP Behaviour',
    desc: 'Stop-loss and take-profit orders should execute at their set price levels (accounting for spread and gaps).',
    checks: [
      'Did the stop-loss fire at the exact SL price, or did it account for spread/slippage?',
      'If the candle gapped through the SL, was it filled at the gap price (realistic) or the SL price (optimistic)?',
      'Did take-profit fire correctly, or were there cases where price hit TP but the trade wasn\'t closed?',
      'When should_cancel_entry() returned True, was the pending order actually cancelled?',
    ],
  },
  {
    title: 'Position Management',
    desc: 'Verify that position sizing, direction, and state are handled correctly throughout the session.',
    checks: [
      'Is the position size what you specified in go_long() / go_short()?',
      'Can the engine handle going from long to short (or vice versa) correctly?',
      'Are there any cases of double entries (opening a second position when one is already active)?',
      'Does update_position() get called on every candle while a position is open?',
    ],
  },
  {
    title: 'Session and Trade Log Integrity',
    desc: 'The trade log should be a complete and accurate record of everything that happened during the session.',
    checks: [
      'Does every entry have a corresponding exit in the trade log?',
      'Are timestamps, prices, and quantities consistent between the trade log and the equity curve?',
      'Does the number of closed trades in the log match the "total trades" stat?',
      'Is the session start and end reflected correctly (first candle date to last candle date)?',
    ],
  },
]

const executionFlow = [
  { method: 'should_cancel_entry()', desc: 'If there\'s a pending entry order, check whether to cancel it.' },
  { method: 'should_long() / should_short()', desc: 'Evaluate entry conditions. If True and no open position, the engine calls go_long() or go_short().' },
  { method: 'go_long() / go_short()', desc: 'Define the entry: quantity, stop-loss price, take-profit price. The engine places the order.' },
  { method: 'update_position()', desc: 'Called every candle while a position is open. Use for trailing stops, scaling, or manual exits.' },
  { method: 'on_open_position()', desc: 'Callback fired when an entry order fills and a new position is opened.' },
  { method: 'on_close_position()', desc: 'Callback fired when the position is fully closed (by SL, TP, or manual close).' },
]

const costAreas = [
  {
    title: 'Spread',
    how: 'Spread is the bid-ask difference. On entry, a buy order fills at ask (mid + half spread) and a sell order fills at bid (mid - half spread). On exit, the reverse applies. This means every round-trip trade costs approximately 1x the full spread.',
    checks: [
      'In the trade log, is the entry price shifted by the expected spread amount from the candle mid-price?',
      'Does the exit price reflect the spread in the opposite direction?',
      'If spread is set to 2 pips on EUR-USD, does each round-trip lose approximately $20 per standard lot to spread?',
      'With spread set to 0, are fills exactly at the candle price?',
    ],
  },
  {
    title: 'Slippage',
    how: 'Slippage simulates execution delay — the fill price may be slightly worse than the order price. It should always move against you (buy higher, sell lower).',
    checks: [
      'With slippage enabled, are fill prices slightly worse than the theoretical price?',
      'Does increasing slippage pips proportionally increase costs per trade?',
      'Is slippage applied to both entries and exits?',
      'With slippage randomness > 0, do you see variation in the slippage amount per trade?',
    ],
  },
  {
    title: 'Swap (Overnight Financing)',
    how: 'Swap charges are applied to positions held past the daily rollover time (5 PM New York / 10 PM UTC in winter). Long and short positions may have different swap rates (one may be positive).',
    checks: [
      'Do positions held only intraday (opened and closed same day) incur zero swap?',
      'Do positions held overnight show a swap charge or credit in the trade details?',
      'Are triple-swap charges applied on Wednesday (covering the weekend)?',
      'Is the swap direction correct — long swaps and short swaps should differ based on the instrument\'s rates?',
    ],
  },
]

const statChecks = [
  { name: 'Net Profit', formula: 'Sum of all closed trade P&Ls (after costs).', check: 'Sum the P&L column in the trade log yourself. Does it match?' },
  { name: 'Win Rate', formula: 'Winning trades / Total trades * 100.', check: 'Count winners and losers in the trade log. Does the percentage match?' },
  { name: 'Profit Factor', formula: 'Gross profit / Gross loss (absolute value).', check: 'Sum all positive P&Ls, sum all negative P&Ls, divide. Does it match?' },
  { name: 'Max Drawdown', formula: 'Largest peak-to-trough decline in equity, as a percentage of the peak.', check: 'Look at the equity curve. The deepest valley from any peak should match this number.' },
  { name: 'Sharpe Ratio', formula: 'Mean return / Std deviation of returns (annualized). Risk-free rate assumed 0.', check: 'A strategy with steady, small gains should have a high Sharpe. Volatile returns should have a low Sharpe. Does the number match your intuition?' },
  { name: 'Sortino Ratio', formula: 'Like Sharpe but only penalizes downside volatility (negative returns).', check: 'Should be >= Sharpe ratio. If it\'s lower, something is wrong.' },
  { name: 'Calmar Ratio', formula: 'Annualized return / Max drawdown.', check: 'Cross-check: (annual return %) / (max drawdown %). Does it match?' },
  { name: 'Average Trade P&L', formula: 'Net profit / Total trades.', check: 'Simple division. Does it match what you compute from the trade log?' },
  { name: 'Expectancy', formula: '(Win rate * Avg win) - (Loss rate * Avg loss).', check: 'Calculate from the trade log wins/losses. Does the reported value match?' },
]

const mcChecks = [
  { title: 'Distribution Shape', desc: 'With trade shuffling, the resulting equity curves should show a distribution of outcomes. The median should be close to the original backtest result. If the distribution is wildly different from the original, the strategy\'s performance may be sequence-dependent — that itself is a useful finding, but check that the simulation isn\'t introducing artifacts.' },
  { title: 'Confidence Intervals', desc: 'The reported confidence intervals (e.g. 5th and 95th percentile) should bracket the original result in most cases. If the original result falls outside the 95% interval, either the strategy is an outlier or the simulation has a bug.' },
  { title: 'Trade Count Consistency', desc: 'Each Monte Carlo iteration should have the same number of trades as the original backtest (for trade shuffling) or a similar number (for candle perturbation). If trade counts vary wildly in shuffle mode, that\'s a bug — shuffling should only change order, not count.' },
  { title: 'Worst-Case Scenarios', desc: 'The worst-case drawdown and P&L should be worse than the original but not impossibly extreme. If the worst case shows a 500% drawdown or positive infinity profit, the simulation logic is broken.' },
  { title: 'Determinism vs. Randomness', desc: 'Running Monte Carlo twice with the same seed (if applicable) should produce identical distributions. Running with different seeds should produce similar but not identical results. If results change dramatically between runs, the sample size may be too low or the simulation has a stability issue.' },
]

const reportTips = [
  { title: 'Clear, specific title', desc: 'Bad: "Something is wrong with backtest". Good: "EUR-USD 1h backtest: SL triggered at 1.0850 but should have triggered at 1.0830 (2-pip spread not applied to stop)".' },
  { title: 'Reproduction details', desc: 'Strategy name, symbol, timeframe, date range, and any cost settings you changed. The developer needs to reproduce the exact scenario.' },
  { title: 'Expected vs. actual', desc: 'Explain what the correct behaviour should be (based on your strategy logic or manual calculation) and what the engine actually did. Specific numbers are essential.' },
  { title: 'One finding per ticket', desc: 'If you found three problems, create three separate tickets. This makes tracking and resolving each one much easier.' },
  { title: 'Priority level', desc: 'Critical = wrong trade execution or data corruption. High = incorrect stats or cost model errors. Medium = logic that behaves unexpectedly in edge cases. Low = suggestions or minor inconsistencies.' },
]

const exampleIssue = `Title: Profit factor shows 2.31 but manual calculation gives 1.87

Strategy: EMACrossover
Symbol: EUR-USD, 1h timeframe
Date range: 2024-06-01 to 2024-09-01
Cost settings: 1.5 pip spread, 0.3 pip slippage, swap enabled

What I expected:
From the trade log I count:
  - 23 winning trades, gross profit = $1,842
  - 18 losing trades, gross loss = $985
  - Profit factor should be 1842 / 985 = 1.87

What I see:
  - Reported profit factor: 2.31
  - This doesn't match my manual count

Additional notes:
  - Win rate shows 56% which matches 23/41
  - Net profit shows $857 which matches 1842 - 985
  - So the issue seems specific to how profit factor
    is calculated, not the underlying trade data`

const priorities = [
  { level: 'Critical', badge: 'bg-red-500/20 text-red-400', desc: 'Wrong trade execution (entries/exits at wrong time or price), data corruption, or trades that should not exist.' },
  { level: 'High', badge: 'bg-amber-500/20 text-amber-400', desc: 'Incorrect statistics, wrong cost model calculations, or results that would mislead someone evaluating a strategy.' },
  { level: 'Medium', badge: 'bg-blue-500/20 text-blue-400', desc: 'Edge cases that produce unexpected results, logic that behaves oddly in specific scenarios.' },
  { level: 'Low', badge: 'bg-green-500/20 text-green-400', desc: 'Minor inconsistencies, suggestions for improvement, or something that looks off but may be intentional.' },
]

const faqs = [
  { q: 'What kind of strategies should I test with?', a: 'Strategies you understand well enough to predict the outcome. The goal is not to find a profitable strategy — it\'s to verify the engine executes correctly. Simple strategies (EMA crossover, RSI thresholds, breakout of N-bar high/low) are ideal because you can mentally trace what should happen on each candle.' },
  { q: 'How do I know if a stat is calculated wrong?', a: 'Cross-check against the trade log. For example: profit factor = sum of all positive P&Ls / sum of all negative P&Ls. If the trade log shows $1,500 gross profit and $800 gross loss, profit factor must be 1.875. If the displayed value differs, that\'s a bug worth reporting.' },
  { q: 'What if I\'m not sure something is a bug?', a: 'Report it anyway with the "Low" priority. Describe what you observed and why it seems off. It\'s far better to report a false positive than to miss a real bug. Add "Not sure if bug" to the title if you want.' },
  { q: 'Should I try to break things?', a: 'Yes — within the resource constraints. Try unusual parameter values, strategies that trade very frequently or very rarely, extremely tight stop-losses, or conditions that are always true. Edge cases reveal bugs that normal usage won\'t find. Just keep date ranges reasonable for this beta deployment.' },
  { q: 'Do I need to know Python?', a: 'Not necessarily. You can generate strategies with LLM Studio using natural language. However, understanding the strategy logic is essential for judging whether the backtest results are correct.' },
  { q: 'Why does my backtest show different results than I expected?', a: 'Common reasons: (1) the cost model reduces profit — spread alone can turn a marginally profitable strategy into a loser; (2) the engine may process signals on candle close, so a signal on candle N executes on candle N+1; (3) market hours filtering may skip some candles. Check the trade log for specifics and report anything that seems wrong.' },
  { q: 'How large a date range should I use?', a: 'For this beta deployment, 1–6 months on 1h or 4h timeframes is ideal. Daily timeframes can go longer. Avoid multi-year ranges on 1-minute candles — the server has limited resources. If you need a large range for a specific test, keep the total candle count manageable.' },
  { q: 'What about the Optimization tab?', a: 'Optimization is not a focus area for this testing phase. Monte Carlo is — see the Monte Carlo tab in this guide.' },
]
</script>
