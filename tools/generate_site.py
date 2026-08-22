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
import struct
import zlib
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


DANSK_MDR_LANG = ["januar", "februar", "marts", "april", "maj", "juni",
                  "juli", "august", "september", "oktober", "november", "december"]


def _classify_easter_position(e: date) -> str:
    """Klassificer påskens placering: 'tidligt', 'gennemsnitligt' eller 'sent'.

    Meeus-spændet er 22. marts (dag 81/82) til 25. april (dag 115/116). Vi
    deler i tre lige store bånd."""
    doy = e.timetuple().tm_yday
    if doy <= 92:
        return "tidligt"
    if doy >= 107:
        return "sent"
    return "gennemsnitligt"


def _fmt_dansk_dato(d: date) -> str:
    """1. januar / 25. maj-format."""
    return f"{d.day}. {DANSK_MDR_LANG[d.month - 1]}"


def _fmt_dansk_dato_aar(d: date) -> str:
    return f"{_fmt_dansk_dato(d)} {d.year}"


def easter_year_context(year: int) -> dict:
    """Beregner påskedato-metrikker og sammenligninger med naboår."""
    e = easter_sunday(year)
    e_prev = easter_sunday(year - 1)
    e_next = easter_sunday(year + 1)
    doy = e.timetuple().tm_yday
    doy_prev = e_prev.timetuple().tm_yday
    doy_next = e_next.timetuple().tm_yday
    return {
        "date": e,
        "day_of_year": doy,
        "position": _classify_easter_position(e),
        "prev_year": year - 1,
        "next_year": year + 1,
        "prev_date": e_prev,
        "next_date": e_next,
        "delta_prev_days": doy - doy_prev,
        "delta_next_days": doy_next - doy,
    }


def _weekend_holidays_in_year(year: int) -> int:
    """Antal officielle helligdage der falder på lørdag/søndag i året."""
    return sum(
        1
        for m in all_marks(year)
        if m.official and m.date.weekday() >= 5
    )


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


def cookie_consent_js_text() -> str:
    """Cookie consent banner + Google Consent Mode v2 (see js/cookie-consent.js)."""
    return r'''/* danskedage.dk — cookie consent banner + Google Consent Mode v2 (GDPR)
 * Standalone, no dependencies. Stores choice in localStorage as 'dd-consent' = 'granted' | 'denied'.
 */
(function () {
  'use strict';
  var KEY = 'dd-consent';

  /* Google Consent Mode v2: default everything to denied BEFORE any consent decision. */
  window.dataLayer = window.dataLayer || [];
  function gtag() { dataLayer.push(arguments); }
  gtag('consent', 'default', {
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
    analytics_storage: 'denied'
  });

  function grantAll() {
    gtag('consent', 'update', {
      ad_storage: 'granted',
      ad_user_data: 'granted',
      ad_personalization: 'granted'
    });
  }

  function read() {
    try { return localStorage.getItem(KEY); } catch (_) { return null; }
  }
  function write(v) {
    try { localStorage.setItem(KEY, v); } catch (_) {}
  }

  var stored = read();
  if (stored === 'granted') grantAll();

  var CSS = [
    '.cookie-banner{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;',
    'background:var(--c-surface,var(--c-cream-2,#ffffff));color:var(--c-text,#23262d);',
    'border-top:1px solid var(--c-line,#d8dbe2);box-shadow:0 -4px 18px rgba(0,0,0,.12);',
    'padding:14px 16px;font-size:.95rem;line-height:1.45}',
    '.cookie-banner.is-hidden{opacity:0;transform:translateY(8px);transition:opacity .2s ease,transform .2s ease}',
    '.cookie-banner__inner{max-width:960px;margin:0 auto;display:flex;flex-direction:column;gap:10px}',
    '@media (min-width:640px){.cookie-banner__inner{flex-direction:row;align-items:center}}',
    '.cookie-banner__text{margin:0;flex:1}',
    '.cookie-banner__text a{color:inherit;text-decoration:underline}',
    '.cookie-banner__actions{display:flex;gap:8px;flex-shrink:0}',
    '.cookie-banner .cc-btn{cursor:pointer;font:inherit;font-weight:600;border-radius:8px;',
    'padding:8px 16px;border:1px solid var(--c-primary,var(--c-ink,#1f2937))}',
    '.cookie-banner .cc-btn--primary{background:var(--c-primary,var(--c-ink,#1f2937));color:#fff}',
    '.cookie-banner .cc-btn--ghost{background:transparent;color:var(--c-text,#23262d);',
    'border-color:var(--c-line,#9aa1ad)}'
  ].join('');

  function buildBanner() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var wrap = document.createElement('div');
    wrap.className = 'cookie-banner';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-label', 'Cookieindstillinger');
    wrap.innerHTML = [
      '<div class="cookie-banner__inner">',
      '  <p class="cookie-banner__text">Vi bruger cookies til annoncer (Google AdSense) og til at forbedre sitet. Læs mere i vores ',
      '  <a href="/privatlivspolitik.html">privatlivspolitik</a>.</p>',
      '  <div class="cookie-banner__actions">',
      '    <button type="button" class="cc-btn cc-btn--ghost" data-cookie="deny">Afvis</button>',
      '    <button type="button" class="cc-btn cc-btn--primary" data-cookie="grant">Accepter</button>',
      '  </div>',
      '</div>'
    ].join('');
    return wrap;
  }

  function init() {
    if (read() === 'granted' || read() === 'denied') return;
    var banner = buildBanner();
    document.body.appendChild(banner);

    banner.addEventListener('click', function (e) {
      var t = e.target.closest('[data-cookie]');
      if (!t) return;
      var action = t.getAttribute('data-cookie');
      write(action === 'grant' ? 'granted' : 'denied');
      if (action === 'grant') grantAll();
      banner.classList.add('is-hidden');
      setTimeout(function () { banner.remove(); }, 250);
      document.dispatchEvent(new CustomEvent('dd:consent', { detail: { value: action } }));
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.CookieConsent = { read: read };
})();
'''


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
    (ROOT / "js" / "today.js").write_text(today_js_text(), encoding="utf-8")
    (ROOT / "js" / "cookie-consent.js").write_text(cookie_consent_js_text(), encoding="utf-8")
    (ROOT / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
    write_png_icon(ROOT / "favicon-16.png", 16)
    write_png_icon(ROOT / "favicon-32.png", 32)
    write_png_icon(ROOT / "favicon-48.png", 48)
    write_png_icon(ROOT / "favicon-192.png", 192)
    write_png_icon(ROOT / "favicon-512.png", 512)
    write_png_icon(ROOT / "apple-touch-icon.png", 180)
    write_og_image(ROOT / "img" / "og-default.png")
    (ROOT / "site.webmanifest").write_text(site_manifest(), encoding="utf-8")
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
:root{--bg:#f7f7f4;--paper:#fdfdfb;--ink:#1c1917;--muted:#585852;--line:#d7d6cd;--brand:#c8102e;--brand-dark:#a30d26;--brand2:#1d4ed8;--accent:#b45309;--soft:#f7ecee;--danger:#c8102e;--hol:#c8102e;--hol-bg:#fae8ea;--sp-ink:#8a4b09;--sp-bg:#f6efdd;--wk-ink:#5b6472;--wk-bg:#eef0f3;--serif:Georgia,'Times New Roman',serif;--sans:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;--radius:2px;--shadow:2px 2px 0 rgba(28,25,23,.9)}
*{box-sizing:border-box}html{font-family:var(--sans);color:var(--ink);background:var(--bg);line-height:1.55}body{margin:0}h1,h2,h3,h4{font-family:var(--serif);letter-spacing:-.005em}a{color:var(--brand-dark)}a:hover{color:#7c0a1d}.skip-link{position:absolute;left:-999px}.skip-link:focus{left:1rem;top:1rem;background:var(--paper);padding:.6rem 1rem;border:2px solid var(--brand);z-index:99}.container{width:min(1120px,calc(100% - 32px));margin-inline:auto}.container--narrow{width:min(820px,calc(100% - 32px));margin-inline:auto}
.site-header{background:var(--paper);border-top:4px solid var(--brand);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}.site-header__inner{display:flex;align-items:center;gap:1rem;justify-content:space-between;min-height:64px}.brand{display:flex;align-items:center;gap:.6rem;text-decoration:none;color:var(--ink)}.brand span{font-family:var(--serif);font-weight:700;font-size:1.18rem;letter-spacing:.01em}.brand__mark{width:34px;height:34px}.brand--footer{color:#fff}
.main-nav ul{list-style:none;margin:0;padding:0;display:flex;gap:.15rem;flex-wrap:wrap}.main-nav a{display:block;text-decoration:none;color:var(--muted);padding:.62rem .55rem .5rem;border-radius:0;border-bottom:2px solid transparent;font-weight:700;font-size:.78rem;text-transform:uppercase;letter-spacing:.07em}.main-nav a[aria-current=page],.main-nav a:hover{background:transparent;color:var(--ink);border-bottom-color:var(--brand)}
.hero{padding:2.6rem 0 1.9rem;background:var(--bg);border-bottom:1px solid var(--line)}.hero-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(280px,.95fr);gap:2rem;align-items:start}.eyebrow{font-size:.74rem;text-transform:uppercase;letter-spacing:.14em;color:var(--brand-dark);font-weight:800}.hero h1{font-size:clamp(2rem,5vw,3.9rem);line-height:1.04;margin:.4rem 0 1rem}.lead{font-size:1.1rem;color:#41403a;max-width:68ch}.hero-actions{display:flex;gap:.7rem;flex-wrap:wrap;margin-top:1.3rem}
.btn{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;border-radius:0;padding:.68rem 1.05rem;font-weight:700;border:1px solid var(--ink);background:var(--paper);color:var(--ink)}.btn--primary{background:var(--brand);border-color:var(--brand);color:#fff}.btn--primary:hover{background:var(--brand-dark);color:#fff}.btn--ghost{border-color:var(--ink);background:var(--paper);color:var(--ink)}
.quick-panel{background:var(--paper);border:1px solid var(--ink);border-radius:0;box-shadow:none;padding:1rem}.quick-panel h2{margin:-1rem -1rem .85rem;background:var(--brand);color:#fdf6f2;font-family:var(--serif);font-weight:700;font-size:1rem;text-align:center;text-transform:uppercase;letter-spacing:.12em;padding:.62rem .5rem}.quick-panel::after{content:"";display:block;margin:1.1rem -1rem -1rem;border-top:2px dashed var(--line);padding-bottom:.5rem}
.mini-calendar{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:var(--line);border:1px solid var(--line)}.mini-calendar span{display:flex;align-items:center;justify-content:center;min-height:34px;border-radius:0;background:var(--paper);font-size:.88rem;font-family:var(--serif);font-weight:600;font-variant-numeric:tabular-nums}.mini-calendar .head{background:var(--bg);color:var(--muted);font-family:var(--sans);font-weight:700;font-size:.66rem;text-transform:uppercase;letter-spacing:.08em}.mini-calendar .empty{background:var(--bg)}.mini-calendar .weekend{background:var(--wk-bg);color:var(--wk-ink)}.mini-calendar .holiday{background:var(--hol-bg);color:var(--hol);font-weight:800}.mini-calendar .special{background:var(--sp-bg);color:var(--sp-ink)}.mini-calendar .today{background:var(--ink);color:var(--bg);font-weight:800;outline:none}
.quick-panel__holidays{margin-top:.85rem}.quick-panel__holidays h3{margin:0 0 .3rem;font-family:var(--sans);font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}.quick-panel__holidays ul{list-style:none;margin:0;padding:0}.quick-panel__holidays li{display:flex;gap:.55rem;padding:.3rem 0;border-top:1px solid var(--line);font-size:.88rem}.quick-panel__holidays li strong{font-variant-numeric:tabular-nums;color:var(--hol)}.quick-panel__nohol{font-size:.86rem;margin:.85rem 0 0}
.section{padding:2.1rem 0}.section-title{display:flex;align-items:end;justify-content:space-between;gap:1rem;margin-bottom:1.05rem;border-top:3px double var(--ink);padding-top:.75rem}.section-title h2{margin:0;font-size:1.5rem}.section-title h2::before{content:"";display:inline-block;width:.5em;height:.5em;background:var(--brand);margin-right:.5rem}.section-title p{margin:.2rem 0 0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}.card{background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:1rem;box-shadow:none}a.card{text-decoration:none;color:inherit}a.card:hover{border-color:var(--ink);box-shadow:3px 3px 0 var(--line)}.card h3{margin:.1rem 0 .4rem}.stat{font-family:var(--serif);font-size:2.1rem;font-weight:700;color:var(--brand-dark);margin:.2rem 0;font-variant-numeric:tabular-nums}.muted{color:var(--muted)}.muted-on-dark{color:#b3b0a7}
.prose{font-size:1.03rem}.prose h2{margin-top:1.8rem}.prose p,.prose li{color:#3c3b35}.prose li{margin:.35rem 0}
.table-wrap{overflow-x:auto;background:var(--paper);border:1px solid var(--line);border-radius:0}table{border-collapse:collapse;width:100%;min-width:640px}th,td{padding:.68rem .8rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}td{font-variant-numeric:tabular-nums}th{background:var(--paper);color:var(--ink);font-size:.74rem;text-transform:uppercase;letter-spacing:.08em;border-bottom:3px double var(--ink)}
.month-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:1rem}.month{background:var(--paper);border:1px solid var(--line);border-radius:0;padding:.85rem}.month--large{max-width:760px;margin:auto;border:1px solid var(--ink)}.month h3{margin:0 0 .65rem;text-align:center;text-transform:uppercase;letter-spacing:.12em;font-size:.98rem;border-bottom:3px double var(--ink);padding-bottom:.5rem}.month h3 a{color:inherit;text-decoration:none}
.calendar-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:var(--line);border:1px solid var(--line)}.calendar-grid span{min-height:32px;display:flex;align-items:center;justify-content:center;border-radius:0;background:var(--paper);font-size:.92rem;font-family:var(--serif);font-weight:600;font-variant-numeric:tabular-nums}.month--large .calendar-grid span{min-height:54px;font-size:1.18rem}.calendar-grid .head{font-family:var(--sans);font-weight:700;background:var(--bg);color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.08em}.calendar-grid .empty{background:var(--bg)}.calendar-grid .weekend{background:var(--wk-bg);color:var(--wk-ink)}.calendar-grid .holiday{background:var(--hol-bg);color:var(--hol);font-weight:800}.calendar-grid .special{background:var(--sp-bg);color:var(--sp-ink)}
.tool{background:var(--paper);border:1px solid var(--line);border-top:3px double var(--ink);border-radius:0;padding:1.05rem;box-shadow:none}.tool-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.8rem}.field label{display:block;font-weight:700;margin-bottom:.25rem}.field input,.field select{width:100%;padding:.66rem .75rem;border:1px solid #85837a;border-radius:0;font:inherit;background:#fff;color:var(--ink)}
.result-box{margin-top:1rem;background:#f4f4ef;border:1px solid var(--ink);border-left:4px solid var(--brand);border-radius:0;padding:1rem}.notice{background:#faf3dd;border:1px solid #d9c58a;border-radius:0;padding:1rem;color:#6b4d10}
.donate-card{text-align:center}.donate-qr{display:block;max-width:190px;height:auto;margin:1rem auto 0;border:1px solid var(--line);border-radius:0}
.footer{margin-top:2rem;padding:2rem 0;background:var(--ink);color:#e7e5de;border-top:4px solid var(--brand)}.footer a{color:#f0eee7}.footer h3{font-size:.92rem;text-transform:uppercase;letter-spacing:.12em;color:#f7f5ef}.footer-grid{display:grid;grid-template-columns:2fr repeat(3,1fr);gap:1rem}.footer ul{list-style:none;padding:0;margin:.4rem 0}.footer li{margin:.25rem 0}
.ad-note{min-height:90px;border:1px dashed var(--line);border-radius:0;display:flex;align-items:center;justify-content:center;color:var(--muted);background:var(--paper)}
.tag{display:inline-flex;padding:.16rem .45rem;border-radius:0;background:var(--soft);color:var(--brand-dark);font-size:.76rem;font-weight:800;letter-spacing:.02em}
.nav-toggle{display:none;background:transparent;border:1px solid var(--ink);border-radius:0;padding:.45rem .6rem;cursor:pointer;color:var(--ink);font:inherit}.nav-toggle__bars{display:inline-flex;flex-direction:column;gap:4px;width:20px;vertical-align:middle}.nav-toggle__bars span{display:block;height:2px;background:currentColor;border-radius:0}
@media(max-width:780px){.hero-grid{grid-template-columns:1fr}.footer-grid{grid-template-columns:1fr}.section-title{display:block}.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}table{min-width:520px}.main-nav a{font-size:.86rem;padding:.45rem}.nav-toggle{display:inline-flex;align-items:center;gap:.4rem;font-weight:700}.main-nav{display:none;flex-basis:100%;order:3}.main-nav.is-open{display:block}.main-nav ul{flex-direction:column;gap:0;padding:.4rem 0}.main-nav a{display:block;width:100%;font-size:.95rem;padding:.6rem .3rem;border-bottom:1px solid var(--line)}.main-nav a[aria-current=page]{border-bottom:1px solid var(--line);background:var(--soft);color:var(--ink)}.site-header__inner{flex-wrap:wrap}.hero{padding:1.6rem 0 1.2rem}.hero h1{font-size:clamp(1.7rem,7vw,2.4rem)}.hero+.ad-slot--header{display:none}.hero+.ad-slot--header+.section{padding-top:1rem}.calendar-grid span{min-height:44px;font-size:1rem}.month--large .calendar-grid span{min-height:46px;font-size:1.05rem}.mini-calendar span{min-height:40px}.calendar-legend{padding:.6rem .7rem;gap:.45rem .7rem}.calendar-legend__item{font-size:.84rem}}
.calendar-grid .today{background:var(--ink);color:var(--bg);font-weight:800;outline:none}.calendar-legend{display:flex;flex-wrap:wrap;gap:.55rem .85rem;align-items:center;margin:0 0 1rem;padding:.7rem .85rem;background:var(--paper);border:1px solid var(--line);border-radius:0}.month--large .calendar-legend{margin-top:.35rem}.calendar-legend__item{display:inline-flex;align-items:center;gap:.4rem;color:#47463f;font-size:.88rem;font-weight:600}.calendar-legend__swatch{width:16px;height:16px;border-radius:0;border:1px solid var(--line);display:inline-block}.calendar-legend__swatch--holiday{background:var(--hol-bg);border-color:var(--hol)}.calendar-legend__swatch--special{background:var(--sp-bg);border-color:#c78a3b}.calendar-legend__swatch--weekend{background:var(--wk-bg);border-color:#c3cad4}.calendar-legend__swatch--today{background:var(--ink);border-color:var(--ink)}
.quick-panel .calendar-legend{margin:.75rem 0 0;padding:.55rem 0;gap:.4rem .65rem;border:0;background:transparent}.quick-panel .calendar-legend__item{font-size:.76rem}.quick-panel .calendar-legend__swatch{width:12px;height:12px;border-radius:0}
.breadcrumbs{background:var(--paper);border-bottom:1px solid var(--line);padding:.65rem 0;font-size:.88rem;color:var(--muted);margin:0}.breadcrumbs a{color:var(--brand-dark);text-decoration:none;font-weight:700}.breadcrumbs a:hover{text-decoration:underline}.breadcrumbs [aria-current=page]{color:var(--ink);font-weight:700}
.ad-slot{padding:.9rem 0;background:transparent}.ad-slot ins{min-height:90px;display:block;border:1px dashed var(--line);border-radius:0;background:var(--paper);color:var(--muted)}.ad-slot ins:empty::before{content:"Annonceområde";display:flex;align-items:center;justify-content:center;height:90px;color:var(--muted);font-size:.85rem;letter-spacing:.04em}.ad-slot--header ins{min-height:100px}.ad-slot--mid ins{min-height:250px}.ad-slot--footer ins{min-height:100px}
.faq{display:flex;flex-direction:column;gap:.6rem}.faq__item{background:var(--paper);border:1px solid var(--line);border-radius:0;padding:.75rem 1rem}.faq__item summary{cursor:pointer;font-weight:700;color:var(--brand-dark);outline:none}.faq__item[open] summary{margin-bottom:.5rem}.faq__item p{margin:.25rem 0 0;color:#3c3b35}
.add-cell{font-size:.84rem;white-space:nowrap}.add-cell a{color:var(--brand-dark);text-decoration:none;font-weight:700}.add-cell a:hover{text-decoration:underline}.export-bar{margin:0 0 1rem;display:flex;align-items:center;gap:.65rem;flex-wrap:wrap}.export-bar .btn{padding:.45rem .9rem;font-size:.92rem}
.field input:focus-visible,.field select:focus-visible,.btn:focus-visible,.main-nav a:focus-visible,a.card:focus-visible,.breadcrumbs a:focus-visible,.faq__item summary:focus-visible{outline:2px solid var(--ink);outline-offset:2px;border-radius:0}
.hero h1{text-wrap:balance}
.btn{cursor:pointer;font:inherit;font-weight:700;transition:background-color .12s ease,border-color .12s ease,box-shadow .12s ease,transform .12s ease}.btn:hover{transform:translate(1px,1px);box-shadow:var(--shadow)}.btn--ghost:hover{background:var(--bg);border-color:var(--ink)}
.card{transition:border-color .12s ease,box-shadow .12s ease}
.calendar-grid span,.mini-calendar span{transition:background-color .12s ease,box-shadow .12s ease}.calendar-grid span[title],.mini-calendar span[title]{cursor:help}.calendar-grid span[title]:hover,.mini-calendar span[title]:hover{box-shadow:inset 0 0 0 2px rgba(28,25,23,.45)}
.calendar-grid .today,.mini-calendar .today{background:var(--ink);color:var(--bg);font-weight:800;outline:none}
tbody tr:nth-child(even) td{background:#f2f2ec}tbody tr:hover td{background:#ecece4}
@media print{.site-header,.main-nav,.footer,.ad-slot,.no-print,.hero-actions,.faq,.export-bar,.add-cell,.skip-link,.breadcrumbs{display:none!important}body{background:#fff;color:#000;font-size:11pt}.section{padding:.4rem 0}.container{width:100%}.hero{padding:0;background:#fff;border:0}.hero h1{font-size:1.4rem}.lead{font-size:1rem;color:#222}.table-wrap{border:0;overflow:visible}table{min-width:0;font-size:10pt}th{background:#eee;color:#000}th:last-child,td:last-child{display:none}.card{break-inside:avoid;box-shadow:none;border-color:#aaa}.notice{background:#fff;border-color:#bbb;color:#000}a{color:#000;text-decoration:none}a[href]:after{content:""}.month-grid{grid-template-columns:repeat(3,1fr);gap:.5rem;page-break-inside:auto}.month{break-inside:avoid;padding:.4rem}}
"""


def js_text() -> str:
    return """\
(function(){
  function easter(y){var a=y%19,b=Math.floor(y/100),c=y%100,d=Math.floor(b/4),e=b%4,f=Math.floor((b+8)/25),g=Math.floor((b-f+1)/3),h=(19*a+b-d-g+15)%30,i=Math.floor(c/4),k=c%4,l=(32+2*e+2*i-h-k)%7,m=Math.floor((a+11*h+22*l)/451),mo=Math.floor((h+l-7*m+114)/31),da=((h+l-7*m+114)%31)+1;return new Date(Date.UTC(y,mo-1,da));}
  function addDays(d,n){var x=new Date(d.getTime());x.setUTCDate(x.getUTCDate()+n);return x;}
  function iso(d){return d.toISOString().slice(0,10);}
  var MONTHS_DK=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december'];
  function fmtDK(d){return d.getUTCDate()+'. '+MONTHS_DK[d.getUTCMonth()]+' '+d.getUTCFullYear();}
  function holidays(y){var e=easter(y),out=[];function push(d,n){out.push([iso(d),n]);}push(new Date(Date.UTC(y,0,1)),'Nytårsdag');push(addDays(e,-3),'Skærtorsdag');push(addDays(e,-2),'Langfredag');push(e,'Påskedag');push(addDays(e,1),'2. påskedag');push(addDays(e,39),'Kristi himmelfartsdag');push(addDays(e,49),'Pinsedag');push(addDays(e,50),'2. pinsedag');push(new Date(Date.UTC(y,11,25)),'Juledag');push(new Date(Date.UTC(y,11,26)),'2. juledag');return new Map(out);}
  function optional(y){return new Set([iso(new Date(Date.UTC(y,4,1))),iso(new Date(Date.UTC(y,5,5))),iso(new Date(Date.UTC(y,11,24))),iso(new Date(Date.UTC(y,11,31)))]);}
  function parse(s){var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}
  function isWorkday(d,includeOffice){var wd=d.getUTCDay();if(wd===0||wd===6)return false;var id=iso(d);if(holidays(d.getUTCFullYear()).has(id))return false;if(includeOffice&&optional(d.getUTCFullYear()).has(id))return false;return true;}
  function fmt(n){return new Intl.NumberFormat('da-DK').format(n);}
  function between(){var start=document.getElementById('bd-start'),end=document.getElementById('bd-end'),mode=document.getElementById('bd-mode'),out=document.getElementById('bd-result');if(!start||!end||!out)return;var a=parse(start.value),b=parse(end.value);if(isNaN(a)||isNaN(b)||b<a){out.innerHTML='Vælg en gyldig start- og slutdato.';return;}var incl=mode.value==='office',days=0,total=0,hol=[];for(var d=a;d<=b;d=addDays(d,1)){total++;if(isWorkday(d,incl))days++;var h=holidays(d.getUTCFullYear()).get(iso(d));if(h)hol.push(h+' ('+fmtDK(d)+')');}out.innerHTML='<strong>'+fmt(days)+' arbejdsdage</strong><br><span>'+fmt(total)+' kalenderdage i perioden.</span>'+(hol.length?'<br><small>Helligdage i perioden: '+hol.join(', ')+'</small>':'');}
  function addBusiness(){var start=document.getElementById('add-start'),amount=document.getElementById('add-amount'),mode=document.getElementById('add-mode'),out=document.getElementById('add-result');if(!start||!amount||!out)return;var d=parse(start.value),n=parseInt(amount.value,10)||0,incl=mode.value==='office';if(isNaN(d)||n<0){out.innerHTML='Vælg en gyldig dato og antal dage.';return;}var left=n;while(left>0){d=addDays(d,1);if(isWorkday(d,incl))left--;}out.innerHTML='<strong>'+fmtDK(d)+'</strong><br><span>'+d.toLocaleDateString('da-DK',{weekday:'long',timeZone:'UTC'})+'</span>';}
  function weekNumber(){var input=document.getElementById('week-date'),out=document.getElementById('week-result');if(!input||!out)return;var d=parse(input.value);if(isNaN(d)){out.innerHTML='Vælg en dato.';return;}var tmp=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()));var day=tmp.getUTCDay()||7;tmp.setUTCDate(tmp.getUTCDate()+4-day);var yStart=new Date(Date.UTC(tmp.getUTCFullYear(),0,1));var week=Math.ceil((((tmp-yStart)/86400000)+1)/7);out.innerHTML='<strong>Uge '+week+'</strong><br><span>'+fmtDK(d)+' ligger i ISO-uge '+week+'.</span>';}
  document.addEventListener('input',between);document.addEventListener('change',between);document.addEventListener('input',addBusiness);document.addEventListener('change',addBusiness);document.addEventListener('input',weekNumber);document.addEventListener('change',weekNumber);between();addBusiness();weekNumber();
})();
"""


def favicon_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#0f766e"/><rect x="12" y="15" width="40" height="37" rx="5" fill="#fff"/><rect x="12" y="15" width="40" height="10" rx="5" fill="#134e4a"/><path d="M22 34h7v7h-7zm13 0h7v7h-7z" fill="#0f766e"/></svg>"""


def write_png_icon(path: Path, size: int) -> None:
    """Write the site calendar mark as a square PNG without external deps."""

    teal = (15, 118, 110, 255)
    dark = (19, 78, 74, 255)
    white = (255, 255, 255, 255)

    def px(value: float) -> int:
        return round(value * size / 64)

    pixels = [[teal for _ in range(size)] for _ in range(size)]

    def fill_rect(x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int, int]) -> None:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(size, x2), min(size, y2)
        for y in range(y1, y2):
            row = pixels[y]
            for x in range(x1, x2):
                row[x] = color

    fill_rect(px(12), px(15), px(52), px(52), white)
    fill_rect(px(12), px(15), px(52), px(25), dark)
    fill_rect(px(22), px(34), px(29), px(41), teal)
    fill_rect(px(35), px(34), px(42), px(41), teal)

    raw = b"".join(b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in pixels)

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def site_manifest() -> str:
    return json.dumps(
        {
            "name": SITE_NAME,
            "short_name": "DanskeDage",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#f7f7f2",
            "theme_color": "#0f766e",
            "icons": [
                {"src": "/favicon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/favicon-512.png", "sizes": "512x512", "type": "image/png"},
                {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
            ],
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def today_js_text() -> str:
    return """\
(function(){
  function pad(n){return n<10?'0'+n:''+n;}
  var now=new Date();
  var iso=now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate());

  // --- Quick-panel mini-kalender: hvis det udgivne HTML viser en tidligere
  // maaned (gammelt build), genopbygges gridden client-side for den aktuelle
  // maaned. Helligdage beregnes med paaske-algoritmen (som calendar-tools.js).
  function easterSunday(y){
    var a=y%19,b=Math.floor(y/100),c=y%100,d=Math.floor(b/4),e=b%4,
        f=Math.floor((b+8)/25),g=Math.floor((b-f+1)/3),
        h=(19*a+b-d-g+15)%30,i=Math.floor(c/4),k=c%4,
        l=(32+2*e+2*i-h-k)%7,m=Math.floor((a+11*h+22*l)/451),
        mo=Math.floor((h+l-7*m+114)/31),da=((h+l-7*m+114)%31)+1;
    return new Date(Date.UTC(y,mo-1,da));
  }
  function addD(dt,n){return new Date(dt.getTime()+n*86400000);}
  function isoOf(dt){return dt.getUTCFullYear()+'-'+pad(dt.getUTCMonth()+1)+'-'+pad(dt.getUTCDate());}
  function marksFor(y){
    var e=easterSunday(y),out={};
    function put(dt,name,official){out[isoOf(dt)]={n:name,o:official};}
    put(new Date(Date.UTC(y,0,1)),'Nyt\\u00e5rsdag',true);
    put(addD(e,-7),'Palmes\\u00f8ndag',false);
    put(addD(e,-3),'Sk\\u00e6rtorsdag',true);
    put(addD(e,-2),'Langfredag',true);
    put(e,'P\\u00e5skedag',true);
    put(addD(e,1),'2. p\\u00e5skedag',true);
    put(addD(e,39),'Kristi himmelfartsdag',true);
    put(addD(e,49),'Pinsedag',true);
    put(addD(e,50),'2. pinsedag',true);
    put(new Date(Date.UTC(y,4,1)),'Arbejdernes kampdag',false);
    put(new Date(Date.UTC(y,5,5)),'Grundlovsdag',false);
    put(new Date(Date.UTC(y,11,24)),'Juleaftensdag',false);
    put(new Date(Date.UTC(y,11,25)),'Juledag',true);
    put(new Date(Date.UTC(y,11,26)),'2. juledag',true);
    put(new Date(Date.UTC(y,11,31)),'Nyt\\u00e5rsaftensdag',false);
    return out;
  }
  function rebuildMiniCalendar(){
    var panel=document.querySelector('.quick-panel[data-auto-month]');
    if(!panel)return;
    var grid=panel.querySelector('.mini-calendar');
    if(!grid)return;
    var first=grid.querySelector('[data-date]');
    if(!first)return;
    if(first.getAttribute('data-date').slice(0,7)===iso.slice(0,7))return;
    var y=now.getFullYear(),m=now.getMonth();
    var marks=marksFor(y);
    var MDR=['Januar','Februar','Marts','April','Maj','Juni','Juli','August','September','Oktober','November','December'];
    var h2=panel.querySelector('h2');
    if(h2)h2.textContent=MDR[m]+' '+y;
    var spans=grid.querySelectorAll('span:not(.head)');
    for(var k=0;k<spans.length;k++)grid.removeChild(spans[k]);
    var lead=(new Date(Date.UTC(y,m,1)).getUTCDay()+6)%7; // man=0
    var dim=new Date(Date.UTC(y,m+1,0)).getUTCDate();
    var frag=document.createDocumentFragment();
    function span(cls,txt,dateIso,title){
      var s=document.createElement('span');
      if(cls)s.className=cls;
      if(dateIso)s.setAttribute('data-date',dateIso);
      if(title)s.title=title;
      s.textContent=txt||'';
      return s;
    }
    for(var a=0;a<lead;a++)frag.appendChild(span('empty',''));
    for(var d=1;d<=dim;d++){
      var di=y+'-'+pad(m+1)+'-'+pad(d);
      var wd=(lead+d-1)%7;
      var cls=[];
      if(wd>=5)cls.push('weekend');
      var mk=marks[di];
      if(mk&&mk.o)cls.push('holiday');
      else if(mk)cls.push('special');
      frag.appendChild(span(cls.join(' '),String(d),di,mk?mk.n:null));
    }
    var tail=(lead+dim)%7;
    if(tail)for(var b=tail;b<7;b++)frag.appendChild(span('empty',''));
    grid.appendChild(frag);
    // "Helligdage denne maaned"-listen
    var official=[];
    for(var key in marks){
      if(marks[key].o&&key.slice(0,7)===iso.slice(0,7))official.push({d:key,n:marks[key].n});
    }
    official.sort(function(x,z){return x.d<z.d?-1:1;});
    var box=panel.querySelector('.quick-panel__holidays');
    var noh=panel.querySelector('.quick-panel__nohol');
    if(official.length){
      var div=document.createElement('div');
      div.className='quick-panel__holidays';
      var lis='';
      for(var e2=0;e2<official.length;e2++){
        lis+='<li><strong>'+official[e2].d.slice(8,10)+'/'+official[e2].d.slice(5,7)+'</strong> <span></span></li>';
      }
      div.innerHTML='<h3>Helligdage denne m\\u00e5ned</h3><ul>'+lis+'</ul>';
      var its=div.querySelectorAll('li span');
      for(var f=0;f<its.length;f++)its[f].textContent=official[f].n;
      if(box)box.replaceWith(div);else if(noh)noh.replaceWith(div);else panel.appendChild(div);
    }else{
      var p=document.createElement('p');
      p.className='quick-panel__nohol muted';
      p.textContent='Ingen helligdage i denne m\\u00e5ned.';
      if(box)box.replaceWith(p);else if(!noh)panel.appendChild(p);
    }
  }
  try{rebuildMiniCalendar();}catch(err){/* behold oprindeligt HTML */}

  var nodes=document.querySelectorAll('[data-date]');
  for(var i=0;i<nodes.length;i++){
    var el=nodes[i];
    if(el.getAttribute('data-date')===iso){
      el.classList.add('today');
    }
  }
  // Hamburger menu toggle (mobile)
  var btn=document.querySelector('.nav-toggle');
  var nav=document.getElementById('main-nav');
  if(btn && nav){
    btn.addEventListener('click',function(){
      var open=nav.classList.toggle('is-open');
      btn.setAttribute('aria-expanded',open?'true':'false');
      btn.setAttribute('aria-label',open?'Luk menu':'Åbn menu');
    });
  }
})();
"""


def write_og_image(path: Path) -> None:
    """Render a 1200x630 OG image: brand teal background + white card + brand text.

    Pure-Python PNG writer reused from write_png_icon. The design mirrors the
    favicon: solid teal field, white rounded calendar card, brand wordmark and
    a short Danish tagline in a simple bitmap typeface.
    """

    width, height = 1200, 630
    teal = (15, 118, 110, 255)
    dark = (19, 78, 74, 255)
    white = (255, 255, 255, 255)
    cream = (236, 253, 245, 255)

    pixels = [[teal for _ in range(width)] for _ in range(height)]

    def fill_rect(x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int, int]) -> None:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        for y in range(y1, y2):
            row = pixels[y]
            for x in range(x1, x2):
                row[x] = color

    # decorative left calendar mark
    mark_x, mark_y, mark_size = 80, 180, 270
    fill_rect(mark_x, mark_y, mark_x + mark_size, mark_y + mark_size, white)
    fill_rect(mark_x, mark_y, mark_x + mark_size, mark_y + 60, dark)
    cell = (mark_size - 50) // 7
    for row in range(2):
        for col in range(2):
            cx = mark_x + 25 + col * (cell + 18)
            cy = mark_y + 110 + row * (cell + 18)
            fill_rect(cx, cy, cx + cell, cy + cell, teal)

    # cream pill background for text region
    fill_rect(420, 110, 1140, 540, cream)
    fill_rect(420, 110, 460, 540, dark)

    # 5x7 bitmap font for the brand line and tagline
    font = _og_bitmap_font()

    def draw_text(text: str, x: int, y: int, scale: int, color: tuple[int, int, int, int]) -> None:
        cursor = x
        for ch in text:
            glyph = font.get(ch.upper()) or font.get(" ")
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit:
                        fill_rect(
                            cursor + gx * scale,
                            y + gy * scale,
                            cursor + (gx + 1) * scale,
                            y + (gy + 1) * scale,
                            color,
                        )
            cursor += (len(glyph[0]) + 1) * scale

    draw_text("DANSKEDAGE.DK", 500, 180, 9, dark)
    draw_text("KALENDER HELLIGDAGE ARBEJDSDAGE", 500, 310, 5, teal)
    draw_text("FRI DANSK KALENDER UDEN LOGIN", 500, 400, 5, dark)

    raw = b"".join(b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in pixels)

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _og_bitmap_font() -> dict[str, list[list[int]]]:
    """Tiny 5x7 uppercase bitmap font used for the OG image."""

    raw = {
        "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
        "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
        "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
        "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
        "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
        "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
        "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
        "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
        "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
        "J": ["00001", "00001", "00001", "00001", "00001", "10001", "01110"],
        "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
        "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
        "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"],
        "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
        "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
        "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
        "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
        "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
        "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
        "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
        "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
        "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
        "W": ["10001", "10001", "10001", "10001", "10101", "11011", "10001"],
        "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
        "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
        "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
        ".": ["00000", "00000", "00000", "00000", "00000", "00000", "00100"],
        "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
        " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    }
    out: dict[str, list[list[int]]] = {}
    for ch, rows in raw.items():
        out[ch] = [[1 if c == "1" else 0 for c in row] for row in rows]
    return out


HREFLANG_MAP = {
    "index.html": "index.html",
    "udbytte.html": "dividendos.html",
    "ugenummer.html": "numero-da-semana.html",
    "aldersberegner.html": "calculadora-idade.html",
    "dato-difference.html": "diferenca-entre-datas.html",
    "nedtaelling.html": "countdown.html",
    "naeste-helligdag.html": "proximo-feriado.html",
    "ugedag.html": "dia-da-semana.html",
    "dato-plus-dage.html": "data-mais-dias.html",
    "beregn-arbejdsdage.html": "calcular-dias-uteis.html",
    "laeg-arbejdsdage-til.html": "adicionar-dias-uteis.html",
    "traek-arbejdsdage-fra.html": "subtrair-dias-uteis.html",
    "dato-fra-uge.html": "data-da-semana.html",
    "kalender-2026.html": "calendario-2026.html",
    "helligdage-2026.html": "feriados-2026.html",
    "arbejdsdage-2026.html": "dias-uteis-2026.html",
    "bedste-feriedage-2026.html": "melhores-dias-para-folga-2026.html",
    "paaske-2026.html": "pascoa-2026.html",
    "kalender-2027.html": "calendario-2027.html",
    "helligdage-2027.html": "feriados-2027.html",
    "arbejdsdage-2027.html": "dias-uteis-2027.html",
    "bedste-feriedage-2027.html": "melhores-dias-para-folga-2027.html",
    "paaske-2027.html": "pascoa-2027.html",
    "kalender-2028.html": "calendario-2028.html",
    "helligdage-2028.html": "feriados-2028.html",
    "arbejdsdage-2028.html": "dias-uteis-2028.html",
    "bedste-feriedage-2028.html": "melhores-dias-para-folga-2028.html",
    "paaske-2028.html": "pascoa-2028.html",
    "kalender-2029.html": "calendario-2029.html",
    "helligdage-2029.html": "feriados-2029.html",
    "arbejdsdage-2029.html": "dias-uteis-2029.html",
    "bedste-feriedage-2029.html": "melhores-dias-para-folga-2029.html",
    "paaske-2029.html": "pascoa-2029.html",
    "kalender-2030.html": "calendario-2030.html",
    "helligdage-2030.html": "feriados-2030.html",
    "arbejdsdage-2030.html": "dias-uteis-2030.html",
    "bedste-feriedage-2030.html": "melhores-dias-para-folga-2030.html",
    "paaske-2030.html": "pascoa-2030.html",
}

BR_DOMAIN = "https://calendariobrasileiro.com.br"


def hreflang_links(path: str, canonical: str) -> str:
    br = HREFLANG_MAP.get(path)
    if not br:
        return ""
    br_url = BR_DOMAIN + ("/" if br == "index.html" else f"/{br}")
    return (
        f'<link rel="alternate" hreflang="da-DK" href="{canonical}">\n'
        f'<link rel="alternate" hreflang="pt-BR" href="{br_url}">\n'
        f'<link rel="alternate" hreflang="x-default" href="{canonical}">\n'
    )


def layout(
    title: str,
    description: str,
    path: str,
    body: str,
    current: str = "",
    breadcrumbs: list[tuple[str, str]] | None = None,
    faq: list[tuple[str, str]] | None = None,
    ads: bool = True,
) -> str:
    # ads=False nas paginas de servico (404, kontakt, vilkaar, privatliv,
    # stoet) e nas editoriais: sao paginas sem conteudo proprio para o
    # leitor, e o AdSense classifica anuncio nelas como "conteudo de lav
    # vaerdi". Foi um dos motivos da afvisning de 2026-08-21.
    canonical = DOMAIN + ("/" if path == "index.html" else f"/{path}")
    hreflang = hreflang_links(path, canonical)
    og_image = DOMAIN + "/img/og-default.png"
    nav_year = ACTIVE_YEAR
    _ads_tags = [
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + ADS_CLIENT + '" crossorigin="anonymous"></script>',
        '<meta name="google-adsense-account" content="' + ADS_CLIENT + '">',
    ]
    ads_head = (chr(10).join(_ads_tags) + chr(10)) if ads else ""
    nav = [
        ("Kalender", f"kalender-{nav_year}.html", "kalender"),
        ("Helligdage", f"helligdage-{nav_year}.html", "helligdage"),
        ("Arbejdsdage", f"arbejdsdage-{nav_year}.html", "arbejdsdage"),
        ("Ugenummer", "ugenummer.html", "ugenummer"),
        ("Skoleferier", "skoleferier.html", "skoleferier"),
        ("Ferieplan", f"bedste-feriedage-{nav_year}.html", "ferieplan"),
        ("Udbytte", "udbytte.html", "udbytte"),
    ]
    nav_html_parts = []
    for label, href, key in nav:
        current_attr = ' aria-current="page"' if key == current else ""
        nav_html_parts.append(f'<li><a href="{href}"{current_attr}>{label}</a></li>')
    nav_html = "".join(nav_html_parts)

    schema_blocks: list[str] = [
        '<script type="application/ld+json">'
        + json.dumps(json_ld(title, description, canonical), ensure_ascii=False)
        + "</script>"
    ]
    breadcrumb_html = ""
    if breadcrumbs:
        schema_blocks.append(
            '<script type="application/ld+json">'
            + json.dumps(breadcrumb_jsonld(breadcrumbs), ensure_ascii=False)
            + "</script>"
        )
        breadcrumb_html = render_breadcrumb_nav(breadcrumbs)
    if faq:
        schema_blocks.append(
            '<script type="application/ld+json">'
            + json.dumps(faq_jsonld(faq), ensure_ascii=False)
            + "</script>"
        )

    if breadcrumb_html:
        body = breadcrumb_html + body
    if faq:
        body = body + render_faq_section(faq)

    schema_html = "\n".join(schema_blocks)

    return f"""<!DOCTYPE html>
<html lang="da-DK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{canonical}">
{hreflang}
<meta name="theme-color" content="#0f766e">
<meta property="og:type" content="website">
<meta property="og:locale" content="da_DK">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(description)}">
<meta name="twitter:image" content="{og_image}">
{ads_head}<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png">
<link rel="icon" type="image/png" sizes="192x192" href="/favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="stylesheet" href="css/style.css">
<script src="js/cookie-consent.js" defer></script>
{schema_html}
</head>
<body>
<a class="skip-link" href="#indhold">Spring til indhold</a>
<header class="site-header"><div class="container site-header__inner">
<a class="brand" href="index.html"><svg class="brand__mark" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="12" fill="#0f766e"/><rect x="12" y="15" width="40" height="37" rx="5" fill="#fff"/><rect x="12" y="15" width="40" height="10" rx="5" fill="#134e4a"/><path d="M22 34h7v7h-7zm13 0h7v7h-7z" fill="#0f766e"/></svg><span>{SITE_NAME}</span></a>
<button class="nav-toggle" type="button" aria-controls="main-nav" aria-expanded="false" aria-label="Åbn menu"><span class="nav-toggle__bars" aria-hidden="true"><span></span><span></span><span></span></span><span>Menu</span></button>
<nav class="main-nav" id="main-nav" aria-label="Hovedmenu"><ul>{nav_html}</ul></nav>
</div></header>
<main id="indhold">{body}</main>
<footer class="footer"><div class="container footer-grid">
<div><h2>{SITE_NAME}</h2><p>Danske kalender- og hverdagsberegnere. Gratis, opdateret og uden login.</p></div>
<div><h3>Kalender</h3><ul><li><a href="kalender-{nav_year}.html">Kalender {nav_year}</a></li><li><a href="helligdage-{nav_year}.html">Helligdage {nav_year}</a></li><li><a href="arbejdsdage-{nav_year}.html">Arbejdsdage {nav_year}</a></li></ul></div>
<div><h3>Værktøjer</h3><ul><li><a href="vaerktoejer.html">Alle værktøjer</a></li><li><a href="beregn-arbejdsdage.html">Beregn arbejdsdage</a></li><li><a href="laeg-arbejdsdage-til.html">Læg arbejdsdage til</a></li><li><a href="traek-arbejdsdage-fra.html">Træk arbejdsdage fra</a></li><li><a href="ugenummer.html">Ugenummer</a></li><li><a href="dato-fra-uge.html">Dato fra ugenummer</a></li><li><a href="aldersberegner.html">Aldersberegner</a></li><li><a href="dato-difference.html">Datoforskel</a></li><li><a href="nedtaelling.html">Nedtælling</a></li><li><a href="naeste-helligdag.html">Næste helligdag</a></li><li><a href="ugedag.html">Ugedag</a></li><li><a href="dato-plus-dage.html">Dato ± N dage</a></li></ul></div>
<div><h3>Site</h3><ul><li><a href="om.html">Om sitet</a></li><li><a href="metode.html">Metode</a></li><li><a href="kilder.html">Kilder</a></li><li><a href="redaktionel-politik.html">Redaktionel politik</a></li><li><a href="kontakt.html">Kontakt</a></li><li><a href="privatlivspolitik.html">Privatlivspolitik</a></li><li><a href="vilkar.html">Vilkår</a></li><li><a href="stot.html">Støt projektet</a></li><li><a href="sitemap.xml">Sitemap</a></li></ul></div>
</div></footer>
<script src="js/calendar-tools.js"></script>
<script src="js/today.js"></script>
</body>
</html>
"""


def json_ld(title: str, description: str, url: str) -> dict:
    publisher = {
        "@type": "Organization",
        "name": SITE_NAME,
        "url": DOMAIN + "/",
        "logo": {
            "@type": "ImageObject",
            "url": DOMAIN + "/favicon-512.png",
            "width": 512,
            "height": 512,
        },
    }
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": description,
        "url": url,
        "inLanguage": "da-DK",
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": DOMAIN + "/", "publisher": publisher},
        "publisher": publisher,
    }


def breadcrumb_jsonld(items: list[tuple[str, str]]) -> dict:
    """Build BreadcrumbList JSON-LD. items: [(name, path)]. Empty path = final."""

    elements = []
    for index, (name, path) in enumerate(items, start=1):
        entry: dict = {
            "@type": "ListItem",
            "position": index,
            "name": name,
        }
        if path:
            entry["item"] = DOMAIN + ("/" if path == "index.html" else f"/{path}")
        elements.append(entry)
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }


def render_breadcrumb_nav(items: list[tuple[str, str]]) -> str:
    parts = []
    for index, (name, path) in enumerate(items):
        if index > 0:
            parts.append('<span aria-hidden="true"> &rsaquo; </span>')
        if path:
            href = "index.html" if path == "index.html" else path
            parts.append(f'<a href="{html.escape(href)}">{html.escape(name)}</a>')
        else:
            parts.append(f'<span aria-current="page">{html.escape(name)}</span>')
    return (
        '<nav class="breadcrumbs" aria-label="Brødkrummesti"><div class="container">'
        + "".join(parts)
        + "</div></nav>"
    )


def faq_jsonld(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in items
        ],
    }


def render_faq_section(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<details class="faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>'
        for q, a in items
    )
    return (
        '<section class="section" id="faq"><div class="container container--narrow">'
        '<div class="section-title"><div><h2>Ofte stillede spørgsmål</h2>'
        '<p>Korte svar på de mest almindelige spørgsmål til denne dato.</p></div></div>'
        f'<div class="faq">{rows}</div></div></section>'
    )


def ad_slot(position: str) -> str:
    """Return empty string — no manual AdSense unit placeholders.

    The site loads the AdSense loader script and the `google-adsense-account`
    meta tag in <head>; Google's Auto Ads handle placement. Manual <ins> blocks
    with fictitious slot IDs (AD_SLOT_HEADER/MID/FOOTER) were removed because
    they trigger AdSense policy warnings until real ad-unit IDs exist.
    """

    del position  # kept for backwards-compatible call sites
    return ""


def hero(
    title: str,
    lead: str,
    year: int | None = None,
    panel: tuple[int, int] | None = None,
) -> str:
    """Render the hero section.

    `panel` is an explicit (year, month) for the quick-panel mini calendar.
    When omitted we fall back to (year or today.year, today.month).
    """

    # Quick-panel SEMPRE mostra o mes corrente, independente da pagina.
    # data-auto-month permite que js/today.js re-renderize o grid client-side
    # quando o HTML publicado for de um mes anterior (build antigo).
    panel = (date.today().year, date.today().month)
    side = mini_month(panel[0], panel[1])
    return f"""<section class="hero"><div class="container hero-grid"><div><span class="eyebrow">Dansk kalender · opdateret {ACTIVE_YEAR}</span><h1>{title}</h1><p class="lead">{lead}</p><div class="hero-actions"><a class="btn btn--primary" href="beregn-arbejdsdage.html">Beregn arbejdsdage</a><a class="btn btn--ghost" href="ugenummer.html">Find ugenummer</a></div></div><aside class="quick-panel" data-auto-month="1">{side}</aside></div></section>"""


def quick_panel_holidays_text(year: int, month: int) -> str:
    """Lista textual de helligdage do mes corrente p/ quick-panel."""
    items = [m for m in all_marks(year) if m.date.month == month and m.kind == "helligdag"]
    if not items:
        return '<p class="quick-panel__nohol muted">Ingen helligdage i denne måned.</p>'
    rows = []
    for h in sorted(items, key=lambda x: x.date):
        rows.append(
            f'<li><strong>{h.date.day:02d}/{h.date.month:02d}</strong> '
            f'<span>{h.name}</span></li>'
        )
    return (
        '<div class="quick-panel__holidays"><h3>Helligdage denne måned</h3>'
        f'<ul>{"".join(rows)}</ul></div>'
    )


def mini_month(year: int, month: int) -> str:
    return (
        f"<h2>{MONTHS[month-1].capitalize()} {year}</h2>"
        + month_calendar_html(year, month, mini=True)
        + mini_calendar_legend()
        + quick_panel_holidays_text(year, month)
    )


def month_calendar_html(year: int, month: int, mini: bool = False) -> str:
    cal = calendar.Calendar(firstweekday=0)
    marks = {m.date: m for m in all_marks(year)}
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
        title = f' title="{html.escape(mark.name)}"' if mark else ""
        parts.append(
            f'<span class="{" ".join(classes)}" data-date="{iso(d)}"{title}>{d.day}</span>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def calendar_legend() -> str:
    return """<div class="calendar-legend" aria-label="Forklaring af kalenderfarver">
<span class="calendar-legend__item"><span class="calendar-legend__swatch calendar-legend__swatch--holiday"></span>Officiel helligdag</span>
<span class="calendar-legend__item"><span class="calendar-legend__swatch calendar-legend__swatch--special"></span>Mærkedag eller lokal fridag</span>
<span class="calendar-legend__item"><span class="calendar-legend__swatch calendar-legend__swatch--weekend"></span>Weekend</span>
<span class="calendar-legend__item"><span class="calendar-legend__swatch calendar-legend__swatch--today"></span>I dag</span>
</div>"""


def mini_calendar_legend() -> str:
    return calendar_legend()


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


def tools_related_grid(exclude: str = "") -> str:
    """Small internal-link grid used between ad slots on the builtin tool pages."""
    links = [
        ("beregn-arbejdsdage.html", "Beregn arbejdsdage", "Antal arbejdsdage mellem to datoer."),
        ("laeg-arbejdsdage-til.html", "Læg arbejdsdage til", "Find datoen efter X arbejdsdage."),
        ("traek-arbejdsdage-fra.html", "Træk arbejdsdage fra", "Gå X arbejdsdage tilbage fra en dato."),
        ("ugenummer.html", "Ugenummer", "Find ISO-ugenummer for en dato."),
        ("dato-fra-uge.html", "Dato fra ugenummer", "Find datoen ud fra år, uge og ugedag."),
        ("vaerktoejer.html", "Alle værktøjer", "Se alle kalender- og dato-beregnere."),
    ]
    cards = "".join(
        f'<a class="card" href="{href}"><h3>{label}</h3><p class="muted">{desc}</p></a>'
        for href, label, desc in links
        if href != exclude
    )
    return (
        '<section class="section"><div class="container">'
        '<div class="section-title"><div><h2>Andre værktøjer</h2>'
        '<p>Flere danske kalender- og dato-beregnere.</p></div></div>'
        f'<div class="grid">{cards}</div></div></section>'
    )


def write_page(
    path: str,
    title: str,
    description: str,
    body: str,
    current: str = "",
    breadcrumbs: list[tuple[str, str]] | None = None,
    faq: list[tuple[str, str]] | None = None,
    ads: bool = True,
) -> None:
    (ROOT / path).write_text(
        layout(title, description, path, body, current, breadcrumbs, faq, ads),
        encoding="utf-8",
    )


# ─── Årsspecifik analyse ────────────────────────────────────────────────────
# Sidefamilierne (helligdage-, arbejdsdage-, paaske- …) fandtes i fem årgange
# med identisk brødtekst, hvor kun datoerne var skiftet ud. Google læser den
# slags som skabelonsider uden selvstændig værdi — det var hovedårsagen til
# AdSense-afvisningen "indhold af lav værdi" den 21. august 2026.
#
# Funktionerne herunder regner de forhold ud, der FAKTISK varierer fra år til
# år, og skriver forskellig tekst afhængigt af resultatet: hvilke helligdage
# der går tabt i weekenden, hvilke klemmedage året giver, og hvordan antallet
# af arbejdsdage ligger i forhold til naboårene.

YEAR_SPAN = (2026, 2030)


def year_profile(year: int) -> dict:
    marks = all_marks(year)
    official = [m for m in marks if m.official]
    lost = [m for m in official if m.date.weekday() >= 5]
    bridges = []
    for m in official:
        wd = m.date.weekday()
        if wd == 1:
            bridges.append({"mark": m, "day": m.date - timedelta(days=1), "ugedag": "mandagen"})
        elif wd == 3:
            bridges.append({"mark": m, "day": m.date + timedelta(days=1), "ugedag": "fredagen"})
    return {
        "official": official,
        "lost": lost,
        "bridges": bridges,
        "stats": year_stats(year),
        "easter": easter_sunday(year),
        "leap": (year % 4 == 0 and year % 100 != 0) or year % 400 == 0,
    }


def _liste(dele: list[str]) -> str:
    """Dansk opremsning: «a, b og c»."""
    if not dele:
        return ""
    if len(dele) == 1:
        return dele[0]
    return ", ".join(dele[:-1]) + " og " + dele[-1]


def helligdage_analyse(year: int) -> str:
    p = year_profile(year)
    lost, bridges = p["lost"], p["bridges"]
    paa_hverdag = len(p["official"]) - len(lost)

    if not lost:
        vurdering = (
            f"<p>{year} er et af de gode helligdagsår: <strong>ingen</strong> af årets "
            f"{len(p['official'])} officielle helligdage falder i en weekend. Alle giver "
            f"altså en fridag, der ellers ville have været en arbejdsdag.</p>"
        )
    else:
        tabt = _liste([
            f"{m.name} ({WEEKDAYS_LONG[m.date.weekday()]} den {_fmt_dansk_dato(m.date)})"
            for m in lost
        ])
        if len(lost) >= 3:
            tone = (f"Det gør {year} til et dårligt helligdagsår — tre eller flere fridage "
                    f"forsvinder i weekenden")
        elif len(lost) == 2:
            tone = f"To fridage går dermed tabt i {year}"
        else:
            tone = f"En enkelt fridag går tabt i {year}"
        vurdering = (
            f"<p>{tone}: {tabt}. Tilbage står <strong>{paa_hverdag} helligdage på hverdage</strong> "
            f"ud af årets {len(p['official'])}. Dansk lovgivning giver ikke erstatningsfridage for "
            f"helligdage, der falder i en weekend — de er ganske enkelt væk det år.</p>"
        )

    if bridges:
        kl = _liste([
            f"{b['ugedag']} den {_fmt_dansk_dato(b['day'])} (omkring {b['mark'].name})"
            for b in bridges
        ])
        klemme = (
            f"<p>Til gengæld giver {year} <strong>{len(bridges)} oplagte klemmedage</strong>: {kl}. "
            f"En enkelt feriedag hver af de dage forlænger fridagen til en lang weekend. "
            f"Klemmedage er ikke fridage efter loven — de aftales lokalt eller trækkes på ferien.</p>"
        )
    else:
        klemme = (
            f"<p>{year} giver ingen klassiske klemmedage: ingen helligdag falder på en tirsdag "
            f"eller torsdag, hvor en enkelt feriedag ville bygge bro til weekenden.</p>"
        )
    return vurdering + klemme


def arbejdsdage_analyse(year: int) -> str:
    lo, hi = YEAR_SPAN
    span = {y: year_stats(y)["workdays"] for y in range(lo, hi + 1)}
    n = span[year]
    hoejest, lavest = max(span.values()), min(span.values())
    p = year_profile(year)

    if n == hoejest and list(span.values()).count(n) == 1:
        plads = f"det <strong>højeste</strong> antal i perioden {lo}–{hi}"
    elif n == lavest and list(span.values()).count(n) == 1:
        plads = f"det <strong>laveste</strong> antal i perioden {lo}–{hi}"
    else:
        plads = f"midt i feltet for perioden {lo}–{hi}, hvor spændet er {lavest}–{hoejest} dage"

    nabo = []
    for andet in (year - 1, year + 1):
        if andet in span:
            d = n - span[andet]
            if d == 0:
                nabo.append(f"det samme som i {andet}")
            else:
                nabo.append(f"{abs(d)} {'flere' if d > 0 else 'færre'} end i {andet}")

    skudt = ""
    if p["leap"]:
        ekstra = date(year, 2, 29)
        skudt = (f" {year} er skudår, så februar har 29 dage; den ekstra dag falder på en "
                 f"{WEEKDAYS_LONG[ekstra.weekday()]}.")

    return (
        f"<p>{year} har <strong>{n} arbejdsdage</strong>, når weekender og officielle "
        f"helligdage er trukket fra. Det er {plads}, og {_liste(nabo)}.{skudt}</p>"
        f"<p>Forskellen mellem årene skyldes næsten udelukkende, hvor helligdagene lander. "
        f"I {year} falder {len(p['lost'])} af dem i en weekend, hvor de ikke koster en "
        f"arbejdsdag. Regner man juleaftensdag, nytårsaftensdag, grundlovsdag og 1. maj med "
        f"som hele eller halve fridage — som mange overenskomster gør — ender man på "
        f"<strong>{p['stats']['office_workdays']} arbejdsdage</strong> i praksis.</p>"
    )


def paaske_analyse(year: int) -> str:
    p = year_profile(year)
    e = p["easter"]
    lo, hi = YEAR_SPAN
    span = {y: easter_sunday(y) for y in range(lo, hi + 1)}
    tidligst = min(span.items(), key=lambda kv: (kv[1].month, kv[1].day))
    senest = max(span.items(), key=lambda kv: (kv[1].month, kv[1].day))

    if year == tidligst[0]:
        placering = f"Det er den <strong>tidligste</strong> påske i perioden {lo}–{hi}"
    elif year == senest[0]:
        placering = f"Det er den <strong>seneste</strong> påske i perioden {lo}–{hi}"
    else:
        placering = (f"Til sammenligning falder påskedag tidligst den "
                     f"{_fmt_dansk_dato(tidligst[1])} i {tidligst[0]} og senest den "
                     f"{_fmt_dansk_dato(senest[1])} i {senest[0]}")

    return (
        f"<p>Påskedag {year} er {_fmt_dansk_dato(e)}, altså en "
        f"{_classify_easter_position(e)} påske. {placering}. Fordi både Kristi "
        f"himmelfartsdag og pinse regnes fra påskedagen, flytter hele forårets "
        f"fridagsmønster sig med den: i {year} ligger Kristi himmelfartsdag den "
        f"{_fmt_dansk_dato(e + timedelta(days=39))} og pinsedag den "
        f"{_fmt_dansk_dato(e + timedelta(days=49))}.</p>"
        f"<p>Påskedag er den første søndag efter den første fuldmåne på eller efter "
        f"forårsjævndøgn — beregnet efter kirkens tabeller, ikke efter den faktiske "
        f"astronomiske fuldmåne. Derfor kan datoen svinge mellem 22. marts og 25. april. "
        f"I {year - 1} var påskedag den {_fmt_dansk_dato(easter_sunday(year - 1))}, og i "
        f"{year + 1} bliver den den {_fmt_dansk_dato(easter_sunday(year + 1))}.</p>"
    )


def kalender_analyse(year: int) -> str:
    """Hvad der er særligt ved netop dette års kalender."""
    p = year_profile(year)
    s = p["stats"]
    nytaar = date(year, 1, 1)
    nytaar_uge = nytaar.isocalendar()
    lange_aar = s["weeks"] == 53
    saerligt = []
    if p["leap"]:
        saerligt.append("det er skudår, så året har 366 dage")
    if lange_aar:
        saerligt.append("året har <strong>53 uger</strong>, hvilket kun sker cirka hvert femte til sjette år")
    if nytaar_uge.week != 1:
        saerligt.append(
            f"1. januar ligger i uge {nytaar_uge.week} af {nytaar_uge.year} og ikke i uge 1 — "
            f"efter ISO 8601 hører de første dage af januar til det foregående års sidste uge, "
            f"når årets første torsdag falder senere"
        )
    if not saerligt:
        saerligt.append(
            f"kalenderen følger det almindelige mønster: {s['days']} dage fordelt på "
            f"{s['weeks']} uger, med 1. januar i uge 1"
        )

    return (
        f"<p>Året begynder på en <strong>{WEEKDAYS_LONG[nytaar.weekday()]}</strong> og slutter på "
        f"en <strong>{WEEKDAYS_LONG[date(year, 12, 31).weekday()]}</strong>. Ugedagen for 1. januar "
        f"afgør hele årets rytme: den bestemmer, hvilke ugedage de faste helligdage lander på, og "
        f"dermed hvor mange af dem der reelt giver fri. I {year} er {_liste(saerligt)}.</p>"
        f"<p>Samlet rummer {year} <strong>{s['workdays']} arbejdsdage</strong>, "
        f"{s['weekend_days']} weekenddage og {len(p['official'])} officielle helligdage, hvoraf "
        f"{len(p['lost'])} falder i en weekend. Påsken — som flytter både Kristi himmelfartsdag og "
        f"pinse med sig — ligger i {year} omkring {_fmt_dansk_dato(p['easter'])}.</p>"
    )


def pinse_analyse(year: int) -> str:
    """Pinsens placering og den lange weekend, den giver netop i år."""
    e = year_profile(year)["easter"]
    pinsedag = e + timedelta(days=49)
    anden = e + timedelta(days=50)
    kristi = e + timedelta(days=39)
    lo, hi = YEAR_SPAN
    span = {y: easter_sunday(y) + timedelta(days=49) for y in range(lo, hi + 1)}
    i_maj = pinsedag.month == 5
    maj_aar = sorted(y for y, d in span.items() if d.month == 5)
    juni_aar = sorted(y for y, d in span.items() if d.month == 6)

    if i_maj:
        maaned = (
            f"<p>Pinsen ligger i {year} i <strong>maj</strong>. Det er den tidlige variant, hvor "
            f"pinsen falder sammen med forsommeren og ofte inden skolernes eksamensperiode. "
        )
        if juni_aar:
            maaned += (
                f"I perioden {lo}–{hi} rykker den ind i juni i "
                f"{_liste([str(y) for y in juni_aar])}.</p>"
            )
        else:
            maaned += f"I hele perioden {lo}–{hi} bliver pinsen i maj.</p>"
    else:
        maaned = (
            f"<p>Pinsen ligger i {year} i <strong>juni</strong> — den sene variant. Så tæt på "
            f"sommerferien mærkes den ekstra mandag mindre i ferieplanlægningen, fordi mange "
            f"alligevel er på vej mod sommerferie. "
        )
        if maj_aar:
            maaned += (
                f"I {_liste([str(y) for y in maj_aar])} falder pinsen derimod i maj.</p>"
            )
        else:
            maaned += f"I hele perioden {lo}–{hi} ligger pinsen i juni.</p>"

    afstand = (pinsedag - kristi).days
    bro = (
        f"<p>Der er {afstand} dage fra Kristi himmelfartsdag den {_fmt_dansk_dato(kristi)} til "
        f"pinsedag. De to helligdage ligger altid ti dage fra hinanden, så maj og juni rummer "
        f"i {year} to lange weekender med kun to ugers mellemrum — det er den tætteste klynge "
        f"af fridage på hele året.</p>"
    )

    return (
        f"<p>Pinsedag {year} falder {_fmt_dansk_dato(pinsedag)}, og 2. pinsedag dagen efter, "
        f"{_fmt_dansk_dato(anden)}. Fordi 2. pinsedag altid er en mandag, giver pinsen hvert år "
        f"en <strong>tre dages weekend</strong> uden at bruge en eneste feriedag — den eneste "
        f"danske helligdag, der automatisk lægger sig op ad en weekend.</p>"
        + maaned
        + bro
        + f"<p>Pinsedag ligger 49 dage — syv uger — efter påskedag og følger derfor påskens "
        f"bevægelse. I {year - 1} var pinsedag den "
        f"{_fmt_dansk_dato(easter_sunday(year - 1) + timedelta(days=49))}, og i {year + 1} "
        f"bliver den den {_fmt_dansk_dato(easter_sunday(year + 1) + timedelta(days=49))}.</p>"
    )


def himmelfart_analyse(year: int) -> str:
    """Klemmedagen og den fire dage lange weekend, som varierer i praksis."""
    e = year_profile(year)["easter"]
    kristi = e + timedelta(days=39)
    fredag = kristi + timedelta(days=1)
    soendag = kristi + timedelta(days=3)
    pinsedag = e + timedelta(days=49)
    lo, hi = YEAR_SPAN
    span = {y: easter_sunday(y) + timedelta(days=39) for y in range(lo, hi + 1)}
    tidligst = min(span.items(), key=lambda kv: (kv[1].month, kv[1].day))
    senest = max(span.items(), key=lambda kv: (kv[1].month, kv[1].day))

    if year == tidligst[0]:
        placering = (
            f"<p>Det er den <strong>tidligste</strong> Kristi himmelfartsdag i perioden "
            f"{lo}–{hi}; senest ligger den den {_fmt_dansk_dato(senest[1])} i {senest[0]}. "
            f"En tidlig himmelfartsdag betyder, at forårets fridage samler sig i april og "
            f"begyndelsen af maj.</p>"
        )
    elif year == senest[0]:
        placering = (
            f"<p>Det er den <strong>seneste</strong> Kristi himmelfartsdag i perioden "
            f"{lo}–{hi}; tidligst ligger den den {_fmt_dansk_dato(tidligst[1])} i "
            f"{tidligst[0]}. Ligger dagen så sent, skubbes pinsen helt hen i juni.</p>"
        )
    else:
        placering = (
            f"<p>I perioden {lo}–{hi} svinger Kristi himmelfartsdag mellem den "
            f"{_fmt_dansk_dato(tidligst[1])} ({tidligst[0]}) og den "
            f"{_fmt_dansk_dato(senest[1])} ({senest[0]}). {year} ligger derimellem.</p>"
        )

    maanedsskift = ""
    if fredag.month != kristi.month:
        maanedsskift = (
            f"<p>Bemærk, at klemmefredagen i {year} falder i den følgende måned: "
            f"helligdagen er den {_fmt_dansk_dato(kristi)}, mens fredagen er den "
            f"{_fmt_dansk_dato(fredag)}. Det har betydning, hvis fridage registreres "
            f"pr. kalendermåned i lønsystemet.</p>"
        )

    return (
        f"<p>Kristi himmelfartsdag {year} er torsdag den {_fmt_dansk_dato(kristi)}. Dagen falder "
        f"altid på en torsdag, 39 dage efter påskedag, og det gør den til årets tydeligste "
        f"klemmedag: tager du fri fredag den {_fmt_dansk_dato(fredag)}, får du "
        f"<strong>fire sammenhængende fridage</strong> frem til søndag den "
        f"{_fmt_dansk_dato(soendag)} — for én enkelt feriedag.</p>"
        + placering
        + maanedsskift
        + f"<p>Fredagen efter er <em>ikke</em> en officiel helligdag. Mange arbejdspladser holder "
        f"lukket alligevel, og en del skoler lægger fridag samme dag, men det afhænger af "
        f"overenskomst og lokal kutyme — det er ikke en ret efter loven. Ti dage senere følger "
        f"pinsen, som i {year} falder den {_fmt_dansk_dato(pinsedag)}.</p>"
    )


def aarsanalyse_sektion(year: int, scope: str) -> str:
    """Indsættes på årssiderne, så hver årgang bærer sin egen analyse."""
    bygger = {
        "helligdage": (f"Hvor mange fridage giver {year} reelt?", helligdage_analyse),
        "arbejdsdage": (f"Ligger {year} højt eller lavt på arbejdsdage?", arbejdsdage_analyse),
        "paaske": (f"Hvor ligger påsken i {year} — og hvorfor flytter den sig?", paaske_analyse),
        "kalender": (f"Hvad er særligt ved kalenderen i {year}?", kalender_analyse),
        "pinse": (f"Hvornår er pinsen i {year} — og hvor lang bliver weekenden?", pinse_analyse),
        "himmelfart": (f"Klemmedagen omkring Kristi himmelfart {year}", himmelfart_analyse),
    }
    if scope not in bygger:
        return ""
    overskrift, fn = bygger[scope]
    return (
        f'<section class="section"><div class="container narrow prose">'
        f"<h2>{overskrift}</h2>{fn(year)}</div></section>"
    )


def render_index(year: int) -> None:
    body = hero(
        f"Kalender {year}",
        f"Se dansk kalender for {year} med helligdage, arbejdsdage, ugenumre, påske, pinse og forslag til gode feriedage.",
        year,
    )
    body += ad_slot("header")
    body += '<section class="section"><div class="container"><div class="section-title"><div><h2>Overblik for året</h2><p>Nøgletal for kalenderåret, beregnet lokalt.</p></div></div>'
    body += year_overview(year)
    body += '</div></section>'
    body += link_grid(year)
    body += ad_slot("mid")
    body += year_calendar_section(year)
    body += ad_slot("footer")
    write_page(
        "index.html",
        f"Kalender {year} - helligdage, arbejdsdage og ugenumre",
        f"Dansk kalender {year} med helligdage, arbejdsdage, ugenumre og ferieforslag.",
        body,
        "kalender",
    )


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
    return '<section class="section"><div class="container"><div class="section-title"><div><h2>Kalender måned for måned</h2><p>Røde dage er officielle helligdage. Gule dage er mærkedage eller almindelige fridage mange steder.</p></div></div>' + calendar_legend() + '<div class="month-grid">' + "".join(months) + "</div></div></section>"


def render_year_pages(year: int) -> None:
    stats = year_stats(year)
    body = hero(
        f"Kalender {year}",
        f"Komplet dansk kalender for {year} med helligdage, arbejdsdage, ugenumre og planlægning af ferie.",
        year,
        panel=(year, 1),
    )
    body += ad_slot("header")
    body += '<section class="section"><div class="container">'
    body += year_overview(year)
    body += '</div></section>' + link_grid(year)
    body += ad_slot("mid")
    body += year_calendar_section(year)
    body += ad_slot("footer")
    body += aarsanalyse_sektion(year, "kalender")
    write_page(
        f"kalender-{year}.html",
        f"Kalender {year} - dansk kalender med helligdage",
        f"Dansk kalender {year}: {stats['workdays']} arbejdsdage, {stats['official_holidays']} officielle helligdage og {stats['weeks']} ISO-uger.",
        body,
        "kalender",
        breadcrumbs=[("Forside", "index.html"), ("Kalender", f"kalender-{ACTIVE_YEAR}.html"), (str(year), "")],
    )

    render_holidays(year)
    render_workdays(year)
    render_easter(year)
    render_pentecost(year)
    render_ascension(year)
    render_best_vacation(year)


def render_holidays(year: int) -> None:
    from datetime import datetime as _dt, timezone as _tz
    from urllib.parse import quote as _q
    marks_list = list(all_marks(year))
    rows = []
    for m in marks_list:
        start = m.date.strftime("%Y%m%d")
        end = (m.date + timedelta(days=1)).strftime("%Y%m%d")
        gcal_text = _q(m.name)
        gcal_details = _q(m.note or "")
        gcal = (f"https://calendar.google.com/calendar/u/0/r/eventedit"
                f"?text={gcal_text}&dates={start}/{end}&details={gcal_details}")
        ol_subject = _q(m.name)
        ol_body = _q(m.note or "")
        ol = (f"https://outlook.live.com/calendar/0/deeplink/compose"
              f"?path=/calendar/action/compose&rru=addevent"
              f"&subject={ol_subject}&startdt={m.date.isoformat()}"
              f"&enddt={(m.date + timedelta(days=1)).isoformat()}"
              f"&allday=true&body={ol_body}")
        rows.append(
            f"<tr><td>{fmt_date(m.date)}</td><td>{WEEKDAYS_LONG[m.date.weekday()]}</td><td>{m.name}</td>"
            f"<td>{'Ja' if m.official else 'Nej'}</td><td>{m.note}</td>"
            f'<td class="add-cell no-print"><a href="{gcal}" target="_blank" rel="nofollow noopener">GCal</a> · '
            f'<a href="{ol}" target="_blank" rel="nofollow noopener">Outlook</a></td></tr>'
        )
    rows_html = "".join(rows)
    ics_name = f"helligdage-{year}.ics"
    now_stamp = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    ics_lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        f"PRODID:-//DanskeDage.dk//Helligdage {year}//DA",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:Helligdage {year}",
        f"X-WR-CALDESC:Danske helligdage og mærkedage — kilde {DOMAIN}",
        "X-WR-TIMEZONE:Europe/Copenhagen",
    ]
    for m in marks_list:
        start = m.date.strftime("%Y%m%d")
        end = (m.date + timedelta(days=1)).strftime("%Y%m%d")
        uid = f"{m.date.isoformat()}-{abs(hash(m.name)) % 10**8}@danskedage.dk"
        summary = m.name.replace(",", "\\,").replace(";", "\\;")
        desc = (m.note or "").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
        ics_lines.extend([
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
            f"SUMMARY:{summary}", f"DESCRIPTION:{desc}",
            "TRANSP:TRANSPARENT", "STATUS:CONFIRMED", "END:VEVENT",
        ])
    ics_lines.append("END:VCALENDAR")
    (ROOT / ics_name).write_text("\r\n".join(ics_lines) + "\r\n", encoding="utf-8")
    download_box = (
        f'<p class="export-bar no-print">'
        f'<a class="btn btn--ghost" href="{ics_name}" download>↓ Download .ics ({year})</a> '
        f'<span class="muted">Importer i Google Calendar, Apple Calendar, Outlook m.m.</span></p>'
    )
    body = hero(
        f"Helligdage {year}",
        f"Alle danske helligdage og vigtige mærkedage i {year}, inklusive påske, pinse, jul og nytår.",
        year,
        panel=(year, 1),
    )
    body += ad_slot("header")
    body += f'<section class="section"><div class="container">{download_box}<div class="table-wrap"><table><thead><tr><th>Dato</th><th>Ugedag</th><th>Dag</th><th>Officiel helligdag</th><th>Note</th><th class="no-print">Tilføj</th></tr></thead><tbody>{rows_html}</tbody></table></div><p class="notice">Store bededag er markeret historisk, men er ikke officiel helligdag i Danmark fra 2024.</p></div></section>'
    body += ad_slot("mid")
    stats = year_stats(year)
    easter_date = easter_sunday(year)
    pentecost_date = easter_date + timedelta(days=49)
    ascension_date = easter_date + timedelta(days=39)
    faq = [
        (
            f"Hvor mange helligdage er der i {year}?",
            f"I {year} er der {stats['official_holidays']} officielle helligdage i Danmark. "
            f"Heraf falder {stats['official_holidays_on_weekdays']} på en hverdag.",
        ),
        (
            f"Hvornår falder påskedag i {year}?",
            f"Påskedag falder {fmt_date(easter_date)} ({WEEKDAYS_LONG[easter_date.weekday()]}). "
            "Skærtorsdag, langfredag og 2. påskedag er ligeledes officielle helligdage.",
        ),
        (
            f"Hvornår er Kristi himmelfartsdag i {year}?",
            f"Kristi himmelfartsdag falder altid på en torsdag, 39 dage efter påskedag. "
            f"I {year} er det {fmt_date(ascension_date)}.",
        ),
        (
            f"Hvornår er pinse i {year}?",
            f"Pinsedag er {fmt_date(pentecost_date)} og 2. pinsedag dagen efter. "
            "Begge dage er officielle helligdage.",
        ),
        (
            "Er store bededag stadig en helligdag?",
            "Nej, store bededag er afskaffet som officiel helligdag fra 2024. "
            "På siden er den markeret historisk, men den tæller ikke som helligdag.",
        ),
    ]
    body += aarsanalyse_sektion(year, "helligdage")
    write_page(
        f"helligdage-{year}.html",
        f"Helligdage {year} i Danmark",
        f"Se danske helligdage {year}: påske, pinse, Kristi himmelfartsdag, jul, nytår og særlige mærkedage.",
        body,
        "helligdage",
        breadcrumbs=[("Forside", "index.html"), ("Helligdage", f"helligdage-{ACTIVE_YEAR}.html"), (str(year), "")],
        faq=faq,
    )


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
    body = hero(
        f"Arbejdsdage {year}",
        f"Beregnede arbejdsdage pr. måned i {year}. Standardtallet tæller mandag-fredag minus officielle helligdage.",
        year,
        panel=(year, 1),
    )
    body += ad_slot("header")
    body += f'<section class="section"><div class="container"><div class="grid"><article class="card"><h3>Standard</h3><p class="stat">{stats["workdays"]}</p><p class="muted">Arbejdsdage uden officielle helligdage.</p></article><article class="card"><h3>Kontor-variant</h3><p class="stat">{stats["office_workdays"]}</p><p class="muted">Trækker også 1. maj, Grundlovsdag, juleaftensdag og nytårsaftensdag fra.</p></article></div></div></section>'
    body += ad_slot("mid")
    body += '<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Måned</th><th>Kalenderdage</th><th>Hverdage</th><th>Helligdage på hverdage</th><th>Arbejdsdage</th><th>Kontor-variant</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></div></section>"

    # ---- Year-specific prose block (differentiates arbejdsdage-<year> pages) ----
    stats_prev = year_stats(year - 1)
    stats_next = year_stats(year + 1)
    diff_prev = stats["workdays"] - stats_prev["workdays"]
    diff_next = stats_next["workdays"] - stats["workdays"]
    weekend_hol = _weekend_holidays_in_year(year)
    e_ctx = easter_year_context(year)
    diff_prev_txt = ("præcis lige så mange" if diff_prev == 0 else
                     f"{abs(diff_prev)} dag{'e' if abs(diff_prev) != 1 else ''} {'flere' if diff_prev > 0 else 'færre'}")
    diff_next_txt = ("præcis lige så mange" if diff_next == 0 else
                     f"{abs(diff_next)} dag{'e' if abs(diff_next) != 1 else ''} {'flere' if diff_next > 0 else 'færre'}")
    # Comparison table for ±2 years
    comp_rows = "".join(
        f"<tr><td>{y}</td><td>{year_stats(y)['workdays']}</td><td>{year_stats(y)['office_workdays']}</td></tr>"
        for y in range(year - 2, year + 3)
    )
    body += (
        f'<section class="section"><div class="container narrow prose">'
        f'<h2>Arbejdsdage {year} — samlet oversigt og variation</h2>'
        f'<p>I {year} er der <strong>{stats["workdays"]} arbejdsdage</strong> efter standardtællingen '
        f'(mandag til fredag minus officielle helligdage) og '
        f'<strong>{stats["office_workdays"]} arbejdsdage</strong> i kontor-varianten, som også trækker 1. maj, '
        f'grundlovsdag, juleaftensdag og nytårsaftensdag fra. '
        f'Sammenlignet med {year - 1} ({stats_prev["workdays"]} standardarbejdsdage) er det {diff_prev_txt} — '
        f'og sammenlignet med {year + 1} ({stats_next["workdays"]}) er der {diff_next_txt}.</p>'
        f'<p>Variationen fra år til år kommer primært fra to kilder. For det første <strong>hvordan påsken flytter sig</strong>: '
        f'i {year} er påskedag {_fmt_dansk_dato(e_ctx["date"])} — {e_ctx["position"]} placeret. Det påvirker fordelingen '
        f'af skærtorsdag, langfredag, 2. påskedag, Kristi himmelfartsdag og pinsen mellem hverdage og weekender. '
        f'For det andet <strong>hvor mange helligdage der falder på en lørdag eller søndag</strong> — i {year} er det '
        f'<strong>{weekend_hol}</strong> af de officielle helligdage, som "spildes" i den forstand, at de ikke giver ekstra fri.</p>'
        f'<h3>Sammenligning: 5-års oversigt</h3>'
        f'<div class="table-wrap"><table><thead><tr><th>År</th><th>Arbejdsdage (standard)</th><th>Kontor-variant</th></tr></thead><tbody>{comp_rows}</tbody></table></div>'
        f'<p class="muted">Se også <a href="/bedste-feriedage-{year}.html">bedste feriedage {year}</a> for hvordan du '
        f'får mest ud af de feriedage, du har til rådighed, samt <a href="/helligdage-{year}.html">helligdage {year}</a> '
        f'for den fulde oversigt over de officielle helligdage.</p>'
        f'</div></section>'
    )

    body += ad_slot("footer")
    body += aarsanalyse_sektion(year, "arbejdsdage")
    write_page(
        f"arbejdsdage-{year}.html",
        f"Arbejdsdage {year} - antal arbejdsdage pr. måned",
        f"Se hvor mange arbejdsdage der er i {year}, måned for måned.",
        body,
        "arbejdsdage",
        breadcrumbs=[("Forside", "index.html"), ("Arbejdsdage", f"arbejdsdage-{ACTIVE_YEAR}.html"), (str(year), "")],
    )


def render_easter(year: int) -> None:
    e = easter_sunday(year)
    rows = [
        ("Palmesøndag", e - timedelta(days=7)),
        ("Skærtorsdag", e - timedelta(days=3)),
        ("Langfredag", e - timedelta(days=2)),
        ("Påskedag", e),
        ("2. påskedag", e + timedelta(days=1)),
    ]
    faq = [
        (
            f"Hvornår er påske {year}?",
            f"Påskedag er {fmt_date(e)} ({WEEKDAYS_LONG[e.weekday()]}). "
            f"Skærtorsdag er {fmt_date(e - timedelta(days=3))} og langfredag {fmt_date(e - timedelta(days=2))}. "
            f"2. påskedag er {fmt_date(e + timedelta(days=1))}.",
        ),
        (
            "Er påske en helligdag i Danmark?",
            "Ja. Skærtorsdag, langfredag, påskedag og 2. påskedag er alle officielle helligdage i Danmark.",
        ),
        (
            "Hvordan beregnes påsken?",
            "Påskedag er den første søndag efter den første fuldmåne på eller efter forårsjævndøgn. "
            "Vi bruger Meeus/Jones/Butcher-algoritmen til at finde datoen.",
        ),
        (
            "Hvor mange feriedage giver påsken?",
            "Påsken kan give op til 5 sammenhængende fridage (skærtorsdag til 2. påskedag) uden at bruge feriedage, "
            "afhængigt af hvilken weekendsammenhæng man har.",
        ),
    ]
    ctx = easter_year_context(year)
    delta_prev = ctx["delta_prev_days"]
    delta_next = ctx["delta_next_days"]
    delta_prev_txt = ("samme dag som" if delta_prev == 0 else
                      f"{abs(delta_prev)} dag{'e' if abs(delta_prev) != 1 else ''} {'senere' if delta_prev > 0 else 'tidligere'} end")
    delta_next_txt = ("samme dag som" if delta_next == 0 else
                      f"{abs(delta_next)} dag{'e' if abs(delta_next) != 1 else ''} {'senere' if delta_next < 0 else 'tidligere'} end")
    fri_start = e - timedelta(days=3)  # skærtorsdag
    fri_end = e + timedelta(days=1)    # 2. påskedag
    length = (fri_end - fri_start).days + 1
    extra = (
        f'<section class="section"><div class="container narrow prose">'
        f'<h2>Påsken i {year}: dato, ugedag og placering</h2>'
        f'<p>Påskedag {year} er <strong>{_fmt_dansk_dato(e)}</strong>. Det er en '
        f'{WEEKDAYS_LONG[e.weekday()].lower()}, og på den kristne kalender den vigtigste søndag i året. '
        f'Datoen er dermed placeret <em>{ctx["position"]}</em> i det spænd påsken kan falde i — '
        f'fra 22. marts (tidligst) til 25. april (senest).</p>'
        f'<p>Sammenlignet med naboårene falder påsken '
        f'{delta_prev_txt} {ctx["prev_year"]} ({_fmt_dansk_dato(ctx["prev_date"])}) og '
        f'{delta_next_txt} {ctx["next_year"]} ({_fmt_dansk_dato(ctx["next_date"])}). '
        f'Årsagen til, at datoen flytter sig så meget år for år, er, at kirkeåret følger månecyklussen: '
        f'påskedag er den første søndag efter den første fuldmåne på eller efter forårsjævndøgn. '
        f'Vi bruger Meeus/Jones/Butcher-algoritmen til at finde datoen.</p>'
        f'<h3>Ferieplanlægning omkring påsken {year}</h3>'
        f'<p>Skærtorsdag ({_fmt_dansk_dato(fri_start)}) og langfredag ({_fmt_dansk_dato(e - timedelta(days=2))}) er begge officielle helligdage. '
        f'Sammen med den efterfølgende weekend og 2. påskedag ({_fmt_dansk_dato(fri_end)}) giver det en sammenhængende blok '
        f'på <strong>{length} kalenderdage</strong> — fra skærtorsdag til 2. påskedag — hvor de fleste ansatte har fri uden at bruge feriedage. '
        f'Overenskomstansatte i den offentlige sektor har normalt hele blokken fri, mens vilkårene kan variere for privatansatte. '
        f'Tjek din overenskomst, hvis du er i tvivl.</p>'
        f'</div></section>'
    )
    extra += aarsanalyse_sektion(year, "paaske")
    render_event_page(
        year,
        "Påske",
        "paaske",
        rows,
        "Påsken styrer også datoerne for Kristi himmelfartsdag og pinse.",
        panel_month=e.month,
        faq=faq,
        extra_html=extra,
    )


def render_pentecost(year: int) -> None:
    e = easter_sunday(year)
    pinse = e + timedelta(days=49)
    rows = [("Pinsedag", pinse), ("2. pinsedag", e + timedelta(days=50))]
    faq = [
        (
            f"Hvornår er pinse {year}?",
            f"Pinsedag er {fmt_date(pinse)} ({WEEKDAYS_LONG[pinse.weekday()]}) "
            f"og 2. pinsedag er {fmt_date(e + timedelta(days=50))}.",
        ),
        (
            "Er pinse en helligdag?",
            "Ja. Både pinsedag og 2. pinsedag er officielle helligdage i Danmark.",
        ),
        (
            "Hvor mange dage efter påske falder pinse?",
            "Pinsedag er 49 dage efter påskedag, og 2. pinsedag dagen efter.",
        ),
        (
            "Hvad er forskellen på pinsedag og 2. pinsedag?",
            "Pinsedag falder altid på en søndag, og 2. pinsedag er den efterfølgende mandag. "
            "Begge er officielle helligdage med løn for mange ansatte.",
        ),
    ]
    pinse2 = e + timedelta(days=50)
    pinse_prev = easter_sunday(year - 1) + timedelta(days=49)
    pinse_next = easter_sunday(year + 1) + timedelta(days=49)
    ctx = easter_year_context(year)
    weekend_holidays = _weekend_holidays_in_year(year)
    # Pinse can fall between 10 May (Easter 22 Mar) and 13 June (Easter 25 Apr)
    doy_pinse = pinse.timetuple().tm_yday
    pinse_pos = ("tidligt" if doy_pinse <= (date(year, 5, 20) - date(year, 1, 1)).days + 1
                 else "sent" if doy_pinse >= (date(year, 6, 3) - date(year, 1, 1)).days + 1
                 else "midt")
    extra = (
        f'<section class="section"><div class="container narrow prose">'
        f'<h2>Pinse i {year} — hvor tidligt eller sent?</h2>'
        f'<p>Pinsedag {year} falder på <strong>{_fmt_dansk_dato(pinse)}</strong> og 2. pinsedag på '
        f'{_fmt_dansk_dato(pinse2)}. Det placerer pinsen <em>{pinse_pos}</em> i sit muligheds­spænd. '
        f'Da pinsen ligger præcis 49 dage efter påskedag, følger den påskens datospænd én-til-én: '
        f'pinsen kan tidligst falde 10. maj (hvis påske er 22. marts) og senest 13. juni (hvis påske er 25. april). '
        f'I {year} betyder påskens {ctx["position"]} placering, at også pinsen er {pinse_pos}.</p>'
        f'<p>Til sammenligning: pinsedag {year - 1} var {_fmt_dansk_dato(pinse_prev)}, '
        f'og pinsedag {year + 1} bliver {_fmt_dansk_dato(pinse_next)}. '
        f'Den store år-til-år bevægelse skyldes, at pinsen hænger sammen med månecyklussen bag påsken — '
        f'ikke med den borgerlige kalender.</p>'
        f'<h3>Lang weekend med pinsen i {year}</h3>'
        f'<p>Pinsedag falder altid på en søndag, og 2. pinsedag er den efterfølgende mandag. '
        f'Sammen med den forudgående lørdag giver det <strong>tre sammenhængende fridage</strong> uden brug af feriedage. '
        f'For {year} betyder det weekenden fra lørdag den {_fmt_dansk_dato(pinse - timedelta(days=1))} '
        f'til mandag den {_fmt_dansk_dato(pinse2)}. '
        f'Ved at tage én feriedag om fredagen den {_fmt_dansk_dato(pinse - timedelta(days=2))} strækker man weekenden til fire dage.</p>'
        f'<p class="muted">Bemærk: I {year} falder i alt {weekend_holidays} af de officielle helligdage på en weekend, '
        f'hvilket påvirker det samlede antal arbejdsdage i året. '
        f'Se <a href="/arbejdsdage-{year}.html">arbejdsdage {year}</a> for hele opgørelsen.</p>'
        f'</div></section>'
    )
    extra += aarsanalyse_sektion(year, "pinse")
    render_event_page(
        year,
        "Pinse",
        "pinse",
        rows,
        "Pinse falder 49 og 50 dage efter påskedag.",
        panel_month=pinse.month,
        faq=faq,
        extra_html=extra,
    )


def render_ascension(year: int) -> None:
    e = easter_sunday(year)
    kristi = e + timedelta(days=39)
    rows = [("Kristi himmelfartsdag", kristi), ("Fredag efter Kr. Himmelfart", e + timedelta(days=40))]
    faq = [
        (
            f"Hvornår er Kristi himmelfartsdag {year}?",
            f"Kristi himmelfartsdag er {fmt_date(kristi)} ({WEEKDAYS_LONG[kristi.weekday()]}).",
        ),
        (
            "Er Kristi himmelfartsdag en helligdag?",
            "Ja. Kristi himmelfartsdag er en officiel helligdag i Danmark og falder altid på en torsdag.",
        ),
        (
            "Er fredagen efter Kristi himmelfart en fridag?",
            "Fredagen er ikke en officiel helligdag, men mange arbejdspladser og skoler holder klemmedag eller "
            "indlægger fridag efter overenskomst.",
        ),
        (
            "Hvor mange dage efter påske falder Kristi himmelfartsdag?",
            "Kristi himmelfartsdag er 39 dage efter påskedag og dermed 10 dage før pinsedag.",
        ),
    ]
    kristi_prev = easter_sunday(year - 1) + timedelta(days=39)
    kristi_next = easter_sunday(year + 1) + timedelta(days=39)
    fredag = e + timedelta(days=40)
    ctx = easter_year_context(year)
    long_weekend_end = e + timedelta(days=42)  # torsdag → søndag = 4 dage
    extra = (
        f'<section class="section"><div class="container narrow prose">'
        f'<h2>Kristi himmelfartsdag {year}: torsdag med klemmedag</h2>'
        f'<p>Kristi himmelfartsdag falder altid på en torsdag, præcis 39 dage efter påskedag. '
        f'I {year} er datoen <strong>{_fmt_dansk_dato(kristi)}</strong>. Fredagen efter — '
        f'{_fmt_dansk_dato(fredag)} — er ikke en officiel helligdag, men mange arbejdspladser og skoler '
        f'holder den som klemmedag for at strække weekenden ud. Praksis varierer mellem brancher og overenskomster.</p>'
        f'<p>Med fredagen som klemmedag får man i {year} <strong>fire sammenhængende fridage</strong>: '
        f'fra torsdag den {_fmt_dansk_dato(kristi)} til søndag den {_fmt_dansk_dato(long_weekend_end)}. '
        f'Sammenligner man med naboårene, var Kristi himmelfartsdag {ctx["prev_year"]} den {_fmt_dansk_dato(kristi_prev)} '
        f'og bliver i {ctx["next_year"]} den {_fmt_dansk_dato(kristi_next)}. '
        f'Rytmen følger påskedatoen — påsken flytter sig, og med den også Kristi himmelfartsdag.</p>'
        f'<h3>Historik og betydning</h3>'
        f'<p>Kristi himmelfartsdag mindes Jesu himmelfart fyrre dage efter opstandelsen. '
        f'Kristendommen har markeret dagen siden det 4. århundrede, og den er en af Danmarks ni officielle helligdage. '
        f'Bemærk: Store bededag, som ligger fire uger før Kristi himmelfartsdag, blev afskaffet som officiel helligdag '
        f'fra og med 2024 ved lov L 3. Det ændrer ikke Kristi himmelfartsdags status.</p>'
        f'</div></section>'
    )
    extra += aarsanalyse_sektion(year, "himmelfart")
    render_event_page(
        year,
        "Kristi himmelfartsdag",
        "kristi-himmelfartsdag",
        rows,
        "Kristi himmelfartsdag falder altid på en torsdag, 39 dage efter påskedag.",
        panel_month=kristi.month,
        faq=faq,
        extra_html=extra,
    )


def render_event_page(
    year: int,
    name: str,
    slug: str,
    rows: list[tuple[str, date]],
    note: str,
    panel_month: int = 1,
    faq: list[tuple[str, str]] | None = None,
    extra_html: str = "",
) -> None:
    table = "".join(
        f"<tr><td>{label}</td><td>{fmt_date(d)}</td><td>{WEEKDAYS_LONG[d.weekday()]}</td></tr>"
        for label, d in rows
    )
    body = hero(
        f"{name} {year}",
        f"Datoer for {name.lower()} i {year}. {note}",
        year,
        panel=(year, panel_month),
    )
    body += ad_slot("header")
    body += f'<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Dag</th><th>Dato</th><th>Ugedag</th></tr></thead><tbody>{table}</tbody></table></div></div></section>'
    if extra_html:
        body += extra_html
    body += ad_slot("mid")
    write_page(
        f"{slug}-{year}.html",
        f"{name} {year} - datoer i Danmark",
        f"Se dato for {name.lower()} {year} og de tilknyttede fridage.",
        body,
        "helligdage",
        breadcrumbs=[
            ("Forside", "index.html"),
            ("Helligdage", f"helligdage-{ACTIVE_YEAR}.html"),
            (name, ""),
            (str(year), ""),
        ],
        faq=faq,
    )


def render_best_vacation(year: int) -> None:
    windows = build_best_vacation_windows(year)
    rows = "".join(
        f"<tr><td>{fmt_date(item['start'])} - {fmt_date(item['end'])}</td><td>{item['days_off']}</td><td>{item['vacation_days']}</td><td>{item['holidays']}</td><td>{item['ratio']:.1f}x</td></tr>"
        for item in windows
    )
    body = hero(
        f"Bedste feriedage {year}",
        f"Forslag til hvordan du kan få flere sammenhængende fridage i {year} ved at placere feriedage omkring weekender og helligdage.",
        year,
        panel=(year, 1),
    )
    body += ad_slot("header")
    body += f'<section class="section"><div class="container"><div class="table-wrap"><table><thead><tr><th>Periode</th><th>Dage fri i alt</th><th>Feriedage brugt</th><th>Helligdage i perioden</th><th>Effekt</th></tr></thead><tbody>{rows}</tbody></table></div><p class="notice">Forslagene bruger kun officielle helligdage og weekender. Tjek altid din overenskomst, lokale fridage og arbejdsgiverens regler.</p></div></section>'
    body += ad_slot("mid")

    # ---- Year-specific prose block ----
    e_ctx = easter_year_context(year)
    top = windows[0] if windows else None
    # Group windows by broad calendar season
    q1 = [w for w in windows if w["start"].month <= 3]
    q2 = [w for w in windows if 4 <= w["start"].month <= 6]
    q3 = [w for w in windows if 7 <= w["start"].month <= 9]
    q4 = [w for w in windows if w["start"].month >= 10]
    top_ratio = top["ratio"] if top else 0
    top_desc = (
        f"{fmt_date(top['start'])} til {fmt_date(top['end'])} — {top['days_off']} fridage for {top['vacation_days']} feriedag(e), {top['ratio']:.1f}x"
        if top else "ingen kandidatvinduer fundet"
    )
    stats = year_stats(year)
    weekend_hol = _weekend_holidays_in_year(year)
    body += (
        f'<section class="section"><div class="container narrow prose">'
        f'<h2>Feriedags-strategi for {year}</h2>'
        f'<p>Den bedste enkeltperiode i {year} er <strong>{top_desc}</strong>. Effekten på {top_ratio:.1f}x betyder, '
        f'at du får {top_ratio:.1f} gange så mange sammenhængende fridage, som du bruger feriedage på.</p>'
        f'<p>Fordelingen af de bedste vinduer i {year} følger påskens placering: '
        f'påsken er {e_ctx["position"]} placeret ({_fmt_dansk_dato(e_ctx["date"])}), hvilket rykker skærtorsdag, '
        f'langfredag, 2. påskedag, Kristi himmelfartsdag og pinsen ind i konkrete uger. '
        f'Af de {len(windows)} kandidatvinduer, vi har fundet i {year}, ligger '
        f'{len(q1)} i 1. kvartal, {len(q2)} i 2. kvartal, {len(q3)} i 3. kvartal og {len(q4)} i 4. kvartal. '
        f'Året har i alt {stats["workdays"]} arbejdsdage efter standardtællingen, og {weekend_hol} af de officielle '
        f'helligdage falder på en weekend — det påvirker naturligvis, hvor mange strategiske vinduer der overhovedet er.</p>'
        f'<h3>Sådan læses tabellen</h3>'
        f'<ul>'
        f'<li><strong>Periode</strong> viser start- og slutdato for den sammenhængende blok fridage.</li>'
        f'<li><strong>Dage fri i alt</strong> er summen af weekender, helligdage og feriedage i perioden.</li>'
        f'<li><strong>Feriedage brugt</strong> er de dage, du selv trækker fra din feriekonto.</li>'
        f'<li><strong>Helligdage i perioden</strong> er de officielle helligdage, du "får med".</li>'
        f'<li><strong>Effekt</strong> er forholdet mellem samlede fridage og feriedage brugt. Højere er bedre.</li>'
        f'</ul>'
        f'<p class="muted">Se også <a href="/arbejdsdage-{year}.html">arbejdsdage {year}</a> for hele opgørelsen '
        f'af arbejdsdage måned for måned, samt <a href="/helligdage-{year}.html">helligdage {year}</a> for '
        f'placeringen af de officielle helligdage.</p>'
        f'</div></section>'
    )

    write_page(
        f"bedste-feriedage-{year}.html",
        f"Bedste feriedage {year} - få mere fri",
        f"Se gode perioder at holde ferie i {year}, baseret på helligdage og weekender.",
        body,
        "ferieplan",
        breadcrumbs=[
            ("Forside", "index.html"),
            ("Ferieplan", f"bedste-feriedage-{ACTIVE_YEAR}.html"),
            (str(year), ""),
        ],
    )


def render_tools() -> None:
    today = date.today().isoformat()
    body = hero("Beregn arbejdsdage mellem to datoer", "Vælg start- og slutdato og se antal arbejdsdage i perioden. Du kan vælge standard eller en kontor-variant med almindelige fridage.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="tool"><div class="tool-grid"><div class="field"><label for="bd-start">Startdato</label><input id="bd-start" type="date" value="{today}"></div><div class="field"><label for="bd-end">Slutdato</label><input id="bd-end" type="date" value="{today}"></div><div class="field"><label for="bd-mode">Regel</label><select id="bd-mode"><option value="official">Kun officielle helligdage</option><option value="office">Kontor-variant</option></select></div></div><div id="bd-result" class="result-box"></div></div></div></section>"""
    body += ad_slot("header")
    body += '<section class="section"><div class="container narrow prose">'
    body += (
        '<h2>Sådan tælles arbejdsdagene</h2><p>Beregneren tæller de hverdage, der ligger i perioden, og trækker weekender og officielle danske helligdage fra. Både start- og slutdato regnes med, hvis de er arbejdsdage — vælger du samme dag i begge felter, og det er en tirsdag, får du altså 1 og ikke 0.</p><h3>De to regelsæt</h3><p><strong>Kun officielle helligdage</strong> følger loven: nytårsdag, skærtorsdag, langfredag, påskedag, 2. påskedag, Kristi himmelfartsdag, pinsedag, 2. pinsedag, juledag og 2. juledag. <strong>Kontor-varianten</strong> trækker desuden 1. maj, grundlovsdag, juleaftensdag og nytårsaftensdag fra. De fire dage er ikke helligdage efter loven, men holdes fri på mange arbejdspladser efter overenskomst eller kutyme. Er du i tvivl om, hvad der gælder hos jer, giver det laveste af de to tal det forsigtige skøn.</p><h3>Hvad beregningen ikke ved</h3><p>Ferie, sygdom, barsel, afspadsering og lokale lukkedage indgår ikke — det er tal for kalenderen, ikke for en konkret ansættelse. Store bededag blev afskaffet som helligdag i 2024 og tælles derfor som en almindelig arbejdsdag. Beregningen gælder Danmark; Færøerne og Grønland har egne helligdage.</p><h3>Typiske anvendelser</h3><p>Antal arbejdsdage bruges blandt andet til at anslå leveringstid i hverdage, til at beregne opsigelsesvarsler i arbejdsdage, til at fordele et budget eller en timenormering over et kvartal, og til at kontrollere en faktura for konsulenttimer. Skal du den anden vej — fra et antal arbejdsdage til en dato — så brug <a href="laeg-arbejdsdage-til.html">Læg arbejdsdage til</a>.</p>'
    )
    body += "</div></section>"

    body += tools_related_grid("beregn-arbejdsdage.html")
    body += ad_slot("mid")
    write_page(
        "beregn-arbejdsdage.html",
        "Beregn arbejdsdage mellem to datoer",
        "Gratis beregner for arbejdsdage mellem to datoer i Danmark.",
        body,
        "arbejdsdage",
        breadcrumbs=[("Forside", "index.html"), ("Beregn arbejdsdage", "")],
    )

    body = hero("Læg arbejdsdage til en dato", "Find datoen efter et bestemt antal arbejdsdage. Beregneren springer weekender og danske helligdage over.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="tool"><div class="tool-grid"><div class="field"><label for="add-start">Startdato</label><input id="add-start" type="date" value="{today}"></div><div class="field"><label for="add-amount">Antal arbejdsdage</label><input id="add-amount" type="number" min="0" value="10"></div><div class="field"><label for="add-mode">Regel</label><select id="add-mode"><option value="official">Kun officielle helligdage</option><option value="office">Kontor-variant</option></select></div></div><div id="add-result" class="result-box"></div></div></div></section>"""
    body += ad_slot("header")
    body += '<section class="section"><div class="container narrow prose">'
    body += (
        '<h2>Sådan regnes datoen ud</h2><p>Beregneren starter dagen <em>efter</em> din startdato og tæller frem, indtil den har passeret det antal arbejdsdage, du har angivet. Weekender og helligdage springes over undervejs — de tæller ikke med, men de skubber slutdatoen længere frem i kalenderen. Startdatoen tælles aldrig med som en af arbejdsdagene, hvilket er den sædvanlige fortolkning af formuleringer som «senest 10 arbejdsdage efter».</p><h3>Et regnet eksempel</h3><p>Starter du en fredag og beder om 3 arbejdsdage, lander du onsdag: lørdag og søndag springes over, og mandag, tirsdag og onsdag er de tre arbejdsdage. Falder der en helligdag ind i ugen, rykker resultatet en dag længere frem. Omkring påsken kan tre arbejdsdage derfor sagtens strække sig over halvanden uge i kalenderen.</p><h3>Frister og varsler</h3><p>Fristerne i dansk lovgivning og i standardkontrakter er ofte formuleret i arbejdsdage netop for at undgå, at en weekend eller en helligdag afkorter den reelle svartid. Bemærk dog, at ikke alle frister regnes ens: nogle løber i kalenderdage, andre i hverdage, og nogle udskydes til førstkommende hverdag, hvis de ender i en weekend. Tjek den præcise ordlyd i aftalen, før du regner en frist for endelig.</p><p>Skal du modsat vide, hvor mange arbejdsdage der ligger mellem to kendte datoer, så brug <a href="beregn-arbejdsdage.html">Beregn arbejdsdage</a>. Skal du gå baglæns fra en deadline, findes <a href="traek-arbejdsdage-fra.html">Træk arbejdsdage fra</a>.</p>'
    )
    body += "</div></section>"

    body += tools_related_grid("laeg-arbejdsdage-til.html")
    body += ad_slot("mid")
    write_page(
        "laeg-arbejdsdage-til.html",
        "Læg arbejdsdage til en dato",
        "Beregn datoen efter X arbejdsdage i Danmark.",
        body,
        "arbejdsdage",
        breadcrumbs=[("Forside", "index.html"), ("Læg arbejdsdage til", "")],
    )

    body = hero("Ugenummer", "Find ISO-ugenummer for en dato i Danmark. Danske kalendere bruger normalt ISO-uger, hvor ugen starter mandag.", date.today().year)
    body += f"""<section class="section"><div class="container"><div class="tool"><div class="tool-grid"><div class="field"><label for="week-date">Dato</label><input id="week-date" type="date" value="{today}"></div></div><div id="week-result" class="result-box"></div></div></div></section>"""
    body += ad_slot("header")
    body += '<section class="section"><div class="container narrow prose">'
    body += (
        '<h2>Sådan fungerer ISO-ugenumre</h2><p>Danmark bruger ISO 8601 til ugenumre, og standarden har to regler, der forklarer næsten al forvirring om emnet: <strong>ugen begynder mandag</strong>, og <strong>uge 1 er den uge, der indeholder årets første torsdag</strong>. Reglen om torsdagen svarer til at sige, at uge 1 er den første uge, hvor mindst fire dage ligger i det nye år.</p><h3>Derfor kan 1. januar ligge i uge 52</h3><p>Falder nytårsdag på en fredag, lørdag eller søndag, hører de første dage af januar til det gamle års sidste uge — og omvendt kan de sidste dage af december tilhøre uge 1 i det nye år. Det er ikke en fejl i kalenderen, men en konsekvens af, at en uge ikke må deles mellem to årstal. Derfor angiver ISO-formatet også året sammen med ugen, for eksempel 2027-W01.</p><h3>År med 53 uger</h3><p>De fleste år har 52 uger, men cirka hvert femte til sjette år rummer 53. Det sker, når året begynder på en torsdag, eller når et skudår begynder på en onsdag. For lønsystemer og vagtplaner, der regner i uger, er de år værd at holde øje med.</p><h3>Ikke det samme som amerikanske uger</h3><p>I USA og en række andre lande begynder ugen søndag, og uge 1 er ganske enkelt den uge, 1. januar falder i. Det giver ofte et ugenummer, der ligger én foran det danske. Arbejder du i regneark eller systemer med engelske standardindstillinger, er det værd at kontrollere, hvilken definition der er slået til — i regneark findes typisk begge varianter som forskellige funktioner.</p><p>Skal du den anden vej, fra ugenummer til dato, så brug <a href="dato-fra-uge.html">Dato fra ugenummer</a>.</p>'
    )
    body += "</div></section>"

    body += tools_related_grid("ugenummer.html")
    body += ad_slot("mid")
    write_page(
        "ugenummer.html",
        "Ugenummer - find uge for en dato",
        "Find ugenummer for en dato i Danmark.",
        body,
        "ugenummer",
        breadcrumbs=[("Forside", "index.html"), ("Ugenummer", "")],
    )


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
    body += ad_slot("header")
    body += '<section class="section"><div class="container"><p class="notice">Skoleferier er ikke en matematisk kalenderregel. Kommunerne kan have forskellige datoer, og skoler kan have lokale afvigelser. Brug tabellen som hurtigt overblik og tjek altid kommunens egen side.</p><div class="grid">' + "".join(cards) + '</div><div class="table-wrap"><table><thead><tr><th>Kommune</th><th>Skoleår</th><th>Ferie/fridag</th><th>Fra</th><th>Til</th><th>Kilde</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div></div></section>"
    body += ad_slot("mid")
    write_page(
        "skoleferier.html",
        "Skoleferier - ferieplaner i store danske kommuner",
        "Skoleferier for udvalgte store kommuner i Danmark med officielle kilder.",
        body,
        "skoleferier",
        breadcrumbs=[("Forside", "index.html"), ("Skoleferier", "")],
    )
    for municipality_data in data["municipalities"]:
        render_school_municipality(municipality_data, data.get("updated", ""), data["municipalities"])


def _skole_dage(h: dict) -> int:
    """Antal kalenderdage i en ferieperiode, begge dage inklusive."""
    a = date.fromisoformat(h["start"])
    b = date.fromisoformat(h["end"])
    return (b - a).days + 1


def _vinterferie_uge(m: dict) -> int | None:
    """Skoleugen for vinterferien — ikke ISO-ugen for startdatoen.

    Kommunerne angiver ferien fra loerdagen for, saa startdatoens ISO-uge
    ligger en uge for tidligt: Aarhus' "13. februar 2027" er loerdag i uge 6,
    men skoleugen er uge 7. Derfor regnes ugen fra den forste hverdag.
    """
    for h in m["holidays"]:
        if h["name"].lower().startswith("vinterferie"):
            d = date.fromisoformat(h["start"])
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d.isocalendar().week
    return None


def skoleferie_analyse(m: dict, alle: list[dict]) -> str:
    """Beregnet, kommunespecifik gennemgang — ikke den samme tekst pr. by.

    Uden det her var de ti kommunesider naesten identiske: samme tabel,
    samme standardtekst. Her regnes tal ud af kommunens egen ferieplan og
    holdes op mod de ovrige kommuner paa sitet.
    """
    if not m["holidays"]:
        return ""

    dage = sum(_skole_dage(h) for h in m["holidays"])
    laengste = max(m["holidays"], key=_skole_dage)
    sommer = next((h for h in m["holidays"] if h["name"].lower().startswith("sommerferie")), None)
    uge = _vinterferie_uge(m)

    # Vinterferien er det klassiske skel mellem kommunerne: uge 7 eller uge 8.
    uger = {}
    for anden in alle:
        u = _vinterferie_uge(anden)
        if u:
            uger.setdefault(u, []).append(anden["name"])
    sammenligning = ""
    if uge and uger:
        andre_samme = [n for n in uger.get(uge, []) if n != m["name"]]
        andre_uger = sorted(u for u in uger if u != uge)
        if andre_uger:
            fordeling = " og ".join(
                f"uge {u} i {_liste(sorted(uger[u]))}" for u in andre_uger
            )
            sammenligning = (
                f"<p>Vinterferien er det punkt, hvor kommunerne oftest er uenige. "
                f"{m['name']} holder <strong>vinterferie i uge {uge}</strong>"
                + (f", ligesom {_liste(sorted(andre_samme))}" if andre_samme else "")
                + f". Til sammenligning ligger den i {fordeling}. "
                f"Har du børn i skole i to kommuner — eller familie på tværs af landet — "
                f"er det her, planerne typisk kolliderer.</p>"
            )
        else:
            sammenligning = (
                f"<p>{m['name']} holder vinterferie i uge {uge}, hvilket er samme uge som de "
                f"øvrige kommuner på sitet.</p>"
            )

    sommer_tekst = ""
    if sommer:
        s_start = date.fromisoformat(sommer["start"])
        s_dage = _skole_dage(sommer)
        sommer_tekst = (
            f"<p>Sommerferien begynder <strong>{WEEKDAYS_LONG[s_start.weekday()]} den "
            f"{_fmt_dansk_dato(s_start)}</strong> og varer {s_dage} dage. Starten er ikke "
            f"kommunens frie valg: efter folkeskoleloven begynder sommerferien den sidste "
            f"lørdag i juni, og skoleåret skal rumme mindst 200 skoledage. Det er "
            f"placeringen af de <em>øvrige</em> ferier, kommunalbestyrelsen bestemmer.</p>"
        )

    return (
        '<section class="section"><div class="container narrow prose">'
        f"<h2>Sådan ligger ferieplanen i {m['name']}</h2>"
        f"<p>Ferieplanen for {m['name']} rummer <strong>{len(m['holidays'])} ferieperioder</strong> "
        f"med i alt <strong>{dage} fridage</strong> talt i kalenderdage, weekender inklusive. "
        f"Den længste sammenhængende periode er {laengste['name'].lower()} med "
        f"{_skole_dage(laengste)} dage.</p>"
        + sommer_tekst
        + sammenligning
        + "<h3>Hvem bestemmer datoerne</h3>"
        "<p>Skoleferier fastsættes <strong>lokalt af kommunalbestyrelsen</strong> og kan variere "
        "fra skole til skole inden for samme kommune — enkelte skoler lægger egne lukkedage eller "
        "flytter en fridag efter aftale i skolebestyrelsen. Planerne vedtages typisk et til to år "
        "frem og kan blive ændret undervejs. Derfor gælder tabellen ovenfor som overblik, ikke som "
        "en garanti: før du booker en rejse, så tjek datoen på kommunens egen side, som der linkes "
        "til øverst.</p>"
        "<h3>SFO og pasning</h3>"
        "<p>At skolen holder ferie betyder ikke nødvendigvis, at SFO'en gør det. De fleste "
        "kommuner holder feriepasning åben i skoleferierne, ofte med tilmelding i god tid og "
        "eventuelt på en anden matrikel end til daglig. Mellem jul og nytår og på enkelte "
        "klemmedage er der derimod ofte lukket. Reglerne står på kommunens side.</p>"
        "</div></section>"
    )


def render_school_municipality(m: dict, updated: str, alle: list[dict] | None = None) -> None:
    rows = "".join(
        f'<tr><td>{h["school_year"]}</td><td>{h["name"]}</td><td>{h["start"]}</td><td>{h["end"]}</td></tr>'
        for h in m["holidays"]
    )
    body = hero(f"Skoleferier i {m['name']}", f"Ferieplan og fridage for skoler i {m['name']}. Datoerne er samlet som et hurtigt overblik med kilde til kommunens egen side.", date.today().year)
    body += ad_slot("header")
    body += f'<section class="section"><div class="container"><div class="grid"><article class="card"><h3>Senest gennemgået</h3><p class="stat">{updated}</p><p class="muted">Tjek altid kommunens egen kalender ved planlægning.</p></article><article class="card"><h3>Officiel kilde</h3><p><a class="text-link" href="{m["source"]}" rel="nofollow noopener" target="_blank">Åbn kommunens side</a></p></article></div><div class="table-wrap"><table><thead><tr><th>Skoleår</th><th>Ferie/fridag</th><th>Fra</th><th>Til</th></tr></thead><tbody>{rows}</tbody></table></div><p class="notice">Nogle skoler kan have lokale afvigelser, særlige lukkedage eller behovsåbent i SFO. Brug derfor siden som hurtigt overblik og verificer altid hos kommunen eller skolen.</p></div></section>'
    body += skoleferie_analyse(m, alle or [m])
    body += ad_slot("mid")
    write_page(
        f"skoleferier-{m['slug']}.html",
        f"Skoleferier {m['name']} - ferieplan og fridage",
        f"Se skoleferier og fridage for {m['name']} kommune med kilde til den officielle ferieplan.",
        body,
        "skoleferier",
        breadcrumbs=[("Forside", "index.html"), ("Skoleferier", "skoleferier.html"), (m["name"], "")],
    )


def render_methodology() -> None:
    """Metode: hvordan datoerne beregnes. Vigtigt E-E-A-T-signal for AdSense."""
    lo, hi = YEAR_SPAN
    body = hero(
        "Metode",
        "Hvordan datoerne på DanskeDage beregnes, hvad der er lovbestemt, "
        "og hvor grænserne for beregningerne går.",
    )
    body += (
        '<section class="section"><div class="container narrow prose">'
        "<h2>Hvad sitet regner ud — og hvordan</h2>"
        "<p>Alle datoer på DanskeDage er <strong>beregnet, ikke indtastet</strong>. "
        "Kalenderen, helligdagene og arbejdsdagene bliver genereret af et program, der kører "
        "hver nat, så siderne altid viser det indeværende år korrekt. Det betyder også, at der "
        "ikke ligger en manuelt vedligeholdt liste, som kan blive glemt et år.</p>"

        "<h3>De bevægelige helligdage</h3>"
        "<p>Påskedag er omdrejningspunktet for hele forårets fridage. Den beregnes med "
        "<em>Meeus/Jones/Butcher-algoritmen</em> for den gregorianske kalender: påskedag er den "
        "første søndag efter den første kirkelige fuldmåne på eller efter forårsjævndøgn. "
        "Bemærk ordet <em>kirkelige</em> — kirken regner efter faste tabeller, ikke efter den "
        "astronomiske fuldmåne, så de to kan afvige med en dag. Resten følger mekanisk af "
        "påskedagen: skærtorsdag ligger 3 dage før, langfredag 2 dage før, 2. påskedag dagen "
        "efter, Kristi himmelfartsdag 39 dage efter og pinsedag 49 dage efter.</p>"

        "<h3>De faste dage</h3>"
        "<p>Nytårsdag (1. januar), juledag (25. december) og 2. juledag (26. december) ligger "
        "fast. Det samme gør de dage, der <em>ikke</em> er officielle helligdage, men hvor mange "
        "alligevel har fri: 1. maj, grundlovsdag (5. juni), juleaftensdag og nytårsaftensdag. "
        "Sitet markerer dem som mærkedage, ikke som helligdage, fordi retten til fri afhænger af "
        "overenskomst eller lokal kutyme — ikke af loven.</p>"

        "<h3>Store bededag</h3>"
        "<p>Store bededag blev afskaffet som officiel helligdag fra og med 2024 ved lov nr. 214 af "
        "6. marts 2023. Dagen vises derfor som historisk mærkedag, og den tæller ikke med i "
        "arbejdsdage eller helligdage for årene på sitet.</p>"

        "<h3>Arbejdsdage</h3>"
        "<p>En arbejdsdag tælles som en hverdag (mandag til fredag), der ikke er en officiel "
        "helligdag. Sitet viser desuden et andet tal, hvor 1. maj, grundlovsdag, juleaftensdag og "
        "nytårsaftensdag er trukket fra — det svarer bedre til virkeligheden på mange "
        "arbejdspladser. Ferie, sygdom, barsel og lokale fridage indgår ikke; det er tal for "
        "kalenderen, ikke for den enkelte ansættelse.</p>"

        "<h3>Ugenumre</h3>"
        "<p>Ugenumre følger ISO 8601, som er den danske standard: ugen begynder mandag, og uge 1 "
        "er den uge, der indeholder årets første torsdag. Derfor kan 1. januar ligge i uge 52 "
        "eller 53 af det foregående år, og nogle år har 53 uger.</p>"

        "<h2>Hvad sitet ikke kan</h2>"
        "<p>Beregningerne siger noget om kalenderen — ikke om din kontrakt. Konkret:</p>"
        "<ul>"
        "<li><strong>Løn og tillæg:</strong> om en helligdag udløser tillæg, og hvor meget, står i "
        "din overenskomst eller ansættelseskontrakt.</li>"
        "<li><strong>Klemmedage:</strong> sitet peger på de dage, hvor en enkelt feriedag giver en "
        "lang weekend. Om du <em>kan</em> holde fri den dag, er en aftale med din arbejdsgiver.</li>"
        "<li><strong>Skoleferier:</strong> de fastsættes kommunalt og kan ændre sig. Datoerne på "
        "sitet er hentet fra kommunernes egne sider, og hver side linker til kilden, så du kan "
        "kontrollere den, før du booker noget.</li>"
        "<li><strong>Andre lande:</strong> alt på sitet gælder Danmark. Færøerne og Grønland har "
        "egne helligdage, som ikke er dækket.</li>"
        "</ul>"

        "<h2>Kontrol af tallene</h2>"
        f"<p>Helligdagsdatoerne for {lo}–{hi} er sammenholdt med de officielle oversigter fra "
        "Folkekirken og Kirkeministeriet, og ugenumrene er kontrolleret mod ISO 8601. Finder du "
        "en fejl, er en mail den hurtigste vej til at få den rettet — se "
        '<a href="kontakt.html">kontakt</a>.</p>'
        '<p class="muted">Senest gennemgået: 22. august 2026.</p>'
        "</div></section>"
    )
    write_page(
        "metode.html",
        "Metode — sådan beregnes datoerne",
        "Sådan beregner DanskeDage helligdage, arbejdsdage og ugenumre: algoritmer, "
        "lovgrundlag og hvad beregningerne ikke dækker.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Metode", "")],
        ads=False,
    )


def render_sources() -> None:
    """Kilder: hvor oplysningerne stammer fra."""
    body = hero(
        "Kilder",
        "De officielle kilder bag helligdage, ugenumre og skoleferier på DanskeDage.",
    )
    kilder = [
        ("Folkekirken — helligdage og kirkeåret",
         "https://www.folkekirken.dk/",
         "Grundlag for de bevægelige helligdage og deres placering i kirkeåret."),
        ("Lov nr. 214 af 6. marts 2023 om konsekvenser ved afskaffelsen af store bededag",
         "https://www.retsinformation.dk/eli/lta/2023/214",
         "Retsgrundlaget for, at store bededag ikke længere er en officiel helligdag."),
        ("Retsinformation — Lov om Danmarks Riges Grundlov",
         "https://www.retsinformation.dk/eli/lta/1953/169",
         "Grundlovsdag den 5. juni. Dagen er ikke en almindelig officiel helligdag, "
         "men fridag mange steder efter overenskomst."),
        ("ISO 8601 — dato- og tidsformat",
         "https://www.iso.org/iso-8601-date-and-time-format.html",
         "Standarden bag ugenumre: ugen starter mandag, og uge 1 indeholder årets "
         "første torsdag."),
        ("Danmarks Statistik",
         "https://www.dst.dk/",
         "Baggrundstal om arbejdsdage og beskæftigelse, brugt til at efterprøve "
         "rimeligheden af sitets egne optællinger."),
        ("Kommunernes egne sider om skoleferier",
         "https://www.kl.dk/",
         "Skoleferier fastsættes lokalt. Hver kommuneside på DanskeDage linker "
         "direkte til den kommunes egen offentliggørelse."),
    ]
    raekker = "".join(
        f"<li><p><strong>{navn}</strong><br>"
        f'<a href="{url}" rel="nofollow noopener" target="_blank">{url}</a><br>'
        f"<span class=\"muted\">{hvad}</span></p></li>"
        for navn, url, hvad in kilder
    )
    body += (
        '<section class="section"><div class="container narrow prose">'
        "<h2>Primære kilder</h2>"
        "<p>Datoerne på sitet er beregnede, men de regler, beregningerne bygger på, kommer fra "
        "de kilder, der står herunder. Astronomiske og kirkelige regler ændrer sig ikke, mens "
        "lovgivning og kommunale skoleferier gør — derfor gennemgås de sidste to hvert år.</p>"
        f"<ol>{raekker}</ol>"
        "<h2>Om links til kilderne</h2>"
        "<p>Links åbner i et nyt vindue og er mærket <code>nofollow</code>. DanskeDage har intet "
        "samarbejde med og modtager ingen betaling fra nogen af de nævnte myndigheder eller "
        "organisationer.</p>"
        '<p class="muted">Senest gennemgået: 22. august 2026.</p>'
        "</div></section>"
    )
    write_page(
        "kilder.html",
        "Kilder",
        "Officielle kilder bag DanskeDages helligdage, ugenumre og skoleferier.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Kilder", "")],
        ads=False,
    )


def render_editorial_policy() -> None:
    """Redaktionel politik: hvem står bag, og hvordan rettes fejl."""
    body = hero(
        "Redaktionel politik",
        "Hvem der står bag DanskeDage, hvordan indholdet bliver til, "
        "og hvordan fejl rettes.",
    )
    body += (
        '<section class="section"><div class="container narrow prose">'
        "<h2>Hvem står bag</h2>"
        "<p>DanskeDage drives og vedligeholdes af <strong>én uafhængig udvikler</strong> med "
        "baggrund i ingeniørvidenskab. For at være helt tydelig om, hvad det betyder: sitet har "
        "<strong>ingen redaktion, intet fagligt panel og ingen juridiske eksperter</strong> "
        "tilknyttet. Der er ikke opfundet «anmeldere» eller «eksperter» bag indholdet — alt, hvad "
        "du læser her, er skrevet og vedligeholdt af én person på grundlag af offentligt "
        'tilgængelige kilder, som er listet på <a href="kilder.html">kildesiden</a>.</p>'

        "<h2>Hvordan indholdet bliver til</h2>"
        "<p>Datoerne er beregnede, ikke indtastede — se "
        '<a href="metode.html">metodesiden</a> for algoritmerne og deres grænser. Den forklarende '
        "tekst er skrevet manuelt. Årssiderne indeholder en analyse, der genberegnes for hvert år, "
        "fordi det, der er værd at vide, faktisk skifter: nogle år mister man tre fridage i "
        "weekenden, andre år ingen.</p>"

        "<h2>Rettelser</h2>"
        "<p>Fejl bliver rettet, så snart de er bekræftet mod kilden, og rettelsen slår igennem på "
        "sitet ved næste natlige kørsel. Er du stødt på en dato, der ikke passer, så skriv til "
        'adressen på <a href="kontakt.html">kontaktsiden</a> — helst med et link til den kilde, du '
        "sammenligner med. Væsentlige rettelser noteres på metodesiden med dato.</p>"

        "<h2>Annoncer</h2>"
        "<p>Sitet er gratis og finansieres af annoncer fra Google AdSense. <strong>Annoncerne har "
        "ingen indflydelse på indholdet.</strong> Der er hverken betalte omtaler, sponsorerede "
        "artikler eller affiliate-links på sitet, og ingen annoncør har set eller godkendt en "
        "tekst før udgivelse. Sider uden selvstændigt indhold — kontakt, vilkår, privatlivspolitik "
        "og fejlsiden — viser ingen annoncer.</p>"

        "<h2>Data om dig</h2>"
        "<p>Beregningerne kører i din browser; de datoer, du indtaster, sendes ikke til nogen "
        'server. Hvad der ellers gemmes, står i <a href="privatlivspolitik.html">'
        "privatlivspolitikken</a>.</p>"

        "<h2>Ansvar</h2>"
        "<p>Indholdet er til almindelig orientering. Sitet er ikke juridisk rådgivning, og "
        "spørgsmål om løn, tillæg og ret til fridage afgøres af din overenskomst eller "
        "ansættelseskontrakt — ikke af en kalender.</p>"
        '<p class="muted">Senest gennemgået: 22. august 2026.</p>'
        "</div></section>"
    )
    write_page(
        "redaktionel-politik.html",
        "Redaktionel politik",
        "Hvem står bag DanskeDage, hvordan indholdet bliver til, hvordan fejl "
        "rettes, og hvilken rolle annoncer spiller.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Redaktionel politik", "")],
        ads=False,
    )


def render_about(start: int, end: int) -> None:
    body = hero("Om kalenderen og kilder", "Nationale helligdage beregnes med kendte kalenderregler, mens skoleferier opdateres efter kommunale kilder.", date.today().year)
    body += ad_slot("header")
    body += f"""<section class="section"><div class="container"><div class="grid"><article class="card"><h3>Periode</h3><p class="stat">{start}-{end}</p><p class="muted">Kalender-, helligdag- og arbejdsdagssider for hele perioden.</p></article><article class="card"><h3>Store bededag</h3><p class="stat">Ikke helligdag</p><p class="muted">Markeret historisk, men ikke talt som officiel helligdag efter 2024.</p></article></div><div class="card"><h2>Metode</h2><p>Påske beregnes med den gregorianske algoritme. Skærtorsdag, langfredag, Kristi himmelfartsdag og pinse beregnes relativt til påskedag. Arbejdsdage tæller mandag-fredag minus officielle helligdage.</p><p>Skoleferier ligger i <code>data/school-holidays.json</code> og skal revideres årligt mod de kommunale kilder.</p></div><div class="card"><h2>Kilder</h2><ul><li><a href="https://regeringen.dk/nyheder/2023/lovforslag-om-afskaffelse-store-bededag-er-vedtaget-i-folketinget/" rel="nofollow noopener" target="_blank">Regeringen: afskaffelse af store bededag</a></li><li><a href="https://natmus.dk/historisk-viden/temaer/fester-og-traditioner/store-bededag/" rel="nofollow noopener" target="_blank">Nationalmuseet: store bededag fra 2024</a></li><li><a href="https://www.oresunddirekt.dk/dk/jeg-arbejder-i-sverige/helligdag-og-ferie/helligdage-2026-i-danmark-og-sverige/" rel="nofollow noopener" target="_blank">Øresunddirekt: helligdage i Danmark</a></li><li><a href="skoleferier.html">Kommunale kilder til skoleferier</a></li></ul></div></div></section>"""
    body += ad_slot("mid")
    body += '<section class="section"><div class="container narrow prose"><h2>Hvad DanskeDage er</h2><p>DanskeDage er en samling danske kalenderberegnere: helligdage, arbejdsdage, ugenumre, datoforskelle og skoleferier. Alt er gratis, der er ingen login, og beregningerne kører i din browser — de datoer, du taster ind, forlader ikke din computer.</p><p>Ideen opstod ud af en helt konkret irritation: at slå op, hvor mange arbejdsdage der er i et kvartal, eller hvilken uge vinterferien ligger i, burde tage fem sekunder. I praksis endte man ofte på sider fyldt med pop-ups eller på et regneark, man selv skulle bygge. Sitet gør én ting og forsøger at gøre den ordentligt.</p><h2>Hvem står bag</h2><p>Sitet drives af <strong>én uafhængig udvikler</strong> med baggrund i ingeniørvidenskab. Der er ingen redaktion og intet fagligt panel — og der er ikke opfundet nogen. Hvad det betyder i praksis, og hvordan fejl bliver rettet, står på <a href="redaktionel-politik.html">den redaktionelle politik</a>.</p><h2>Hvordan tallene bliver til</h2><p>Datoerne er <strong>beregnede, ikke indtastede</strong>. Påskedag findes med den gregorianske algoritme, og skærtorsdag, langfredag, Kristi himmelfartsdag og pinse følger mekanisk af den. Arbejdsdage er hverdage minus officielle helligdage. Ugenumre følger ISO 8601. Store bededag har ikke været officiel helligdag siden 2024 og tælles derfor ikke med. Den fulde gennemgang — inklusive hvad beregningerne <em>ikke</em> dækker — står på <a href="metode.html">metodesiden</a>, og kilderne er samlet på <a href="kilder.html">kildesiden</a>.</p><h2>Årssiderne</h2><p>Hvert år får sine egne sider, fordi det, der er værd at vide, faktisk skifter fra år til år. Nogle år ryger tre helligdage i weekenden og er tabt; andre år ingen. Nogle år giver flere klemmedage, hvor en enkelt feriedag bygger bro til weekenden; andre år ingen. Analysen på hver årsside genberegnes, så den beskriver netop det år — ikke et gennemsnit.</p><h2>Skoleferier</h2><p>Skoleferier fastsættes kommunalt og er den del af sitet, der ændrer sig mest. Datoerne stammer fra kommunernes egne offentliggørelser, og hver kommuneside linker direkte til kilden, så du kan kontrollere den. Tjek altid kommunens side, før du booker en rejse.</p><h2>Fejl og forslag</h2><p>Finder du en dato, der ikke passer, er en mail den hurtigste vej til at få den rettet — gerne med et link til den kilde, du sammenligner med. Forslag til beregnere, der mangler, er også velkomne. Skriv via <a href="kontakt.html">kontaktsiden</a>.</p></div></section>'
    write_page(
        "om.html",
        "Om DanskeDage kalender - metode og kilder",
        f"Metode, kilder og vedligeholdelse for {SITE_NAME} kalender.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Om", "")],
    )


def render_contact() -> None:
    subject_error = "Fejl%20paa%20DanskeDage.dk"
    subject_suggestion = "Forslag%20til%20DanskeDage.dk"
    body = hero("Kontakt DanskeDage.dk", "Har du fundet en fejl i en dato, en beregner eller en kilde? Skriv til os, så retter vi det hurtigst muligt.", date.today().year)
    body += ad_slot("header")
    body += f"""<section class="section"><div class="container--narrow"><article class="card prose"><h2>Skriv til os</h2><p>Send en e-mail til <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>. Vi bruger e-mailen til fejlrapporter, forslag til nye kalenderfunktioner og spørgsmål om kilderne på siden.</p><p><a class="btn btn--primary" href="mailto:{CONTACT_EMAIL}?subject={subject_error}">Rapportér en fejl</a> <a class="btn btn--ghost" href="mailto:{CONTACT_EMAIL}?subject={subject_suggestion}">Foreslå en forbedring</a></p><h2>Når du rapporterer en fejl</h2><p>Skriv gerne hvilken side det drejer sig om, hvilken dato eller beregning der ser forkert ud, og hvilken officiel kilde du sammenligner med. For skoleferier er det særligt nyttigt med link til kommunens egen ferieplan.</p><h2>Privatliv</h2><p>Hvis du kontakter os via e-mail, modtager vi den e-mailadresse og det indhold, du selv sender. Vi bruger det kun til at svare på henvendelsen.</p></article></div></section>"""
    body += ad_slot("mid")
    write_page(
        "kontakt.html",
        f"Kontakt - {SITE_NAME}",
        f"Kontakt {SITE_NAME}: rapportér fejl i kalender, helligdage, arbejdsdage eller skoleferier.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Kontakt", "")],
        ads=False,
    )


def render_privacy_policy() -> None:
    body = hero("Privatlivspolitik", "Sådan håndterer DanskeDage.dk data, cookies, annoncer og eksterne links.", date.today().year)
    body += ad_slot("header")
    body += f"""<section class="section"><div class="container--narrow"><article class="card prose"><p class="muted">Sidst opdateret: {date.today().strftime('%Y-%m-%d')}.</p><h2>Kort fortalt</h2><p>{SITE_NAME} respekterer dit privatliv. De interaktive beregnere for arbejdsdage og ugenumre kører direkte i din browser. De datoer, du indtaster, bliver ikke sendt til vores server og bliver ikke gemt af os.</p><h2>Data i beregnerne</h2><p>Startdatoer, slutdatoer og antal arbejdsdage behandles lokalt med JavaScript på din enhed. Når du lukker eller genindlæser siden, forsvinder disse oplysninger fra beregneren.</p><h2>Serverlogfiler</h2><p>Som på andre hjemmesider kan hostingudbyderen registrere tekniske oplysninger såsom IP-adresse, browsertype, tidspunkt for besøg og forespurgte sider. Disse oplysninger bruges til drift, sikkerhed og fejlfinding.</p><h2>Cookies og annoncer</h2><p>Siden kan vise annoncer via Google AdSense for at finansiere drift og vedligeholdelse. Google og dets partnere kan bruge cookies til at vise og måle annoncer. Du kan læse mere om Googles brug af data på <a href="https://policies.google.com/technologies/partner-sites" rel="nofollow noopener" target="_blank">Googles side om partnerwebsteder</a> og ændre annonceindstillinger på <a href="https://www.google.com/settings/ads" rel="nofollow noopener" target="_blank">Googles annonceindstillinger</a>.</p><p>Vi bruger ikke login, betalingsmur eller egne analytics-cookies i kalenderberegnerne.</p><h2>Eksterne links</h2><p>Siden linker til officielle kilder og kommunale ferieplaner. Vi kontrollerer ikke disse eksterne sider og er ikke ansvarlige for deres indhold eller privatlivspraksis.</p><h2>Dine rettigheder</h2><p>Hvis du har spørgsmål om privatliv eller ønsker indsigt, rettelse eller sletning af oplysninger, du selv har sendt til os via e-mail, kan du kontakte os på <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>. Du kan også kontakte <a href="https://www.datatilsynet.dk/" rel="nofollow noopener" target="_blank">Datatilsynet</a>.</p><h2>Kontakt</h2><p>Spørgsmål om denne privatlivspolitik kan sendes til <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p></article></div></section>"""
    body += ad_slot("mid")
    write_page(
        "privatlivspolitik.html",
        f"Privatlivspolitik - {SITE_NAME}",
        f"Privatlivspolitik for {SITE_NAME}: data, cookies, annoncer og kontakt.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Privatlivspolitik", "")],
        ads=False,
    )


def render_terms() -> None:
    body = hero("Vilkår", "Betingelser for brug af DanskeDage.dk og kalenderberegnerne.", date.today().year)
    body += ad_slot("header")
    body += f"""<section class="section"><div class="container--narrow"><article class="card prose"><p class="muted">Sidst opdateret: {date.today().strftime('%Y-%m-%d')}.</p><h2>1. Accept af vilkårene</h2><p>Når du bruger {SITE_NAME}, accepterer du disse vilkår. Hvis du ikke er enig, bør du lade være med at bruge siden.</p><h2>2. Informativt formål</h2><p>Siden tilbyder kalenderoplysninger, helligdage, arbejdsdage, ugenumre, skoleferier og relaterede beregnere med et udelukkende informativt formål. Oplysningerne erstatter ikke officiel rådgivning, kommunale afgørelser eller juridisk vurdering.</p><h2>3. Kilder og nøjagtighed</h2><p>Vi gør os umage for at beregne nationale helligdage korrekt og linke til relevante officielle og kommunale kilder. Skoleferier fastsættes lokalt og kan ændres, og enkelte skoler kan have afvigelser. Tjek derfor altid den officielle kilde, før du planlægger rejser, fravær eller arbejde.</p><h2>4. Ansvarsbegrænsning</h2><p>{SITE_NAME} stilles til rådighed som den er. Vi er ikke ansvarlige for tab, forsinkelser, fejlagtig planlægning eller andre konsekvenser, der måtte opstå ved brug af siden.</p><h2>5. Eksterne links og annoncer</h2><p>Siden kan indeholde links til tredjepartssider og vise annoncer via Google AdSense. Tredjepartssider har deres egne vilkår og privatlivspolitikker.</p><h2>6. Ændringer</h2><p>Vilkårene kan opdateres, når siden ændres, eller når regler og datakilder ændrer sig. Datoen øverst viser den aktuelle version.</p><h2>7. Kontakt</h2><p>Spørgsmål om vilkårene kan sendes til <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p></article></div></section>"""
    body += ad_slot("mid")
    write_page(
        "vilkar.html",
        f"Vilkår - {SITE_NAME}",
        f"Vilkår for brug af {SITE_NAME}, kalenderdata og beregnere.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Vilkår", "")],
        ads=False,
    )


def render_404() -> None:
    """Write 404.html — same shell as layout() but with noindex,follow + DA copy."""

    title = "Siden blev ikke fundet - 404"
    description = "Den side, du leder efter, findes ikke længere på DanskeDage.dk."
    nav_year = ACTIVE_YEAR
    nav = [
        ("Kalender", f"/kalender-{nav_year}.html", "kalender"),
        ("Helligdage", f"/helligdage-{nav_year}.html", "helligdage"),
        ("Arbejdsdage", f"/arbejdsdage-{nav_year}.html", "arbejdsdage"),
        ("Ugenummer", "/ugenummer.html", "ugenummer"),
        ("Skoleferier", "/skoleferier.html", "skoleferier"),
        ("Ferieplan", f"/bedste-feriedage-{nav_year}.html", "ferieplan"),
    ]
    nav_html = "".join(f'<li><a href="{href}">{label}</a></li>' for label, href, _ in nav)
    body = (
        '<section class="hero"><div class="container">'
        '<span class="eyebrow">Fejl 404</span>'
        '<h1>Siden blev ikke fundet</h1>'
        '<p class="lead">Linket er forældet, eller siden er flyttet. '
        'Brug menuen herover eller hop direkte til en af de mest brugte sider.</p>'
        '<div class="hero-actions">'
        '<a class="btn btn--primary" href="/">Tilbage til forsiden</a> '
        f'<a class="btn btn--ghost" href="/kalender-{nav_year}.html">Kalender {nav_year}</a>'
        '</div></div></section>'
        '<section class="section"><div class="container"><div class="grid">'
        f'<a class="card" href="/kalender-{nav_year}.html"><h3>Kalender {nav_year}</h3>'
        '<p class="muted">Måned-for-måned kalender med helligdage og uger.</p></a>'
        f'<a class="card" href="/helligdage-{nav_year}.html"><h3>Helligdage {nav_year}</h3>'
        '<p class="muted">Alle danske helligdage i året.</p></a>'
        f'<a class="card" href="/arbejdsdage-{nav_year}.html"><h3>Arbejdsdage {nav_year}</h3>'
        '<p class="muted">Antal arbejdsdage pr. måned.</p></a>'
        '<a class="card" href="/vaerktoejer.html"><h3>Værktøjer</h3>'
        '<p class="muted">Alle kalender- og dato-beregnere.</p></a>'
        '<a class="card" href="/artikler/"><h3>Artikler</h3>'
        '<p class="muted">Baggrund om dansk kalender og helligdage.</p></a>'
        '<a class="card" href="/kontakt.html"><h3>Kontakt</h3>'
        '<p class="muted">Skriv hvis du fandt et brudt link.</p></a>'
        '</div></div></section>'
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="da-DK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - {SITE_NAME}</title>
<meta name="description" content="{html.escape(description)}">
<meta name="robots" content="noindex,follow">
<meta name="theme-color" content="#0f766e">
<meta property="og:type" content="website">
<meta property="og:locale" content="da_DK">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png">
<link rel="icon" type="image/png" sizes="192x192" href="/favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="stylesheet" href="/css/style.css">
<script src="/js/cookie-consent.js" defer></script>
</head>
<body>
<a class="skip-link" href="#indhold">Spring til indhold</a>
<header class="site-header"><div class="container site-header__inner">
<a class="brand" href="/"><svg class="brand__mark" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="12" fill="#0f766e"/><rect x="12" y="15" width="40" height="37" rx="5" fill="#fff"/><rect x="12" y="15" width="40" height="10" rx="5" fill="#134e4a"/><path d="M22 34h7v7h-7zm13 0h7v7h-7z" fill="#0f766e"/></svg><span>{SITE_NAME}</span></a>
<button class="nav-toggle" type="button" aria-controls="main-nav" aria-expanded="false" aria-label="Åbn menu"><span class="nav-toggle__bars" aria-hidden="true"><span></span><span></span><span></span></span><span>Menu</span></button>
<nav class="main-nav" id="main-nav" aria-label="Hovedmenu"><ul>{nav_html}</ul></nav>
</div></header>
<main id="indhold">{body}</main>
<footer class="footer"><div class="container footer-grid">
<div><h2>{SITE_NAME}</h2><p>Danske kalender- og hverdagsberegnere. Gratis, opdateret og uden login.</p></div>
<div><h3>Kalender</h3><ul><li><a href="/kalender-{nav_year}.html">Kalender {nav_year}</a></li><li><a href="/helligdage-{nav_year}.html">Helligdage {nav_year}</a></li><li><a href="/arbejdsdage-{nav_year}.html">Arbejdsdage {nav_year}</a></li></ul></div>
<div><h3>Værktøjer</h3><ul><li><a href="/vaerktoejer.html">Alle værktøjer</a></li><li><a href="/beregn-arbejdsdage.html">Beregn arbejdsdage</a></li><li><a href="/ugenummer.html">Ugenummer</a></li><li><a href="/aldersberegner.html">Aldersberegner</a></li></ul></div>
<div><h3>Site</h3><ul><li><a href="/om.html">Om og kilder</a></li><li><a href="/kontakt.html">Kontakt</a></li><li><a href="/privatlivspolitik.html">Privatlivspolitik</a></li><li><a href="/vilkar.html">Vilkår</a></li><li><a href="/sitemap.xml">Sitemap</a></li></ul></div>
</div></footer>
<script src="/js/calendar-tools.js"></script>
<script src="/js/today.js"></script>
</body>
</html>
"""
    (ROOT / "404.html").write_text(html_doc, encoding="utf-8")


def render_support() -> None:
    qr = '<img class="donate-qr" src="img/bmc_qr.png" alt="QR-kode til Buy Me a Coffee" width="190" height="190" loading="lazy">' if (ROOT / "img" / "bmc_qr.png").exists() else ""
    body = hero("Støt projektet", "Hvis DanskeDage.dk hjælper dig, kan du støtte projektet via Buy Me a Coffee.", date.today().year)
    body += ad_slot("header")
    body += f"""<section class="section"><div class="container--narrow"><article class="card donate-card prose"><h2>Buy Me a Coffee</h2><p>Siden er gratis og uden login. Bidrag hjælper med domæne, hosting, årlige opdateringer og nye kalenderfunktioner.</p><p><a class="btn btn--primary" href="{BUY_ME_A_COFFEE}" target="_blank" rel="noopener">Støt på Buy Me a Coffee</a></p>{qr}</article><p class="muted" id="del">Du kan også hjælpe gratis ved at dele siden med andre, der søger danske datoer, helligdage eller arbejdsdage.</p></div></section>"""
    body += ad_slot("mid")
    write_page(
        "stot.html",
        f"Støt projektet - {SITE_NAME}",
        f"Støt {SITE_NAME} via Buy Me a Coffee og hjælp med at holde siden gratis.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Støt projektet", "")],
        ads=False,
    )


# Haandskrevne sider i roden som generatoren ALDRIG maa slette/overskrive.
HAND_AUTHORED = {"udbytte.html"}


def generate(start: int, end: int) -> None:
    global ACTIVE_YEAR
    ensure_base_files()

    for old in ROOT.glob("*.html"):
        if old.name in HAND_AUTHORED:
            continue
        old.unlink()
    for old in ROOT.glob("*.xml"):
        old.unlink()

    current_year = min(max(date.today().year, start), end)
    ACTIVE_YEAR = current_year
    render_index(current_year)
    render_tools()
    render_school_holidays()
    render_about(start, end)
    render_methodology()
    render_sources()
    render_editorial_policy()
    render_contact()
    render_privacy_policy()
    render_terms()
    render_support()
    render_404()
    # Extra interactive tools (aldersberegner, datoforskel, nedtælling, ...).
    import sys
    sys.modules[__name__] = sys.modules[__name__]
    from extra_tool_pages import render_all as _render_extra_tools
    _render_extra_tools(sys.modules[__name__])
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
    urls = [
        "",
        "beregn-arbejdsdage.html",
        "laeg-arbejdsdage-til.html",
        "ugenummer.html",
        "skoleferier.html",
        "om.html",
        "metode.html",
        "kilder.html",
        "redaktionel-politik.html",
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
        "udbytte.html",
    ]
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
    # Static editorial articles in /artikler/ — file system is the source of truth.
    artikler_dir = ROOT / "artikler"
    artikler_urls: list[str] = []
    if artikler_dir.exists():
        for page in sorted(artikler_dir.glob("*.html")):
            if page.name == "index.html":
                artikler_urls.append("artikler/")
            else:
                artikler_urls.append(f"artikler/{page.name}")
    urls.extend(artikler_urls)

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
    parser.add_argument("--end", type=int, default=2030)  # ano corrente + 4 próximos
    args = parser.parse_args()
    if args.end < args.start:
        raise SystemExit("--end must be >= --start")
    generate(args.start, args.end)
    print(f"Generated DanskeDage calendar site from {args.start} to {args.end} in {ROOT}")


if __name__ == "__main__":
    main()
