"""
Learner — updates pipeline learned state (Q-tables, scorer weights) across iterations.

After each backtest iteration, the learner can:
1. Carry forward Q-table updates from the pipeline's QAbort
2. Accumulate danger scorer statistics
3. Save/load learned state for resume
"""
import os


class Learner:
    """
    Carries pipeline learned state across autopilot iterations.

    Between iterations, the learner saves pipeline state from the just-finished
    backtest and loads it into the next iteration's pipeline config, enabling
    cumulative learning across repeated backtests.
    """

    def __init__(self, state_dir: str):
        self.state_dir = os.path.join(state_dir, 'pipeline_state')
        os.makedirs(self.state_dir, exist_ok=True)

    def save_from_strategies(self, routes):
        """
        After a backtest completes, save pipeline state from strategies.
        Called with the router.routes list while the process state is still alive.
        """
        for r in routes:
            pipelines = getattr(r.strategy, '_pipelines', None)
            if pipelines is None:
                continue
            for p in pipelines.pipelines:
                p_dir = os.path.join(self.state_dir, p.name)
                p.save_state(p_dir)

    def get_pipeline_state_dir(self, pipeline_name: str) -> str:
        """Return the state directory for a specific pipeline (for load_state)."""
        return os.path.join(self.state_dir, pipeline_name)

    @property
    def has_saved_state(self) -> bool:
        return os.path.exists(self.state_dir) and len(os.listdir(self.state_dir)) > 0
