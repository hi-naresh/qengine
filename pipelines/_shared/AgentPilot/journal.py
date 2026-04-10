"""Structured trading journal — persistent memory across LLM consultations."""
from __future__ import annotations
import json
from typing import Optional


class Journal:
    """
    Maintains a rolling window of LLM decisions, market snapshots,
    thesis, and lessons learned. Persisted as JSON.
    """

    def __init__(self, config: dict):
        cfg = config.get('journal', {})
        self._max_entries = cfg.get('max_entries', 50)
        self._include_in_prompt = cfg.get('include_in_prompt', 10)

        self.entries: list[dict] = []
        self.thesis: str = ''
        self.lessons: list[str] = []
        self.regime_assessment: str = 'unknown'
        self.consecutive_wins: int = 0
        self.consecutive_losses: int = 0
        self.total_consultations: int = 0

    def record(self, bar_index: int, trigger: str, decision_dict: dict,
               market_snapshot: dict, reasoning: str = '') -> None:
        """Record a new consultation entry."""
        self.total_consultations += 1

        entry = {
            'bar_index': bar_index,
            'trigger': trigger,
            'decision': decision_dict,
            'market_snapshot': market_snapshot,
            'reasoning': reasoning,
            'outcome': None,  # filled on cycle_end
        }
        self.entries.append(entry)

        # Update thesis from decision reasoning
        if reasoning:
            self.thesis = reasoning

        # Trim to max size
        if len(self.entries) > self._max_entries:
            self.entries = self.entries[-self._max_entries:]

    def record_outcome(self, pnl: float) -> None:
        """Attach outcome to the most recent entry and update streaks."""
        # Find last entry without outcome
        for entry in reversed(self.entries):
            if entry['outcome'] is None:
                entry['outcome'] = {'pnl': round(pnl, 4), 'win': pnl > 0}
                break

        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

    def add_lesson(self, lesson: str) -> None:
        """Add a lesson learned (from LLM's post-mortem)."""
        self.lessons.append(lesson)
        # Keep last 20 lessons
        if len(self.lessons) > 20:
            self.lessons = self.lessons[-20:]

    def get_prompt_context(self) -> str:
        """
        Format journal for inclusion in LLM prompt.
        Returns a concise summary of recent history.
        """
        lines = []

        if self.thesis:
            lines.append(f'Current thesis: {self.thesis}')
        if self.regime_assessment != 'unknown':
            lines.append(f'Regime assessment: {self.regime_assessment}')

        lines.append(f'Streak: {self.consecutive_wins}W / {self.consecutive_losses}L')

        if self.lessons:
            lines.append('Lessons learned:')
            for lesson in self.lessons[-5:]:
                lines.append(f'  - {lesson}')

        # Recent decisions
        recent = self.entries[-self._include_in_prompt:]
        if recent:
            lines.append(f'\nRecent decisions ({len(recent)} of {len(self.entries)} total):')
            for entry in recent:
                dec = entry.get('decision', {})
                snap = entry.get('market_snapshot', {})
                outcome = entry.get('outcome')
                outcome_str = ''
                if outcome:
                    outcome_str = f' -> {"WIN" if outcome["win"] else "LOSS"} {outcome["pnl"]}'

                lines.append(
                    f'  Bar {entry["bar_index"]}: {dec.get("signal", "?")} '
                    f'(conf={dec.get("confidence", "?")}) '
                    f'trigger={entry["trigger"]} '
                    f'price={snap.get("price", "?")} '
                    f'danger={snap.get("danger", "?")}'
                    f'{outcome_str}'
                )
                if entry.get('reasoning'):
                    lines.append(f'    Reasoning: {entry["reasoning"][:120]}')

        return '\n'.join(lines)

    # ── Persistence ──

    def state_dict(self) -> dict:
        return {
            'entries': self.entries,
            'thesis': self.thesis,
            'lessons': self.lessons,
            'regime_assessment': self.regime_assessment,
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'total_consultations': self.total_consultations,
        }

    def load_state_dict(self, d: dict) -> None:
        self.entries = d.get('entries', [])
        self.thesis = d.get('thesis', '')
        self.lessons = d.get('lessons', [])
        self.regime_assessment = d.get('regime_assessment', 'unknown')
        self.consecutive_wins = d.get('consecutive_wins', 0)
        self.consecutive_losses = d.get('consecutive_losses', 0)
        self.total_consultations = d.get('total_consultations', 0)
