#!/usr/bin/env python3
"""Generate a static Danish calendar site for DanskeDage.dk.

The generated HTML is intentionally plain and dependency-free. National
holidays are calculated by formula; municipal school holidays live in
data/school-holidays.json because they require annual human review.
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOMAIN = "https://danskedage.dk"
SITE_NAME = "DanskeDage.dk"
ADS_CLIENT = "ca-pub-7516029395999799"
CONTACT_EMAIL = "calculadoraestatistica@gmail.com"
BUY_ME_A_COFFEE = "https://buymeacoffee.com/calculadoraestatistica"
ACTIVE_YEAR = date.today().year

MONTHS = [
    "januar",
    "februar",
    "marts",
    "april",
    "maj",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "december",
]
WEEKDAYS = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
WEEKDAYS_LONG = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


@dataclass(frozen=True)
class DayMark:
    date: date
    name: str
    kind: str
    official: bool = False
    note: str = ""


def slugify(text: str) -> str:
    out = (
        text.lower()
        .replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
    )
    keep = []
    last_dash = False
    for ch in out:
        if ch.isalnum():
            keep.append(ch)
            last_dash = False
        elif not last_dash:
            keep.append("-")
            last_dash = True
    return "".join(keep).strip("-")


def fmt_date(d: date) -> str:
    return f"{d.day}. {MONTHS[d.month - 1]} {d.year}"


def iso(d: date) -> str:
    return d.isoformat()


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday using the Meeus/Jones/Butcher algorithm."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def all_marks(year: int) -> list[DayMark]:
    e = easter_sunday(year)
    marks = [
        DayMark(date(year, 1, 1), "Nytårsdag", "helligdag", True),
        DayMark(e - timedelta(days=7), "Palmesøndag", "mærkedag", False),
        DayMark(e - timedelta(days=3), "Skærtorsdag", "helligdag", True),
        DayMark(e - timedelta(days=2), "Langfredag", "helligdag", True),
        DayMark(e, "Påskedag", "helligdag", True),
        DayMark(e + timedelta(days=1), "2. påskedag", "helligdag", True),
        DayMark(e + timedelta(days=26), "Store bededag (historisk)", "historisk", False, "Afskaffet som helligdag fra 2024."),
        DayMark(e + timedelta(days=39), "Kristi himmelfartsdag", "helligdag", True),
        DayMark(e + timedelta(days=49), "Pinsedag", "helligdag", True),
        DayMark(e + timedelta(days=50), "2. pinsedag", "helligdag", True),
        DayMark(date(year, 5, 1), "Arbejdernes kampdag", "mærkedag", False),
        DayMark(date(year, 6, 5), "Grundlovsdag", "mærkedag", False, "Fridag mange steder, men ikke almindelig officiel helligdag."),
        DayMark(date(year, 12, 24), "Juleaftensdag", "mærkedag", False, "Normal arbejdsdag i loven, men fri mange steder."),
        DayMark(date(year, 12, 25), "Juledag", "helligdag", True),
        DayMark(date(year, 12, 26), "2. juledag", "helligdag", True),
        DayMark(date(year, 12, 31), "Nytårsaftensdag", "mærkedag", False, "Normal arbejdsdag i loven, men fri mange steder."),
    ]
    return sorted(marks, key=lambda x: x.date)


def official_holidays(year: int) -> set[date]:
    return {mark.date for mark in all_marks(year) if mark.official}


def office_optional_days(year: int) -> set[date]:
    names = {"Arbejdernes kampdag", "Grundlovsdag", "Juleaftensdag", "Nytårsaftensdag"}
    return {mark.date for mark in all_marks(year) if mark.name in names}


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def is_workday(d: date, include_common_office_days: bool = False) -> bool:
    if d.weekday() >= 5:
        return False
    if d in official_holidays(d.year):
        return False
    if include_common_office_days and d in office_optional_days(d.year):
        return False
    return True


def year_stats(year: int) -> dict:
    days = list(daterange(date(year, 1, 1), date(year, 12, 31)))
    official = official_holidays(year)
    return {
        "days": len(days),
        "weekend_days": sum(1 for d in days if d.weekday() >= 5),
        "official_holidays": len(official),
        "official_holidays_on_weekdays": sum(1 for d in official if d.weekday() < 5),
        "workdays": sum(1 for d in days if is_workday(d)),
        "office_workdays": sum(1 for d in days if is_workday(d, True)),
        "weeks": date(year, 12, 28).isocalendar().week,
    }


def build_best_vacation_windows(year: int) -> list[dict]:
    first = date(year, 1, 1)
    last = date(year, 12, 31)
    candidates = []
    for start_offset in range((last - first).days + 1):
        start = first + timedelta(days=start_offset)
        for length in range(4, 17):
            end = start + timedelta(days=length - 1)
            if end.year != year:
                continue
            days = list(daterange(start, end))
            vacation_days = [d for d in days if is_workday(d)]
            off_days = len(days)
            if not vacation_days or len(vacation_days) > 6:
                continue
            ratio = off_days / len(vacation_days)
            holiday_names = [m.name for m in all_marks(year) if m.date in days and m.official]
            if ratio >= 2.0 or holiday_names:
                candidates.append(
                    {
                        "start": start,
                        "end": end,
                        "days_off": off_days,
                        "vacation_days": len(vacation_days),
                        "ratio": ratio,
                        "holidays": ", ".join(holiday_names) if holiday_names else "weekender",
                    }
                )
    candidates.sort(key=lambda x: (x["ratio"], x["days_off"]), reverse=True)
    picked = []
    used_ranges: list[tuple[date, date]] = []
    for item in candidates:
        if any(not (item["end"] < a or item["start"] > b) for a, b in used_ranges):
            continue
        picked.append(item)
        used_ranges.append((item["start"], item["end"]))
        if len(picked) >= 10:
            break
    return sorted(picked, key=lambda x: x["start"])


def ensure_base_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    (ROOT / "css").mkdir(exist_ok=True)
    (ROOT / "js").mkdir(exist_ok=True)
    (ROOT / "img").mkdir(exist_ok=True)

    school_file = DATA_DIR / "school-holidays.json"
    if not school_file.exists():
        school_file.write_text(json.dumps(default_school_holidays(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (ROOT / "ads.txt").write_text("google.com, pub-7516029395999799, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    (ROOT / "CNAME").write_text("danskedage.dk\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {DOMAIN}/sitemap.xml\n", encoding="utf-8")

    (ROOT / "css" / "style.css").write_text(css_text(), encoding="utf-8")
    (ROOT / "js" / "calendar-tools.js").write_text(js_text(), encoding="utf-8")
    (ROOT / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
    qr_sources = [
        ROOT.parent / "site_lonberegning_dk" / "img" / "bmc_qr.png",
        ROOT.parent / "site_calculadora_dk" / "img" / "bmc_qr.png",
    ]
    for source in qr_sources:
        if source.exists():
            shutil.copy2(source, ROOT / "img" / "bmc_qr.png")
            break


def default_school_holidays() -> dict:
    return {
        "updated": "2026-06-10",
        "review_note": "Municipal school holidays are not purely formula-based. Review this file once per year before running tools/annual_review.py.",
        "school_years": ["2026-2027", "2027-2028"],
        "municipalities": [
            municipality("Kobenhavn", "København", "https://www.kk.dk/borger/dagtilbud-og-skole/skole-og-fritid/vejledende-ferieplan-for-skoleaaret-i-koebenhavns-kommune", [
                ("2026-2027", "Sommerferie 2026", "2026-06-29", "2026-08-10"),
                ("2026-2027", "Efterårsferie", "2026-10-12", "2026-10-16"),
                ("2026-2027", "Juleferie", "2026-12-21", "2027-01-01"),
                ("2026-2027", "Vinterferie", "2027-02-15", "2027-02-19"),
                ("2026-2027", "Påskeferie", "2027-03-22", "2027-03-29"),
                ("2026-2027", "Kr. Himmelfartsferie", "2027-05-06", "2027-05-07"),
                ("2026-2027", "Pinse", "2027-05-16", "2027-05-17"),
                ("2026-2027", "Sommerferie 2027", "2027-06-28", "2027-08-06"),
            ]),
            municipality("Aarhus", "Aarhus", "https://aarhus.dk/borger/pasning-skole-og-uddannelse/skole-sfo-og-klub/naar-dit-barn-gaar-i-skole/ferier-og-fridage", [
                ("2026-2027", "Sommerferie 2026", "2026-06-27", "2026-08-10"),
                ("2026-2027", "Efterårsferie", "2026-10-10", "2026-10-18"),
                ("2026-2027", "Juleferie", "2026-12-19", "2027-01-03"),
                ("2026-2027", "Vinterferie", "2027-02-13", "2027-02-21"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kr. Himmelfartsdag", "2027-05-06", "2027-05-06"),
                ("2026-2027", "Fridag efter Kr. Himmelfart", "2027-05-07", "2027-05-07"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
                ("2026-2027", "Sommerferie 2027", "2027-06-26", "2027-08-08"),
            ]),
            municipality("Odense", "Odense", "https://www.odense.dk/borger/familie-boern-og-unge/skole-og-sfo/0-9-klasse/praktiske-oplysninger/feriekalender", [
                ("2026-2027", "Juleferie", "2026-12-21", "2027-01-04"),
                ("2026-2027", "Vinterferie", "2027-02-13", "2027-02-21"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kr. Himmelfartsdag", "2027-05-06", "2027-05-07"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
                ("2026-2027", "Sommerferien begynder", "2027-06-26", "2027-06-26"),
            ]),
            municipality("Aalborg", "Aalborg", "https://www.aalborg.dk/mit-liv/mit-barn/skole/skoleliv/skoleferie-og-fravaer/", [
                ("2026-2027", "Efterårsferie", "2026-10-10", "2026-10-18"),
                ("2026-2027", "Juleferie", "2026-12-23", "2027-01-03"),
                ("2026-2027", "Vinterferie", "2027-02-20", "2027-02-28"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kristi Himmelfartsferie", "2027-05-06", "2027-05-09"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
            ]),
            municipality("Esbjerg", "Esbjerg", "https://skoler.esbjerg.dk/praktisk-information/feriekalender", [
                ("2026-2027", "Sommerferie 2026", "2026-06-27", "2026-08-12"),
            ]),
            municipality("Kolding", "Kolding", "https://www.kolding.dk/borger/skole-og-uddannelse/ferier-lukning-og-behovsaabent", [
                ("2026-2027", "Sommerferie 2026", "2026-06-27", "2026-08-09"),
                ("2026-2027", "Efterårsferie", "2026-10-10", "2026-10-18"),
                ("2026-2027", "Juleferie", "2026-12-19", "2027-01-04"),
                ("2026-2027", "Vinterferie", "2027-02-13", "2027-02-21"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kr. himmelfartsdag + 1 dag", "2027-05-06", "2027-05-07"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
            ]),
            municipality("Horsens", "Horsens", "https://horsens.dk/familie/boernogunge/ferieplaner", [
                ("2026-2027", "Sommerferie 2026", "2026-06-27", "2026-08-09"),
                ("2026-2027", "Efterårsferie", "2026-10-10", "2026-10-18"),
                ("2026-2027", "Juleferie", "2026-12-19", "2027-01-04"),
                ("2026-2027", "Vinterferie", "2027-02-13", "2027-02-21"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kristi Himmelfart", "2027-05-06", "2027-05-09"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
            ]),
            municipality("Vejle", "Vejle", "https://www.vejle.dk/da/service-og-selvbetjening/borger/boern-skole-og-familie/skole-og-uddannelse/skoleliv/ferier-og-andre-fridage-i-skoleaaret/", [
                ("2026-2027", "Sommerferie 2026", "2026-06-27", "2026-08-10"),
                ("2026-2027", "Efterårsferie", "2026-10-10", "2026-10-18"),
                ("2026-2027", "Juleferie", "2026-12-19", "2027-01-03"),
                ("2026-2027", "Vinterferie", "2027-02-13", "2027-02-21"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kr. Himmelfartsdag + dagen efter", "2027-05-06", "2027-05-09"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
                ("2026-2027", "Sommerferie 2027", "2027-06-26", "2027-08-09"),
            ]),
            municipality("Roskilde", "Roskilde", "https://www.roskilde.dk/da-dk/service-og-selvbetjening/borger/skole-og-uddannelse/folkeskole/skoleferier-og-lukkedage/", [
                ("2026-2027", "Efterårsferie", "2026-10-10", "2026-10-18"),
                ("2026-2027", "Juleferie", "2026-12-19", "2027-01-03"),
                ("2026-2027", "Vinterferie", "2027-02-20", "2027-02-28"),
                ("2026-2027", "Påskeferie", "2027-03-20", "2027-03-29"),
                ("2026-2027", "Kristi Himmelfartsferie", "2027-05-06", "2027-05-09"),
                ("2026-2027", "Pinseferie", "2027-05-15", "2027-05-17"),
                ("2026-2027", "Sommerferie 2027", "2027-06-26", "2027-08-08"),
            ]),
        ],
    }


def municipality(slug: str, name: str, source: str, rows: list[tuple[str, str, str, str]]) -> dict:
    return {
        "slug": slugify(slug),
        "name": name,
        "source": source,
        "holidays": [
            {"school_year": school_year, "name": holiday_name, "start": start, "end": end}
            for school_year, holiday_name, start, end in rows
        ],
    }


def css_text() -> str:
    return """\
:root{--bg:#f7f7f2;--paper:#fff;--ink:#19201d;--muted:#667067;--line:#dfe3dc;--brand:#0f766e;--brand2:#1d4ed8;--accent:#b45309;--soft:#ecfdf5;--danger:#b91c1c;--radius:8px;--shadow:0 12px 28px rgba(15,23,42,.08)}
*{box-sizing:border-box}html{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:var(--bg);line-height:1.55}body{margin:0}a{color:#0f5f59}a:hover{color:#0b4b45}.skip-link{position:absolute;left:-999px}.skip-link:focus{left:1rem;top:1rem;background:#fff;padding:.6rem 1rem;border:2px solid var(--brand);z-index:99}.container{width:min(1120px,calc(100% - 32px));margin-inline:auto}.container--narrow{width:min(820px,calc(100% - 32px));margin-inline:auto}.site-header{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}.site-header__inner{display:flex;align-items:center;gap:1rem;justify-content:space-between;min-height:64px}.brand{display:flex;align-items:center;gap:.65rem;text-decoration:none;color:var(--ink);font-weight:800}.brand__mark{width:36px;height:36px}.main-nav ul{list-style:none;margin:0;padding:0;display:flex;gap:.25rem;flex-wrap:wrap}.main-nav a{display:block;text-decoration:none;color:var(--muted);padding:.55rem .7rem;border-radius:6px;font-weight:650;font-size:.95rem}.main-nav a[aria-current=page],.main-nav a:hover{background:#eef7f4;color:#0f5f59}.hero{padding:2.6rem 0 1.6rem;background:linear-gradient(180deg,#fff 0,#f7f7f2 100%)}.hero-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(280px,.95fr);gap:2rem;align-items:start}.eyebrow{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--brand);font-weight:800}.hero h1{font-size:clamp(2rem,5vw,4.2rem);line-height:1.02;margin:.35rem 0 1rem;letter-spacing:0}.lead{font-size:1.12rem;color:#39423d;max-width:68ch}.hero-actions{display:flex;gap:.7rem;flex-wrap:wrap;margin-top:1.3rem}.btn{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;border-radius:7px;padding:.72rem 1rem;font-weight:800;border:1px solid transparent}.btn--primary{background:var(--brand);color:#fff}.btn--primary:hover{background:#0b5d55;color:#fff}.btn--ghost{border-color:var(--line);background:#fff;color:var(--ink)}.quick-panel{background:#fff;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:1rem}.mini-calendar{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}.mini-calendar span{display:flex;align-items:center;justify-content:center;min-height:34px;border-radius:5px;background:#f4f6f2;font-size:.85rem}.mini-calendar .head{background:#e6ece6;color:#475047;font-weight:800}.mini-calendar .holiday{background:#fee2e2;color:#991b1b;font-weight:800}.mini-calendar .today{outline:2px solid var(--brand);background:#ecfdf5}.section{padding:2rem 0}.section-title{display:flex;align-items:end;justify-content:space-between;gap:1rem;margin-bottom:1rem}.section-title h2{margin:0;font-size:1.55rem}.section-title p{margin:.2rem 0 0;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}.card{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:1rem;box-shadow:0 8px 18px rgba(15,23,42,.04)}.card h3{margin:.1rem 0 .4rem}.stat{font-size:2rem;font-weight:850;color:#0f5f59;margin:.2rem 0}.muted{color:var(--muted)}.prose{font-size:1.03rem}.prose h2{margin-top:1.8rem}.prose p,.prose li{color:#33403a}.prose li{margin:.35rem 0}.table-wrap{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:var(--radius)}table{border-collapse:collapse;width:100%;min-width:640px}th,td{padding:.72rem .8rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#eef2ee;color:#475047;font-size:.82rem;text-transform:uppercase;letter-spacing:.04em}.month-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:1rem}.month{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:.8rem}.month h3{margin:0 0 .65rem;text-transform:capitalize}.calendar-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}.calendar-grid span{min-height:32px;display:flex;align-items:center;justify-content:center;border-radius:5px;background:#f8faf7;font-size:.86rem}.calendar-grid .head{font-weight:800;background:#e7ece7;color:#4b554d}.calendar-grid .empty{background:transparent}.calendar-grid .weekend{background:#f1f5f9;color:#64748b}.calendar-grid .holiday{background:#fee2e2;color:#991b1b;font-weight:800}.calendar-grid .special{background:#fef3c7;color:#92400e}.tool{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:1rem;box-shadow:var(--shadow)}.tool-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.8rem}.field label{display:block;font-weight:750;margin-bottom:.25rem}.field input,.field select{width:100%;padding:.68rem .75rem;border:1px solid #cbd5cf;border-radius:6px;font:inherit}.result-box{margin-top:1rem;background:#ecfdf5;border:1px solid #bbf7d0;border-radius:7px;padding:1rem}.notice{background:#fffbeb;border:1px solid #fde68a;border-radius:7px;padding:1rem;color:#713f12}.donate-card{text-align:center}.donate-qr{display:block;max-width:190px;height:auto;margin:1rem auto 0;border:1px solid var(--line);border-radius:8px}.footer{margin-top:2rem;padding:2rem 0;background:#10201c;color:#e7f5ef}.footer a{color:#a7f3d0}.footer-grid{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:1rem}.footer ul{list-style:none;padding:0;margin:.4rem 0}.footer li{margin:.25rem 0}.ad-note{min-height:90px;border:1px dashed #cbd5cf;border-radius:7px;display:flex;align-items:center;justify-content:center;color:var(--muted);background:#fff}.breadcrumbs{font-size:.9rem;color:var(--muted);margin:.9rem 0}.tag{display:inline-flex;padding:.18rem .45rem;border-radius:999px;background:#eef7f4;color:#0f5f59;font-size:.78rem;font-weight:800}@media(max-width:760px){.hero-grid{grid-template-columns:1fr}.main-nav ul{gap:.1rem}.footer-grid{grid-template-columns:1fr}.section-title{display:block}table{min-width:520px}}
"""


def js_text() -> str:
    return """\
(function(){
  function easter(y){var a=y%19,b=Math.floor(y/100),c=y%100,d=Math.floor(b/4),e=b%4,f=Math.floor((b+8)/25),g=Math.floor((b-f+1)/3),h=(19*a+b-d-g+15)%30,i=Math.floor(c/4),k=c%4,l=(32+2*e+2*i-h-k)%7,m=Math.floor((a+11*h+22*l)/451),mo=Math.floor((h+l-7*m+114)/31),da=((h+l-7*m+114)%31)+1;return new Date(Date.UTC(y,mo-1,da));}
  function addDays(d,n){var x=new Date(d.getTime());x.setUTCDate(x.getUTCDate()+n);return x;}
  function iso(d){return d.toISOString().slice(0,10);}
  function holidays(y){var e=easter(y),out=[];function push(d,n){out.push([iso(d),n]);}push(new Date(Date.UTC(y,0,1)),'Nytårsdag');push(addDays(e,-3),'Skærtorsdag');push(addDays(e,-2),'Langfredag');push(e,'Påskedag');push(addDays(e,1),'2. påskedag');push(addDays(e,39),'Kristi himmelfartsdag');push(addDays(e,49),'Pinsedag');push(addDays(e,50),'2. pinsedag');push(new Date(Date.UTC(y,11,25)),'Juledag');push(new Date(Date.UTC(y,11,26)),'2. juledag');return new Map(out);}
  function optional(y){return new Set([iso(new Date(Date.UTC(y,4,1))),iso(new Date(Date.UTC(y,5,5))),iso(new Date(Date.UTC(y,11,24))),iso(new Date(Date.UTC(y,11,31)))]);}
  function parse(s){var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}
  function isWorkday(d,includeOffice){var wd=d.getUTCDay();if(wd===0||wd===6)return false;var id=iso(d);if(holidays(d.getUTCFullYear()).has(id))return false;if(includeOffice&&optional(d.getUTCFullYear()).has(id))return false;return true;}
  function fmt(n){return new Intl.NumberFormat('da-DK').format(n);}
  function between(){var start=document.getElementById('bd-start'),end=document.getElementById('bd-end'),mode=document.getElementById('bd-mode'),out=document.getElementById('bd-result');if(!start||!end||!out)return;var a=parse(start.value),b=parse(end.value);if(isNaN(a)||isNaN(b)||b<a){out.innerHTML='Vælg en gyldig start- og slutdato.';return;}var incl=mode.value==='office',days=0,total=0,hol=[];for(var d=a;d<=b;d=addDays(d,1)){total++;if(isWorkday(d,incl))days++;var h=holidays(d.getUTCFullYear()).get(iso(d));if(h)hol.push(h+' ('+iso(d)+')');}out.innerHTML='<strong>'+fmt(days)+' arbejdsdage</strong><br><span>'+fmt(total)+' kalenderdage i perioden.</span>'+(hol.length?'<br><small>Helligdage i perioden: '+hol.join(', ')+'</small>':'');}
  function addBusiness(){var start=document.getElementById('add-start'),amount=document.getElementById('add-amount'),mode=document.getElementById('add-mode'),out=document.getElementById('add-result');if(!start||!amount||!out)return;var d=parse(start.value),n=parseInt(amount.value,10)||0,incl=mode.value==='office';if(isNaN(d)||n<0){out.innerHTML='Vælg en gyldig dato og antal dage.';return;}var left=n;while(left>0){d=addDays(d,1);if(isWorkday(d,incl))left--;}out.innerHTML='<strong>'+iso(d)+'</strong><br><span>'+d.toLocaleDateString('da-DK',{weekday:'long',year:'numeric',month:'long',day:'numeric',timeZone:'UTC'})+'</span>';}
  function weekNumber(){var input=document.getElementById('week-date'),out=document.getElementById('week-result');if(!input||!out)return;var d=parse(input.value);if(isNaN(d)){out.innerHTML='Vælg en dato.';return;}var tmp=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()));var day=tmp.getUTCDay()||7;tmp.setUTCDate(tmp.getUTCDate()+4-day);var yStart=new Date(Date.UTC(tmp.getUTCFullYear(),0,1));var week=Math.ceil((((tmp-yStart)/86400000)+1)/7);out.innerHTML='<strong>Uge '+week+'</strong><br><span>'+input.value+' ligger i ISO-uge '+week+'.</span>';}
  document.addEventListener('input',between);document.addEventListener('change',between);document.addEventListener('input',addBusiness);document.addEventListener('change',addBusiness);document.addEventListener('input',weekNumber);document.addEventListener('change',weekNumber);between();addBusiness();weekNumber();
})();
"""


def favicon_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#0f766e"/><rect x="12" y="15" width="40" height="37" rx="5" fill="#fff"/><rect x="12" y="15" width="40" height="10" rx="5" fill="#134e4a"/><path d="M22 34h7v7h-7zm13 0h7v7h-7z" fill="#0f766e"/></svg>"""


def layout(title: str, description: str, path: str, body: str, current: str = "") -> str:
    canonical = DOMAIN + ("/" if path == "index.html" else f"/{path}")
    nav_year = ACTIVE_YEAR
    nav = [
        ("Kalender", f"kalender-{nav_year}.html", "kalender"),
        ("Helligdage", f"helligdage-{nav_year}.html", "helligdage"),
        ("Arbejdsdage", f"arbejdsdage-{nav_year}.html", "arbejdsdage"),
        ("Ugenummer", "ugenummer.html", "ugenummer"),
        ("Skoleferier", "skoleferier.html", "skoleferier"),
        ("Ferieplan", f"bedste-feriedage-{nav_year}.html", "ferieplan"),
    ]
    nav_html_parts = []
    for label, href, key in nav:
        current_attr = ' aria-current="page"' if key == current else ""
        nav_html_parts.append(f'<li><a href="{href}"{current_attr}>{label}</a></li>')
    nav_html = "".join(nav_html_parts)
    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#0f766e">
<meta property="og:type" content="website">
<meta property="og:locale" content="da_DK">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{canonical}">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADS_CLIENT}" crossorigin="anonymous"></script>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="css/style.css">
<script type="application/ld+json">{json.dumps(json_ld(title, description, canonical), ensure_ascii=False)}</script>
</head>
<body>
<a class="skip-link" href="#indhold">Spring til indhold</a>
<header class="site-header"><div class="container site-header__inner">
<a class="brand" href="index.html"><svg class="brand__mark" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="12" fill="#0f766e"/><rect x="12" y="15" width="40" height="37" rx="5" fill="#fff"/><rect x="12" y="15" width="40" height="10" rx="5" fill="#134e4a"/><path d="M22 34h7v7h-7zm13 0h7v7h-7z" fill="#0f766e"/></svg><span>{SITE_NAME}</span></a>
<nav class="main-nav" aria-label="Hovedmenu"><ul>{nav_html}</ul></nav>
</div></header>
<main id="indhold">{body}</main>
<footer class="footer"><div class="container footer-grid">
<div><h2>{SITE_NAME}</h2><p>Danske kalender- og hverdagsberegnere. Gratis, opdateret og uden login.</p></div>
<div><h3>Kalender</h3><ul><li><a href="kalender-{nav_year}.html">Kalender {nav_year}</a></li><li><a href="helligdage-{nav_year}.html">Helligdage {nav_year}</a></li><li><a href="arbejdsdage-{nav_year}.html">Arbejdsdage {nav_year}</a></li></ul></div>
<div><h3>Værktøjer</h3><ul><li><a href="beregn-arbejdsdage.html">Beregn arbejdsdage</a></li><li><a href="laeg-arbejdsdage-til.html">Læg arbejdsdage til</a></li><li><a href="ugenummer.html">Ugenummer</a></li></ul></div>
<div><h3>Site</h3><ul><li><a href="om.html">Om og kilder</a></li><li><a href="kontakt.html">Kontakt</a></li><li><a href="privatlivspolitik.html">Privatlivspolitik</a></li><li><a href="vilkar.html">Vilkår</a></li><li><a href="stot.html">Støt projektet</a></li><li><a href="sitemap.xml">Sitemap</a></li></ul></div>
</div></footer>
<script src="js/calendar-tools.js"></script>
</body>
</html>
"""


def json_ld(title: str, description: str, url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": description,
        "url": url,
        "inLanguage": "da-DK",
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": DOMAIN + "/"},
    }


def hero(title: str, lead: str, year: int | None = None) -> str:
    side = mini_month(date.today().year if year is None else year, date.today().month if year is None else 1)
    return f"""<section class="hero"><div class="container hero-grid"><div><span class="eyebrow">Dansk kalender · opdateret {ACTIVE_YEAR}</span><h1>{title}</h1><p class="lead">{lead}</p><div class="hero-actions"><a class="btn btn--primary" href="beregn-arbejdsdage.html">Beregn arbejdsdage</a><a class="btn btn--ghost" href="ugenummer.html">Find ugenummer</a></div></div><aside class="quick-panel">{side}</aside></div></section>"""


def mini_month(year: int, month: int) -> str:
    return f"<h2>{MONTHS[month-1].capitalize()} {year}</h2>" + month_calendar_html(year, month, mini=True)


def month_calendar_html(year: int, month: int, mini: bool = False) -> str:
    cal = calendar.Calendar(firstweekday=0)
    marks = {m.date: m for m in all_marks(year)}
    today = date.today()
    cls = "mini-calendar" if mini else "calendar-grid"
    parts = [f'<div class="{cls}">']
    for wd in WEEKDAYS:
        parts.append(f'<span class="head">{wd}</span>')
    for d in cal.itermonthdates(year, month):
        if d.month != month:
            parts.append('<span class="empty"></span>')
            continue
        classes = []
        if d.weekday() >= 5:
            classes.append("weekend")
        mark = marks.get(d)
        if mark and mark.official:
            classes.append("holiday")
        elif mark:
            classes.append("special")
        if d == today:
            classes.append("today")
        title = f' title="{html.escape(mark.name)}"' if mark else ""
        parts.append(f'<span class="{" ".join(classes)}"{title}>{d.day}</span>')
    parts.append("</div>")
    return "\n".join(parts)


def year_overview(year: int) -> str:
    stats = year_stats(year)
    cards = [
        ("Arbejdsdage", stats["workdays"], "mandag-fredag minus officielle helligdage"),
        ("Helligdage", stats["official_holidays"], "officielle helligdage i kalenderåret"),
        ("Uger", stats["weeks"], "ISO-uger i året"),
        ("Weekenddage", stats["weekend_days"], "lørdage og søndage"),
    ]
    return '<div class="grid">' + "".join(
        f'<article class="card"><h3>{label}</h3><p class="stat">{value}</p><p class="muted">{desc}</p></article>'
        for label, value, desc in cards
    ) + "</div>"


def write_page(path: str, title: str, description: str, body: str, current: str = "") -> None:
    (ROOT / path).write_text(layout(title, description, path, body, current), encoding="utf-8")


def render_index(year: int) -> None:
    body = hero(
        f"Kalender {year}",
        f"Se dansk kalender for {year} med helligdage, arbejdsdage, ugenumre, påske, pinse og forslag til gode feriedage.",
        year,
    )
    body += '<section class="section"><div class="container"><div class="section-title"><div><h2>Overblik for året</h2><p>Nøgletal for kalenderåret, beregnet lokalt.</p></div></div>'
    body += year_overview(year)
    body += '</div></section>'
    body += link_grid(year)
    body += year_calendar_section(year)
    write_page("index.html", f"Kalender {year} - helligdage, arbejdsdage og ugenumre", f"Dansk kalender {year} med helligdage, arbejdsdage, ugenumre og ferieforslag.", body, "kalender")


def link_grid(year: int) -> str:
    links = [
        (f"Helligdage {year}", f"helligdage-{year}.html", "Officielle helligdage og særlige mærkedage."),
        (f"Arbejdsdage {year}", f"arbejdsdage-{year}.html", "Antal arbejdsdage pr. måned og hele året."),
        (f"Bedste feriedage {year}", f"bedste-feriedage-{year}.html", "Få mere fri ud af færre feriedage."),
        (f"Påske {year}", f"paaske-{year}.html", "Datoer for påskeugen."),
        (f"Pinse {year}", f"pinse-{year}.html", "Pinsedag og 2. pinsedag."),
        (f"Kristi himmelfartsdag {year}", f"kristi-himmelfartsdag-{year}.html", "Dato og feriebrug omkring helligdagen."),
    ]
    return '<section class="section"><div class="container"><div class="grid">' + "".join(
        f'<a class="card" href="{href}"><h3>{title}</h3><p class="muted">{desc}</p></a>'
        for title, href, desc in links
    ) + "</div></div></section>"


def year_calendar_section(year: int) -> str:
    months = []
    for month in range(1, 13):
        months.append(f'<section class="month"><h3>{MONTHS[month-1]} {year}</h3>{month_calendar_html(year, month)}</section>')
    return '<section class="section"><div class="container"><div class="section-title"><div><h2>Kalender måned for måned</h2><p>Røde dage er officielle helligdage. Gule dage er mærkedage eller almindelige fridage mange steder.</p></div></div><div class="month-grid">' + "".join(months) + "</div></div></section>"


def render_year_pages(year: int) -> None:
    stats = year_stats(year)
    body = hero(f"Kalender {year}", f"Komplet dansk kalender for {year} med helligdage, arbejdsdage, ugenumre og planlægning af ferie.", year)
    body += '<section class="section"><div class="container">'
    body += year_overview(year)
    body += '</div></section>' + link_grid(year) + year_calendar_section(year)
    write_page(f"kalender-{year}.html", f"Kalender {year} - dansk kalender med helligdage", f"Dansk kalender {year}: {stats['workdays']} arbejdsdage, {stats['official_holidays']} officielle helligdage og {stats['weeks']} ISO-uger.", body, "kalender")

    render_holidays(year)
    render_workdays(year)
    render_easter(year)
    render_pentecost(year)
    render_ascension(year)
    render_best_vacation(year)


def render_holidays(year: int) -> None:
    rows = "".join(
        f"<tr><td>{fmt_date(m.date)}</td><td>{WEEKDAYS_LONG[m.date.weekday()]}</td><td>{m.name}</td><td>{'Ja' if m.official else 'Nej'}</td><td>{m.note}</td></tr>"
        for m in all_marks(year)
    )
    body = hero(f"Helligdage {year}", f"Alle danske helligdage og vigtige mærkedage i {year}, inklusive påske, pinse, jul og nytår.", year)
    body += f'<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Dato</th><th>Ugedag</th><th>Dag</th><th>Officiel helligdag</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table></div><p class="notice">Store bededag er markeret historisk, men er ikke officiel helligdag i Danmark fra 2024.</p></div></section>'
    write_page(f"helligdage-{year}.html", f"Helligdage {year} i Danmark", f"Se danske helligdage {year}: påske, pinse, Kristi himmelfartsdag, jul, nytår og særlige mærkedage.", body, "helligdage")


def render_workdays(year: int) -> None:
    official = official_holidays(year)
    optional = office_optional_days(year)
    rows = []
    for month in range(1, 13):
        days = list(daterange(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])))
        rows.append(
            f"<tr><td>{MONTHS[month-1].capitalize()}</td><td>{len(days)}</td><td>{sum(1 for d in days if d.weekday()<5)}</td><td>{sum(1 for d in days if d in official and d.weekday()<5)}</td><td>{sum(1 for d in days if is_workday(d))}</td><td>{sum(1 for d in days if is_workday(d, True))}</td></tr>"
        )
    stats = year_stats(year)
    body = hero(f"Arbejdsdage {year}", f"Beregnede arbejdsdage pr. måned i {year}. Standardtallet tæller mandag-fredag minus officielle helligdage.", year)
    body += f'<section class="section"><div class="container"><div class="grid"><article class="card"><h3>Standard</h3><p class="stat">{stats["workdays"]}</p><p class="muted">Arbejdsdage uden officielle helligdage.</p></article><article class="card"><h3>Kontor-variant</h3><p class="stat">{stats["office_workdays"]}</p><p class="muted">Trækker også 1. maj, Grundlovsdag, juleaftensdag og nytårsaftensdag fra.</p></article></div></div></section>'
    body += '<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Måned</th><th>Kalenderdage</th><th>Hverdage</th><th>Helligdage på hverdage</th><th>Arbejdsdage</th><th>Kontor-variant</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></div></section>"
    write_page(f"arbejdsdage-{year}.html", f"Arbejdsdage {year} - antal arbejdsdage pr. måned", f"Se hvor mange arbejdsdage der er i {year}, måned for måned.", body, "arbejdsdage")


def render_easter(year: int) -> None:
    e = easter_sunday(year)
    rows = [
        ("Palmesøndag", e - timedelta(days=7)),
        ("Skærtorsdag", e - timedelta(days=3)),
        ("Langfredag", e - timedelta(days=2)),
        ("Påskedag", e),
        ("2. påskedag", e + timedelta(days=1)),
    ]
    render_event_page(year, "Påske", "paaske", rows, "Påsken styrer også datoerne for Kristi himmelfartsdag og pinse.")


def render_pentecost(year: int) -> None:
    e = easter_sunday(year)
    rows = [("Pinsedag", e + timedelta(days=49)), ("2. pinsedag", e + timedelta(days=50))]
    render_event_page(year, "Pinse", "pinse", rows, "Pinse falder 49 og 50 dage efter påskedag.")


def render_ascension(year: int) -> None:
    e = easter_sunday(year)
    rows = [("Kristi himmelfartsdag", e + timedelta(days=39)), ("Fredag efter Kr. Himmelfart", e + timedelta(days=40))]
    render_event_page(year, "Kristi himmelfartsdag", "kristi-himmelfartsdag", rows, "Kristi himmelfartsdag falder altid på en torsdag, 39 dage efter påskedag.")


def render_event_page(year: int, name: str, slug: str, rows: list[tuple[str, date]], note: str) -> None:
    table = "".join(f"<tr><td>{label}</td><td>{fmt_date(d)}</td><td>{WEEKDAYS_LONG[d.weekday()]}</td></tr>" for label, d in rows)
    body = hero(f"{name} {year}", f"Datoer for {name.lower()} i {year}. {note}", year)
    body += f'<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Dag</th><th>Dato</th><th>Ugedag</th></tr></thead><tbody>{table}</tbody></table></div></div></section>'
    write_page(f"{slug}-{year}.html", f"{name} {year} - datoer i Danmark", f"Se dato for {name.lower()} {year} og de tilknyttede fridage.", body, "helligdage")


def render_best_vacation(year: int) -> None:
    rows = "".join(
        f"<tr><td>{fmt_date(item['start'])} - {fmt_date(item['end'])}</td><td>{item['days_off']}</td><td>{item['vacation_days']}</td><td>{item['holidays']}</td><td>{item['ratio']:.1f}x</td></tr>"
        for item in build_best_vacation_windows(year)
    )
    body = hero(f"Bedste feriedage {year}", f"Forslag til hvordan du kan få flere sammenhængende fridage i {year} ved at placere feriedage omkring weekender og helligdage.", year)
    body += f'<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Periode</th><th>Dage fri i alt</th><th>Feriedage brugt</th><th>Helligdage i perioden</th><th>Effekt</th></tr></thead><tbody>{rows}</tbody></table></div><p class="notice">Forslagene bruger kun officielle helligdage og weekender. Tjek altid din overenskomst, lokale fridage og arbejdsgiverens regler.</p></div></section>'
    write_page(f"bedste-feriedage-{year}.html", f"Bedste feriedage {year} - få mere fri", f"Se gode perioder at holde ferie i {year}, baseret på helligdage og weekender.", body, "ferieplan")


def render_tools() -> None:
    today = date.today().isoformat()
    body = hero("Beregn arbejdsdage mellem to datoer", "Vælg start- og slutdato og se antal arbejdsdage i perioden. Du kan vælge standard eller en kontor-variant med almindelige fridage.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="tool"><div class="tool-grid"><div class="field"><label for="bd-start">Startdato</label><input id="bd-start" type="date" value="{today}"></div><div class="field"><label for="bd-end">Slutdato</label><input id="bd-end" type="date" value="{today}"></div><div class="field"><label for="bd-mode">Regel</label><select id="bd-mode"><option value="official">Kun officielle helligdage</option><option value="office">Kontor-variant</option></select></div></div><div id="bd-result" class="result-box"></div></div></div></section>"""
    write_page("beregn-arbejdsdage.html", "Beregn arbejdsdage mellem to datoer", "Gratis beregner for arbejdsdage mellem to datoer i Danmark.", body, "arbejdsdage")

    body = hero("Læg arbejdsdage til en dato", "Find datoen efter et bestemt antal arbejdsdage. Beregneren springer weekender og danske helligdage over.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="tool"><div class="tool-grid"><div class="field"><label for="add-start">Startdato</label><input id="add-start" type="date" value="{today}"></div><div class="field"><label for="add-amount">Antal arbejdsdage</label><input id="add-amount" type="number" min="0" value="10"></div><div class="field"><label for="add-mode">Regel</label><select id="add-mode"><option value="official">Kun officielle helligdage</option><option value="office">Kontor-variant</option></select></div></div><div id="add-result" class="result-box"></div></div></div></section>"""
    write_page("laeg-arbejdsdage-til.html", "Læg arbejdsdage til en dato", "Beregn datoen efter X arbejdsdage i Danmark.", body, "arbejdsdage")

    body = hero("Ugenummer", "Find ISO-ugenummer for en dato i Danmark. Danske kalendere bruger normalt ISO-uger, hvor ugen starter mandag.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="tool"><div class="tool-grid"><div class="field"><label for="week-date">Dato</label><input id="week-date" type="date" value="{today}"></div></div><div id="week-result" class="result-box"></div></div></div></section>"""
    write_page("ugenummer.html", "Ugenummer - find uge for en dato", "Find ugenummer for en dato i Danmark.", body, "ugenummer")


def render_school_holidays() -> None:
    data = json.loads((DATA_DIR / "school-holidays.json").read_text(encoding="utf-8-sig"))
    cards = []
    rows = []
    for m in data["municipalities"]:
        cards.append(
            f'<article class="card"><h3>{m["name"]}</h3><p>{len(m["holidays"])} registrerede ferieperioder.</p><a class="text-link" href="skoleferier-{m["slug"]}.html">Se skoleferier for {m["name"]}</a></article>'
        )
        for h in m["holidays"]:
            rows.append(
                f'<tr><td><a href="skoleferier-{m["slug"]}.html">{m["name"]}</a></td><td>{h["school_year"]}</td><td>{h["name"]}</td><td>{h["start"]}</td><td>{h["end"]}</td><td><a href="{m["source"]}" rel="nofollow noopener" target="_blank">Kilde</a></td></tr>'
            )
    body = hero("Skoleferier i store kommuner", "Se udvalgte skoleferier i større danske kommuner. Skoleferier fastsættes lokalt og skal derfor revideres årligt.", date.today().year)
    body += '<section class="section"><div class="container"><p class="notice">Skoleferier er ikke en matematisk kalenderregel. Kommunerne kan have forskellige datoer, og skoler kan have lokale afvigelser. Brug tabellen som hurtigt overblik og tjek altid kommunens egen side.</p><div class="grid">' + "".join(cards) + '</div><div class="table-wrap"><table><thead><tr><th>Kommune</th><th>Skoleår</th><th>Ferie/fridag</th><th>Fra</th><th>Til</th><th>Kilde</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></div></section>"
    write_page("skoleferier.html", "Skoleferier - ferieplaner i store danske kommuner", "Skoleferier for udvalgte store kommuner i Danmark med officielle kilder.", body, "skoleferier")
    for municipality_data in data["municipalities"]:
        render_school_municipality(municipality_data, data.get("updated", ""))


def render_school_municipality(m: dict, updated: str) -> None:
    rows = "".join(
        f'<tr><td>{h["school_year"]}</td><td>{h["name"]}</td><td>{h["start"]}</td><td>{h["end"]}</td></tr>'
        for h in m["holidays"]
    )
    body = hero(f"Skoleferier i {m['name']}", f"Ferieplan og fridage for skoler i {m['name']}. Datoerne er samlet som et hurtigt overblik med kilde til kommunens egen side.", date.today().year)
    body += f'<section class="section"><div class="container"><div class="grid"><article class="card"><h3>Senest gennemgået</h3><p class="stat">{updated}</p><p class="muted">Tjek altid kommunens egen kalender ved planlægning.</p></article><article class="card"><h3>Officiel kilde</h3><p><a class="text-link" href="{m["source"]}" rel="nofollow noopener" target="_blank">Åbn kommunens side</a></p></article></div><div class="table-wrap"><table><thead><tr><th>Skoleår</th><th>Ferie/fridag</th><th>Fra</th><th>Til</th></tr></thead><tbody>{rows}</tbody></table></div><p class="notice">Nogle skoler kan have lokale afvigelser, særlige lukkedage eller behovsåbent i SFO. Brug derfor siden som hurtigt overblik og verificer altid hos kommunen eller skolen.</p></div></section>'
    write_page(f"skoleferier-{m['slug']}.html", f"Skoleferier {m['name']} - ferieplan og fridage", f"Se skoleferier og fridage for {m['name']} kommune med kilde til den officielle ferieplan.", body, "skoleferier")


def render_about(start: int, end: int) -> None:
    body = hero("Om kalenderen og kilder", "Nationale helligdage beregnes med kendte kalenderregler, mens skoleferier opdateres efter kommunale kilder.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="grid"><article class="card"><h3>Periode</h3><p class="stat">{start}-{end}</p><p class="muted">Kalender-, helligdag- og arbejdsdagssider for hele perioden.</p></article><article class="card"><h3>Store bededag</h3><p class="stat">Ikke helligdag</p><p class="muted">Markeret historisk, men ikke talt som officiel helligdag efter 2024.</p></article></div><div class="card"><h2>Metode</h2><p>Påske beregnes med den gregorianske algoritme. Skærtorsdag, langfredag, Kristi himmelfartsdag og pinse beregnes relativt til påskedag. Arbejdsdage tæller mandag-fredag minus officielle helligdage.</p><p>Skoleferier ligger i <code>data/school-holidays.json</code> og skal revideres årligt mod de kommunale kilder.</p></div><div class="card"><h2>Kilder</h2><ul><li><a href="https://regeringen.dk/nyheder/2023/lovforslag-om-afskaffelse-store-bededag-er-vedtaget-i-folketinget/" rel="nofollow noopener" target="_blank">Regeringen: afskaffelse af store bededag</a></li><li><a href="https://natmus.dk/historisk-viden/temaer/fester-og-traditioner/store-bededag/" rel="nofollow noopener" target="_blank">Nationalmuseet: store bededag fra 2024</a></li><li><a href="https://www.oresunddirekt.dk/dk/jeg-arbejder-i-sverige/helligdag-og-ferie/helligdage-2026-i-danmark-og-sverige/" rel="nofollow noopener" target="_blank">Øresunddirekt: helligdage i Danmark</a></li><li><a href="skoleferier.html">Kommunale kilder til skoleferier</a></li></ul></div></div></section>"""
    write_page("om.html", "Om DanskeDage kalender - metode og kilder", f"Metode, kilder og vedligeholdelse for {SITE_NAME} kalender.", body)


def render_contact() -> None:
    subject_error = "Fejl%20paa%20DanskeDage.dk"
    subject_suggestion = "Forslag%20til%20DanskeDage.dk"
    body = hero("Kontakt DanskeDage.dk", "Har du fundet en fejl i en dato, en beregner eller en kilde? Skriv til os, så retter vi det hurtigst muligt.", date.today().year)
    body += f"""<section class="section"><div class="container--narrow"><article class="card prose"><h2>Skriv til os</h2><p>Send en e-mail til <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>. Vi bruger e-mailen til fejlrapporter, forslag til nye kalenderfunktioner og spørgsmål om kilderne på siden.</p><p><a class="btn btn--primary" href="mailto:{CONTACT_EMAIL}?subject={subject_error}">Rapportér en fejl</a> <a class="btn btn--ghost" href="mailto:{CONTACT_EMAIL}?subject={subject_suggestion}">Foreslå en forbedring</a></p><h2>Når du rapporterer en fejl</h2><p>Skriv gerne hvilken side det drejer sig om, hvilken dato eller beregning der ser forkert ud, og hvilken officiel kilde du sammenligner med. For skoleferier er det særligt nyttigt med link til kommunens egen ferieplan.</p><h2>Privatliv</h2><p>Hvis du kontakter os via e-mail, modtager vi den e-mailadresse og det indhold, du selv sender. Vi bruger det kun til at svare på henvendelsen.</p></article></div></section>"""
    write_page("kontakt.html", f"Kontakt - {SITE_NAME}", f"Kontakt {SITE_NAME}: rapportér fejl i kalender, helligdage, arbejdsdage eller skoleferier.", body)


def render_privacy_policy() -> None:
    body = hero("Privatlivspolitik", "Sådan håndterer DanskeDage.dk data, cookies, annoncer og eksterne links.", date.today().year)
    body += f"""<section class="section"><div class="container--narrow"><article class="card prose"><p class="muted">Sidst opdateret: {date.today().strftime('%Y-%m-%d')}.</p><h2>Kort fortalt</h2><p>{SITE_NAME} respekterer dit privatliv. De interaktive beregnere for arbejdsdage og ugenumre kører direkte i din browser. De datoer, du indtaster, bliver ikke sendt til vores server og bliver ikke gemt af os.</p><h2>Data i beregnerne</h2><p>Startdatoer, slutdatoer og antal arbejdsdage behandles lokalt med JavaScript på din enhed. Når du lukker eller genindlæser siden, forsvinder disse oplysninger fra beregneren.</p><h2>Serverlogfiler</h2><p>Som på andre hjemmesider kan hostingudbyderen registrere tekniske oplysninger såsom IP-adresse, browsertype, tidspunkt for besøg og forespurgte sider. Disse oplysninger bruges til drift, sikkerhed og fejlfinding.</p><h2>Cookies og annoncer</h2><p>Siden kan vise annoncer via Google AdSense for at finansiere drift og vedligeholdelse. Google og dets partnere kan bruge cookies til at vise og måle annoncer. Du kan læse mere om Googles brug af data på <a href="https://policies.google.com/technologies/partner-sites" rel="nofollow noopener" target="_blank">Googles side om partnerwebsteder</a> og ændre annonceindstillinger på <a href="https://www.google.com/settings/ads" rel="nofollow noopener" target="_blank">Googles annonceindstillinger</a>.</p><p>Vi bruger ikke login, betalingsmur eller egne analytics-cookies i kalenderberegnerne.</p><h2>Eksterne links</h2><p>Siden linker til officielle kilder og kommunale ferieplaner. Vi kontrollerer ikke disse eksterne sider og er ikke ansvarlige for deres indhold eller privatlivspraksis.</p><h2>Dine rettigheder</h2><p>Hvis du har spørgsmål om privatliv eller ønsker indsigt, rettelse eller sletning af oplysninger, du selv har sendt til os via e-mail, kan du kontakte os på <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>. Du kan også kontakte <a href="https://www.datatilsynet.dk/" rel="nofollow noopener" target="_blank">Datatilsynet</a>.</p><h2>Kontakt</h2><p>Spørgsmål om denne privatlivspolitik kan sendes til <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p></article></div></section>"""
    write_page("privatlivspolitik.html", f"Privatlivspolitik - {SITE_NAME}", f"Privatlivspolitik for {SITE_NAME}: data, cookies, annoncer og kontakt.", body)


def render_terms() -> None:
    body = hero("Vilkår", "Betingelser for brug af DanskeDage.dk og kalenderberegnerne.", date.today().year)
    body += f"""<section class="section"><div class="container--narrow"><article class="card prose"><p class="muted">Sidst opdateret: {date.today().strftime('%Y-%m-%d')}.</p><h2>1. Accept af vilkårene</h2><p>Når du bruger {SITE_NAME}, accepterer du disse vilkår. Hvis du ikke er enig, bør du lade være med at bruge siden.</p><h2>2. Informativt formål</h2><p>Siden tilbyder kalenderoplysninger, helligdage, arbejdsdage, ugenumre, skoleferier og relaterede beregnere med et udelukkende informativt formål. Oplysningerne erstatter ikke officiel rådgivning, kommunale afgørelser eller juridisk vurdering.</p><h2>3. Kilder og nøjagtighed</h2><p>Vi gør os umage for at beregne nationale helligdage korrekt og linke til relevante officielle og kommunale kilder. Skoleferier fastsættes lokalt og kan ændres, og enkelte skoler kan have afvigelser. Tjek derfor altid den officielle kilde, før du planlægger rejser, fravær eller arbejde.</p><h2>4. Ansvarsbegrænsning</h2><p>{SITE_NAME} stilles til rådighed som den er. Vi er ikke ansvarlige for tab, forsinkelser, fejlagtig planlægning eller andre konsekvenser, der måtte opstå ved brug af siden.</p><h2>5. Eksterne links og annoncer</h2><p>Siden kan indeholde links til tredjepartssider og vise annoncer via Google AdSense. Tredjepartssider har deres egne vilkår og privatlivspolitikker.</p><h2>6. Ændringer</h2><p>Vilkårene kan opdateres, når siden ændres, eller når regler og datakilder ændrer sig. Datoen øverst viser den aktuelle version.</p><h2>7. Kontakt</h2><p>Spørgsmål om vilkårene kan sendes til <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p></article></div></section>"""
    write_page("vilkar.html", f"Vilkår - {SITE_NAME}", f"Vilkår for brug af {SITE_NAME}, kalenderdata og beregnere.", body)


def render_support() -> None:
    qr = '<img class="donate-qr" src="img/bmc_qr.png" alt="QR-kode til Buy Me a Coffee" width="190" height="190" loading="lazy">' if (ROOT / "img" / "bmc_qr.png").exists() else ""
    body = hero("Støt projektet", "Hvis DanskeDage.dk hjælper dig, kan du støtte projektet via Buy Me a Coffee.", date.today().year)
    body += f"""<section class="section"><div class="container--narrow"><article class="card donate-card prose"><h2>Buy Me a Coffee</h2><p>Siden er gratis og uden login. Bidrag hjælper med domæne, hosting, årlige opdateringer og nye kalenderfunktioner.</p><p><a class="btn btn--primary" href="{BUY_ME_A_COFFEE}" target="_blank" rel="noopener">Støt på Buy Me a Coffee</a></p>{qr}</article><p class="muted" id="del">Du kan også hjælpe gratis ved at dele siden med andre, der søger danske datoer, helligdage eller arbejdsdage.</p></div></section>"""
    write_page("stot.html", f"Støt projektet - {SITE_NAME}", f"Støt {SITE_NAME} via Buy Me a Coffee og hjælp med at holde siden gratis.", body)


def generate(start: int, end: int) -> None:
    global ACTIVE_YEAR
    ensure_base_files()

    for old in ROOT.glob("*.html"):
        old.unlink()
    for old in ROOT.glob("*.xml"):
        old.unlink()

    current_year = min(max(date.today().year, start), end)
    ACTIVE_YEAR = current_year
    render_index(current_year)
    render_tools()
    render_school_holidays()
    render_about(start, end)
    render_contact()
    render_privacy_policy()
    render_terms()
    render_support()
    for year in range(start, end + 1):
        render_year_pages(year)
        write_calendar_json(year)
    write_sitemap(start, end)
    write_readme(start, end)


def write_calendar_json(year: int) -> None:
    data = {
        "year": year,
        "stats": year_stats(year),
        "holidays": [
            {
                "date": iso(m.date),
                "name": m.name,
                "kind": m.kind,
                "official": m.official,
                "note": m.note,
            }
            for m in all_marks(year)
        ],
        "best_vacation_windows": [
            {
                "start": iso(x["start"]),
                "end": iso(x["end"]),
                "days_off": x["days_off"],
                "vacation_days": x["vacation_days"],
                "ratio": round(x["ratio"], 2),
                "holidays": x["holidays"],
            }
            for x in build_best_vacation_windows(year)
        ],
    }
    (DATA_DIR / f"calendar-{year}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_sitemap(start: int, end: int) -> None:
    urls = ["", "beregn-arbejdsdage.html", "laeg-arbejdsdage-til.html", "ugenummer.html", "skoleferier.html", "om.html", "kontakt.html", "privatlivspolitik.html", "vilkar.html", "stot.html"]
    school_file = DATA_DIR / "school-holidays.json"
    if school_file.exists():
        school_data = json.loads(school_file.read_text(encoding="utf-8-sig"))
        urls.extend(f"skoleferier-{m['slug']}.html" for m in school_data.get("municipalities", []))
    for year in range(start, end + 1):
        urls.extend(
            [
                f"kalender-{year}.html",
                f"helligdage-{year}.html",
                f"arbejdsdage-{year}.html",
                f"paaske-{year}.html",
                f"pinse-{year}.html",
                f"kristi-himmelfartsdag-{year}.html",
                f"bedste-feriedage-{year}.html",
            ]
        )
    today = date.today().isoformat()
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        loc = DOMAIN + ("/" if not u else f"/{u}")
        priority = "1.0" if not u else ("0.8" if any(k in u for k in ["kalender", "helligdage", "arbejdsdage"]) else "0.6")
        body.append(f"<url><loc>{loc}</loc><lastmod>{today}</lastmod><changefreq>yearly</changefreq><priority>{priority}</priority></url>")
    body.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(body) + "\n", encoding="utf-8")


def write_readme(start: int, end: int) -> None:
    text = f"""# DanskeDage Kalender

Static Danish calendar site generated from `tools/generate_site.py`.

Generated range: {start}-{end}

## Generate

```powershell
python .\\tools\\generate_site.py --start {start} --end {end}
```

## Validate

```powershell
python .\\tools\\validate_site.py --start {start} --end {end}
```

## Annual cron/review

```powershell
python .\\tools\\annual_review.py
```

The annual review regenerates pages, validates internal links, checks expected files/data, and prints the human-review checklist. By default it keeps at least 15 future years generated, while never generating less than {end}.

- confirm no public-holiday law changed;
- review `data/school-holidays.json` against municipal sources;
- update `lastmod` and sitemap;
- review AdSense slots if you add manual units.

## Pages included

- calendar, public-holiday, workday, Easter, Pentecost, Ascension and vacation-planning pages for each generated year;
- business-day calculators and ISO week-number calculator;
- school-holiday overview plus municipality pages based on `data/school-holidays.json`.
- trust/legal pages for AdSense review: about, contact, privacy policy, terms and support.

## Publish

The folder is plain HTML/CSS/JS. It can be published directly as a static site.
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2026)
    parser.add_argument("--end", type=int, default=2050)
    args = parser.parse_args()
    if args.end < args.start:
        raise SystemExit("--end must be >= --start")
    generate(args.start, args.end)
    print(f"Generated DanskeDage calendar site from {args.start} to {args.end} in {ROOT}")


if __name__ == "__main__":
    main()
