# QEngine

A multi-asset algorithmic trading platform for forex, commodities, and more (coming soon).

---

## What is QEngine?

QEngine is a Python-based algorithmic trading engine with a modern web dashboard. It provides a complete workflow for developing, testing, optimizing, and deploying trading strategies across forex, commodity, index, and stock markets.

### Key Features

- **Strategy Framework**: Write strategies in Python with 175+ built-in technical indicators
- **Backtesting Engine**: Minute-by-minute event-driven simulation with realistic forex modeling (spreads, swaps, leverage, market hours)
- **Hyperparameter Optimization**: Distributed search using Optuna + Ray across multiple CPU cores
- **Monte Carlo Simulation**: Stress-test strategies with trade shuffling and candle perturbation
- **Live Trading**: Built-in broker drivers for OANDA, IG Markets, and Interactive Brokers
- **Web Dashboard**: Vue 3 interface for backtesting, optimization, live trading, and strategy editing
- **LLM Studio**: AI-powered strategy generation using Claude, GPT, or Gemini
- **Code Editor**: In-browser strategy editor with Pyright-powered code intelligence

### Supported Brokers

| Broker | Backtesting | Paper Trading | Live Trading |
|--------|:-----------:|:-------------:|:------------:|
| OANDA | Yes | Yes | Yes |
| OANDA Demo | -- | Yes | Yes |
| IG Markets | Yes | Yes | Yes |
| IG Markets Demo | -- | Yes | Yes |
| Interactive Brokers | Yes | Yes | Yes |
| Interactive Brokers Paper | -- | Yes | Yes |

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Database | PostgreSQL (Peewee ORM) |
| Cache | Redis |
| Frontend | Vue 3, Vite, Tailwind CSS |
| Indicators | jesse_rust (Rust-based) |
| Optimization | Optuna + Ray |
| LLM | Anthropic / OpenAI / Google Gemini |

---

## Quick Start

### Prerequisites
- Python 3.10-3.12
- PostgreSQL 12+
- Redis 6+

### Install
```bash
# Clone the repository
git clone <your-repo-url> qengine
cd qengine

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install
pip install -r requirements.txt
pip install -e .
```

### Configure
```bash
# Create .env file with database credentials
cat > .env << EOF
POSTGRES_HOST=127.0.0.1
POSTGRES_NAME=qengine_db
POSTGRES_PORT=5432
POSTGRES_USERNAME=qengine_user
POSTGRES_PASSWORD=password
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
APP_PORT=9000
PASSWORD=your-dashboard-password
EOF
```

### Run
```bash
qengine run
# Open http://localhost:9000
```

See [PRE-SETUP.md](./new-docs/PRE-SETUP.md) for detailed setup instructions.

---

## Documentation

| Document | Description |
|----------|-------------|
| [PRE-SETUP.md](./new-docs/PRE-SETUP.md) | System requirements, database setup, environment configuration |
| [RUN.md](./new-docs/RUN.md) | Starting the backend, frontend dev, Docker, CLI commands |
| [ARCHITECTURE.md](./new-docs/ARCHITECTURE.md) | System architecture, directory structure, data flow |
| [HIGH-LEVEL-LOGIC.md](./new-docs/HIGH-LEVEL-LOGIC.md) | How backtesting, optimization, Monte Carlo, and strategy execution work |
| [STRATEGY.md](./new-docs/STRATEGY.md) | Complete strategy writing guide (basic to advanced) |
| [PROGRESS.md](./new-docs/PROGRESS.md) | Development phases and roadmap |
| [CHANGELOG.md](./new-docs/CHANGELOG.md) | Version history |
| [CONTRIBUTIONS.md](./new-docs/CONTRIBUTIONS.md) | How to contribute |

---

## Write Your First Strategy

```python
from qengine.strategies import Strategy
import qengine.indicators as ta


class SimpleRSI(Strategy):

    def should_long(self) -> bool:
        return ta.rsi(self.candles, 14) < 30

    def go_long(self):
        qty = self.balance * self.leverage / self.price
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - self.pips_to_price(20)
        self.take_profit = qty, self.price + self.pips_to_price(40)

    def should_short(self) -> bool:
        return ta.rsi(self.candles, 14) > 70

    def go_short(self):
        qty = self.balance * self.leverage / self.price
        self.sell = qty, self.price
        self.stop_loss = qty, self.price + self.pips_to_price(20)
        self.take_profit = qty, self.price - self.pips_to_price(40)
```

Save as `strategies/SimpleRSI/__init__.py`, then backtest from the dashboard.

See [STRATEGY.md](./new-docs/STRATEGY.md) for the complete guide.

---

## Project Origin

QEngine v2.0.0 is built upon the foundation of [Jesse](https://github.com/jesse-ai/jesse), an open-source algorithmic trading framework. QEngine extends Jesse with forex/CFD broker support, a modern Vue 3 dashboard, LLM-powered strategy generation, and multi-asset capabilities.

Original Jesse framework by jesse-ai, licensed under MIT.

---

## License

MIT License. See [LICENSE](./LICENSE) for details.
