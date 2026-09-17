"""Generate deterministic CSV tables for storage and index benchmarks."""

import argparse
import csv
import random
from pathlib import Path


def generate(size, seed, output_dir):
    rng = random.Random(seed + size)
    ids = list(range(size))
    rng.shuffle(ids)

    with (output_dir / f"records_{size}.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("id", "category", "value"))
        for record_id in ids:
            writer.writerow((record_id, rng.randrange(100), rng.randrange(1, 1_000_001)))

    with (output_dir / f"details_{size}.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("id", "record_id", "value"))
        detail_ids = list(range(2 * size))
        rng.shuffle(detail_ids)
        for detail_id in detail_ids:
            writer.writerow((detail_id, detail_id // 2, rng.randrange(1, 1_000_001)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "generated")
    args = parser.parse_args()
    if any(size <= 0 for size in args.sizes):
        parser.error("all sizes must be positive integers")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for size in args.sizes:
        generate(size, args.seed, args.output_dir)
        print(f"Generated {size} records and {2 * size} details in {args.output_dir}")


if __name__ == "__main__":
    main()
