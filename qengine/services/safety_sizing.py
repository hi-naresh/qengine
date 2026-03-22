"""
Safety Sizing Module (M1)
=========================
Pure arithmetic safety layer for martingale/grid-hedge strategies.
Calculates worst-case exposure and dynamically sizes positions
to ensure finite balance survives losing streaks.

Always active. Cannot be disabled. <1ms latency.
"""


class SafetySizing:
    """
    Given current balance and hedge parameters, compute:
    1. Maximum safe initial_size
    2. Whether a proposed cycle is affordable
    3. Dynamic size scaling as balance changes
    """

    def __init__(self, max_risk_per_cycle_pct: float = 0.15,
                 max_total_exposure_pct: float = 0.50,
                 margin_buffer_pct: float = 0.20):
        """
        Args:
            max_risk_per_cycle_pct: Max fraction of balance at risk per hedge cycle (default 15%)
            max_total_exposure_pct: Max fraction of balance in open exposure (default 50%)
            margin_buffer_pct: Reserve fraction of balance as margin buffer (default 20%)
        """
        self.max_risk_per_cycle_pct = max_risk_per_cycle_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.margin_buffer_pct = margin_buffer_pct

    def max_exposure_units(self, initial_size: float, multiplier: float,
                           max_levels: int) -> float:
        """Total units committed if ALL levels fire (geometric series)."""
        if multiplier == 1.0:
            return initial_size * max_levels
        return initial_size * (multiplier ** max_levels - 1) / (multiplier - 1)

    def worst_case_loss(self, initial_size: float, multiplier: float,
                        max_levels: int, hedge_pips: float,
                        pip_value: float) -> float:
        """
        Dollar loss if all levels fire and final level also loses.

        Each level loses: size_at_level * hedge_pips * pip_value
        Total = sum over all levels.
        """
        total_loss = 0.0
        for level in range(max_levels):
            size = initial_size * (multiplier ** level)
            total_loss += size * hedge_pips * pip_value
        return total_loss

    def max_safe_initial_size(self, balance: float, multiplier: float,
                               max_levels: int, hedge_pips: float,
                               pip_value: float,
                               max_risk_pct: float = None) -> float:
        """
        Largest initial_size where worst-case loss < max_risk_pct of balance.

        Worst-case loss is linear in initial_size, so we solve:
          worst_case_loss(1.0, ...) * x = balance * max_risk_pct
          x = (balance * max_risk_pct) / worst_case_loss(1.0, ...)
        """
        if max_risk_pct is None:
            max_risk_pct = self.max_risk_per_cycle_pct

        unit_loss = self.worst_case_loss(1.0, multiplier, max_levels,
                                          hedge_pips, pip_value)
        if unit_loss <= 0:
            return 0.0
        return (balance * max_risk_pct) / unit_loss

    def can_afford_cycle(self, balance: float, initial_size: float,
                          multiplier: float, max_levels: int,
                          hedge_pips: float, pip_value: float,
                          max_risk_pct: float = None) -> bool:
        """Binary check: is this cycle safe to start?"""
        if max_risk_pct is None:
            max_risk_pct = self.max_risk_per_cycle_pct

        worst = self.worst_case_loss(initial_size, multiplier, max_levels,
                                      hedge_pips, pip_value)
        return worst <= balance * max_risk_pct

    def dynamic_size(self, balance: float, base_size: float,
                      multiplier: float, max_levels: int,
                      hedge_pips: float, pip_value: float,
                      max_risk_pct: float = None) -> float:
        """Scale base_size down if it exceeds safety limit. Never scales up."""
        max_safe = self.max_safe_initial_size(
            balance, multiplier, max_levels, hedge_pips, pip_value, max_risk_pct
        )
        return min(base_size, max_safe)

    def exposure_ratio(self, initial_size: float, multiplier: float,
                        max_levels: int, balance: float,
                        hedge_pips: float, pip_value: float) -> float:
        """Worst-case loss as fraction of balance. >1.0 means certain ruin."""
        if balance <= 0:
            return float('inf')
        worst = self.worst_case_loss(initial_size, multiplier, max_levels,
                                      hedge_pips, pip_value)
        return worst / balance

    def levels_affordable(self, balance: float, initial_size: float,
                           multiplier: float, hedge_pips: float,
                           pip_value: float,
                           max_risk_pct: float = None) -> int:
        """How many hedge levels can the balance actually support?"""
        if max_risk_pct is None:
            max_risk_pct = self.max_risk_per_cycle_pct

        max_loss = balance * max_risk_pct
        cumulative = 0.0
        for level in range(50):  # hard cap
            size = initial_size * (multiplier ** level)
            cumulative += size * hedge_pips * pip_value
            if cumulative > max_loss:
                return level
        return 50
