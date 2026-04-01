"""
Persistent state for autopilot sessions.

Tracks iteration history, best config, and pipeline learned state (Q-tables etc).
Saved as JSON + numpy files in a session directory.
"""
import os
import json
import time


class AutopilotState:
    """Persistent autopilot state — survives cancellation and resume."""

    def __init__(self, session_dir: str):
        self.session_dir = session_dir
        self.iteration = 0
        self.history = []          # [{iteration, metrics, hp, pipeline_stats, timestamp}, ...]
        self.best_metric = None    # best objective value seen
        self.best_config = None    # hp config that produced best_metric
        self.best_iteration = -1
        self.objective_key = 'net_profit_percentage'  # metric to optimize
        self.maximize = True       # True = higher is better

        os.makedirs(session_dir, exist_ok=True)

    def record(self, metrics: dict, hp: dict, pipeline_stats: dict = None):
        """Record one iteration result."""
        entry = {
            'iteration': self.iteration,
            'metrics': metrics,
            'hp': hp,
            'pipeline_stats': pipeline_stats,
            'timestamp': time.time(),
        }
        self.history.append(entry)

        obj = metrics.get(self.objective_key, 0) or 0
        if self.best_metric is None or (self.maximize and obj > self.best_metric) or (not self.maximize and obj < self.best_metric):
            self.best_metric = obj
            self.best_config = hp
            self.best_iteration = self.iteration

        self.iteration += 1

    def save(self):
        """Persist state to disk."""
        state = {
            'iteration': self.iteration,
            'history': self.history,
            'best_metric': self.best_metric,
            'best_config': self.best_config,
            'best_iteration': self.best_iteration,
            'objective_key': self.objective_key,
            'maximize': self.maximize,
        }
        path = os.path.join(self.session_dir, 'state.json')
        with open(path, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def load(self):
        """Resume from saved state."""
        path = os.path.join(self.session_dir, 'state.json')
        if not os.path.exists(path):
            return
        with open(path) as f:
            state = json.load(f)
        self.iteration = state.get('iteration', 0)
        self.history = state.get('history', [])
        self.best_metric = state.get('best_metric')
        self.best_config = state.get('best_config')
        self.best_iteration = state.get('best_iteration', -1)
        self.objective_key = state.get('objective_key', 'net_profit_percentage')
        self.maximize = state.get('maximize', True)

    @property
    def summary(self) -> dict:
        return {
            'iteration': self.iteration,
            'best_metric': self.best_metric,
            'best_config': self.best_config,
            'best_iteration': self.best_iteration,
            'total_iterations': len(self.history),
        }
