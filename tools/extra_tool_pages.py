"""Extra interactive tool pages for DanskeDage.dk.

Eight stand-alone calculators that share the existing layout/hero/footer
infrastructure of generate_site.py. Each render_* function writes one HTML
file and registers a sitemap URL in the EXTRA_TOOL_PAGES list.

All tools run client-side in plain JavaScript. Holiday data is mirrored from
the Python generator (all_marks/official_holidays) so the JS can compute
business days, next holidays, etc., without a network round-trip.
"""

from __future__ import annotations

import json
from datetime import date

# Public list of slugs/titles consumed by generate_site.py for sitemap, footer
# and the optional hub page. Keep it in sync if you add or rename tools.
EXTRA_TOOL_PAGES: list[tuple[str, str]] = [
    ("aldersberegner.html", "Aldersberegner"),
    ("dato-difference.html", "Datoforskel"),
    ("nedtaelling.html", "Nedtælling"),
    ("naeste-helligdag.html", "Næste helligdag"),
    ("ugedag.html", "Ugedag"),
    ("dato-plus-dage.html", "Dato plus eller minus dage"),
    ("traek-arbejdsdage-fra.html", "Træk arbejdsdage fra"),
    ("dato-fra-uge.html", "Dato fra ugenummer"),
]


# ---------------------------------------------------------------------------
# Helpers shared by every tool page.
# ---------------------------------------------------------------------------


def _holiday_js_data(g) -> str:
    """Serialize official holidays for current + next 6 years as a JS object.

    Uses the canonical all_marks() data from the generator module ``g``.
    """

    today = date.today()
    out: dict[str, list[dict]] = {}
    for year in range(today.year - 1, today.year + 8):
        marks = g.all_marks(year)
        out[str(year)] = [
            {
                "date": m.date.isoformat(),
                "name": m.name,
                "official": m.official,
                "kind": m.kind,
            }
            for m in marks
        ]
    return json.dumps(out, ensure_ascii=False)


def _related_tools(current_slug: str) -> str:
    """Render a related tools card row, excluding the current page."""

    items = []
    for slug, label in EXTRA_TOOL_PAGES:
        if slug == current_slug:
            continue
        items.append(
            f'<a class="card" href="{slug}"><h3>{label}</h3>'
            f'<p class="muted">Åbn værktøjet</p></a>'
        )
    return (
        '<section class="section"><div class="container">'
        '<div class="section-title"><div><h2>Andre værktøjer</h2>'
        '<p>Flere danske kalender- og dato-beregnere.</p></div></div>'
        f'<div class="grid">{"".join(items)}</div></div></section>'
    )


def _prose_block(html_inner: str) -> str:
    return (
        '<section class="section"><div class="container container--narrow">'
        f'<article class="card prose">{html_inner}</article></div></section>'
    )


# ---------------------------------------------------------------------------
# 1. Aldersberegner
# ---------------------------------------------------------------------------


def render_aldersberegner(g) -> None:
    today = date.today().isoformat()
    holidays = _holiday_js_data(g)

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="ab-birth">Fødselsdato</label>
    <input id="ab-birth" type="date" value="2000-01-01"></div>
  <div class="field"><label for="ab-ref">Referencedato</label>
    <input id="ab-ref" type="date" value="{today}"></div>
</div>
<div id="ab-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
</div></div></section>
<script>
(function(){{
  var WD=['søndag','mandag','tirsdag','onsdag','torsdag','fredag','lørdag'];
  var MONTHS=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december'];
  function parse(s){{var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}}
  function fmt(n){{return new Intl.NumberFormat('da-DK').format(n);}}
  function fmtDK(d){{return d.getUTCDate()+'. '+MONTHS[d.getUTCMonth()]+' '+d.getUTCFullYear();}}
  function relDelta(birth, ref){{
    var y=ref.getUTCFullYear()-birth.getUTCFullYear();
    var m=ref.getUTCMonth()-birth.getUTCMonth();
    var d=ref.getUTCDate()-birth.getUTCDate();
    if(d<0){{
      var startMonthDays=new Date(Date.UTC(birth.getUTCFullYear(), birth.getUTCMonth()+1, 0)).getUTCDate();
      d+=startMonthDays; m--;
    }}
    if(m<0){{m+=12; y--;}}
    return {{years:y, months:m, days:d}};
  }}
  function nextBirthday(birth, ref){{
    var y=ref.getUTCFullYear();
    var next=new Date(Date.UTC(y, birth.getUTCMonth(), birth.getUTCDate()));
    if(next<ref) next=new Date(Date.UTC(y+1, birth.getUTCMonth(), birth.getUTCDate()));
    return next;
  }}
  function update(){{
    var b=document.getElementById('ab-birth'), r=document.getElementById('ab-ref'), out=document.getElementById('ab-result');
    if(!b||!r||!out) return;
    var birth=parse(b.value), ref=parse(r.value);
    if(isNaN(birth)||isNaN(ref)){{out.innerHTML='Vælg en gyldig fødselsdato.';return;}}
    if(ref<birth){{out.innerHTML='Referencedatoen skal være efter fødselsdatoen.';return;}}
    var rd=relDelta(birth, ref);
    var totalDays=Math.round((ref-birth)/86400000);
    var weeks=Math.floor(totalDays/7);
    var hours=totalDays*24;
    var nb=nextBirthday(birth, ref);
    var daysToNext=Math.round((nb-ref)/86400000);
    var bwd=WD[birth.getUTCDay()];
    var nbTxt = daysToNext===0 ? fmtDK(nb)+' (i dag)' : fmtDK(nb)+' (om '+daysToNext+' dage)';
    out.innerHTML=
      '<strong>'+rd.years+' år, '+rd.months+' måneder og '+rd.days+' dage</strong>'+
      '<br><span>'+fmt(totalDays)+' levede dage · '+fmt(weeks)+' uger · '+fmt(hours)+' timer</span>'+
      '<br><span>Født på en <strong>'+bwd+'</strong>.</span>'+
      '<br><span>Næste fødselsdag: '+nbTxt+'.</span>';
  }}
  document.addEventListener('input', update);
  document.addEventListener('change', update);
  document.addEventListener('DOMContentLoaded', update);
  update();
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvordan beregnes alderen?</h2>
<p>Aldersberegneren tager din fødselsdato og en referencedato (som standard
i dag) og finder forskellen i hele år, måneder og dage. Den bruger samme
princip som CPR-registret og folkeregistret: et helt år tæller først, når
fødselsdagen er passeret.</p>
<h2>Hvad viser den ekstra information?</h2>
<ul>
<li><strong>Samlet antal dage</strong> – antallet af kalenderdage siden fødslen.</li>
<li><strong>Uger og timer</strong> – nyttigt til runde tal og statistik.</li>
<li><strong>Fødselsdag på ugedag</strong> – hvilken ugedag du blev født på.</li>
<li><strong>Dage til næste fødselsdag</strong> – tæller ned til næste runde år.</li>
</ul>
<h2>Bruges referencedatoen til noget særligt?</h2>
<p>Ja. Hvis du fx skal opgive alderen pr. en kontraktdato, en eksamen eller
en flyrejse, kan du sætte referencedatoen i fremtiden eller fortiden og se
nøjagtigt hvor gammel personen var (eller bliver) den dag.</p>
""")

    faq = [
        (
            "Hvordan tæller beregneren skudår med?",
            "Beregningen bruger almindelige kalenderdage, så skudår påvirker "
            "automatisk det samlede antal dage. Den 29. februar tæller med som "
            "én dag på lige fod med andre datoer.",
        ),
        (
            "Hvad sker der, hvis fødselsdatoen er en 29. februar?",
            "Næste fødselsdag rykker til 1. marts i ikke-skudår, men selve "
            "alderen i år, måneder og dage beregnes præcist ud fra antallet "
            "af forløbne måneder.",
        ),
        (
            "Bliver fødselsdatoen gemt?",
            "Nej. Hele beregningen sker i din browser, og DanskeDage.dk gemmer "
            "ikke datoer eller andre indtastninger.",
        ),
        (
            "Kan jeg bruge værktøjet til kæledyr eller historiske personer?",
            "Ja. Beregneren kender ikke til personer – den arbejder kun med "
            "datoer. Du kan derfor finde alderen på en hund, en bil, et "
            "kontraktforhold eller en historisk skikkelse.",
        ),
    ]

    title = "Aldersberegner – nøjagtig alder i år, måneder og dage"
    desc = (
        "Beregn nøjagtig alder i år, måneder og dage. Se også samlet antal "
        "levede dage, uger og dage til næste fødselsdag."
    )
    body = g.hero(
        "Aldersberegner",
        "Beregn nøjagtig alder i år, måneder og dage. Se samlet antal "
        "levede dage, uger, timer og hvor mange dage der er til næste fødselsdag.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("aldersberegner.html")
    body += g.ad_slot("footer")

    g.write_page(
        "aldersberegner.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Aldersberegner", "")],
        faq=faq,
    )

    # Reference to holidays object kept for parity with sibling tools.
    _ = holidays


# ---------------------------------------------------------------------------
# 2. Datoforskel
# ---------------------------------------------------------------------------


def render_dato_difference(g) -> None:
    today = date.today().isoformat()

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="dd-1">Dato 1</label>
    <input id="dd-1" type="date" value="{today}"></div>
  <div class="field"><label for="dd-2">Dato 2</label>
    <input id="dd-2" type="date" value="{today}"></div>
  <div class="field"><label for="dd-incl">Tæl slutdato med?</label>
    <select id="dd-incl"><option value="no">Nej</option><option value="yes">Ja</option></select></div>
</div>
<div id="dd-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
</div></div></section>
<script>
(function(){{
  function parse(s){{var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}}
  function fmt(n){{return new Intl.NumberFormat('da-DK').format(n);}}
  function relDelta(a, b){{
    var sign=1;
    if(b<a){{var t=a; a=b; b=t; sign=-1;}}
    var y=b.getUTCFullYear()-a.getUTCFullYear();
    var m=b.getUTCMonth()-a.getUTCMonth();
    var d=b.getUTCDate()-a.getUTCDate();
    if(d<0){{
      var startMonthDays=new Date(Date.UTC(a.getUTCFullYear(), a.getUTCMonth()+1, 0)).getUTCDate();
      d+=startMonthDays; m--;
    }}
    if(m<0){{m+=12; y--;}}
    return {{years:y, months:m, days:d, sign:sign}};
  }}
  function update(){{
    var a=document.getElementById('dd-1'), b=document.getElementById('dd-2'),
        incl=document.getElementById('dd-incl'), out=document.getElementById('dd-result');
    if(!a||!b||!out) return;
    var d1=parse(a.value), d2=parse(b.value);
    if(isNaN(d1)||isNaN(d2)){{out.innerHTML='Vælg to gyldige datoer.';return;}}
    var inclYes = incl && incl.value==='yes';
    var diffMs=Math.abs(d2-d1);
    var totalDays=Math.round(diffMs/86400000) + (inclYes?1:0);
    var totalHours=totalDays*24;
    var totalMinutes=totalHours*60;
    var totalSeconds=totalMinutes*60;
    var weeks=Math.floor(totalDays/7);
    var remDays=totalDays%7;
    var rd=relDelta(d1,d2);
    var sign=d2<d1?'(dato 2 er før dato 1)':'';
    out.innerHTML=
      '<strong>'+rd.years+' år, '+rd.months+' måneder, '+rd.days+' dage</strong> '+sign+
      '<br><span>'+fmt(totalDays)+' dage i alt · '+fmt(weeks)+' uger og '+remDays+' dage</span>'+
      '<br><span>'+fmt(totalHours)+' timer · '+fmt(totalMinutes)+' minutter · '+fmt(totalSeconds)+' sekunder</span>';
  }}
  document.addEventListener('input', update);
  document.addEventListener('change', update);
  document.addEventListener('DOMContentLoaded', update);
  update();
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvad bruges en datoforskel til?</h2>
<p>Datoforskel er et af de mest brugte kalenderværktøjer i Danmark. Det
hjælper med at planlægge graviditet, ferier, kontrakter, opsigelsesfrister,
projektdeadlines og runde mærkedage.</p>
<h2>Hvordan tolkes resultaterne?</h2>
<ul>
<li><strong>År, måneder, dage</strong> – brugbart til officielle perioder
som ansættelse, leje eller barsel.</li>
<li><strong>Samlet antal dage</strong> – det rene kalenderantal mellem de
to datoer, uafhængigt af måneder.</li>
<li><strong>Uger og dage</strong> – ofte brugt i graviditetsforløb og
sportstræning.</li>
<li><strong>Timer, minutter, sekunder</strong> – nyttigt til faktura-,
hosting- og kontraktperioder, hvor præcision tæller.</li>
</ul>
<h2>Skal slutdatoen tælle med?</h2>
<p>Det afhænger af konteksten. Når du beregner ferieperioder eller
hoteludlejning, tæller slutdatoen ofte med. Når du beregner antal dage
<em>mellem</em> to begivenheder, tælles den typisk ikke med. Skift
indstillingen efter behov.</p>
""")

    faq = [
        (
            "Tæller datoforskel kalenderdage eller arbejdsdage?",
            "Datoforskel tæller kalenderdage. Hvis du har brug for arbejdsdage, "
            "skal du bruge værktøjet \"Beregn arbejdsdage\".",
        ),
        (
            "Hvad er forskellen på relativ forskel og samlet antal dage?",
            "Relativ forskel viser hele år, måneder og dage, fx \"2 år, 3 måneder, "
            "5 dage\". Samlet antal dage er den rene sum af kalenderdage mellem "
            "datoerne, fx 825 dage.",
        ),
        (
            "Kan jeg bytte rækkefølgen på datoerne?",
            "Ja. Beregneren viser altid en positiv tidsforskel, men markerer "
            "tydeligt, hvis dato 2 ligger før dato 1.",
        ),
        (
            "Bliver tiden på dagen brugt i beregningen?",
            "Nej. Værktøjet arbejder med hele kalenderdage. Hvis du har brug "
            "for præcis tid, kan du selv lægge timer og minutter til efter "
            "behov.",
        ),
    ]

    title = "Datoforskel – år, måneder, dage, timer og minutter"
    desc = (
        "Beregn forskellen mellem to datoer i år, måneder, uger, dage, "
        "timer og minutter. Velegnet til graviditet, kontrakter og projekter."
    )
    body = g.hero(
        "Datoforskel",
        "Beregn forskellen mellem to datoer i år, måneder, uger, dage, timer "
        "og minutter. Nyttigt til graviditet, kontrakter og projekter.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("dato-difference.html")
    body += g.ad_slot("footer")

    g.write_page(
        "dato-difference.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Datoforskel", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# 3. Nedtælling
# ---------------------------------------------------------------------------


def render_nedtaelling(g) -> None:
    next_year = date.today().year + 1
    default_target = f"{next_year}-01-01"

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="nt-date">Måldato</label>
    <input id="nt-date" type="date" value="{default_target}"></div>
  <div class="field"><label for="nt-name">Begivenhedens navn (valgfrit)</label>
    <input id="nt-name" type="text" placeholder="f.eks. Nytår" maxlength="80"></div>
</div>
<div id="nt-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
<p class="muted" id="nt-share" style="margin-top:.7rem"></p>
</div></div></section>
<script>
(function(){{
  var WD=['søndag','mandag','tirsdag','onsdag','torsdag','fredag','lørdag'];
  function pad(n){{return n<10?'0'+n:''+n;}}
  function esc(s){{var d=document.createElement('span');d.textContent=String(s||'');return d.innerHTML;}}
  var timer=null;
  function tick(){{
    var di=document.getElementById('nt-date'), ni=document.getElementById('nt-name'),
        out=document.getElementById('nt-result'), share=document.getElementById('nt-share');
    if(!di||!out) return;
    if(!di.value){{out.textContent='Vælg en måldato.';return;}}
    if(!/^\d{{4}}-\d{{2}}-\d{{2}}$/.test(di.value)){{out.textContent='Vælg en gyldig dato.';return;}}
    var parts=di.value.split('-').map(Number);
    var target=new Date(parts[0], parts[1]-1, parts[2]);
    if(isNaN(target)){{out.textContent='Vælg en gyldig dato.';return;}}
    var now=new Date();
    var ms=target-now;
    var rawName=(ni && ni.value)? ni.value.slice(0,80) : 'Begivenhed';
    var name=esc(rawName);
    var wd=WD[target.getDay()];
    if(ms<=0){{
      if(timer){{clearInterval(timer); timer=null;}}
      out.innerHTML='<strong>'+name+' er nået!</strong><br><span>Måldatoen '+esc(di.value)+' ('+wd+') er passeret.</span>';
    }} else {{
      var s=Math.floor(ms/1000);
      var d=Math.floor(s/86400); s-=d*86400;
      var h=Math.floor(s/3600); s-=h*3600;
      var m=Math.floor(s/60); s-=m*60;
      out.innerHTML='<strong>'+d+' dage '+pad(h)+':'+pad(m)+':'+pad(s)+'</strong>'+
        '<br><span>'+name+' – '+esc(di.value)+' ('+wd+')</span>';
    }}
    var url=new URL(window.location.href);
    url.searchParams.set('d', di.value);
    if(ni && ni.value) url.searchParams.set('e', rawName); else url.searchParams.delete('e');
    if(share){{
      share.textContent='Delbar permalink: ';
      var a=document.createElement('a');
      a.href=url.toString(); a.textContent=url.toString();
      share.appendChild(a);
    }}
  }}
  function init(){{
    var params=new URLSearchParams(window.location.search);
    var d=params.get('d'), e=(params.get('e')||'').slice(0,80);
    if(d&&/^\d{{4}}-\d{{2}}-\d{{2}}$/.test(d)) document.getElementById('nt-date').value=d;
    if(e) document.getElementById('nt-name').value=e;
    tick();
    if(timer){{clearInterval(timer);}}
    timer=setInterval(tick, 1000);
  }}
  document.addEventListener('DOMContentLoaded', init);
  document.addEventListener('input', tick);
  document.addEventListener('change', tick);
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvad er en nedtælling?</h2>
<p>Nedtællingsuret viser antallet af dage, timer, minutter og sekunder
indtil en valgt måldato. Det opdateres hvert sekund, så du kan følge med
i realtid.</p>
<h2>Hvornår er nedtælling nyttig?</h2>
<ul>
<li><strong>Nytår, jul, fødselsdage</strong> – klassiske begivenheder, hvor
ventetiden er en del af glæden.</li>
<li><strong>Ferierejser</strong> – hold motivationen oppe på arbejdspladsen.</li>
<li><strong>Eksamen og deadlines</strong> – planlæg studier og opgaver.</li>
<li><strong>Pension og runde mærkedage</strong> – tæl ned til en milepæl.</li>
</ul>
<h2>Delbar permalink</h2>
<p>URL'en opdateres automatisk med din valgte dato og begivenhedsnavn.
Kopiér linket og send det til venner eller kolleger – de ser præcis samme
nedtælling, når de åbner siden.</p>
""")

    faq = [
        (
            "Skal jeg lade siden være åben for at se nedtællingen?",
            "Ja. Nedtællingen kører i din browser og opdateres hvert sekund, "
            "så længe fanen er åben. Hvis du lukker siden, fryser uret, men "
            "kommer du tilbage til samme link, fortsætter det.",
        ),
        (
            "Hvilken tidszone bruges?",
            "Værktøjet bruger din computers tidszone. For brugere i Danmark "
            "svarer det til Europe/Copenhagen og tager højde for sommertid.",
        ),
        (
            "Kan jeg lave flere nedtællinger?",
            "Ja. Åbn flere faner og indtast forskellige datoer, eller gem "
            "permalinks som bogmærker.",
        ),
        (
            "Hvad sker der, når måldatoen er passeret?",
            "Beskeden skifter til \"Begivenhed er nået!\". Du kan derefter "
            "vælge en ny måldato og starte forfra.",
        ),
    ]

    title = "Nedtælling – live ur til vigtige datoer"
    desc = (
        "Live nedtælling i dage, timer, minutter og sekunder til en valgt "
        "dato. Del permalink med venner og kolleger."
    )
    body = g.hero(
        "Nedtælling",
        "Live nedtælling til en måldato. Værktøjet opdateres hvert sekund "
        "og giver dig en delbar permalink.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("nedtaelling.html")
    body += g.ad_slot("footer")

    g.write_page(
        "nedtaelling.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Nedtælling", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# 4. Næste helligdag
# ---------------------------------------------------------------------------


def render_naeste_helligdag(g) -> None:
    today = date.today()
    upcoming: list[tuple[date, str]] = []
    for year in (today.year, today.year + 1, today.year + 2):
        for m in g.all_marks(year):
            if m.official and m.date >= today:
                upcoming.append((m.date, m.name))
    upcoming.sort(key=lambda x: x[0])
    upcoming = upcoming[:5]

    if upcoming:
        first_date, first_name = upcoming[0]
        days_left = (first_date - today).days
        weekday_name = g.WEEKDAYS_LONG[first_date.weekday()]
        weekend_hint = ""
        if first_date.weekday() == 0:
            weekend_hint = " (lang weekend mulig – falder på en mandag)"
        elif first_date.weekday() == 4:
            weekend_hint = " (lang weekend mulig – falder på en fredag)"
        elif first_date.weekday() == 3:
            weekend_hint = " (klemmedag mulig – falder på en torsdag)"

        next_card = (
            '<div class="result-box" aria-live="polite" aria-atomic="true">'
            f'<strong>{first_name}</strong>'
            f'<br><span>{g.fmt_date(first_date)} ({weekday_name})</span>'
            f'<br><span>Om <strong>{days_left}</strong> dage{weekend_hint}.</span>'
            '</div>'
        )

        rows = "".join(
            f"<tr><td>{g.fmt_date(d)}</td>"
            f"<td>{g.WEEKDAYS_LONG[d.weekday()]}</td>"
            f"<td>{name}</td>"
            f"<td>{(d - today).days} dage</td></tr>"
            for d, name in upcoming
        )
        table = (
            '<section class="section"><div class="container">'
            '<div class="section-title"><div><h2>De næste 5 helligdage</h2>'
            '<p>Officielle danske helligdage – fra i dag og frem.</p></div></div>'
            '<div class="table-wrap"><table><thead><tr><th>Dato</th>'
            '<th>Ugedag</th><th>Helligdag</th><th>Tid tilbage</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></div></section>'
        )
    else:
        next_card = (
            '<div class="result-box" aria-live="polite" aria-atomic="true">Ingen kommende helligdage fundet i de næste år.</div>'
        )
        table = ""

    prose = _prose_block("""
<h2>Hvad regnes som en officiel helligdag i Danmark?</h2>
<p>De officielle helligdage i Danmark er nytårsdag, skærtorsdag, langfredag,
påskedag, 2. påskedag, Kristi himmelfartsdag, pinsedag, 2. pinsedag, juledag
og 2. juledag. Store bededag er afskaffet som officiel helligdag fra 2024.</p>
<h2>Klemmedage og lange weekender</h2>
<p>Når en helligdag falder på en torsdag eller mandag, opstår der ofte
mulighed for en lang weekend. Ved at lægge én feriedag til kan du få fire
sammenhængende fridage – en såkaldt klemmedag.</p>
<h2>Sådan bruges siden</h2>
<p>Siden viser automatisk den næste officielle helligdag og de fem
efterfølgende. Du behøver ikke indtaste noget – datoerne opdateres når
året skifter.</p>
""")

    faq = [
        (
            "Tæller værktøjet 1. maj og Grundlovsdag med?",
            "Nej. 1. maj og Grundlovsdag er mærkedage og typisk halve fridage, "
            "men ikke officielle helligdage. Siden viser kun lovbestemte "
            "helligdage.",
        ),
        (
            "Hvorfor er store bededag ikke med?",
            "Store bededag blev afskaffet som officiel helligdag i 2024. "
            "Datoen findes stadig i kalenderen, men tæller ikke længere som "
            "fridag.",
        ),
        (
            "Hvordan beregnes påske, pinse og Kristi himmelfart?",
            "Påskedag beregnes med Meeus/Jones/Butcher-algoritmen. De øvrige "
            "bevægelige helligdage er fastlagt som faste afstande fra påsken: "
            "skærtorsdag (-3), langfredag (-2), 2. påskedag (+1), Kristi "
            "himmelfartsdag (+39), pinsedag (+49) og 2. pinsedag (+50).",
        ),
        (
            "Kan jeg planlægge ferie ud fra siden?",
            "Ja. Brug værktøjet \"Bedste feriedage\" til konkrete ferieforslag, "
            "eller \"Beregn arbejdsdage\" til at planlægge fravær.",
        ),
    ]

    title = "Næste helligdag i Danmark"
    desc = (
        "Se den næste danske helligdag og de næste 5 i en samlet liste – "
        "med ugedag, dage tilbage og mulige klemmedage."
    )
    body = g.hero(
        "Næste helligdag",
        "Find den næste danske helligdag automatisk. Værktøjet viser også "
        "de næste 5 helligdage og markerer mulige klemmedage.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += (
        '<section class="section"><div class="container">'
        '<div class="section-title"><div><h2>Næste officielle helligdag</h2>'
        '<p>Beregnet ud fra dags dato.</p></div></div>'
        f'{next_card}</div></section>'
    )
    body += table
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("naeste-helligdag.html")
    body += g.ad_slot("footer")

    g.write_page(
        "naeste-helligdag.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Næste helligdag", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# 5. Ugedag
# ---------------------------------------------------------------------------


def render_ugedag(g) -> None:
    today = date.today().isoformat()

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="wd-date">Dato</label>
    <input id="wd-date" type="date" value="{today}"></div>
</div>
<div id="wd-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
<div id="wd-around" style="margin-top:1rem"></div>
</div></div></section>
<script>
(function(){{
  var WD=['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag'];
  var MONTHS=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december'];
  function parse(s){{var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}}
  function isoWeek(d){{
    var t=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()));
    var day=t.getUTCDay()||7;
    t.setUTCDate(t.getUTCDate()+4-day);
    var ys=new Date(Date.UTC(t.getUTCFullYear(),0,1));
    return Math.ceil((((t-ys)/86400000)+1)/7);
  }}
  function doy(d){{
    var s=new Date(Date.UTC(d.getUTCFullYear(),0,1));
    return Math.floor((d-s)/86400000)+1;
  }}
  function wdName(d){{var w=d.getUTCDay(); return WD[(w+6)%7];}}
  function update(){{
    var inp=document.getElementById('wd-date'), out=document.getElementById('wd-result'),
        around=document.getElementById('wd-around');
    if(!inp||!out) return;
    var d=parse(inp.value);
    if(isNaN(d)){{out.innerHTML='Vælg en gyldig dato.';return;}}
    var name=wdName(d);
    var pretty=d.getUTCDate()+'. '+MONTHS[d.getUTCMonth()]+' '+d.getUTCFullYear();
    out.innerHTML='<strong>'+pretty+' faldt på en '+name+'</strong>'+
      '<br><span>ISO-uge '+isoWeek(d)+' · dag '+doy(d)+' i året</span>';
    var rows='<table><thead><tr><th>År</th><th>Dato</th><th>Ugedag</th></tr></thead><tbody>';
    for(var i=-1;i<=5;i++){{
      var y=d.getUTCFullYear()+i;
      var dd=new Date(Date.UTC(y, d.getUTCMonth(), d.getUTCDate()));
      var ds=y+'-'+String(d.getUTCMonth()+1).padStart(2,'0')+'-'+String(d.getUTCDate()).padStart(2,'0');
      rows+='<tr><td>'+y+'</td><td>'+ds+'</td><td>'+wdName(dd)+'</td></tr>';
    }}
    rows+='</tbody></table>';
    around.innerHTML='<div class="table-wrap">'+rows+'</div>';
  }}
  document.addEventListener('input', update);
  document.addEventListener('change', update);
  document.addEventListener('DOMContentLoaded', update);
  update();
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvilken ugedag falder en dato på?</h2>
<p>Værktøjet finder ugedagen for enhver dato – fortid, nutid eller fremtid.
Det er praktisk, når du skal tjekke fødselsdage, gamle kontrakter, historiske
begivenheder eller fremtidige planlagte mærkedage.</p>
<h2>Bonus: samme dato i nærliggende år</h2>
<p>Tabellen viser den samme dato fra året før til fem år frem. Sådan kan du
hurtigt se, om en mærkedag falder på en hverdag eller weekend i de
kommende år.</p>
<h2>ISO-uge og dagnummer</h2>
<p>Værktøjet viser også ISO-ugen (den standard, danske kalendere bruger) og
dagnummeret i året (1-365 eller 1-366 i skudår). Det kan være nyttigt i
forretningsplanlægning og rapportering.</p>
""")

    faq = [
        (
            "Hvilken ugedagsorden bruges?",
            "Værktøjet følger ISO 8601, hvor ugen starter mandag. Det er "
            "standarden i Danmark og resten af Europa.",
        ),
        (
            "Virker værktøjet for datoer langt tilbage i tiden?",
            "Ja. JavaScript kan håndtere datoer mange århundreder tilbage. "
            "Bemærk dog, at den gregorianske kalender først blev indført i "
            "1700 i Danmark, så ugedage før det skal tolkes med omhu.",
        ),
        (
            "Tæller skudår med i dagnummeret?",
            "Ja. Skudår har 366 dage, så datoer efter 29. februar får et "
            "andet dagnummer end i normale år.",
        ),
        (
            "Hvad er ISO-uge?",
            "ISO-uge er en internationalt anerkendt nummerering, hvor uge 1 "
            "altid indeholder årets første torsdag. Det betyder, at året kan "
            "have enten 52 eller 53 ISO-uger.",
        ),
    ]

    title = "Ugedag – hvilken ugedag faldt datoen på?"
    desc = (
        "Find ud af, hvilken ugedag en dato faldt på (eller falder på). "
        "Bonus: samme dato i nærliggende år."
    )
    body = g.hero(
        "Ugedag",
        "Find ugedagen for enhver dato. Nyttigt til fødsler, gamle kontrakter "
        "og historiske datoer. Se også samme dato i 5 nærliggende år.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("ugedag.html")
    body += g.ad_slot("footer")

    g.write_page(
        "ugedag.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Ugedag", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# 6. Dato +/- N dage
# ---------------------------------------------------------------------------


def render_dato_plus_dage(g) -> None:
    today = date.today().isoformat()

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="pd-start">Startdato</label>
    <input id="pd-start" type="date" value="{today}"></div>
  <div class="field"><label for="pd-op">Operation</label>
    <select id="pd-op"><option value="plus">Læg til (+)</option><option value="minus">Træk fra (−)</option></select></div>
  <div class="field"><label for="pd-n">Antal dage</label>
    <input id="pd-n" type="number" min="0" value="30"></div>
</div>
<div id="pd-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
</div></div></section>
<script>
(function(){{
  var WD=['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag'];
  var MONTHS=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december'];
  function parse(s){{var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}}
  function fmtDK(d){{return d.getUTCDate()+'. '+MONTHS[d.getUTCMonth()]+' '+d.getUTCFullYear();}}
  function update(){{
    var s=document.getElementById('pd-start'), op=document.getElementById('pd-op'),
        n=document.getElementById('pd-n'), out=document.getElementById('pd-result');
    if(!s||!n||!out) return;
    var d=parse(s.value);
    var days=parseInt(n.value,10);
    if(isNaN(d)||isNaN(days)){{out.innerHTML='Vælg en dato og et tal.';return;}}
    var sign = (op && op.value==='minus')? -1 : 1;
    var res=new Date(d.getTime()+sign*days*86400000);
    var name=WD[(res.getUTCDay()+6)%7];
    out.innerHTML='<strong>'+fmtDK(res)+'</strong>'+
      '<br><span>'+days+' kalenderdage '+(sign>0?'efter':'før')+' '+fmtDK(d)+' = '+name+'</span>';
  }}
  document.addEventListener('input', update);
  document.addEventListener('change', update);
  document.addEventListener('DOMContentLoaded', update);
  update();
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvornår skal du tælle kalenderdage?</h2>
<p>Mange frister i Danmark regnes i <strong>kalenderdage</strong>, ikke
arbejdsdage. Det gælder fx fortrydelsesret, opsigelsesvarsler i visse
kontrakter, lægelige forløb og graviditetsterminer.</p>
<h2>Eksempler på brug</h2>
<ul>
<li><strong>Returret:</strong> 14 dage fra modtagelse af varen.</li>
<li><strong>Graviditet:</strong> 280 dage fra sidste menstruation.</li>
<li><strong>Kontraktfrister:</strong> 30, 60 eller 90 dages varsel.</li>
<li><strong>Klagefrister:</strong> typisk 4 uger = 28 kalenderdage.</li>
</ul>
<h2>Forskel på dette værktøj og "Læg arbejdsdage til"</h2>
<p>Denne beregner tæller <em>alle</em> dage med – også weekender og
helligdage. Hvis du i stedet skal finde en dato N arbejdsdage frem, skal
du bruge værktøjet <a href="laeg-arbejdsdage-til.html">Læg arbejdsdage til</a>
eller <a href="traek-arbejdsdage-fra.html">Træk arbejdsdage fra</a>.</p>
""")

    faq = [
        (
            "Tæller startdagen med?",
            "Nej. Beregneren lægger N dage til startdatoen, så resultatet er "
            "startdatoen plus N. Hvis du vil tælle startdagen med, skal du "
            "trække 1 fra antallet.",
        ),
        (
            "Hvad sker der, hvis resultatet havner i et nyt år?",
            "Beregneren håndterer årsskifter automatisk – også skudår.",
        ),
        (
            "Kan jeg bruge negative tal?",
            "Du kan ikke skrive negativt, men du kan vælge \"Træk fra\" som "
            "operation. Det giver samme resultat som at lægge et negativt "
            "antal til.",
        ),
        (
            "Hvorfor svarer det ikke til \"30 arbejdsdage\"?",
            "Fordi dette værktøj tæller alle dage. Hvis du vil springe "
            "weekender og helligdage over, så brug arbejdsdage-værktøjerne.",
        ),
    ]

    title = "Dato ± N dage – læg dage til eller træk fra"
    desc = (
        "Læg N kalenderdage til en dato eller træk dem fra. Velegnet til "
        "frister, forfald, graviditet og kontrakter."
    )
    body = g.hero(
        "Dato ± N dage",
        "Læg N kalenderdage til eller træk fra en dato. Velegnet til frister, "
        "forfald, graviditet og kontrakter.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("dato-plus-dage.html")
    body += g.ad_slot("footer")

    g.write_page(
        "dato-plus-dage.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Dato ± N dage", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# 7. Træk arbejdsdage fra
# ---------------------------------------------------------------------------


def render_traek_arbejdsdage_fra(g) -> None:
    today = date.today().isoformat()
    holidays = _holiday_js_data(g)

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="ta-start">Slutdato</label>
    <input id="ta-start" type="date" value="{today}"></div>
  <div class="field"><label for="ta-n">Antal arbejdsdage</label>
    <input id="ta-n" type="number" min="0" value="10"></div>
  <div class="field"><label for="ta-mode">Regel</label>
    <select id="ta-mode"><option value="official">Kun officielle helligdage</option><option value="office">Kontor-variant</option></select></div>
</div>
<div id="ta-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
</div></div></section>
<script>
(function(){{
  var WD=['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag'];
  var MONTHS=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december'];
  var HOL={holidays};
  var OFFICE_NAMES={{'Arbejdernes kampdag':1,'Grundlovsdag':1,'Juleaftensdag':1,'Nytårsaftensdag':1}};
  function parse(s){{var p=s.split('-').map(Number);return new Date(Date.UTC(p[0],p[1]-1,p[2]));}}
  function fmt(d){{return d.getUTCFullYear()+'-'+String(d.getUTCMonth()+1).padStart(2,'0')+'-'+String(d.getUTCDate()).padStart(2,'0');}}
  function fmtDK(d){{return d.getUTCDate()+'. '+MONTHS[d.getUTCMonth()]+' '+d.getUTCFullYear();}}
  function holidaysFor(y){{return HOL[String(y)]||[];}}
  function isHoliday(d, includeOffice){{
    var iso=fmt(d);
    var list=holidaysFor(d.getUTCFullYear());
    for(var i=0;i<list.length;i++){{
      if(list[i].date===iso){{
        if(list[i].official) return true;
        if(includeOffice && OFFICE_NAMES[list[i].name]) return true;
      }}
    }}
    return false;
  }}
  function isWorkday(d, includeOffice){{
    var wd=d.getUTCDay();
    if(wd===0||wd===6) return false;
    return !isHoliday(d, includeOffice);
  }}
  function update(){{
    var s=document.getElementById('ta-start'), n=document.getElementById('ta-n'),
        m=document.getElementById('ta-mode'), out=document.getElementById('ta-result');
    if(!s||!n||!out) return;
    var d=parse(s.value);
    var days=parseInt(n.value,10);
    if(isNaN(d)||isNaN(days)||days<0){{out.innerHTML='Vælg en gyldig dato og et positivt antal arbejdsdage.';return;}}
    var includeOffice = m && m.value==='office';
    var origin=new Date(d.getTime());
    var left=days;
    while(left>0){{
      d=new Date(d.getTime()-86400000);
      if(isWorkday(d, includeOffice)) left--;
    }}
    var name=WD[(d.getUTCDay()+6)%7];
    var calendarDays=Math.round((origin-d)/86400000);
    out.innerHTML='<strong>'+fmtDK(d)+'</strong>'+
      '<br><span>'+days+' arbejdsdage før '+fmtDK(origin)+' = '+name+'</span>'+
      '<br><span>Det svarer til '+calendarDays+' kalenderdage tilbage.</span>';
  }}
  document.addEventListener('input', update);
  document.addEventListener('change', update);
  document.addEventListener('DOMContentLoaded', update);
  update();
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvorfor regne baglæns i arbejdsdage?</h2>
<p>Mange frister i Danmark angives som et antal arbejdsdage <em>før</em>
en bestemt deadline – fx betaling 10 arbejdsdage før en ydelse, afmelding
af kursus eller indlevering af materiale.</p>
<h2>Hvilke dage tæller som arbejdsdage?</h2>
<p>Som standard tæller mandag til fredag minus officielle helligdage. Den
valgfri kontor-variant trækker også 1. maj, Grundlovsdag, juleaftensdag og
nytårsaftensdag fra, da mange arbejdspladser holder lukket disse dage.</p>
<h2>Modstykket: læg arbejdsdage til</h2>
<p>Hvis du i stedet skal finde en dato N arbejdsdage <em>frem</em>, så brug
<a href="laeg-arbejdsdage-til.html">Læg arbejdsdage til</a>. Sammen dækker
de to værktøjer de fleste frister i kontrakter og forvaltning.</p>
""")

    faq = [
        (
            "Tælles slutdatoen som arbejdsdag?",
            "Nej. Beregneren tager udgangspunkt i slutdatoen og går baglæns. "
            "Den første arbejdsdag, den finder, er dagen før slutdatoen "
            "(forudsat den er en hverdag).",
        ),
        (
            "Hvad er kontor-varianten?",
            "Kontor-varianten trækker også 1. maj, Grundlovsdag, juleaftensdag "
            "og nytårsaftensdag fra. Mange overenskomster giver fri disse "
            "dage, selvom de juridisk er almindelige arbejdsdage.",
        ),
        (
            "Tager beregneren højde for skoleferier?",
            "Nej. Skoleferier er lokale og påvirker ikke arbejdsdage. Brug "
            "siden <a href=\"skoleferier.html\">Skoleferier</a> til "
            "kommunale ferieplaner.",
        ),
        (
            "Hvad nu hvis svaret falder på en helligdag i et tidligere år?",
            "Beregneren benytter helligdagsdata for både indeværende og "
            "tidligere år, så den giver korrekte svar selv ved store "
            "tilbageregninger.",
        ),
    ]

    title = "Træk arbejdsdage fra en dato"
    desc = (
        "Træk N arbejdsdage fra en dato. Værktøjet springer weekender og "
        "danske helligdage over."
    )
    body = g.hero(
        "Træk arbejdsdage fra",
        "Træk N arbejdsdage fra en dato. Modsat af \"Læg arbejdsdage til\". "
        "Tager hensyn til weekender og danske helligdage.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("traek-arbejdsdage-fra.html")
    body += g.ad_slot("footer")

    g.write_page(
        "traek-arbejdsdage-fra.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Træk arbejdsdage fra", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# 8. Dato fra ugenummer
# ---------------------------------------------------------------------------


def render_dato_fra_uge(g) -> None:
    today = date.today()
    cur_year = today.year

    tool = f"""
<section class="section"><div class="container"><div class="tool">
<div class="tool-grid">
  <div class="field"><label for="dw-year">År</label>
    <input id="dw-year" type="number" min="2000" max="2060" value="{cur_year}"></div>
  <div class="field"><label for="dw-week">ISO-uge</label>
    <input id="dw-week" type="number" min="1" max="53" value="1"></div>
  <div class="field"><label for="dw-day">Ugedag</label>
    <select id="dw-day">
      <option value="1">Mandag</option><option value="2">Tirsdag</option>
      <option value="3">Onsdag</option><option value="4">Torsdag</option>
      <option value="5">Fredag</option><option value="6">Lørdag</option>
      <option value="7">Søndag</option>
    </select></div>
</div>
<div id="dw-result" class="result-box" aria-live="polite" aria-atomic="true"></div>
</div></div></section>
<script>
(function(){{
  var WD=['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag'];
  var MONTHS=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december'];
  function isoWeekDate(year, week, day){{
    // Day: 1=Monday .. 7=Sunday (ISO)
    var jan4=new Date(Date.UTC(year,0,4));
    var jan4Day=jan4.getUTCDay()||7;
    var mondayWeek1=new Date(jan4.getTime() - (jan4Day-1)*86400000);
    return new Date(mondayWeek1.getTime() + ((week-1)*7 + (day-1))*86400000);
  }}
  function doy(d){{
    var s=new Date(Date.UTC(d.getUTCFullYear(),0,1));
    return Math.floor((d-s)/86400000)+1;
  }}
  function fmtISO(d){{return d.getUTCFullYear()+'-'+String(d.getUTCMonth()+1).padStart(2,'0')+'-'+String(d.getUTCDate()).padStart(2,'0');}}
  function update(){{
    var y=document.getElementById('dw-year'), w=document.getElementById('dw-week'),
        dy=document.getElementById('dw-day'), out=document.getElementById('dw-result');
    if(!y||!w||!dy||!out) return;
    var year=parseInt(y.value,10), week=parseInt(w.value,10), day=parseInt(dy.value,10);
    if(isNaN(year)||isNaN(week)||isNaN(day)){{out.innerHTML='Vælg gyldigt år, uge og ugedag.';return;}}
    if(week<1||week>53){{out.innerHTML='ISO-uger går fra 1 til 53.';return;}}
    var d=isoWeekDate(year, week, day);
    var pretty=d.getUTCDate()+'. '+MONTHS[d.getUTCMonth()]+' '+d.getUTCFullYear();
    out.innerHTML='<strong>'+fmtISO(d)+' ('+WD[day-1]+')</strong>'+
      '<br><span>'+pretty+'</span>'+
      '<br><span>Dag '+doy(d)+' i året '+d.getUTCFullYear()+'.</span>';
    if(d.getUTCFullYear()!==year){{
      out.innerHTML += '<br><span class="muted">OBS: datoen ligger i kalenderåret '+d.getUTCFullYear()+' pga. ISO-ugeoverlappet.</span>';
    }}
  }}
  document.addEventListener('input', update);
  document.addEventListener('change', update);
  document.addEventListener('DOMContentLoaded', update);
  update();
}})();
</script>
"""

    prose = _prose_block("""
<h2>Hvad er en ISO-uge?</h2>
<p>ISO-uge er en standardiseret nummerering af ugerne, hvor uge 1 altid
indeholder årets første torsdag. Det betyder, at uge 1 kan starte i det
foregående år og uge 53 kan strække sig ind i det næste.</p>
<h2>Brug i virksomhedsplanlægning</h2>
<p>Mange virksomheder, projekter og produktionsplaner refererer til
ugenumre i stedet for datoer – fx \"levering uge 27, torsdag\". Dette
værktøj omsætter den slags planer til en konkret kalenderdato.</p>
<h2>Modstykket</h2>
<p>Hvis du i stedet har en dato og vil finde dens ISO-uge, så brug
<a href="ugenummer.html">Ugenummer</a>.</p>
""")

    faq = [
        (
            "Kan et år have 53 ISO-uger?",
            "Ja. Hvis 1. januar falder på en torsdag, eller hvis året er et "
            "skudår, der starter på en onsdag, har året 53 ISO-uger.",
        ),
        (
            "Hvad sker der, hvis jeg vælger uge 1, mandag i januar?",
            "Resultatet kan ligge i december det foregående år, fordi ISO-uge "
            "1 nogle gange begynder i december. Værktøjet markerer det "
            "tydeligt.",
        ),
        (
            "Hvilken dag er \"dag 1\" i ugen?",
            "Mandag. ISO-standarden definerer mandag som ugens første dag, "
            "og det er den danske kalenderstandard.",
        ),
        (
            "Hvordan beregnes resultatet?",
            "Vi finder mandagen i uge 1 (mandagen før eller på 4. januar) "
            "og lægger derefter (uge-1)·7 + (dag-1) dage til.",
        ),
    ]

    title = "Dato fra ugenummer – find kalenderdato af ISO-uge"
    desc = (
        "Givet år + ISO-ugenummer + ugedag, returner den konkrete kalenderdato. "
        "Nyttigt til virksomhedsplanlægning og logistik."
    )
    body = g.hero(
        "Dato fra ugenummer",
        "Find kalenderdatoen for en bestemt ISO-uge og ugedag. Nyttigt til "
        "virksomhedsplanlægning – f.eks. \"uge 27 i 2027, torsdag\".",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += tool
    body += g.ad_slot("mid")
    body += prose
    body += _related_tools("dato-fra-uge.html")
    body += g.ad_slot("footer")

    g.write_page(
        "dato-fra-uge.html",
        title,
        desc,
        body,
        breadcrumbs=[("Forside", "index.html"), ("Dato fra ugenummer", "")],
        faq=faq,
    )


# ---------------------------------------------------------------------------
# Hub page that links to all extra tools.
# ---------------------------------------------------------------------------


def render_tools_hub(g) -> None:
    descriptions = {
        "aldersberegner.html": "Nøjagtig alder i år, måneder og dage – plus levede dage.",
        "dato-difference.html": "Forskel mellem to datoer i år, måneder, uger, dage, timer og minutter.",
        "nedtaelling.html": "Live nedtælling til en vigtig dato. Delbar permalink.",
        "naeste-helligdag.html": "Næste danske helligdag og de 5 efterfølgende.",
        "ugedag.html": "Hvilken ugedag faldt en bestemt dato på?",
        "dato-plus-dage.html": "Læg N kalenderdage til eller træk fra en dato.",
        "traek-arbejdsdage-fra.html": "Træk N arbejdsdage fra en dato (modsat af læg til).",
        "dato-fra-uge.html": "Find datoen ud fra år, ISO-uge og ugedag.",
    }
    cards = []
    for slug, label in EXTRA_TOOL_PAGES:
        cards.append(
            f'<a class="card" href="{slug}"><h3>{label}</h3>'
            f'<p class="muted">{descriptions.get(slug, "")}</p></a>'
        )

    body = g.hero(
        "Værktøjer",
        "Samling af danske kalender- og dato-beregnere. Alle værktøjer er "
        "gratis, uden login og kører lokalt i din browser.",
        date.today().year,
    )
    body += g.ad_slot("header")
    body += (
        '<section class="section"><div class="container">'
        '<div class="section-title"><div><h2>Alle værktøjer</h2>'
        '<p>Vælg det værktøj, du har brug for.</p></div></div>'
        f'<div class="grid">{"".join(cards)}</div>'
        '</div></section>'
    )
    body += g.ad_slot("mid")

    g.write_page(
        "vaerktoejer.html",
        "Værktøjer – danske kalender- og dato-beregnere",
        "Samling af danske kalender- og dato-beregnere på DanskeDage.dk.",
        body,
        breadcrumbs=[("Forside", "index.html"), ("Værktøjer", "")],
    )


# ---------------------------------------------------------------------------
# Public entry point used by generate_site.py
# ---------------------------------------------------------------------------


def render_all(g) -> list[str]:
    """Generate all extra tool pages. Returns list of HTML filenames produced."""

    render_aldersberegner(g)
    render_dato_difference(g)
    render_nedtaelling(g)
    render_naeste_helligdag(g)
    render_ugedag(g)
    render_dato_plus_dage(g)
    render_traek_arbejdsdage_fra(g)
    render_dato_fra_uge(g)
    render_tools_hub(g)

    return [slug for slug, _ in EXTRA_TOOL_PAGES] + ["vaerktoejer.html"]
