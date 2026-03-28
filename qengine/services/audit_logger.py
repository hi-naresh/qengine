"""
Structured audit & request logging for QEngine.

- Request logger: FastAPI middleware that logs every HTTP request with user context.
- Audit logger: explicit calls for sensitive actions (login, register, delete, impersonate).

Logs go to storage/logs/audit.log (JSON lines) and storage/logs/requests.log (JSON lines).
"""
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

LOG_DIR = 'storage/logs'

def _make_logger(name: str, filename: str, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            os.path.join(LOG_DIR, filename),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


_request_logger = _make_logger('qengine.requests', 'requests.log')
_audit_logger = _make_logger('qengine.audit', 'audit.log')


def log_request(*, method: str, path: str, status: int, duration_ms: float,
                user_id: str = None, username: str = None, ip: str = None):
    """Log an HTTP request with user context."""
    entry = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'type': 'request',
        'method': method,
        'path': path,
        'status': status,
        'duration_ms': round(duration_ms, 1),
    }
    if user_id:
        entry['user_id'] = user_id
    if username:
        entry['username'] = username
    if ip:
        entry['ip'] = ip
    _request_logger.info(json.dumps(entry, separators=(',', ':')))


def audit(action: str, *, user_id: str = None, username: str = None,
          target_user_id: str = None, ip: str = None, detail: str = None):
    """Log a sensitive/audit-worthy action."""
    entry = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'type': 'audit',
        'action': action,
    }
    if user_id:
        entry['user_id'] = user_id
    if username:
        entry['username'] = username
    if target_user_id:
        entry['target_user_id'] = target_user_id
    if ip:
        entry['ip'] = ip
    if detail:
        entry['detail'] = detail
    _audit_logger.info(json.dumps(entry, separators=(',', ':')))
