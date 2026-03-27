# Autopilot Framework — Implementation Plan

## Context

qengine needs an intelligent framework that wraps any strategy with learning capabilities (danger scoring, entry gating, Q-learning abort) and an orchestrator that auto-tunes hyperparameters across repeated backtest sessions. Decision: **Approach B** — framework hooks inject into the Strategy base class; no PilotStrategy subclass needed. Any existing strategy gains intelligence automatically when `_framework` is set.

---

## Phase 1: Framework Core — `qengine/framework/`

Pure Python classes, no qengine internals dependency. Unit-testable in isolation.

### Create Files

| File | Class | Purpose |
|------|-------|---------|
| `qengine/framework/__init__.py` | — | Exports GridPilot, DangerScorer, QAbort, EntryGate, FrameworkStats |
| `qengine/framework/danger_scorer.py` | `DangerScorer` | 7 weighted features → Welford online normalization → sigmoid score [0,1] |
| `qengine/framework/q_abort.py` | `QAbort` | Q-table (level × duration_bin × danger_entry × danger_now = 1625 states, 2 actions). `decide()` → hold/abort. `learn()` for Q-update. `save()`/`load()` for numpy persistence |
| `qengine/framework/entry_gate.py` | `EntryGate` | Rolling deque of danger scores + percentile threshold. `should_allow(score) → bool` |
| `qengine/framework/pilot.py` | `GridPilot` | Composes all three. Interface: `on_before()`, `gate_entry()`, `should_abort()`, `on_cycle_end()` |
| `qengine/framework/stats.py` | `FrameworkStats` | Dataclass tracking gate checks, blocks, aborts, danger time-series. `to_dict()` for serialization |

### DangerScorer Design
- 7 features with fixed weights (from GBM importance on 20yr EUR-USD):
  - D1_range_atr (0.30, inverted), 5m_chop (0.15), 15m_chop (0.15), D1_chop (0.10), 5m_adx (0.10, inverted), 5m_hurst (0.10, inverted), 1H_atr_ratio (0.10)
- Online Welford normalization per feature (no pre-training)
- Output: sigmoid(weighted_sum) → [0, 1]
- Warmup: returns 0.5 until 50 observations

### QAbort Design
- State: (level:13, duration_bin:5, danger_entry:5, danger_now:5) = 1,625 states
- Duration bins: [0-5, 5-10, 10-20, 20-50, 50+] bars
- Danger bins: thresholds [0.3, 0.5, 0.7, 0.85]
- Actions: {continue=0, abort=1}
- Defaults: α=0.01, γ=0.95, ε=0.0 (pure exploitation; configurable)
- Can load pre-trained Q-table from `q_table_v2.npy`

### GridPilot Interface
```python
class GridPilot:
    def __init__(self, config: dict)
    def on_before(self, strategy)          # update danger scorer from strategy candle data
    def gate_entry(self) -> bool           # True = allow, False = block
    def should_abort(self, strategy) -> bool  # True = abort cycle
    def on_cycle_end(self, pnl, strategy)  # Q-learning reward update
    @property
    def stats(self) -> FrameworkStats
    def save_state(self, path) / load_state(self, path)
```

### Verify
- Unit tests: DangerScorer output range, QAbort table shape/learning, EntryGate percentile logic
- No qengine imports needed

---

## Phase 2: Strategy Hook Injection

**6 touch points in Strategy.py, ~15 lines total. All guarded by `if self._framework:`**

### Modify: `qengine/strategies/Strategy.py`

**1. `__init__` (after line 88, after `self._cached_metrics = {}`)**
```python
self._framework = None  # GridPilot instance, set externally
```

**2. `_execute()` (line 1390) — call `on_before` after `self.before()`**
```python
# line 1404-1405 becomes:
self.before()
if self._framework:
    self._framework.on_before(self)
self._check()
```

**3. `_check()` (after lines 1076+1083) — gate entry signals**
After `should_long` and `should_short` are computed (line 1083), before the if/elif block (line 1085):
```python
if self._framework and (should_long or should_short):
    if not self._framework.gate_entry():
        should_long = False
        should_short = False
```

**4. `_update_position()` (line 851) — abort check before strategy logic**
Insert before `self.update_position()` (line 858):
```python
if self._framework and self._framework.should_abort(self):
    if self.position.is_cfd_mode and hasattr(self, 'close_all_tickets'):
        self.close_all_tickets(self.price)
    else:
        self.broker.reduce_position_at(self.position.qty, self.price, self.price)
    return
```

**5. `_on_close_position()` (line 1179) — learning callback**
After `closed_trade` is retrieved (line 1186), before `_broadcast`:
```python
if self._framework:
    self._framework.on_cycle_end(closed_trade.pnl, self)
```

**6. No change to `_on_open_position()`** — framework tracks entries via gate_entry() stats already.

### Modify: `qengine/modes/backtest_mode.py`

**In `_prepare_routes()` (after line 818, after `r.strategy._init_objects()`):**
```python
# Attach framework if configured
fw_conf = config.get('app', {}).get('framework')
if fw_conf and fw_conf.get('enabled'):
    from qengine.framework import GridPilot
    r.strategy._framework = GridPilot(fw_conf)
```

**In `_generate_outputs()` (after line 1291, before `return result`):**
```python
# Collect framework stats
for r in router.routes:
    if getattr(r.strategy, '_framework', None):
        result.setdefault('framework_stats', {})[
            f"{r.exchange}-{r.symbol}"
        ] = r.strategy._framework.stats.to_dict()
```

### Modify: `qengine/config.py`

**In `set_config()` — pass framework config through:**
```python
if 'framework' in conf:
    config['app']['framework'] = conf['framework']
```

### Verify
- Run existing backtest with `_framework = None` → identical results (backward compat)
- Run with `framework: {enabled: true}` → hooks fire, stats collected
- Mock DangerScorer high → entries blocked
- Mock QAbort → abort triggered mid-cycle

---

## Phase 3: Programmatic Backtest API Extension

`qengine/research/backtest.py` already provides an isolated `backtest()` function. Extend it.

### Modify: `qengine/research/backtest.py`

**Add `framework_config` parameter to `backtest()` and `_isolated_backtest()`:**
```python
def backtest(..., framework_config: dict = None) -> dict:
```

**Thread it into config before simulator runs:**
```python
if framework_config:
    config['framework'] = framework_config
```

**After simulator, collect framework stats (already handled by `_generate_outputs` from Phase 2).**

### Verify
- Call `research.backtest.backtest()` with `framework_config={enabled: True}`
- Verify result dict contains `framework_stats` key
- Call without → no `framework_stats` key

---

## Phase 4: Autopilot Orchestrator — `qengine/autopilot/`

### Create Files

| File | Class | Purpose |
|------|-------|---------|
| `qengine/autopilot/__init__.py` | — | Exports AutopilotRunner |
| `qengine/autopilot/runner.py` | `AutopilotRunner` | Main loop: think → config → execute → learn → persist → publish |
| `qengine/autopilot/brain.py` | `Brain` | Bayesian optimization over HP space (optuna or simple TPE). `suggest()` → config, `report()` ← results |
| `qengine/autopilot/learner.py` | `Learner` | Updates Q-table + danger scorer from framework_stats |
| `qengine/autopilot/state.py` | `AutopilotState` | Persistent state: Q-table, scorer, iteration history, best config. JSON + numpy save/load |

### Runner Loop
```python
class AutopilotRunner:
    def run(self, max_iterations=100):
        while iteration < max_iterations and is_process_active():
            hp = self.brain.suggest(self.state)
            result = research.backtest.backtest(
                config={...}, routes=[...], candles=self.candles,
                framework_config={'enabled': True, **self.fw_config},
                hyperparameters=hp,
                generate_equity_curve=True,
            )
            self.learner.update(result.get('framework_stats', {}), self.state)
            self.brain.report(result['metrics'], self.state)
            self.state.save()
            sync_publish('autopilot.iteration', {
                'iteration': iteration,
                'metrics': result['metrics'],
                'hyperparameters': hp,
                'framework_stats': result.get('framework_stats'),
            })
```

### Controller: `qengine/controllers/autopilot_controller.py`
- `POST /autopilot` → `process_manager.add_task(autopilot_runner.run, ...)`
- `POST /autopilot/cancel` → `process_manager.cancel_process(id)`
- `GET /autopilot/state/{id}` → return current state from file

### Register in `qengine/__init__.py`
- Add autopilot_controller router to FastAPI app

### Verify
- Unit test Brain: suggestions vary, reports update prior
- Integration: 3-iteration loop on small date range, verify state persistence
- Cancel mid-run, resume from saved state

---

## Phase 5: Frontend Extensions — `Backtest.vue`

All changes conditional — `v-if="frameworkStats"` guards. No new route/tab.

### Config Panel (after Hyperparameters section, ~line 248)

New collapsible "Framework" section:
- Toggle: `form.frameworkEnabled` (checkbox)
- When enabled, show:
  - Entry Gate toggle + gate percentile slider (default 75)
  - Q-Abort toggle
  - Danger Scorer toggle (always on when framework enabled)

### Request Payload (in `runBacktest()`)
```javascript
if (form.frameworkEnabled) {
  payload.config.framework = {
    enabled: true,
    entry_gate: form.frameworkEntryGate,
    q_abort: form.frameworkQAbort,
    gate_percentile: form.frameworkGatePercentile,
  }
}
```

### WebSocket Handler — add `framework_stats` event
```javascript
else if (event === 'backtest.framework_stats') {
  frameworkStatsData.value = data
}
```

### Summary Tab — new "Framework Decisions" section
After existing metric groups, `v-if="frameworkStats"`:
- Gate Checks, Entries Blocked, Entries Allowed, Block Rate
- Aborts Triggered, Abort Rate
- Avg Danger @ Entry, Avg Danger @ Exit

### Charts Tab — danger score time-series
Below existing equity/floating_pnl/margin charts:
- New synced chart: "Danger Score" using Lightweight Charts
- Only renders when `frameworkStats?.danger_scores?.length`

### Sessions Tab — extra columns
When `frameworkStats` present:
- Danger @ Entry, Gate Decision (pass/block), Abort Decision (continue/abort)

### Backend: Publish framework_stats via WebSocket
In `backtest_mode.py` result publishing block (after sessions, before metrics):
```python
if result.get('framework_stats'):
    sync_publish('framework_stats', result['framework_stats'], compression=True)
```

### Verify
- Toggle framework checkbox → section appears/hides
- Run backtest with framework → Framework Decisions section in Summary
- Danger chart renders below equity charts
- Sessions table shows extra columns
- Without framework → zero visual change

---

## Dependency Order

```
Phase 1 (Framework Core)
    ↓
Phase 2 (Strategy Hooks) → Phase 3 (Programmatic API)
                                ↓
                          Phase 4 (Autopilot)
    ↓
Phase 5 (Frontend) — can start after Phase 2+3
```

## Critical Files

| File | Action | Phase |
|------|--------|-------|
| `qengine/framework/__init__.py` | Create | 1 |
| `qengine/framework/danger_scorer.py` | Create | 1 |
| `qengine/framework/q_abort.py` | Create | 1 |
| `qengine/framework/entry_gate.py` | Create | 1 |
| `qengine/framework/pilot.py` | Create | 1 |
| `qengine/framework/stats.py` | Create | 1 |
| `qengine/strategies/Strategy.py` | Modify (~15 lines) | 2 |
| `qengine/modes/backtest_mode.py` | Modify (~10 lines in `_prepare_routes` + `_generate_outputs`) | 2 |
| `qengine/config.py` | Modify (~3 lines in `set_config`) | 2 |
| `qengine/research/backtest.py` | Modify (~5 lines, add `framework_config` param) | 3 |
| `qengine/autopilot/__init__.py` | Create | 4 |
| `qengine/autopilot/runner.py` | Create | 4 |
| `qengine/autopilot/brain.py` | Create | 4 |
| `qengine/autopilot/learner.py` | Create | 4 |
| `qengine/autopilot/state.py` | Create | 4 |
| `qengine/controllers/autopilot_controller.py` | Create | 4 |
| `frontend/src/views/Backtest.vue` | Modify (config section + results display) | 5 |

## Key Design Decisions

1. **Abort before `update_position()`**: Prevents strategy from placing new hedge orders that would immediately be cancelled
2. **Gate suppresses signals, doesn't skip computation**: Strategy still computes should_long/should_short (updating internal state) but orders aren't placed
3. **`on_cycle_end` in `_on_close_position`**: Natural place — closed_trade.pnl is the Q-learning reward
4. **Framework attached in `_prepare_routes()`**: After `_init_objects()` when position/broker are ready
5. **`research/backtest.py` as programmatic API**: Already exists as a pure function — just thread framework_config through
6. **Stats separate from metrics**: `result['framework_stats']` keeps existing `pickMetrics()` pattern untouched
