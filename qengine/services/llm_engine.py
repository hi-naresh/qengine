import re
import os
from typing import Optional


class LLMEngine:
    """
    Strategy generation and refinement using LLM.
    Independent module - called by the main engine but doesn't
    directly interact with backtesting/trading.

    Supports: Anthropic (Claude), OpenAI (GPT), Google Gemini, or any OpenAI-compatible API.
    """

    def __init__(self):
        self.provider: Optional[str] = None   # 'anthropic', 'openai', 'gemini'
        self.api_key: Optional[str] = None
        self.model: Optional[str] = None      # e.g., 'gemini-2.5-flash'
        self.temperature: float = 0.3
        self.max_tokens: int = 4096

    def configure(self, provider: str, api_key: str, model: str = None,
                  temperature: float = 0.3) -> None:
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    def configure_from_env(self, user_id: str = None) -> bool:
        """Auto-configure from environment variables, .env file, or DB settings (UI)."""
        from qengine.services.env import ENV_VALUES

        def _get(key: str, default: str = '') -> str:
            return os.environ.get(key, '') or ENV_VALUES.get(key, '') or default

        # Try env vars / .env first
        gemini_key = _get('GEMINI_API_KEY')
        if gemini_key:
            self.provider = 'gemini'
            self.api_key = gemini_key
            self.model = _get('LLM_MODEL', 'gemini-2.5-flash')
            return True

        anthropic_key = _get('ANTHROPIC_API_KEY')
        if anthropic_key:
            self.provider = 'anthropic'
            self.api_key = anthropic_key
            self.model = _get('LLM_MODEL', 'claude-sonnet-4-6')
            return True

        openai_key = _get('OPENAI_API_KEY')
        if openai_key:
            self.provider = 'openai'
            self.api_key = openai_key
            self.model = _get('LLM_MODEL', 'gpt-4o')
            return True

        # Fallback: check DB-stored LLM settings (configured via UI)
        try:
            from qengine.controllers.settings_controller import _get_settings_from_db, ADMIN_SETTINGS_ID
            settings = _get_settings_from_db(user_id or ADMIN_SETTINGS_ID)
            llm_conf = settings.get('llm', {})
            if llm_conf.get('api_key') and llm_conf.get('provider'):
                self.provider = llm_conf['provider']
                self.api_key = llm_conf['api_key']
                self.model = llm_conf.get('model', '')
                self.temperature = llm_conf.get('temperature', 0.3)
                return True
        except Exception:
            pass

        return False

    @property
    def is_configured(self) -> bool:
        return self.provider is not None and self.api_key is not None

    def generate_strategy(
        self,
        description: str,
        asset_class: str = 'forex',
        symbol: str = 'EUR-USD',
    ) -> dict:
        """
        Generate a strategy from natural language description.

        Returns:
            {
                'code': str,           # Complete Python strategy class
                'explanation': str,     # What the strategy does
                'valid': bool,          # Whether the code is syntactically valid
                'errors': list,         # Syntax errors if any
            }
        """
        if not self.is_configured:
            return {
                'code': '',
                'explanation': '',
                'valid': False,
                'errors': ['LLM not configured. Set provider and API key.'],
            }

        system_prompt = self._build_system_prompt(asset_class)
        user_prompt = self._build_user_prompt(description, symbol)

        response = self._call_llm(system_prompt, user_prompt)
        code = self._extract_code(response)
        code = self._clean_code(code)
        validation = self.validate_strategy(code)

        # Self-heal: if syntax error, ask LLM to fix it once
        if not validation['valid'] and any('Syntax error' in e for e in validation.get('errors', [])):
            code = self._fix_syntax(code, validation['errors'])
            validation = self.validate_strategy(code)

        return {
            'code': code,
            'explanation': response,
            'valid': validation['valid'],
            'errors': validation.get('errors', []),
        }

    def refine_strategy(
        self,
        current_code: str,
        feedback: str,
        backtest_results: dict = None,
    ) -> dict:
        """Refine an existing strategy based on user feedback and/or backtest results."""
        if not self.is_configured:
            return {
                'code': current_code,
                'explanation': 'LLM not configured.',
                'valid': False,
                'errors': ['LLM not configured.'],
            }

        bt_context = ''
        if backtest_results:
            bt_context = f'\n\nBacktest results:\n{_format_backtest_results(backtest_results)}'

        prompt = f"""Current strategy code:
```python
{current_code}
```

User feedback: {feedback}
{bt_context}

Please improve the strategy based on the feedback. Output ONLY the complete updated Python strategy class."""

        response = self._call_llm(self._build_system_prompt(), prompt)
        code = self._extract_code(response)
        code = self._clean_code(code)
        validation = self.validate_strategy(code)

        # Self-heal: if syntax error, ask LLM to fix it once
        if not validation['valid'] and any('Syntax error' in e for e in validation.get('errors', [])):
            code = self._fix_syntax(code, validation['errors'])
            validation = self.validate_strategy(code)

        return {
            'code': code,
            'explanation': response,
            'valid': validation['valid'],
            'errors': validation.get('errors', []),
        }

    def validate_strategy(self, code: str) -> dict:
        """Validate generated strategy code - syntax check + structure check."""
        if not code or not code.strip():
            return {'valid': False, 'errors': ['Empty code']}

        errors = []

        # Syntax check
        try:
            compile(code, '<strategy>', 'exec')
        except SyntaxError as e:
            errors.append(f'Syntax error: {e}')
            return {'valid': False, 'errors': errors}

        # Structure check: must have Strategy base class
        if 'Strategy' not in code:
            errors.append('Code must extend the Strategy base class')

        # Must have required methods
        required_methods = ['should_long', 'go_long', 'should_short', 'go_short']
        for method in required_methods:
            if f'def {method}' not in code:
                errors.append(f'Missing required method: {method}()')

        if errors:
            return {'valid': False, 'errors': errors}

        return {'valid': True, 'errors': []}

    def _clean_code(self, code: str) -> str:
        """Remove common non-code artifacts from extracted code."""
        if not code:
            return code

        lines = code.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # Skip markdown artifacts
            if stripped.startswith('```'):
                continue
            # Skip common LLM preamble lines
            if stripped.lower().startswith(('here is', 'here\'s', 'below is', 'sure,', 'certainly')):
                continue
            # Skip lines that are clearly not code and appear before any import/class
            if not cleaned and stripped and not stripped.startswith(('#', 'import', 'from', 'class', '@', '"', "'")):
                # Check if it looks like natural language (no = or : or ( in non-comment)
                if '=' not in stripped and '(' not in stripped and ':' not in stripped:
                    continue
            cleaned.append(line)

        # Strip leading/trailing empty lines
        result = '\n'.join(cleaned).strip()
        return result if result else code

    def _fix_syntax(self, code: str, errors: list) -> str:
        """Ask LLM to fix syntax errors in generated code."""
        if not self.is_configured:
            return code

        try:
            fix_prompt = f"""The following Python strategy code has syntax errors. Fix ONLY the syntax errors and output the complete corrected code. Do NOT add explanations - output ONLY the Python code.

Errors: {'; '.join(errors)}

Code:
```python
{code}
```"""
            response = self._call_llm(
                "You are a Python syntax fixer. Output ONLY valid Python code, nothing else. No explanations, no markdown.",
                fix_prompt,
            )
            fixed = self._extract_code(response)
            fixed = self._clean_code(fixed)
            return fixed if fixed else code
        except Exception:
            return code

    def _build_system_prompt(self, asset_class: str = 'forex') -> str:
        """Build system prompt with strategy template and framework docs."""
        # Try to load StrategyAGENT.md for comprehensive context
        agent_guide = self._load_strategy_agent_guide()
        if agent_guide:
            return f"""You are a trading strategy developer for the TradeEngine framework.
You write Python strategies that extend the Strategy base class.

Asset class: {asset_class}

{agent_guide}

CRITICAL RULES:
1. Output ONLY valid Python code for a complete strategy class
2. The class MUST import and extend Strategy: from qengine.strategies import Strategy
3. Import indicators: import qengine.indicators as ta
4. MUST implement: should_long(), go_long(), should_short(), go_short()
5. Use self.lot_size_for_risk(risk_pct, stop_pips) for position sizing (forex/CFD)
6. Use self.pips_to_price() for stop/TP distances (forex/CFD)
7. Always include hyperparameters() for tunable values
8. Always set stop_loss in go_long()/go_short() for risk management
9. Include should_cancel_entry() returning True
10. Filters are method references WITHOUT parentheses
11. should_long/should_short MUST return bool, not indicator values"""
        else:
            return self._build_fallback_system_prompt(asset_class)

    def _load_strategy_agent_guide(self) -> str:
        """Load StrategyAGENT.md if available."""
        import pathlib
        # Check multiple possible locations
        candidates = [
            pathlib.Path(__file__).parent.parent.parent / 'StrategyAGENT.md',
            pathlib.Path.cwd() / 'StrategyAGENT.md',
        ]
        for path in candidates:
            try:
                if path.exists():
                    content = path.read_text(encoding='utf-8')
                    # Truncate if too long for context window (keep under 12k chars)
                    if len(content) > 12000:
                        content = content[:12000] + '\n\n[... truncated for context limit]'
                    return content
            except Exception:
                continue
        return ''

    def _build_fallback_system_prompt(self, asset_class: str = 'forex') -> str:
        """Fallback system prompt when StrategyAGENT.md is not available."""
        return f"""You are a trading strategy developer for the TradeEngine framework.
You write Python strategies that extend the Strategy base class.

Asset class: {asset_class}

PRICE & CANDLE DATA:
- self.price, self.open, self.high, self.low, self.close, self.volume
- self.candles: numpy array shape (N, 6) = [timestamp, open, close, high, low, volume]
- self.current_candle: single candle array
- self.get_candles(exchange, symbol, timeframe): candles from another route
- self.time: current timestamp in milliseconds

POSITION PROPERTIES:
- self.is_long, self.is_short, self.is_open, self.is_close (booleans)
- self.position.qty, self.position.entry_price, self.position.pnl
- self.average_entry_price, self.average_stop_loss, self.average_take_profit

ACCOUNT:
- self.balance, self.available_margin, self.leveraged_available_margin
- self.leverage, self.fee_rate, self.portfolio_value, self.capital

FOREX/CFD SPECIFIC:
- self.asset_class: 'forex', 'commodity', 'index', 'stock', 'crypto'
- self.pip_size: pip size for instrument (0.0001 for EUR-USD, 0.01 for JPY pairs)
- self.contract_size: standard lot size (100000 for forex)
- self.spread: current spread in price units
- self.session: 'tokyo', 'london', 'new_york', 'overlap', 'off'
- self.market_is_open: bool
- self.minutes_to_close: int or None
- self.swap_long, self.swap_short: overnight swap rates
- self.pips_to_price(pips): convert pips to price distance
- self.price_to_pips(distance): convert price distance to pips
- self.lot_size_for_risk(risk_pct, stop_pips): lot size for % risk and pip stop distance

MODE DETECTION:
- self.is_backtesting, self.is_livetrading, self.is_papertrading, self.is_live

STRATEGY VARIABLES:
- self.vars: dict (resets between trades)
- self.shared_vars: dict (persists across all strategies)
- self.index: current candle index
- self.hp: hyperparameters dict, access via self.hp.get('name', default)

LIFECYCLE METHODS (optional overrides):
- before(): runs before strategy logic each candle
- after(): runs after strategy logic each candle
- update_position(): runs every candle while position open (trailing stops)
- on_open_position(order): fires when position opens
- on_close_position(order, closed_trade): fires when position closes
- on_increased_position(order): fires on position increase
- on_reduced_position(order): fires on position decrease
- on_cancel(): fires when entry orders cancelled
- filters(): return list of filter method references (without parentheses)
- hyperparameters(): return list of param dicts
- watch_list(): return list of dicts for live monitoring
- should_cancel_entry(): return bool (default True)

ORDER SYNTAX:
  self.buy = (qty, price)  OR  [(qty1, p1), (qty2, p2)]
  self.sell = (qty, price)  OR  [(qty1, p1), (qty2, p2)]
  self.stop_loss = (qty, price)  OR  [(qty1, p1), (qty2, p2)]
  self.take_profit = (qty, price)  OR  [(qty1, p1), (qty2, p2)]

CHARTING:
- self.add_line_to_candle_chart(title, value, color)
- self.add_extra_line_chart(chart_name, title, value, color)
- self.add_horizontal_line_to_candle_chart(title, value, color, line_style)

INDICATORS (import qengine.indicators as ta):
Trend: sma, ema, dema, tema, hma, kama, alma, wma, vwma, supertrend, ichimoku_cloud, macd, adx, aroon, sar
Momentum: rsi, stoch, srsi, cci, mfi, willr, roc, mom, tsi, ao, fisher
Volatility: atr, natr, bollinger_bands, keltner, donchian, stddev, trange
Volume: obv, ad, adosc, vpt, efi
Advanced: squeeze_momentum, ttm_squeeze, waddah_attar_explosion, hull_suit, hurst_exponent, zscore
170+ total indicators available.

CRITICAL RULES:
1. Output ONLY valid Python code for a complete strategy class
2. MUST: from qengine.strategies import Strategy; import qengine.indicators as ta
3. MUST implement: should_long()->bool, go_long(), should_short()->bool, go_short()
4. Use self.lot_size_for_risk() for position sizing (forex/CFD)
5. Use self.pips_to_price() for SL/TP distances (forex/CFD)
6. Always include hyperparameters() for tunable values
7. Always set stop_loss for risk management
8. Filters passed as method references WITHOUT parentheses"""

    def _build_user_prompt(self, description: str, symbol: str) -> str:
        return f"""Create a trading strategy for {symbol}.

Description: {description}

Requirements:
1. Complete Python class extending Strategy
2. Include all 4 required methods (should_long, go_long, should_short, go_short)
3. Use proper risk management (position sizing based on account risk)
4. Include should_cancel_entry() if appropriate
5. Add hyperparameters() for key parameters that could be optimized"""

    def _extract_code(self, response: str) -> str:
        """Extract Python code from LLM response."""
        # Try to find python code blocks (greedy - take the longest one)
        code_blocks = re.findall(r'```python\s*(.*?)```', response, re.DOTALL)
        if code_blocks:
            # Pick the block that contains 'class' and 'Strategy'
            for block in code_blocks:
                if 'class ' in block and 'Strategy' in block:
                    return block.strip()
            return code_blocks[0].strip()

        # Try generic code blocks
        code_blocks = re.findall(r'```\s*(.*?)```', response, re.DOTALL)
        if code_blocks:
            for block in code_blocks:
                if 'class ' in block and 'Strategy' in block:
                    return block.strip()
            return code_blocks[0].strip()

        # No code blocks found - try to extract from raw text
        # Find everything starting from the first import or class statement
        lines = response.split('\n')
        code_start = None
        code_end = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if code_start is None and (
                stripped.startswith('import ') or
                stripped.startswith('from ') or
                stripped.startswith('class ')
            ):
                code_start = i
            # Track the last line that looks like code (indented or keyword)
            if code_start is not None and stripped and not stripped.startswith('#') and (
                line[0:1] in (' ', '\t') or
                stripped.startswith(('import ', 'from ', 'class ', 'def ', '@', ')'))
                or stripped in ('', 'pass', 'return', 'True', 'False')
            ):
                code_end = i

        if code_start is not None:
            end = (code_end or len(lines) - 1) + 1
            extracted = '\n'.join(lines[code_start:end]).strip()
            if 'class ' in extracted and 'Strategy' in extracted:
                return extracted

        # Last resort: return as-is
        return response.strip()

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the configured LLM provider."""
        if self.provider == 'gemini':
            return self._call_gemini(system_prompt, user_prompt)
        elif self.provider == 'anthropic':
            return self._call_anthropic(system_prompt, user_prompt)
        elif self.provider == 'openai':
            return self._call_openai(system_prompt, user_prompt)
        else:
            raise ValueError(f'Unsupported LLM provider: {self.provider}')

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        from google import genai
        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model or 'gemini-2.5-flash',
            contents=f'{system_prompt}\n\n{user_prompt}',
            config={
                'temperature': self.temperature,
                'max_output_tokens': self.max_tokens,
            },
        )
        return response.text

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model or 'claude-sonnet-4-6',
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}]
        )
        return response.content[0].text

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model or 'gpt-4o',
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ]
        )
        return response.choices[0].message.content


def _format_backtest_results(results: dict) -> str:
    """Format backtest results for LLM context."""
    keys = ['total', 'win_rate', 'net_profit_percentage', 'max_drawdown',
            'sharpe_ratio', 'sortino_ratio', 'total_pips', 'avg_pips_per_trade']
    lines = []
    for k in keys:
        if k in results:
            lines.append(f'  {k}: {results[k]}')
    return '\n'.join(lines)


# Global singleton
llm_engine = LLMEngine()
