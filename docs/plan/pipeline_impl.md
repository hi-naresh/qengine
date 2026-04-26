# Pipeline System Refactor Plan

## Context

qengine needs a **pluggable pipeline system** where multiple intelligent pipelines can be built, swapped, stacked, and run on any strategy — in backtesting and live trading. If one pipeline doesn't work, create another. The system should be flexible enough to inject one or many pipelines simultaneously.

**Decision: Approach B** — pipeline hooks inject into Strategy base class. No PilotStrategy subclass. Any strategy gains intelligence automatically via `self._pipelines`.

---

## Core Architecture Change: From Hardcoded to Pluggable

**Old (hardcoded):**
```python
self._framework = GridPilot(config)  # only one, tightly coupled
```

**New (pluggable):**
```python
# Abstract contract — any pipeline implements this
class Pipeline(ABC):
    name: str
    def on_before(self, strategy): ...
    def gate_entry(self) -> bool: ...
    def should_abort(self, strategy) -> bool: ...
    def on_cycle_end(self, pnl, strategy): ...
    def stats(self) -> dict: ...

# Strategy gets a list — zero, one, or many
self._pipelines: list[Pipeline] = []
```

**Composition rules when multiple pipelines are stacked:**
- `on_before()` → all called in order
- `gate_entry()` → **AND** — all must allow (any veto blocks)
- `should_abort()` → **OR** — any can trigger abort
- `on_cycle_end()` → all called in order (each learns from outcome)
- `stats` → collected per-pipeline by name

---

## Directory Structure

```
qengine/framework/
    __init__.py              # Exports Pipeline ABC, registry, load helpers
    base.py                  # Pipeline ABC + PipelineStack (multi-pipeline runner)
    registry.py              # Pipeline registry (discover, list, instantiate by name)
    stats.py                 # PipelineStats base dataclass

    components/              # Reusable building blocks (shared across pipelines)
        __init__.py
        danger_scorer.py     # DangerScorer (Welford + sigmoid)
        q_abort.py           # QAbort (tabular Q-learning)
        entry_gate.py        # EntryGate (percentile threshold)

    pipelines/               # Concrete pipeline implementations
        __init__.py
        grid_pilot.py        # GridPilot: danger scorer + Q-abort + entry gate
        # Future:
        # momentum_pilot.py  # Momentum-based entry timing
        # regime_pilot.py    # HMM regime detection + conditional params
        # ml_pilot.py        # Neural net signal filtering

qengine/autopilot/           # Orchestrator (uses pipelines)
    __init__.py
    runner.py                # AutopilotRunner — session loop
    brain.py                 # Brain — Bayesian HP optimization
    learner.py               # Learner — updates pipeline state from results
    state.py                 # AutopilotState — persistent across restarts
```

---

## Phase 1: Pipeline Abstraction + First Pipeline

### 1a. Pipeline Contract — `qengine/framework/base.py`

```python
from abc import ABC, abstractmethod
from typing import Optional

class Pipeline(ABC):
    """Base class for all pipelines. Implement this to create a new pipeline."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique pipeline identifier (e.g. 'grid_pilot', 'momentum_pilot')."""

    def on_before(self, strategy) -> None:
        """Called every candle, before strategy logic. Update internal state."""
        pass

    def gate_entry(self) -> bool:
        """Should the strategy be allowed to enter? True=allow, False=block."""
        return True

    def should_abort(self, strategy) -> bool:
        """Should the current position be force-closed? True=abort."""
        return False

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Called when a position closes. Use for learning/reward updates."""
        pass

    def on_open_position(self, strategy) -> None:
        """Called when a position opens. Use for tracking entry state."""
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """Return pipeline-specific stats for result payload."""

    def save_state(self, path: str) -> None:
        """Persist learned state to disk."""
        pass

    def load_state(self, path: str) -> None:
        """Restore learned state from disk."""
        pass

    @classmethod
    def default_config(cls) -> dict:
        """Default configuration for this pipeline (shown in frontend)."""
        return {}
```

### 1b. PipelineStack — `qengine/framework/base.py` (same file)

```python
class PipelineStack:
    """Manages multiple pipelines on a single strategy. Handles composition rules."""

    def __init__(self, pipelines: list[Pipeline]):
        self.pipelines = pipelines

    def on_before(self, strategy):
        for p in self.pipelines:
            p.on_before(strategy)

    def gate_entry(self) -> bool:
        # AND rule: all must allow
        return all(p.gate_entry() for p in self.pipelines)

    def should_abort(self, strategy) -> bool:
        # OR rule: any can abort
        return any(p.should_abort(strategy) for p in self.pipelines)

    def on_cycle_end(self, pnl, strategy):
        for p in self.pipelines:
            p.on_cycle_end(pnl, strategy)

    def on_open_position(self, strategy):
        for p in self.pipelines:
            p.on_open_position(strategy)

    def get_stats(self) -> dict:
        # Keyed by pipeline name
        return {p.name: p.get_stats() for p in self.pipelines}

    def save_state(self, base_path):
        for p in self.pipelines:
            p.save_state(f"{base_path}/{p.name}")

    def load_state(self, base_path):
        for p in self.pipelines:
            p.load_state(f"{base_path}/{p.name}")
```

### 1c. Pipeline Registry — `qengine/framework/registry.py`

```python
_REGISTRY: dict[str, type[Pipeline]] = {}

def register(cls: type[Pipeline]) -> type[Pipeline]:
    """Decorator to register a pipeline class."""
    _REGISTRY[cls.name] = cls
    return cls

def get_pipeline(name: str) -> type[Pipeline]:
    """Get pipeline class by name."""
    return _REGISTRY[name]

def list_pipelines() -> list[dict]:
    """List all registered pipelines with name + default_config (for frontend dropdown)."""
    return [
        {'name': cls.name, 'config': cls.default_config()}
        for cls in _REGISTRY.values()
    ]

def create_pipelines(configs: list[dict]) -> PipelineStack:
    """Instantiate pipelines from config list. Returns PipelineStack."""
    pipelines = []
    for conf in configs:
        cls = _REGISTRY[conf['name']]
        pipelines.append(cls(conf))
    return PipelineStack(pipelines)
```

### 1d. Reusable Components — `qengine/framework/components/`

These are building blocks that any pipeline can compose:

| File | Class | Purpose |
|------|-------|---------|
| `danger_scorer.py` | `DangerScorer` | 7 weighted features → Welford → sigmoid [0,1] |
| `q_abort.py` | `QAbort` | Tabular Q-learning (1625 states × 2 actions) |
| `entry_gate.py` | `EntryGate` | Percentile-based entry blocking |

Same specs as before — but now they're **components**, not the pipeline itself. Any pipeline can pick and choose which components to use.

### 1e. First Pipeline: GridPilot — `qengine/framework/pipelines/grid_pilot.py`

```python
from qengine.framework.base import Pipeline
from qengine.framework.registry import register
from qengine.framework.components import DangerScorer, QAbort, EntryGate

@register
class GridPilot(Pipeline):
    name = 'grid_pilot'

    def __init__(self, config: dict):
        self.scorer = DangerScorer(config.get('scorer', {}))
        self.gate = EntryGate(config.get('gate', {}))
        self.abort = QAbort(config.get('abort', {}))
        self._stats = {...}

    def on_before(self, strategy):
        score = self.scorer.update(strategy)
        self.gate.observe(score)

    def gate_entry(self) -> bool:
        return self.gate.should_allow(self.scorer.current_score)

    def should_abort(self, strategy) -> bool:
        return self.abort.decide(strategy) == 'abort'

    def on_cycle_end(self, pnl, strategy):
        self.abort.learn(pnl, strategy)

    def get_stats(self) -> dict:
        return {**self._stats, 'scorer': self.scorer.stats, ...}

    @classmethod
    def default_config(cls) -> dict:
        return {
            'scorer': {'warmup': 50},
            'gate': {'percentile': 75, 'enabled': True},
            'abort': {'enabled': True, 'alpha': 0.01, 'gamma': 0.95, 'epsilon': 0.0},
        }
```

### Verify Phase 1
- Instantiate GridPilot with default config → all components initialize
- PipelineStack with 1 pipeline → same behavior as single pipeline
- PipelineStack with 2 mock pipelines → AND/OR rules work
- Registry: register, list, create by name
- No qengine imports needed for unit tests

---

## Phase 2: Strategy Hook Injection

**Same 6 touch points as before, but now `self._pipelines: PipelineStack | None` instead of `self._framework`.**

### Modify: `qengine/strategies/Strategy.py`

**1. `__init__` — add pipelines slot**
```python
self._pipelines = None  # PipelineStack instance, set externally
```

**2. `_execute()` — call on_before**
```python
self.before()
if self._pipelines:
    self._pipelines.on_before(self)
self._check()
```

**3. `_check()` — gate entry**
```python
if self._pipelines and (should_long or should_short):
    if not self._pipelines.gate_entry():
        should_long = False
        should_short = False
```

**4. `_update_position()` — abort check**
```python
if self._pipelines and self._pipelines.should_abort(self):
    if self.position.is_cfd_mode and hasattr(self, 'close_all_tickets'):
        self.close_all_tickets(self.price)
    else:
        self.broker.reduce_position_at(self.position.qty, self.price, self.price)
    return
```

**5. `_on_close_position()` — learning**
```python
if self._pipelines:
    self._pipelines.on_cycle_end(closed_trade.pnl, self)
```

**6. `_on_open_position()` — track entry state**
```python
if self._pipelines:
    self._pipelines.on_open_position(self)
```

### Modify: `qengine/modes/backtest_mode.py`

**In `_prepare_routes()` — use registry to create pipelines:**
```python
from qengine.framework.registry import create_pipelines

fw_conf = config.get('app', {}).get('pipelines')  # list of pipeline configs
if fw_conf:
    r.strategy._pipelines = create_pipelines(fw_conf)
```

**In `_generate_outputs()` — collect per-pipeline stats:**
```python
for r in router.routes:
    if getattr(r.strategy, '_pipelines', None):
        result.setdefault('pipeline_stats', {})[
            f"{r.exchange}-{r.symbol}"
        ] = r.strategy._pipelines.get_stats()
```

### Modify: `qengine/config.py`
```python
if 'pipelines' in conf:
    config['app']['pipelines'] = conf['pipelines']
```

### Config Format (what frontend sends)
```json
{
  "pipelines": [
    {
      "name": "grid_pilot",
      "scorer": {"warmup": 50},
      "gate": {"percentile": 75, "enabled": true},
      "abort": {"enabled": true, "alpha": 0.01}
    }
  ]
}
```

Multiple pipelines:
```json
{
  "pipelines": [
    {"name": "grid_pilot", "gate": {"percentile": 80}},
    {"name": "momentum_pilot", "lookback": 20}
  ]
}
```

### Also: Live mode hook — `qengine/modes/live_mode.py`

Same pipeline attachment in live mode's strategy initialization:
```python
fw_conf = config.get('app', {}).get('pipelines')
if fw_conf:
    from qengine.framework.registry import create_pipelines
    r.strategy._pipelines = create_pipelines(fw_conf)
```

**Same pipeline code runs in backtest AND live — no mode-specific logic needed.**

### New API endpoint for pipeline discovery
```python
# qengine/controllers/framework_controller.py
@router.get("/pipelines")
def list_pipelines():
    """Return all registered pipelines + their default configs."""
    from qengine.framework.registry import list_pipelines
    return list_pipelines()
```

### Verify Phase 2
- Backtest with no pipelines → identical to current behavior
- Backtest with `pipelines: [{name: "grid_pilot"}]` → hooks fire
- Backtest with 2 pipelines → both fire, AND/OR rules work
- Live mode with pipeline → same behavior as backtest
- `GET /pipelines` → returns available pipeline list

---

## Phase 3: Programmatic Backtest API Extension

### Modify: `qengine/research/backtest.py`

```python
def backtest(..., pipelines: list[dict] = None) -> dict:
```

Thread into config:
```python
if pipelines:
    config['pipelines'] = pipelines
```

Stats already collected by `_generate_outputs()` from Phase 2.

### Verify
- `backtest(pipelines=[{'name': 'grid_pilot'}])` → result has `pipeline_stats`
- `backtest()` → no `pipeline_stats` key

---

## Phase 4: Autopilot Orchestrator — `qengine/autopilot/`

Same structure as before, but pipeline-aware:

| File | Class | Purpose |
|------|-------|---------|
| `runner.py` | `AutopilotRunner` | Session loop — uses any pipeline(s) |
| `brain.py` | `Brain` | Bayesian optimization over HP space + pipeline config |
| `learner.py` | `Learner` | Updates pipeline state from per-pipeline stats |
| `state.py` | `AutopilotState` | Persists: pipeline states, iteration history, best config |

### Runner Loop (pipeline-agnostic)
```python
class AutopilotRunner:
    def __init__(self, pipeline_configs: list[dict], ...):
        self.pipeline_configs = pipeline_configs  # which pipelines to use

    def run(self, max_iterations=100):
        while iteration < max_iterations and is_process_active():
            hp = self.brain.suggest(self.state)
            result = research.backtest.backtest(
                config={...}, routes=[...], candles=self.candles,
                pipelines=self.pipeline_configs,
                hyperparameters=hp,
            )
            # Learn from per-pipeline stats
            self.learner.update(result.get('pipeline_stats', {}), self.state)
            self.brain.report(result['metrics'], self.state)
            self.state.save()
            self.publish_progress(iteration, result)
```

### Controller: `qengine/controllers/autopilot_controller.py`
```python
@router.post("")
def start_autopilot(request_json: AutopilotRequestJson):
    # request_json.pipelines = [{"name": "grid_pilot", ...}]
    process_manager.add_task(run_autopilot, request_json.id, ...)

@router.get("/pipelines")
def list_available():
    return list_pipelines()
```

### Verify
- Run 3-iteration loop with grid_pilot → state persists
- Run with a different pipeline → same loop works
- Cancel mid-run, resume → pipeline state loaded correctly

---

## Phase 5: Frontend Extensions — `Backtest.vue`

### Config Panel — Pipeline Section (after Hyperparameters)

```vue
<!-- Pipeline Configuration -->
<div class="pt-2">
  <div class="flex items-center justify-between mb-1">
    <label class="label mb-0">Pipelines</label>
    <button @click="addPipeline" class="text-xs text-brand-400">+ Add Pipeline</button>
  </div>

  <div v-for="(pl, idx) in form.pipelines" :key="idx" class="mb-2 p-2 bg-surface-800 rounded">
    <div class="flex items-center gap-2 mb-1">
      <select v-model="pl.name" class="select text-xs flex-1" @change="onPipelineChange(idx)">
        <option v-for="p in availablePipelines" :key="p.name" :value="p.name">{{ p.name }}</option>
      </select>
      <button @click="removePipeline(idx)" class="text-surface-500 hover:text-red-400">&times;</button>
    </div>
    <!-- Pipeline-specific config fields (loaded from default_config) -->
    <div v-for="(val, key) in pl.config" :key="key" class="flex gap-2 items-center text-xs">
      <span class="text-surface-400 w-24">{{ key }}</span>
      <input v-model="pl.config[key]" class="input text-xs py-1 flex-1" />
    </div>
  </div>
</div>
```

**On mount**: fetch `GET /pipelines` → populate `availablePipelines` dropdown.

### Request Payload
```javascript
if (form.pipelines.length) {
  payload.config.pipelines = form.pipelines.map(pl => ({
    name: pl.name,
    ...pl.config
  }))
}
```

### Summary Tab — Per-Pipeline Stats
```vue
<!-- Pipeline Stats (per pipeline) -->
<div v-for="(stats, pipelineName) in pipelineStats" :key="pipelineName" class="mb-4">
  <h3 class="text-xs font-semibold text-surface-500 mb-2">
    Pipeline: {{ pipelineName }}
  </h3>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
    <div v-for="(val, key) in stats" :key="key" class="p-2 bg-surface-800 rounded">
      <div class="text-surface-500 text-xs">{{ key }}</div>
      <div class="font-mono text-surface-100">{{ formatMetric(val) }}</div>
    </div>
  </div>
</div>
```

### Charts Tab — Pipeline-specific charts
Each pipeline's stats can include time-series data (e.g. danger_scores for GridPilot). Render conditionally.

### WebSocket Handler
```javascript
else if (event === 'backtest.pipeline_stats') {
  pipelineStatsData.value = data
}
```

### Backend: Publish pipeline_stats
```python
if result.get('pipeline_stats'):
    sync_publish('pipeline_stats', result['pipeline_stats'], compression=True)
```

### Verify
- `GET /pipelines` → dropdown populated
- Add pipeline → config fields appear
- Add 2 pipelines → both shown
- Run backtest → per-pipeline stats in Summary
- No pipelines selected → no pipeline UI

---

## Dependency Order

```
Phase 1a (Pipeline ABC + Stack + Registry)
Phase 1b (Components: DangerScorer, QAbort, EntryGate)
Phase 1c (First pipeline: GridPilot)
    ↓
Phase 2 (Strategy hooks + backtest/live attachment)
    ↓
Phase 3 (Programmatic API extension)
    ↓
Phase 4 (Autopilot orchestrator)

Phase 5 (Frontend) — can start after Phase 2
```

## Critical Files

| File | Action | Phase |
|------|--------|-------|
| `qengine/framework/__init__.py` | Create | 1a |
| `qengine/framework/base.py` | Create (Pipeline ABC + PipelineStack) | 1a |
| `qengine/framework/registry.py` | Create | 1a |
| `qengine/framework/stats.py` | Create | 1a |
| `qengine/framework/components/__init__.py` | Create | 1b |
| `qengine/framework/components/danger_scorer.py` | Create | 1b |
| `qengine/framework/components/q_abort.py` | Create | 1b |
| `qengine/framework/components/entry_gate.py` | Create | 1b |
| `qengine/framework/pipelines/__init__.py` | Create | 1c |
| `qengine/framework/pipelines/grid_pilot.py` | Create | 1c |
| `qengine/strategies/Strategy.py` | Modify (~15 lines) | 2 |
| `qengine/modes/backtest_mode.py` | Modify (~10 lines) | 2 |
| `qengine/modes/live_mode.py` | Modify (~5 lines) | 2 |
| `qengine/config.py` | Modify (~3 lines) | 2 |
| `qengine/controllers/framework_controller.py` | Create (`GET /pipelines`) | 2 |
| `qengine/research/backtest.py` | Modify (~5 lines) | 3 |
| `qengine/autopilot/__init__.py` | Create | 4 |
| `qengine/autopilot/runner.py` | Create | 4 |
| `qengine/autopilot/brain.py` | Create | 4 |
| `qengine/autopilot/learner.py` | Create | 4 |
| `qengine/autopilot/state.py` | Create | 4 |
| `qengine/controllers/autopilot_controller.py` | Create | 4 |
| `frontend/src/views/Backtest.vue` | Modify | 5 |

## Key Design Decisions

1. **Pipeline ABC, not hardcoded class**: Any pipeline implements the same 6-method contract. Engine doesn't know or care which pipeline is running.
2. **PipelineStack composition**: AND for gates (all must allow), OR for aborts (any can trigger). Multiple pipelines work naturally.
3. **Components are shared, not pipeline-specific**: DangerScorer, QAbort, EntryGate can be reused by any pipeline. GridPilot composes all three; a future MomentumPilot might only use EntryGate.
4. **Registry pattern**: Pipelines self-register via `@register` decorator. Frontend discovers them via `GET /pipelines`. Adding a new pipeline = one file + decorator.
5. **Same code, backtest and live**: Pipeline attachment happens in `_prepare_routes()` (backtest) and live mode init — same `create_pipelines()` call. Pipeline doesn't know which mode it's in.
6. **Config is a list of dicts**: `[{"name": "grid_pilot", ...}]` — naturally supports zero, one, or many pipelines.
7. **Stats keyed by pipeline name**: Result payload: `{"pipeline_stats": {"OANDA-EUR-USD": {"grid_pilot": {...}, "momentum_pilot": {...}}}}`.

## Creating a New Pipeline (developer workflow)

```python
# qengine/framework/pipelines/my_pipeline.py
from qengine.framework.base import Pipeline
from qengine.framework.registry import register

@register
class MyPipeline(Pipeline):
    name = 'my_pipeline'

    def __init__(self, config: dict):
        self.threshold = config.get('threshold', 0.5)

    def gate_entry(self) -> bool:
        return self.some_condition()

    def get_stats(self) -> dict:
        return {'decisions': self.count}

    @classmethod
    def default_config(cls) -> dict:
        return {'threshold': 0.5}
```

That's it. One file, `@register`, implements the contract. Immediately available in frontend dropdown, usable in backtest and live, composable with other pipelines.
