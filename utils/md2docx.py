#!/usr/bin/env python3
"""Convert Markdown file(s) to DOCX using pypandoc.

Usage:
  Single file:   python md2docx.py paper.md
  Bind & convert: python md2docx.py --bind dist/ -o example.docx
  Bind only (md): python md2docx.py --bind dist/ --md-only -o example.md
"""

import argparse
import sys
from pathlib import Path

try:
    import pypandoc
except ImportError:
    print("pypandoc not installed. Install with: pip install pypandoc")
    sys.exit(1)

# Default section order for --bind
SECTION_ORDER = [
    "0_title_abstract",
    "1_introduction",
    "2_related_work",
    "3_system_architecture",
    "4_training_methodology",
    "5_experimental_setup",
    "6_results",
    "7_discussion",
    "8_conclusion",
    "ack_decl_data_useAI",
    "references",
    "appendix",
]


def bind_sections(dist_dir: Path) -> str:
    """Concatenate section .md files from a directory in order."""
    parts = []
    for name in SECTION_ORDER:
        f = dist_dir / f"{name}.md"
        if not f.exists():
            print(f"  Warning: skipping missing section {f.name}")
            continue
        parts.append(f.read_text())
        print(f"  + {f.name} ({len(f.read_text().splitlines())} lines)")
    return "\n\n".join(parts)


def convert(md_path: str, output_path: str | None = None):
    md = Path(md_path)
    if not md.exists():
        print(f"File not found: {md}")
        sys.exit(1)

    out = Path(output_path) if output_path else md.with_suffix(".docx")
    pypandoc.convert_file(
        str(md), "docx", outputfile=str(out),
        extra_args=[f"--resource-path={md.parent.resolve()}"],
    )
    print(f"Created: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bind & convert Markdown to DOCX")
    parser.add_argument("input", nargs="?", help="Path to .md file (single-file mode)")
    parser.add_argument("--bind", metavar="DIR", help="Bind all sections from DIR in order, then convert")
    parser.add_argument("--md-only", action="store_true", help="With --bind: output combined .md only, no docx")
    parser.add_argument("-o", "--output", help="Output path (default: input.docx or DIR/submit.docx)")
    args = parser.parse_args()

    if args.bind:
        dist = Path(args.bind)
        if not dist.is_dir():
            print(f"Not a directory: {dist}")
            sys.exit(1)

        combined = bind_sections(dist)
        md_out = Path(args.output) if args.output else dist / "submit_1_1.md"
        if not md_out.suffix:
            md_out = md_out.with_suffix(".md" if args.md_only else ".docx")
        if not args.md_only and md_out.suffix == ".docx":
            md_out = md_out.with_suffix(".md")

        md_out.write_text(combined)
        print(f"Bound: {md_out} ({len(combined.splitlines())} lines)")

        if not args.md_only:
            docx_out = Path(args.output) if args.output and args.output.endswith(".docx") else md_out.with_suffix(".docx")
            pypandoc.convert_file(
                str(md_out), "docx", outputfile=str(docx_out),
                extra_args=[f"--resource-path={dist.resolve()}"],
            )
            print(f"Created: {docx_out}")

    elif args.input:
        convert(args.input, args.output)
    else:
        parser.print_help()
