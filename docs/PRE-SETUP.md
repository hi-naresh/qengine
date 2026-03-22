# Pre-Setup Guide

Everything you need before running QEngine.

---

## System Requirements

| Component       | Minimum            | Recommended         |
|-----------------|--------------------|---------------------|
| OS              | macOS, Linux, WSL2 | Ubuntu 22.04+ / macOS 13+ |
| Python          | 3.10               | 3.11 or 3.12        |
| PostgreSQL      | 12                 | 15+                  |
| Redis           | 6                  | 7+                   |
| RAM             | 4 GB               | 8 GB+                |
| CPU             | 2 cores            | 4+ cores (optimization uses Ray) |
| Node.js         | 18 (frontend dev)  | 20+ LTS              |

> **Note:** Python 3.13 is **not** supported for optimization and Monte Carlo modes (Ray dependency).

---

## 1. Install Python

### macOS (Homebrew)
```bash
brew install python@3.12
```

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

### Conda (any OS)
```bash
conda create -n qengine python=3.12
conda activate qengine
```

Verify:
```bash
python --version   # should show 3.10, 3.11, or 3.12
```

---

## 2. Install PostgreSQL

### macOS
```bash
brew install postgresql@15
brew services start postgresql@15
```

### Ubuntu/Debian
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Docker (any OS)
```bash
docker run -d --name qengine-postgres \
  -e POSTGRES_USER=qengine_user \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=qengine_db \
  -p 5432:5432 postgres:15
```

### Create Database and User

```bash
psql postgres
```

```sql
CREATE USER qengine_user WITH PASSWORD 'password';
CREATE DATABASE qengine_db OWNER qengine_user;
GRANT ALL PRIVILEGES ON DATABASE qengine_db TO qengine_user;
\q
```

failsafe :
```bash
# open PostgreSQL CLI
psql postgres
# create database
CREATE DATABASE jesse_db;
# create new user
CREATE USER jesse_user WITH PASSWORD 'password';
# set privileges of the created user
GRANT ALL PRIVILEGES ON DATABASE jesse_db to jesse_user;
# set the owner of the database to the new user (required for PostgreSQL >= 15)
ALTER DATABASE jesse_db OWNER TO jesse_user;
# exit PostgreSQL CLI
\q
```

---

## 3. Install Redis

### macOS
```bash
brew install redis
brew services start redis
```

### Ubuntu/Debian
```bash
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

### Docker
```bash
docker run -d --name qengine-redis -p 6379:6379 redis:7
```

Verify:
```bash
redis-cli ping   # should return PONG
```

---

## 4. Clone and Set Up the Project

```bash
git clone <your-repo-url> qengine
cd qengine
```

### Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows (WSL recommended)
```

### Install dependencies
```bash
pip install --upgrade pip
pip install Cython numpy
pip install -r requirements.txt
pip install -e .
```

The `pip install -e .` command registers the `qengine` CLI command globally in your virtual environment.

---

## 5. Configure Environment Variables

Copy the example env file (or create `.env` manually):

```bash
cp .env.example .env   # if .env.example exists
```

Create/edit `.env` in the project root:

```env
# Database
POSTGRES_HOST=127.0.0.1
POSTGRES_NAME=qengine_db
POSTGRES_PORT=5432
POSTGRES_USERNAME=qengine_user
POSTGRES_PASSWORD=password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Application
APP_PORT=9000
APP_HOST=0.0.0.0
PASSWORD=your-dashboard-password

# Optional: LLM Engine (for AI strategy generation)
# GEMINI_API_KEY=your-key
# ANTHROPIC_API_KEY=your-key
# OPENAI_API_KEY=your-key
# LLM_MODEL=gemini-2.0-flash

# Optional: Development
# IS_DEV_ENV=TRUE
```

> **Important:** The `PASSWORD` field is **required** for production. It protects the dashboard login.

---

## 6. Create the Strategies Directory

QEngine expects a `strategies/` folder in the working directory:

```bash
mkdir -p strategies
```

Example strategies (`SurefireHedge`, `SurefireHedgeV2`) are included in the repository.

---

## 7. Verify Installation

```bash
qengine --version
```

Should print `2.0.0` (or the current version).

---

## 8. Optional: Frontend Development Setup

Only needed if you want to modify the dashboard UI:

```bash
cd frontend
npm install
```

See [RUN.md](./RUN.md) for how to start the frontend dev server.

---

## 9. Optional: Broker API Keys

To use live/paper trading, you'll need API credentials from your broker:

| Broker               | What You Need                          |
|----------------------|----------------------------------------|
| OANDA                | API key + Account ID (practice or live) |
| OANDA Demo           | Same as above (practice server)         |
| IG Markets           | API key + Account ID                    |
| IG Markets Demo      | Same as above (demo server)             |
| Interactive Brokers   | TWS running with API enabled            |
| Interactive Brokers Paper | TWS Paper Trading with API enabled |

Broker credentials are configured through the dashboard Settings page after starting QEngine.

---

## Troubleshooting

### `qengine: command not found`
Re-run `pip install -e .` and make sure your virtual environment is active.

### Database connection errors
Check that PostgreSQL is running and the credentials in `.env` match what you created.

### Redis connection errors
Check that Redis is running: `redis-cli ping` should return `PONG`.

### `ModuleNotFoundError: No module named 'jesse_rust'`
Install the Rust indicators package: `pip install jesse-rust==1.0.1`

### Python 3.13 errors with Ray
Optimization and Monte Carlo require Python 3.12 or lower. Ray does not yet support 3.13.

---

Next: [RUN.md](./RUN.md) - How to start QEngine
