"""
AgentCoordinator — lightweight heuristic controller for GA hyper-parameters.

Implements the "multi-agent" logic from Budiharto & Prasetyo (2025) in a
deliberately simple if-then form (the paper describes agents adjusting GA
knobs based on fitness feedback + market microstructure; we deliver the same
behaviour without the RL overhead).

Adjustment knobs:
    mutation_sigma  (exploration magnitude)
    crossover_rate  (recombination intensity)
    tournament_k    (selection pressure)

Inputs per retrain:
    best_fitness          : best individual fitness this retrain
    fitness_std           : std across the population
    market_vol_percentile : current NATR vs its rolling distribution (0..1)

Rules (documented in-line below).
"""

from typing import Any, Dict, List, Optional


class AgentCoordinator:
    def __init__(self, cfg: dict, ga_cfg: dict):
        self.cfg = cfg
        # Current values — these mutate over the run
        self.mutation_sigma = float(ga_cfg.get('mutation_sigma', 0.05))
        self.crossover_rate = float(ga_cfg.get('crossover_rate', 0.7))
        self.tournament_k = int(ga_cfg.get('tournament_k', 3))

        # History
        self.best_fitness_history: List[float] = []
        self.adjustment_log: List[Dict[str, Any]] = []
        self._stall_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def adjust(
        self,
        retrain_idx: int,
        best_fitness: float,
        fitness_std: float,
        market_vol_percentile: Optional[float],
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Consume retrain feedback and produce new GA hyper-parameters.

        Returns a dict describing the adjustment (added to adjustment_log).
        """
        reasons: List[str] = []

        # --- 1. Fitness trend -------------------------------------------
        improved = True
        if self.best_fitness_history:
            prev_best = max(self.best_fitness_history)
            if best_fitness - prev_best < self.cfg['stall_improvement_eps']:
                improved = False

        if improved:
            self._stall_count = 0
        else:
            self._stall_count += 1

        old_sigma = self.mutation_sigma
        if self._stall_count >= self.cfg['stall_retrains']:
            # Plateau -> jolt exploration
            self.mutation_sigma = min(
                self.cfg['mutation_sigma_max'],
                self.mutation_sigma * self.cfg['mutation_sigma_boost'],
            )
            reasons.append(
                f'stall({self._stall_count}) -> sigma x{self.cfg["mutation_sigma_boost"]}')
            self._stall_count = 0

        # --- 2. Fitness volatility --------------------------------------
        # Low std across pop = converged; raise mutation to diversify.
        # High std = already exploring; damp mutation.
        if fitness_std is not None:
            if fitness_std < 1.0:        # empirical threshold for composite fitness
                self.mutation_sigma = min(
                    self.cfg['mutation_sigma_max'],
                    self.mutation_sigma * 1.1,
                )
                reasons.append('low_pop_std -> sigma+10%')
            elif fitness_std > 25.0:
                self.mutation_sigma = max(
                    self.cfg['mutation_sigma_min'],
                    self.mutation_sigma * self.cfg['mutation_sigma_damp'],
                )
                reasons.append('high_pop_std -> sigma dampened')

        self.mutation_sigma = float(max(
            self.cfg['mutation_sigma_min'],
            min(self.cfg['mutation_sigma_max'], self.mutation_sigma),
        ))

        # --- 3. Market volatility agent ---------------------------------
        # Elevated vol -> tighten tournament (more selection pressure).
        # Compressed vol -> loosen tournament (more exploration of tail configs).
        old_k = self.tournament_k
        old_cross = self.crossover_rate
        if market_vol_percentile is not None:
            if market_vol_percentile >= self.cfg['vol_high_quantile']:
                self.tournament_k = min(self.cfg['tournament_k_max'],
                                        self.tournament_k + 1)
                self.crossover_rate = min(
                    self.cfg['crossover_rate_max'],
                    self.crossover_rate + 0.05,
                )
                reasons.append(
                    f'vol_high({market_vol_percentile:.2f}) -> k+1, xover+0.05')
            elif market_vol_percentile <= self.cfg['vol_low_quantile']:
                self.tournament_k = max(self.cfg['tournament_k_min'],
                                        self.tournament_k - 1)
                self.crossover_rate = max(
                    self.cfg['crossover_rate_min'],
                    self.crossover_rate - 0.05,
                )
                reasons.append(
                    f'vol_low({market_vol_percentile:.2f}) -> k-1, xover-0.05')

        self.tournament_k = int(max(
            self.cfg['tournament_k_min'],
            min(self.cfg['tournament_k_max'], self.tournament_k),
        ))
        self.crossover_rate = float(max(
            self.cfg['crossover_rate_min'],
            min(self.cfg['crossover_rate_max'], self.crossover_rate),
        ))

        # --- 4. Record history ------------------------------------------
        self.best_fitness_history.append(float(best_fitness))

        rec: Dict[str, Any] = {
            'retrain': retrain_idx,
            'ts': timestamp,
            'best_fitness': round(float(best_fitness), 4),
            'fitness_std': round(float(fitness_std), 4) if fitness_std is not None else None,
            'vol_pctile': round(float(market_vol_percentile), 4) if market_vol_percentile is not None else None,
            'sigma_before': round(old_sigma, 4),
            'sigma_after': round(self.mutation_sigma, 4),
            'crossover_before': round(old_cross, 4),
            'crossover_after': round(self.crossover_rate, 4),
            'tournament_k_before': old_k,
            'tournament_k_after': self.tournament_k,
            'reasons': reasons or ['stable'],
            'improved': improved,
            'stall_count': self._stall_count,
        }
        self.adjustment_log.append(rec)
        return rec

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            'mutation_sigma': self.mutation_sigma,
            'crossover_rate': self.crossover_rate,
            'tournament_k': self.tournament_k,
            'best_fitness_history': list(self.best_fitness_history),
            'adjustment_log': list(self.adjustment_log),
            'stall_count': self._stall_count,
            'cfg': self.cfg,
        }

    @classmethod
    def from_dict(cls, d: dict, ga_cfg: dict) -> 'AgentCoordinator':
        coord = cls(d.get('cfg', {}) or {}, ga_cfg)
        coord.mutation_sigma = float(d.get('mutation_sigma', coord.mutation_sigma))
        coord.crossover_rate = float(d.get('crossover_rate', coord.crossover_rate))
        coord.tournament_k = int(d.get('tournament_k', coord.tournament_k))
        coord.best_fitness_history = list(d.get('best_fitness_history', []))
        coord.adjustment_log = list(d.get('adjustment_log', []))
        coord._stall_count = int(d.get('stall_count', 0))
        return coord
