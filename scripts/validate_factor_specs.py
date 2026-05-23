#!/usr/bin/env python3
"""Validate and normalize QuantLab factor_spec JSONL."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantlab.signal.factor_spec import DEFAULT_SCHEMA, validate_specs_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate factor_spec JSONL")
    parser.add_argument("--input", required=True, help="Raw factor_spec JSONL")
    parser.add_argument("--output", required=True, help="Normalized accepted JSONL")
    parser.add_argument("--rejected", required=True, help="Rejected CSV")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Schema YAML")
    args = parser.parse_args()

    result = validate_specs_file(args.input, args.output, args.rejected, args.schema)
    print(f"accepted: {len(result.accepted)} -> {args.output}")
    print(f"rejected: {len(result.rejected)} -> {args.rejected}")


if __name__ == "__main__":
    main()
