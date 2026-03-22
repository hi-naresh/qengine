# Contributing to QEngine

Guidelines for contributing to the QEngine project.

---

## Getting Started

1. Fork and clone the repository
2. Follow [PRE-SETUP.md](./PRE-SETUP.md) to set up your development environment
3. Create a feature branch from `main`
4. Make your changes
5. Run tests
6. Submit a pull request

---

## Development Setup

```bash
# Clone your fork
git clone <your-fork-url>
cd qengine

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -r requirements.txt
pip install -e .

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Running Both Servers (Development)
```bash
# Terminal 1: Backend
qengine run

# Terminal 2: Frontend dev server (hot reload)
cd frontend
npm run dev
```

---

## Code Style

### Python
- Follow PEP 8 with 120-character line length
- Use type hints for function parameters and return values
- Use `snake_case` for functions and variables
- Use `PascalCase` for classes
- Imports: standard library, then third-party, then local (separated by blank lines)

### JavaScript/Vue
- Follow Vue 3 Composition API patterns
- Use `camelCase` for variables and functions
- Use `PascalCase` for component names
- Tailwind CSS for styling (no custom CSS unless necessary)

### General
- Keep functions focused and short
- Write self-documenting code; add comments only for non-obvious logic
- No dead code or commented-out blocks in PRs
- No console.log or print statements in production code

---

## Project Structure

When adding features, place code in the correct layer:

| Layer | Directory | Purpose |
|-------|-----------|---------|
| Controllers | `qengine/controllers/` | HTTP route handlers (thin, delegate to services) |
| Services | `qengine/services/` | Business logic |
| Models | `qengine/models/` | Database models (Peewee ORM) |
| Modes | `qengine/modes/` | Execution modes (backtest, optimize, live) |
| Strategies | `qengine/strategies/` | Base strategy class |
| Indicators | `qengine/indicators/` | Technical indicators |
| Frontend Views | `frontend/src/views/` | Page-level Vue components |
| Frontend Components | `frontend/src/components/` | Reusable UI components |

---

## Testing

### Running Tests
```bash
# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_phase1.py -v

# With coverage
python -m pytest tests/ --cov=qengine -v
```

### Writing Tests
- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use fixtures for common setup
- Test edge cases and error conditions, not just happy paths

### What to Test
- New services and business logic
- Strategy framework changes
- API endpoint changes (request/response contracts)
- Database model changes

---

## Pull Request Process

### Before Submitting
1. Run the full test suite and ensure all tests pass
2. Build the frontend (`cd frontend && npm run build`) if you changed frontend code
3. Update documentation if you changed user-facing behavior
4. Keep PRs focused -- one feature or fix per PR

### PR Description
- Clearly describe what the PR does and why
- Reference any related issues
- Include before/after screenshots for UI changes
- List any breaking changes

### Review Criteria
- Code follows the project's style conventions
- Tests are included for new functionality
- No unnecessary dependencies added
- Documentation updated for user-facing changes
- No security vulnerabilities introduced

---

## Types of Contributions

### Bug Fixes
- Create an issue describing the bug first
- Reference the issue in your PR
- Include a test that reproduces the bug

### New Indicators
- Add to `qengine/indicators/`
- Follow the existing indicator pattern (function that takes candles + params)
- Export from `qengine/indicators/__init__.py`
- Include docstring with parameter descriptions

### New Broker Drivers
- Add to `qengine/live_drivers/`
- Implement the standard driver interface
- Add broker to `qengine/enums/__init__.py` (brokers dataclass)
- Add broker info to `qengine/info.py` (broker_info dict)
- Include paper trading mode

### Dashboard Features
- Vue 3 components in `frontend/src/`
- Add API proxy entry in `frontend/vite.config.js` for new endpoints
- Follow the existing component patterns (Sidebar, routing, etc.)

### Strategy Examples
- Add to `strategies/` directory
- Include comprehensive docstring explaining the strategy logic
- Use hyperparameters for all tunable values
- Include a `watch_list()` for live monitoring

---

## Commit Messages

- Use imperative mood: "Add feature" not "Added feature"
- Keep the first line under 72 characters
- Reference issue numbers where applicable
- Separate subject from body with a blank line

Examples:
```
Add ATR-based trailing stop to strategy framework

Fix margin calculation for forex cross pairs

Update OANDA driver to handle weekend reconnection
```

---

## Reporting Issues

Use the project's issue tracker. Include:
- QEngine version (`qengine --version`)
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or screenshots

---

## Acknowledgments

QEngine is built upon the foundation of [Jesse](https://github.com/jesse-ai/jesse) by jesse-ai. We acknowledge and appreciate the original work that made this project possible.

All contributions to QEngine are welcome and appreciated.
