"""v2.7 per-page runtime (T-030): T-021/T-023 coding -> support re-gating rounds -> Stage 6 inputs.

Per institution this module drives every stored rendered page through

1. T-021 :func:`g3o.run.presweep.stage_page_code.run_page_code_stage` (the
   ``page_code_v27`` artifact; a page that cannot be coded, e.g. at least 75%
   of its verdict-request parts failed BY COUNT, writes no artifact and is
   recorded in the attrition ledger by that stage);
2. :func:`g3o.classify.question_rounds.complete_page_rounds` (support check,
   recombination, re-gating and the extra rounds of newly eligible questions);
3. T-023 :func:`g3o.run.presweep.stage_activity_code.run_stage` (the
   ``activity_code_v27`` artifact) and
   :func:`~g3o.classify.question_rounds.complete_activity_rounds`;
4. pair support and :func:`g3o.classify.jev_activity_code.finalize_pairs`;
5. the per-page producer (:func:`produce_page`): final per-page values and
   their T-024 support -> T-028 support/coder nodes -> the
   :class:`~g3o.run.presweep.stage_validate_v27.Stage6Institution` inputs
   (reviewed pages, observations, relation records, input quotes, within-page
   decisions, observation fragments, source rows, page artifacts).

Rules carried here, not decided here:

- **Durable resume.** Every jev response is journaled (fsynced) in
  ``<inst>/perpage_v27/journal.jsonl`` before it is used
  (:class:`~g3o.run.presweep.stage_validate_v27.RequestJournal`); the round
  helpers' checkpoints (result plus checked support) are written atomically
  to ``<inst>/perpage_v27/<url_hash>/{page,activity,pairs}.json``. The
  journal key binds the coder setup (setup pointer, configured models, coder
  versions). A re-run loads the checkpoint and asks only what is missing;
  failed requests are never replayed and are asked again (an unidentified,
  billed jev response is kept for accounting only; except a re-ask after a page
  halving, whose unidentified response is replayed as its final failure, PI
  ruling 75 a). A response with a request id
  that lacks an asked answer is a completed response here and is replayed on
  resume: its missing answer is a failed part vote, exactly as in an uninterrupted
  run (the Stage 6 Z1 b no-replay rule is not applied to this stage). Support results are serialized whole
  (:func:`support_to_dict`), so a resumed check is never re-run. PI ruling 98 b: a resumed page's pass-2
  page request, rebuilt from the stored T-023 artifact, with no recorded response in the journal holds
  the institution (:data:`PASS2_NOT_JOURNALED`) instead of being sent live. PI ruling 105 b: the same for
  a resumed page's pass-1 page request (:data:`PASS1_NOT_JOURNALED`) and 87 c activity-only request
  (:data:`ACTIVITY_ONLY_NOT_JOURNALED`); the residual ``source_type`` answers are saved before the first
  pass-1 request and loaded on a resume (:data:`SOURCE_TYPE_FILE`), never asked again, also after a C4
  archive (review M-1). PI ruling 110 b: answers whose deciding part failed with no answer are not saved;
  the institution is held before that request (:data:`RESIDUAL_PART_FAILED`) and the question is asked
  again on the next run (answered parts replayed from the journal). PI ruling 120 c: a deciding part whose
  response has a request id but no answer is replayed every run (this stage keeps such responses), so the hold
  names that part's jev ``request_key``; a ``pi_release.json`` naming it authorises one live re-ask (the
  journal's ``reask_spent`` marker first, the new response journaled and replayed afterwards). A part that
  failed otherwise (the request raised or came back with no request id) has no replayable journaled response (a
  billed response with no request id is kept as ``jev_unidentified`` for accounting only) and is asked again live on the next run without a release; its hold text does not offer the key (review L-a / L-b,
  :class:`ResidualPartFailed`). PI ruling 126 a (kept): once a jev key's one-time re-ask is spent, a further
  ask of the same request in the same process (its next journal slot, with no response recorded there) is
  refused by the journal like any spent key
  (:class:`~g3o.run.presweep.stage_validate_v27.ReaskSpentUnanswered`), not sent live.
  PI rulings 104 b / 113 b: a ``pi_release.json`` key naming one of these held requests
  (:data:`REASK_RELEASABLE`) authorises one live re-ask; only a release naming the key in ``keys`` does: a
  release naming ``all`` authorises no re-ask (it only resets the 41 a rejection counts; PI ruling 125 a,
  stated in every hold that offers a key). A release is checked against the last run's ``held.json``, which
  lists only the institution-wide hold when one page broke the institution, so a held request of another page
  is not releasable until that hold clears (review L-d, :func:`_apply_pi_release`). For a pass-1 or
  activity-only request the page's
  activity-level state (:data:`ACTIVITY_STATE_FILES` and the T-023 activity artifact) is archived first
  (:func:`archive_activity_state`), so the new response's spans are coded from scratch. PI ruling 121 b: for a
  pass-1 page request (not an activity-only one) ``page.json`` is archived too
  (:data:`PAGE_REQUEST_STATE_FILES`, :func:`archive_page_request_state`), before the page's rounds start
  (``PerPageProviders.prepare_pass1_reask``), so the page-level support is checked again on the new response's
  quotes and a row's snippet and provenance name one response. PI ruling 127 a (accepted, spend control): that
  re-ask's cost is the re-asked request plus the page-level support's X35 calls, and it may trigger further
  jev extra-round and extractor extra-round calls; every one is journaled. Review H-1 (PI ruling
  114 b): the archive is followed by a fresh ``pass1_requests.json`` naming the request about to be sent
  (:func:`record_pass1_reask`), and the journal refuses a live call of any key whose re-ask was used up with no
  response recorded since (:class:`~g3o.run.presweep.stage_validate_v27.ReaskSpentUnanswered`): the adapter
  turns it into the not-journaled hold of the request's kind, which only a new release file lifts.
- **Publication.** A page with any pending or stopped question (an extra
  round that failed, a gate awaiting it) holds its whole institution: the
  holds go to ``perpage_v27/held.json`` and the attrition ledger, nothing is
  passed to Stage 6, and pending values are never published or turned into
  negatives. A per-page producer error for one page (:data:`PRODUCER_FAILED`:
  a refusal, a page with neither a page-code artifact nor a recorded failure)
  holds that institution the same way and the stage goes on; stage stops
  (:data:`STAGE_STOPS`) still propagate. An absent upstream value
  (``MissingUpstreamError``) is a wiring gap, not institution data: it stops
  the stage loudly (RC-D-033 C2 a). When a
  held institution is later ready, :data:`HELD_RELEASED` is recorded.
- **Failed or unparsable extractor response (C3 a, QA4 M3).** A T-022 pass-1 or
  T-032 pass-2 response that failed or broke the answer contract
  (:class:`ExtractorResponseFailed`, raised by the provider adapters) holds that
  institution as pending (stage :data:`EXTRACT_RESPONSE_FAILED` in ``held.json``,
  the attrition ledger, ``PerPageMetrics.held``) and the stage goes on with the
  next institution; nothing of it is published. The response is never replayed as
  final: a failed one is journaled ``extract_failed`` and an unparsable one is
  rejected in the journal (``extract_rejected``), both kept for accounting only,
  so the next run asks the request again.
- **Rejection cap and PI release (ruling 34 b / 41 a).** The journal counts
  ``extract_rejected`` entries (never ``extract_failed``) per exact request key
  (the journal's SHA256 over setup, prompt and request), across every run and
  resume in this run folder. When a rejection brings a key to
  :data:`~g3o.run.presweep.stage_validate_v27.EXTRACT_REJECT_CAP` (3), the
  institution is held with stage :data:`EXTRACT_REJECTED_CAP` (``held.json``
  names page, pass, ``custom_id``, ``request_key`` and ``rejections``); on every
  later run the journal refuses a live call for that key
  (:class:`~g3o.run.presweep.stage_validate_v27.ExtractRejectCapReached`) and the
  institution is held the same way, with no extractor call. Only the PI releases
  it, with ``<inst>/pi_release.json`` in the institution folder (format:
  :func:`read_pi_release`): before any call, a valid file is recorded as a
  ``pi_released`` journal entry (journal lines are never rewritten or deleted),
  after which the rejections recorded before it no longer count for the released
  keys, and the file is moved to ``<inst>/archive/pi_release/<NNN>/`` so it is
  never re-applied (a file with the same bytes as a recorded release is only
  moved, ruling 47.2 a). A malformed release file is refused explicitly: the
  institution is held (:data:`PI_RELEASE_MALFORMED`) and the file stays in place;
  so is a file naming a key with no ``extract_rejected`` entry counted in the
  journal. A journal write of the release that fails holds the institution
  (:data:`PI_RELEASE_RECORD_FAILED`, ruling 28 a), the file staying in place.
- **Stale page state on a C4 hold (ruling 33 a).** A C4 a hold (a pass-1 activity
  with no ``activity_name``; :attr:`ExtractorResponseFailed.archive_page_state`)
  moves that page's saved state (``page.json``, ``activity.json``, ``pairs.json``,
  ``pass1_requests.json`` and the T-023 activity artifact; :data:`PAGE_STATE_FILES`) to
  ``<page dir>/archive/<NNN>/`` (archive, never delete; ``source_type.json`` stays, review M-1),
  so the next run codes the page again from the new pass-1 answer
  instead of resuming from state built on the rejected one. The archive is all or
  nothing across runs: a pending marker (:data:`PAGE_ARCHIVE_PENDING`) is written
  first and moved last, and an ``OSError`` that survives the write retries (ruling
  28 a) holds the institution (``held.json`` lists ``archived``, ``archive_left``
  and ``archive_error``; attrition detail ``<page>:<stage>:``:data:`ARCHIVE_FAILED`)
  instead of stopping the stage. The next run finishes that same archive before it
  loads any of the page's state, and holds again (:data:`ARCHIVE_FAILED`) if it
  still cannot.
- **Provider seams.** The support check (T-022 pass-1 quotes, T-032 pass-2
  quotes, X35 entailment and the T-024 check) and the T-022 activity spans are
  injected (:class:`PerPageProviders`); this module does not call them itself.
  :func:`g3o.run.presweep.perpage_providers_v27.build_perpage_providers` builds
  them over injected extractor and X35 calls, bound to the instrument's pinned
  models (refused otherwise); those calls are journaled per institution.
- **Values with no producer here** are explicit inputs (:class:`PageUpstream`,
  :class:`InstitutionUpstream`) and refuse when absent
  (:class:`~g3o.persist.stage6_adapters.MissingUpstreamError`): the
  non-classifier row values (T-015 source fields, T-022 quote-step values,
  T-024 derived values) and the quote-step codes' support, an injected stored
  page artifact layout (absent: written by :mod:`g3o.persist.page_artifact`,
  PI ruling A5.1 a), T-025 follow provenance of an input page (the follow
  leg, ``run_perpage_v27(follow=...)``, sets it on the pages it fetches:
  :mod:`g3o.run.presweep.follow_v27`), independence groups (produced
  in Stage 6 when not injected, A7) and the merged-activity values RC-D-030 X1 a
  leaves without a rule computable from the merged row
  (:data:`~g3o.run.presweep.stage_validate_v27.MERGE_INPUT_ITEMS`).
  When no row values are injected and ``PageUpstream.page_fields`` is set, the
  T-015 source-row assembler (:mod:`g3o.run.presweep.source_row_v27`, PI ruling
  35 a) builds them after coding; while it still refuses an unproduced row item, or
  refuses one for a missing wiring input, that is a ``MissingUpstreamError`` naming
  the items (a stage stop, RC-D-033 C2 a). PI ruling 97 b: an item refused on the
  page's own data alone (``source_row_v27.CONDITIONAL_ITEMS``) holds that institution
  (:data:`ROW_VALUE_REFUSED` in ``held.json``, naming the items and each refusal; the
  attrition detail names the items) and the stage goes on.
- **Reviewed page with no activity (RC-D-030 Y2 a).** It gets one page-level
  source row: ``activity_id`` ``_NA_``, empty ``observation_ids``, its
  page-level values and nodes (support nodes with no observation), the
  upstream source values and codes keyed :data:`NO_ACTIVITY`, and ``_NA_``
  set by rule (``vocabularies/missing/na_label``) on the activity-question
  items the sources table holds.
- **Supported observation (setting F; replaces RC-D-030 Y1 b).** ``ActivityObservation.supported`` is
  derived here (:func:`observation_supported`): the observation's final
  ``core.activity_type`` or its final ``core.action_type`` is supported (support
  status ``supported`` at the deciding part).
- **Within-page decisions (RC-D-030 Y5 a).** A finalized T-023 pair whose
  combined value is one relation decides that relation, with the lowest
  chosen probability among the parts that chose it, supported only if all of
  those parts are (:func:`within_page_decision`); more than one value, or none
  a part chose, gives no decision and Stage 6 holds the pair.
- **Combined values.** A final classifier value must be carried by a support
  node of one of its parts (the original code or its downgrade replacement);
  gate and rule values get ``set_by_rule`` nodes with mechanical records. A
  combined value no part node carries (e.g. ``unknown`` from failed votes) is
  refused as a per-institution hold (RC-D-030 Y3 b): ``perpage_v27/held.json``
  names the page and values (stage ``combined_value_uncarried``), the
  attrition ledger records it, and nothing of the institution reaches Stage 6.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date as iso_date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from g3o.classify import jev_activity_code as jac
from g3o.classify import jev_page_code as jpc
from g3o.classify.jev_activity_code import (
    ActivityCoderConfig,
    ActivityPageInput,
    PageActivityResult,
    PairResult,
    finalize_pairs,
    nano_values,
    value_label,
)
from g3o.classify.jev_page_code import PageCoderConfig, PageCodeResult, PageInput, contact_text
from g3o.classify.permanent_pilot import PERMANENT_PILOT_RULE
from g3o.classify.question_rounds import (
    HALVING_PAGE_FAILED,
    REASK_SEAM,
    ActivityRoundResult,
    PageRoundResult,
    complete_activity_rounds,
    complete_page_rounds,
)
from g3o.common import attrition
from g3o.common import source_fields as sf
from g3o.common.artifact_io import artifact_exists, gz_path, plain_path, read_artifact
from g3o.common.cost_monitor import BudgetExceededError, UnpricedModelError
from g3o.common.instrument import canonical_json, sha256_text
from g3o.common.jev_client import JevAccountError
from g3o.common.jev_record import CoderRecord
from g3o.common.part_combine import NOT_COVERED
from g3o.common.paths import institution_dir
from g3o.common.run_state import clear_done, mark_done
from g3o.common.source_fields import MissingUpstreamError as SourceFieldsMissingUpstreamError
from g3o.common.storage import METADATA_ITEMS, table_fields
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import (
    NO_QUOTE,
    CodeEvidence,
    Entailment,
    PageSources,
    QuoteMatch,
    SupportGateError,
    SupportResult,
    _locate,
    _locate_by_words,
    check_code,
)
from g3o.extract.batch import url_hash
from g3o.persist.page_artifact import write_page_artifact
from g3o.persist.stage6_adapters import (
    MissingUpstreamError,
    PageArtifact,
    SupportContext,
    coder_nodes,
    replace_with_retry,
    support_nodes,
)
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_activity_code, stage_page_code
from g3o.run.presweep.official_site_v27 import load_run_official_sites
from g3o.run.presweep.perpage_batch_v27 import BATCH_PENDING, BatchDeferred
from g3o.run.presweep.stage_validate_v27 import DONE_MARKER as STAGE6_DONE_MARKER
from g3o.run.presweep.stage_validate_v27 import (
    EXTRACT_REJECT_CAP,
    ExtractRejectCapReached,
    ObservationInput,
    RequestJournal,
    Stage6Institution,
)
from g3o.validate import merged_activity_v27 as ma
from g3o.validate import uncertainty_flags_v27 as uf
from g3o.validate.consolidate_v27 import (
    MISSING,
    RELATIONS,
    ActivityObservation,
    ConsolidationError,
    RelationDecision,
    ReviewedPage,
    outcome_values,
)
from g3o.validate.stage6_v27 import InputQuote, ObservationRecord, Stage6QuoteNotApproved

STAGE = "perpage_v27"
#: ruling 48.3 a: ``_state/.done/<DONE_MARKER>.json``, written once the whole pass finished (no stage
#: stop); the run report reads it for an unheld institution as v2.5 reads its extract marker
DONE_MARKER = "perpage_v27"
WORK_DIR = "perpage_v27"
JOURNAL = "journal.jsonl"
HELD_FILE = "held.json"
HELD_REASON = "perpage_held"
HELD_RELEASED = "perpage_held_released"  # appended when a held institution's per-page hold clears
ACTIVITY_DIR = "activity_code_v27"
CHECKPOINT_FORMAT = "g3o-perpage-checkpoint-v1"
PIPELINE = "web_extract"
FAILED_PAGE_VERDICT = "not_assessable"  # an unreviewed page keeps a signed verdict code; never counted
FAILED_PAGE_SUPPORT = "not_asked"  # R-045: no support check ran on a page that was not coded
#: The items of a per-page activity fragment. PI ruling 94 a: the Stage-6-only items
#: (:data:`~g3o.run.presweep.source_row_v27.STAGE6_ACTIVITY_ITEMS`) are not among them.
ACTIVITY_ITEMS = (frozenset(table_fields("activities")) - {"core.n_sources", "core.confidence"} - set(METADATA_ITEMS)
                  - set(srow.STAGE6_ACTIVITY_ITEMS))
SOURCE_ITEMS = frozenset(table_fields("sources")) - set(METADATA_ITEMS)
#: The items a per-page source row must carry. PI ruling 140 (gate 3): Stage 6 alone produces
#: :data:`~g3o.run.presweep.source_row_v27.STAGE6_SOURCE_ITEMS` (``core.confidence``) and fills it there.
SOURCE_ROW_ITEMS = SOURCE_ITEMS - set(srow.STAGE6_SOURCE_ITEMS)
PRODUCED_CODERS = frozenset({"classifier"})
T015_CLASSIFIER = "core.source_type"  # a classifier item T-015 owns: an upstream value and code

#: Setting F (replaces RC-D-030 Y1 b): an observation is supported when either of these final values is supported.
SUPPORTED_ITEMS = ("core.activity_type", "core.action_type")
#: RC-D-030 Y2 a: upstream key (source values, codes) of a no-activity page's page-level source row.
NO_ACTIVITY = "_NA_"
#: Signed slot of the rule "store `_NA_` on items of a row that has no activity" (R-045, all-01 b).
NA_RULE = "vocabularies/missing/na_label"
VALUES_PRODUCER = "T-015 / T-022 / T-024 row values with no producer on this branch"
ARTIFACT_PRODUCER = "T-014/T-020 stored page artifact and its segment layout"
FOLLOW_PRODUCER = "T-025 follow provenance (followed / attempted page)"
UNCARRIED_STAGE = "combined_value_uncarried"  # RC-D-030 Y3 b: per-institution hold
#: a per-page producer refused or failed for one page (held.json names the error): per-institution hold
PRODUCER_FAILED = "page_producer_failed"
#: every attempted page of the institution failed (T-021 wrote no artifact, or the page failed after
#: halving) and no unread follow attempt gives it a row, so it has no source row for Stage 6 (whose
#: response requires one). Held as pending, never concluded (ruling 45 a): held.json names each failed
#: page and its reason; the next pass codes the pages again (calibration candidate C189). At least one
#: page must be retryable (a T-021 failure): when every page failed after halving, see NO_PAGE_CODED_FAILED.
NO_PAGE_CODED = "no_page_coded"
#: attrition reason (no hold): every attempted page of the institution failed after halving in an extra round
#: (PI ruling 69 b), which is never asked again, and no unread follow attempt gives it a row. A terminal failure,
#: not a pending hold (a :data:`NO_PAGE_CODED` hold would never clear): the institution is not passed to Stage 6,
#: any earlier hold is released, and the run report counts this reason as a failure (PROCESSING_FAILED, never
#: NO_EVIDENCE_FOUND: rulings 45 a, E2 a). The detail names each page and its reason (calibration C189).
NO_PAGE_CODED_FAILED = "no_page_coded_failed"
#: C3 a (QA4 M3): a pass-1/pass-2 extractor response failed or broke the answer contract (held.json
#: names the pass, the request and the error): per-institution hold, asked again on the next run
EXTRACT_RESPONSE_FAILED = "extract_response_failed"
#: ruling 33 a: a page's saved state is moved under ``<page dir>/<PAGE_ARCHIVE_DIR>/<NNN>/`` on a C4 hold
#: (the project's ``archive`` folder name, as :data:`g3o.run.archive.ARCHIVE_DIRNAME`)
PAGE_ARCHIVE_DIR = "archive"
#: the per-page checkpoint files under the page dir (the T-023 activity artifact lives in ACTIVITY_DIR)
#: the pair-support checkpoint, written after the page's pass-2 page request was built (``page_pass2``,
#: then ``pair_support``); its presence on a later run means that request was made by an earlier process
#: (PI ruling 98 b reads it)
PAIRS_FILE = "pairs.json"
#: PI ruling 105 b (with 95 a): the page's residual source_type answers (the stored residual result), written
#: before the page's first pass-1 request and loaded on a resume instead of asking again
SOURCE_TYPE_FILE = "source_type.json"
#: PI ruling 105 b: the pass-1 requests built for the page (the T-022 page request, the 87 c activity-only
#: request; their ``custom_id``, or None), written once ``activity_input`` returned; a later process reads it
#: to know a rebuild is a resume
PASS1_FILE = "pass1_requests.json"
#: the page-dir files the C4 archive (ruling 33 a, :func:`_archive_page_state`) moves. Review M-1:
#: :data:`SOURCE_TYPE_FILE` is not among them. The residual answers depend on no pass-1 answer (asked on the
#: T-021 parts, which the archive keeps), so ruling 105 b's "saved and never asked again" survives a C4 archive:
#: archiving them would make the next run ask the residual question again, a part that failed live (paid, with
#: no journal guard), and a changed first pass-1 request key would drop the 34 b rejection count. The C4 archive
#: is the only path that resets a page's saved state; a future path that resets ALL of it must also archive
#: :data:`SOURCE_TYPE_FILE`.
PAGE_STATE_FILES = ("page.json", "activity.json", PAIRS_FILE, PASS1_FILE)
#: PI ruling 113 b: the page's activity-level state, archived (with the T-023 activity artifact) before the one
#: live re-ask a PI release authorises for a pass-1 / activity-only hold (:func:`archive_activity_state`), so
#: the new response's spans are never mixed with state built on the old ones. For an activity-only re-ask
#: ``page.json`` stays (the ruling names activity-level state only; a pass-1 page request re-ask also moves it, PI
#: ruling 121 b, :data:`PAGE_REQUEST_STATE_FILES`), and so does :data:`SOURCE_TYPE_FILE` (review M-1).
ACTIVITY_STATE_FILES = ("activity.json", PAIRS_FILE, PASS1_FILE)
#: PI ruling 121 b: before the one live re-ask a PI release authorises for a pass-1 PAGE request hold
#: (:data:`PASS1_NOT_JOURNALED`, not an activity-only one), ``page.json`` is archived with the activity-level state
#: (:func:`archive_page_request_state`): its page-level support was checked on the old response's quotes. Still not
#: :data:`SOURCE_TYPE_FILE` (review M-1).
PAGE_REQUEST_STATE_FILES = ("page.json", *ACTIVITY_STATE_FILES)
#: written in the page dir before a C4 archive moves anything and moved into the archive folder last;
#: while it is in the page dir the archive is incomplete and the page's saved state is never loaded
PAGE_ARCHIVE_PENDING = "archive_pending.json"
#: ruling 33 a with ruling 28 a: a page-state archive that a filesystem error left incomplete holds the
#: institution (held.json lists what was moved, what was left and the error); the next run finishes it
ARCHIVE_FAILED = "page_state_archive_failed"
#: ruling 34 b / 41 a: an extractor request rejected EXTRACT_REJECT_CAP times is a permanent hold
#: (held.json names the page, pass, custom_id, request key and rejection count); only a PI release
#: (:data:`PI_RELEASE_FILE`) lets the stage call it again
EXTRACT_REJECTED_CAP = "extract_rejected_cap"
#: ruling 34 b / 41 a: the PI release file, in the institution folder (``<inst>/pi_release.json``)
PI_RELEASE_FILE = "pi_release.json"
#: consumed release files are moved (never deleted) to ``<inst>/archive/pi_release/<NNN>/pi_release.json``
PI_RELEASE_ARCHIVE = "pi_release"
#: a release file that cannot be read or does not follow the format holds the institution (never ignored)
PI_RELEASE_MALFORMED = "pi_release_malformed"
#: ruling 28 a: a consumed release whose move to archive failed after the write retries holds the
#: institution; the release is already recorded in the journal, so the next run only finishes the move
PI_RELEASE_ARCHIVE_FAILED = "pi_release_archive_failed"
#: ruling 28 a: an OSError appending the release to the journal holds the institution (file stays in place)
PI_RELEASE_RECORD_FAILED = "pi_release_record_failed"
_PI_RELEASE_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_PI_RELEASE_FIELDS = frozenset({"released_by", "date", "keys", "all", "note"})


class FollowWiringError(ValueError):
    """A T-025 follow-leg error that is a wiring gap, not institution data (review L5): the fetch seam
    broke its contract (unknown outcome; a page without ``fetched`` or ``fetched`` without a page), the
    leg was handed no page, a page of another institution or a page already followed, a round mixed
    hops, a followed page id was already coded, or the stored follow state is unusable (review M3: not
    UTF-8 JSON, another format, release, back-fill flag or rules, a missing key or a malformed field).
    It stops the stage (:data:`STAGE_STOPS`); any other ``ValueError`` of the follow leg (e.g. a fetched
    page whose URL is not the URL tried) holds its institution (:data:`FOLLOW_FAILED`), except a malformed
    page checkpoint of a followed page (:class:`MalformedCheckpoint`, PI ruling 118 b), which stops it too."""


class MalformedCheckpoint(ValueError):
    """A per-page checkpoint in the page dir that cannot be used (PI ruling 118 b): ``page.json`` /
    ``activity.json`` (:meth:`Checkpoint.load`), ``pairs.json``, :data:`SOURCE_TYPE_FILE`
    (:func:`load_source_typing`), :data:`PASS1_FILE` (:func:`read_pass1_requests`,
    :func:`_record_pass1_requests`) or the archive marker :data:`PAGE_ARCHIVE_PENDING`: bytes that are not
    UTF-8 JSON, another format or kind, or content that does not decode (or was asked on other parts).

    It stops the stage (:data:`STAGE_STOPS`) on a searched and on a followed page alike: the follow leg's
    per-institution ``ValueError`` handler (:data:`FOLLOW_FAILED`) never turns it into a hold. Its message
    keeps the convention ``unsupported per-page checkpoint: <path>`` for another format or kind."""


class MalformedCheckpointJSON(MalformedCheckpoint, json.JSONDecodeError):
    """A per-page checkpoint whose bytes are not JSON (PI ruling 118 b): still a ``json.JSONDecodeError``, as
    the page checkpoints' convention has it, and a :class:`MalformedCheckpoint` (a stage stop)."""


#: Review L5: an error of the T-025 follow leg that is institution data, not wiring: per-institution hold.
FOLLOW_FAILED = "follow_failed"
#: Errors that stop the whole stage; every other producer error holds its institution only.
#: Both ``MissingUpstreamError`` classes subclass ``ValueError``; they are listed here so the
#: per-institution ``ValueError`` handlers never swallow a wiring gap (RC-D-033 C2 a). So does
#: :class:`MalformedCheckpoint` (PI ruling 118 b: a malformed page checkpoint, searched or followed page).
STAGE_STOPS = (JevAccountError, stage_page_code.StageStopped, SupportGateError, Stage6QuoteNotApproved,
               BudgetExceededError, UnpricedModelError, MissingUpstreamError, SourceFieldsMissingUpstreamError,
               FollowWiringError, MalformedCheckpoint)


class ExtractorResponseFailed(Exception):
    """A T-022 pass-1 / T-032 pass-2 extractor response failed or broke the answer contract (C3 a).

    Raised by the provider adapters for one bad response only: an
    ``ExtractorResult`` with ``success`` false or no text, or an answer the parser
    refuses (:class:`~g3o.extract.parser_v27.ExtractContractError`). The per-page
    stage holds that institution as pending and goes on (QA4 M3: a deterministic
    contract-violating response no longer stops the stage on every resume).
    ``request`` is the journaled extractor request (``custom_id``, ``params``),
    or None when the caller has none; it is not a stage stop.

    ``archive_page_state`` (ruling 33 a) is set for a C4 a hold: the page's saved
    state was built on the rejected pass-1 answer, so the stage moves it to archive.
    """

    def __init__(self, pass_name: str, request: Mapping[str, Any] | None, detail: str, *,
                 archive_page_state: bool = False) -> None:
        super().__init__(f"{pass_name} extractor response failed: {detail}")
        self.pass_name, self.request, self.detail = pass_name, request, detail
        self.archive_page_state = archive_page_state


#: PI ruling 98 b (2026-11-14): on a resume, a rebuilt pass-2 page request with no recorded response in the
#: institution's request journal holds the institution (held.json names the page, ``custom_id`` and request key)
PASS2_NOT_JOURNALED = "pass2_request_not_journaled"
#: review H-1: the hint a not-journaled hold carries when the journal itself refused the call because the key's
#: PI-released re-ask was used up (PI ruling 114 b) with no response recorded since
_SPENT_NOTE = (" (review H-1: its PI-released re-ask was used up by a reask_spent journal entry and no response "
               "was recorded after it, so a new release file, with other bytes, is needed: PI ruling 114 b)")
#: review L-4: a re-ask is authorised only by a release that names the key; an ``all`` release resets the 41 a
#: rejection counts and authorises no re-ask
_NAME_KEY_NOTE = ("; the key must be named in the release's \"keys\" to authorise a re-ask: an \"all\" release "
                  "authorises none")


class Pass2RequestNotJournaled(Exception):  # noqa: N818 - names the hold, as ExtractRejectCapReached does
    """A resumed page's pass-2 page request, rebuilt from the stored T-023 artifact, has no recorded response
    in the institution's request journal (PI ruling 98 b): no live paid call is made; the institution is held.

    Raised by :meth:`g3o.run.presweep.perpage_providers_v27._Adapter._rebuild_page_request2` before any call;
    not a stage stop. Review H-1: also raised (``spent`` True) when the journal refuses a live call of a request
    whose PI-released re-ask was used up with no response recorded since
    (:class:`~g3o.run.presweep.stage_validate_v27.ReaskSpentUnanswered`, PI ruling 114 b)."""

    def __init__(self, page_id: str, custom_id: str, key: str, *, spent: bool = False) -> None:
        super().__init__(f"page {page_id}: the rebuilt pass-2 page request {custom_id!r} (journal key {key}) has "
                         "no recorded response in the request journal; no live call made on a resume (PI ruling "
                         f"98 b){_SPENT_NOTE if spent else ''}; naming this key in {PI_RELEASE_FILE} authorises one "
                         f"live re-ask (PI ruling 104 b){_NAME_KEY_NOTE}")
        self.page_id, self.custom_id, self.key, self.spent = page_id, custom_id, key, spent


#: PI ruling 105 b (2026-11-14, extending 98 b): on a resume, the page's rebuilt T-022 pass-1 page request with
#: no recorded response in the institution's request journal holds the institution (no live call)
PASS1_NOT_JOURNALED = "pass1_request_not_journaled"
#: PI ruling 105 b: the same for the page's rebuilt 87 c activity-only pass-1 request
ACTIVITY_ONLY_NOT_JOURNALED = "activity_only_request_not_journaled"


class Pass1RequestNotJournaled(Exception):  # noqa: N818 - names the hold, as Pass2RequestNotJournaled does
    """A resumed page's pass-1 request (the T-022 page request rebuilt from the stored T-021 artifact, or the
    87 c activity-only request) has no recorded response in the institution's request journal (PI ruling
    105 b, the 98 b check): no live paid call is made; the institution is held with ``stage``
    (:data:`PASS1_NOT_JOURNALED` / :data:`ACTIVITY_ONLY_NOT_JOURNALED`).

    Raised by the provider adapter (:mod:`g3o.run.presweep.perpage_providers_v27`) before any call; not a
    stage stop. Review H-1: also raised (``spent`` True) when the journal refuses a live call of a request
    whose PI-released re-ask was used up with no response recorded since
    (:class:`~g3o.run.presweep.stage_validate_v27.ReaskSpentUnanswered`, PI ruling 114 b)."""

    def __init__(self, page_id: str, custom_id: str, key: str, stage: str, *, spent: bool = False) -> None:
        super().__init__(f"page {page_id}: the rebuilt pass-1 request {custom_id!r} (journal key {key}) has no "
                         "recorded response in the request journal; no live call made on a resume (PI ruling "
                         f"105 b){_SPENT_NOTE if spent else ''}; naming this key in {PI_RELEASE_FILE} authorises "
                         "one live re-ask, after the page's activity-level state is archived (PI rulings 104 b / "
                         f"113 b){_NAME_KEY_NOTE}")
        self.page_id, self.custom_id, self.key, self.stage, self.spent = page_id, custom_id, key, stage, spent


class PageArchiveIncomplete(Exception):
    """An ``OSError`` that survived the write retries stopped a page-state archive (ruling 33 a / 28 a).

    ``archived`` are the paths already in the archive folder, ``left`` the ones
    still at their live paths (both relative to the institution dir). The
    pending marker (:data:`PAGE_ARCHIVE_PENDING`) stays in the page dir when it
    was written, so no later run loads the page's state before the archive is
    finished.
    """

    def __init__(self, archived: list[str], left: list[str], error: OSError,
                 files: Sequence[str] = PAGE_STATE_FILES) -> None:
        super().__init__(f"page-state archive incomplete: {type(error).__name__}: {error}")
        self.archived, self.left = archived, left
        self.error = f"{type(error).__name__}: {error}"
        #: the page-dir files this archive moves (:data:`PAGE_STATE_FILES`, or :data:`ACTIVITY_STATE_FILES`
        #: for a PI ruling 113 b archive, :data:`PAGE_REQUEST_STATE_FILES` for 121 b); the next run finishes the
        #: same archive
        self.files = tuple(files)


#: PI ruling 97 b (2026-11-14): a row value the T-015 assembler refused on the page's own data
#: (``source_row_v27.CONDITIONAL_ITEMS``, not a wiring gap): per-institution hold; held.json names the page,
#: the items and each refusal
ROW_VALUE_REFUSED = "row_value_refused"
#: Review M2: the refusal (under :data:`ROW_VALUE_REFUSED`, item ``core.source_type``) of a page whose residual
#: source_type question has a T-021 part over the request limit: that part is not halved (its halves are not
#: parts of the page's first pass-1 request, PI ruling 95 a), so the page's own data holds the institution
RESIDUAL_OVER_LIMIT = "source_type_residual_part_over_limit"
#: PI ruling 110 b (2026-11-14): the residual source_type question's deciding part failed with no answer
#: (:func:`~g3o.run.presweep.source_row_v27.residual_deciding_part_failed`): per-institution hold before T-022
#: (held.json names the page, the part and its cause); the answers are not saved, and the next run asks the
#: question again (answered parts replayed from the journal, the failed part asked live). Never ``unknown``.
RESIDUAL_PART_FAILED = "source_type_residual_part_failed"


class ResidualPartFailed(Exception):  # noqa: N818 - names the hold, as Pass2RequestNotJournaled does
    """PI ruling 110 b: the deciding part of a page's residual ``source_type`` question failed with no answer.

    Raised by :func:`_residual_source_type` before the answers are saved and before the page's first pass-1
    request is built, so that request (and its 105 b journal check) is only ever built on answers that are
    final; the page is held as pending (:data:`RESIDUAL_PART_FAILED`). Not a stage stop.

    The message is chosen by case, so each is true for its cause (review L-a / L-b):

    * ``spent`` (whatever the cause): the key's PI-released re-ask was used up with no answer (PI ruling 114 b),
      so the journal refuses a live call of it on every later run; a new release naming the key authorises one
      more (PI ruling 122 b).
    * :data:`~g3o.classify.jev_page_code.ANSWER_MISSING` (a response with a request id but no answer): the
      response is journaled and replayed on every run, so without a release the hold recurs; a release naming
      ``request_key`` authorises one live re-ask (PI ruling 120 c). With no key (the request could not be named)
      no release can name it.
    * :data:`~g3o.classify.jev_page_code.REQUEST_FAILED` / :data:`~g3o.classify.jev_page_code.MISSING_REQUEST_ID`
      (the request raised, or came back with no request id): no replayable response is journaled (a billed
      response with no request id is kept as ``jev_unidentified`` for accounting only), so the next run asks the
      part again live with no release (PI ruling 110 b). Any other cause: asked again on the next run
      (110 b), and not offered for release either.

    In the last two cases the hold still carries ``request_key`` (so :func:`_apply_pi_release` accepts a release
    naming it, :data:`REASK_RELEASABLE`; what is accepted is unchanged), but the message does not offer the key
    as releasable: no release is needed, and one naming the key would make that next live call the one-time
    re-ask, so a second failure would then need a new release (PI ruling 114 b).

    Every message that names a key as releasable says that only a release naming it in ``keys`` authorises the
    re-ask: an ``all`` release authorises none (PI ruling 125 a, :data:`_NAME_KEY_NOTE`)."""

    def __init__(self, page_id: str, part_id: str, cause: str | None, request_key: str | None = None, *,
                 spent: bool = False) -> None:
        if spent:  # review L-1: a spent re-ask is not asked again on the next run: the journal refuses it
            tail = (f"held, not asked again live without a new release (PI ruling 114 b){_SPENT_NOTE}; naming "
                    f"request key {request_key} in {PI_RELEASE_FILE} authorises one more live re-ask (PI rulings "
                    f"120 c / 122 b){_NAME_KEY_NOTE}")
        elif cause == jpc.ANSWER_MISSING and request_key is not None:
            tail = ("held: the response has a request id but no answer, so it is replayed from the request journal "
                    f"on every run and the hold recurs; naming its request key {request_key} in {PI_RELEASE_FILE} "
                    f"authorises one live re-ask (PI ruling 120 c){_NAME_KEY_NOTE}")
        elif cause == jpc.ANSWER_MISSING:
            tail = ("held: the response has a request id but no answer, so it is replayed from the request journal "
                    "on every run and the hold recurs; its request key could not be named, so no "
                    f"{PI_RELEASE_FILE} can release it (PI ruling 120 c)")
        elif cause in (jpc.REQUEST_FAILED, jpc.MISSING_REQUEST_ID):  # review L-a: nothing replayable to re-ask
            tail = ("held; the request raised or came back with no request id, so no replayable response is "
                    "journaled and the next run asks this part again live (PI ruling 110 b); no "
                    f"{PI_RELEASE_FILE} is needed for this cause")
        else:  # review L-a: not offered for release
            tail = (f"held, asked again on the next run (PI ruling 110 b); no {PI_RELEASE_FILE} re-ask is offered "
                    f"for this cause (only a response with a request id but no answer, {jpc.ANSWER_MISSING}, is "
                    "released that way: PI ruling 120 c)")
        super().__init__(f"page {page_id}: the residual source_type question's deciding part {part_id!r} failed "
                         f"with no answer ({cause}); {tail}")
        self.page_id, self.part_id, self.cause = page_id, part_id, cause
        #: PI ruling 120 c: the journal key of the deciding part's jev request (None when it cannot be named)
        self.request_key, self.spent = request_key, spent

    def hold(self) -> dict[str, Any]:
        return {"page_id": self.page_id, "stage": RESIDUAL_PART_FAILED, "items": [sf.SOURCE_TYPE],
                "part_id": self.part_id, "cause": self.cause, "request_key": self.request_key, "error": str(self)}


class RowValueRefused(ConsolidationError):
    """Row values refused on the page's own data (PI ruling 97 b): the institution is held, the stage goes on.

    ``refused`` maps each item to its refusal. Not a ``MissingUpstreamError`` (that is a wiring gap and
    stops the stage); nothing of the institution is published. A rerun holds it again while the page's
    data still refuses the item."""

    def __init__(self, page_id: str, refused: Mapping[str, str]) -> None:
        super().__init__(f"row values refused on page {page_id}'s own data: "
                         + "; ".join(f"{item}: {why}" for item, why in sorted(refused.items())))
        self.page_id, self.refused = page_id, dict(sorted(refused.items()))


class UncarriedCombinedValue(ConsolidationError):
    """A final value no part support node carries (RC-D-030 Y3 b): the institution is held."""

    def __init__(self, page_id: str, values: Sequence[str]) -> None:
        super().__init__(f"no part support node carries {list(values)} on page {page_id}")
        self.page_id, self.values = page_id, list(values)


# ---------------------------------------------------------------------------
# SupportResult (de)serialization
# ---------------------------------------------------------------------------


def support_to_dict(sr: SupportResult) -> dict[str, Any]:
    """Whole T-024 result, JSON-safe; :func:`support_from_dict` restores an equal object."""
    out = asdict(sr)
    out["flags"] = list(sr.flags)
    return out


def support_from_dict(doc: Mapping[str, Any]) -> SupportResult:
    data = dict(doc)
    if data.get("match") is not None:
        data["match"] = QuoteMatch(**data["match"])
    if data.get("entailment") is not None:
        data["entailment"] = Entailment(**data["entailment"])
    data["flags"] = tuple(data.get("flags") or ())
    return SupportResult(**data)


# ---------------------------------------------------------------------------
# Durable checkpoints
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(text.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    replace_with_retry(tmp, path)


def _read_checkpoint(path: Path, kind: str) -> dict[str, Any]:
    """The per-page checkpoint document at ``path`` of ``kind`` (PI ruling 118 b). Bytes that are not JSON raise
    :class:`MalformedCheckpointJSON` (a ``json.JSONDecodeError``), bytes that are not UTF-8, a document that is
    not an object or of another format or kind :class:`MalformedCheckpoint`; an ``OSError`` propagates."""
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedCheckpointJSON(f"malformed per-page checkpoint {path}: {exc.msg}", exc.doc, exc.pos) from exc
    except UnicodeDecodeError as exc:
        raise MalformedCheckpoint(f"malformed per-page checkpoint {path}: not UTF-8 ({exc})") from exc
    if not isinstance(doc, dict) or doc.get("format") != CHECKPOINT_FORMAT or doc.get("kind") != kind:
        raise MalformedCheckpoint(f"unsupported per-page checkpoint: {path}")
    return doc


def _decode_checkpoint(path: Path, decode: Callable[[], Any]) -> Any:
    """``decode()`` of a checkpoint read from ``path``; content that does not decode is a
    :class:`MalformedCheckpoint` (PI ruling 118 b)."""
    try:
        return decode()
    except MalformedCheckpoint:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise MalformedCheckpoint(f"malformed per-page checkpoint {path}: {type(exc).__name__}: {exc}") from exc


class Checkpoint:
    """One round helper's durable state: its result and the support checked so far."""

    def __init__(self, path: Path, kind: str) -> None:
        self.path, self.kind = path, kind
        self.writes = 0

    def save(self, result: Any, support: Sequence[SupportResult]) -> None:
        doc = {"format": CHECKPOINT_FORMAT, "kind": self.kind, "result": result.to_dict(),
               "support": [support_to_dict(s) for s in support]}
        _atomic_write(self.path, canonical_json(doc))
        self.writes += 1

    def load(self) -> tuple[Any, tuple[SupportResult, ...]] | None:
        """The saved result and support, or None; a malformed file raises :class:`MalformedCheckpoint`."""
        if not self.path.exists():
            return None
        doc = _read_checkpoint(self.path, self.kind)
        cls = PageCodeResult if self.kind == "page" else PageActivityResult
        return _decode_checkpoint(self.path, lambda: (cls.from_dict(doc["result"]),
                                                      tuple(support_from_dict(s) for s in doc["support"])))


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageUpstream:
    """Explicit per-page inputs whose producers are absent here (refuse when missing).

    ``artifact_path`` (run-relative) and ``segments`` locate the stored page
    artifact (each part ``chunk_id`` and ``<page>#chrome``). Both ``None``: the
    producer writes it (:mod:`g3o.persist.page_artifact`, PI ruling A5.1 a);
    only one of them given is refused. ``activity_values``
    / ``source_values`` hold, per T-022 activity id, the non-classifier items of
    the activities / sources table rows; ``codes`` the support results and
    coder records of the quote-step values among them. A page with no activity
    keys its page-level source row's values and codes :data:`NO_ACTIVITY`. ``ActivityObservation.supported``
    is derived by the producer (setting F; replaces RC-D-030 Y1 b), not an input.

    ``page_fields`` (T-030, PI ruling D1 a): the page-level source values the
    stored page fixes before coding
    (:class:`g3o.run.presweep.perpage_inputs_v27.PageSourceFields`: X28 URL and
    access date, A1 deterministic date, A2 archive test, A3 language, A4
    syndication group). With ``activity_values``, ``source_values`` and ``codes``
    all ``None``, :func:`produce_page` runs the T-015 source-row assembler on it
    after coding (PI ruling 35 a, :func:`g3o.run.presweep.source_row_v27.assemble`),
    which refuses while any row item has no producer; otherwise it is carried, not
    read, and the injected values hold every row value.

    ``followed`` / ``hop`` (T-025): a searched page is ``followed=False`` (hop
    unused); a page the follow leg fetched (:mod:`g3o.run.presweep.follow_v27`) is
    ``followed=True`` with its hop (>= 1) from the searched page, which the T-015
    assembler turns into ``core.discovery_path`` (PI ruling 61 a).
    """

    artifact_path: str | None = None
    segments: Mapping[str, tuple[int, int]] | None = None
    followed: bool | None = None
    activity_values: Mapping[str, Mapping[str, Any]] | None = None
    source_values: Mapping[str, Mapping[str, Any]] | None = None
    codes: Mapping[str, Sequence[tuple[SupportResult, CoderRecord]]] | None = None
    page_fields: Any = None
    hop: int | None = None


@dataclass(frozen=True)
class PageSpec:
    page: PageInput
    upstream: PageUpstream


@dataclass(frozen=True)
class InstitutionUpstream:
    independence_groups: Mapping[str, str] | None = None  # source id -> group; None: produced in Stage 6 (A7)
    merged_values: Mapping[tuple[str, ...], Mapping[str, Any]] | None = None


@dataclass(frozen=True)
class PerPageInstitution:
    run_id: str
    institution_uid: str
    institution: Mapping[str, Any]  # the six master identity columns
    country: str | None
    pages: Sequence[PageSpec]  # attempted order (page order of the pooled quotes)
    upstream: InstitutionUpstream

    @property
    def institution_id(self) -> str:
        return str(self.institution["institution_id"])


PageSupportFn = Callable[[PageInput, PageCodeResult, Sequence[CoderRecord]], Sequence[SupportResult]]
ActivityInputFn = Callable[[PageInput, PageRoundResult], ActivityPageInput | None]
ActivitySupportFn = Callable[[ActivityPageInput, PageActivityResult, Sequence[tuple[str, CoderRecord]]],
                             Sequence[SupportResult]]
PairSupportFn = Callable[[ActivityPageInput, PageActivityResult], Sequence[SupportResult]]


@dataclass(frozen=True)
class PerPageProviders:
    """Injected seams: T-024 support for page codes, T-022 spans, T-032/T-024 activity and pair support."""

    page_support: PageSupportFn
    activity_input: ActivityInputFn
    activity_support: ActivitySupportFn
    pair_support: PairSupportFn


@dataclass
class PerPageMetrics:
    ready: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    #: institutions that are a terminal failure (:data:`NO_PAGE_CODED_FAILED`): neither ready nor held
    failed: list[str] = field(default_factory=list)
    failed_pages: list[str] = field(default_factory=list)
    live_requests: int = 0
    replayed_requests: int = 0
    #: PI ruling 134: extractor results journaled from a Message Batch in this pass
    batched_requests: int = 0
    checkpoint_writes: int = 0
    usage: dict[str, dict[str, int]] = field(default_factory=dict)
    #: page id -> why its verdict support was downgraded ``downgraded_no_quote`` (PI ruling 99.1 a / 99.2)
    verdict_downgrades: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The per-page producer (T-028 per-page fragments)
# ---------------------------------------------------------------------------


def _support_key(sr: SupportResult) -> tuple[Any, ...]:
    return (sr.activity_id, sr.item_id, sr.part, sr.chunk_id, sr.linked_activity)


def _index(support: Iterable[SupportResult]) -> dict[tuple[Any, ...], SupportResult]:
    out: dict[tuple[Any, ...], SupportResult] = {}
    for sr in support:
        if out.setdefault(_support_key(sr), sr) is not sr:
            raise ValueError(f"duplicate support identity {_support_key(sr)}")
    return out


# PI Q-T3 (i) a (2026-11-18, T-041): a combined value set because every part gave the temporary
# answer (R-044, codebook combining_conventions.not_covered_by_this_part: "the page is 'not
# documented'") is carried by a rule node naming that signed slot, so it is stored, not held (Y3 b
# then holds only a combined value no part and no rule carries).
NOT_COVERED_RULE = "combining_conventions:not_covered_by_this_part"


def _all_not_covered(records: Iterable[CoderRecord], item: str, part: str | None, value: Any,
                     part_id: str | None) -> bool:
    """True when ``value`` was set by the all-parts-not-covered rule: no deciding part, and every
    classifier record for ``item``/``part`` gave the temporary answer."""
    if part_id is not None or value == NOT_COVERED:
        return False
    answers = [r.chosen_value for r in records
               if r.coder_type == "classifier" and r.item_id == item and r.item_part == part]
    return bool(answers) and all(a == NOT_COVERED for a in answers)


def _rule_support(rec: CoderRecord, activity_id: str | None, sources: PageSources) -> SupportResult:
    if not rec.rule_reference:
        raise ValueError(f"mechanical record for {rec.item_id} names no rule")
    return check_code(CodeEvidence(rec.item_id, str(rec.chosen_value), rec.chunk_id, part=rec.item_part,
                                   rule_name=rec.rule_reference, activity_id=activity_id), sources)


def _mechanical(item: str, part: str | None, qid: str | None, value: Any, rule: str, *, coder_version: str,
                qsv: str, setup_pointer: str) -> CoderRecord:
    return CoderRecord(item_id=item, item_part=part, question_id=qid, support_id=None, observation_id=None,
                       chunk_id=None, coder_type="mechanical", coder_version=coder_version,
                       configured_model=None, actual_response_model=None, request_id=None,
                       question_set_version=qsv, setup_pointer=setup_pointer, answer_type="rule",
                       chosen_value=value, confidence=None, probability_distribution=None, rule_reference=rule)


def _listify(values: Mapping[str, Any]) -> dict[str, Any]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in values.items()}


def _carried(row: Mapping[str, Any]) -> list[str]:
    """Classifier/quote-step values of a row that no support node carries."""
    missing = []
    for item, value in row["values"].items():
        f = FIELDS[item]
        if f["coder"] not in {"classifier", "quote_step"}:
            continue
        pairs = (list(value.items()) if "parts" in f else [(None, v) for v in value]
                 if isinstance(value, list) else [(None, value)])
        for part, selected in pairs:
            if not any(s["item_id"] == item and s["item_part"] == part and s["value_json"] == selected
                       for s in row["item_support"]):
                missing.append(f"{item}/{part}={selected!r}")
    return missing


class _Row:
    def __init__(self, emit: Callable[..., Any]) -> None:
        self.values: dict[str, Any] = {}
        self.item_support: list[dict[str, Any]] = []
        self.coder_records: list[dict[str, Any]] = []
        self._emit = emit
        self._ids: set[str] = set()

    def add(self, sr: SupportResult, rec: CoderRecord, ctx: SupportContext) -> dict[str, Any]:
        nodes, projections, provenance = self._emit(sr, rec, ctx)
        for node in nodes:
            if node["support_id"] not in self._ids:
                self._ids.add(node["support_id"])
                self.item_support.append(node)
        self.coder_records.extend(projections)
        return {"nodes": nodes, "provenance": provenance}

    def doc(self) -> dict[str, Any]:
        return {"values": _listify(self.values), "item_support": self.item_support,
                "coder_records": self.coder_records}


@dataclass
class PageProduct:
    page: ReviewedPage
    observations: list[ActivityObservation] = field(default_factory=list)
    records: list[ObservationRecord] = field(default_factory=list)
    quotes: list[InputQuote] = field(default_factory=list)
    within: list[RelationDecision] = field(default_factory=list)
    observation_inputs: dict[str, ObservationInput] = field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, PageArtifact] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)


def observation_id(page_id: str, activity_id: str) -> str:
    return f"{page_id}.{activity_id}"


def source_id(number: int) -> str:
    """Source claims are ``S<n>`` per institution (response_v27), numbered in page then activity order."""
    return f"S{number}"


def _passage_order(artifact: PageArtifact, sr: SupportResult) -> int:
    start, _ = artifact.span(sr.quote_chunk_id)
    text = artifact.segment_text(sr.quote_chunk_id)
    found = _locate(sr.supporting_text, text) or _locate_by_words(sr.supporting_text, text)
    if found is None:
        raise ConsolidationError(f"supported quote of {sr.item_id} is not located on its stored segment")
    return start + found[0]


def observation_supported(aid: str, outcomes: Mapping[str, Any],
                          support: Mapping[tuple[Any, ...], SupportResult]) -> bool:
    """Setting F (replaces RC-D-030 Y1 b): the final ``activity_type`` or ``action_type`` is supported.

    A value is supported when its final outcome was combined from the parts without
    failing and the support result at its deciding part has status ``supported``; a
    gated, rule-set, failed (downgraded) or missing value is not.
    """
    def value_supported(item: str) -> bool:
        o = next((o for o in outcomes.values() if o.item_id == item and o.part is None), None)
        if o is None or o.state != "combined" or o.failed or o.part_id is None:
            return False
        sr = support.get((aid, item, None, o.part_id, None))
        return not (sr is None or sr.support_status != "supported" or sr.value != o.value)

    return any(value_supported(item) for item in SUPPORTED_ITEMS)


def within_page_decision(pair: PairResult, answered: Sequence[tuple[CoderRecord, SupportResult]]
                         ) -> tuple[str, float | None, str] | None:
    """RC-D-030 Y5 a: a finalized T-023 pair -> ``(relation, probability, support status)`` or None.

    ``answered`` pairs each answered part record (not the temporary part answer)
    with its checked support, in part order. One relation in the combined value:
    that relation, the lowest chosen probability among the parts that chose it
    (None when one of them has none), ``supported`` only if all of those parts
    are (else the first other status). More than one value, a value outside the
    relation vocabulary, an unfinished outcome, or another value no part chose:
    None, so the pair is held. PI Q-T3 (ii) a (2026-11-18, T-041): ``unknown``
    because every answered part's vote failed its check is a decision, as a
    failed cross-page vote is: ``unknown`` (never merges), the lowest answered
    probability, the first non-supported status.
    """
    if pair.outcome.state != "combined":
        return None
    raw = pair.outcome.value
    values = list(dict.fromkeys(raw if isinstance(raw, (list, tuple)) else [raw]))
    if len(values) != 1 or values[0] not in RELATIONS:
        return None
    relation = values[0]
    chose = [(rec, sr) for rec, sr in answered if rec.chosen_value == relation]
    if not chose:
        if relation != "unknown" or not pair.outcome.failed or not answered:
            return None
        chose = list(answered)
    probs = [rec.chosen_answer_probability for rec, _ in chose]
    probability = None if any(p is None for p in probs) else min(probs)
    status = next((sr.support_status for _, sr in chose if sr.support_status != "supported"), "supported")
    return relation, probability, status


def _activity_source_items(config: ActivityCoderConfig) -> list[str]:
    """Sources-table items asked by the activity question set (the evaluation items), in set order."""
    qset = config.question_set if config.question_set is not None else jac.load_set("activity")
    return list(dict.fromkeys(q["item_id"] for q in qset["questions"] if q["item_id"] in SOURCE_ITEMS))


def failed_page(spec: PageSpec, reason: str) -> ReviewedPage:
    """An attempted page that failed: unreviewed, failed, reason kept. Either T-021 could not code
    it (no artifact), or it was coded and failed after halving in an extra round (PI ruling 69 b)."""
    if spec.upstream.followed is None:
        raise MissingUpstreamError(FOLLOW_PRODUCER, [spec.page.page_id])
    return ReviewedPage(spec.page.page_id, PIPELINE, FAILED_PAGE_VERDICT, None, FAILED_PAGE_SUPPORT, False, True,
                        spec.upstream.followed, (), (), (), failure_reason=reason)


def quote_stage_as_of(product: PageProduct, oid: str, sid: str) -> str:
    """``InputQuote.stage_as_of``: the pooled-quote order's fallback date for an undated source (R-044).

    PI ruling 94 a: a per-page fragment carries no ``core.stage_as_of`` (Stage 6 is its only
    producer), so the observation's date is read with the Stage 6 rule itself
    (:func:`g3o.validate.merged_activity_v27.observation_stage_as_of`) over this observation's
    fragment and its source row. It orders quotes only; it is never a row value. An absent input
    raises ``MissingUpstreamError`` (a stage stop, as any absent upstream value here) and a
    malformed one :class:`~g3o.validate.merged_activity_v27.MalformedA8Value` (ruling 32 b).
    """
    view = SimpleNamespace(observation_inputs={oid: product.observation_inputs[oid]},
                           sources={sid: product.sources[sid]})
    return ma.observation_stage_as_of(view, oid).date


def produce_page(*, run_dir: Path, run_id: str, institution_uid: str, spec: PageSpec, page_order: int,
                 first_source: int,
                 page_round: PageRoundResult, activity_input: ActivityPageInput | None,
                 activity_round: ActivityRoundResult | None, pairs: Sequence[PairResult],
                 pair_support: Sequence[SupportResult], page_config: PageCoderConfig,
                 activity_config: ActivityCoderConfig, instrument: dict[str, Any],
                 extraction: Any = None, official_sites: Any = None, pass2: Any = None,
                 activity_extraction: Any = None, source_typing: Any = None,
                 source_type_codes: Any = None) -> PageProduct:
    """Final per-page values and their support -> the Stage 6 per-page inputs of one coded page.

    ``source_typing`` / ``source_type_codes``: the page's residual ``source_type`` answers and their
    checks (PI ruling 95 a; ``_PageState``), which the T-015 assembler turns into the row value.

    ``extraction`` is the page's T-022 pass-1 page request (``PerPageProviders.page_extraction``),
    read by the T-015 source-row assembler when no row values are injected (PI ruling 35 a);
    ``official_sites`` the run's official sites it reads (PI ruling 70 b,
    :func:`g3o.run.presweep.official_site_v27.load_run_official_sites`); ``pass2`` the page's
    T-032 pass-2 page request (``PerPageProviders.page_pass2``), whose field tasks it reads for
    an open reported_* gate (PI ruling 73.1 b); ``activity_extraction`` the page's activity-only
    pass-1 request (PI ruling 87 c, ``PerPageProviders.activity_extraction``) when its activities
    came from it, whose spans and response the assembler then reads for the activity fields.

    Uncertainty flags (PI A6.1 a / A6.3 a): each node carries its own code's flags
    (:func:`g3o.validate.uncertainty_flags_v27.code_flags`); an observation row's
    ``core.uncertainty_flags`` is the union of its nodes' flags (ruling 11; a page
    holds no cross-page relation, so the R1 a ``identity_unresolved`` exception of
    :func:`~g3o.validate.uncertainty_flags_v27.row_flags` never applies here).
    """
    page, up = spec.page, spec.upstream
    if not (page_round.complete and (activity_round is None or activity_round.complete)):
        raise ConsolidationError("page has pending questions; nothing is produced")
    if up.followed is None:
        raise MissingUpstreamError(FOLLOW_PRODUCER, [page.page_id])
    if (up.artifact_path is None) != (up.segments is None):  # half an injected layout: a wiring gap
        raise MissingUpstreamError(ARTIFACT_PRODUCER, [page.page_id])
    result = page_round.result
    if up.artifact_path is None:  # A5.1 a: produce the stored page artifact (main, separator, chrome)
        stored = write_page_artifact(run_dir, institution_id=page.institution_id, url=page.url,
                                     page_id=page.page_id, main_text=page.text, chunks=result.chunks,
                                     chrome_text=contact_text(page))
        artifact_path, segments = stored.path, stored.segments
    else:  # injected layout (PageUpstream seam, PI ruling D1 a)
        artifact_path, segments = up.artifact_path, up.segments
    text = (run_dir / artifact_path).read_bytes().decode("utf-8")
    sources = PageSources(page.page_id, {c.chunk_id: c.text for c in result.chunks}, contact_text(page))
    acts = {} if activity_round is None else {a.activity_id: a for a in activity_round.result.activities}
    finals = {} if activity_round is None else {f.activity_id: f for f in activity_round.final}
    keys = list(acts) or [NO_ACTIVITY]  # source-row units: one per activity, or the page (Y2 a)
    if up.page_fields is not None and all(v is None for v in (up.activity_values, up.source_values, up.codes)):
        # PI ruling 35 a: the T-015 assembler builds the rows after coding. A row is published whole or
        # not at all, so any item it cannot produce yet is a wiring gap that stops the stage (RC-D-033 C2 a).
        verdict = page_round.final.items[jpc.VERDICT]
        if verdict.state == "combined":
            vsr = next((s for s in page_round.support if s.item_id == jpc.VERDICT and s.activity_id is None
                        and s.part is None and s.chunk_id == verdict.part_id), None)
        else:  # a rule-set verdict (e.g. R-015): its set_by_rule support carries no quote (PI ruling 72 a)
            vsr = next((_rule_support(r, None, sources) for r in result.records
                        if r.item_id == jpc.VERDICT and r.coder_type != "classifier"), None)
        rows = srow.assemble(page, up.page_fields, outcome_values(page_round.final.items),
                             {aid: outcome_values(f.outcomes) for aid, f in finals.items()},
                             followed=up.followed, hop=up.hop, extraction=extraction, sources=sources,
                             verdict_support=vsr, official_sites=official_sites, pass2=pass2,
                             activity_extraction=activity_extraction, source_typing=source_typing,
                             source_type_codes=source_type_codes,
                             provenance=srow.Provenance.of(instrument, extraction,
                                                           rule_coder_version=activity_config.coder_version))
        if rows.stops:  # unproduced items and wiring gaps stop the stage (RC-D-033 C2 a, PI 32 b)
            raise MissingUpstreamError(f"{VALUES_PRODUCER} ({srow.ASSEMBLER})", sorted(rows.refused))
        if rows.refused:  # PI ruling 97 b: refused on the page's own data: this institution is held
            raise RowValueRefused(page.page_id, rows.data_refusals())
        a_vals, s_vals, codes = rows.to_upstream(keys)
        up = replace(up, activity_values=a_vals, source_values=s_vals, codes=codes)
    for name, value, need in (("activity_values", up.activity_values, list(acts)),
                              ("source_values", up.source_values, keys), ("codes", up.codes, keys)):
        if need and (value is None or set(need) - set(value)):
            raise MissingUpstreamError(f"{VALUES_PRODUCER} ({name})",
                                       sorted(set(need) - set(value or {})) or [page.page_id])
    uf.check_pipeline(PIPELINE)
    given_flags = sorted(aid for aid in acts if uf.ITEM in up.activity_values[aid])
    if given_flags:
        raise ValueError(f"upstream values overwrite the produced {uf.ITEM} (A6): {given_flags}")
    # A6.1 a: the adoption-stage answers of each activity's parts, before combining.
    stage_answers = {aid: uf.classifier_answers(a.records) for aid, a in acts.items()}
    labels = activity_config.labels if activity_config.labels is not None else jac.default_labels()
    qsv_page = result.question_set_version
    qsv_act = None if activity_round is None else activity_round.result.question_set_version
    out = PageProduct(page=None)  # type: ignore[arg-type]

    def emit(sr: SupportResult, rec: CoderRecord, ctx: SupportContext, artifact: PageArtifact) -> Any:
        flags = uf.code_flags(sr, stage_answers=stage_answers.get(sr.activity_id, ()))
        nodes = support_nodes(sr, sources, artifact, replace(ctx, uncertainty_flags=flags), instrument)
        rec = replace(rec, support_id=nodes.original["support_id"], observation_id=nodes.original["observation_id"])
        projection, final_projection, _ = coder_nodes(rec, nodes, instrument)
        out.provenance.append(nodes.provenance)
        return ([n for n in (nodes.original, nodes.final) if n is not None],
                [c for c in (projection, final_projection) if c is not None], nodes.provenance)

    page_support = _index(page_round.support)
    act_support = _index(() if activity_round is None else activity_round.support)
    pair_index = _index(pair_support)

    def page_codes() -> list[tuple[SupportResult, CoderRecord]]:
        codes = []
        for rec in result.records:
            if rec.coder_type == "classifier":
                if rec.chosen_value == NOT_COVERED:
                    continue  # the temporary part answer is never checked or stored (R-044)
                codes.append((page_support[(None, rec.item_id, rec.item_part, rec.chunk_id, None)], rec))
            else:
                codes.append((_rule_support(rec, None, sources), rec))
        for iid in page_round.final.regated:
            o = page_round.final.items[iid]
            rec = _mechanical(iid, None, None, o.value, o.rule_reference, coder_version=page_config.coder_version,
                              qsv=qsv_page, setup_pointer=page_config.setup_pointer)
            codes.append((_rule_support(rec, None, sources), rec))
        for iid, o in page_round.final.items.items():
            if (o.state == "combined" and iid not in page_round.final.regated and not o.failed
                    and _all_not_covered(result.records, iid, None, o.value, o.part_id)):
                rec = _mechanical(iid, None, None, o.value, NOT_COVERED_RULE,
                                  coder_version=page_config.coder_version, qsv=qsv_page,
                                  setup_pointer=page_config.setup_pointer)
                codes.append((_rule_support(rec, None, sources), rec))
        return codes

    def activity_codes(aid: str) -> list[tuple[SupportResult, CoderRecord]]:
        act, fin = acts[aid], finals[aid]
        codes = []
        for rec in act.records:
            if rec.item_id in jac.PAIR_ITEMS:
                continue  # pair records come from the finalized pairs
            if rec.coder_type == "classifier":
                if rec.chosen_value == NOT_COVERED:
                    continue
                codes.append((act_support[(aid, rec.item_id, rec.item_part, rec.chunk_id, None)], rec))
            else:
                codes.append((_rule_support(rec, aid, sources), rec))
        rule_set = [(qid, o) for qid, o in fin.outcomes.items()
                    if qid in fin.regated or o.rule_reference == PERMANENT_PILOT_RULE]
        for qid, o in rule_set:
            rec = _mechanical(o.item_id, o.part, qid, o.value, o.rule_reference,
                              coder_version=activity_config.coder_version, qsv=qsv_act,
                              setup_pointer=activity_config.setup_pointer)
            codes.append((_rule_support(rec, aid, sources), rec))
        for qid, o in fin.outcomes.items():
            if (o.state == "combined" and (qid, o) not in rule_set and not o.failed
                    and o.item_id not in jac.PAIR_ITEMS
                    and _all_not_covered(act.records, o.item_id, o.part, o.value, o.part_id)):
                rec = _mechanical(o.item_id, o.part, qid, o.value, NOT_COVERED_RULE,
                                  coder_version=activity_config.coder_version, qsv=qsv_act,
                                  setup_pointer=activity_config.setup_pointer)
                codes.append((_rule_support(rec, aid, sources), rec))
        return codes

    page_values = outcome_values(page_round.final.items)
    page_list = page_codes()
    page_nodes: list[dict[str, Any]] = []
    page_coders: list[dict[str, Any]] = []
    oids = {aid: observation_id(page.page_id, aid) for aid in acts}
    sids = {aid: source_id(first_source + n) for n, aid in enumerate(keys)}
    artifacts = {aid: PageArtifact(sids[aid], artifact_path, text, dict(segments)) for aid in keys}
    spans = {} if activity_input is None else {s.activity_id: s for s in activity_input.spans}
    for aid in keys:
        oid, sid, artifact = oids.get(aid), sids[aid], artifacts[aid]
        ctx = SupportContext(run_id, institution_uid, oid, sid, None)
        a_row = _Row(lambda sr, rec, c, a=artifact: emit(sr, rec, c, a))
        s_row = _Row(lambda sr, rec, c, a=artifact: emit(sr, rec, c, a))
        if oid is None:  # Y2 a: activity-question items of the sources table take _NA_ by rule
            act_values = {i: NO_ACTIVITY for i in _activity_source_items(activity_config)}
        else:
            act_values = outcome_values(finals[aid].outcomes)
        produced_a = {k: v for k, v in act_values.items() if k in ACTIVITY_ITEMS}
        if oid is not None:  # checked against the row's nodes once they are all added
            produced_a[uf.ITEM] = [uf.STAGE_AMBIGUOUS] if uf.stage_ambiguous(stage_answers[aid]) else []
        produced_s = {**{k: v for k, v in page_values.items() if k in SOURCE_ITEMS},
                      **{k: v for k, v in act_values.items() if k in SOURCE_ITEMS}}
        units = [(produced_s, up.source_values[aid], SOURCE_ROW_ITEMS, s_row)]
        if oid is not None:
            units.insert(0, (produced_a, up.activity_values[aid], ACTIVITY_ITEMS, a_row))
        for produced, given, table, row in units:
            clash = sorted(set(produced) & set(given))
            if clash:
                raise ValueError(f"upstream values overwrite produced classifier values: {clash}")
            given_classifier = sorted(k for k in given if FIELDS[k]["coder"] in PRODUCED_CODERS
                                      and k != T015_CLASSIFIER)
            if given_classifier:
                raise ValueError(f"classifier values must come from the coders: {given_classifier}")
            if table is ACTIVITY_ITEMS:
                stage6_only = sorted(set(given) & set(srow.STAGE6_ACTIVITY_ITEMS))
                if stage6_only:  # PI ruling 94 a: one producer per item, and it is Stage 6
                    raise ValueError(f"per-page activity values name Stage-6-only items (ruling 94 a): {stage6_only}")
            else:
                stage6_only = sorted(set(given) & set(srow.STAGE6_SOURCE_ITEMS))
                if stage6_only:  # PI ruling 140 (review O2 M3): Stage 6 is the only producer of these
                    raise ValueError(f"per-page source values name Stage-6-only items (ruling 140): {stage6_only}")
            row.values.update({**given, **produced})
            missing = sorted(table - set(row.values))
            if missing:
                raise MissingUpstreamError(VALUES_PRODUCER, missing)
        for sr, rec in page_list:
            added = s_row.add(sr, rec, ctx)
            if aid == keys[0]:
                page_nodes.extend(added["nodes"])
        if oid is not None:
            for sr, rec in activity_codes(aid):
                (s_row if rec.item_id in SOURCE_ITEMS else a_row).add(sr, rec, ctx)
        else:
            for item, value in act_values.items():
                rec = _mechanical(item, None, None, value, NA_RULE, coder_version=page_config.coder_version,
                                  qsv=qsv_page, setup_pointer=page_config.setup_pointer)
                s_row.add(_rule_support(rec, None, sources), rec, ctx)
        for sr, rec in up.codes[aid]:
            if FIELDS[rec.item_id]["coder"] != "quote_step" and rec.item_id != T015_CLASSIFIER:
                raise ValueError(f"upstream code for {rec.item_id} is not a quote-step or T-015 value")
            if oid is None and rec.item_id not in SOURCE_ITEMS:
                raise ValueError(f"upstream code for {rec.item_id} on a page with no activity")
            (a_row if rec.item_id in ACTIVITY_ITEMS else s_row).add(sr, rec, ctx)
        if aid == keys[0]:
            page_ids = {n["support_id"] for n in page_nodes}
            page_coders = [c for c in s_row.coder_records if c["support_id"] in page_ids]
        out.artifacts[sid] = artifact
        src = s_row.doc()
        src.update(observation_ids=[] if oid is None else [oid], page_artifact_path=artifact_path,
                   page_content_sha256=sha256_text(text))
        out.sources[sid] = src
        docs = [src]
        if oid is not None:
            if a_row.values[uf.ITEM] != uf.row_flags(a_row.item_support):
                raise ConsolidationError(f"{uf.ITEM} of {oid} differs from its nodes' flags")
            out.observation_inputs[oid] = ObservationInput(oid, sid, a_row.doc())
            docs.insert(0, a_row.doc())
        for doc in docs:
            missing = _carried(doc)
            if missing:
                raise UncarriedCombinedValue(page.page_id, missing)
    for pair in pairs:  # within-page decisions; nodes on the earlier (lhs) observation's row
        lhs, rhs = pair.activity_id, pair.linked_activity
        if lhs not in acts or rhs not in acts:
            raise ConsolidationError("pair names an activity that was not coded")
        frag = out.observation_inputs[oids[lhs]].row
        ctx = SupportContext(run_id, institution_uid, oids[lhs], sids[lhs], None, linked_observation_id=oids[rhs])
        checked: list[tuple[SupportResult, list[str]]] = []
        answered: list[tuple[CoderRecord, SupportResult]] = []
        records: list[dict[str, Any]] = []
        for rec in pair.records:
            if rec.chosen_value == NOT_COVERED:
                continue
            sr = pair_index[(lhs, rec.item_id, rec.item_part, rec.chunk_id, rhs)]
            nodes, projections, _ = emit(sr, rec, ctx, artifacts[lhs])
            known = {s["support_id"] for s in frag["item_support"]}
            frag["item_support"].extend(n for n in nodes if n["support_id"] not in known)
            frag["coder_records"].extend(projections)
            records.extend(projections)
            checked.append((sr, [n["support_id"] for n in nodes]))
            answered.append((rec, sr))
        decided = within_page_decision(pair, answered)
        if decided is None:
            continue  # no decision: Stage 6 holds the institution on the missing pair
        relation, probability, status = decided
        if relation not in RELATIONS:
            raise ConsolidationError(f"within-page relation {relation!r} is outside the signed vocabulary")
        ids = tuple(i for sr, node_ids in checked if relation in (sr.original_value, sr.value) for i in node_ids)
        out.within.append(RelationDecision(oids[lhs], oids[rhs], relation, probability, status, tuple(records),
                                           ids, "within_page"))
    verdict = page_round.final.items[jpc.VERDICT]
    if verdict.state == "combined":
        vsr = page_support.get((None, jpc.VERDICT, None, verdict.part_id, None))
        if vsr is None:
            raise ConsolidationError("final page verdict has no support result at its deciding part")
        verdict_status = vsr.support_status
    else:
        verdict_status = "set_by_rule"
    out.page = ReviewedPage(page.page_id, PIPELINE, verdict.value, verdict.probability, verdict_status, True, False,
                            up.followed, tuple(sids[a] for a in keys), tuple(page_coders), tuple(page_nodes))
    for aid in acts:
        oid, sid, artifact = oids[aid], sids[aid], artifacts[aid]
        frag = out.observation_inputs[oid].row
        src_values = out.sources[sid]["values"]
        date = src_values.get("core.source_publication_date")
        date = date if isinstance(date, str) and date not in MISSING else None
        type_label = value_label("core.source_type", None, src_values.get("core.source_type"), labels)
        stage_as_of: str | None = None  # read only when the observation has a quote (below)
        quotes = []
        by_id = {n["support_id"]: n for n in frag["item_support"]}
        all_sr = [*(sr for sr, rec in activity_codes(aid)), *(sr for sr, _ in up.codes[aid])]
        for sr in all_sr:
            if sr.support_status != "supported" or sr.supporting_text is None or sr.item_id not in ACTIVITY_ITEMS:
                continue
            node = next(n for n in by_id.values() if n["item_id"] == sr.item_id and n["item_part"] == sr.part
                        and n["chunk_id"] == sr.chunk_id and n["value_json"] == sr.original_value
                        and n["input_support_ids"] == [])
            if stage_as_of is None:
                stage_as_of = quote_stage_as_of(out, oid, sid)
            quotes.append(InputQuote(node["support_id"], oid, sid, sources, sr.chunk_id, sr.quote_chunk_id,
                                     sr.supporting_text, type_label, date, stage_as_of,
                                     page.url, page_order, _passage_order(artifact, sr)))
        quotes.sort(key=lambda q: (q.passage_order, q.support_id))
        out.quotes.extend(quotes)
        out.records.append(ObservationRecord(oid, page.page_id, dict(frag["values"]), page.url, tuple(quotes)))
        out.observations.append(ActivityObservation(
            oid, page.page_id, finals[aid].outcomes, nano_values(spans[aid]),
            observation_supported(aid, finals[aid].outcomes, act_support),
            tuple(frag["coder_records"]), tuple(frag["item_support"])))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def page_state_dir(run_dir: Path, page: Any) -> Path:
    """``<inst>/perpage_v27/<url_hash>``: the page's checkpoints (``page`` needs ``institution_id`` and ``url``)."""
    return institution_dir(run_dir, page.institution_id) / WORK_DIR / url_hash(page.url)


_page_dir = page_state_dir


def _archive_page_state(run_dir: Path, page: PageInput, files: Sequence[str] = PAGE_STATE_FILES) -> list[str]:
    """Move ``page``'s saved state to ``<page dir>/archive/<NNN>/`` (ruling 33 a); never deletes.

    The per-page checkpoints named in ``files`` (default :data:`PAGE_STATE_FILES`;
    :data:`ACTIVITY_STATE_FILES` for a PI ruling 113 b re-ask, :func:`archive_activity_state`)
    and the T-023 activity artifact (either stored form, kept under ``activity_code_v27/``
    in the archive folder) are moved; the residual ``source_type`` answers
    (:data:`SOURCE_TYPE_FILE`) stay (review M-1). Each call takes the next free ``NNN``.
    Returns the archived paths relative to the institution dir (empty when the page had
    no saved state).

    All or nothing across runs (ruling 28 a): the folder and ``files`` are first recorded in
    :data:`PAGE_ARCHIVE_PENDING` in the page dir, and that marker is moved into
    the archive folder only after every file. An ``OSError`` that survives the
    write retries raises :class:`PageArchiveIncomplete` (the caller holds the
    institution); the marker stays, so :func:`_rounds_for_page` finishes this
    same archive before it loads any state. A call with the marker present
    resumes the recorded folder and file set instead of taking a new ``NNN`` (a marker
    written before ``files`` were recorded moves :data:`PAGE_STATE_FILES`).
    """
    inst_dir = institution_dir(run_dir, page.institution_id)
    pdir = _page_dir(run_dir, page)
    marker = pdir / PAGE_ARCHIVE_PENDING
    art = stage_activity_code.artifact_path(inst_dir / ACTIVITY_DIR, page.page_id)

    def rel_inst(path: Path) -> str:
        return path.relative_to(inst_dir).as_posix()

    def state_moves(names: Sequence[str]) -> list[tuple[Path, Path]]:
        if isinstance(names, str) or not all(isinstance(n, str) and n in PAGE_STATE_FILES for n in names):
            raise MalformedCheckpoint(f"unsupported per-page checkpoint: page-state archive of {names!r} ({marker})")
        found = [(pdir / name, Path(name)) for name in names]
        found += [(p, Path(ACTIVITY_DIR) / p.name) for p in (gz_path(art), plain_path(art))]
        return [(src, rel) for src, rel in found if src.exists()]

    files = tuple(files)
    root = pdir / PAGE_ARCHIVE_DIR
    archived: list[str] = []
    moves: list[tuple[Path, Path]] = []
    try:
        if marker.exists():  # an earlier archive of this page was left incomplete: finish that one
            doc = _read_checkpoint(marker, "archive_pending")
            name, files = doc.get("archive"), doc.get("files", PAGE_STATE_FILES)
            if not isinstance(name, str) or not re.fullmatch(r"[0-9]{3,}", name) or not isinstance(files, list | tuple):
                raise MalformedCheckpoint(f"unsupported per-page checkpoint: {marker}")
            dest = root / name
            files = tuple(files)
            moves = state_moves(files)
        else:
            moves = state_moves(files)
            if not moves:
                return []
            taken = {p.name for p in root.iterdir()} if root.is_dir() else set()
            n = 1
            while f"{n:03d}" in taken:
                n += 1
            dest = root / f"{n:03d}"
            _atomic_write(marker, canonical_json({"format": CHECKPOINT_FORMAT, "kind": "archive_pending",
                                                  "archive": dest.name, "files": list(files)}))
        for src, rel in moves:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_with_retry(src, target)
            archived.append(rel_inst(target))
        dest.mkdir(parents=True, exist_ok=True)
        replace_with_retry(marker, dest / PAGE_ARCHIVE_PENDING)  # last: this archive is complete
    except OSError as exc:
        left = [rel_inst(src) for src, _ in moves if src.exists()]
        if marker.exists():
            left.append(rel_inst(marker))
        raise PageArchiveIncomplete(archived, left, exc, files) from exc
    return archived


def archive_activity_state(run_dir: Path, page: Any) -> list[str]:
    """PI ruling 113 b: move ``page``'s activity-level state (:data:`ACTIVITY_STATE_FILES` and the T-023
    activity artifact) to ``<page dir>/archive/<NNN>/`` before the one live re-ask a PI release authorises
    for a pass-1 / activity-only hold (:data:`PASS1_NOT_JOURNALED`, :data:`ACTIVITY_ONLY_NOT_JOURNALED`).

    Called by the provider adapter right before that call
    (:meth:`g3o.run.presweep.perpage_providers_v27._Adapter._require_journaled`), inside
    ``activity_input``: the activity checkpoint, the T-023 artifact and the pair checkpoint are read only
    after it, so the page's activity state is built again from the new response's spans. ``page.json`` and
    :data:`SOURCE_TYPE_FILE` stay. Review H-1: the adapter then writes a fresh ``pass1_requests.json`` naming the
    request about to be sent (:func:`record_pass1_reask`), so a re-ask that dies or fails is still checked by
    the next run's 105 b guard.

    Crash-safe and idempotent, as the 33 a archive (:func:`_archive_page_state`): the pending marker records
    the file set, an incomplete archive is finished by the next run before any state is loaded (or from
    ``held.json``'s ``archive_files``), and a call that finds nothing to move (an earlier run archived it and
    then stopped before the call) takes no new folder. The re-ask's authorisation is spent by the journal
    only after this returns (PI ruling 114 b), so a crash here leaves it to the next run.

    Since PI ruling 121 b this is the archive of an activity-only re-ask (:data:`ACTIVITY_ONLY_NOT_JOURNALED`); a
    pass-1 page request re-ask uses :func:`archive_page_request_state`."""
    return _archive_page_state(run_dir, page, ACTIVITY_STATE_FILES)


def archive_page_request_state(run_dir: Path, page: Any) -> list[str]:
    """PI ruling 121 b: before the one live re-ask a PI release authorises for a pass-1 page request hold
    (:data:`PASS1_NOT_JOURNALED`), move ``page.json`` with the page's activity-level state
    (:data:`PAGE_REQUEST_STATE_FILES` and the T-023 activity artifact) to ``<page dir>/archive/<NNN>/``.
    :data:`SOURCE_TYPE_FILE` stays (review M-1).

    The page-level support saved in ``page.json`` was checked on the old response's quotes, while the stage reads
    the page request (its ``request_id``, the row's provenance) from the new response: archiving it makes the
    page's rounds start again from the stored T-021 result, so ``page_support`` makes the page request itself
    (the re-ask) and checks the support on the new quotes. So it is called before the page's rounds
    (:meth:`g3o.run.presweep.perpage_providers_v27._Adapter.prepare_pass1_reask`, from :func:`_rounds_for_page`
    right before ``page.json`` is loaded), never inside ``activity_input`` (too late: the page round of that run
    would already have been completed from the old ``page.json``). The adapter then writes a fresh
    ``pass1_requests.json`` naming the request (:func:`record_pass1_reask`), as for 113 b. PI ruling 127 a
    (accepted, spend control): the rebuilt rounds cost the re-ask plus the page-level support's X35 calls, and may
    trigger further jev extra-round and extractor extra-round calls, all journaled; not only "one extra jev
    page-support call". Crash-safe and
    idempotent as :func:`archive_activity_state` (the pending marker records this file set)."""
    return _archive_page_state(run_dir, page, PAGE_REQUEST_STATE_FILES)


#: review H-1: the :data:`PASS1_FILE` field that names a request of each 105 b hold stage
_PASS1_SLOTS = {PASS1_NOT_JOURNALED: "page_request", ACTIVITY_ONLY_NOT_JOURNALED: "activity_only"}


def _newest_archived_pass1(run_dir: Path, page: Any) -> dict[str, Any] | None:
    """Review L-3: the :data:`PASS1_FILE` record in the page's newest archive folder (highest ``NNN``) that holds
    one, or None. The folder taken by an archive that found no live record holds none, so it is skipped.

    Review L-c: a malformed archived record (not UTF-8 JSON, another format or kind) raises
    :class:`MalformedCheckpoint` (:class:`MalformedCheckpointJSON` for bytes that are not JSON) through
    :func:`_read_checkpoint`, and the stage stops, as for a malformed live
    page checkpoint (PI ruling 118 b); it is not skipped in favour of an older folder. Kept as built.

    PI ruling 124 a (accepted as built): the newest folder holding a record may be one a C4 hold archived (ruling
    33 a) rather than the re-ask archive whose record went missing, so the other field may carry a request name
    from that older state and the next run's 105 b check may hold that page when it need not (an over-hold,
    never a live call)."""
    root = page_state_dir(run_dir, page) / PAGE_ARCHIVE_DIR
    if not root.is_dir():
        return None
    folders = sorted((p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"[0-9]{3,}", p.name)),
                     key=lambda p: int(p.name), reverse=True)
    for folder in folders:
        if (folder / PASS1_FILE).exists():
            return _read_checkpoint(folder / PASS1_FILE, "pass1_requests")
    return None


def record_pass1_reask(run_dir: Path, page: Any, previous: Mapping[str, Any] | None, stage: str,
                       custom_id: str) -> None:
    """Review H-1 (PI rulings 105 b / 113 b / 114 b): write a fresh :data:`PASS1_FILE` naming the request about to
    be sent as the one live re-ask a PI release authorised, right after :func:`archive_activity_state` (or, for a
    pass-1 page request, :func:`archive_page_request_state`, PI ruling 121 b) moved the old record away and before
    that call (:meth:`g3o.run.presweep.perpage_providers_v27._Adapter._archive_for_reask`).

    ``custom_id`` goes in the field of ``stage`` (:data:`PASS1_NOT_JOURNALED`: ``page_request``;
    :data:`ACTIVITY_ONLY_NOT_JOURNALED`: ``activity_only``); the other field keeps the archived record's value
    (``previous``, as :func:`read_pass1_requests` read it before the archive; None: there was none). So when that
    call dies while sending, times out, fails or is rejected (``activity_input`` never returns, and
    :func:`_record_pass1_requests` never runs), the next run's provider-level 105 b check still finds the request
    named and holds it instead of sending it live; the journal refuses that call as well
    (:class:`~g3o.run.presweep.stage_validate_v27.ReaskSpentUnanswered`). Once ``activity_input`` returns, the
    stage rewrites the record from the requests actually built. Any other ``stage`` is a wiring error
    (``TypeError``, the stage stops).

    PI ruling 123 a (accepted, left as is): a crash after this write and before the journal's ``reask_spent``
    marker leaves the release unspent, so the next run archives again; the only file left to move is this fresh
    record, which then lands alone in a second archive folder (``archive/<NNN+1>/pass1_requests.json``).

    Review L-3: ``previous`` None is read again from the newest archive folder holding a record
    (:func:`_newest_archived_pass1`): an archive that died after moving the record was finished by the next run
    before the read (``_rounds_for_page``, ``held.json``'s ``archive_files``), so the read found none, and the other
    field would otherwise be written None, dropping the 105 b trigger for the other request. That fallback may
    read an older C4 archive's record and so over-hold the page (PI ruling 124 a, accepted as built), and a
    malformed archived record stops the stage (review L-c, PI ruling 118 b)."""
    if stage not in _PASS1_SLOTS:
        raise TypeError(f"page {page.page_id}: no pass-1 request record for hold stage {stage!r} (wiring error)")
    if previous is None:  # review L-3
        previous = _newest_archived_pass1(run_dir, page)
    doc = {name: (previous or {}).get(name) for name in _PASS1_SLOTS.values()}
    doc[_PASS1_SLOTS[stage]] = custom_id
    _atomic_write(page_state_dir(run_dir, page) / PASS1_FILE,
                  canonical_json({"format": CHECKPOINT_FORMAT, "kind": "pass1_requests", **doc}))


def _failure_reason(run_dir: Path, page: PageInput) -> str:
    reasons = [r["reason"] for r in attrition.read_records(run_dir)
               if r.get("stage") == stage_page_code.STAGE and r.get("url") == page.url
               and r.get("reason") != stage_page_code.PART_FAILURES]
    if not reasons:
        raise RuntimeError(f"page {page.page_id} has neither a page-code artifact nor a recorded failure")
    return reasons[-1]


@dataclass
class _PageState:
    spec: PageSpec
    page_round: PageRoundResult | None = None
    activity_input: ActivityPageInput | None = None
    activity_round: ActivityRoundResult | None = None
    pairs: tuple[PairResult, ...] = ()
    pair_support: tuple[SupportResult, ...] = ()
    extraction: Any = None  # the page's T-022 pass-1 page request (PerPageProviders.page_extraction)
    #: the page's activity-only pass-1 request (PI ruling 87 c; PerPageProviders.activity_extraction), or None
    activity_extraction: Any = None
    pass2: Any = None  # the page's T-032 pass-2 page request (PerPageProviders.page_pass2; PI ruling 73.1 b)
    #: the page's residual source_type answers (PI ruling 95 a; :func:`_residual_source_type`), or None
    source_typing: Any = None
    #: their T-024 checks, (support, record) pairs (``PerPageProviders.source_type_codes``)
    source_type_codes: Any = None
    #: review M2: row values already refused on the page's own data before T-022 (a residual source_type part
    #: over the request limit); the page is coded on, and the institution is held before its rows are produced
    #: (PI rulings 97 b, 106 a)
    row_refusal: Any = None
    failure: str | None = None
    holds: list[dict[str, Any]] = field(default_factory=list)


def downgrade_verdict_support(page: PageInput, page_round: PageRoundResult) -> PageRoundResult:
    """PI ruling 99.1 a / 99.2: the final verdict's support at its deciding part, re-checked with no quote
    (T-024, :func:`~g3o.common.support_check.check_code`): ``downgraded_no_quote``, the verdict value kept
    (R-041). The final items are not re-combined (the verdict stands, its support is downgraded), and the
    page checkpoint is not rewritten: the decision is made again from the journaled activity-only request
    on every run. Only a combined ``confirms_activity`` verdict is downgraded; anything else is a wiring
    error (``TypeError``)."""
    verdict = page_round.final.items.get(jpc.VERDICT)
    if verdict is None or verdict.state != "combined" or verdict.value != "confirms_activity":
        raise TypeError(f"page {page.page_id}: only a combined confirms_activity verdict is downgraded")
    key = (None, jpc.VERDICT, None, verdict.part_id, None)
    old = _index(page_round.support).get(key)
    if old is None:
        raise ConsolidationError("final page verdict has no support result at its deciding part")
    sources = PageSources(page.page_id, {c.chunk_id: c.text for c in page_round.result.chunks}, contact_text(page))
    new = check_code(CodeEvidence(jpc.VERDICT, old.original_value, old.chunk_id,
                                  probability=old.chosen_answer_probability), sources)
    if new.support_status != NO_QUOTE:
        raise TypeError(f"page {page.page_id}: verdict re-check without a quote gave {new.support_status!r}")
    support = tuple(new if _support_key(s) == key else s for s in page_round.support)
    return replace(page_round, support=support)


def _reask_seam(ask: Any) -> Any:
    """The journaled ``ask``'s re-ask seam (PI ruling 75 a; re-ask review LOW (a)).

    The per-page stage always journals ``ask`` (:meth:`RequestJournal.ask`), whose ``reask``
    attribute replays a re-ask already billed without a request id. It is passed to
    :func:`complete_page_rounds` explicitly; an ``ask`` without it (e.g. a wrapper that hid it)
    would silently resend a billed re-ask, so it is a wiring error that stops the stage
    (``TypeError``, not a per-institution hold; ruling 32 b)."""
    seam = getattr(ask, REASK_SEAM, None)
    if not callable(seam):
        raise TypeError(f"the per-page jev ask function has no callable {REASK_SEAM!r} seam (the request "
                        "journal's; ruling 75 a): a wiring error, the stage stops")
    return seam


def _residual_source_type(run_dir: Path, spec: PageSpec, ask: Any, page_config: PageCoderConfig,
                          official_sites: Any) -> Any:
    """PI ruling 95 a (building 83 b): the residual ``source_type`` question, asked before T-022.

    Only for a page whose rows the T-015 assembler builds (``page_fields`` given, no injected rows) and
    that ``items/core.source_type/rules/0`` leaves to the question: neither official
    (:func:`~g3o.run.presweep.source_row_v27.official_value`) nor an archive address, and readable
    (R-015). Asked with the journaled ``ask`` (recorded, priced, replayed on a resume) on the page's
    T-021 parts, so each answer's part is a part of the page's first pass-1 request
    (:func:`~g3o.common.source_fields.code_source_type`). Returns the classifier
    :class:`~g3o.common.source_fields.SourceTyping`, or None (typed by rule, or a refused input: no call is
    made, and the assembler refuses or types the page itself).

    PI ruling 112 a: a page the T-025 follow leg fetched (``followed`` True, no injected rows) is coded before
    its ``page_fields`` exist (``follow_v27.InstitutionLeg.finish`` builds them once every page is known, for
    the A4 grouping), and they always come from ``perpage_inputs_v27.page_source_fields``, so its rows are the
    assembler's. It is asked at coding time too, with the A2 archive test worked out from its URL
    (:func:`followed_archive_address`, the value ``finish`` later stores; a mismatch would stop the stage in the
    assembler: a residual answer for a page typed by rule, or a residual page with none, PI ruling 111 a).

    PI ruling 105 b: the answers are saved in the page dir (:data:`SOURCE_TYPE_FILE`) before the page's first
    pass-1 request is built, and a later run loads them instead of asking again: a non-deciding part that
    failed in an earlier run (an exception or a response with no request id, never replayed by the journal)
    is not asked again live, so the first pass-1 request is rebuilt with the same parameters and replayed
    from the journal. The file is kept across a C4 archive (ruling 33 a; review M-1, :data:`PAGE_STATE_FILES`):
    the answers depend on no pass-1 answer.

    PI ruling 110 b: when the deciding part failed with no answer
    (:func:`~g3o.run.presweep.source_row_v27.residual_deciding_part_failed`), the answers are NOT saved and
    :class:`ResidualPartFailed` is raised; the caller holds the institution before the page's first pass-1
    request is built. Saving only final answers (rather than saving these and re-asking the failed part on
    load) keeps that request, and so its 105 b journal check, built once on the answers it carries: a re-ask
    after the request was sent would change its quote tasks and hold the page as not journaled. The next run
    asks the question again through the journal: every answered part's response is replayed (no live call),
    only the failed part is asked live."""
    page, up = spec.page, spec.upstream
    if any(v is not None for v in (up.activity_values, up.source_values, up.codes)):
        return None
    followed_now = up.page_fields is None and getattr(up, "followed", None) is True  # PI ruling 112 a
    if up.page_fields is None and not followed_now:
        return None
    try:
        official = srow.official_value(page, official_sites)
    except srow._REFUSALS:  # absent data: the assembler refuses source_type; nothing is asked
        return None
    archive = (followed_archive_address(page) if followed_now
               else getattr(up.page_fields, "archive_address", None))
    if not isinstance(archive, bool) or sf.route_source_type(official, archive) is not None:
        return None
    t021 = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(run_dir, page.institution_id,
                                                                                page.url)))
    path = _page_dir(run_dir, page) / SOURCE_TYPE_FILE
    saved = load_source_typing(path, t021.chunks)
    if saved is not None:  # PI ruling 105 b: a resume reads the answers it asked, never asks again
        return saved
    asked: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def recording(state: dict[str, Any], questions: dict[str, Any]) -> Any:
        asked.append((state, questions))  # PI ruling 120 c: names the deciding part's request in a hold
        return ask(state, questions)
    try:
        typing = sf.code_source_type(page, recording, page_config, layout=t021.chunks)
    except jpc.LayoutPartOverLimit as exc:  # review M2: never halved; the page's own data (PI ruling 97 b)
        raise RowValueRefused(page.page_id, {sf.SOURCE_TYPE: f"{RESIDUAL_OVER_LIMIT}: {exc}"}) from exc
    if typing.typed_by != "classifier":
        return None
    failed_part = srow.residual_deciding_part_failed(typing)
    if failed_part is not None:  # PI ruling 110 b: not saved, so the next run asks again; held before T-022
        key = _residual_part_key(ask, asked, typing.result.chunks, failed_part)
        spent_fn = getattr(ask, "spent_unanswered", None)
        raise ResidualPartFailed(page.page_id, failed_part, typing.outcome.cause, key,
                                 spent=key is not None and spent_fn is not None and spent_fn(key))
    save_source_typing(path, typing)
    return typing


def _residual_part_key(ask: Any, asked: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
                       chunks: Sequence[Any], part_id: str) -> str | None:
    """PI ruling 120 c: the journal key of the residual ``source_type`` request sent for part ``part_id``.

    The residual set has one question in one round, so each of the page's T-021 parts (``chunks``, the given
    layout, never halved: review M2) gets exactly one request; it is the one ``asked`` whose state is that
    part (``page_part`` ``"<index> of <n>"`` and its ``page_text``). The key is the journaled ``ask``'s
    (:meth:`~g3o.run.presweep.stage_validate_v27.RequestJournal.ask`, ``request_key``): the same request on
    every run (the same T-021 parts, setup and question), so a release names it stably. None when ``ask`` is not
    journaled (no ``request_key``) or no single request matches."""
    key_of = getattr(ask, "request_key", None)
    index = next((i for i, c in enumerate(chunks, start=1) if c.chunk_id == part_id), None)
    if key_of is None or index is None:
        return None
    text, part = chunks[index - 1].text, f"{index} of {len(chunks)}"
    keys = {key_of(state, questions) for state, questions in asked
            if state.get("page_part") == part and state.get("page_text") == text}
    return next(iter(keys)) if len(keys) == 1 else None


def followed_archive_address(page: Any) -> bool:
    """PI ruling 112 a: the A2 archive-address test of a followed page at coding time, from its URL. The same
    test on the same input as the page fields the follow leg builds later
    (``perpage_inputs_v27.page_source_fields``: :func:`~g3o.common.source_fields.source_archive_address` of
    ``RenderedPage.url``, which equals the followed ``PageInput.url``: ``rendered_page_input`` copies it and
    ``follow_v27`` refuses a fetched page whose URL is not the URL tried), so the two values are equal."""
    return sf.source_archive_address(page.url)


def save_source_typing(path: Path, typing: Any) -> None:
    """Write the page's residual ``source_type`` answers (its stored residual result) to ``path`` (PI ruling
    105 b; :data:`SOURCE_TYPE_FILE`)."""
    if typing.typed_by != "classifier" or typing.result is None:
        raise TypeError("only a classifier-typed (residual) source_type is saved")
    if srow.residual_deciding_part_failed(typing) is not None:
        raise TypeError("a residual source_type whose deciding part failed with no answer is never saved (PI "
                        "ruling 110 b)")
    _atomic_write(path, canonical_json({"format": CHECKPOINT_FORMAT, "kind": "source_type",
                                        "result": typing.result.to_dict()}))


def load_source_typing(path: Path, layout: Sequence[Any]) -> Any:
    """The residual ``source_type`` answers saved at ``path`` (:func:`save_source_typing`), rebuilt with
    :func:`~g3o.common.source_fields.classifier_source_typing` (equal to the typing that was saved), or None
    when there is no such file. A file of another format, or asked on parts other than ``layout`` (the page's
    T-021 parts), is refused (:class:`MalformedCheckpoint`, a ``ValueError`` and a stage stop: PI ruling
    118 b)."""
    if not path.exists():
        return None
    doc = _read_checkpoint(path, "source_type")
    typing = _decode_checkpoint(path, lambda: sf.classifier_source_typing(PageCodeResult.from_dict(doc["result"])))
    if [c.chunk_id for c in typing.result.chunks] != [c.chunk_id for c in layout]:
        raise MalformedCheckpoint(f"per-page checkpoint {path} was asked on parts other than the page's T-021 parts")
    if srow.residual_deciding_part_failed(typing) is not None:  # never saved since PI ruling 110 b
        # review L-1: only code before PI ruling 110 b wrote such a file; the stage stops (PI ruling 118 b) and the
        # message tells the operator how to clear it
        raise MalformedCheckpoint(f"per-page checkpoint {path} holds residual answers whose deciding part failed "
                                  "with no answer (PI ruling 110 b: such answers are never saved; this file was "
                                  "written by code before that ruling). To clear it, move this file by hand into "
                                  "an archive folder (never delete it) and run the stage again: the next run asks "
                                  "the residual source_type question again (answered parts replayed from the "
                                  "journal)")
    return typing


def _record_pass1_requests(pdir: Path, extraction: Any, activity_extraction: Any) -> bool:
    """PI ruling 105 b: record the pass-1 requests built for the page (:data:`PASS1_FILE`): the T-022 page
    request's ``custom_id`` and the 87 c activity-only request's (None when not built). Written only when it
    changes; returns whether it was written.

    PI ruling 118 b: an existing malformed record is never silently overwritten: it raises
    :class:`MalformedCheckpoint` (a stage stop), as :func:`read_pass1_requests` does."""
    path = pdir / PASS1_FILE
    text = canonical_json({"format": CHECKPOINT_FORMAT, "kind": "pass1_requests",
                           "page_request": getattr(extraction, "custom_id", None),
                           "activity_only": getattr(activity_extraction, "custom_id", None)})
    if path.exists():
        _read_checkpoint(path, "pass1_requests")  # refuses a malformed record (PI ruling 118 b)
        if path.read_bytes().decode("utf-8") == text:
            return False
    _atomic_write(path, text)
    return True


def read_pass1_requests(run_dir: Path, page: Any) -> dict[str, Any] | None:
    """The page's :data:`PASS1_FILE` record (:func:`_record_pass1_requests`), or None when no process wrote it.

    A record of another kind or format raises :class:`MalformedCheckpoint` (a ``ValueError``) and bytes that
    are not JSON raise :class:`MalformedCheckpointJSON` (a ``json.JSONDecodeError`` too), as
    :meth:`Checkpoint.load` does for page.json / activity.json. Both are stage stops (:data:`STAGE_STOPS`), on a
    searched and on a followed page (PI ruling 118 b). The same holds for :func:`load_source_typing`."""
    path = page_state_dir(run_dir, page) / PASS1_FILE
    if not path.exists():
        return None
    return _read_checkpoint(path, "pass1_requests")


def _rounds_for_page(run_dir: Path, st: _PageState, ask: Any, providers: PerPageProviders,
                     page_config: PageCoderConfig, activity_config: ActivityCoderConfig,
                     metrics: PerPageMetrics, official_sites: Any = None) -> None:
    page = st.spec.page
    pdir = _page_dir(run_dir, page)
    # ruling 33 a: an archive left incomplete (its marker is still here) is finished before any
    # state is loaded; PageArchiveIncomplete holds the institution again
    if (pdir / PAGE_ARCHIVE_PENDING).exists():
        _archive_page_state(run_dir, page)
    # PI ruling 95 a: the residual source_type question runs before T-022 (the page's first pass-1 request)
    try:
        st.source_typing = _residual_source_type(run_dir, st.spec, ask, page_config, official_sites)
    except RowValueRefused as exc:  # review M2: the page's own data; held where 97 b holds are (PI ruling 106 a)
        st.source_typing, st.row_refusal = None, exc
    except ResidualPartFailed as exc:  # PI ruling 110 b: held before the first pass-1 request is built
        st.holds.append(exc.hold())
        return
    if st.source_typing is not None:
        set_typing = getattr(providers, "set_source_typing", None)
        if set_typing is None:
            raise TypeError(f"page {page.page_id}: the per-page providers take no residual source_type "
                            "(set_source_typing; PI ruling 95 a): a wiring error, the stage stops")
        set_typing(page.page_id, st.source_typing)
    # PI ruling 121 b: a released pass-1 page request re-ask archives page.json (with the activity-level state)
    # BEFORE it is loaded, so this run's page rounds check the support on the new response's quotes (absent on fakes)
    prepare_reask = getattr(providers, "prepare_pass1_reask", None)
    if prepare_reask is not None:
        prepare_reask(page)
    page_ckpt = Checkpoint(pdir / "page.json", "page")
    saved = page_ckpt.load()
    if saved is None:
        result = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(
            run_dir, page.institution_id, page.url)))
        support: tuple[SupportResult, ...] = ()
    else:
        result, support = saved
    st.page_round = complete_page_rounds(
        page, result, support, ask_fn=ask, config=page_config,
        check_support=lambda r, recs: providers.page_support(page, r, recs), checkpoint=page_ckpt.save,
        reask_fn=_reask_seam(ask))
    metrics.checkpoint_writes += page_ckpt.writes
    if st.page_round.failed:  # ruling 69 b: failed after halving in an extra round, as a T-021 failure
        failure = st.page_round.failure
        attrition.record(run_dir, institution_id=page.institution_id, stage=STAGE, reason=failure["reason"],
                         url=page.url, detail=failure["detail"])
        st.failure = failure["reason"]
        metrics.failed_pages.append(page.page_id)
        return
    if not st.page_round.complete:
        st.holds.append({"page_id": page.page_id, "stage": "page_rounds", "items": sorted(
            k for k, o in st.page_round.final.items.items() if o.state in ("pending", "stopped"))})
        return
    inp = providers.activity_input(page, st.page_round)
    st.activity_input = inp
    verdict_downgrade = getattr(providers, "verdict_downgrade", None)  # PI ruling 99.1 a / 99.2 (absent on fakes)
    reason = None if verdict_downgrade is None else verdict_downgrade(page.page_id)
    if reason is not None:
        if inp is not None:
            raise TypeError(f"page {page.page_id}: a verdict downgrade ({reason}) with activity spans (wiring error)")
        st.page_round = downgrade_verdict_support(page, st.page_round)
        metrics.verdict_downgrades[page.page_id] = reason
    page_extraction = getattr(providers, "page_extraction", None)  # absent on test fakes: None (refused)
    st.extraction = None if page_extraction is None else page_extraction(page.page_id)
    activity_extraction = getattr(providers, "activity_extraction", None)  # PI ruling 87 c (absent on fakes)
    st.activity_extraction = None if activity_extraction is None else activity_extraction(page.page_id)
    if page_extraction is not None and _record_pass1_requests(pdir, st.extraction, st.activity_extraction):
        metrics.checkpoint_writes += 1  # PI ruling 105 b: a later process's rebuild of these is a resume
    if st.source_typing is not None:  # PI ruling 95 a: checked on the first request's quotes (or none)
        st.source_type_codes = providers.source_type_codes(page.page_id)
    if inp is None:
        return
    act_ckpt = Checkpoint(pdir / "activity.json", "activity")
    saved_act = act_ckpt.load()
    if saved_act is None:
        art = stage_activity_code.artifact_path(institution_dir(run_dir, page.institution_id) / ACTIVITY_DIR,
                                                page.page_id)
        if artifact_exists(art):  # coded, then interrupted before the first checkpoint
            act_result = PageActivityResult.from_json(read_artifact(art))
        else:
            act_result = stage_activity_code.run_stage([inp], ask, activity_config, out_dir=art.parent,
                                                       run_dir=run_dir).results[0]
        act_ckpt.save(act_result, ())
        act_support: tuple[SupportResult, ...] = ()
    else:
        act_result, act_support = saved_act
    st.activity_round = complete_activity_rounds(
        inp, act_result, act_support, ask_fn=ask, config=activity_config,
        check_support=lambda r, recs: providers.activity_support(inp, r, recs), checkpoint=act_ckpt.save)
    metrics.checkpoint_writes += act_ckpt.writes
    if not st.activity_round.complete:
        st.holds.append({"page_id": page.page_id, "stage": "activity_rounds", "items": sorted(
            f"{a.activity_id}:{q}" for a in st.activity_round.final for q, o in a.outcomes.items()
            if o.state in ("pending", "stopped"))})
        return
    # PI ruling 73.1 b: the page's pass-2 page request, whose field tasks hold the open reported_* lists
    # (absent on test fakes: None, and an open gate is refused by the assembler).
    page_pass2 = getattr(providers, "page_pass2", None)
    st.pass2 = None if page_pass2 is None else page_pass2(inp)
    result_now = st.activity_round.result
    if result_now.pairs:
        pair_path = pdir / PAIRS_FILE
        if pair_path.exists():
            doc = _read_checkpoint(pair_path, "pairs")  # PI ruling 118 b: malformed: a stage stop
            st.pair_support = _decode_checkpoint(pair_path,
                                                 lambda: tuple(support_from_dict(s) for s in doc["support"]))
        else:
            st.pair_support = tuple(providers.pair_support(inp, result_now))
            _atomic_write(pair_path, canonical_json({"format": CHECKPOINT_FORMAT, "kind": "pairs",
                                                     "support": [support_to_dict(s) for s in st.pair_support]}))
            metrics.checkpoint_writes += 1
        st.pairs = finalize_pairs(result_now, st.pair_support, activity_config)


def _code_states(run_dir: Path, to_code: Sequence[_PageState], broken: dict[str, Any] | None, *, ask: Any,
                 providers: PerPageProviders, inst_providers: PerPageProviders, journal: RequestJournal,
                 page_config: PageCoderConfig, activity_config: ActivityCoderConfig, metrics: PerPageMetrics,
                 cost_check_callback: Callable[[str, dict[str, int]], bool] | None,
                 official_sites: Any = None) -> dict[str, Any] | None:
    """T-021 coding and the rounds of ``to_code`` (one institution); returns the institution's hold, if any.

    ``official_sites``: the run's official sites, read by the residual ``source_type`` step (PI ruling 95 a).

    ``broken`` is returned unchanged unless a page sets a hold (the caller passes
    ``to_code`` empty when it already holds the institution).
    """
    coded = stage_page_code.run_page_code_stage(run_dir, [s.spec.page for s in to_code], ask_fn=ask,
                                                config=page_config, concurrency=1,
                                                cost_check_callback=cost_check_callback)
    if coded.stopped_early:  # the cost check stopped T-021: uncoded pages are not failures
        raise stage_page_code.StageStopped("page coding stopped by the cost check")
    deferred: list[dict[str, Any]] = []  # PI ruling 134: pages whose extractor request waits for a batch
    for st in to_code:
        page = st.spec.page
        if not artifact_exists(stage_page_code.artifact_path(run_dir, page.institution_id, page.url)):
            try:
                st.failure = _failure_reason(run_dir, page)
            except STAGE_STOPS:
                raise
            except (ConsolidationError, ValueError, RuntimeError) as exc:
                return _producer_hold(page.page_id, exc)
            metrics.failed_pages.append(page.page_id)
            continue
        try:
            _rounds_for_page(run_dir, st, ask, inst_providers, page_config, activity_config, metrics,
                             official_sites=official_sites)
        except PageArchiveIncomplete as exc:  # finishing an earlier archive failed again
            return _archive_hold(page.page_id, exc)
        except ExtractRejectCapReached as exc:  # ruling 34 b / 41 a: no call was made
            return _cap_hold(page.page_id, exc.pass_name, exc.custom_id, exc.key, exc.rejections,
                             "no extractor call made")
        except Pass2RequestNotJournaled as exc:  # PI ruling 98 b: no call was made
            return {"page_id": exc.page_id, "stage": PASS2_NOT_JOURNALED, "pass": "pass2",
                    "custom_id": exc.custom_id, "request_key": exc.key, "error": str(exc)}
        except Pass1RequestNotJournaled as exc:  # PI ruling 105 b: no call was made
            return {"page_id": exc.page_id, "stage": exc.stage, "pass": "pass1",
                    "custom_id": exc.custom_id, "request_key": exc.key, "error": str(exc)}
        except BatchDeferred as exc:  # PI ruling 134: the request waits for a Message Batch; no call was made
            # the institution's other pages go on in this wave (their requests join the same batch); the
            # institution is held below once every page has had its turn
            deferred.append({"page_id": page.page_id, "custom_id": exc.custom_id, "batch_state": exc.state,
                             "error": str(exc)})
            continue
        except ExtractorResponseFailed as exc:  # C3 a: this institution is held as pending
            broken = _response_hold(page.page_id, exc)
            if exc.request is not None and hasattr(providers, "journal_prompt"):
                # never replayed as final: the next run asks the request again
                journal.reject_extract(exc.request, providers.journal_prompt, exc.detail)
                key = journal.extract_key(exc.request, providers.journal_prompt)
                if journal.rejections(key) >= EXTRACT_REJECT_CAP:  # ruling 34 b / 41 a
                    broken = _cap_hold(page.page_id, exc.pass_name, broken["custom_id"], key,
                                       journal.rejections(key), exc.detail)
                elif journal.reask_spent_unanswered(key, kind="extract"):  # review L-1: not asked again
                    broken = _response_hold(page.page_id, exc, spent_key=key)
            if exc.archive_page_state:  # ruling 33 a: the next run codes the page again
                try:
                    broken["archived"] = _archive_page_state(run_dir, page)
                except PageArchiveIncomplete as aexc:  # ruling 28 a: held, never a crash
                    broken.update(_archive_detail(aexc))
            return broken
    if deferred and broken is None:  # PI ruling 134: held until the batch answers (the first page names it)
        return {**deferred[0], "stage": BATCH_PENDING, "deferred_pages": [d["page_id"] for d in deferred]}
    return broken


def _first_complete(run_dir: Path, page: PageInput) -> str | None:
    """The combined ``core.page_complete`` the page's first pass-1 request was built on: its stored T-021
    result, as ``jev_page_code.to_pass1_page`` reads it (PI ruling 82 c)."""
    first = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(run_dir, page.institution_id,
                                                                                 page.url)))
    complete = first.page_complete
    return complete.value if complete is not None and complete.state == "combined" else None


def _follow_rounds(run_dir: Path, inst: PerPageInstitution, states: list[_PageState], follow: Any,
                   held_path: Path, unread: list[dict[str, Any]], **code: Any) -> dict[str, Any] | None:
    """The T-025 follow leg of one institution (RC-D-023 C-1 a), after its searched pages are coded.

    Each round follows the links of the last round's coded pages
    (:meth:`g3o.run.presweep.follow_v27.InstitutionLeg.round`); the pages it fetched
    are appended to ``states`` and coded like searched pages (their own T-021 pass
    and extractor call, the same request journal). A round stops the leg when a
    page holds the institution; the next run resumes from the follow state and the
    journal. Once no round fetches a page, the specs get their follow page fields
    (:meth:`~g3o.run.presweep.follow_v27.InstitutionLeg.finish`), and each URL
    tried and not fetched, or link not followed, is appended to ``unread`` (PI
    rulings 79 b / 96 a / 102 a: it enters Stage 6 through
    :func:`g3o.run.presweep.follow_v27.unread_products`). Returns the hold, or None.
    """
    from g3o.run.presweep.follow_v27 import round_page

    leg = follow.start(run_dir, inst)
    current = list(states)
    while True:
        pages = [round_page(st.spec, st.page_round, st.extraction,
                            first_complete=_first_complete(run_dir, st.spec.page)) for st in current
                 if st.failure is None and st.page_round is not None]
        new_specs = leg.round(pages)
        if not new_specs:
            break
        known = {st.spec.page.page_id for st in states}
        clash = sorted(s.page.page_id for s in new_specs if s.page.page_id in known)
        if clash:
            raise FollowWiringError(f"{inst.institution_id}: followed page id(s) {clash} already coded")
        current = [_PageState(spec) for spec in new_specs]
        states.extend(current)
        broken = _finish_failed_archives(run_dir, current, held_path)  # ruling 33 a, as for searched pages
        if broken is None:
            broken = _code_states(run_dir, current, None, **code)
        if broken is not None or any(st.holds for st in current):
            return broken
    for st, spec in zip(states, leg.finish([st.spec for st in states]), strict=True):
        st.spec = spec
    unread.extend(leg.unreviewed())  # PI rulings 79 b / 96 a / 102 a
    return None


def run_perpage_v27(run_dir: Path, institutions: Iterable[PerPageInstitution], *, ask_fn: Any,
                    providers: PerPageProviders, page_config: PageCoderConfig,
                    activity_config: ActivityCoderConfig, instrument: dict[str, Any],
                    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
                    test_only_unbound_providers: bool = False,
                    follow: Any = None,
                    ) -> tuple[list[Stage6Institution], PerPageMetrics]:
    """Code, re-gate and produce every page; return the institutions ready for Stage 6.

    ``JevAccountError`` / budget stops propagate after the journal and
    checkpoints hold what finished; the next run resumes from them.

    ``providers`` must come from
    :func:`~g3o.run.presweep.perpage_providers_v27.build_perpage_providers` for this
    instrument, declaring its pinned extractor and X35 models (QA3 F3); their extractor
    and X35 calls are journaled per institution. ``test_only_unbound_providers`` lifts
    that check for offline fakes in tests only.

    ``follow`` (T-025): a :class:`g3o.run.presweep.follow_v27.FollowLeg`. Given, each
    institution's searched pages are followed after they are coded
    (:func:`_follow_rounds`); the pages fetched are coded and produced with them,
    after the searched pages (attempted order). None: no page is followed.
    """
    if page_config.setup_pointer != instrument["instrument_id"] or \
            activity_config.setup_pointer != instrument["instrument_id"]:
        raise ValueError("per-page coder configuration is bound to a different instrument")
    cfg = instrument["payload"]["extractor_configuration"]
    if not test_only_unbound_providers and not (
            getattr(providers, "bound_instrument_id", None) == instrument["instrument_id"]
            and getattr(providers, "extractor_model", None) == cfg.get("model")
            and getattr(providers, "x35_model", None) and providers.x35_model == cfg.get("x35_model")
            and hasattr(providers, "with_seams")):
        raise ValueError("per-page providers are not bound to this instrument (or their extractor / X35 model "
                         "differs from the pinned one): build them with build_perpage_providers")
    # Ruling 48.3 a / 45 a: this pass may release a held institution, so neither marker from an
    # earlier finished pass stands until this pass (and then Stage 6) finishes again.
    clear_done(run_dir, DONE_MARKER)
    clear_done(run_dir, STAGE6_DONE_MARKER)
    metrics = PerPageMetrics()
    ready: list[Stage6Institution] = []
    official_sites = load_run_official_sites(run_dir)  # PI ruling 70 b: read from the run folder every pass
    # The journal key binds the setup: a response recorded under another setup is never replayed.
    setup = {"setup_pointer": page_config.setup_pointer,
             "page": {"configured_model": page_config.configured_model, "coder_version": page_config.coder_version},
             "activity": {"configured_model": activity_config.configured_model,
                          "coder_version": activity_config.coder_version}}
    for inst in institutions:
        inst_dir = institution_dir(run_dir, inst.institution_id)
        journal = RequestJournal(inst_dir / WORK_DIR / JOURNAL, setup)
        ask = journal.ask(ask_fn)
        inst_providers = providers
        if hasattr(providers, "with_seams"):  # extractor and X35 calls journaled (usage, durable resume)
            inst_providers = providers.with_seams(*journal.seams(providers.journal_prompt))
        states = [_PageState(spec) for spec in inst.pages]
        held_path = inst_dir / WORK_DIR / HELD_FILE
        # a producer error for one page: this institution is held. First, any page-state archive the
        # last run's held.json names as failed (even before its marker was written) is finished.
        broken: dict[str, Any] | None = _finish_failed_archives(run_dir, states, held_path)
        if broken is None:  # ruling 34 b / 41 a: a PI release is recorded before any extractor call
            broken = _apply_pi_release(inst_dir, journal)
        to_code = states if broken is None else []
        unread: list[dict[str, Any]] = []  # PI rulings 79 b / 96 a / 102 a: unread follow attempts
        try:
            broken = _code_states(run_dir, to_code, broken, ask=ask, providers=providers,
                                  inst_providers=inst_providers, journal=journal, page_config=page_config,
                                  activity_config=activity_config, metrics=metrics,
                                  cost_check_callback=cost_check_callback, official_sites=official_sites)
            # Review L5: an institution with no page has nothing to follow from (not an error).
            if follow is not None and broken is None and states and not any(st.holds for st in states):
                try:
                    broken = _follow_rounds(run_dir, inst, states, follow, held_path, unread, ask=ask,
                                            providers=providers, inst_providers=inst_providers, journal=journal,
                                            page_config=page_config, activity_config=activity_config,
                                            metrics=metrics, cost_check_callback=cost_check_callback,
                                            official_sites=official_sites)
                except STAGE_STOPS:  # PI ruling 118 b: a malformed page checkpoint of a followed page too
                    raise
                except ValueError as exc:  # institution data: this institution is held
                    # Review L4: no OSError here. As on the searched-page path, an OSError holds only
                    # where ruling 28 a says so (a page-state archive that survived the write retries,
                    # held inside _code_states / _finish_failed_archives); any other leaves the stage.
                    broken = {"page_id": inst.institution_id, "stage": FOLLOW_FAILED,
                              "error": f"{type(exc).__name__}: {exc}"}
        finally:
            metrics.live_requests += journal.live
            metrics.replayed_requests += journal.replayed
            metrics.batched_requests += journal.batched  # PI ruling 134
            metrics.usage[inst.institution_id] = journal.usage()
        holds = [broken] if broken is not None else [h for st in states for h in st.holds]
        if holds:
            _atomic_write(held_path, canonical_json({"institution_id": inst.institution_id, "held": holds}))
            # PI ruling 134: waiting for a batch is not attrition (and attrition.record dedups ignoring the
            # detail, so recording it would hide the institution's real hold reason of a later pass)
            if not all(h["stage"] == BATCH_PENDING for h in holds):
                attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_REASON,
                                 detail=", ".join(_hold_label(h) for h in holds))
            metrics.held.append(inst.institution_id)
            continue
        products: list[PageProduct | ReviewedPage] = []
        next_source = 1
        uncarried: UncarriedCombinedValue | None = None
        for order, st in enumerate(states):
            try:
                if st.failure is not None:
                    products.append(failed_page(st.spec, st.failure))
                    continue
                if st.row_refusal is not None:  # review M2: refused before T-022 (PI rulings 97 b, 106 a)
                    raise st.row_refusal
                products.append(produce_page(
                    run_dir=run_dir, run_id=inst.run_id, institution_uid=inst.institution_uid, spec=st.spec,
                    page_order=order, first_source=next_source, page_round=st.page_round,
                    activity_input=st.activity_input, activity_round=st.activity_round, pairs=st.pairs,
                    pair_support=st.pair_support, page_config=page_config, activity_config=activity_config,
                    instrument=instrument, extraction=st.extraction, official_sites=official_sites,
                    pass2=st.pass2, activity_extraction=st.activity_extraction,
                    source_typing=st.source_typing, source_type_codes=st.source_type_codes))
            except UncarriedCombinedValue as exc:  # Y3 b: refused as a per-institution hold
                uncarried = exc
                break
            except RowValueRefused as exc:  # PI ruling 97 b: the page's own data: this institution only
                broken = _row_refused_hold(exc)
                break
            except STAGE_STOPS:
                raise
            except (ConsolidationError, ValueError, RuntimeError) as exc:  # this institution only
                broken = _producer_hold(st.spec.page.page_id, exc)
                break
            next_source += len(products[-1].sources)
        if unread and uncarried is None and broken is None:  # PI rulings 79 b / 96 a / 102 a
            from g3o.run.presweep.follow_v27 import unread_products
            try:
                products += unread_products(unread, run_id=inst.run_id, institution_uid=inst.institution_uid,
                                            institution_id=inst.institution_id, first_source=next_source,
                                            coder_version=page_config.coder_version, instrument=instrument,
                                            known_pages=[st.spec.page.page_id for st in states])
            except STAGE_STOPS:  # FollowWiringError / MissingUpstreamError: a wiring gap stops the stage
                raise
            except (ConsolidationError, ValueError, RuntimeError) as exc:  # review M-3: this institution only
                broken = _producer_hold(inst.institution_id, exc)
        if uncarried is None and broken is None and not any(isinstance(p, PageProduct) for p in products):
            failed_pages = [{"page_id": st.spec.page.page_id, "reason": st.failure} for st in states]
            if states and all(st.failure == HALVING_PAGE_FAILED for st in states):  # ruling 69 b: terminal
                _clear_held(run_dir, inst.institution_id, held_path)
                attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE,
                                 reason=NO_PAGE_CODED_FAILED,
                                 detail=", ".join(f"{p['page_id']}:{p['reason']}" for p in failed_pages))
                metrics.failed.append(inst.institution_id)
                continue
            broken = {"page_id": inst.institution_id, "stage": NO_PAGE_CODED, "failed_pages": failed_pages}
        if uncarried is not None or broken is not None:
            hold = broken if broken is not None else {
                "page_id": uncarried.page_id, "stage": UNCARRIED_STAGE, "items": sorted(uncarried.values)}
            _atomic_write(held_path, canonical_json({"institution_id": inst.institution_id, "held": [hold]}))
            detail = f"{hold['page_id']}:{hold['stage']}"
            if hold["stage"] == ROW_VALUE_REFUSED:  # ruling 97 b: the reason names the items refused
                detail += ":" + ",".join(hold["items"])
            attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_REASON,
                             detail=detail)
            metrics.held.append(inst.institution_id)
            continue
        _clear_held(run_dir, inst.institution_id, held_path)
        ready.append(_institution(inst, products))
        metrics.ready.append(inst.institution_id)
    # Ruling 48.3 a: the pass finished (a stage stop raised above and never gets here); held
    # institutions stay pending, and the report decides them from held.json first (ruling 45 a).
    # Marker only: the stage does not skip on it, a resume runs the pass again.
    mark_done(run_dir, DONE_MARKER, no_batch=True)
    return ready, metrics


def _clear_held(run_dir: Path, institution_id: str, held_path: Path) -> None:
    """Clear an earlier pass's hold of this institution (a ``HELD_RELEASED`` row naming it), if any."""
    if held_path.exists():
        previous = json.loads(held_path.read_bytes().decode("utf-8")).get("held", [])
        attrition.record(run_dir, institution_id=institution_id, stage=STAGE, reason=HELD_RELEASED,
                         detail=", ".join(f"{h['page_id']}:{h['stage']}" for h in previous))
        held_path.unlink()


def _producer_hold(page_id: str, exc: BaseException) -> dict[str, Any]:
    return {"page_id": page_id, "stage": PRODUCER_FAILED, "error": f"{type(exc).__name__}: {exc}"}


def _archive_detail(exc: PageArchiveIncomplete) -> dict[str, Any]:
    detail = {"archived": exc.archived, "archive_left": exc.left, "archive_error": exc.error}
    if exc.files != PAGE_STATE_FILES:  # PI ruling 113 b: the next run finishes the same (activity-level) archive
        detail["archive_files"] = list(exc.files)
    return detail


def _archive_hold(page_id: str, exc: PageArchiveIncomplete) -> dict[str, Any]:
    return {"page_id": page_id, "stage": ARCHIVE_FAILED, **_archive_detail(exc)}


def _row_refused_hold(exc: RowValueRefused) -> dict[str, Any]:
    """PI ruling 97 b: the hold of row values refused on the page's own data (names the items and each refusal)."""
    return {"page_id": exc.page_id, "stage": ROW_VALUE_REFUSED, "items": sorted(exc.refused),
            "refusals": exc.refused, "error": str(exc)}


def _hold_label(hold: Mapping[str, Any]) -> str:
    label = f"{hold['page_id']}:{hold['stage']}"
    if "archive_error" in hold and hold["stage"] != ARCHIVE_FAILED:
        label += f":{ARCHIVE_FAILED}"
    return label


def _finish_failed_archives(run_dir: Path, states: Sequence[_PageState], held_path: Path) -> dict[str, Any] | None:
    """Finish each page-state archive the last run's ``held.json`` names as failed (ruling 33 a).

    This also covers a failure before the pending marker was written, when
    nothing but ``held.json`` records that the page's state must not be used
    (its ``archive_files`` name a PI ruling 113 b activity-level archive; absent: the 33 a file set).
    Returns the hold for the first page whose archive fails again, else None.
    """
    if not held_path.exists():
        return None
    previous = json.loads(held_path.read_bytes().decode("utf-8")).get("held", [])
    failed = {h["page_id"]: tuple(h.get("archive_files") or PAGE_STATE_FILES) for h in previous
              if "archive_error" in h}
    for st in states:
        if st.spec.page.page_id in failed:
            try:
                _archive_page_state(run_dir, st.spec.page, failed[st.spec.page.page_id])
            except PageArchiveIncomplete as exc:
                return _archive_hold(st.spec.page.page_id, exc)
    return None


def _response_hold(page_id: str, exc: ExtractorResponseFailed, spent_key: str | None = None) -> dict[str, Any]:
    """C3 a: the hold of a failed or unparsable extractor response (asked again on the next run).

    Review L-1: ``spent_key`` is the request key when that response answered a PI-released re-ask the journal now
    reports as spent with no answer (:meth:`~g3o.run.presweep.stage_validate_v27.RequestJournal.
    reask_spent_unanswered`): the next run does NOT ask it again (the journal refuses the live call, PI ruling
    114 b), so the hold names the key and says a new release is needed (PI ruling 122 b accepts it)."""
    request = exc.request or {}
    hold = {"page_id": page_id, "stage": EXTRACT_RESPONSE_FAILED, "pass": exc.pass_name,
            "custom_id": request.get("custom_id"), "error": exc.detail}
    if spent_key is not None:
        hold["request_key"] = spent_key
        hold["error"] = (f"{exc.detail} (review L-1: this response answered a PI-released re-ask, used up by its "
                         "reask_spent journal entry (PI ruling 114 b), so the next run does not ask the request "
                         f"again; a new {PI_RELEASE_FILE}, with other bytes, naming request key {spent_key} "
                         f"authorises one more re-ask: PI ruling 122 b{_NAME_KEY_NOTE})")
    return hold


def _cap_hold(page_id: str, pass_name: str | None, custom_id: Any, key: str, rejections: int,
              detail: str) -> dict[str, Any]:
    """Ruling 34 b / 41 a: the permanent hold of a request rejected :data:`EXTRACT_REJECT_CAP` times."""
    return {"page_id": page_id, "stage": EXTRACT_REJECTED_CAP, "pass": pass_name, "custom_id": custom_id,
            "request_key": key, "rejections": rejections,
            "error": f"extractor request rejected {rejections} times (cap {EXTRACT_REJECT_CAP}): permanent hold "
                     f"until the PI releases it with {PI_RELEASE_FILE} in the institution folder; a release "
                     f"file byte-identical to an already recorded release is ignored (only archived, not "
                     f"re-applied: ruling 47.2 a) ({detail})"}


def _release_hold(stage: str, path: Path, detail: str) -> dict[str, Any]:
    return {"page_id": PI_RELEASE_FILE, "stage": stage, "path": path.name, "error": detail}


def read_pi_release(path: Path) -> dict[str, Any]:
    """Read and check a PI release file (:func:`parse_pi_release`); ``OSError`` if it cannot be read."""
    return parse_pi_release(path.read_bytes())


def parse_pi_release(raw: bytes) -> dict[str, Any]:
    """Parse and check a PI release file's bytes (ruling 34 b / 41 a); raise ``ValueError`` naming the defect.

    Format (UTF-8 JSON object; no other fields)::

        {"released_by": "<name>", "date": "YYYY-MM-DD",
         "keys": ["<64-hex request key>", ...]}        # or "all": true instead of "keys"
         (optional "note": "<text>")

    Exactly one of ``keys`` (a non-empty list of journal request keys, as
    ``held.json`` names them in ``request_key``) or ``all`` (``true``: every key)
    must be given. ``date`` must match ``YYYY-MM-DD`` exactly and be a real date.
    """
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"not UTF-8 JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise ValueError("not a JSON object")
    unknown = sorted(set(doc) - _PI_RELEASE_FIELDS)
    if unknown:
        raise ValueError(f"unknown field(s) {unknown}; allowed: {sorted(_PI_RELEASE_FIELDS)}")
    by = doc.get("released_by")
    if not isinstance(by, str) or not by.strip():
        raise ValueError("released_by must be a non-empty string")
    when = doc.get("date")
    try:
        if not isinstance(when, str) or not _PI_RELEASE_DATE.fullmatch(when):
            raise TypeError
        iso_date.fromisoformat(when)
    except (TypeError, ValueError):
        raise ValueError("date must be an ISO date string (YYYY-MM-DD)") from None
    if "note" in doc and not isinstance(doc["note"], str):
        raise ValueError("note must be a string")
    has_keys, has_all = "keys" in doc, "all" in doc
    if has_keys == has_all:
        raise ValueError('give exactly one of "keys" (a list of request keys) or "all": true')
    if has_all:
        if doc["all"] is not True:
            raise ValueError('"all" must be true')
        keys = None
    else:
        keys = doc["keys"]
        if (not isinstance(keys, list) or not keys
                or not all(isinstance(k, str) and len(k) == 64 and all(c in "0123456789abcdef" for c in k)
                           for k in keys)):
            raise ValueError('"keys" must be a non-empty list of 64-character lowercase hex request keys')
        keys = sorted(set(keys))
    return {"keys": keys, "all": has_all, "released_by": by, "date": when}


#: PI ruling 104 b: the hold stages whose ``request_key`` a ``pi_release.json`` key may name for one live
#: re-ask; PI ruling 113 b adds the 105 b pass-1 and activity-only holds (their page's activity-level state is
#: archived before that call, :func:`archive_activity_state`). PI ruling 120 c adds the 110 b residual-part hold
#: (:data:`RESIDUAL_PART_FAILED`): its ``request_key`` is the deciding part's jev request, and the journaled jev
#: call makes that one re-ask live instead of replaying the response that has no answer. Only a key a hold of
#: these stages names in ``held.json`` is releasable (or, PI ruling 122 b, one already released and spent with no
#: answer). PI ruling 103 b: a 97 b page-data hold (:data:`ROW_VALUE_REFUSED`) is never releasable this way.
REASK_RELEASABLE = frozenset({PASS2_NOT_JOURNALED, PASS1_NOT_JOURNALED, ACTIVITY_ONLY_NOT_JOURNALED,
                              RESIDUAL_PART_FAILED})


def _reaskable_keys(inst_dir: Path) -> frozenset[str]:
    """The request keys the last run's ``held.json`` holds under :data:`REASK_RELEASABLE` (PI ruling 104 b).

    An absent or unreadable ``held.json`` gives none, so a release naming such a key is refused.

    Review L-d: when a page broke the institution (one institution-wide hold, e.g. another page's 98 b / 105 b
    hold, a failed extractor response or an incomplete page-state archive), ``held.json`` lists only that hold,
    not the per-page holds of
    the institution's other pages (such as a 110 b residual-part hold, which is kept per page). Their keys are
    then not here, and a release naming one is refused (unless the journal reports it as a spent re-ask with no
    answer, PI ruling 122 b) until a run without that institution-wide hold lists them again."""
    try:
        doc = json.loads((inst_dir / WORK_DIR / HELD_FILE).read_bytes().decode("utf-8"))
        holds = doc.get("held", []) if isinstance(doc, dict) else []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return frozenset()
    return frozenset(h["request_key"] for h in holds if isinstance(h, dict) and h.get("stage") in REASK_RELEASABLE
                     and isinstance(h.get("request_key"), str))


def _apply_pi_release(inst_dir: Path, journal: RequestJournal) -> dict[str, Any] | None:
    """Consume ``<inst>/pi_release.json`` if present (ruling 34 b / 41 a); a hold dict when it cannot be.

    PI ruling 104 b: a key the release names may also be the ``request_key`` of a 98 b hold, or (PI ruling
    113 b) of a 105 b pass-1 / activity-only hold, or (PI ruling 120 c) the jev ``request_key`` of a 110 b
    residual-part hold (:data:`REASK_RELEASABLE`), in the last run's ``held.json``;
    it is recorded in the release's ``reask_keys`` and authorises ONE live re-ask of that request
    (:meth:`~g3o.run.presweep.stage_validate_v27.RequestJournal.reask_authorised`), used up by the
    ``reask_spent`` journal entry written just before that call (PI ruling 114 b: a failure before or while
    sending wastes it); a second re-ask needs a new release file. ``all`` authorises no re-ask. PI ruling
    122 b: a key the journal reports as a spent re-ask with no answer
    (:meth:`~g3o.run.presweep.stage_validate_v27.RequestJournal.reask_spent_unanswered`) is re-askable the same
    way, whatever ``held.json`` shows (an ``extract_failed`` or rejected re-ask leaves an
    ``extract_response_failed`` hold): only a key already released and spent can match, and the release still
    authorises exactly one live call. A key that is neither rejected nor so held nor so spent is refused
    (:data:`PI_RELEASE_MALFORMED`); PI ruling 103 b: a 97 b page-data hold carries no request key and stays
    unreleasable. PI ruling 125 a: a re-ask needs its key named in ``keys``; a release naming ``all`` authorises
    no re-ask (it resets the 41 a rejection counts only), as every hold that offers a key says.

    Review L-d: the held keys are read from the last run's ``held.json`` (:func:`_reaskable_keys`), which lists
    only the institution-wide hold when another page of the same institution broke it; a release naming a key of
    a page held behind that hold (e.g. a 110 b residual-part key) is then refused, and stays refused until that
    other page's hold clears and a run lists the key again. While an earlier page-state archive is still broken
    (:func:`_finish_failed_archives` holds the institution), the release file is not read at all: it stays in
    place and is applied on the first run that gets past that hold.

    The file's bytes are read once; the same bytes are parsed and hashed. A valid
    file is recorded in the per-page journal (:meth:`RequestJournal.record_release`,
    unless a release with the same bytes is already there: then it is only archived,
    ruling 47.2 a) and then moved to ``<inst>/archive/pi_release/<NNN>/pi_release.json``
    (never deleted, so it is not re-applied). A malformed file, or one naming a key
    with no ``extract_rejected`` entry counted in the journal, holds the institution
    (:data:`PI_RELEASE_MALFORMED`) and stays in place; an ``OSError`` writing the
    journal entry holds it (:data:`PI_RELEASE_RECORD_FAILED`, ruling 28 a) and the file
    stays in place; a move that fails after the write retries holds it
    (:data:`PI_RELEASE_ARCHIVE_FAILED`, ruling 28 a) with the release already recorded
    and no empty ``<NNN>`` folder left behind.
    """
    path = inst_dir / PI_RELEASE_FILE
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return _release_hold(PI_RELEASE_MALFORMED, path, f"unreadable: {type(exc).__name__}: {exc}")
    try:
        release = parse_pi_release(raw)
    except ValueError as exc:
        return _release_hold(PI_RELEASE_MALFORMED, path, f"refused (ruling 34 b / 41 a release format): {exc}")
    sha = hashlib.sha256(raw).hexdigest()
    if not journal.release_applied(sha):
        reaskable = _reaskable_keys(inst_dir)  # ruling 104 b: request keys held under 98 b
        # PI ruling 122 b: a key whose released re-ask was spent with no answer is re-askable too, whatever
        # held.json says (after an extract_failed / rejected re-ask it shows extract_response_failed)
        unrejected = [k for k in release["keys"] or () if journal.rejections(k) == 0 and k not in reaskable
                      and not journal.reask_spent_unanswered(k) and journal.x35_failures(k) == 0]
        if unrejected:
            return _release_hold(PI_RELEASE_MALFORMED, path,
                                 f"refused (ruling 34 b / 41 a / 104 b / 113 b / 122 b): key(s) with no "
                                 f"extract_rejected entry counted in this journal since their last release, no "
                                 f"{' / '.join(sorted(REASK_RELEASABLE))} hold in {HELD_FILE} and no spent re-ask "
                                 f"left unanswered: {unrejected}; drop these keys from {PI_RELEASE_FILE} and run "
                                 f"again (review L-d: when another page of this institution broke it, {HELD_FILE} "
                                 "lists only that hold, so a key held on another page is not listed and is "
                                 "refused until that hold clears)")
        reask = sorted(k for k in release["keys"] or () if k in reaskable or journal.reask_spent_unanswered(k))
        try:
            journal.record_release({**release, "file_sha256": sha, "reask_keys": reask})
        except OSError as exc:
            return _release_hold(PI_RELEASE_RECORD_FAILED, path,
                                 f"release not recorded, journal write failed: {type(exc).__name__}: {exc}")
    root = inst_dir / PAGE_ARCHIVE_DIR / PI_RELEASE_ARCHIVE
    dest: Path | None = None
    try:
        taken = {p.name for p in root.iterdir()} if root.is_dir() else set()
        n = 1
        while f"{n:03d}" in taken:
            n += 1
        dest = root / f"{n:03d}"
        dest.mkdir(parents=True)
        replace_with_retry(path, dest / PI_RELEASE_FILE)
    except OSError as exc:
        if dest is not None and dest.is_dir() and not any(dest.iterdir()):
            try:
                dest.rmdir()  # no empty <NNN> folder left behind by a failed move
            except OSError:
                pass
        return _release_hold(PI_RELEASE_ARCHIVE_FAILED, path,
                             f"release recorded, move to archive failed: {type(exc).__name__}: {exc}")
    return None


def _institution(inst: PerPageInstitution, products: Sequence[PageProduct | ReviewedPage]) -> Stage6Institution:
    pages, observations, records, within, quotes, provenance = [], [], [], [], [], []
    inputs: dict[str, ObservationInput] = {}
    sources: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, PageArtifact] = {}
    for p in products:
        if isinstance(p, ReviewedPage):
            pages.append(p)
            continue
        pages.append(p.page)
        observations += p.observations
        records += p.records
        within += p.within
        quotes += p.quotes
        provenance += p.provenance
        inputs.update(p.observation_inputs)
        sources.update(p.sources)
        artifacts.update(p.artifacts)
    up = inst.upstream
    return Stage6Institution(inst.run_id, inst.institution_uid, inst.institution, inst.country, pages,
                             observations, records, within, quotes, inputs, sources, artifacts, provenance,
                             independence_groups=up.independence_groups, merged_values=up.merged_values)


__all__ = [
    "EXTRACT_RESPONSE_FAILED", "ExtractorResponseFailed", "HELD_REASON", "HELD_RELEASED", "NO_ACTIVITY", "NO_PAGE_CODED", "NO_PAGE_CODED_FAILED", "PRODUCER_FAILED", "STAGE_STOPS",
    "ROW_VALUE_REFUSED", "RowValueRefused", "quote_stage_as_of", "PASS2_NOT_JOURNALED", "Pass2RequestNotJournaled", "UNCARRIED_STAGE", "UncarriedCombinedValue", "InstitutionUpstream", "PageSpec", "PageUpstream", "PerPageInstitution", "PerPageMetrics",
    "FOLLOW_FAILED", "FollowWiringError", "ARCHIVE_FAILED", "PAGE_ARCHIVE_DIR", "PAGE_ARCHIVE_PENDING", "PAGE_STATE_FILES", "PageArchiveIncomplete",
    "ACTIVITY_STATE_FILES", "archive_activity_state", "PAGE_REQUEST_STATE_FILES", "archive_page_request_state",
    "record_pass1_reask", "MalformedCheckpoint", "MalformedCheckpointJSON",
    "PerPageProviders", "failed_page", "observation_id", "observation_supported", "produce_page",
    "run_perpage_v27", "source_id", "support_from_dict", "support_to_dict", "within_page_decision",
]
