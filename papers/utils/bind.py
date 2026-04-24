"""
bind.py — Concatenates all dist/ section files into a single submission document.

Usage (from repo root):
    python papers/utils/bind.py                     # writes papers/drafts/submit_1_1.md
    python papers/utils/bind.py --out my_output.md  # custom output path
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Ordered list of sections to include in the final document.
# version_log.md is intentionally excluded (internal tracking only).
SECTION_ORDER = [
    "0_title_abstract.md",
    "1_introduction.md",
    "2_related_work.md",
    "3_system_architecture.md",
    "4_training_methodology.md",
    "5_experimental_setup.md",
    "6_results.md",
    "7_discussion.md",
    "8_conclusion.md",
    "ack_decl_data_useAI.md",
    "references.md",
    "appendix.md",
]

_DIST_DIR = Path(__file__).parent.parent / "drafts" / "dist"
_DEFAULT_OUT = Path(__file__).parent.parent / "drafts" / "submit_1_1.md"


def bind(out_path: Path = _DEFAULT_OUT) -> None:
    parts: list[str] = []

    for filename in SECTION_ORDER:
        src = _DIST_DIR / filename
        if not src.exists():
            print(f"[bind] WARNING: {src} not found — skipping")
            continue
        content = src.read_text(encoding="utf-8").rstrip("\n")
        parts.append(content)
        print(f"[bind] included {filename}")

    combined = "\n\n---\n\n".join(parts) + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(combined, encoding="utf-8")
    print(f"\n[bind] wrote {out_path}  ({len(combined):,} chars, {len(parts)} sections)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bind dist/ sections into submit_1_1.md")
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Output path (default: {_DEFAULT_OUT})",
    )
    args = parser.parse_args()
    bind(args.out)
