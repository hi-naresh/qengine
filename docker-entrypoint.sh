#!/usr/bin/env bash
set -euo pipefail

# Generate .env from system environment variables
# (Fly.io sets secrets as env vars, but qengine reads from .env file)
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

exec "$@"
