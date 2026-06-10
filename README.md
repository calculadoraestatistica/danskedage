# DanskeDage Kalender

Static Danish calendar site generated from `tools/generate_site.py`.

Generated range: 2026-2050

## Generate

```powershell
python .\tools\generate_site.py --start 2026 --end 2050
```

## Validate

```powershell
python .\tools\validate_site.py --start 2026 --end 2050
```

## Annual cron/review

```powershell
python .\tools\annual_review.py
```

The annual review regenerates pages, validates internal links, checks expected files/data, and prints the human-review checklist. By default it keeps at least 15 future years generated, while never generating less than 2050.

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
