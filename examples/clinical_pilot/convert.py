"""Regenerate benchmark.json from the v0.5 sources (thin shim over the native loader).

As of infereval v0.17.0 the v0.5 schema is supported natively: the framework's
``infereval bearers-import`` command (and :func:`infereval.cli.bearers_cmd.build_benchmark`)
map the bearers file + items document straight onto the ``Benchmark`` model, with
every v0.5 concept in a first-class field — no ``construction_metadata.source``
smuggling. This script is a convenience wrapper that regenerates the checked-in
``benchmark.json`` from the canonical sources.

Equivalent to::

    infereval bearers-import bearers_v0.5.txt benchmark_v0.5.json -o benchmark.json

Usage::

    python examples/clinical_pilot/convert.py            # writes benchmark.json
    python examples/clinical_pilot/convert.py --check    # validate only, no write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
BEARERS_V05 = HERE / "bearers_v0.5.txt"
BENCHMARK_V05 = HERE / "benchmark_v0.5.json"
OUTPUT = HERE / "benchmark.json"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="Validate only; don't write")
    p.add_argument("--out", type=Path, default=OUTPUT, help=f"Output path (default: {OUTPUT.name})")
    args = p.parse_args()

    try:
        from infereval.bearers import load_bearers_file
        from infereval.cli.bearers_cmd import build_benchmark
    except ImportError:
        print("ERROR: infereval must be installed to regenerate this benchmark.", file=sys.stderr)
        return 1

    doc = load_bearers_file(BEARERS_V05)
    items_doc = json.loads(BENCHMARK_V05.read_text(encoding="utf-8"))
    bench = build_benchmark(doc, items_doc)
    print(
        f"Built benchmark id={bench.id!r}: {len(bench.bearers)} bearers, {bench.n} items, "
        f"{len(bench.ordinal_families)} ordinal families."
    )

    if args.check:
        print("Check passed; no file written.")
        return 0

    bench.dump(args.out)
    print(f"Wrote {args.out.name} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
