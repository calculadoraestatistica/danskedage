#!/usr/bin/env python3
"""Udbytte-scraper for danske aktier (Nasdaq Copenhagen) via Yahoo Finance.

To datakilder, begge gratis og uden API-noegle:
  1. Chart API  (query1.finance.yahoo.com/v8/finance/chart) — historiske
     udbytter pr. ticker (ex-datoer + beloeb). Ingen auth.
  2. quoteSummary calendarEvents — kommende ex-dato/udbetalingsdato.
     Kraever cookie+crumb-dans, implementeret med ren urllib.

Tickerlisten er kurateret (OMXC25 + likvide mid caps) og revideres aarligt.

Modes:
    python tools/scrape_dividends_dk.py --backfill   # 15 aars historik
    python tools/scrape_dividends_dk.py              # dagligt inkrement

Output (data/udbytte/):
    meta.json      {updated_at, years, total_events}
    hist-YYYY.json events med ex-dato i det aar
    recent.json    vindue [nu -4, nu +13 maaneder] + kommende

Eventformat (korte noegler, samme skema som BR-sitet):
    t  ticker      n  selskabsnavn     v  beloeb pr. aktie
    cy valuta      ty type             dc ex-dato (YYYY-MM-DD)
    dp udbetalingsdato eller null      est true hvis dp er estimeret
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "udbytte"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# (yahoo-symbol uden .CO, visningsnavn)
TICKERS = [
    ("NOVO-B", "Novo Nordisk B"),
    ("MAERSK-A", "A.P. Møller-Mærsk A"),
    ("MAERSK-B", "A.P. Møller-Mærsk B"),
    ("DSV", "DSV"),
    ("CARL-B", "Carlsberg B"),
    ("COLO-B", "Coloplast B"),
    ("GN", "GN Store Nord"),
    ("VWS", "Vestas Wind Systems"),
    ("ORSTED", "Ørsted"),
    ("NSIS-B", "Novonesis B"),
    ("TRYG", "Tryg"),
    ("DEMANT", "Demant"),
    ("PNDORA", "Pandora"),
    ("ROCK-B", "Rockwool B"),
    ("AMBU-B", "Ambu B"),
    ("BAVA", "Bavarian Nordic"),
    ("GMAB", "Genmab"),
    ("ISS", "ISS"),
    ("JYSK", "Jyske Bank"),
    ("DANSKE", "Danske Bank"),
    ("NDA-DK", "Nordea Bank"),
    ("RBREW", "Royal Unibrew"),
    # SYDB (Sydbank), TOP (Topdanmark/Sampo 2024) og SPNO (Spar Nord/Nykredit
    # 2025) er afnoteret/404 hos Yahoo — fjernet ved 2026-revision.
    ("FLS", "FLSmidth"),
    ("NKT", "NKT"),
    ("ZEAL", "Zealand Pharma"),
    ("ALK-B", "ALK-Abelló B"),
    ("DFDS", "DFDS"),
    ("DNORD", "D/S Norden"),
    ("TRMD-A", "Torm A"),
    ("RILBA", "Ringkjøbing Landbobank"),
    ("MATAS", "Matas"),
    ("NETC", "Netcompany"),
    ("HLUN-B", "H. Lundbeck B"),
    ("SOLAR-B", "Solar B"),
    ("SCHO", "Schouw & Co"),
    ("PAAL-B", "Per Aarsleff B"),
    ("BO", "Bang & Olufsen"),
    ("CBRAIN", "cBrain"),
    ("ALMB", "Alm. Brand"),
    ("STG", "Scandinavian Tobacco Group"),
    ("TIV", "Tivoli"),
]

CHART_API = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}.CO"
    "?range={rng}&interval=1d&events=div"
)
CRUMB_API = "https://query1.finance.yahoo.com/v1/test/getcrumb"
QSUMMARY_API = (
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}.CO"
    "?modules=calendarEvents&crumb={crumb}"
)
REQUEST_DELAY_S = 0.35
RETRIES = 3


def make_opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA), ("Accept", "application/json,text/html")]
    return opener


def get_json(opener, url: str) -> dict | None:
    for attempt in range(RETRIES):
        try:
            with opener.open(url, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == RETRIES - 1:
                print(f"  giver op: {url.split('?')[0]} ({exc})", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None


def get_crumb(opener) -> str | None:
    """Cookie+crumb-dansen: besoeg fc.yahoo.com (saetter A3-cookie), hent crumb."""
    try:
        try:
            opener.open("https://fc.yahoo.com", timeout=15)
        except urllib.error.HTTPError:
            pass  # 404 forventet — vi vil kun have cookien
        with opener.open(CRUMB_API, timeout=15) as resp:
            crumb = resp.read().decode("utf-8").strip()
            return crumb if crumb and "<" not in crumb else None
    except (urllib.error.URLError, TimeoutError):
        return None


def epoch_to_iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except (ValueError, TypeError, OSError):
        return None


def fetch_history(opener, sym: str, name: str, rng: str) -> list[dict]:
    data = get_json(opener, CHART_API.format(sym=sym, rng=rng))
    if not data:
        return []
    try:
        result = data["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return []
    currency = (result.get("meta") or {}).get("currency") or "DKK"
    divs = ((result.get("events") or {}).get("dividends")) or {}
    out = []
    for item in divs.values():
        dc = epoch_to_iso(item.get("date"))
        amount = item.get("amount")
        if not dc or not amount:
            continue
        out.append({
            "t": sym, "n": name, "v": round(float(amount), 6),
            "cy": currency, "ty": "Udbytte", "dc": dc, "dp": None,
        })
    return out


def fetch_upcoming(opener, crumb: str, sym: str, name: str) -> list[dict]:
    data = get_json(opener, QSUMMARY_API.format(sym=sym, crumb=crumb))
    if not data:
        return []
    try:
        cal = data["quoteSummary"]["result"][0]["calendarEvents"]
    except (KeyError, IndexError, TypeError):
        return []
    ex_raw = (cal.get("exDividendDate") or {})
    pay_raw = (cal.get("dividendDate") or {})
    ex_iso = epoch_to_iso(ex_raw.get("raw")) if isinstance(ex_raw, dict) else None
    pay_iso = epoch_to_iso(pay_raw.get("raw")) if isinstance(pay_raw, dict) else None
    if not ex_iso:
        return []
    today_iso = date.today().isoformat()
    if ex_iso < today_iso and (not pay_iso or pay_iso < today_iso):
        return []  # kun fremtidige
    return [{
        "t": sym, "n": name, "v": None, "cy": "DKK", "ty": "Udbytte",
        "dc": ex_iso, "dp": pay_iso, "upcoming": True,
    }]


def event_key(ev: dict) -> tuple:
    return (ev["t"], ev["dc"])


def load_all_events() -> dict[tuple, dict]:
    seen: dict[tuple, dict] = {}
    if not OUT_DIR.exists():
        return seen
    for f in sorted(OUT_DIR.glob("hist-*.json")):
        for ev in json.loads(f.read_text(encoding="utf-8")):
            seen[event_key(ev)] = ev
    recent = OUT_DIR / "recent.json"
    if recent.exists():
        payload = json.loads(recent.read_text(encoding="utf-8"))
        for ev in payload.get("events", []):
            seen[event_key(ev)] = ev
    return seen


def add_months(d: date, n: int) -> tuple[int, int]:
    total = d.year * 12 + (d.month - 1) + n
    return total // 12, total % 12 + 1


def write_outputs(seen: dict[tuple, dict], upcoming: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    win_lo = "{0}-{1:02d}-01".format(*add_months(today, -4))
    y_hi, m_hi = add_months(today, 13)
    win_hi = f"{y_hi}-{m_hi:02d}-31"

    by_year: dict[int, list[dict]] = {}
    recent_events: list[dict] = []
    for ev in seen.values():
        by_year.setdefault(int(ev["dc"][:4]), []).append(ev)
        if (win_lo <= ev["dc"] <= win_hi) or (ev.get("dp") and win_lo <= ev["dp"] <= win_hi):
            recent_events.append(ev)

    for year, evs in sorted(by_year.items()):
        evs.sort(key=lambda e: (e["dc"], e["t"]))
        (OUT_DIR / f"hist-{year}.json").write_text(
            json.dumps(evs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # kommende, som ikke allerede findes i historikken
    up_out = [ev for ev in upcoming if event_key(ev) not in seen]
    recent_events.sort(key=lambda e: (e["dc"], e["t"]))
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (OUT_DIR / "recent.json").write_text(
        json.dumps({
            "updated_at": now_iso, "window": [win_lo, win_hi],
            "events": recent_events, "provisioned": up_out,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT_DIR / "meta.json").write_text(
        json.dumps({
            "updated_at": now_iso,
            "source": "Yahoo Finance (Nasdaq Copenhagen)",
            "tickers": len(TICKERS),
            "years": sorted(by_year),
            "total_events": len(seen),
            "recent_events": len(recent_events),
            "upcoming": len(up_out),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(seen)} events, {len(recent_events)} i vinduet, {len(up_out)} kommende.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="15 aars historik")
    args = ap.parse_args()

    opener = make_opener()
    seen = load_all_events()
    print(f"Allerede gemt: {len(seen)} events")

    rng = "15y" if args.backfill else "1y"
    for i, (sym, name) in enumerate(TICKERS, 1):
        for ev in fetch_history(opener, sym, name, rng):
            seen[event_key(ev)] = ev
        if i % 10 == 0 or i == len(TICKERS):
            print(f"  historik {i}/{len(TICKERS)} — {len(seen)} events")
        time.sleep(REQUEST_DELAY_S)

    upcoming: list[dict] = []
    crumb = get_crumb(opener)
    if crumb:
        print(f"Crumb OK — henter kommende udbytter...")
        for i, (sym, name) in enumerate(TICKERS, 1):
            upcoming.extend(fetch_upcoming(opener, crumb, sym, name))
            time.sleep(REQUEST_DELAY_S)
        print(f"  kommende: {len(upcoming)}")
    else:
        print("ADVARSEL: kunne ikke hente crumb — springer kommende udbytter over.", file=sys.stderr)

    if not seen:
        print("FEJL: ingen events hentet — skriver ikke.", file=sys.stderr)
        return 1
    write_outputs(seen, upcoming)
    return 0


if __name__ == "__main__":
    sys.exit(main())
