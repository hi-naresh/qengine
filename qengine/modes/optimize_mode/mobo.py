"""
Multi-Objective Bayesian Optimization (MOBO) for hedging strategies.

Uses Gaussian Process surrogate models to simultaneously optimize:
  Objective 1: Maximize net profit (or selected ratio)
  Objective 2: Minimize bust risk (max drawdown, bust count proxy)

With analytical constraints from the Surefire p*m formula:
  Risk = (p * m)^N / (m - 1)
  Hard constraint: p * m < 1

Built on scipy/numpy only (no PyTorch/BoTorch dependency).
Uses Ray for parallel backtest evaluation, same as the Optuna optimizer.
"""
import os
import json
import base64
from datetime import timedelta
from multiprocessing import cpu_count
from math import log10

import ray
import numpy as np
from scipy.spatial.distance import cdist
from scipy.linalg import cho_solve, cho_factor
from scipy.optimize import minimize as scipy_minimize
from scipy.stats import norm

import qengine.helpers as jh
import qengine.services.logger as logger
from qengine import exceptions
from qengine.config import config
from qengine.services.redis import sync_publish, is_process_active
from qengine.modes.optimize_mode.fitness import get_fitness
from qengine.routes import router
from qengine.services.progressbar import Progressbar
from qengine.models.OptimizationSession import (
    update_optimization_session_status,
    update_optimization_session_trials,
    get_optimization_session,
    get_optimization_session_by_id,
)
import traceback


@ray.remote
def ray_evaluate_mobo_trial(
    user_config, formatted_routes, formatted_data_routes, strategy_hp, hp,
    training_warmup_candles, training_candles, testing_warmup_candles,
    testing_candles, optimal_total, fast_mode, trial_number, session_id,
):
    """Ray remote function — same as standard optimizer but returns richer metrics."""
    try:
        score, training_metrics, testing_metrics = get_fitness(
            user_config, formatted_routes, formatted_data_routes, strategy_hp, hp,
            training_warmup_candles, training_candles, testing_warmup_candles,
            testing_candles, optimal_total, fast_mode, session_id,
        )
        return {
            'trial_number': trial_number,
            'score': score,
            'params': hp,
            'training_metrics': training_metrics,
            'testing_metrics': testing_metrics,
        }
    except exceptions.RouteNotFound as e:
        raise RuntimeError(f"RouteNotFound: {e}")
    except Exception as e:
        logger.log_optimize_mode(f"MOBO Trial {trial_number} failed: {e}", session_id)
        raise


# ─── Gaussian Process (minimal implementation) ───────────────────────────────

class SimpleGP:
    """Minimal Gaussian Process regressor using RBF kernel + scipy.
    Sufficient for 5-20 dims with <500 observations."""

    def __init__(self, length_scale=1.0, noise=1e-6):
        self.length_scale = length_scale
        self.noise = noise
        self.X_train = None
        self.y_train = None
        self._L = None
        self._alpha = None

    def _kernel(self, X1, X2):
        """RBF (squared exponential) kernel"""
        dists = cdist(X1 / self.length_scale, X2 / self.length_scale, 'sqeuclidean')
        return np.exp(-0.5 * dists)

    def fit(self, X, y):
        self.X_train = np.asarray(X, dtype=np.float64)
        self.y_train = np.asarray(y, dtype=np.float64)
        K = self._kernel(self.X_train, self.X_train)
        K += self.noise * np.eye(len(K))
        self._L = cho_factor(K)
        self._alpha = cho_solve(self._L, self.y_train)

    def predict(self, X, return_std=False):
        X = np.asarray(X, dtype=np.float64)
        K_star = self._kernel(X, self.X_train)
        mu = K_star @ self._alpha
        if not return_std:
            return mu
        v = cho_solve(self._L, K_star.T)
        var = 1.0 - np.sum(K_star.T * v, axis=0)
        var = np.maximum(var, 1e-10)
        return mu, np.sqrt(var)


# ─── Pareto utilities ─────────────────────────────────────────────────────────

def is_pareto_dominated(obj, pareto_front):
    """Check if obj is dominated by any point in the Pareto front.
    Both objectives are MAXIMIZED (profit up, negative-drawdown up)."""
    for p in pareto_front:
        if all(p[i] >= obj[i] for i in range(len(obj))) and any(p[i] > obj[i] for i in range(len(obj))):
            return True
    return False


def compute_pareto_front(objectives):
    """Return indices of non-dominated points. Objectives are MAXIMIZED."""
    n = len(objectives)
    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        if not is_pareto[i]:
            continue
        for j in range(n):
            if i == j or not is_pareto[j]:
                continue
            # j dominates i?
            if all(objectives[j][k] >= objectives[i][k] for k in range(2)) and \
               any(objectives[j][k] > objectives[i][k] for k in range(2)):
                is_pareto[i] = False
                break
    return np.where(is_pareto)[0]


def ehvi_acquisition(mu1, sigma1, mu2, sigma2, pareto_front, ref_point):
    """Approximate Expected Hypervolume Improvement (EHVI).
    Simplified: uses the product of per-objective Expected Improvement
    as a proxy for true EHVI (which is expensive to compute exactly)."""
    # Per-objective EI against the Pareto front bounds
    if len(pareto_front) == 0:
        # No Pareto front yet — use pure exploration
        return sigma1 * sigma2

    best1 = max(p[0] for p in pareto_front)
    best2 = max(p[1] for p in pareto_front)

    # EI for objective 1 (profit)
    if sigma1 > 1e-10:
        z1 = (mu1 - best1) / sigma1
        ei1 = sigma1 * (z1 * norm.cdf(z1) + norm.pdf(z1))
    else:
        ei1 = max(0, mu1 - best1)

    # EI for objective 2 (safety)
    if sigma2 > 1e-10:
        z2 = (mu2 - best2) / sigma2
        ei2 = sigma2 * (z2 * norm.cdf(z2) + norm.pdf(z2))
    else:
        ei2 = max(0, mu2 - best2)

    # Combined: product of EIs + exploration bonus
    exploration = 0.1 * (sigma1 + sigma2)
    return ei1 * ei2 + exploration


# ─── MOBO Optimizer ───────────────────────────────────────────────────────────

class MOBOOptimizer:
    """Multi-Objective Bayesian Optimizer for hedging strategies."""

    def __init__(
        self,
        session_id: str,
        user_config: dict,
        training_warmup_candles: dict,
        training_candles: dict,
        testing_warmup_candles: dict,
        testing_candles: dict,
        fast_mode: bool,
        optimal_total: int,
        cpu_cores: int,
    ):
        if jh.python_version() == (3, 13):
            raise ValueError('Optimization not supported on Python 3.13 (Ray dependency).')

        self.session_id = session_id

        strategy_class = jh.get_strategy_class(router.routes[0].strategy_name)
        self.strategy_hp = strategy_class.hyperparameters(None)
        if not self.strategy_hp:
            update_optimization_session_status(self.session_id, 'stopped')
            raise exceptions.InvalidStrategy('Strategy does not implement hyperparameters().')

        self.solution_len = len(self.strategy_hp)
        self.start_time = jh.now_to_timestamp()
        self.fast_mode = fast_mode
        self.optimal_total = optimal_total
        self.training_warmup_candles = training_warmup_candles
        self.training_candles = training_candles
        self.testing_warmup_candles = testing_warmup_candles
        self.testing_candles = testing_candles

        # Enrich config for Ray workers
        exchange_name = router.routes[0].exchange
        exchange_config = config['env']['exchanges'].get(exchange_name, {})
        if exchange_config:
            user_config['exchange'] = {
                'balance': exchange_config.get('balance', 10000),
                'fee': exchange_config.get('fee', 0),
                'type': exchange_config.get('type', 'cfd'),
                'futures_leverage': exchange_config.get('futures_leverage', 30),
                'futures_leverage_mode': exchange_config.get('futures_leverage_mode', 'cross'),
            }
        self.user_config = user_config

        available = cpu_count()
        self.cpu_cores = min(cpu_cores, available) if cpu_cores >= 1 else available

        # MOBO uses fewer trials — GP is sample-efficient
        base_trials = jh.get_config('env.optimization.trials', 200)
        self.n_trials = max(30, self.solution_len * min(base_trials, 50))
        self.n_startup = max(10, self.cpu_cores * 2)

        self.progressbar = Progressbar(self.n_trials)
        self.best_trials = []
        self.trial_counter = 0
        self.completed_trials = 0
        self.pruned_trials = 0

        # Collected observations
        self.X_observed = []  # Normalized param vectors
        self.y_profit = []    # Objective 1: net profit %
        self.y_safety = []    # Objective 2: negative max_drawdown (higher = safer)
        self.all_results = [] # Full trial results for display

        # Pareto front tracking
        self.pareto_indices = []
        self.pareto_front = []

        # Objective curve buffer
        self.objective_curve_buffer = []
        self.total_objective_curve_buffer = []

        # Parameter bounds for normalization
        self._param_names = []
        self._param_bounds = []
        self._param_types = []
        self._categorical_maps = {}
        self._setup_param_space()

        # GP surrogates (fitted after startup phase)
        self.gp_profit = SimpleGP(length_scale=1.0, noise=1e-4)
        self.gp_safety = SimpleGP(length_scale=1.0, noise=1e-4)

        # Initialize Ray
        if not ray.is_initialized():
            try:
                ray.init(num_cpus=self.cpu_cores, ignore_reinit_error=True)
            except Exception:
                self.cpu_cores = 1
                ray.init(num_cpus=1, ignore_reinit_error=True)

        # Termination checker
        client_id = jh.get_session_id()
        from timeloop import Timeloop
        self.tl = Timeloop()

        @self.tl.job(interval=timedelta(seconds=1))
        def check_for_termination():
            if is_process_active(client_id) is False:
                if get_optimization_session(self.session_id)['status'] != 'terminated':
                    update_optimization_session_status(self.session_id, 'stopped')
                raise exceptions.Termination
        self.tl.start()

    def _setup_param_space(self):
        """Build normalized parameter space for GP."""
        for param in self.strategy_hp:
            name = str(param['name'])
            ptype = param['type']
            if isinstance(ptype, type):
                ptype = ptype.__name__
            else:
                ptype = ptype.strip("'").strip('"')

            self._param_names.append(name)
            self._param_types.append(ptype)

            if ptype in ('int', 'float'):
                self._param_bounds.append((param['min'], param['max']))
            elif ptype == 'categorical':
                options = param['options']
                self._categorical_maps[name] = {v: i / max(len(options) - 1, 1) for i, v in enumerate(options)}
                self._param_bounds.append((0.0, 1.0))

    def _hp_to_vector(self, hp):
        """Convert HP dict to normalized [0, 1] vector for GP."""
        vec = []
        for i, name in enumerate(self._param_names):
            val = hp.get(name, 0)
            ptype = self._param_types[i]
            lo, hi = self._param_bounds[i]

            if ptype == 'categorical':
                vec.append(self._categorical_maps[name].get(val, 0.5))
            else:
                vec.append((val - lo) / max(hi - lo, 1e-10))
        return np.array(vec)

    def _vector_to_hp(self, vec):
        """Convert normalized vector back to HP dict."""
        hp = {}
        for i, name in enumerate(self._param_names):
            ptype = self._param_types[i]
            lo, hi = self._param_bounds[i]

            if ptype == 'categorical':
                # Find closest categorical value
                cat_map = self._categorical_maps[name]
                best_key = min(cat_map.keys(), key=lambda k: abs(cat_map[k] - vec[i]))
                hp[name] = best_key
            elif ptype == 'int':
                raw = lo + vec[i] * (hi - lo)
                step = next((p.get('step', 1) for p in self.strategy_hp if str(p['name']) == name), 1)
                hp[name] = int(round((raw - lo) / step) * step + lo)
                hp[name] = max(int(lo), min(int(hi), hp[name]))
            else:  # float
                raw = lo + vec[i] * (hi - lo)
                step = next((p.get('step') for p in self.strategy_hp if str(p['name']) == name), None)
                if step:
                    raw = round((raw - lo) / step) * step + lo
                hp[name] = max(lo, min(hi, raw))
        return hp

    def _generate_random_hp(self):
        """Generate random HP dict (for startup phase)."""
        hp = {}
        for param in self.strategy_hp:
            name = str(param['name'])
            ptype = param['type']
            if isinstance(ptype, type):
                ptype = ptype.__name__
            else:
                ptype = ptype.strip("'").strip('"')

            if ptype == 'int':
                step = param.get('step') or 1
                steps = (param['max'] - param['min']) // step + 1
                hp[name] = int(param['min'] + np.random.randint(0, steps) * step)
            elif ptype == 'float':
                step = param.get('step')
                if step:
                    steps = int((param['max'] - param['min']) / step) + 1
                    hp[name] = param['min'] + np.random.randint(0, steps) * step
                else:
                    hp[name] = np.random.uniform(param['min'], param['max'])
            elif ptype == 'categorical':
                hp[name] = param['options'][np.random.randint(0, len(param['options']))]
        return hp

    def _is_hedging_viable(self, hp):
        """Analytical p*m pruning (same logic as standard optimizer)."""
        hp_names = {str(p['name']) for p in self.strategy_hp}
        if 'sizing_factor' not in hp_names or 'max_levels' not in hp_names:
            return True

        sizing_factor = hp.get('sizing_factor', 2.0)
        sizing_operator = hp.get('sizing_operator', 'multiplier')
        max_levels = hp.get('max_levels', 6)

        if sizing_operator == 'sqrt':
            eff_m = sizing_factor ** 0.5
        elif sizing_operator == 'linear':
            return True
        elif sizing_operator == 'fibonacci':
            eff_m = 1.618
        else:
            eff_m = sizing_factor

        p = 0.60
        if p * eff_m >= 1.0:
            return False
        if eff_m > 1.0:
            risk = (p * eff_m) ** max_levels / (eff_m - 1)
            if risk > 0.01:
                return False
        return True

    def _suggest_next_hp(self):
        """Use GP surrogate + EHVI acquisition to suggest next HP."""
        if len(self.X_observed) < self.n_startup:
            # Startup: random with pruning
            for _ in range(20):
                hp = self._generate_random_hp()
                if self._is_hedging_viable(hp):
                    return hp
                self.pruned_trials += 1
            return hp

        # Fit GPs on observed data
        X = np.array(self.X_observed)
        self.gp_profit.fit(X, np.array(self.y_profit))
        self.gp_safety.fit(X, np.array(self.y_safety))

        # Update Pareto front
        objectives = list(zip(self.y_profit, self.y_safety))
        self.pareto_indices = compute_pareto_front(objectives)
        self.pareto_front = [objectives[i] for i in self.pareto_indices]

        # Generate candidates and score by EHVI acquisition
        best_hp = None
        best_acq = -np.inf
        n_candidates = max(200, self.solution_len * 50)

        for _ in range(n_candidates):
            hp = self._generate_random_hp()
            if not self._is_hedging_viable(hp):
                continue

            x = self._hp_to_vector(hp).reshape(1, -1)
            mu1, s1 = self.gp_profit.predict(x, return_std=True)
            mu2, s2 = self.gp_safety.predict(x, return_std=True)

            acq = ehvi_acquisition(mu1[0], s1[0], mu2[0], s2[0], self.pareto_front, ref_point=(0, 0))

            if acq > best_acq:
                best_acq = acq
                best_hp = hp

        return best_hp if best_hp is not None else self._generate_random_hp()

    def _process_result(self, result):
        """Process a completed trial and update MOBO state."""
        trial_number = result['trial_number']
        params = result['params']
        training_metrics = result['training_metrics']
        testing_metrics = result['testing_metrics']

        self.completed_trials += 1
        self.progressbar.update()

        # Extract objectives
        profit = training_metrics.get('net_profit_percentage', 0) if training_metrics else 0
        max_dd = training_metrics.get('max_drawdown', -100) if training_metrics else -100
        safety = -abs(max_dd)  # Higher = safer (less drawdown)

        self.X_observed.append(self._hp_to_vector(params))
        self.y_profit.append(profit)
        self.y_safety.append(safety)

        # Compute Pareto front for display
        objectives = list(zip(self.y_profit, self.y_safety))
        pareto_idx = compute_pareto_front(objectives)
        is_pareto = (len(self.all_results)) in pareto_idx if len(self.all_results) < len(objectives) else False

        self.all_results.append(result)

        # Publish general info
        general_info = {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
            'trial': f'{self.completed_trials}/{self.n_trials}',
            'objective_function': 'MOBO (profit vs drawdown)',
            'exchange_type': config['env']['exchanges'][router.routes[0].exchange].get('type', 'cfd'),
            'leverage_mode': config['env']['exchanges'][router.routes[0].exchange].get('futures_leverage_mode', 'cross'),
            'leverage': config['env']['exchanges'][router.routes[0].exchange].get('futures_leverage', 30),
            'cpu_cores': self.cpu_cores,
            'sampler': 'mobo',
            'pruned_trials': self.pruned_trials,
            'pareto_size': len(pareto_idx),
        }
        sync_publish('general_info', general_info)
        sync_publish('progressbar', {
            'current': self.progressbar.current,
            'estimated_remaining_seconds': self.progressbar.estimated_remaining_seconds,
        })

        # Objective curve data
        if training_metrics:
            data_point = {
                'trial': trial_number + 1,
                'training': training_metrics,
                'testing': testing_metrics if testing_metrics else {},
            }
            self.objective_curve_buffer.append(data_point)

        buffer_size = len(self.objective_curve_buffer)
        if buffer_size >= 10 or (buffer_size > 0 and self.completed_trials % 5 == 0):
            sync_publish('objective_curve', self.objective_curve_buffer)
            self.total_objective_curve_buffer.extend(self.objective_curve_buffer)
            self.objective_curve_buffer = []

        # Update best trials (use composite score: 0.6*profit_rank + 0.4*safety_rank)
        score = result['score']
        if score > 0.0001:
            params_str = json.dumps(params, sort_keys=True)
            dna = base64.b64encode(params_str.encode()).decode()
            trial_info = {
                'trial': trial_number,
                'params': params,
                'fitness': round(score, 4),
                'value': score,
                'dna': dna,
                'training_metrics': training_metrics,
                'testing_metrics': testing_metrics,
                'is_pareto': is_pareto,
                'profit_pct': round(profit, 2),
                'max_drawdown': round(max_dd, 2),
            }

            best_count = jh.get_config('env.optimization.best_candidates_count', 20)
            insert_idx = 0
            for idx, t in enumerate(self.best_trials):
                if score > t['value']:
                    insert_idx = idx
                    break
                else:
                    insert_idx = idx + 1
            if insert_idx < best_count or len(self.best_trials) < best_count:
                self.best_trials.insert(insert_idx, trial_info)
                self.best_trials = self.best_trials[:best_count]

            self._publish_best_candidates()

        # Periodic DB save
        if self.completed_trials % 5 == 0:
            update_optimization_session_trials(
                self.session_id, self.completed_trials, self.best_trials,
                self.total_objective_curve_buffer, self.n_trials,
            )

    def _publish_best_candidates(self):
        """Publish best candidates with Pareto tags."""
        candidates = []
        for idx, t in enumerate(self.best_trials):
            train_pnl = t.get('training_metrics', {}).get('net_profit_percentage', 'N/A')
            test_pnl = t.get('testing_metrics', {}).get('net_profit_percentage', 'N/A')
            if isinstance(train_pnl, (int, float)):
                train_pnl = round(train_pnl, 2)
            if isinstance(test_pnl, (int, float)):
                test_pnl = round(test_pnl, 2)

            candidates.append({
                'rank': f"#{idx + 1}",
                'trial': f"Trial {t['trial']}",
                'params': t['params'],
                'fitness': t['fitness'],
                'dna': t['dna'],
                'training_metrics': t.get('training_metrics', {}),
                'testing_metrics': t.get('testing_metrics', {}),
                'objective_metric': f"{train_pnl}% / {test_pnl}%",
            })
        sync_publish('best_candidates', candidates)

    def run(self):
        """Main MOBO optimization loop."""
        logger.log_optimize_mode(
            f"MOBO session started with {self.cpu_cores} CPU cores, {self.n_trials} trials",
            self.session_id,
        )

        try:
            max_workers = self.cpu_cores  # Conservative for GP-based optimization
            active_refs = {}

            while self.completed_trials < self.n_trials:
                if self.completed_trials == 0:
                    update_optimization_session_trials(
                        self.session_id, 0, [], [], self.n_trials,
                    )

                while len(active_refs) < max_workers and self.trial_counter < self.n_trials:
                    hp = self._suggest_next_hp()

                    ref = ray_evaluate_mobo_trial.options(num_cpus=1).remote(
                        self.user_config,
                        router.formatted_routes,
                        router.formatted_data_routes,
                        self.strategy_hp,
                        hp,
                        self.training_warmup_candles,
                        self.training_candles,
                        self.testing_warmup_candles,
                        self.testing_candles,
                        self.optimal_total,
                        self.fast_mode,
                        self.trial_counter,
                        self.session_id,
                    )
                    active_refs[ref] = self.trial_counter
                    self.trial_counter += 1

                if not active_refs:
                    break

                done_refs, _ = ray.wait(list(active_refs.keys()), num_returns=1, timeout=0.5)

                for ref in done_refs:
                    trial_number = active_refs.pop(ref)
                    try:
                        result = ray.get(ref)
                        self._process_result(result)
                    except Exception as e:
                        logger.log_optimize_mode(f"MOBO trial {trial_number} failed: {e}", self.session_id)
                        raise

            # Flush remaining buffer
            if self.objective_curve_buffer:
                sync_publish('objective_curve', self.objective_curve_buffer)
                self.total_objective_curve_buffer.extend(self.objective_curve_buffer)
                self.objective_curve_buffer = []

            # Final save
            update_optimization_session_trials(
                self.session_id, self.completed_trials, self.best_trials,
                self.total_objective_curve_buffer, self.n_trials,
            )
            update_optimization_session_status(self.session_id, 'finished')

            # Publish Pareto summary
            objectives = list(zip(self.y_profit, self.y_safety))
            pareto_idx = compute_pareto_front(objectives) if objectives else []
            sync_publish('alert', {
                'message': f"MOBO finished {self.n_trials} trials. "
                           f"Pareto front: {len(pareto_idx)} non-dominated solutions. "
                           f"Pruned {self.pruned_trials} infeasible configs (p*m constraint).",
                'type': 'success',
            })

        except exceptions.Termination:
            logger.log_optimize_mode("MOBO terminated by user", self.session_id)
            update_optimization_session_status(self.session_id, 'stopped')
            raise
        except Exception as e:
            logger.log_optimize_mode(f"MOBO error: {e}", self.session_id)
            update_optimization_session_status(self.session_id, 'stopped')
            from qengine.models.OptimizationSession import add_session_exception
            add_session_exception(self.session_id, str(e), str(traceback.format_exc()))
            raise
        finally:
            ray.shutdown()
