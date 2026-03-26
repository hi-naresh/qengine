#!/usr/bin/env python3
"""
Script 19: Tabular Q-Learning for Mid-Cycle Abort Decision
============================================================
Learns when to abort a surefire hedge cycle mid-way (take controlled loss)
vs continue (risk catastrophic bust loss).

State = (current_level, regime_at_entry, regime_now, regime_changed)
Action = {continue=0, abort=1}
Reward = realized P&L at cycle termination

Surefire parameters: 12 levels, sqrt(2) multiplier, 0.5% base.
Abort at level L means accepting cumulative loss so far as a controlled exit.
"""

import os, sys, pickle, time
os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict

import qengine.indicators as ta
import qengine.helpers as jh
from qengine.research import get_candles

# ---- Paths -----------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'results')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---- Surefire Parameters ---------------------------------------------------
MAX_LEVELS = 12
MULTIPLIER = np.sqrt(2)
BASE_PCT = 0.005
TP_ATR_MULTIPLE = 0.8
RISK_REWARD = 2.0
ATR_PERIOD = 14
PIP_SIZE = 0.0001
BASE_SIZE = 0.1
PIP_VALUE = 10.0
MAX_BARS_PER_LEVEL = 500
EMA_FAST = 8
EMA_SLOW = 21
STARTING_BALANCE = 10_000

# ---- Q-Learning Parameters -------------------------------------------------
N_LEVELS = 13          # 0..12
N_REGIME_VALS = 10     # regime capped at 0..9
N_REGIME_CHANGED = 2   # 0 or 1
N_STATES = N_LEVELS * N_REGIME_VALS * N_REGIME_VALS * N_REGIME_CHANGED  # 2600
N_ACTIONS = 2          # 0=continue, 1=abort

ALPHA_LR = 0.1         # learning rate
GAMMA = 0.95           # discount factor
EPSILON_START = 0.15    # initial exploration
EPSILON_MIN = 0.02      # minimum exploration
EPSILON_DECAY = 0.998   # decay per episode

ACTION_CONTINUE = 0
ACTION_ABORT = 1


# =============================================================================
# Part 1: State Encoding
# =============================================================================

def encode_state(current_level, regime_at_entry, regime_now, regime_changed):
    """
    Encode (level, regime_entry, regime_now, changed) -> flat index.
    current_level: 0..12 (13 values)
    regime_at_entry: 0..9 (10 values, capped)
    regime_now: 0..9 (10 values, capped)
    regime_changed: 0 or 1
    Total: 13 * 10 * 10 * 2 = 2600
    """
    level = min(current_level, N_LEVELS - 1)
    r_entry = min(regime_at_entry, N_REGIME_VALS - 1)
    r_now = min(regime_now, N_REGIME_VALS - 1)
    changed = 1 if regime_changed else 0

    idx = (level * N_REGIME_VALS * N_REGIME_VALS * N_REGIME_CHANGED +
           r_entry * N_REGIME_VALS * N_REGIME_CHANGED +
           r_now * N_REGIME_CHANGED +
           changed)
    return idx


def decode_state(idx):
    """Inverse of encode_state."""
    changed = idx % N_REGIME_CHANGED
    idx //= N_REGIME_CHANGED
    r_now = idx % N_REGIME_VALS
    idx //= N_REGIME_VALS
    r_entry = idx % N_REGIME_VALS
    idx //= N_REGIME_VALS
    level = idx
    return level, r_entry, r_now, changed


# =============================================================================
# Part 2: Abort Loss Computation
# =============================================================================

def compute_abort_losses():
    """
    Compute the controlled (abort) loss at each level.
    Abort at level L = sum of all losses from levels 0..L-1.
    Each level's loss = hedge_dist * size_at_level * pip_value.

    Uses average ATR for distance computation.
    Returns array of shape (MAX_LEVELS,) with cumulative loss at each level.
    """
    # We need ATR to compute distances. Use a typical value.
    # For generality, normalize to "units of base position loss".
    # Position size at level l: BASE_SIZE * MULTIPLIER^l
    # Loss at level l: hedge_dist_pips * PIP_VALUE * size_l

    sizes = np.array([BASE_SIZE * (MULTIPLIER ** l) for l in range(MAX_LEVELS)])
    # Cumulative loss after losing levels 0..L-1 (abort before level L plays out)
    # At level 0, no prior losses yet (abort = 0 loss)
    # At level 1, lost level 0
    # At level L, lost levels 0..L-1
    cum_size = np.cumsum(sizes)  # proportional to cumulative loss

    return sizes, cum_size


def compute_abort_loss_pnl(level, avg_atr):
    """
    Compute the P&L of aborting at a given level.
    This is the cumulative loss from levels 0..level-1.
    Negative value (it's a loss).
    """
    if level == 0:
        return 0.0  # no loss incurred yet at level 0

    tp_dist = avg_atr * TP_ATR_MULTIPLE
    hedge_dist = tp_dist / RISK_REWARD
    sl_pips = hedge_dist / PIP_SIZE

    total_loss = 0.0
    for l in range(level):
        size = BASE_SIZE * (MULTIPLIER ** l)
        total_loss += sl_pips * PIP_VALUE * size

    return -total_loss


def compute_bust_loss_pnl(avg_atr):
    """Total loss if all MAX_LEVELS are exhausted (bust)."""
    return compute_abort_loss_pnl(MAX_LEVELS, avg_atr)


# =============================================================================
# Part 3: TabularQLearner Class
# =============================================================================

class TabularQLearner:
    """
    Tabular Q-Learning for the abort decision.
    Q-table: N_STATES x N_ACTIONS
    """

    def __init__(self, n_states=N_STATES, n_actions=N_ACTIONS,
                 alpha=ALPHA_LR, gamma=GAMMA,
                 epsilon=EPSILON_START, epsilon_min=EPSILON_MIN,
                 epsilon_decay=EPSILON_DECAY):
        self.n_states = n_states
        self.n_actions = n_actions
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        # Initialize Q-table with small optimistic values
        # Slightly favor "continue" initially (optimistic about winning)
        self.Q = np.zeros((n_states, n_actions))
        self.Q[:, ACTION_CONTINUE] = 0.01  # slight optimism for continue

        # Visit counts for analysis
        self.visit_count = np.zeros((n_states, n_actions), dtype=int)

        # Training history
        self.episode_rewards = []
        self.episode_aborts = []
        self.epsilon_history = []

    def choose_action(self, state, explore=True):
        """Epsilon-greedy action selection."""
        if explore and np.random.random() < self.epsilon:
            return np.random.randint(self.n_actions)
        return np.argmax(self.Q[state])

    def update(self, state, action, reward, next_state=None, done=True):
        """
        Q-learning update:
        Q(s,a) <- Q(s,a) + alpha * [r + gamma * max_a' Q(s',a') - Q(s,a)]

        If done=True (terminal), no next state discount.
        """
        self.visit_count[state, action] += 1

        if done or next_state is None:
            target = reward
        else:
            target = reward + self.gamma * np.max(self.Q[next_state])

        self.Q[state, action] += self.alpha * (target - self.Q[state, action])

    def decay_epsilon(self):
        """Decay exploration rate."""
        self.epsilon = max(self.epsilon_min,
                           self.epsilon * self.epsilon_decay)

    def get_policy(self):
        """Return greedy policy: for each state, the best action."""
        return np.argmax(self.Q, axis=1)

    def get_q_table(self):
        return self.Q.copy()

    def get_state_dict(self):
        return {
            'Q': self.Q.copy(),
            'visit_count': self.visit_count.copy(),
            'epsilon': self.epsilon,
            'episode_rewards': self.episode_rewards.copy(),
            'episode_aborts': self.episode_aborts.copy(),
        }


# =============================================================================
# Part 4: Load Price Data and Build Cycle Episodes
# =============================================================================

def load_price_data():
    """Load EUR-USD 5m candles."""
    print("Loading EUR-USD 5m candles from OANDA...")
    t0 = time.time()
    warmup_candles, candles = get_candles('OANDA', 'EUR-USD', '5m',
        jh.date_to_timestamp('2006-01-02'), jh.date_to_timestamp('2025-12-31'),
        warmup_candles_num=210)
    if warmup_candles is not None and warmup_candles.ndim == 2 and len(warmup_candles) > 0:
        candles = np.concatenate([warmup_candles, candles], axis=0)
    print(f"Total candles: {len(candles):,} ({time.time()-t0:.1f}s)")
    return candles


def compute_indicators(candles):
    ema_fast = ta.ema(candles, period=EMA_FAST, sequential=True)
    ema_slow = ta.ema(candles, period=EMA_SLOW, sequential=True)
    atr_arr = ta.atr(candles, period=ATR_PERIOD, sequential=True)
    adx_arr = ta.adx(candles, period=ATR_PERIOD, sequential=True)
    return ema_fast, ema_slow, atr_arr, adx_arr


def assign_regime(adx_arr, atr_arr, bar_idx):
    """Assign regime from ADX/ATR (fallback when HMM not available)."""
    adx_val = adx_arr[bar_idx] if not np.isnan(adx_arr[bar_idx]) else 25.0
    start = max(0, bar_idx - 1000)
    window = atr_arr[start:bar_idx+1]
    window = window[~np.isnan(window)]
    if len(window) < 50:
        atr_pctile = 50.0
    else:
        atr_pctile = (np.sum(window < atr_arr[bar_idx]) / len(window)) * 100.0

    if adx_val < 20:
        adx_bin = 0
    elif adx_val < 35:
        adx_bin = 1
    else:
        adx_bin = 2

    atr_bin = 0 if atr_pctile < 50 else 1
    regime_map = {
        (0, 0): 0, (0, 1): 1, (1, 0): 2, (1, 1): 3, (2, 0): 4, (2, 1): 4,
    }
    return regime_map.get((adx_bin, atr_bin), 2)


def simulate_level(entry_price, direction, tp_dist, hedge_dist, start_bar,
                   highs, lows):
    """Simulate one level."""
    if direction == 'long':
        tp_price = entry_price + tp_dist
        sl_price = entry_price - hedge_dist
    else:
        tp_price = entry_price - tp_dist
        sl_price = entry_price + hedge_dist

    max_bar = min(start_bar + MAX_BARS_PER_LEVEL, len(highs))
    for j in range(start_bar, max_bar):
        h, l = highs[j], lows[j]
        if direction == 'long':
            if l <= sl_price and h >= tp_price:
                return ('sl', j, sl_price)
            if h >= tp_price:
                return ('tp', j)
            if l <= sl_price:
                return ('sl', j, sl_price)
        else:
            if h >= sl_price and l <= tp_price:
                return ('sl', j, sl_price)
            if l <= tp_price:
                return ('tp', j)
            if h >= sl_price:
                return ('sl', j, sl_price)
    return ('timeout', max_bar - 1)


def build_level_episodes(candles, atr_arr, adx_arr, ema_fast, ema_slow):
    """
    Build cycle episodes with level-by-level outcomes.
    Each episode is a list of level results for one cycle,
    along with regime info.
    """
    closes = candles[:, 2]
    highs = candles[:, 3]
    lows = candles[:, 4]

    min_start = max(ATR_PERIOD + 5, EMA_SLOW + 5)
    signals = []
    for i in range(min_start, len(candles) - MAX_BARS_PER_LEVEL):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if np.isnan(ema_fast[i-1]) or np.isnan(ema_slow[i-1]):
            continue
        if np.isnan(atr_arr[i]) or atr_arr[i] <= 0:
            continue
        if ema_fast[i-1] <= ema_slow[i-1] and ema_fast[i] > ema_slow[i]:
            signals.append((i, 'long'))
        elif ema_fast[i-1] >= ema_slow[i-1] and ema_fast[i] < ema_slow[i]:
            signals.append((i, 'short'))

    print(f"Total signals: {len(signals):,}")

    episodes = []
    next_allowed = 0

    for sig_bar, sig_dir in signals:
        if sig_bar < next_allowed:
            continue

        entry_price = closes[sig_bar]
        direction = sig_dir
        current_bar = sig_bar + 1

        regime_at_entry = assign_regime(adx_arr, atr_arr, sig_bar)
        level_outcomes = []  # list of (level, outcome, pnl, regime_now)
        cum_pnl = 0.0
        valid = True

        for level in range(MAX_LEVELS):
            current_atr = atr_arr[min(current_bar, len(atr_arr)-1)]
            if np.isnan(current_atr) or current_atr <= 0:
                current_atr = atr_arr[sig_bar]
            if np.isnan(current_atr) or current_atr <= 0:
                valid = False
                break

            tp_dist = current_atr * TP_ATR_MULTIPLE
            hedge_dist = tp_dist / RISK_REWARD
            size = BASE_SIZE * (MULTIPLIER ** level)
            tp_pips = tp_dist / PIP_SIZE
            sl_pips = hedge_dist / PIP_SIZE

            # Get current regime (may have changed since entry)
            regime_now = assign_regime(adx_arr, atr_arr,
                                       min(current_bar, len(adx_arr)-1))

            result = simulate_level(entry_price, direction, tp_dist,
                                    hedge_dist, current_bar, highs, lows)

            if result[0] == 'tp':
                profit = tp_pips * PIP_VALUE * size
                cum_pnl += profit
                level_outcomes.append({
                    'level': level,
                    'outcome': 'win',
                    'level_pnl': profit,
                    'cum_pnl': cum_pnl,
                    'regime_now': regime_now,
                    'end_bar': result[1],
                })
                break
            elif result[0] == 'sl':
                loss = sl_pips * PIP_VALUE * size
                cum_pnl -= loss
                level_outcomes.append({
                    'level': level,
                    'outcome': 'loss',
                    'level_pnl': -loss,
                    'cum_pnl': cum_pnl,
                    'regime_now': regime_now,
                    'end_bar': result[1],
                })
                entry_price = result[2]
                direction = 'short' if direction == 'long' else 'long'
                current_bar = result[1] + 1
                if current_bar >= len(highs):
                    valid = False
                    break
            elif result[0] == 'timeout':
                valid = False
                break

        if not valid or len(level_outcomes) == 0:
            continue

        # Determine cycle outcome
        last = level_outcomes[-1]
        if last['outcome'] == 'win':
            cycle_outcome = 'win'
        elif len(level_outcomes) == MAX_LEVELS and last['outcome'] == 'loss':
            cycle_outcome = 'bust'
        else:
            cycle_outcome = 'incomplete'
            continue  # skip incomplete

        episodes.append({
            'entry_bar': sig_bar,
            'regime_at_entry': regime_at_entry,
            'level_outcomes': level_outcomes,
            'cycle_outcome': cycle_outcome,
            'total_pnl': cum_pnl,
            'timestamp': candles[sig_bar, 0],
        })
        next_allowed = last['end_bar'] + 1

    print(f"Built {len(episodes)} complete episodes")
    n_wins = sum(1 for e in episodes if e['cycle_outcome'] == 'win')
    n_busts = sum(1 for e in episodes if e['cycle_outcome'] == 'bust')
    print(f"  Wins: {n_wins}, Busts: {n_busts}")

    return episodes


# =============================================================================
# Part 5: Q-Learning Training on Historical Episodes
# =============================================================================

def train_q_learner(episodes, n_epochs=50, verbose=True):
    """
    Train tabular Q-learner on historical cycle episodes.

    For each episode (cycle):
      - Simulate level by level
      - At each level, Q-learner decides: continue or abort
      - If abort: realize controlled loss (cumulative loss so far), update Q
      - If continue and level wins: realize profit, update Q
      - If continue and level loses: move to next level
      - If all levels exhausted (bust): realize catastrophic loss, update Q
    """
    learner = TabularQLearner()

    for epoch in range(n_epochs):
        np.random.shuffle(episodes)  # randomize episode order each epoch
        epoch_rewards = []
        epoch_aborts = 0
        epoch_continues = 0

        for ep in episodes:
            regime_entry = ep['regime_at_entry']
            levels = ep['level_outcomes']

            for i, lvl in enumerate(levels):
                level = lvl['level']
                regime_now = lvl['regime_now']
                regime_changed = 1 if regime_now != regime_entry else 0

                state = encode_state(level, regime_entry, regime_now,
                                     regime_changed)
                action = learner.choose_action(state)

                if action == ACTION_ABORT:
                    # Abort: take controlled loss (cumulative loss so far)
                    if i > 0:
                        abort_pnl = levels[i-1]['cum_pnl']  # loss up to prev level
                    else:
                        abort_pnl = 0.0  # abort at level 0 = no loss
                    learner.update(state, ACTION_ABORT, abort_pnl, done=True)
                    epoch_rewards.append(abort_pnl)
                    epoch_aborts += 1
                    break  # cycle ends

                else:  # continue
                    epoch_continues += 1

                    if lvl['outcome'] == 'win':
                        # Cycle won at this level
                        reward = lvl['cum_pnl']
                        learner.update(state, ACTION_CONTINUE, reward,
                                       done=True)
                        epoch_rewards.append(reward)
                        break

                    elif lvl['outcome'] == 'loss':
                        if i == len(levels) - 1:
                            # Last level lost = bust
                            reward = lvl['cum_pnl']
                            learner.update(state, ACTION_CONTINUE, reward,
                                           done=True)
                            epoch_rewards.append(reward)
                        else:
                            # Lost this level, next level coming
                            next_lvl = levels[i+1]
                            next_regime = next_lvl['regime_now']
                            next_changed = 1 if next_regime != regime_entry else 0
                            next_state = encode_state(
                                next_lvl['level'], regime_entry,
                                next_regime, next_changed)
                            # Intermediate reward = 0 (no realized P&L yet)
                            learner.update(state, ACTION_CONTINUE, 0,
                                           next_state=next_state, done=False)

        learner.decay_epsilon()

        avg_reward = np.mean(epoch_rewards) if epoch_rewards else 0
        learner.episode_rewards.append(avg_reward)
        learner.episode_aborts.append(epoch_aborts)
        learner.epsilon_history.append(learner.epsilon)

        if verbose and (epoch % 10 == 0 or epoch == n_epochs - 1):
            print(f"  Epoch {epoch:3d}: avg_reward={avg_reward:8.2f}, "
                  f"aborts={epoch_aborts:5d}, continues={epoch_continues:5d}, "
                  f"epsilon={learner.epsilon:.4f}")

    return learner


# =============================================================================
# Part 6: Evaluation Helpers
# =============================================================================

def evaluate_policy(episodes, learner, explore=False, label="Q-Learner"):
    """
    Evaluate a policy on episodes. Returns metrics.
    """
    total_pnl = 0.0
    n_traded = 0
    n_aborted = 0
    n_wins = 0
    n_busts = 0
    abort_levels = []
    cycle_pnls = []

    for ep in episodes:
        regime_entry = ep['regime_at_entry']
        levels = ep['level_outcomes']
        aborted = False

        for i, lvl in enumerate(levels):
            level = lvl['level']
            regime_now = lvl['regime_now']
            regime_changed = 1 if regime_now != regime_entry else 0

            state = encode_state(level, regime_entry, regime_now, regime_changed)
            action = learner.choose_action(state, explore=explore)

            if action == ACTION_ABORT:
                if i > 0:
                    pnl = levels[i-1]['cum_pnl']
                else:
                    pnl = 0.0
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_aborted += 1
                abort_levels.append(level)
                aborted = True
                break

            if lvl['outcome'] == 'win':
                pnl = lvl['cum_pnl']
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_wins += 1
                break

            if lvl['outcome'] == 'loss' and i == len(levels) - 1:
                pnl = lvl['cum_pnl']
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_busts += 1

        n_traded += 1

    bust_rate = n_busts / n_traded if n_traded > 0 else 0
    abort_rate = n_aborted / n_traded if n_traded > 0 else 0

    return {
        'label': label,
        'n_episodes': n_traded,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': n_aborted,
        'bust_rate': bust_rate,
        'abort_rate': abort_rate,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_traded if n_traded > 0 else 0,
        'abort_levels': abort_levels,
        'cycle_pnls': np.array(cycle_pnls),
    }


def evaluate_never_abort(episodes):
    """Baseline: never abort, always continue."""
    total_pnl = 0.0
    n_wins = 0
    n_busts = 0
    cycle_pnls = []

    for ep in episodes:
        pnl = ep['total_pnl']
        total_pnl += pnl
        cycle_pnls.append(pnl)
        if ep['cycle_outcome'] == 'win':
            n_wins += 1
        else:
            n_busts += 1

    n_total = len(episodes)
    return {
        'label': 'Never-Abort',
        'n_episodes': n_total,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': 0,
        'bust_rate': n_busts / n_total if n_total > 0 else 0,
        'abort_rate': 0.0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_total if n_total > 0 else 0,
        'abort_levels': [],
        'cycle_pnls': np.array(cycle_pnls),
    }


def evaluate_threshold_abort(episodes, max_level=6):
    """Simple rule: abort if level >= max_level."""
    total_pnl = 0.0
    n_wins = 0
    n_busts = 0
    n_aborted = 0
    abort_levels = []
    cycle_pnls = []

    for ep in episodes:
        levels = ep['level_outcomes']
        aborted = False

        for i, lvl in enumerate(levels):
            if lvl['level'] >= max_level:
                if i > 0:
                    pnl = levels[i-1]['cum_pnl']
                else:
                    pnl = 0.0
                total_pnl += pnl
                cycle_pnls.append(pnl)
                n_aborted += 1
                abort_levels.append(lvl['level'])
                aborted = True
                break

            if lvl['outcome'] == 'win':
                total_pnl += lvl['cum_pnl']
                cycle_pnls.append(lvl['cum_pnl'])
                n_wins += 1
                break

            if lvl['outcome'] == 'loss' and i == len(levels) - 1:
                total_pnl += lvl['cum_pnl']
                cycle_pnls.append(lvl['cum_pnl'])
                n_busts += 1

    n_total = len(episodes)
    return {
        'label': f'Threshold-Abort (L>={max_level})',
        'n_episodes': n_total,
        'n_wins': n_wins,
        'n_busts': n_busts,
        'n_aborted': n_aborted,
        'bust_rate': n_busts / n_total if n_total > 0 else 0,
        'abort_rate': n_aborted / n_total if n_total > 0 else 0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / n_total if n_total > 0 else 0,
        'abort_levels': abort_levels,
        'cycle_pnls': np.array(cycle_pnls),
    }


# =============================================================================
# Part 7: Break-Even Analysis
# =============================================================================

def break_even_analysis():
    """
    At what P(bust) is abort optimal per level?

    abort_loss(L) = cumulative loss through level L
    bust_loss = cumulative loss through all MAX_LEVELS

    Expected value of continue at level L:
      E[continue] = P(win_remaining) * E[win_pnl] + P(bust_remaining) * bust_loss
    E[abort] = abort_loss(L)

    Abort is optimal when E[abort] > E[continue]:
      abort_loss > P(win) * win_pnl + P(bust) * bust_loss
    """
    sizes, cum_sizes = compute_abort_losses()

    print("\n  Break-Even Analysis: At what P(bust|remaining) is abort optimal?")
    print(f"  {'Level':<8} {'Size':<10} {'CumSize':<12} {'Abort/Bust':<12} "
          f"{'P(bust) threshold':<20}")
    print(f"  {'-'*60}")

    # Normalize: bust_loss proportional to sum of all sizes
    bust_total = cum_sizes[-1]

    for level in range(MAX_LEVELS):
        abort_loss = cum_sizes[level]  # proportional
        remaining_bust = bust_total    # if we don't abort, worst case is full bust

        # Break-even: abort when E[abort] > E[continue]
        # E[continue] = (1-p_bust) * win_reward + p_bust * (-bust_total)
        # E[abort] = -abort_loss
        # -abort_loss > (1-p) * win + p * (-bust_total)
        #
        # Approximate: win_reward ~ 0 (small compared to bust)
        # -abort_loss > p * (-bust_total)
        # p > abort_loss / bust_total

        p_threshold = abort_loss / bust_total if bust_total > 0 else 0
        print(f"  L{level:<7} {sizes[level]:<10.4f} {cum_sizes[level]:<12.4f} "
              f"{abort_loss/bust_total:<12.4f} "
              f"P(bust) > {p_threshold*100:.1f}%")

    return sizes, cum_sizes


# =============================================================================
# Part 8: Walk-Forward Evaluation
# =============================================================================

def walk_forward_q_learning(episodes):
    """Walk-forward: train on expanding window, test on next segment."""
    timestamps = np.array([e['timestamp'] for e in episodes])
    ts_min, ts_max = timestamps.min(), timestamps.max()
    total_dur = ts_max - ts_min
    seg_dur = total_dur / 4

    boundaries = [ts_min + i * seg_dur for i in range(5)]
    segments = []
    for i in range(4):
        seg = [e for e in episodes if boundaries[i] <= e['timestamp'] < boundaries[i+1]]
        segments.append(seg)

    wf_results = []
    for test_idx in range(1, len(segments)):
        train_eps = []
        for j in range(test_idx):
            train_eps.extend(segments[j])
        test_eps = segments[test_idx]

        if len(test_eps) < 5 or len(train_eps) < 10:
            continue

        # Train
        learner = train_q_learner(train_eps, n_epochs=30, verbose=False)

        # Evaluate on test
        q_result = evaluate_policy(test_eps, learner, explore=False,
                                   label=f'Q-Learner Seg{test_idx}')
        never_result = evaluate_never_abort(test_eps)
        thresh_result = evaluate_threshold_abort(test_eps, max_level=6)

        wf_results.append({
            'test_idx': test_idx,
            'n_train': len(train_eps),
            'n_test': len(test_eps),
            'q_learner': q_result,
            'never_abort': never_result,
            'threshold_abort': thresh_result,
        })

    return wf_results


# =============================================================================
# MAIN EXECUTION
# =============================================================================

print("=" * 80)
print("  SCRIPT 19: Tabular Q-Learning for Mid-Cycle Abort Decision")
print("=" * 80)

# ---- Load data and build episodes ------------------------------------------
candles = load_price_data()
ema_fast, ema_slow, atr_arr, adx_arr = compute_indicators(candles)
episodes = build_level_episodes(candles, atr_arr, adx_arr, ema_fast, ema_slow)

# ---- Compute abort losses ---------------------------------------------------
print("\n" + "=" * 80)
print("ABORT LOSS ANALYSIS")
print("=" * 80)
sizes, cum_sizes = break_even_analysis()

avg_atr = np.nanmean(atr_arr[ATR_PERIOD:])
print(f"\n  Average ATR: {avg_atr:.6f}")
print(f"\n  Abort loss in $ at each level (avg ATR):")
for level in range(MAX_LEVELS):
    abort_pnl = compute_abort_loss_pnl(level, avg_atr)
    print(f"    L{level}: ${abort_pnl:,.2f}")
bust_pnl = compute_bust_loss_pnl(avg_atr)
print(f"    Full bust: ${bust_pnl:,.2f}")

# ---- Train Q-Learner -------------------------------------------------------
print("\n" + "=" * 80)
print("Q-LEARNING TRAINING (50 epochs)")
print("=" * 80)
learner = train_q_learner(episodes, n_epochs=50, verbose=True)

# ---- Evaluate ---------------------------------------------------------------
print("\n" + "=" * 80)
print("EVALUATION: Q-Learner vs Never-Abort vs Threshold-Abort")
print("=" * 80)

q_result = evaluate_policy(episodes, learner, explore=False, label='Q-Learner')
never_result = evaluate_never_abort(episodes)

# Test multiple threshold levels
threshold_results = {}
for max_lvl in [4, 5, 6, 7, 8]:
    threshold_results[max_lvl] = evaluate_threshold_abort(episodes, max_level=max_lvl)

# Print comparison
all_results = [never_result, q_result]
all_results.extend(threshold_results.values())

print(f"\n  {'Strategy':<30} {'Episodes':<10} {'Wins':<8} {'Busts':<8} "
      f"{'Aborts':<8} {'Bust%':<8} {'Abort%':<8} {'TotalPnL':<12} {'AvgPnL':<10}")
print(f"  {'-'*102}")
for r in all_results:
    print(f"  {r['label']:<30} {r['n_episodes']:<10} {r['n_wins']:<8} "
          f"{r['n_busts']:<8} {r['n_aborted']:<8} "
          f"{r['bust_rate']*100:<8.2f} {r['abort_rate']*100:<8.2f} "
          f"${r['total_pnl']:<11,.2f} ${r['avg_pnl']:<9,.2f}")

# ---- Policy Analysis: What does Q-learner learn? ----------------------------
print("\n" + "=" * 80)
print("POLICY ANALYSIS: What levels/regimes does Q-learner abort?")
print("=" * 80)

policy = learner.get_policy()

# Analyze abort decisions by level and regime
print("\n  Abort policy by (level, regime_changed):")
print(f"  {'Level':<8} {'Changed=0 (same regime)':<30} {'Changed=1 (diff regime)':<30}")
print(f"  {'-'*68}")

for level in range(MAX_LEVELS):
    abort_same = 0
    total_same = 0
    abort_diff = 0
    total_diff = 0
    for r_entry in range(N_REGIME_VALS):
        for r_now in range(N_REGIME_VALS):
            for changed in [0, 1]:
                state = encode_state(level, r_entry, r_now, changed)
                if learner.visit_count[state].sum() == 0:
                    continue  # unvisited state
                action = policy[state]
                if changed == 0:
                    total_same += 1
                    if action == ACTION_ABORT:
                        abort_same += 1
                else:
                    total_diff += 1
                    if action == ACTION_ABORT:
                        abort_diff += 1

    same_pct = (abort_same / total_same * 100) if total_same > 0 else 0
    diff_pct = (abort_diff / total_diff * 100) if total_diff > 0 else 0
    print(f"  L{level:<7} {abort_same:>3}/{total_same:<5} ({same_pct:5.1f}% abort)"
          f"           {abort_diff:>3}/{total_diff:<5} ({diff_pct:5.1f}% abort)")

# Summarize abort levels from evaluation
if q_result['abort_levels']:
    abort_arr = np.array(q_result['abort_levels'])
    print(f"\n  Abort level distribution (from evaluation):")
    for lvl in sorted(np.unique(abort_arr)):
        count = np.sum(abort_arr == lvl)
        print(f"    Level {lvl}: {count} aborts ({count/len(abort_arr)*100:.1f}%)")

# ---- Walk-Forward Evaluation ------------------------------------------------
print("\n" + "=" * 80)
print("WALK-FORWARD EVALUATION")
print("=" * 80)

wf_results = walk_forward_q_learning(episodes)

print(f"\n  {'Seg':<6} {'Train':<8} {'Test':<8} "
      f"{'Q-Bust%':<10} {'NvA-Bust%':<10} {'Thr-Bust%':<10} "
      f"{'Q-PnL':<12} {'NvA-PnL':<12} {'Thr-PnL':<12}")
print(f"  {'-'*98}")
for r in wf_results:
    q = r['q_learner']
    nva = r['never_abort']
    thr = r['threshold_abort']
    print(f"  {r['test_idx']:<6} {r['n_train']:<8} {r['n_test']:<8} "
          f"{q['bust_rate']*100:<10.2f} {nva['bust_rate']*100:<10.2f} "
          f"{thr['bust_rate']*100:<10.2f} "
          f"${q['total_pnl']:<11,.2f} ${nva['total_pnl']:<11,.2f} "
          f"${thr['total_pnl']:<11,.2f}")

n_q_beats_nva = sum(1 for r in wf_results
                     if r['q_learner']['bust_rate'] < r['never_abort']['bust_rate'])
n_q_beats_thr = sum(1 for r in wf_results
                     if r['q_learner']['bust_rate'] < r['threshold_abort']['bust_rate'])
print(f"\n  Q-learner beats never-abort on bust rate: {n_q_beats_nva}/{len(wf_results)}")
print(f"  Q-learner beats threshold-abort on bust rate: {n_q_beats_thr}/{len(wf_results)}")


# =============================================================================
# CHARTS
# =============================================================================
plt.style.use('seaborn-v0_8-darkgrid')

# ---- Chart 1: Policy Heatmap -----------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(18, 8))

# Heatmap: abort probability by (level, regime_now) when regime_changed=1
ax = axes[0]
abort_prob_changed = np.zeros((MAX_LEVELS, N_REGIME_VALS))
for level in range(MAX_LEVELS):
    for r_now in range(N_REGIME_VALS):
        n_abort = 0
        n_total = 0
        for r_entry in range(N_REGIME_VALS):
            state = encode_state(level, r_entry, r_now, 1)
            if learner.visit_count[state].sum() > 0:
                n_total += 1
                if policy[state] == ACTION_ABORT:
                    n_abort += 1
        abort_prob_changed[level, r_now] = n_abort / n_total if n_total > 0 else np.nan

im = ax.imshow(abort_prob_changed.T, aspect='auto', cmap='RdYlGn_r',
               vmin=0, vmax=1, origin='lower')
ax.set_xlabel('Hedge Level', fontsize=12)
ax.set_ylabel('Current Regime', fontsize=12)
ax.set_title('Abort Probability (Regime Changed)', fontweight='bold')
ax.set_xticks(range(MAX_LEVELS))
ax.set_yticks(range(N_REGIME_VALS))
plt.colorbar(im, ax=ax, label='P(abort)')

# Heatmap: abort probability by (level, regime_now) when regime_changed=0
ax = axes[1]
abort_prob_same = np.zeros((MAX_LEVELS, N_REGIME_VALS))
for level in range(MAX_LEVELS):
    for r_now in range(N_REGIME_VALS):
        n_abort = 0
        n_total = 0
        for r_entry in range(N_REGIME_VALS):
            state = encode_state(level, r_entry, r_now, 0)
            if learner.visit_count[state].sum() > 0:
                n_total += 1
                if policy[state] == ACTION_ABORT:
                    n_abort += 1
        abort_prob_same[level, r_now] = n_abort / n_total if n_total > 0 else np.nan

im = ax.imshow(abort_prob_same.T, aspect='auto', cmap='RdYlGn_r',
               vmin=0, vmax=1, origin='lower')
ax.set_xlabel('Hedge Level', fontsize=12)
ax.set_ylabel('Current Regime', fontsize=12)
ax.set_title('Abort Probability (Same Regime)', fontweight='bold')
ax.set_xticks(range(MAX_LEVELS))
ax.set_yticks(range(N_REGIME_VALS))
plt.colorbar(im, ax=ax, label='P(abort)')

plt.suptitle('Script 19: Q-Learner Abort Policy Heatmap\n'
             f'{len(episodes)} episodes, {MAX_LEVELS} levels, sqrt(2) multiplier',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19_policy_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUTPUT_DIR}/19_policy_heatmap.png")


# ---- Chart 2: Training Curves + Comparison ---------------------------------
fig, axes = plt.subplots(2, 2, figsize=(18, 14))

# Training reward curve
ax = axes[0, 0]
ax.plot(learner.episode_rewards, color='#3498db', linewidth=1.2)
ax.set_xlabel('Epoch')
ax.set_ylabel('Average Reward ($)')
ax.set_title('Q-Learning Training: Average Reward per Epoch', fontweight='bold')
ax.grid(True, alpha=0.3)

# Epsilon decay
ax = axes[0, 1]
ax.plot(learner.epsilon_history, color='#e74c3c', linewidth=1.5)
ax.set_xlabel('Epoch')
ax.set_ylabel('Epsilon')
ax.set_title('Exploration Rate (Epsilon) Decay', fontweight='bold')
ax.grid(True, alpha=0.3)

# Comparison bar chart
ax = axes[1, 0]
strategies = ['Never-Abort', 'Q-Learner']
for max_lvl in sorted(threshold_results.keys()):
    strategies.append(f'Threshold L>={max_lvl}')

bust_rates = [never_result['bust_rate'] * 100, q_result['bust_rate'] * 100]
for max_lvl in sorted(threshold_results.keys()):
    bust_rates.append(threshold_results[max_lvl]['bust_rate'] * 100)

colors = ['#e74c3c', '#2ecc71'] + ['#3498db'] * len(threshold_results)
bars = ax.bar(range(len(strategies)), bust_rates, color=colors,
              edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(strategies)))
ax.set_xticklabels(strategies, rotation=30, ha='right', fontsize=9)
ax.set_ylabel('Bust Rate (%)')
ax.set_title('Bust Rate Comparison', fontweight='bold')
for bar, rate in zip(bars, bust_rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
            f'{rate:.2f}%', ha='center', fontsize=8)
ax.grid(True, alpha=0.3, axis='y')

# P&L comparison
ax = axes[1, 1]
pnls = [never_result['total_pnl'], q_result['total_pnl']]
for max_lvl in sorted(threshold_results.keys()):
    pnls.append(threshold_results[max_lvl]['total_pnl'])

pnl_colors = ['#27ae60' if p > 0 else '#e74c3c' for p in pnls]
bars = ax.bar(range(len(strategies)), pnls, color=pnl_colors,
              edgecolor='black', alpha=0.8)
ax.set_xticks(range(len(strategies)))
ax.set_xticklabels(strategies, rotation=30, ha='right', fontsize=9)
ax.set_ylabel('Total P&L ($)')
ax.set_title('Total P&L Comparison', fontweight='bold')
ax.axhline(y=0, color='black', linewidth=0.5)
ax.grid(True, alpha=0.3, axis='y')

plt.suptitle('Script 19: Q-Learner vs Baselines\n'
             f'{len(episodes)} episodes, {MAX_LEVELS} levels',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/19_comparison.png")


# ---- Chart 3: Equity Curves ------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 7))

# Never-abort equity
cum_pnl_nva = np.cumsum(never_result['cycle_pnls'])
ax.plot(range(len(cum_pnl_nva)), cum_pnl_nva,
        label='Never-Abort', color='#e74c3c', linewidth=1.2, alpha=0.7)

# Q-learner equity
cum_pnl_q = np.cumsum(q_result['cycle_pnls'])
ax.plot(range(len(cum_pnl_q)), cum_pnl_q,
        label='Q-Learner', color='#2ecc71', linewidth=1.5)

# Best threshold
best_thresh_lvl = min(threshold_results.keys(),
                      key=lambda k: threshold_results[k]['bust_rate'])
best_thresh = threshold_results[best_thresh_lvl]
cum_pnl_thr = np.cumsum(best_thresh['cycle_pnls'])
ax.plot(range(len(cum_pnl_thr)), cum_pnl_thr,
        label=f'Threshold L>={best_thresh_lvl}', color='#3498db',
        linewidth=1.2, alpha=0.7, linestyle='--')

ax.axhline(y=0, color='black', linewidth=0.5, linestyle=':')
ax.set_xlabel('Cycle #')
ax.set_ylabel('Cumulative P&L ($)')
ax.set_title('Equity Curves: Abort Strategy Comparison', fontweight='bold',
             fontsize=14)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig(f'{OUTPUT_DIR}/19_equity_curves.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {OUTPUT_DIR}/19_equity_curves.png")


# ---- Chart 4: Walk-Forward Results -----------------------------------------
if len(wf_results) > 0:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    seg_ids = [r['test_idx'] for r in wf_results]
    x = np.arange(len(seg_ids))
    width = 0.25

    ax = axes[0]
    q_busts = [r['q_learner']['bust_rate'] * 100 for r in wf_results]
    nva_busts = [r['never_abort']['bust_rate'] * 100 for r in wf_results]
    thr_busts = [r['threshold_abort']['bust_rate'] * 100 for r in wf_results]

    ax.bar(x - width, nva_busts, width, label='Never-Abort',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x, q_busts, width, label='Q-Learner',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.bar(x + width, thr_busts, width, label='Threshold',
           color='#3498db', alpha=0.7, edgecolor='black')
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('Bust Rate (%)')
    ax.set_title('Walk-Forward: Bust Rate', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    q_pnls = [r['q_learner']['total_pnl'] for r in wf_results]
    nva_pnls = [r['never_abort']['total_pnl'] for r in wf_results]
    thr_pnls = [r['threshold_abort']['total_pnl'] for r in wf_results]

    ax.bar(x - width, nva_pnls, width, label='Never-Abort',
           color='#e74c3c', alpha=0.7, edgecolor='black')
    ax.bar(x, q_pnls, width, label='Q-Learner',
           color='#2ecc71', alpha=0.7, edgecolor='black')
    ax.bar(x + width, thr_pnls, width, label='Threshold',
           color='#3498db', alpha=0.7, edgecolor='black')
    ax.set_xlabel('Test Segment')
    ax.set_ylabel('P&L ($)')
    ax.set_title('Walk-Forward: P&L', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Seg {s}' for s in seg_ids])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    fig.savefig(f'{OUTPUT_DIR}/19_walk_forward.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {OUTPUT_DIR}/19_walk_forward.png")


# =============================================================================
# SAVE OUTPUTS
# =============================================================================

# Save Q-table
np.save(os.path.join(DATA_DIR, 'q_table.npy'), learner.Q)
np.save(os.path.join(DATA_DIR, 'q_visit_count.npy'), learner.visit_count)
print(f"Saved: {DATA_DIR}/q_table.npy")
print(f"Saved: {DATA_DIR}/q_visit_count.npy")

# Save full learner state
learner_state = learner.get_state_dict()
with open(os.path.join(DATA_DIR, 'q_learner_state.pkl'), 'wb') as f:
    pickle.dump(learner_state, f)
print(f"Saved: {DATA_DIR}/q_learner_state.pkl")

# Save comparison metrics
comparison = {
    'never_abort': {k: v for k, v in never_result.items() if k != 'cycle_pnls'},
    'q_learner': {k: v for k, v in q_result.items() if k != 'cycle_pnls'},
    'threshold_results': {
        k: {kk: vv for kk, vv in v.items() if kk != 'cycle_pnls'}
        for k, v in threshold_results.items()
    },
    'walk_forward': wf_results,
}
with open(os.path.join(DATA_DIR, 'abort_comparison.pkl'), 'wb') as f:
    pickle.dump(comparison, f)
print(f"Saved: {DATA_DIR}/abort_comparison.pkl")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

print(f"""
  Surefire Config: {MAX_LEVELS} levels, sqrt(2) multiplier, 0.5% base
  Total Episodes: {len(episodes)}
  State Space: {N_STATES} states (level x regime_entry x regime_now x changed)
  Q-Learning: alpha={ALPHA_LR}, gamma={GAMMA}, {50} epochs

  NEVER-ABORT BASELINE:
    Bust rate: {never_result['bust_rate']*100:.2f}%
    Total P&L: ${never_result['total_pnl']:,.2f}

  Q-LEARNER:
    Bust rate: {q_result['bust_rate']*100:.2f}%
    Abort rate: {q_result['abort_rate']*100:.2f}%
    Total P&L: ${q_result['total_pnl']:,.2f}
    Aborts at levels: {np.unique(q_result['abort_levels']).tolist() if q_result['abort_levels'] else 'none'}

  BEST THRESHOLD ABORT (L>={best_thresh_lvl}):
    Bust rate: {best_thresh['bust_rate']*100:.2f}%
    Abort rate: {best_thresh['abort_rate']*100:.2f}%
    Total P&L: ${best_thresh['total_pnl']:,.2f}

  Walk-forward: Q-learner beats never-abort on bust rate: {n_q_beats_nva}/{len(wf_results)} segments
  Walk-forward: Q-learner beats threshold on bust rate: {n_q_beats_thr}/{len(wf_results)} segments

  KEY INSIGHT: Q-learning discovers the break-even points where
  controlled loss (abort) has higher expected value than continuing.
  It learns regime-specific thresholds (not just level-based rules).
""")

print("FILES SAVED:")
print(f"  {OUTPUT_DIR}/19_policy_heatmap.png")
print(f"  {OUTPUT_DIR}/19_comparison.png")
print(f"  {OUTPUT_DIR}/19_equity_curves.png")
print(f"  {OUTPUT_DIR}/19_walk_forward.png")
print(f"  {DATA_DIR}/q_table.npy")
print(f"  {DATA_DIR}/q_visit_count.npy")
print(f"  {DATA_DIR}/q_learner_state.pkl")
print(f"  {DATA_DIR}/abort_comparison.pkl")
print("=" * 80)
