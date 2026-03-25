#!/usr/bin/env bash
set -euo pipefail

# QEngine Deploy Script
# Usage: ./deploy.sh [setup|deploy|logs|stop]

COMPOSE="docker compose"

case "${1:-deploy}" in
  setup)
    echo "==> Initial server setup"
    # Install Docker if not present
    if ! command -v docker &>/dev/null; then
      echo "Installing Docker..."
      curl -fsSL https://get.docker.com | sh
      sudo usermod -aG docker "$USER"
      echo "Docker installed. Log out and back in, then re-run this script."
      exit 0
    fi

    # Create .env from example if missing
    if [ ! -f .env ]; then
      cp .env.example .env
      echo "Created .env from .env.example — edit it with your credentials!"
      exit 1
    fi

    echo "==> Building and starting services..."
    $COMPOSE up -d --build
    echo "==> Done! App should be live at https://$(grep DOMAIN .env | cut -d= -f2)"
    ;;

  deploy)
    echo "==> Pulling latest code..."
    git pull origin master

    echo "==> Rebuilding app container..."
    $COMPOSE build app
    $COMPOSE up -d app

    echo "==> Deployed!"
    $COMPOSE ps
    ;;

  logs)
    $COMPOSE logs -f --tail=100 "${2:-app}"
    ;;

  stop)
    $COMPOSE down
    ;;

  restart)
    $COMPOSE restart app
    ;;

  *)
    echo "Usage: ./deploy.sh [setup|deploy|logs|stop|restart]"
    exit 1
    ;;
esac
