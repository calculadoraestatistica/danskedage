#!/usr/bin/env python3
"""Annual review runner for the static DanskeDage calendar site.

Use this from cron/Task Scheduler. It regenerates the static files and runs
the local validator, then prints the manual checks that still matter.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def run(command: list[str]) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2026)
    parser.add_argument("--end", type=int, default=2050)
    parser.add_argument("--future-years", type=int, default=15, help="Extend generation at least this many years ahead.")
    args = parser.parse_args()

    today = date.today()
    end = max(args.end, today.year + args.future_years)
    start = min(args.start, today.year)

    print(f"Annual review for DanskeDage calendar ({today.isoformat()})")
    print(f"Generating static pages from {start} to {end}.")
    run([sys.executable, str(TOOLS / "generate_site.py"), "--start", str(start), "--end", str(end)])
    run([sys.executable, str(TOOLS / "validate_site.py"), "--start", str(start), "--end", str(end)])

    print("\nManual review checklist before publishing:")
    print("1. Public holidays: confirm no Danish public-holiday law changed since the last update.")
    print("   - Store bededag is treated as historical/non-official after 2024.")
    print("   - If the law changes, update all_marks() in tools/generate_site.py.")
    print("2. School holidays: update data/school-holidays.json from each municipality source.")
    print("   - Add the next school year as municipalities publish it.")
    print("   - Update the top-level 'updated' field.")
    print("   - Keep partial data only when the page clearly links to the source.")
    print("3. Spot-check generated pages:")
    print("   - index.html should be the current year.")
    print("   - sitemap.xml should include every generated HTML page.")
    print("   - beregn-arbejdsdage.html, laeg-arbejdsdage-til.html and ugenummer.html should calculate in the browser.")
    print("4. Monetization/deployment:")
    print("   - Check ads.txt and the AdSense publisher id.")
    print("   - Check CNAME before publishing if the final domain changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
