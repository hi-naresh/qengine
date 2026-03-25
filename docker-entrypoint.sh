#!/usr/bin/env bash
set -euo pipefail

# Parse Railway/Fly connection URLs into individual vars qengine expects
# REDIS_URL=redis://default:password@host:port
if [ -n "${REDIS_URL:-}" ] && [ -z "${REDIS_HOST:-}" ]; then
  # Strip protocol
  stripped="${REDIS_URL#*://}"
  # Extract password (between : and @)
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

# Write .env file (qengine reads from file, not env vars)
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

# Try qengine CLI first, fallback to uvicorn directly
if [ "$1" = "qengine" ]; then
  "$@" || {
    echo "[entrypoint] 'qengine run' failed, falling back to uvicorn..."
    exec python -c "
from qengine.services.web import fastapi_app
import uvicorn
uvicorn.run(fastapi_app, host='${APP_HOST:-0.0.0.0}', port=int('${APP_PORT:-9000}'), log_level='info')
"
  }
else
  exec "$@"
fi
