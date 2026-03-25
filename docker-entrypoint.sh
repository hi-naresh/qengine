#!/usr/bin/env bash
set -euo pipefail

# ── Start embedded Redis if no external Redis configured ──
if [ -z "${REDIS_URL:-}" ] && [ -z "${REDIS_HOST:-}" ]; then
  echo "[entrypoint] No REDIS_URL or REDIS_HOST set — starting embedded Redis..."
  redis-server --daemonize yes --port 6379 --save "" --appendonly no
  export REDIS_HOST=127.0.0.1
  export REDIS_PORT=6379
  export REDIS_PASSWORD=""
  echo "[entrypoint] Embedded Redis started on 127.0.0.1:6379"
fi

# ── Parse Railway/Fly connection URLs ──
# REDIS_URL=redis://default:password@host:port
if [ -n "${REDIS_URL:-}" ] && [ -z "${REDIS_HOST:-}" ]; then
  stripped="${REDIS_URL#*://}"
  if [[ "$stripped" == *"@"* ]]; then
    userpass="${stripped%%@*}"
    hostport="${stripped#*@}"
    export REDIS_PASSWORD="${userpass#*:}"
  else
    hostport="$stripped"
    export REDIS_PASSWORD=""
  fi
  export REDIS_HOST="${hostport%%:*}"
  export REDIS_PORT="${hostport#*:}"
  export REDIS_PORT="${REDIS_PORT%%/*}"
  echo "[entrypoint] Parsed REDIS_URL -> ${REDIS_HOST}:${REDIS_PORT}"
fi

# DATABASE_URL=postgresql://user:pass@host:port/dbname
if [ -n "${DATABASE_URL:-}" ] && [ -z "${POSTGRES_HOST:-}" ]; then
  stripped="${DATABASE_URL#*://}"
  userpass="${stripped%%@*}"
  export POSTGRES_USERNAME="${userpass%%:*}"
  export POSTGRES_PASSWORD="${userpass#*:}"
  hostrest="${stripped#*@}"
  hostport="${hostrest%%/*}"
  export POSTGRES_HOST="${hostport%%:*}"
  export POSTGRES_PORT="${hostport#*:}"
  export POSTGRES_NAME="${hostrest#*/}"
  export POSTGRES_NAME="${POSTGRES_NAME%%\?*}"
  echo "[entrypoint] Parsed DATABASE_URL -> ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_NAME}"
fi

# ── Defaults for required vars ──
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_NAME="${POSTGRES_NAME:-qengine_db}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export POSTGRES_USERNAME="${POSTGRES_USERNAME:-qengine_user}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-password}"
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_DB="${REDIS_DB:-0}"
export REDIS_PASSWORD="${REDIS_PASSWORD:-}"
export APP_PORT="${APP_PORT:-9000}"
export APP_HOST="${APP_HOST:-0.0.0.0}"
export PASSWORD="${PASSWORD:-test}"
export APP_PASSWORD="${APP_PASSWORD:-test}"
export IS_DEV_ENV="${IS_DEV_ENV:-FALSE}"

# ── Write .env file (qengine reads from file, not env vars) ──
ENV_KEYS=(
  POSTGRES_HOST POSTGRES_NAME POSTGRES_PORT POSTGRES_USERNAME POSTGRES_PASSWORD
  REDIS_HOST REDIS_PORT REDIS_DB REDIS_PASSWORD
  APP_PORT APP_HOST PASSWORD APP_PASSWORD IS_DEV_ENV
  OANDA_API_KEY OANDA_ACCOUNT_ID
  IG_USERNAME IG_PASSWORD IG_API_KEY IG_ACCOUNT_ID
  GEMINI_API_KEY
  IBKR_ACCOUNT_ID IBKR_HOST IBKR_PORT
)

: > /qengine/.env
for key in "${ENV_KEYS[@]}"; do
  echo "${key}=${!key:-}" >> /qengine/.env
done

echo "[entrypoint] .env generated:"
cat /qengine/.env | grep -v -E '(PASSWORD|API_KEY|SECRET)' || true
echo "[entrypoint] Starting: $*"

# ── Run ──
if [ "$1" = "qengine" ]; then
  "$@" || {
    echo "[entrypoint] 'qengine run' failed, falling back to uvicorn..."
    exec python -c "
from qengine.services.web import fastapi_app
import uvicorn
uvicorn.run(fastapi_app, host='${APP_HOST}', port=int('${APP_PORT}'), log_level='info')
"
  }
else
  exec "$@"
fi
