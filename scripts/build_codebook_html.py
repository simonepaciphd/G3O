#!/usr/bin/env python3
"""
build_codebook_html.py — front-facing coverage codebook for the G3O institution
master, as a single self-contained HTML document.

Replaces the PDF codebook (PI ruling 2026-08-08: the coverage codebook ships as
HTML and HTML fully replaces the PDF; the 2026-08-08 PDF build is the last one).
The retired generator, `build_codebook_pdf.py`, lives beside the master on
Drive under `inputs/G3O_Institution_Master/scripts/python/` until the WS7 code
migration moves the master-build scripts into this repo; this script is the
first WS7 landing in `scripts/`. Aggregation logic and SOURCE_LEGEND are ported
from it unchanged.

Reads the canonical master (`data_final/master_institutions.csv`) and documents
coverage at the grain

    country  x  government_level  x  institution_type

with, per category, the institution count and the *actual* source(s) it came
from — the specific official register / statistical URL for compiled
subnational rows, or the organization name + URL for cross-country sources.
Provenance is listed inline in the coverage table; there is no appendix.

Structure of the document:
  1. Title + the vintage line, derived from the master's own `master_build_id`
     column (never typed by hand — the numbers and the vintage cannot move
     separately).
  2. Summary: totals and breakdowns by government level and institution type.
  3. Coverage detail: grouped by country (A-Z); within each country one row per
     (government_level x institution_type) with count and source(s).

The document deliberately carries NO reliability figure of any kind — no
accuracy, agreement, determinism, precision, recall, or error-rate number.
It describes what the registry holds, not how well anything performs.

The HTML is self-contained: inline CSS, no scripts, no external requests. It is
served as a static asset from the g3o-website repo (`public/codebook/`) and
linked from the registry methodology page.

Usage:
    python scripts/build_codebook_html.py --master X --outdir Y
    python scripts/build_codebook_html.py --master X --outdir Y --summary-json

Requires: Python 3.10+, stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# --------------------------------------------------------------------------- #
# Readable labels — ported verbatim from build_codebook_pdf.py (2026-08-08
# state, i.e. including the PI-signed NCES entry). Unknown values fall back to
# a humanized version of the code, so the script stays correct as the master
# gains new levels/types/sources.
# --------------------------------------------------------------------------- #
LEVEL_LABELS = {
    "national": "National",
    "first_subnational": "First subnational (state / province / region)",
    "second_subnational": "Second subnational (county / district)",
    "local": "Local (municipality / city / commune)",
    "other": "Other",
}
# Order used in summary + detail (unknown levels appended alphabetically after).
LEVEL_ORDER = ["national", "first_subnational", "second_subnational", "local", "other"]

TYPE_LABELS = {
    "municipality": "Municipality",
    "district": "District",
    "school_district": "School district",
    "region": "Region",
    "ministry": "Ministry",
    "parliament": "Parliament",
    "supreme_court": "Supreme court",
    "constitutional_court": "Constitutional court",
    "statistical_office": "Statistical office",
    "ip_office": "IP office",
    "supreme_audit": "Supreme audit institution",
    "telecom_regulator": "Telecom regulator",
    "fiu": "Financial intelligence unit",
    "central_bank": "Central bank",
    "customs_admin": "Customs administration",
    "tax_admin": "Tax administration",
    "insurance_regulator": "Insurance regulator",
    "ombudsman": "Ombudsman",
    "securities_regulator": "Securities regulator",
    "energy_regulator": "Energy regulator",
    "competition": "Competition authority",
    "election_management": "Electoral management body",
    "data_protection": "Data protection authority",
    "anti_corruption": "Anti-corruption authority",
    "banking_supervisor": "Banking supervisor",
}

# dataset_id -> (readable name, canonical org URL). URLs are well-known, stable
# organization homepages. Unknown ids humanize the code and carry no URL.
SOURCE_LEGEND = {
    "subnational_RAs": ("Compiled by G3O from official sources", ""),
    "subnational_automated": ("geoBoundaries / GADM — subnational governments", "https://www.geoboundaries.org"),
    "nces_district_websites": ("NCES Common Core of Data — US school districts", "https://nces.ed.gov/ccd/"),
    "cross_country_executive_national_whogov": ("WhoGov V3.1 — national executive / ministries", "https://www.bsg.ox.ac.uk/about/partnerships/who-governs"),
    "cross_country_legislative_national_ipu": ("IPU Parline — national parliaments", "https://data.ipu.org"),
    "cross_country_judicial_national_factbook": ("CIA World Factbook — national supreme / constitutional courts", "https://www.cia.gov/the-world-factbook/field/judicial-branch/"),
    "unsd_nso": ("UN Statistics Division — national statistical offices", "https://unstats.un.org"),
    "wipo_members": ("WIPO — national intellectual-property offices", "https://www.wipo.int"),
    "intosai_members": ("INTOSAI — supreme audit institutions", "https://www.intosai.org"),
    "itu_regulators": ("ITU — telecommunications regulators", "https://www.itu.int"),
    "egmont_members": ("Egmont Group — financial intelligence units", "https://egmontgroup.org"),
    "bis_central_banks": ("BIS — central banks", "https://www.bis.org"),
    "wco_members": ("WCO — customs administrations", "https://www.wcoomd.org"),
    "imf_isora": ("IMF ISORA — tax administrations", "https://www.imf.org/en/Data/ISORA"),
    "iais_members": ("IAIS — insurance regulators", "https://www.iaisweb.org"),
    "ioi_members": ("IOI — ombudsman institutions", "https://www.theioi.org"),
    "iosco_members": ("IOSCO — securities regulators", "https://www.iosco.org"),
    "icer_members": ("ICER — energy regulators", "https://www.icer-regulators.net"),
    "icn_members": ("ICN — competition authorities", "https://www.internationalcompetitionnetwork.org"),
    "idea_emd": ("International IDEA — electoral management bodies", "https://www.idea.int"),
    "gpa_members": ("Global Privacy Assembly — data protection authorities", "https://globalprivacyassembly.org"),
    "unodc_acauthorities": ("UNODC — anti-corruption authorities", "https://www.unodc.org"),
    "bcbs_members": ("BCBS — banking supervisors", "https://www.bis.org/bcbs"),
}

# Dataset ids whose rows each carry a specific per-row source_url (an official
# register / statistical-office page, or — for national judicial — that country's
# CIA World Factbook page). Provenance is shown inline per category, so the actual
# source varies by institution rather than collapsing to one blanket label.
PRIMARY_SOURCE_IDS = {
    "subnational_RAs",
    "cross_country_judicial_national_factbook",
}


def split_source_url(raw: str) -> tuple[str, str]:
    """Split a stored source_url into (url, note). Many primary-collection URLs
    carry a trailing free-text descriptor, e.g.
        'https://lgdirectory.gov.in (LGD: 255,293 gram panchayats ...)'
    Returns ('', '') for blanks, (url, '') for a bare URL, (url, note) otherwise."""
    s = (raw or "").strip()
    if not s:
        return "", ""
    parts = s.split(None, 1)
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")


def humanize(code: str) -> str:
    return str(code).replace("_", " ").strip().capitalize() if code else "(blank)"


def level_label(code: str) -> str:
    return LEVEL_LABELS.get(code, humanize(code))


def type_label(code: str) -> str:
    return TYPE_LABELS.get(code, humanize(code))


def source_name(code: str) -> str:
    return SOURCE_LEGEND.get(code, (humanize(code), ""))[0]


def source_url(code: str) -> str:
    return SOURCE_LEGEND.get(code, (humanize(code), ""))[1]


def level_sort_key(code: str):
    return (LEVEL_ORDER.index(code) if code in LEVEL_ORDER else len(LEVEL_ORDER), code)


def fmt_int(n: int) -> str:
    return f"{int(n):,}"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def link(url: str, text: str) -> str:
    return f'<a href="{esc(url)}" rel="noopener">{esc(text)}</a>'


# --------------------------------------------------------------------------- #
# Aggregation — same grain and same dedup rules as the PDF generator.
# --------------------------------------------------------------------------- #
def row_source_ref(sid: str, surl: str) -> tuple[str, str]:
    """Resolve one master row to (dedup_key, html_display) for its *actual* source.

    - Compiled subnational rows (PRIMARY_SOURCE_IDS) carry a specific official
      register / statistical-office URL in `source_url`; that URL (plus any
      free-text note) is the real provenance and is shown verbatim.
    - Cross-country rows resolve to the organization's readable name hyperlinked
      to its canonical homepage.
    Unknown ids fall back to a humanized name with no URL."""
    if sid in PRIMARY_SOURCE_IDS:
        url, note = split_source_url(surl)
        if url:
            disp = link(url, url)
            if note:
                disp += f' <span class="note">{esc(note)}</span>'
            return url, disp
        if note:
            return "note:" + note, esc(note)
        return sid, esc(source_name(sid))
    name = source_name(sid)
    url = source_url(sid)
    return sid, (link(url, name) if url else esc(name))


def aggregate(master: Path):
    """Single pass over the master. Returns (detail, summaries, build_id).

    Grain of `detail`: {(country, level, type): [count, {ref_key: ref_display}]}
    with provenance inlined — there is no appendix."""
    counts: Counter = Counter()
    refs: defaultdict = defaultdict(dict)
    build_ids: Counter = Counter()
    countries_iso: dict[str, str] = {}
    by_level: Counter = Counter()
    by_type: Counter = Counter()
    ref_keys: set[str] = set()
    n_rows = 0

    with master.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"country", "government_level", "institution_type",
                    "source_dataset_id", "source_url", "master_build_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"ERROR: master lacks required column(s): {sorted(missing)}")
        for row in reader:
            n_rows += 1
            country = (row.get("country") or "").strip()
            level = (row.get("government_level") or "").strip()
            itype = (row.get("institution_type") or "").strip()
            sid = (row.get("source_dataset_id") or "").strip()
            surl = (row.get("source_url") or "").strip()
            build_ids[(row.get("master_build_id") or "").strip()] += 1
            iso = (row.get("country_iso3") or "").strip()
            if country not in countries_iso and iso:
                countries_iso[country] = iso

            key = (country, level, itype)
            counts[key] += 1
            by_level[level] += 1
            by_type[itype] += 1
            ref_key, ref_disp = row_source_ref(sid, surl)
            ref_keys.add(ref_key)
            refs[key].setdefault(ref_key, ref_disp)

    if len(build_ids) != 1:
        raise SystemExit(
            "ERROR: master carries "
            f"{len(build_ids)} distinct master_build_id values {sorted(build_ids)!r}; "
            "refusing to stamp a vintage on a mixed build."
        )
    build_id = next(iter(build_ids))

    summaries = {
        "n_rows": n_rows,
        "n_countries": len({c for (c, _, _) in counts}),
        "n_levels": len(by_level),
        "n_types": len(by_type),
        # Count the *actual* sources the table cites (distinct official registers +
        # cross-country organizations), not the internal source_dataset_id buckets:
        # the latter (~22) badly understates a table that names hundreds of sources.
        "n_sources": len(ref_keys),
        "n_detail_categories": len(counts),
        "by_level": dict(by_level),
        "by_type": dict(by_type),
        "iso_by_country": countries_iso,
    }
    return counts, refs, summaries, build_id


def vintage_from_build_id(build_id: str) -> str:
    """The vintage line comes FROM the data: `mb-YYYY-MM-DD` carries its own
    as-of date, so a regenerated document can never pair fresh numbers with a
    stale date or vice versa."""
    m = re.fullmatch(r"mb-(\d{4}-\d{2}-\d{2})", build_id)
    if not m:
        raise SystemExit(
            f"ERROR: master_build_id {build_id!r} does not match 'mb-YYYY-MM-DD'; "
            "cannot derive the vintage line."
        )
    return f"As of {m.group(1)}, from master build {build_id}."


# --------------------------------------------------------------------------- #
# Document generation
# --------------------------------------------------------------------------- #
# Palette matches the PDF's: navy headers, pale blue country bands. Inline and
# self-contained by design — the document must render with no external request.
CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 0 1rem 4rem; background: #fff; color: #1a1a1a;
         font: 16px/1.5 Georgia, 'Times New Roman', serif; }
  main { max-width: 60rem; margin: 0 auto; }
  header { text-align: center; padding: 2.5rem 0 1rem; border-bottom: 2px solid #1f3b5f; }
  header h1 { font-size: 1.6rem; margin: 0; color: #1f3b5f; }
  header p.sub { font-size: 1.15rem; margin: .4rem 0 0; }
  header p.vintage { font-size: .9rem; color: #444; margin: .8rem 0 0; }
  h2 { color: #1f3b5f; font-size: 1.25rem; margin: 2.2rem 0 .6rem; }
  h3 { color: #1f3b5f; font-size: 1.05rem; margin: 1.8rem 0 .4rem;
       background: #e8eef6; padding: .35rem .5rem; }
  p.lead { max-width: 44rem; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; }
  th { text-align: left; color: #1f3b5f; border-bottom: 2px solid #1f3b5f;
       padding: .4rem .6rem .4rem 0; vertical-align: bottom; }
  td { border-bottom: 1px solid #d9dee6; padding: .4rem .6rem .4rem 0;
       vertical-align: top; }
  td.num, th.num { text-align: right; white-space: nowrap; padding-right: 1.2rem; }
  table.kv { max-width: 28rem; }
  table.kv td:last-child { text-align: right; font-weight: bold; }
  a { color: #1a4f9c; word-break: break-all; }
  .note { display: block; font-size: .8rem; color: #555; }
  .src { max-width: 30rem; }
  @media (max-width: 640px) { body { font-size: 15px; } th, td { padding-right: .5rem; } }
"""

OVERVIEW = (
    "This codebook summarises the government institutions catalogued in the G3O "
    "database. For every country (identified by its ISO 3166-1 alpha-3 code) it "
    "lists, at each level of government, the types of public institution on "
    "record, how many of each, and the actual source each was drawn from. "
    "Sources are listed inline in the coverage table: for cross-country "
    "institutions this is the compiling organization; for the subnational "
    "governments that G3O compiles itself, it is the specific official register "
    "or statistical office the records came from."
)


def anchor_id(country: str) -> str:
    return "c-" + re.sub(r"[^a-z0-9]+", "-", country.lower()).strip("-")


def build_html(counts, refs, summaries, vintage: str) -> str:
    L = []
    L.append("<!doctype html>")
    L.append('<html lang="en"><head><meta charset="utf-8">')
    L.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    L.append("<title>G3O — Government Institutions — Coverage Codebook</title>")
    L.append(f"<style>{CSS}</style></head><body><main>")

    L.append("<header>")
    L.append("<h1>G3O Global Government GenAI Observatory</h1>")
    L.append('<p class="sub">Government Institutions — Coverage Codebook</p>')
    L.append(f'<p class="vintage">{esc(vintage)}</p>')
    L.append("</header>")

    L.append(f'<p class="lead">{esc(OVERVIEW)}</p>')

    # ---- Summary ----
    L.append("<h2>Summary</h2>")
    L.append('<div class="tablewrap"><table class="kv"><tbody>')
    for label, val in [
        ("Total institutions", summaries["n_rows"]),
        ("Countries / territories", summaries["n_countries"]),
        ("Government levels", summaries["n_levels"]),
        ("Institution types", summaries["n_types"]),
        ("Distinct sources cited", summaries["n_sources"]),
    ]:
        L.append(f"<tr><td>{esc(label)}</td><td>{fmt_int(val)}</td></tr>")
    L.append("</tbody></table></div>")

    # ---- By government level ----
    L.append("<h2>Institutions by government level</h2>")
    L.append('<div class="tablewrap"><table><thead><tr>'
             '<th>Government level</th><th class="num">Institutions</th>'
             "</tr></thead><tbody>")
    lv = summaries["by_level"]
    for code in sorted(lv, key=level_sort_key):
        L.append(f'<tr><td>{esc(level_label(code))}</td><td class="num">{fmt_int(lv[code])}</td></tr>')
    L.append("</tbody></table></div>")

    # ---- By institution type ----
    L.append("<h2>Institutions by type</h2>")
    L.append('<div class="tablewrap"><table><thead><tr>'
             '<th>Institution type</th><th class="num">Institutions</th>'
             "</tr></thead><tbody>")
    ty = summaries["by_type"]
    for code in sorted(ty, key=lambda c: (-ty[c], c)):
        L.append(f'<tr><td>{esc(type_label(code))}</td><td class="num">{fmt_int(ty[code])}</td></tr>')
    L.append("</tbody></table></div>")

    # ---- Detail table ----
    L.append("<h2>Coverage detail — by country</h2>")
    L.append('<p class="lead">Within each country: one row per government level '
             "× institution type, with the count and the actual source(s) the "
             "records were drawn from.</p>")

    by_country: defaultdict = defaultdict(list)
    for (country, level, itype), n in counts.items():
        by_country[country].append((level, itype, n))

    for country in sorted(by_country):
        iso = summaries["iso_by_country"].get(country, "")
        head = esc(country) + (f" ({esc(iso)})" if iso else "")
        L.append(f'<h3 id="{anchor_id(country)}">{head}</h3>')
        L.append('<div class="tablewrap"><table><thead><tr>'
                 '<th>Government level</th><th>Institution type</th>'
                 '<th class="num">Count</th><th>Source</th></tr></thead><tbody>')
        rows = sorted(by_country[country], key=lambda r: (level_sort_key(r[0]), r[1]))
        for level, itype, n in rows:
            ref_map = refs[(country, level, itype)]
            src = "<br>".join(ref_map[k] for k in sorted(ref_map)) or "—"
            L.append(
                f"<tr><td>{esc(level_label(level))}</td>"
                f"<td>{esc(type_label(itype))}</td>"
                f'<td class="num">{fmt_int(n)}</td>'
                f'<td class="src">{src}</td></tr>'
            )
        L.append("</tbody></table></div>")

    L.append("</main></body></html>")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate the G3O institution-master coverage codebook (self-contained HTML)."
    )
    ap.add_argument("--master", type=Path, required=True, help="path to master_institutions.csv")
    ap.add_argument("--outdir", type=Path, required=True, help="output directory")
    ap.add_argument("--name", default="master_codebook", help="output basename (no extension)")
    ap.add_argument("--summary-json", action="store_true",
                    help="also write <name>.summary.json with the computed aggregates, "
                         "for verification against an independent recompute")
    args = ap.parse_args()

    if not args.master.exists():
        print(f"ERROR: master not found: {args.master}", file=sys.stderr)
        return 2
    args.outdir.mkdir(parents=True, exist_ok=True)

    print(f"Reading master: {args.master}")
    counts, refs, summaries, build_id = aggregate(args.master)
    vintage = vintage_from_build_id(build_id)
    print(f"  {summaries['n_rows']:,} rows | {summaries['n_countries']} countries | "
          f"{summaries['n_types']} types | {summaries['n_sources']} sources | "
          f"{summaries['n_detail_categories']:,} detail categories | {build_id}")

    out = args.outdir / f"{args.name}.html"
    out.write_text(build_html(counts, refs, summaries, vintage), encoding="utf-8", newline="\n")
    print(f"  wrote {out}")

    if args.summary_json:
        sj = args.outdir / f"{args.name}.summary.json"
        sj.write_text(json.dumps({**summaries, "master_build_id": build_id, "vintage": vintage},
                                 indent=2, sort_keys=True),
                      encoding="utf-8", newline="\n")
        print(f"  wrote {sj}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
