import os
import warnings
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from qengine.services.web import fastapi_app
import qengine.helpers as jh

# import cli to register the routes. Do NOT remove this import.
from qengine.cli import cli


# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# get the qengine package directory
QENGINE_DIR = os.path.dirname(os.path.abspath(__file__))

# define lifespan (replaces deprecated @on_event("shutdown"))
@asynccontextmanager
async def lifespan(app):
    # ── Startup: restore saved settings from DB ──
    _restore_saved_settings()
    # ── Ensure ErrorReport table exists ──
    try:
        from qengine.services.error_tracker import ensure_table
        ensure_table()
    except Exception:
        pass
    yield
    from qengine.services.db import database
    database.close_connection()
    from qengine.services.lsp import terminate_lsp_server
    terminate_lsp_server()


def _restore_saved_settings():
    """Load persisted LLM and broker settings from DB on startup."""
    try:
        from qengine.services.db import database
        from qengine.models.Option import Option
        import json
        import peewee

        database.open_connection()
        try:
            o = Option.get(Option.type == 'app_settings')
            data = json.loads(o.json)
        except peewee.DoesNotExist:
            data = {}
        finally:
            database.close_connection()

        # Restore LLM engine config
        llm_conf = data.get('llm', {})
        if llm_conf.get('api_key') and llm_conf.get('provider'):
            from qengine.services.llm_engine import llm_engine
            llm_engine.configure(
                provider=llm_conf['provider'],
                api_key=llm_conf['api_key'],
                model=llm_conf.get('model') or None,
                temperature=llm_conf.get('temperature', 0.3),
            )

        # Restore broker API keys into ExchangeApiKeys table (if not already there)
        broker_conf = data.get('brokers', {})
        if broker_conf:
            _sync_broker_keys_to_db(broker_conf)

    except Exception:
        # Don't crash startup if DB isn't available yet (e.g. first run)
        pass


def _sync_broker_keys_to_db(broker_conf: dict):
    """Ensure broker credentials from app_settings are available in ExchangeApiKeys."""
    from qengine.services.db import database
    from qengine.models.ExchangeApiKeys import ExchangeApiKeys
    import json
    import peewee

    database.open_connection()
    try:
        for broker_id, conf in broker_conf.items():
            api_key = conf.get('api_key', '')
            if not api_key:
                continue

            # Check if a key for this broker already exists
            name = f'{broker_id}_settings'
            exists = ExchangeApiKeys.select().where(
                ExchangeApiKeys.name == name
            ).exists()

            if exists:
                # Update existing key
                ExchangeApiKeys.update(
                    api_key=api_key,
                    api_secret=conf.get('api_secret', ''),
                    additional_fields=json.dumps({
                        'account_id': conf.get('account_id', ''),
                        **(conf.get('additional_fields') or {}),
                    }),
                ).where(ExchangeApiKeys.name == name).execute()
            else:
                # Create new key entry
                ExchangeApiKeys.create(
                    id=jh.generate_unique_id(),
                    exchange_name=broker_id,
                    name=name,
                    api_key=api_key,
                    api_secret=conf.get('api_secret', ''),
                    additional_fields=json.dumps({
                        'account_id': conf.get('account_id', ''),
                        **(conf.get('additional_fields') or {}),
                    }),
                    created_at=jh.now_to_datetime(),
                )
    except Exception:
        pass
    finally:
        database.close_connection()

fastapi_app.router.lifespan_context = lifespan




# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Routes
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
from qengine.controllers.websocket_controller import router as websocket_router
from qengine.controllers.optimization_controller import router as optimization_router
from qengine.controllers.monte_carlo_controller import router as monte_carlo_router
from qengine.controllers.exchange_controller import router as exchange_router
from qengine.controllers.backtest_controller import router as backtest_router
from qengine.controllers.candles_controller import router as candles_router
from qengine.controllers.strategy_controller import router as strategy_router
from qengine.controllers.auth_controller import router as auth_router
from qengine.controllers.config_controller import router as config_router
from qengine.controllers.notification_controller import router as notification_router
from qengine.controllers.system_controller import router as system_router
from qengine.controllers.file_controller import router as file_router
from qengine.controllers.lsp_controller import router as lsp_router
from qengine.controllers.closed_trade_controller import router as closed_trade_router
from qengine.controllers.order_controller import router as order_router
from qengine.controllers.tabs_controller import router as tabs_router
from qengine.controllers.llm_controller import router as llm_router
from qengine.controllers.broker_controller import router as broker_router
from qengine.controllers.market_data_controller import router as market_data_router
from qengine.controllers.settings_controller import router as settings_router
from qengine.controllers.playground_controller import router as playground_router
from qengine.controllers.issue_controller import router as issue_router
from qengine.controllers.framework_controller import router as framework_router
from qengine.controllers.report_controller import router as report_router

# register routers
fastapi_app.include_router(websocket_router)
fastapi_app.include_router(optimization_router)
fastapi_app.include_router(monte_carlo_router)
fastapi_app.include_router(exchange_router)
fastapi_app.include_router(backtest_router)
fastapi_app.include_router(candles_router)
fastapi_app.include_router(strategy_router)
fastapi_app.include_router(auth_router)
fastapi_app.include_router(config_router)
fastapi_app.include_router(notification_router)
fastapi_app.include_router(system_router)
fastapi_app.include_router(file_router)
fastapi_app.include_router(lsp_router)
fastapi_app.include_router(closed_trade_router)
fastapi_app.include_router(order_router)
fastapi_app.include_router(tabs_router)
fastapi_app.include_router(llm_router)
fastapi_app.include_router(broker_router)
fastapi_app.include_router(market_data_router)
fastapi_app.include_router(settings_router)
fastapi_app.include_router(playground_router)
fastapi_app.include_router(issue_router)
fastapi_app.include_router(framework_router)
fastapi_app.include_router(report_router)

# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Live Trade Plugin
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Always register live controller — built-in forex/CFD live drivers or qengine_live
from qengine.controllers.live_controller import router as live_router
fastapi_app.include_router(live_router)


# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Static Files (Must be loaded at the end to prevent overlapping with API endpoints)
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# QEngine Dashboard (must be LAST to not overlap API routes)
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
fastapi_app.mount("/assets", StaticFiles(directory=f"{QENGINE_DIR}/static/assets"), name="assets")

@fastapi_app.get("/favicon.svg")
async def favicon():
    return FileResponse(f"{QENGINE_DIR}/static/favicon.svg")

@fastapi_app.get("/")
@fastapi_app.get("/{rest_of_path:path}")
async def dashboard(rest_of_path: str = ""):
    from starlette.responses import Response
    import os
    html_path = f"{QENGINE_DIR}/static/index.html"
    with open(html_path, 'rb') as f:
        content = f.read()
    return Response(
        content=content,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )
