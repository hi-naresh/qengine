#!/usr/bin/env python3
"""Convert a Markdown file to DOCX using pypandoc."""

import argparse
import sys
from pathlib import Path

try:
    import pypandoc
except ImportError:
    print("pypandoc not installed. Install with: pip install pypandoc")
    sys.exit(1)


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
    parser = argparse.ArgumentParser(description="Convert Markdown to DOCX")
    parser.add_argument("input", help="Path to .md file")
    parser.add_argument("-o", "--output", help="Output .docx path (default: same name, .docx extension)")
    args = parser.parse_args()
    convert(args.input, args.output)
