import asyncio
import json
import time
from typing import Set
from starlette.websockets import WebSocket

from qengine.services.redis import async_redis
from qengine.services.multiprocessing import process_manager
import qengine.helpers as jh


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.is_subscribed = False
        self.redis_subscriber = None
        self.reader_task = None
        self.heartbeat_task = None
        self.heartbeat_interval = 30
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        await self.start_heartbeat()
        
    def disconnect(self, websocket: WebSocket):
        # Use discard to avoid KeyError if already removed
        self.active_connections.discard(websocket)
        
    async def broadcast(self, message: dict):
        # Process id with the manager for each websocket separately
        # Be resilient to per-connection send failures so a single bad client
        # does not stop the Redis listener loop.
        for connection in list(self.active_connections):
            message_copy = dict(message)
            message_copy['id'] = process_manager.get_client_id(message_copy['id'])
            try:
                await connection.send_json(message_copy)
            except Exception as e:
                # Drop the failing connection and continue broadcasting
                jh.terminal_debug(f"WebSocket send error: {str(e)}")
                self.disconnect(connection)
            
    async def start_redis_listener(self, channel_pattern):
        # Start or restart the listener task if missing or completed
        if self.reader_task is None or self.reader_task.done():
            self.is_subscribed = True
            # Start the resilient listener task which will (re)subscribe internally
            self.reader_task = asyncio.create_task(self._redis_listener(channel_pattern))
            
    async def _redis_listener(self, channel_pattern):
        # Keep the subscription alive and resubscribe on failures with backoff
        backoff_seconds = 0.1
        while self.is_subscribed:
            try:
                self.redis_subscriber, = await async_redis.psubscribe(channel_pattern)
                # Reset backoff after a successful subscribe
                backoff_seconds = 0.1
                async for ch, message in self.redis_subscriber.iter():
                    # Parse the message and broadcast to all clients
                    message_dict = json.loads(message)
                    # Intercept exception/error events and track as ErrorReports
                    _track_redis_error_event(message_dict)
                    await self.broadcast(message_dict)
            except asyncio.CancelledError:
                # Task was cancelled as part of shutdown
                break
            except Exception as e:
                jh.terminal_debug(f"Redis listener error: {str(e)}")
                # Exponential backoff to avoid tight retry loops
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 5.0)
            
    async def start_heartbeat(self):
        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
    async def _heartbeat_loop(self):
        while len(self.active_connections) > 0:
            try:
                ping_message = {
                    'event': 'ping',
                    'timestamp': time.time(),
                    'id': 0,
                    'data': None
                }
                await self.broadcast(ping_message)
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                jh.terminal_debug(f"Heartbeat error: {str(e)}")
                await asyncio.sleep(self.heartbeat_interval)
    
    async def stop_redis_listener(self):
        if self.is_subscribed and len(self.active_connections) == 0:
            # Only unsubscribe if no clients are connected
            self.is_subscribed = False
            if self.reader_task and not self.reader_task.done():
                self.reader_task.cancel()
                try:
                    await self.reader_task
                except asyncio.CancelledError:
                    pass
            
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
                    
            from qengine.services.env import ENV_VALUES
            try:
                await async_redis.punsubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")
            except Exception as e:
                jh.terminal_debug(f"Redis punsubscribe error: {str(e)}")
            jh.terminal_debug("Redis unsubscribed - no more active connections")


def _track_redis_error_event(message_dict: dict):
    """Intercept exception and error events from Redis and store as ErrorReports.
    Uses ONLY stdlib imports (json, os, uuid, time) to guarantee it works.
    This runs in the main process — the ONLY reliable place to capture subprocess errors."""
    import json as _json, os as _os, uuid as _uuid, time as _time, sys as _sys

    try:
        event = message_dict.get('event', '')
        data = message_dict.get('data')
        if not data or not isinstance(data, dict):
            return

        report = None

        if event.endswith('.exception') or event.endswith('.playground_exception'):
            error_msg = data.get('error', 'Unknown error')
            session_type = event.split('.')[0] if '.' in event else 'system'
            error_type = error_msg.split(':')[0].strip() if ':' in error_msg else None
            report = {
                'id': str(_uuid.uuid4()),
                'session_id': None,
                'session_type': session_type,
                'error_type': error_type,
                'message': str(error_msg)[:10000],
                'traceback': data.get('traceback', ''),
                'context': None,
                'status': 'new',
                'issue_id': None,
                'user_id': None,
                'created_at': int(_time.time() * 1000),
            }

        # NOTE: .error_log events are NOT tracked — they are follow-up messages
        # (e.g. "Session terminated") that always accompany an .exception event.

        if report is None:
            return

        # 1. Write directly to file (GUARANTEED to work — no qengine imports)
        error_dir = 'storage/logs/error-reports'
        _os.makedirs(error_dir, exist_ok=True)
        fpath = _os.path.join(error_dir, f"{report['created_at']}_{report['id'][:8]}.json")
        with open(fpath, 'w') as f:
            _json.dump(report, f)

        print(f"[ERROR_TRACKER] Captured {event} -> {fpath}", file=_sys.stderr)

        # 2. Also try Redis hash + DB via track_error (best-effort, for faster reads)
        try:
            from qengine.services.error_tracker import _store_to_redis, _store_to_db
            _store_to_redis(report)
            _store_to_db(report)
        except Exception:
            pass

    except Exception as e:
        import sys
        print(f"[WS_MANAGER] _track_redis_error_event FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)


# Create a global instance
ws_manager = ConnectionManager()
