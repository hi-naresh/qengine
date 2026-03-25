#!/usr/bin/env bash
set -euo pipefail

# Generate .env from system environment variables
# (Railway/Fly set secrets as env vars, but qengine reads from .env file)
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
  val="${!key:-}"
  if [ -n "$val" ]; then
    echo "${key}=${val}" >> /qengine/.env
  fi
done

echo "[entrypoint] .env generated with $(wc -l < /qengine/.env) vars"
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
