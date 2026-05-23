#!/usr/bin/env python3
"""Compile normalized factor_spec JSONL into deterministic factor code."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantlab.signal.factor_spec import compile_specs_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile factor specs to compute_factor Python files")
    parser.add_argument("--input", required=True, help="Normalized factor_spec JSONL")
    parser.add_argument("--output-dir", required=True, help="Output factor code directory")
    parser.add_argument("--manifest", default=None, help="Optional compiler manifest CSV")
    args = parser.parse_args()

    rows = compile_specs_file(args.input, args.output_dir, args.manifest)
    print(f"compiled: {len(rows)} -> {args.output_dir}")
    if args.manifest:
        print(f"manifest: {args.manifest}")


if __name__ == "__main__":
    main()
