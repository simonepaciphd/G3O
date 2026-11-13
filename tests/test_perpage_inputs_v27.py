"""T-030 default v2.7 per-page inputs from stored scrape artifacts (PI ruling D1 a).

A fixture run dir with two institutions and stored ``RenderedPage`` artifacts
(HTML with metadata dates, a URL date, an archive-host URL, a short page,
near-duplicate pages, the same text at a second institution). Checks
``page_id = url_hash(url)``, fields verbatim from the page and master row, each
A-producer value, syndication groups scoped to the institution, and the
refusals kept for values no producer supplies (``followed``, the row values,
``merged_values``; ``discovery_path`` / ``text_source`` unruled). One dispatch
test runs ``run_v27_dispatch`` with the default builder and fake calls: it
refuses before any jev or extractor call. No network: lingua runs locally.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace

import pytest

from g3o.common import date_signals, language_id
from g3o.common import source_fields as sf
from g3o.common.paths import institution_dir
from g3o.extract.batch import url_hash
from g3o.persist.stage6_adapters import MissingUpstreamError
from g3o.run.presweep import orchestrator as orch
from g3o.run.presweep import perpage_inputs_v27 as pin
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep.config import PIPELINE_V27
from g3o.run.presweep.records import institution_record
from g3o.scrape.render import FetchMetadata, RenderedPage
from tests._layout import uid_for, write_manifest

RUN_ID = "R-T030-INPUTS"
ACCESS = "2026-11-10"
I1, I2, I3 = "INST-0000001", "INST-0000002", "INST-0000003"

ROWS = [
    {"master_row_id": "1", "institution_name": "Council One", "country": "Australia", "government_level": "local",
     "branch": "executive", "institution_type": "council", "website": "https://one.example.gov/"},
    {"master_row_id": "2", "institution_name": "Ministerio Dos", "country": "Uruguay",
     "government_level": "national", "branch": "executive", "institution_type": "ministry", "website": ""},
    {"master_row_id": "3", "institution_name": "Agency Three", "country": "Australia",
     "government_level": "national", "branch": "executive", "institution_type": "agency", "website": ""},
]

EN = ("The council announced today that it will begin a pilot of a generative artificial intelligence "
      "assistant to help residents find information about waste collection, permits and local services. "
      "Staff will review every answer before it is published, and the pilot will run for six months while "
      "the council measures accuracy, cost and resident satisfaction across all of its service areas.")
EN_DUP = EN + " Further details follow."


def _page(url, text, *, title="", metadata_dates=None, chrome=None, links=None, emails=None, method="html"):
    return RenderedPage(url=url, text=text, title=title, content_type="html" if method == "html" else "render",
                        fetch_metadata=FetchMetadata(access_date=ACCESS, fetch_method=method),
                        chrome_text=chrome, links=links, email_links=emails, metadata_dates=metadata_dates)


META = [{"tag": date_signals.TAG_SCHEMA, "found_as": "json-ld", "raw": "2025-03-12T10:00:00Z",
         "value": "2025-03-12"}]
LINKS = [{"href": "https://one.example.gov/ai", "text": "AI pilot"}]

P_META = _page("https://one.example.gov/news/ai-pilot", EN, title="AI pilot", metadata_dates=META,
               chrome="Contact us: info@one.example.gov", links=LINKS, emails=["info@one.example.gov"])
P_URL = _page("https://one.example.gov/news/2024/05/20/budget", "Budget papers for the coming year. " * 12,
              title="Budget", metadata_dates=[], chrome="", links=[], emails=[])
P_DUP = _page("https://one.example.gov/media/ai-pilot-release", EN_DUP, title="Release", metadata_dates=[])
P_ARCHIVE = _page("https://web.archive.org/web/2024/https://dos.example.gub.uy/ia", EN, title="Archivo",
                  metadata_dates=None, method="render")
P_SHORT = _page("https://dos.example.gub.uy/contacto", "Contacto.", title="Contacto", metadata_dates=[])

SCRAPED = {I1: [P_META, P_URL, P_DUP], I2: [P_ARCHIVE, P_SHORT], I3: []}


def _run_dir(tmp_path, *, languages="en", manifest=None):
    run_dir = tmp_path / "run"
    write_manifest(run_dir, manifest or {"run_id": RUN_ID, "institutions": [I1, I2, I3],
                                         "config": {"pipeline_version": PIPELINE_V27}})
    for row in ROWS:
        rec = institution_record(row)
        d = institution_dir(run_dir, rec["institution_id"])
        d.mkdir(parents=True, exist_ok=True)
        rec["institution_search_languages"] = languages
        (d / "institution.json").write_text(json.dumps(rec), encoding="utf-8")
    return run_dir


def _built(tmp_path):
    insts = pin.build_perpage_inputs(_run_dir(tmp_path), ROWS, SCRAPED)
    return {i.institution_id: i for i in insts}


def _spec(inst, page):
    return next(s for s in inst.pages if s.page.page_id == url_hash(page.url))


def test_page_input_fields_verbatim_and_page_id_is_url_hash(tmp_path):
    insts = _built(tmp_path)
    assert list(insts) == [I1, I2]  # I3 has no stored page: nothing to code
    one = insts[I1]
    assert [s.page.page_id for s in one.pages] == [url_hash(p.url) for p in SCRAPED[I1]]  # Stage 4 order
    page = _spec(one, P_META).page
    assert page.page_id == url_hash(P_META.url)
    assert (page.url, page.title, page.text, page.chrome_text) == (P_META.url, P_META.title, P_META.text,
                                                                   P_META.chrome_text)
    assert page.links == tuple(LINKS) and page.email_links == ("info@one.example.gov",)
    assert (page.institution_id, page.institution, page.country, page.level_of_government) == \
        (I1, "Council One", "Australia", "local")
    archive = _spec(insts[I2], P_ARCHIVE).page
    assert archive.chrome_text is None and archive.links is None and archive.email_links is None  # not measured
    assert _spec(one, P_URL).page.links == () and _spec(one, P_URL).page.chrome_text == ""


def test_institution_identity_uid_and_run_id(tmp_path):
    one = _built(tmp_path)[I1]
    assert one.run_id == RUN_ID and one.institution_uid == uid_for(I1)
    assert one.institution == {"institution_id": I1, "institution_name": "Council One", "country": "Australia",
                               "branch_of_government": "executive", "level_of_government": "local",
                               "institution_search_languages": "en"}
    assert one.country == "Australia"
    assert one.upstream == pp.InstitutionUpstream(independence_groups=None, merged_values=None)


def test_a1_dates_with_the_recorded_access_date(tmp_path):
    insts = _built(tmp_path)
    meta, url = _spec(insts[I1], P_META), _spec(insts[I1], P_URL)
    assert meta.page.has_metadata_date and url.page.has_metadata_date
    assert meta.upstream.page_fields.publication_date.value == "2025-03-12"
    assert meta.upstream.page_fields.publication_date.date_origin == "metadata"
    assert url.upstream.page_fields.publication_date.value == "2024-05-20"
    assert url.upstream.page_fields.publication_date.date_origin == "web_address"
    for spec in (meta, url, _spec(insts[I2], P_ARCHIVE)):
        assert spec.upstream.page_fields.access_date.value == ACCESS
        assert spec.upstream.page_fields.url.value == spec.page.url
    # No metadata/URL date: the T-022 quote step owns the date; nothing is set (never not_documented here).
    for page in (P_ARCHIVE, P_SHORT):
        spec = _spec(insts[I2], page)
        assert spec.page.has_metadata_date is False and spec.upstream.page_fields.publication_date is None


def test_a1_access_date_bounds_the_window(tmp_path):
    late = _page("https://one.example.gov/news/2027/01/02/x", EN, metadata_dates=[])
    insts = {i.institution_id: i for i in pin.build_perpage_inputs(_run_dir(tmp_path), ROWS[:1], {I1: [late]})}
    spec = insts[I1].pages[0]
    assert spec.page.has_metadata_date is False and spec.upstream.page_fields.publication_date is None


def test_a2_archive_address_and_a3_language(tmp_path):
    insts = _built(tmp_path)
    assert _spec(insts[I2], P_ARCHIVE).upstream.page_fields.archive_address is True
    assert _spec(insts[I1], P_META).upstream.page_fields.archive_address is False
    meta = _spec(insts[I1], P_META).upstream.page_fields.language
    assert meta.value == sf.source_language(EN).value and meta.value not in (language_id.UNKNOWN, language_id.MUL)
    assert _spec(insts[I2], P_SHORT).upstream.page_fields.language.value == language_id.UNKNOWN


def test_a4_syndication_groups_are_scoped_to_the_institution(tmp_path):
    insts = _built(tmp_path)
    g = {p.url: _spec(insts[I1], p).upstream.page_fields.syndication_group for p in SCRAPED[I1]}
    assert g[P_META.url].value == g[P_DUP.url].value != g[P_URL.url].value
    assert set(g[P_META.url].detail["members"]) == {url_hash(P_META.url), url_hash(P_DUP.url)}
    archive = _spec(insts[I2], P_ARCHIVE).upstream.page_fields.syndication_group
    assert archive.value != g[P_META.url].value  # same text, other institution: never one group
    assert archive.detail["institution_id"] == I2 and archive.detail["members"] == [url_hash(P_ARCHIVE.url)]
    assert _spec(insts[I2], P_SHORT).upstream.page_fields.syndication_group.detail["short_page"] is True


@pytest.mark.parametrize("scraped", [{**SCRAPED, I3: []}, {I1: SCRAPED[I1], I2: SCRAPED[I2]},
                                     {**SCRAPED, I3: None}])
def test_zero_page_institution_is_skipped_without_error(tmp_path, scraped):
    """Ruling 37 a: an institution with no stored page yields no PerPageInstitution and raises nothing
    (skipped before its uid or identity are read: here it has no institution.json at all); its outcome
    is decided afterwards from the run folder, as v2.5 does."""
    run_dir = _run_dir(tmp_path)
    (institution_dir(run_dir, I3) / "institution.json").unlink()
    insts = pin.build_perpage_inputs(run_dir, ROWS, scraped)
    assert [i.institution_id for i in insts] == [I1, I2]
    assert [i.institution_id for i in insts] == [I1, I2]  # re-iterable, same result
    with pytest.raises(MissingUpstreamError):  # the pages present still refuse as before
        pin.require_complete(insts)
    only_empty = pin.build_perpage_inputs(run_dir, [ROWS[2]], scraped)
    assert list(only_empty) == [] and pin.require_complete(only_empty) == 0


def test_unproduced_values_still_refuse(tmp_path):
    insts = _built(tmp_path)
    for inst in insts.values():
        for spec in inst.pages:
            up = spec.upstream
            assert (up.artifact_path, up.segments) == (None, None)  # A5 writes the artifact in the stage
            assert (up.followed, up.activity_values, up.source_values, up.codes) == (None, None, None, None)
    with pytest.raises(MissingUpstreamError, match="T-025 follow provenance") as exc:
        pin.require_complete(list(insts.values()))
    assert f"{I1}/{url_hash(P_META.url)}" in exc.value.missing
    followed = [replace(i, pages=[replace(s, upstream=replace(s.upstream, followed=False)) for s in i.pages])
                for i in insts.values()]
    with pytest.raises(MissingUpstreamError, match=r"row values .*\(activity_values, source_values, codes\)"):
        pin.require_complete(followed)


@pytest.mark.parametrize("absent", ["activity_values", "source_values", "codes"])
def test_require_complete_refuses_each_none_row_value(tmp_path, absent):
    """Review fix (LOW): activity_values is pre-checked with source_values and codes (None only;
    key coverage stays with produce_page, after coding)."""
    insts = _built(tmp_path)
    full = dict(followed=False, activity_values={}, source_values={}, codes={})
    complete = [replace(i, pages=[replace(s, upstream=replace(s.upstream, **full)) for s in i.pages])
                for i in insts.values()]
    assert pin.require_complete(complete) == 5  # empty mappings pass: coverage is not checked here
    one = complete[0]
    first = replace(one.pages[0], upstream=replace(one.pages[0].upstream, **{absent: None}))
    broken = [replace(one, pages=[first, *one.pages[1:]]), *complete[1:]]
    with pytest.raises(MissingUpstreamError, match="row values") as exc:
        pin.require_complete(broken)
    assert exc.value.missing == (f"{I1}/{first.page.page_id}",)


def test_unproduced_values_refusals_in_the_stage(tmp_path):
    insts = _built(tmp_path)
    # The per-page stage's own refusal is unchanged: failed_page still refuses a page with no follow value.
    with pytest.raises(MissingUpstreamError, match="T-025 follow provenance"):
        pp.failed_page(insts[I1].pages[0], "jev_request_failed")
    with pytest.raises(sf.UnruledError):
        sf.discovery_path()
    with pytest.raises(sf.UnruledError):
        sf.text_source()
    with pytest.raises(MissingUpstreamError, match="T-025 follow provenance"):
        pin.require_complete(pin.default_perpage_inputs(_run_dir(tmp_path / "again"), ROWS, SCRAPED, None, None))


@pytest.mark.parametrize("column", ["institution_name", "country", "branch_of_government", "level_of_government"])
def test_identity_drift_on_each_master_column_is_refused(tmp_path, column):
    run_dir = _run_dir(tmp_path)
    path = institution_dir(run_dir, I1) / "institution.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**rec, column: "Other"}), encoding="utf-8")
    # The builder is lazy: each refusal comes when the institution is reached (the check pass).
    with pytest.raises(ValueError, match=rf"differs from the master row on \['{column}'\]"):
        list(pin.build_perpage_inputs(run_dir, ROWS[:1], SCRAPED))


def test_country_fields_come_from_their_intended_sources(tmp_path, monkeypatch):
    """Ruling 38 a: ``PerPageInstitution.country`` is the stored identity block's country (the drift
    check pins it to the master row) and ``PageInput.country`` the master row's, through
    ``institution_record``. The two agree by construction, so the source of each is pinned by
    giving the identity block a country the master row does not have."""
    real = pin._identity
    monkeypatch.setattr(pin, "_identity", lambda *a: {**real(*a), "country": "Identity Country"})
    one = next(iter(pin.build_perpage_inputs(_run_dir(tmp_path), ROWS[:1], SCRAPED)))
    assert one.country == one.institution["country"] == "Identity Country"
    assert {s.page.country for s in one.pages} == {"Australia"} == {ROWS[0]["country"]}


def test_identity_drift_duplicate_url_and_missing_uid_are_refused(tmp_path):
    run_dir = _run_dir(tmp_path)
    path = institution_dir(run_dir, I1) / "institution.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({k: v for k, v in rec.items() if k != "institution_search_languages"}),
                    encoding="utf-8")
    with pytest.raises(MissingUpstreamError, match="institution_search_languages"):
        list(pin.build_perpage_inputs(run_dir, ROWS[:1], SCRAPED))
    with pytest.raises(ValueError, match="share a URL"):
        list(pin.build_perpage_inputs(_run_dir(tmp_path / "dup"), ROWS[:1], {I1: [P_META, P_META]}))
    run_dir = _run_dir(tmp_path / "uids", manifest={"run_id": RUN_ID, "institutions": [I1],
                                                    "institution_uids": {I2: uid_for(I2)}})
    with pytest.raises(MissingUpstreamError, match="institution_uids"):
        list(pin.build_perpage_inputs(run_dir, ROWS[:1], SCRAPED))


class RecordingScraped(Mapping):
    """A ``ScrapedPages`` stand-in that records each institution read (pages parsed on access)."""

    def __init__(self, pages):
        self.pages, self.reads = pages, []

    def __getitem__(self, inst_id):
        self.reads.append(inst_id)
        return list(self.pages[inst_id])

    def __iter__(self):
        return iter(self.pages)

    def __len__(self):
        return len(self.pages)


def test_builder_is_lazy_one_institution_at_a_time_and_re_iterable(tmp_path):
    """Review fix (memory): no page is read when the builder is called; iteration reads one
    institution's pages per step; a second pass reads them again (nothing is held)."""
    scraped = RecordingScraped(SCRAPED)
    built = pin.build_perpage_inputs(_run_dir(tmp_path), ROWS, scraped)
    assert not isinstance(built, list) and scraped.reads == []
    it = iter(built)
    assert next(it).institution_id == I1 and scraped.reads == [I1]
    assert next(it).institution_id == I2 and scraped.reads == [I1, I2]
    with pytest.raises(StopIteration):
        next(it)
    assert scraped.reads == [I1, I2, I3]
    assert [i.institution_id for i in built] == [I1, I2]  # re-iterable: a fresh pass
    assert scraped.reads == [I1, I2, I3] * 2
    # The completeness check is one pass that keeps no institution (returns the page count).
    complete = [replace(i, pages=[replace(s, upstream=replace(s.upstream, followed=False, activity_values={},
                                                              source_values={}, codes={})) for s in i.pages])
                for i in built]
    assert pin.require_complete(iter(complete)) == len(SCRAPED[I1]) + len(SCRAPED[I2])


# ---------------------------------------------------------------------------
# Dispatch with the default builder (fake calls; mirrors test_orchestrator_v27_dispatch)
# ---------------------------------------------------------------------------


def test_v27_dispatch_default_builder_refuses_before_any_call(tmp_path, monkeypatch):
    from tests.test_e2e_perpage_v27 import SETTINGS, FakeJev
    from tests.test_perpage_providers_v27 import FakeEntail, FakeExtractor, _world

    run_dir, _bound, _instrument, world, _ = _world(tmp_path)
    write_manifest(run_dir, {"run_id": RUN_ID, "institutions": [I1, I2],
                             "config": {"pipeline_version": PIPELINE_V27}})
    for row in ROWS[:2]:
        rec = institution_record(row)
        d = institution_dir(run_dir, rec["institution_id"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "institution.json").write_text(json.dumps({**rec, "institution_search_languages": "en"}),
                                            encoding="utf-8")
    jev, extract, entail = FakeJev(), FakeExtractor(world), FakeEntail()
    v27 = orch.V27Dispatch(settings=SETTINGS, jev_ask_fn=jev, extract_fn=extract, entail_fn=entail)
    assert v27.perpage_inputs is None
    with pytest.raises(MissingUpstreamError, match="ruling 36 a"):  # refused at entry while producers are missing
        orch.run_v27_dispatch(run_dir, ROWS[:2], SCRAPED, v27)
    # Once the producers exist the entry refusal lifts; the builder's own guard still refuses.
    monkeypatch.setattr(pin, "MISSING_PRODUCERS", ())
    scraped = RecordingScraped(SCRAPED)
    with pytest.raises(MissingUpstreamError, match="T-025 follow provenance") as exc:
        orch.run_v27_dispatch(run_dir, ROWS[:2], scraped, v27)
    # The refusal comes from the first (check) pass over the lazy inputs: each institution read once.
    assert scraped.reads == [I1, I2]
    assert exc.value.missing == tuple(f"{i}/{url_hash(p.url)}" for i in (I1, I2) for p in SCRAPED[i])
    assert jev.calls == [] and extract.jobs == [] and entail.calls == []
    assert not (institution_dir(run_dir, I1) / pp.WORK_DIR).exists()
