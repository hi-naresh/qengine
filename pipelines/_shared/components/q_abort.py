import os
import numpy as np


# State dimensions (matches phase2 notebook 19b exactly)
N_LEVELS = 13         # hedge levels 0-12
N_DURATION_BINS = 5   # [0-5, 5-10, 10-20, 20-50, 50+] bars
N_DANGER_BINS = 5     # discretized danger score bins
N_ACTIONS = 2         # 0=continue, 1=abort

DURATION_EDGES = [5, 10, 20, 50]
DANGER_EDGES = [0.3, 0.5, 0.7, 0.85]

TOTAL_STATES = N_LEVELS * N_DURATION_BINS * N_DANGER_BINS * N_DANGER_BINS  # 1625

# Valid modes
MODE_EVAL = 'eval'      # frozen policy, no learning (production)
MODE_TRAIN = 'train'    # epsilon-greedy exploration + learning (research)
MODE_ONLINE = 'online'  # learns from experience but no forced exploration (legacy)


def _bin_duration(bars: int) -> int:
    for i, edge in enumerate(DURATION_EDGES):
        if bars < edge:
            return i
    return len(DURATION_EDGES)


def _bin_danger(score: float) -> int:
    for i, edge in enumerate(DANGER_EDGES):
        if score < edge:
            return i
    return len(DANGER_EDGES)


def _encode_state(level: int, duration_bars: int, danger_entry: float, danger_now: float) -> int:
    """Flatten (level, duration_bin, danger_entry_bin, danger_now_bin) → single int index."""
    l = min(level, N_LEVELS - 1)
    d = _bin_duration(duration_bars)
    de = _bin_danger(danger_entry)
    dn = _bin_danger(danger_now)
    return (l * N_DURATION_BINS * N_DANGER_BINS * N_DANGER_BINS
            + d * N_DANGER_BINS * N_DANGER_BINS
            + de * N_DANGER_BINS
            + dn)


class QAbort:
    """
    Tabular Q-learning agent for mid-cycle abort decisions.

    State: (level, duration_bin, danger_at_entry, danger_now) → 1,625 states
    Actions: {0: continue, 1: abort}

    Modes:
        'eval'   — Frozen pre-trained policy. No learning, no exploration.
                   Use in production / backtesting with a trained model.
        'train'  — Full RL training. Epsilon-greedy exploration + Q-updates.
                   Use in research notebooks for training new Q-tables.
        'online' — Learns from experience but only explores via epsilon config.
                   Legacy mode, not recommended (cascade bug with epsilon=0).

    Phase2 research (19b) trained on 60,370 cycles over 20yr EUR-USD:
        - 449 states visited, 45 prefer abort, 404 prefer continue
        - Bust rate: 0.17% → 0.12% (-32% reduction)
        - Abort rate: only 0.16% (surgical, not aggressive)
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.alpha = config.get('alpha', 0.01)
        self.gamma = config.get('gamma', 0.95)
        self.epsilon = config.get('epsilon', 0.0)
        self.enabled = config.get('enabled', True)

        # Mode determines learning behavior
        self.mode = config.get('mode', MODE_EVAL)
        if self.mode not in (MODE_EVAL, MODE_TRAIN, MODE_ONLINE):
            self.mode = MODE_EVAL

        # Training mode requires exploration
        if self.mode == MODE_TRAIN and self.epsilon <= 0:
            self.epsilon = 0.15  # phase2 default start epsilon

        self.epsilon_min = config.get('epsilon_min', 0.02)
        self.epsilon_decay = config.get('epsilon_decay', 0.998)

        self.q_table = np.zeros((TOTAL_STATES, N_ACTIONS), dtype=np.float64)
        self.visit_count = np.zeros((TOTAL_STATES, N_ACTIONS), dtype=np.int64)

        # Load pre-trained Q-table if path provided
        q_path = config.get('q_table_path')
        if q_path and os.path.exists(q_path):
            self.q_table = np.load(q_path)
        vc_path = config.get('visit_count_path')
        if vc_path and os.path.exists(vc_path):
            self.visit_count = np.load(vc_path)

        self._pretrained = bool(
            (q_path and os.path.exists(q_path))
            or np.any(self.q_table != 0)
        )

        # Track current episode for learning
        self._episode_states = []   # [(state_idx, action_idx), ...]
        self._episode_active = False

        # Training stats
        self._episodes_completed = 0

    @property
    def is_learning(self) -> bool:
        return self.mode in (MODE_TRAIN, MODE_ONLINE)

    def decide(self, level: int, duration_bars: int,
               danger_entry: float, danger_now: float) -> str:
        """
        Decide whether to continue or abort.
        Returns 'continue' or 'abort'.
        """
        if not self.enabled:
            return 'continue'

        state = _encode_state(level, duration_bars, danger_entry, danger_now)

        if self.mode == MODE_TRAIN and self.epsilon > 0 and np.random.random() < self.epsilon:
            # Training: epsilon-greedy exploration
            action = np.random.randint(N_ACTIONS)
        elif self._pretrained:
            # Pre-trained table: trust learned Q-values directly
            action = int(np.argmax(self.q_table[state]))
        else:
            # No pre-trained table: only prefer abort if actually explored.
            # Without this, untried abort (Q=0) beats learned-negative continue,
            # causing a runaway abort cascade after any loss.
            if self.visit_count[state, 1] == 0:
                action = 0  # continue — abort never tried here
            else:
                action = int(np.argmax(self.q_table[state]))

        # Track for learning (only in learning modes)
        if self.is_learning and self._episode_active:
            self._episode_states.append((state, action))

        self.visit_count[state, action] += 1

        return 'abort' if action == 1 else 'continue'

    def start_episode(self):
        """Call when a new cycle begins."""
        self._episode_states = []
        self._episode_active = True

    def end_episode(self, reward: float):
        """
        Call when cycle ends (TP hit, bust, or abort).
        In eval mode, this is a no-op (frozen policy).
        In train/online mode, applies Q-learning update.
        """
        if not self._episode_active or not self._episode_states:
            self._episode_active = False
            return

        # Only update Q-values in learning modes
        if self.is_learning:
            for i in range(len(self._episode_states) - 1, -1, -1):
                state, action = self._episode_states[i]

                if i == len(self._episode_states) - 1:
                    target = reward
                else:
                    next_state = self._episode_states[i + 1][0]
                    target = reward + self.gamma * np.max(self.q_table[next_state])
                    reward *= self.gamma

                self.q_table[state, action] += self.alpha * (target - self.q_table[state, action])

            # Decay epsilon in training mode
            if self.mode == MODE_TRAIN and self.epsilon > self.epsilon_min:
                self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)

        self._episodes_completed += 1
        self._episode_active = False
        self._episode_states = []

    @property
    def stats(self) -> dict:
        visited = int(np.sum(self.visit_count > 0))
        total_visits = int(np.sum(self.visit_count))

        nonzero = self.q_table[self.q_table != 0]
        q_stats = {}
        if len(nonzero) > 0:
            q_stats = {
                'q_mean': round(float(np.mean(nonzero)), 6),
                'q_std': round(float(np.std(nonzero)), 6),
                'q_min': round(float(np.min(nonzero)), 6),
                'q_max': round(float(np.max(nonzero)), 6),
            }

        abort_preferred = 0
        continue_preferred = 0
        for s in range(TOTAL_STATES):
            if self.visit_count[s].sum() > 0:
                if self.q_table[s, 1] > self.q_table[s, 0]:
                    abort_preferred += 1
                else:
                    continue_preferred += 1

        # Most visited states
        flat_visits = self.visit_count.sum(axis=1)
        top_states_idx = np.argsort(flat_visits)[-5:][::-1]
        top_states = []
        for idx in top_states_idx:
            if flat_visits[idx] == 0:
                break
            dn = idx % N_DANGER_BINS
            rem = idx // N_DANGER_BINS
            de = rem % N_DANGER_BINS
            rem = rem // N_DANGER_BINS
            d = rem % N_DURATION_BINS
            l = rem // N_DURATION_BINS
            top_states.append({
                'level': int(l),
                'duration_bin': int(d),
                'danger_entry_bin': int(de),
                'danger_now_bin': int(dn),
                'visits': int(flat_visits[idx]),
                'q_continue': round(float(self.q_table[idx, 0]), 6),
                'q_abort': round(float(self.q_table[idx, 1]), 6),
                'policy': 'abort' if self.q_table[idx, 1] > self.q_table[idx, 0] else 'continue',
            })

        return {
            'enabled': self.enabled,
            'mode': self.mode,
            'pretrained': self._pretrained,
            'alpha': self.alpha,
            'gamma': self.gamma,
            'epsilon': round(self.epsilon, 4),
            'episodes_completed': self._episodes_completed,
            'states_visited': visited,
            'total_states': TOTAL_STATES,
            'coverage': round(visited / TOTAL_STATES, 4),
            'total_visits': total_visits,
            'abort_preferred_states': abort_preferred,
            'continue_preferred_states': continue_preferred,
            'top_states': top_states,
            **q_stats,
        }

    def save(self, path: str):
        np.save(os.path.join(path, 'q_table.npy'), self.q_table)
        np.save(os.path.join(path, 'q_visit_count.npy'), self.visit_count)

    def load(self, path: str):
        q_path = os.path.join(path, 'q_table.npy')
        v_path = os.path.join(path, 'q_visit_count.npy')
        if os.path.exists(q_path):
            self.q_table = np.load(q_path)
            self._pretrained = True
        if os.path.exists(v_path):
            self.visit_count = np.load(v_path)
