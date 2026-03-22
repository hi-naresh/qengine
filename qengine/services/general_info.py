import os
import requests
import qengine.helpers as jh
from qengine.info import exchange_info, qengine_supported_timeframes, QENGINE_API_URL
from qengine.services.env import is_dev_env


def get_general_info(has_live=False) -> dict:
    from qengine.version import __version__ as qengine_version
    system_info = {
        'qengine_version': qengine_version
    }
    plan_info = {'plan': 'guest'}
    limits = {}

    # Determine if live is provided by external qengine_live or our built-in drivers
    has_qengine_live_package = False
    has_builtin_live = False
    if has_live:
        try:
            import qengine_live
            has_qengine_live_package = True
        except ImportError:
            pass
        try:
            from qengine.live_drivers import live_drivers
            if live_drivers:
                has_builtin_live = True
        except ImportError:
            pass

    if has_live and has_qengine_live_package:
        from qengine.services.auth import get_access_token
        access_token = get_access_token()
        if not access_token:
            has_live = False

        # version info
        from qengine_live.version import __version__ as live_version
        system_info['live_plugin_version'] = live_version

        if access_token:
            try:
                response = requests.post(
                    QENGINE_API_URL + '/v2/user-info',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    raise Exception(
                        f"upstream API returned unexpected content type '{content_type}'. "
                        f"The service might be temporarily unavailable. Please try again later."
                    )
                if response.status_code != 200:
                    try:
                        error_message = response.json().get('message', 'Unknown error')
                    except Exception:
                        error_message = f"Received status code {response.status_code}"
                    raise Exception(
                        f"Failed to get user info from upstream API: {error_message}"
                    )
                plan_info = response.json()
                limits = plan_info['limits']
            except requests.exceptions.RequestException as e:
                raise Exception(
                    f"Failed to connect to upstream API. The service might be temporarily unavailable. "
                    f"Error: {str(e)}"
                )
            except ValueError as e:
                raise Exception(
                    f"upstream API returned invalid JSON response. The service might be temporarily unavailable. "
                    f"Error: {str(e)}"
                )
    elif has_live and has_builtin_live:
        # Built-in forex/CFD live drivers — no external API needed
        from qengine.version import __version__ as te_version
        system_info['live_plugin_version'] = te_version
        plan_info = {'plan': 'free'}
        limits = {}

    strategies_path = os.getcwd() + "/strategies/"
    strategies = list(sorted([name for name in os.listdir(strategies_path) if os.path.isdir(strategies_path + name) and not name.startswith('.')]))
    if "__pycache__" in strategies:
        strategies.remove("__pycache__")

    system_info['python_version'] = '{}.{}'.format(*jh.python_version())
    system_info['operating_system'] = jh.get_os()
    system_info['cpu_cores'] = jh.cpu_cores_count()
    system_info['is_docker'] = jh.is_docker()

    update_info = {}

    try:
        # if we are in local dev, consider offline
        if is_dev_env():
            raise ValueError("qengine is running locally, so don't check for updates from pypi")
            
        response = requests.get('https://pypi.org/pypi/qengine/json', timeout=10)
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            update_info['latest_version'] = response.json()['info']['version']
        else:
            raise ValueError("Invalid response from PyPI")
            
        response = requests.get(
            QENGINE_API_URL + '/plugins/live/releases/info',
            timeout=10
        )
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            update_info['qengine_live_latest_version'] = response.json()[0]['version']
        else:
            raise ValueError("Invalid response from API")
            
        update_info['is_update_info_available'] = True
    except Exception as e:
        update_info['is_update_info_available'] = False
        # Log the error for debugging purposes
        jh.debug(f"Failed to fetch update info: {str(e)}")

    res = {
        'exchanges': exchange_info,
        'strategies': strategies,
        'qengine_supported_timeframes': qengine_supported_timeframes,
        'has_live_plugin_installed': has_live,
        'system_info': system_info,
        'update_info': update_info,
        'plan': plan_info['plan'],
    }

    if has_live and limits:
        res['limits'] = {
            'ip_limit': limits.get('ip_limit', 999),
            'live_trading_tabs': limits.get('live_trading_tabs', 10),
            'trading_routes': limits.get('trading_routes', 10),
            'data_routes': limits.get('data_routes', 10),
            'timeframes': limits.get('timeframes', 14),
            'exchanges': list(limits['exchanges'].keys()) if 'exchanges' in limits else [],
        }
    elif has_live:
        # Built-in forex live — no external limits
        from qengine.info import live_trading_exchanges
        res['limits'] = {
            'ip_limit': 999,
            'live_trading_tabs': 10,
            'trading_routes': 10,
            'data_routes': 10,
            'timeframes': 14,
            'exchanges': live_trading_exchanges,
        }

    return res
