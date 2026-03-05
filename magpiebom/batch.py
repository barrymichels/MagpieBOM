# magpiebom/batch.py
import sys

from magpiebom.cli import run_pipeline
from magpiebom.report import generate_report


def _read_part_numbers(args) -> list[str]:
    """Read part numbers from args, file, or stdin."""
    parts = []

    if args.parts:
        for item in args.parts:
            # If it looks like a file, read it
            try:
                with open(item) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts.append(line)
            except (OSError, UnicodeDecodeError):
                # Not a file — treat as a part number
                parts.append(item)
    elif not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith("#"):
                parts.append(line)

    return parts


def batch_main(args):
    part_numbers = _read_part_numbers(args)

    if not part_numbers:
        print("No part numbers provided. Pass them as arguments, in a file, or via stdin.", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(part_numbers)} part(s)...", file=sys.stderr)
    results = []

    for i, pn in enumerate(part_numbers, 1):
        print(f"\n[{i}/{len(part_numbers)}] {pn}", file=sys.stderr)
        result = run_pipeline(
            part_number=pn,
            output_dir=args.output_dir,
            no_open=True,
            verbose=args.verbose,
        )
        results.append(result)
        status = "found" if result["image_path"] else "not found"
        print(f"  Result: {status}", file=sys.stderr)

    report_path = generate_report(results, args.output_dir)
    found = sum(1 for r in results if r["image_path"])
    print(f"\nDone: {found}/{len(results)} parts found", file=sys.stderr)
    print(f"Report: {report_path}", file=sys.stderr)
