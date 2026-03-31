import math


class WelfordNormalizer:
    """Online mean/variance tracker using Welford's algorithm. O(1) per update."""

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float) -> float:
        """Add observation, return z-score (0.0 during warmup)."""
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

        if self.n < 2:
            return 0.0
        var = self.m2 / (self.n - 1)
        std = math.sqrt(var) if var > 0 else 1e-8
        return (x - self.mean) / std

    def seed(self, mean: float, std: float, n: int = 10000):
        """Seed with pre-computed statistics from phase2 research.

        This allows the normalizer to produce accurate z-scores from
        the first observation, skipping the warmup period entirely.
        Welford state is reconstructed: m2 = std^2 * (n - 1).
        """
        self.n = n
        self.mean = mean
        self.m2 = (std ** 2) * (n - 1)

    def state_dict(self) -> dict:
        return {'n': self.n, 'mean': self.mean, 'm2': self.m2}

    def load_state_dict(self, d: dict):
        self.n = d['n']
        self.mean = d['mean']
        self.m2 = d['m2']


# Feature definitions: (key, weight, inverted)
# Inverted means high raw value = low danger (e.g. strong ADX = safe)
FEATURES = [
    ('D1_range_atr',  0.30, True),   # low range/ATR = choppy = danger
    ('5m_chop',       0.15, False),  # high choppiness = danger
    ('15m_chop',      0.15, False),
    ('D1_chop',       0.10, False),
    ('5m_adx',        0.10, True),   # low ADX = no trend = danger
    ('5m_hurst',      0.10, True),   # close to 0.5 = random walk = danger
    ('1H_atr_ratio',  0.10, False),  # high ATR ratio = volatile = danger
]


class DangerScorer:
    """
    Real-time market danger scoring using 7 weighted features.

    - Online Welford normalization (no pre-training needed)
    - Can be seeded with pre-computed stats from phase2 research
    - Sigmoid output → [0, 1]
    - Warmup period returns 0.5 (neutral) unless seeded

    Usage:
        scorer = DangerScorer()
        score = scorer.update(features_dict)  # returns float [0, 1]

    With pre-trained params (skips warmup):
        scorer = DangerScorer({'pretrained_params': params_dict})
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.warmup = config.get('warmup', 50)
        self._normalizers = {f[0]: WelfordNormalizer() for f in FEATURES}
        self._current_score = 0.5
        self._update_count = 0
        self._seeded = False

        # Seed normalizers with pre-computed statistics from phase2 research.
        # Format: {'means': {feature: mean}, 'stds': {feature: std}, 'n': count}
        pretrained = config.get('pretrained_params')
        if pretrained:
            self._seed_normalizers(pretrained)

    def _seed_normalizers(self, params: dict):
        """Initialize normalizers from pre-computed statistics.

        Accepts the format from phase2's danger_scorer_params.json:
        {
            'n': 60370,
            'means': {'5m_chop': 50.68, ...},
            'stds': {'5m_chop': 9.39, ...}
        }
        """
        means = params.get('means', {})
        stds = params.get('stds', {})
        n = params.get('n', 10000)

        seeded_count = 0
        for key in self._normalizers:
            if key in means and key in stds:
                self._normalizers[key].seed(means[key], stds[key], n)
                seeded_count += 1

        if seeded_count > 0:
            self._seeded = True
            # Seeded normalizers are already warmed up
            self._update_count = self.warmup

    @property
    def current_score(self) -> float:
        return self._current_score

    def update(self, features: dict) -> float:
        """
        Feed a dict of feature values, get back danger score [0, 1].

        features: dict with keys matching FEATURES (e.g. '5m_chop', 'D1_range_atr').
                  Missing keys are skipped (their contribution is 0).
        """
        self._update_count += 1

        if not self._seeded and self._update_count < self.warmup:
            # Still warming up normalizers — feed data but return neutral
            for key, _, _ in FEATURES:
                if key in features:
                    self._normalizers[key].update(features[key])
            self._current_score = 0.5
            return 0.5

        weighted_sum = 0.0
        total_weight = 0.0

        for key, weight, inverted in FEATURES:
            if key not in features:
                continue
            z = self._normalizers[key].update(features[key])
            if inverted:
                z = -z  # high raw value = low danger → negate
            weighted_sum += weight * z
            total_weight += weight

        if total_weight > 0:
            weighted_sum /= total_weight  # normalize by active weights

        # Sigmoid: maps (-inf, inf) → (0, 1)
        self._current_score = 1.0 / (1.0 + math.exp(-weighted_sum))
        return self._current_score

    @property
    def stats(self) -> dict:
        feature_stats = {}
        for key, weight, inverted in FEATURES:
            norm = self._normalizers[key]
            std = math.sqrt(norm.m2 / (norm.n - 1)) if norm.n > 1 and norm.m2 > 0 else 0
            feature_stats[key] = {
                'weight': weight,
                'inverted': inverted,
                'observations': norm.n,
                'mean': round(norm.mean, 6),
                'std': round(std, 6),
            }
        return {
            'current_score': round(self._current_score, 4),
            'update_count': self._update_count,
            'warmed_up': self._update_count >= self.warmup,
            'seeded': self._seeded,
            'warmup_target': self.warmup,
            'features': feature_stats,
        }

    def state_dict(self) -> dict:
        return {
            'update_count': self._update_count,
            'current_score': self._current_score,
            'seeded': self._seeded,
            'normalizers': {
                k: v.state_dict() for k, v in self._normalizers.items()
            },
        }

    def load_state_dict(self, d: dict):
        self._update_count = d['update_count']
        self._current_score = d['current_score']
        self._seeded = d.get('seeded', False)
        for k, v in d.get('normalizers', {}).items():
            if k in self._normalizers:
                self._normalizers[k].load_state_dict(v)
