"""AgentPilot configuration with defaults and deep-merge."""
import copy
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    'warmup': 50,                        # bars before pipeline activates
    'llm': {
        'provider': None,                # 'ollama', 'anthropic', 'openai', 'gemini' (auto-detect)
        'api_key': None,                 # not needed for ollama
        'model': None,                   # provider default if None (ollama: qwen2.5:7b)
        'temperature': 0.2,              # low for reproducibility
        'max_tokens': 2048,
        'ollama_url': 'http://localhost:11434',  # Ollama server URL
    },
    'scanner': {
        'min_consult_interval': 480,     # min bars between market trigger consultations
        'atr_spike_mult': 2.0,           # ATR > mult * rolling_mean triggers consult
        'rsi_thresholds': [25, 75],      # RSI crossing these triggers consult
        'danger_thresholds': [0.25, 0.75],  # danger score crossing triggers consult
        'max_hold_bars': 960,            # consult if position held this long without check
        'enabled': True,
    },
    'journal': {
        'max_entries': 50,               # rolling window of past decisions
        'include_in_prompt': 10,         # last N entries sent to LLM
    },
    'sizing': {
        'confidence_scaling': True,      # scale size by confidence score
        'min_confidence': 0.3,           # block entry below this confidence
        'max_sizing_pct': 0.05,          # cap at 5% of balance per entry
    },
    'cache': {
        'enabled': True,
        'max_size': 10000,               # max cached decisions
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning new dict."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def merge_config(user_config: dict) -> dict:
    """Deep merge user config over defaults."""
    if not user_config:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_config)
