# Running QEngine

How to start the backend, frontend, and production builds.

---

## Quick Start

```bash
# Make sure you're in the project root and venv is active
cd jesse-master
source .venv/bin/activate

# Start the backend
qengine run
```

Open your browser: **http://localhost:9000**

That's it. The dashboard serves at the root URL.

---

## Backend Server

### Using the CLI command
```bash
qengine run
```

### Using Python module directly
```bash
python -m qengine
```

### What happens on startup:
1. Displays the QEngine ASCII banner and version
2. Runs database migrations automatically
3. Installs/checks the Python Language Server (for strategy code editor)
4. Restores saved settings (LLM config, broker keys) from the database
5. Starts the FastAPI/Uvicorn server

### Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `APP_PORT`  | 9000    | Server port |
| `APP_HOST`  | 0.0.0.0 | Bind address |
| `PASSWORD`  | (required) | Dashboard login password |

---

## Frontend Development

For modifying the Vue 3 dashboard:

```bash
cd frontend
npm install      # first time only
npm run dev
```

The Vite dev server runs on **http://localhost:3000** and proxies API calls to the backend at port 9000.

> **Both servers must be running:** backend on 9000, frontend dev on 3000.

### Frontend proxy configuration (vite.config.js)

The dev server automatically proxies these paths to the backend:
- `/auth`, `/backtest`, `/candles`, `/config`, `/exchange-api-keys`
- `/general-info`, `/live`, `/marketplace`, `/notification-api-keys`
- `/optimization`, `/monte-carlo`, `/strategies`, `/ws`
- `/issues`, `/settings`, `/brokers`, `/market-data`, `/llm`
- And more...

---

## Production Build

To build the frontend for production (output goes to `qengine/static/`):

```bash
cd frontend
npm run build
```

After building, the backend serves the built files directly -- no separate frontend server needed.

```bash
cd ..
qengine run
# Dashboard is now at http://localhost:9000
```

---

## Docker

### Build the image
```bash
docker build -t qengine .
```

### Run with Docker Compose (recommended)

Create a `docker-compose.yml`:

```yaml
version: '3.8'
services:
  qengine:
    build: .
    ports:
      - "9000:9000"
    env_file: .env
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: qengine_user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: qengine_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

```bash
docker-compose up -d
```

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test phases
python -m pytest tests/test_phase*.py -v

# Broker tests
python -m pytest tests/test_broker*.py -v
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `qengine run` | Start the application server |
| `qengine install-live` | Install/configure the live trading plugin |
| `qengine --version` | Show version |
| `qengine --help` | Show all commands |

---

## Architecture of the Running System

```
Browser (port 3000 dev / 9000 prod)
  |
  |-- HTTP/WebSocket --> FastAPI (Uvicorn, port 9000)
  |                        |
  |                        |-- PostgreSQL (port 5432)
  |                        |-- Redis (port 6379, pub/sub for real-time updates)
  |                        |-- LSP Server (port 9001, code intelligence)
  |                        |-- Ray (multi-core optimization/monte carlo)
```

---

## Stopping the Server

Press `Ctrl+C` in the terminal. QEngine gracefully:
- Closes the database connection
- Terminates the LSP server
- Stops all background processes

---

Previous: [PRE-SETUP.md](./PRE-SETUP.md) | Next: [ARCHITECTURE.md](./ARCHITECTURE.md)
