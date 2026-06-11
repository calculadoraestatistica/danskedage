#!/usr/bin/env python3
"""Validate the generated static DanskeDage calendar site.

This script intentionally uses only the Python standard library so it can run
from a simple cron job without installing dependencies.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "https://danskedage.dk"
YEAR_PAGE_PREFIXES = [
    "kalender",
    "helligdage",
    "arbejdsdage",
    "paaske",
    "pinse",
    "kristi-himmelfartsdag",
    "bedste-feriedage",
]
STATIC_HTML = {
    "index.html",
    "beregn-arbejdsdage.html",
    "laeg-arbejdsdage-til.html",
    "ugenummer.html",
    "skoleferier.html",
    "om.html",
    "kontakt.html",
    "privatlivspolitik.html",
    "vilkar.html",
    "stot.html",
    # Extra interactive tools.
    "vaerktoejer.html",
    "aldersberegner.html",
    "dato-difference.html",
    "nedtaelling.html",
    "naeste-helligdag.html",
    "ugedag.html",
    "dato-plus-dage.html",
    "traek-arbejdsdage-fra.html",
    "dato-fra-uge.html",
}
KNOWN_DATES = {
    2026: {
        "Påskedag": "2026-04-05",
        "Kristi himmelfartsdag": "2026-05-14",
        "2. pinsedag": "2026-05-25",
    },
    2027: {
        "Påskedag": "2027-03-28",
        "Kristi himmelfartsdag": "2027-05-06",
        "2. pinsedag": "2027-05-17",
    },
    2028: {
        "Påskedag": "2028-04-16",
        "Kristi himmelfartsdag": "2028-05-25",
        "2. pinsedag": "2028-06-05",
    },
}


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value for name, value in attrs if value}
        for attr in ("href", "src"):
            if attr in attr_map:
                self.links.append((attr, attr_map[attr] or ""))
        if "srcset" in attr_map:
            for item in (attr_map["srcset"] or "").split(","):
                candidate = item.strip().split(" ", 1)[0]
                if candidate:
                    self.links.append(("srcset", candidate))


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def local_target(raw_url: str, source: Path) -> Path | None:
    value = html.unescape(raw_url).strip()
    if not value or value.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None

    raw_path = unquote(parsed.path)
    if not raw_path:
        return None
    candidate = ROOT / raw_path.lstrip("/") if raw_path.startswith("/") else source.parent / raw_path
    if raw_path.endswith("/") or candidate.name == "":
        candidate = candidate / "index.html"
    return candidate.resolve()


def expected_html(start: int, end: int) -> set[str]:
    expected = set(STATIC_HTML)
    school_file = ROOT / "data" / "school-holidays.json"
    if school_file.exists():
        school_data = read_json(school_file)
        for municipality in school_data.get("municipalities", []):  # type: ignore[union-attr]
            expected.add(f"skoleferier-{municipality['slug']}.html")
    for year in range(start, end + 1):
        for prefix in YEAR_PAGE_PREFIXES:
            expected.add(f"{prefix}-{year}.html")
    return expected


def validate_links(errors: list[str]) -> None:
    root_resolved = ROOT.resolve()
    for page in sorted(ROOT.glob("*.html")):
        parser = LinkCollector()
        parser.feed(page.read_text(encoding="utf-8"))
        for attr, target in parser.links:
            resolved = local_target(target, page)
            if resolved is None:
                continue
            if not str(resolved).startswith(str(root_resolved)):
                errors.append(f"{page.name}: {attr} escapes site root -> {target}")
            elif not resolved.exists():
                errors.append(f"{page.name}: broken local {attr} -> {target}")


def validate_expected_files(start: int, end: int, errors: list[str], warnings: list[str]) -> None:
    expected = expected_html(start, end)
    actual = {path.name for path in ROOT.glob("*.html")}
    for name in sorted(expected - actual):
        errors.append(f"missing expected HTML file: {name}")
    for name in sorted(actual - expected):
        warnings.append(f"unexpected root HTML file: {name}")

    required_assets = [
        "css/style.css",
        "js/calendar-tools.js",
        "favicon-48.png",
        "favicon-192.png",
        "apple-touch-icon.png",
        "site.webmanifest",
        "ads.txt",
        "robots.txt",
        "CNAME",
        "sitemap.xml",
    ]
    for asset in required_assets:
        if not (ROOT / asset).exists():
            errors.append(f"missing asset: {asset}")


def validate_sitemap(start: int, end: int, errors: list[str]) -> None:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        errors.append("missing sitemap.xml")
        return
    tree = ET.parse(sitemap)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [node.text or "" for node in tree.findall(".//sm:loc", ns)]
    expected_urls = {DOMAIN + "/" if name == "index.html" else f"{DOMAIN}/{name}" for name in expected_html(start, end)}
    for url in sorted(expected_urls - set(locs)):
        errors.append(f"sitemap missing URL: {url}")
    for url in locs:
        if not url.startswith(DOMAIN):
            errors.append(f"sitemap URL outside domain: {url}")
            continue
        rel = url.removeprefix(DOMAIN).lstrip("/") or "index.html"
        if not (ROOT / rel).exists():
            errors.append(f"sitemap URL has no local file: {url}")


def validate_calendar_json(start: int, end: int, errors: list[str]) -> None:
    for year in range(start, end + 1):
        path = ROOT / "data" / f"calendar-{year}.json"
        if not path.exists():
            errors.append(f"missing calendar JSON: {path.relative_to(ROOT)}")
            continue
        data = read_json(path)
        if data.get("year") != year:  # type: ignore[union-attr]
            errors.append(f"{path.name}: wrong year value")
            continue

        stats = data.get("stats", {})  # type: ignore[union-attr]
        holidays = data.get("holidays", [])  # type: ignore[union-attr]
        official = set()
        by_name = {}
        for item in holidays:
            day = date.fromisoformat(item["date"])
            by_name[item["name"]] = item["date"]
            if item.get("official"):
                official.add(day)

        workdays = sum(
            1
            for month in range(1, 13)
            for day in range(1, 32)
            if _valid_date(year, month, day)
            and date(year, month, day).weekday() < 5
            and date(year, month, day) not in official
        )
        if stats.get("workdays") != workdays:
            errors.append(f"{path.name}: workdays mismatch, got {stats.get('workdays')} expected {workdays}")

        store_bededag = next((item for item in holidays if item["name"] == "Store bededag (historisk)"), None)
        if store_bededag and store_bededag.get("official"):
            errors.append(f"{path.name}: Store bededag should not be official after 2024")

        for name, expected_date in KNOWN_DATES.get(year, {}).items():
            if by_name.get(name) != expected_date:
                errors.append(f"{path.name}: {name} is {by_name.get(name)}, expected {expected_date}")


def _valid_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def validate_school_data(errors: list[str], warnings: list[str]) -> None:
    path = ROOT / "data" / "school-holidays.json"
    if not path.exists():
        errors.append("missing data/school-holidays.json")
        return
    data = read_json(path)
    municipalities = data.get("municipalities", [])  # type: ignore[union-attr]
    if len(municipalities) < 8:
        warnings.append("school holiday data has fewer than 8 municipalities")
    for municipality in municipalities:
        for key in ("slug", "name", "source", "holidays"):
            if key not in municipality:
                errors.append(f"school municipality missing {key}: {municipality}")
        if not str(municipality.get("source", "")).startswith("https://"):
            errors.append(f"{municipality.get('name', 'unknown')}: source should be HTTPS")
        holidays = municipality.get("holidays", [])
        if not holidays:
            warnings.append(f"{municipality.get('name', 'unknown')}: no school holiday rows")
        for row in holidays:
            start = date.fromisoformat(row["start"])
            end = date.fromisoformat(row["end"])
            if start > end:
                errors.append(f"{municipality.get('name')}: holiday starts after end -> {row}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2026)
    parser.add_argument("--end", type=int, default=2050)
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    validate_expected_files(args.start, args.end, errors, warnings)
    validate_links(errors)
    validate_sitemap(args.start, args.end, errors)
    validate_calendar_json(args.start, args.end, errors)
    validate_school_data(errors, warnings)

    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: validated {len(list(ROOT.glob('*.html')))} HTML pages, {args.start}-{args.end}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
