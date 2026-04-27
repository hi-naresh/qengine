"""
FinRLPilot — policy module.

Dependency fallback order:
    1. stable-baselines3 (ideal — used as a gym-style PPO trainer)
    2. plain PyTorch (custom PPO with MLP 2x64)
    3. Tabular, state-discretised Q-learner (same shape as GridPilot.QAbort)

At import time we detect which backends are available and expose a single
`build_policy(config)` helper that returns a policy object with the API:

    policy.act(state_vec: np.ndarray) -> int       # action in [0, n_actions)
    policy.record(state, action, reward, done)     # add experience
    policy.update()                                 # train step (no-op in eval)
    policy.save(path: str)                          # persist to disk
    policy.load(path: str)                          # restore
    policy.stats() -> dict                          # diagnostics

This lets the pipeline be backend-agnostic.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

HAS_SB3 = False
HAS_TORCH = False
try:
    import stable_baselines3  # noqa: F401
    HAS_SB3 = True
except Exception:
    pass

try:
    import torch  # noqa: F401
    HAS_TORCH = True
except Exception:
    pass


BACKEND: str
# Priority: torch > sb3 > tabular.
# The SB3 wrapper (SB3PPOPolicy) is inference-only — its update() is a no-op
# because offline-RL training against SB3 requires a full gym.Env we don't
# build here. The TorchPPOPolicy is a complete bandit-PPO (record/update/
# save/load), so we prefer it when torch is available. Users who want SB3
# inference from a pre-trained policy.zip can set config['backend_override']
# = 'sb3' explicitly.
if HAS_TORCH:
    BACKEND = 'torch'
elif HAS_SB3:
    BACKEND = 'sb3'
else:
    BACKEND = 'tabular'


# ---------------------------------------------------------------------------
# Tabular fallback Q-learner
# ---------------------------------------------------------------------------

class TabularQPolicy:
    """State-discretised tabular Q-learner — same shape as GridPilot.QAbort.

    We bin the first `feature_subset` features of the state vector into
    `n_bins` bins each. This keeps the table small (n_bins ** feature_subset).

    Action space: discrete, size = n_actions.

    Learning: Q-learning with epsilon-greedy exploration in train mode.

    This is the fallback when neither stable-baselines3 nor PyTorch is
    available. It is NOT a PPO policy — the algorithm is documented in
    get_stats() and pipeline architecture metadata.
    """

    kind = 'tabular'

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.n_actions: int = int(self.config.get('n_actions', 4))
        disc = self.config.get('discretize', {})
        self.n_bins: int = int(disc.get('n_bins', 3))
        self.feature_subset: int = int(disc.get('feature_subset', 4))
        self.state_dim: int = int(self.config.get('state_dim', 10))
        self.mode: str = self.config.get('mode', 'eval')

        policy_cfg = self.config.get('policy', {})
        self.alpha: float = float(policy_cfg.get('lr', 0.1))
        self.gamma: float = float(policy_cfg.get('gamma', 0.99))
        self.epsilon: float = float(policy_cfg.get('entropy_coef', 0.1))

        total_states = self.n_bins ** self.feature_subset
        self.total_states = total_states
        self.q_table: np.ndarray = np.zeros((total_states, self.n_actions), dtype=np.float64)
        self.visit_count: np.ndarray = np.zeros((total_states, self.n_actions), dtype=np.int64)

        # Feature bins — computed lazily using Welford-style running min/max
        self._feat_min: np.ndarray = np.full(self.feature_subset, np.inf)
        self._feat_max: np.ndarray = np.full(self.feature_subset, -np.inf)

        # Trajectory buffer for online updates
        self._buffer: List[dict] = []
        self._rng = np.random.default_rng(42)

        # Stats
        self.total_updates: int = 0
        self.action_counts: Counter = Counter()
        self.reward_history: List[float] = []

    # -- State discretisation ------------------------------------------------

    def _encode_state(self, state_vec: np.ndarray) -> int:
        """Discretise state vec → integer index in [0, total_states)."""
        if state_vec is None:
            return 0
        sv = np.asarray(state_vec, dtype=np.float64).flatten()
        if len(sv) < self.feature_subset:
            sv = np.concatenate([sv, np.zeros(self.feature_subset - len(sv))])
        sv = sv[: self.feature_subset]

        # Update running min/max
        for i in range(self.feature_subset):
            if np.isfinite(sv[i]):
                if sv[i] < self._feat_min[i]:
                    self._feat_min[i] = sv[i]
                if sv[i] > self._feat_max[i]:
                    self._feat_max[i] = sv[i]

        idx = 0
        for i in range(self.feature_subset):
            lo, hi = self._feat_min[i], self._feat_max[i]
            if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-12:
                bin_idx = 0
            else:
                norm = (sv[i] - lo) / (hi - lo)
                bin_idx = int(np.clip(np.floor(norm * self.n_bins), 0, self.n_bins - 1))
            idx = idx * self.n_bins + bin_idx
        return int(idx)

    # -- Public API ----------------------------------------------------------

    def act(self, state_vec: np.ndarray) -> int:
        state_idx = self._encode_state(state_vec)

        if self.mode == 'train' and self._rng.random() < self.epsilon:
            action = int(self._rng.integers(0, self.n_actions))
        else:
            # Greedy — break ties randomly so unvisited states explore
            qvals = self.q_table[state_idx]
            max_q = qvals.max()
            tied = np.flatnonzero(qvals == max_q)
            action = int(self._rng.choice(tied))

        self.action_counts[action] += 1
        return action

    def record(self, state: np.ndarray, action: int, reward: float, done: bool = True) -> None:
        """Add experience. For tabular Q, we treat each cycle as a bandit step:
        no next-state bootstrapping (done=True)."""
        self._buffer.append({
            'state': np.asarray(state, dtype=np.float64).copy() if state is not None else None,
            'action': int(action),
            'reward': float(reward),
            'done': bool(done),
        })
        self.reward_history.append(float(reward))

    def update(self) -> Dict[str, Any]:
        """Apply Q-learning updates from the buffer."""
        if self.mode != 'train' or not self._buffer:
            self._buffer.clear()
            return {'updated': False}

        td_errors: List[float] = []
        for step in self._buffer:
            if step['state'] is None:
                continue
            s_idx = self._encode_state(step['state'])
            a = step['action']
            r = step['reward']
            # Bandit formulation — no next state
            old_q = self.q_table[s_idx, a]
            new_q = old_q + self.alpha * (r - old_q)
            self.q_table[s_idx, a] = new_q
            self.visit_count[s_idx, a] += 1
            td_errors.append(abs(new_q - old_q))

        self.total_updates += 1
        self._buffer.clear()
        return {
            'updated': True,
            'mean_td_error': float(np.mean(td_errors)) if td_errors else 0.0,
            'n_updates': self.total_updates,
        }

    def stats(self) -> Dict[str, Any]:
        visited = int((self.visit_count.sum(axis=1) > 0).sum())
        recent = self.reward_history[-100:] if self.reward_history else []
        return {
            'backend': 'tabular',
            'state_bins': self.n_bins ** self.feature_subset,
            'states_visited': visited,
            'coverage': visited / max(1, self.total_states),
            'total_steps': int(self.visit_count.sum()),
            'total_updates': self.total_updates,
            'action_counts': {int(k): int(v) for k, v in self.action_counts.items()},
            'mean_reward_all': float(np.mean(self.reward_history)) if self.reward_history else 0.0,
            'mean_reward_100': float(np.mean(recent)) if recent else 0.0,
            'reward_std_100': float(np.std(recent)) if recent else 0.0,
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        np.savez(
            path,
            q_table=self.q_table,
            visit_count=self.visit_count,
            feat_min=self._feat_min,
            feat_max=self._feat_max,
        )
        meta_path = path + '.meta.json'
        with open(meta_path, 'w') as f:
            json.dump({
                'backend': 'tabular',
                'n_actions': self.n_actions,
                'n_bins': self.n_bins,
                'feature_subset': self.feature_subset,
                'state_dim': self.state_dim,
                'mode': self.mode,
                'alpha': self.alpha,
                'gamma': self.gamma,
                'epsilon': self.epsilon,
                'total_updates': self.total_updates,
                'action_counts': dict(self.action_counts),
            }, f)

    def load(self, path: str) -> None:
        # Accept both `path` and `path + '.npz'`
        candidate = path if path.endswith('.npz') else path + '.npz'
        if not os.path.exists(candidate):
            candidate = path
        data = np.load(candidate)
        self.q_table = data['q_table']
        self.visit_count = data['visit_count']
        if 'feat_min' in data.files:
            self._feat_min = data['feat_min']
        if 'feat_max' in data.files:
            self._feat_max = data['feat_max']

        meta_path = (path if not path.endswith('.npz') else path[:-4]) + '.meta.json'
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            self.total_updates = int(meta.get('total_updates', 0))
            self.action_counts = Counter({int(k): int(v) for k, v in meta.get('action_counts', {}).items()})


# ---------------------------------------------------------------------------
# Torch-based PPO (used when PyTorch is available but not SB3)
# ---------------------------------------------------------------------------

class TorchPPOPolicy:
    """Minimal PPO with an MLP 2x64 policy & value head.

    Only constructed when PyTorch is importable. Kept compact — the goal is
    functional parity with SB3 for our toy offline setting, not state of the
    art performance.
    """

    kind = 'torch'

    def __init__(self, config: Dict[str, Any]):
        import torch
        import torch.nn as nn

        self.config = config or {}
        self.n_actions: int = int(self.config.get('n_actions', 4))
        self.state_dim: int = int(self.config.get('state_dim', 10))
        self.mode: str = self.config.get('mode', 'eval')

        pc = self.config.get('policy', {})
        self.lr: float = float(pc.get('lr', 3e-4))
        self.gamma: float = float(pc.get('gamma', 0.99))
        self.clip_eps: float = float(pc.get('clip_eps', 0.2))
        self.entropy_coef: float = float(pc.get('entropy_coef', 0.01))
        self.n_epochs: int = int(pc.get('n_epochs', 4))
        self.batch_size: int = int(pc.get('batch_size', 64))
        hidden = int(pc.get('hidden_dim', 64))

        self.torch = torch
        self.nn = nn

        # Shared trunk → policy head + value head
        self.net = nn.Sequential(
            nn.Linear(self.state_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        self.policy_head = nn.Linear(hidden, self.n_actions)
        self.value_head = nn.Linear(hidden, 1)
        self.optim = torch.optim.Adam(
            list(self.net.parameters())
            + list(self.policy_head.parameters())
            + list(self.value_head.parameters()),
            lr=self.lr,
        )

        self._buffer: List[dict] = []
        self.total_updates: int = 0
        self.action_counts: Counter = Counter()
        self.reward_history: List[float] = []

    def _forward(self, state_t):
        h = self.net(state_t)
        return self.policy_head(h), self.value_head(h).squeeze(-1)

    def _safe_state(self, state_vec):
        sv = np.asarray(state_vec, dtype=np.float32).flatten()
        if len(sv) < self.state_dim:
            sv = np.concatenate([sv, np.zeros(self.state_dim - len(sv), dtype=np.float32)])
        return sv[: self.state_dim]

    def act(self, state_vec: np.ndarray) -> int:
        torch = self.torch
        sv = self._safe_state(state_vec)
        sv = np.nan_to_num(sv, nan=0.0, posinf=0.0, neginf=0.0)
        with torch.no_grad():
            logits, _ = self._forward(torch.from_numpy(sv))
            if self.mode == 'train':
                probs = torch.softmax(logits, dim=-1)
                action = int(torch.multinomial(probs, 1).item())
            else:
                action = int(torch.argmax(logits).item())
        self.action_counts[action] += 1
        return action

    def record(self, state: np.ndarray, action: int, reward: float, done: bool = True) -> None:
        self._buffer.append({
            'state': self._safe_state(state),
            'action': int(action),
            'reward': float(reward),
            'done': bool(done),
        })
        self.reward_history.append(float(reward))

    def update(self) -> Dict[str, Any]:
        if self.mode != 'train' or not self._buffer:
            self._buffer.clear()
            return {'updated': False}

        torch = self.torch
        nn = self.nn
        states = torch.from_numpy(np.stack([b['state'] for b in self._buffer]))
        actions = torch.tensor([b['action'] for b in self._buffer], dtype=torch.long)
        rewards = torch.tensor([b['reward'] for b in self._buffer], dtype=torch.float32)
        # Bandit formulation: each cycle is independent — no bootstrapped return
        returns = rewards

        # Normalise returns for stability
        if returns.std() > 1e-6:
            advantages = (returns - returns.mean()) / (returns.std() + 1e-6)
        else:
            advantages = returns - returns.mean()

        # Old log-probs
        with torch.no_grad():
            old_logits, _ = self._forward(states)
            old_logp = torch.log_softmax(old_logits, dim=-1).gather(1, actions.unsqueeze(-1)).squeeze(-1)

        losses = []
        for _ in range(self.n_epochs):
            logits, values = self._forward(states)
            logp = torch.log_softmax(logits, dim=-1).gather(1, actions.unsqueeze(-1)).squeeze(-1)
            ratio = torch.exp(logp - old_logp)
            clipped = torch.clamp(ratio, 1 - self.clip_eps, 1 + self.clip_eps)
            policy_loss = -torch.min(ratio * advantages, clipped * advantages).mean()
            value_loss = ((values - returns) ** 2).mean()
            probs = torch.softmax(logits, dim=-1)
            entropy = -(probs * torch.log(probs.clamp_min(1e-8))).sum(-1).mean()
            loss = policy_loss + 0.5 * value_loss - self.entropy_coef * entropy
            self.optim.zero_grad()
            loss.backward()
            self.optim.step()
            losses.append(float(loss.item()))

        self.total_updates += 1
        self._buffer.clear()
        return {
            'updated': True,
            'mean_loss': float(np.mean(losses)) if losses else 0.0,
            'n_updates': self.total_updates,
        }

    def stats(self) -> Dict[str, Any]:
        recent = self.reward_history[-100:] if self.reward_history else []
        return {
            'backend': 'torch',
            'state_dim': self.state_dim,
            'n_actions': self.n_actions,
            'total_steps': sum(self.action_counts.values()),
            'total_updates': self.total_updates,
            'action_counts': {int(k): int(v) for k, v in self.action_counts.items()},
            'mean_reward_all': float(np.mean(self.reward_history)) if self.reward_history else 0.0,
            'mean_reward_100': float(np.mean(recent)) if recent else 0.0,
            'reward_std_100': float(np.std(recent)) if recent else 0.0,
        }

    def save(self, path: str) -> None:
        torch = self.torch
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        torch.save({
            'net': self.net.state_dict(),
            'policy_head': self.policy_head.state_dict(),
            'value_head': self.value_head.state_dict(),
            'config': {
                'n_actions': self.n_actions,
                'state_dim': self.state_dim,
                'hidden_dim': self.config.get('policy', {}).get('hidden_dim', 64),
            },
            'reward_history': self.reward_history,
            'action_counts': dict(self.action_counts),
            'total_updates': self.total_updates,
        }, path)

    def load(self, path: str) -> None:
        torch = self.torch
        ckpt = torch.load(path, map_location='cpu')
        self.net.load_state_dict(ckpt['net'])
        self.policy_head.load_state_dict(ckpt['policy_head'])
        self.value_head.load_state_dict(ckpt['value_head'])
        self.reward_history = list(ckpt.get('reward_history', []))
        self.action_counts = Counter({int(k): int(v) for k, v in ckpt.get('action_counts', {}).items()})
        self.total_updates = int(ckpt.get('total_updates', 0))


# ---------------------------------------------------------------------------
# SB3 wrapper (thin — full training is in the offline script)
# ---------------------------------------------------------------------------

class SB3PPOPolicy:
    """Thin adapter around stable-baselines3 PPO for inference.

    Training loop lives in the offline script; here we support act/save/load so
    a trained SB3 model loaded from disk can drive live decisions.
    """

    kind = 'sb3'

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.n_actions: int = int(self.config.get('n_actions', 4))
        self.state_dim: int = int(self.config.get('state_dim', 10))
        self.mode: str = self.config.get('mode', 'eval')
        self._model = None  # SB3 model (loaded lazily)
        self._buffer: List[dict] = []
        self.action_counts: Counter = Counter()
        self.reward_history: List[float] = []
        self.total_updates: int = 0

    def _ensure_model(self):
        if self._model is not None:
            return
        # Build a random-policy skeleton so act() works before training
        import stable_baselines3 as sb3
        import gymnasium as gym
        from gymnasium.spaces import Box, Discrete
        # Minimal env — not stepped from here; used only for observation space
        class _StubEnv(gym.Env):
            observation_space = Box(low=-1e6, high=1e6, shape=(self.state_dim,))
            action_space = Discrete(self.n_actions)
            def reset(self, *a, **k):
                return np.zeros(self.state_dim, dtype=np.float32), {}
            def step(self, a):
                return np.zeros(self.state_dim, dtype=np.float32), 0.0, True, False, {}
        # Can't easily build the env class inside the method; fall back to
        # untrained random model if not loaded from disk.
        self._stub_env = None
        self._model = None

    def act(self, state_vec: np.ndarray) -> int:
        sv = np.asarray(state_vec, dtype=np.float32).flatten()
        if len(sv) < self.state_dim:
            sv = np.concatenate([sv, np.zeros(self.state_dim - len(sv), dtype=np.float32)])
        sv = np.nan_to_num(sv[: self.state_dim], nan=0.0, posinf=0.0, neginf=0.0)
        if self._model is None:
            # Random policy until weights are loaded
            action = int(np.random.randint(0, self.n_actions))
        else:
            action, _ = self._model.predict(sv, deterministic=(self.mode != 'train'))
            action = int(action)
        self.action_counts[action] += 1
        return action

    def record(self, state, action, reward, done=True):
        self._buffer.append({'state': state, 'action': action, 'reward': reward, 'done': done})
        self.reward_history.append(float(reward))

    def update(self) -> Dict[str, Any]:
        # Actual training happens in the offline script. Here we no-op.
        self._buffer.clear()
        return {'updated': False, 'note': 'SB3 training is offline-only'}

    def stats(self) -> Dict[str, Any]:
        recent = self.reward_history[-100:] if self.reward_history else []
        return {
            'backend': 'sb3',
            'state_dim': self.state_dim,
            'n_actions': self.n_actions,
            'total_steps': sum(self.action_counts.values()),
            'total_updates': self.total_updates,
            'action_counts': {int(k): int(v) for k, v in self.action_counts.items()},
            'mean_reward_all': float(np.mean(self.reward_history)) if self.reward_history else 0.0,
            'mean_reward_100': float(np.mean(recent)) if recent else 0.0,
            'reward_std_100': float(np.std(recent)) if recent else 0.0,
            'model_loaded': self._model is not None,
        }

    def save(self, path: str) -> None:
        if self._model is not None:
            self._model.save(path)

    def load(self, path: str) -> None:
        try:
            import stable_baselines3 as sb3
            self._model = sb3.PPO.load(path)
        except Exception:
            self._model = None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_policy(config: Dict[str, Any]):
    """Instantiate the best available policy backend.

    Priority: torch > sb3 > tabular (see BACKEND comment above).
    Callers can force a specific backend via config['backend_override'] in
    {'torch', 'sb3', 'tabular'} — useful when a trained policy file on disk
    requires a specific backend to load.
    """
    override = (config or {}).get('backend_override')
    if override == 'torch' and HAS_TORCH:
        return TorchPPOPolicy(config)
    if override == 'sb3' and HAS_SB3:
        return SB3PPOPolicy(config)
    if override == 'tabular':
        return TabularQPolicy(config)

    if HAS_TORCH:
        return TorchPPOPolicy(config)
    if HAS_SB3:
        return SB3PPOPolicy(config)
    return TabularQPolicy(config)
