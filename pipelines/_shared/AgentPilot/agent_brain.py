"""AgentBrain — LLM API calls, caching, and response parsing."""
from __future__ import annotations
import hashlib
import json
import os
import re
from collections import OrderedDict
from typing import Optional

from .decision import AgentDecision


class AgentBrain:
    """
    Manages LLM API calls with provider switching, caching, and response parsing.

    Supports:
      - ollama   — Local models via Ollama (no API key, fastest)
      - anthropic — Claude (cloud)
      - openai   — GPT / any OpenAI-compatible API (cloud)
      - gemini   — Google Gemini (cloud)

    Provider is auto-detected: ollama (if running) > env API keys.
    """

    # Default models per provider
    _DEFAULT_MODELS = {
        'ollama': 'gemma4:latest',
        'anthropic': 'claude-sonnet-4-6',
        'openai': 'gpt-4o',
        'gemini': 'gemini-2.5-flash',
    }

    def __init__(self, config: dict):
        llm_cfg = config.get('llm', {})
        cache_cfg = config.get('cache', {})

        self._provider: Optional[str] = llm_cfg.get('provider')
        self._api_key: Optional[str] = llm_cfg.get('api_key')
        self._model: Optional[str] = llm_cfg.get('model')
        self._temperature: float = llm_cfg.get('temperature', 0.2)
        self._max_tokens: int = llm_cfg.get('max_tokens', 2048)
        self._ollama_base_url: str = llm_cfg.get('ollama_url', 'http://localhost:11434')

        # Cache: OrderedDict for LRU-like behavior
        self._cache_enabled = cache_cfg.get('enabled', True)
        self._cache_max = cache_cfg.get('max_size', 10000)
        self._cache: OrderedDict[str, dict] = OrderedDict()

        # Stats
        self.api_calls: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.errors: int = 0

        # Auto-configure if not explicitly set
        if not self._provider:
            self._auto_configure()

    @property
    def is_configured(self) -> bool:
        # Ollama doesn't need an API key
        if self._provider == 'ollama':
            return True
        return self._provider is not None and self._api_key is not None

    @property
    def provider(self) -> Optional[str]:
        return self._provider

    @property
    def model(self) -> Optional[str]:
        return self._model

    def consult(self, system_prompt: str, user_prompt: str) -> AgentDecision:
        """Consult the LLM. Returns an AgentDecision."""
        result, _ = self.consult_with_raw(system_prompt, user_prompt)
        return result

    def consult_with_raw(self, system_prompt: str, user_prompt: str) -> tuple[AgentDecision, str]:
        """
        Consult the LLM. Returns (AgentDecision, raw_response).

        Checks cache first. On cache miss, calls the API and caches the result.
        On any error, returns a safe 'hold' decision.
        """
        if not self.is_configured:
            return AgentDecision(signal='hold', reasoning='LLM not configured'), ''

        # Cache lookup
        state_hash = self._hash_prompt(user_prompt)
        if self._cache_enabled and state_hash in self._cache:
            self.cache_hits += 1
            cached = self._cache[state_hash]
            return AgentDecision.from_dict(cached), cached.get('_raw', '')

        self.cache_misses += 1

        # API call
        try:
            raw_response = self._call_llm(system_prompt, user_prompt)
            decision_dict = self._parse_response(raw_response)
            decision = AgentDecision.from_dict(decision_dict)

            # Cache result (include raw for audit)
            if self._cache_enabled:
                cache_entry = decision.to_dict()
                cache_entry['_raw'] = raw_response[:2000]
                self._cache[state_hash] = cache_entry
                while len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)

            self.api_calls += 1
            return decision, raw_response

        except Exception as e:
            self.errors += 1
            return AgentDecision(
                signal='hold',
                reasoning=f'LLM error: {str(e)[:100]}',
                confidence=0.0,
            ), f'ERROR: {str(e)[:200]}'

    # ── Provider Dispatch ──

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the configured LLM provider."""
        if self._provider == 'ollama':
            return self._call_ollama(system_prompt, user_prompt)
        elif self._provider == 'anthropic':
            return self._call_anthropic(system_prompt, user_prompt)
        elif self._provider == 'openai':
            return self._call_openai(system_prompt, user_prompt)
        elif self._provider == 'gemini':
            return self._call_gemini(system_prompt, user_prompt)
        else:
            raise ValueError(f'Unsupported provider: {self._provider}')

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Call Ollama's OpenAI-compatible API at localhost:11434."""
        import urllib.request
        import urllib.error

        url = f'{self._ollama_base_url}/v1/chat/completions'
        model = self._model or self._DEFAULT_MODELS['ollama']

        payload = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': self._temperature,
            'max_tokens': self._max_tokens,
            'stream': False,
        }).encode('utf-8')

        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data['choices'][0]['message']['content']
        except urllib.error.URLError as e:
            raise ConnectionError(
                f'Ollama not reachable at {self._ollama_base_url}. '
                f'Is it running? Start with: ollama serve\n'
                f'Error: {e}'
            )

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self._model or self._DEFAULT_MODELS['anthropic'],
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        return response.content[0].text

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        import openai
        client = openai.OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model or self._DEFAULT_MODELS['openai'],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        )
        return response.choices[0].message.content

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        from google import genai
        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model or self._DEFAULT_MODELS['gemini'],
            contents=f'{system_prompt}\n\n{user_prompt}',
            config={
                'temperature': self._temperature,
                'max_output_tokens': self._max_tokens,
            },
        )
        return response.text

    # ── Response Parsing ──

    def _parse_response(self, raw: str) -> dict:
        """Parse LLM response into a decision dict. Handles JSON in code fences, raw JSON, or partial."""
        cleaned = raw.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()

        # Try direct JSON parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the response (handles nested objects)
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: extract key fields with regex
        return self._extract_fields_regex(cleaned)

    def _extract_fields_regex(self, text: str) -> dict:
        """Last-resort field extraction from malformed JSON."""
        result = {}
        signal_match = re.search(r'"signal"\s*:\s*"(\w+)"', text)
        if signal_match:
            result['signal'] = signal_match.group(1)
        conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
        if conf_match:
            result['confidence'] = float(conf_match.group(1))
        sizing_match = re.search(r'"sizing_pct"\s*:\s*([\d.]+)', text)
        if sizing_match:
            result['sizing_pct'] = float(sizing_match.group(1))
        reason_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', text)
        if reason_match:
            result['reasoning'] = reason_match.group(1)
        return result

    def _hash_prompt(self, prompt: str) -> str:
        """Hash prompt for cache key (ignores whitespace variations)."""
        normalized = ' '.join(prompt.split())
        return hashlib.md5(normalized.encode()).hexdigest()

    # ── Auto-Configuration ──

    def _auto_configure(self) -> None:
        """
        Auto-detect LLM provider. Priority:
          1. Ollama (if running locally — free, fast)
          2. Gemini (env key)
          3. Anthropic (env key)
          4. OpenAI (env key)
        """
        # 1. Check if Ollama is running locally
        if self._check_ollama():
            self._provider = 'ollama'
            self._model = self._model or self._DEFAULT_MODELS['ollama']
            return

        # 2. Check env vars for cloud providers
        from qengine.services.env import ENV_VALUES

        def _get(key: str) -> str:
            return os.environ.get(key, '') or ENV_VALUES.get(key, '')

        gemini_key = _get('GEMINI_API_KEY')
        if gemini_key:
            self._provider = 'gemini'
            self._api_key = gemini_key
            self._model = self._model or _get('LLM_MODEL') or self._DEFAULT_MODELS['gemini']
            return

        anthropic_key = _get('ANTHROPIC_API_KEY')
        if anthropic_key:
            self._provider = 'anthropic'
            self._api_key = anthropic_key
            self._model = self._model or _get('LLM_MODEL') or self._DEFAULT_MODELS['anthropic']
            return

        openai_key = _get('OPENAI_API_KEY')
        if openai_key:
            self._provider = 'openai'
            self._api_key = openai_key
            self._model = self._model or _get('LLM_MODEL') or self._DEFAULT_MODELS['openai']
            return

    def _check_ollama(self) -> bool:
        """Check if Ollama is running locally by pinging its API."""
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(
                f'{self._ollama_base_url}/api/tags',
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    # Check if our preferred model is available
                    data = json.loads(resp.read().decode('utf-8'))
                    models = [m.get('name', '') for m in data.get('models', [])]
                    # If any model is available, Ollama is good to go
                    if models:
                        # Try to use our preferred model if available
                        preferred = self._model or self._DEFAULT_MODELS['ollama']
                        if any(preferred in m for m in models):
                            self._model = preferred
                        else:
                            # Use first available model
                            self._model = models[0]
                        return True
            return False
        except (urllib.error.URLError, OSError, Exception):
            return False

    # ── Persistence ──

    def save_cache(self, path: str) -> None:
        cache_file = os.path.join(path, 'decision_cache.json')
        try:
            with open(cache_file, 'w') as f:
                json.dump(dict(self._cache), f)
        except Exception:
            pass

    def load_cache(self, path: str) -> None:
        cache_file = os.path.join(path, 'decision_cache.json')
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                self._cache = OrderedDict(data)
        except Exception:
            pass

    def state_dict(self) -> dict:
        return {
            'provider': self._provider,
            'model': self._model,
            'temperature': self._temperature,
            'api_calls': self.api_calls,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'errors': self.errors,
            'cache_size': len(self._cache),
        }
