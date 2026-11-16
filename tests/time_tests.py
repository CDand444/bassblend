#!/usr/bin/env python3
"""Measure how long each offline test takes to run."""

import sys
import subprocess
import argparse
from pathlib import Path
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', help='Run only these comma-separated test names (without .py)')
    parser.add_argument('--top', type=int, help='Print only top N slowest rows')
    args = parser.parse_args()

    # Find repo root
    repo_root = Path(__file__).resolve().parent.parent
    test_dir = repo_root / 'tests'

    test_files = sorted(test_dir.glob('test_*.py'))

    unmatched_names = False

    if args.only:
        only_names = set(args.only.split(','))
        found_names = set()
        matched_files = []
        for test_file in test_files:
            if test_file.stem in only_names or test_file.name in only_names:
                matched_files.append(test_file)
                found_names.add(test_file.stem)
        # Check for unmatched names
        unmatched = only_names - found_names
        for name in unmatched:
            print(f"no such test file: {name}", file=sys.stderr)
            unmatched_names = True
        if not matched_files:
            return 1
        test_files = matched_files

    if not test_files:
        print("No matching test files found.")
        return 1

    results = []
    total_time = 0.0
    ok_count = 0
    fail_count = 0
    timeout_count = 0

    for test_file in test_files:
        # Measure wall-clock time
        start_time = time.perf_counter()

        try:
            result = subprocess.run(
                [sys.executable, str(test_file)],
                cwd=str(repo_root),
                timeout=300,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            end_time = time.perf_counter()
            elapsed = round(end_time - start_time, 1)

            if result.returncode == 0:
                output_lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
                last_line = output_lines[-1] if output_lines else ""
                if "passed" in last_line:
                    status = "ok"
                    ok_count += 1
                else:
                    status = "FAIL"
                    fail_count += 1
            else:
                status = "FAIL"
                fail_count += 1

        except subprocess.TimeoutExpired:
            end_time = time.perf_counter()
            elapsed = round(end_time - start_time, 1)
            status = "TIMEOUT"
            timeout_count += 1

        results.append((test_file.name, elapsed, status))
        total_time += (end_time - start_time)

    # Sort by time (descending)
    results.sort(key=lambda x: x[1], reverse=True)

    # Print table
    print(f"{'File':<20} {'Seconds':<10} {'Result'}")
    print("-" * 40)

    for file_name, seconds, status in results[:args.top] if args.top else results:
        print(f"{file_name:<20} {seconds:<10} {status}")

    # Print total line
    print("-" * 40)
    print(f"Total: {total_time:.1f}s ({ok_count} ok, {fail_count} FAIL, {timeout_count} TIMEOUT)")

    # Exit code 1 if any file is not ok, or if any names were unmatched
    return 1 if fail_count > 0 or timeout_count > 0 or unmatched_names else 0

if __name__ == "__main__":
    sys.exit(main())