"""Print timings and counts only. Never print or save private review content."""

import argparse
from time import perf_counter
from unittest.mock import patch

import engine as E


def benchmark(path):
    data = E.load_reviews(path)
    with patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")):
        started = perf_counter()
        result = E.analyze_offline(data)
        seconds = perf_counter() - started
    print(f"Reviews: {len(data)} | Locations: {data['location'].nunique()} | "
          f"Seconds: {seconds:.3f} | Needs review: {int(result['needs_review'].sum())}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", help="CSV paths. File content is not printed.")
    args = parser.parse_args()
    for path in args.csv:
        benchmark(path)
