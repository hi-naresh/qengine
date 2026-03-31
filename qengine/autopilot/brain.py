"""
Bayesian optimization brain for autopilot hyperparameter search.

Uses Tree-structured Parzen Estimator (TPE) via optuna when available,
falls back to random search with shrinking bounds.
"""
import random
import math


class Brain:
    """
    Suggests hyperparameter configs and learns from results.

    hp_space: dict mapping param_name → {'low': float, 'high': float, 'type': 'float'|'int'|'log'}
    """

    def __init__(self, hp_space: dict, seed: int = 42):
        self.hp_space = hp_space
        self.seed = seed
        self._rng = random.Random(seed)
        self._study = None
        self._use_optuna = False
        self._trial_map = {}  # iteration → optuna trial

        if hp_space:
            self._try_init_optuna()

    def _try_init_optuna(self):
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            self._study = optuna.create_study(
                direction='maximize',
                sampler=optuna.samplers.TPESampler(seed=self.seed),
            )
            self._use_optuna = True
        except ImportError:
            pass

    def suggest(self, iteration: int) -> dict:
        """Return a hyperparameter config dict for this iteration."""
        if not self.hp_space:
            return {}

        if self._use_optuna:
            return self._suggest_optuna(iteration)
        return self._suggest_random()

    def _suggest_optuna(self, iteration: int) -> dict:
        import optuna
        trial = self._study.ask()
        self._trial_map[iteration] = trial
        hp = {}
        for name, spec in self.hp_space.items():
            low, high = spec['low'], spec['high']
            ptype = spec.get('type', 'float')
            if ptype == 'int':
                hp[name] = trial.suggest_int(name, int(low), int(high))
            elif ptype == 'log':
                hp[name] = trial.suggest_float(name, low, high, log=True)
            else:
                hp[name] = trial.suggest_float(name, low, high)
        return hp

    def _suggest_random(self) -> dict:
        hp = {}
        for name, spec in self.hp_space.items():
            low, high = spec['low'], spec['high']
            ptype = spec.get('type', 'float')
            if ptype == 'int':
                hp[name] = self._rng.randint(int(low), int(high))
            elif ptype == 'log':
                hp[name] = math.exp(self._rng.uniform(math.log(low), math.log(high)))
            else:
                hp[name] = self._rng.uniform(low, high)
        return hp

    def report(self, iteration: int, objective_value: float):
        """Report the result of an iteration back to the optimizer."""
        if self._use_optuna and iteration in self._trial_map:
            trial = self._trial_map.pop(iteration)
            self._study.tell(trial, objective_value)
