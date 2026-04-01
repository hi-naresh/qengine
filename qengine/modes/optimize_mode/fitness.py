import sys
from math import log10
import qengine.helpers as jh
from qengine.research.backtest import _isolated_backtest as isolated_backtest
from qengine.services import logger
import numpy as np
from qengine import exceptions


def _formatted_inputs_for_isolated_backtest(user_config, routes):
    # Format input parameters required for backtest simulation.
    # user_config['exchange'] is populated by the Optimizer from the global config
    # before being passed to Ray workers.
    exc = user_config.get('exchange', {})
    return {
        'starting_balance': exc.get('balance', 10000),
        'fee': exc.get('fee', 0),
        'type': exc.get('type', 'cfd'),
        'futures_leverage': exc.get('futures_leverage', 30),
        'futures_leverage_mode': exc.get('futures_leverage_mode', 'cross'),
        'exchange': routes[0]['exchange'],
        'warm_up_candles': jh.get_config('env.data.warmup_candles_num')
    }


def get_fitness(
        user_config: dict, routes: list, data_routes: list, strategy_hp, hp: dict,
        training_warmup_candles: dict, training_candles: dict,
        testing_warmup_candles: dict, testing_candles: dict, optimal_total: int, fast_mode: bool, session_id
) -> tuple:
    """
    Evaluates the fitness (i.e. backtest performance) of the strategy
    using the given hyperparameters (hp). The fitness score is calculated based on the backtest results.
    """
    try:
        inputs = _formatted_inputs_for_isolated_backtest(user_config, routes)
        # Run backtest simulation for the training data using the suggested hyperparameters
        training_metrics = isolated_backtest(
            inputs,
            routes,
            data_routes,
            candles=training_candles,
            warmup_candles=training_warmup_candles,
            hyperparameters=hp,
            fast_mode=fast_mode
        )['metrics']

        # Gate: require minimum trades for statistical significance
        min_trades = max(5, optimal_total // 10)
        if training_metrics['total'] < min_trades:
            logger.log_optimize_mode(
                f'Only {training_metrics["total"]} trades (need {min_trades}). hp configuration is invalid', session_id)
            score = 0.0001
            testing_metrics = {}
            return score, training_metrics, testing_metrics

        objective_function_config = jh.get_config('env.optimization.objective_function', 'sharpe')

        # Map objective function to metric key and normalization range
        ratio_config = {
            'sharpe':       ('sharpe_ratio',   -.5, 5),
            'calmar':       ('calmar_ratio',   -.5, 30),
            'sortino':      ('sortino_ratio',  -.5, 15),
            'omega':        ('omega_ratio',    -.5, 5),
            'serenity':     ('serenity_index', -.5, 15),
            'smart sharpe': ('smart_sharpe',   -.5, 5),
            'smart sortino':('smart_sortino',  -.5, 15),
        }

        if objective_function_config not in ratio_config:
            raise ValueError(
                f'Unknown objective function `{objective_function_config}`. '
                f'Choose from: {", ".join(ratio_config.keys())}.'
            )

        metric_key, norm_min, norm_max = ratio_config[objective_function_config]
        ratio = training_metrics[metric_key]

        # Negative ratio = not viable
        if ratio < 0:
            score = 0.0001
            logger.log_optimize_mode(
                f"NEGATIVE RATIO: {objective_function_config}: {ratio}, total: {training_metrics['total']}", session_id)
            try:
                testing_metrics = isolated_backtest(
                    inputs, routes, data_routes,
                    candles=testing_candles, warmup_candles=testing_warmup_candles,
                    hyperparameters=hp, fast_mode=fast_mode
                )['metrics']
            except Exception:
                testing_metrics = {}
            return score, training_metrics, testing_metrics

        # Run testing backtest
        testing_metrics = isolated_backtest(
            inputs, routes, data_routes,
            candles=testing_candles, warmup_candles=testing_warmup_candles,
            hyperparameters=hp, fast_mode=fast_mode
        )['metrics']

        # Score = normalized ratio (pure metric score)
        # Trade count is a gate (above), not a multiplier — avoids penalizing
        # strategies that trade less frequently but with high quality
        score = jh.normalize(ratio, norm_min, norm_max)

        # Small bonus (up to 10%) for reaching the target trade count,
        # to break ties between equally-rated strategies
        if training_metrics['total'] < optimal_total:
            trade_bonus = 0.1 * (log10(training_metrics['total']) / log10(optimal_total))
        else:
            trade_bonus = 0.1
        score = score * (0.9 + trade_bonus)

        if np.isnan(score):
            logger.log_optimize_mode(f'Score is nan. hp configuration is invalid', session_id)
            score = 0.0001
        else:
            logger.log_optimize_mode(
                f"hp config is usable => {objective_function_config}: {round(ratio, 2)}, "
                f"total: {training_metrics['total']}, "
                f"pnl%: {round(training_metrics['net_profit_percentage'], 2)}%, "
                f"win-rate: {round(training_metrics['win_rate']*100, 2)}%", session_id)

        return score, training_metrics, testing_metrics

    except exceptions.RouteNotFound as e:
        raise e
    except Exception as e:
        import sys, traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback_details = {
            "filename": exc_traceback.tb_frame.f_code.co_filename,
            "line": exc_traceback.tb_lineno,
            "name": exc_traceback.tb_frame.f_code.co_name,
            "type": exc_type.__name__,
            "message": str(e)
        }
        logger.log_optimize_mode(f"Trial evaluation failed: {traceback_details}", session_id)
        return 0.0001, {}, {}
