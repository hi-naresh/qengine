import pytest
from qengine.services.llm_engine import LLMEngine, llm_engine


# ── 6.1 LLM Engine Core ──

def test_llm_engine_singleton():
    assert llm_engine is not None
    assert isinstance(llm_engine, LLMEngine)


def test_llm_engine_default_not_configured():
    engine = LLMEngine()
    assert engine.is_configured is False
    assert engine.provider is None
    assert engine.api_key is None


def test_llm_engine_configure():
    engine = LLMEngine()
    engine.configure('anthropic', 'test-key', 'claude-sonnet-4-6', 0.3)
    assert engine.is_configured is True
    assert engine.provider == 'anthropic'
    assert engine.api_key == 'test-key'
    assert engine.model == 'claude-sonnet-4-6'
    assert engine.temperature == 0.3


def test_llm_engine_configure_openai():
    engine = LLMEngine()
    engine.configure('openai', 'sk-test', 'gpt-4o')
    assert engine.is_configured is True
    assert engine.provider == 'openai'


def test_generate_strategy_returns_error_when_not_configured():
    engine = LLMEngine()
    result = engine.generate_strategy('create a simple SMA crossover')
    assert result['valid'] is False
    assert 'not configured' in result['errors'][0]
    assert result['code'] == ''


def test_refine_strategy_returns_error_when_not_configured():
    engine = LLMEngine()
    result = engine.refine_strategy('some code', 'make it better')
    assert result['valid'] is False
    assert 'not configured' in result['errors'][0]


# ── 6.2 Strategy Validation ──

def test_validate_empty_code():
    engine = LLMEngine()
    result = engine.validate_strategy('')
    assert result['valid'] is False
    assert 'Empty code' in result['errors'][0]


def test_validate_syntax_error():
    engine = LLMEngine()
    result = engine.validate_strategy('def foo(:\n  pass')
    assert result['valid'] is False
    assert 'Syntax error' in result['errors'][0]


def test_validate_valid_strategy():
    code = '''
from qengine.strategies import Strategy

class MyStrategy(Strategy):
    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_short(self):
        return False

    def go_short(self):
        pass
'''
    engine = LLMEngine()
    result = engine.validate_strategy(code)
    assert result['valid'] is True
    assert result['errors'] == []


def test_validate_missing_methods():
    code = '''
from qengine.strategies import Strategy

class MyStrategy(Strategy):
    def should_long(self):
        return False
'''
    engine = LLMEngine()
    result = engine.validate_strategy(code)
    assert result['valid'] is False
    assert any('go_long' in e for e in result['errors'])


def test_validate_no_strategy_class():
    code = '''
def hello():
    print("world")
'''
    engine = LLMEngine()
    result = engine.validate_strategy(code)
    assert result['valid'] is False
    assert any('Strategy' in e for e in result['errors'])


# ── 6.3 Code Extraction ──

def test_extract_code_from_markdown():
    engine = LLMEngine()
    response = '''Here's your strategy:

```python
from qengine.strategies import Strategy

class MyStrat(Strategy):
    def should_long(self):
        return True
    def go_long(self):
        pass
    def should_short(self):
        return False
    def go_short(self):
        pass
```

This strategy buys when...'''

    code = engine._extract_code(response)
    assert 'class MyStrat' in code
    assert 'def should_long' in code
    assert '```' not in code


def test_extract_code_from_plain_response():
    engine = LLMEngine()
    response = '''from qengine.strategies import Strategy

class MyStrat(Strategy):
    def should_long(self):
        return True
    def go_long(self):
        pass
    def should_short(self):
        return False
    def go_short(self):
        pass'''

    code = engine._extract_code(response)
    assert 'class MyStrat' in code


def test_extract_code_generic_block():
    engine = LLMEngine()
    response = '''```
from qengine.strategies import Strategy

class MyStrat(Strategy):
    def should_long(self):
        return True
    def go_long(self):
        pass
    def should_short(self):
        return False
    def go_short(self):
        pass
```'''

    code = engine._extract_code(response)
    assert 'class MyStrat' in code


# ── 6.4 System Prompt ──

def test_system_prompt_contains_framework_docs():
    engine = LLMEngine()
    prompt = engine._build_system_prompt('forex')
    assert 'self.pip_size' in prompt
    assert 'self.session' in prompt
    assert 'self.lot_size_for_risk' in prompt
    assert 'sma' in prompt.lower()
    assert 'should_long' in prompt


def test_system_prompt_commodity():
    engine = LLMEngine()
    prompt = engine._build_system_prompt('commodity')
    assert 'commodity' in prompt


def test_user_prompt():
    engine = LLMEngine()
    prompt = engine._build_user_prompt('buy when RSI is oversold', 'EUR-USD')
    assert 'EUR-USD' in prompt
    assert 'RSI is oversold' in prompt


# ── 6.5 Request Models ──

def test_request_models_exist():
    from qengine.services.web import (
        GenerateStrategyRequestJson,
        RefineStrategyRequestJson,
        ValidateStrategyRequestJson,
        ConfigureLLMRequestJson,
    )
    # Verify they can be instantiated
    gen = GenerateStrategyRequestJson(description='test')
    assert gen.description == 'test'
    assert gen.asset_class == 'forex'
    assert gen.symbol == 'EUR-USD'

    ref = RefineStrategyRequestJson(code='x', feedback='y')
    assert ref.code == 'x'
    assert ref.backtest_results is None

    val = ValidateStrategyRequestJson(code='z')
    assert val.code == 'z'

    cfg = ConfigureLLMRequestJson(provider='anthropic', api_key='key')
    assert cfg.provider == 'anthropic'
    assert cfg.temperature == 0.3


# ── 6.6 Controller Registration ──

def test_llm_controller_router_exists():
    from qengine.controllers.llm_controller import router
    assert router.prefix == '/llm'
    routes = [r.path for r in router.routes]
    assert any('/generate' in r for r in routes)
    assert any('/refine' in r for r in routes)
    assert any('/validate' in r for r in routes)
    assert any('/configure' in r for r in routes)
    assert any('/status' in r for r in routes)


# ── 6.7 Backtest Results Formatting ──

def test_format_backtest_results():
    from qengine.services.llm_engine import _format_backtest_results
    results = {
        'total': 50,
        'win_rate': 0.6,
        'net_profit_percentage': 15.5,
        'max_drawdown': -8.2,
        'sharpe_ratio': 1.5,
    }
    formatted = _format_backtest_results(results)
    assert 'total: 50' in formatted
    assert 'win_rate: 0.6' in formatted
    assert 'sharpe_ratio: 1.5' in formatted


def test_llm_engine_configure_gemini():
    engine = LLMEngine()
    engine.configure('gemini', 'gemini-test-key', 'gemini-2.0-flash')
    assert engine.is_configured is True
    assert engine.provider == 'gemini'
    assert engine.model == 'gemini-2.0-flash'


def test_llm_engine_gemini_is_default_provider():
    """Gemini should be checked first in configure_from_env."""
    import os
    engine = LLMEngine()
    old_gemini = os.environ.get('GEMINI_API_KEY')
    os.environ['GEMINI_API_KEY'] = 'test-gemini-key'
    try:
        result = engine.configure_from_env()
        assert result is True
        assert engine.provider == 'gemini'
        assert engine.api_key == 'test-gemini-key'
        assert engine.model == 'gemini-2.5-flash'
    finally:
        if old_gemini:
            os.environ['GEMINI_API_KEY'] = old_gemini
        else:
            os.environ.pop('GEMINI_API_KEY', None)


def test_llm_engine_gemini_dispatch():
    """_call_llm should dispatch to _call_gemini for gemini provider."""
    engine = LLMEngine()
    engine.configure('gemini', 'test-key')
    # Verify the dispatch path exists (don't actually call the API)
    assert hasattr(engine, '_call_gemini')
    assert callable(engine._call_gemini)


def test_configure_from_env_no_keys():
    engine = LLMEngine()
    # Without env vars, .env values, or DB settings, should return False
    import os
    from unittest.mock import patch
    from qengine.services.env import ENV_VALUES
    old_gemini = os.environ.pop('GEMINI_API_KEY', None)
    old_anthropic = os.environ.pop('ANTHROPIC_API_KEY', None)
    old_openai = os.environ.pop('OPENAI_API_KEY', None)
    # Also clear ENV_VALUES (loaded from .env) so configure_from_env can't find keys there
    saved_env = {}
    for k in ('GEMINI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
        if k in ENV_VALUES:
            saved_env[k] = ENV_VALUES.pop(k)
    try:
        # Mock out DB settings lookup so it can't find keys there either
        with patch('qengine.services.llm_engine.LLMEngine.configure_from_env',
                   wraps=engine.configure_from_env) as _:
            # Patch the DB import to raise so the except block catches it
            with patch.dict('sys.modules', {'qengine.controllers.settings_controller': None}):
                assert engine.configure_from_env() is False
    finally:
        if old_gemini:
            os.environ['GEMINI_API_KEY'] = old_gemini
        if old_anthropic:
            os.environ['ANTHROPIC_API_KEY'] = old_anthropic
        if old_openai:
            os.environ['OPENAI_API_KEY'] = old_openai
        ENV_VALUES.update(saved_env)
