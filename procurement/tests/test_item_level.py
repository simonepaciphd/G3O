"""Item-level text/money rules (R1-R5, R8) and the insufficient-text guard.

Shapes are taken from the real ARCE payloads: no award.value, prices only on
awards[].items[].unit.value, tender items unpriced.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.core.classify import INSUFFICIENT_TEXT_FLAG, NLPClassifier, needs_review
from pipeline.core.models import RawRecord
from pipeline.core.search import load_queries
from pipeline.core.standardize import (
    DESCRIPTION_FROM_ITEMS_FLAG, VALUE_CURRENCY_MISSING_FLAG, VALUE_FROM_ITEMS_FLAG,
    VALUE_MIXED_CURRENCY_FLAG, VALUE_PARTIAL_FLAG, extract_ocds)

ROOT = Path(__file__).parents[1]
QUERIES = load_queries(str(ROOT / "config" / "genai_queries.yaml"))


def _item(desc, qty, amount=None, currency="UYU"):
    item = {"id": "1-1", "description": desc, "classification": {"id": "1", "description": desc},
            "quantity": qty, "unit": {"name": "UNIDAD", "id": "22"}}
    if amount is not None:
        item["unit"]["value"] = {"amount": amount, "currency": currency}
    return item


def _release(awards=None, tender=None):
    rel = {"ocid": "ocds-test-1", "id": "adjudicacion-1", "tag": ["award"] if awards else ["tender"],
           "buyer": {"name": "Intendencia de Prueba"}}
    if awards is not None:
        rel["awards"] = awards
    if tender is not None:
        rel["tender"] = tender
    return RawRecord(source_id="t", native_id=rel["id"], payload={"releases": [rel]},
                     fetched_at="2026-10-09T00:00:00Z", raw_payload_ref="t.json")


def test_award_items_supply_description_and_summed_value():
    rows = extract_ocds(_release(awards=[{"id": "a1", "items": [
        _item("CARRO DE LIMPIEZA", 5, 4400.0), _item("GUANTES", 2, 100.0)]}]))
    (row,) = rows
    assert row["description"] == "CARRO DE LIMPIEZA; GUANTES"
    assert row["value_amount"] == 22200.0 and row["value_currency"] == "UYU"
    assert row["value_is_estimated"] is False and row["value_covers"] == "single_award"
    assert {DESCRIPTION_FROM_ITEMS_FLAG, VALUE_FROM_ITEMS_FLAG} <= set(row["extraction_flags"])


def test_award_value_wins_over_items_and_top_level_text_is_untouched():
    rows = extract_ocds(_release(
        awards=[{"id": "a1", "value": {"amount": 10, "currency": "USD"},
                 "items": [_item("X", 1, 999.0)]}],
        tender={"title": "Licencia ChatGPT", "description": "Suscripcion"}))
    (row,) = rows
    assert (row["value_amount"], row["value_currency"]) == (10, "USD")
    assert row["title"] == "Licencia ChatGPT" and row["description"] == "Suscripcion"
    assert "extraction_flags" not in row


def test_unpriced_lines_give_a_partial_total_never_an_imputed_one():
    (row,) = extract_ocds(_release(awards=[{"id": "a1", "items": [
        _item("A", 3, 10.0), _item("B", 4)]}]))
    assert row["value_amount"] == 30.0
    assert VALUE_PARTIAL_FLAG in row["extraction_flags"]


def test_mixed_currencies_are_never_summed():
    (row,) = extract_ocds(_release(awards=[{"id": "a1", "items": [
        _item("A", 1, 10.0, "UYU"), _item("B", 1, 5.0, "USD")]}]))
    assert "value_amount" not in row
    assert VALUE_MIXED_CURRENCY_FLAG in row["extraction_flags"]


def test_missing_currency_gives_no_amount():
    (row,) = extract_ocds(_release(awards=[{"id": "a1", "items": [_item("A", 1, 10.0, None)]}]))
    assert "value_amount" not in row
    assert VALUE_CURRENCY_MISSING_FLAG in row["extraction_flags"]


def test_each_award_sums_only_its_own_lines():
    rows = extract_ocds(_release(awards=[
        {"id": "a1", "items": [_item("A", 1, 10.0, "UYU")]},
        {"id": "a2", "items": [_item("B", 2, 5.0, "USD")]}]))
    assert [(r["value_amount"], r["value_currency"]) for r in rows] == [(10.0, "UYU"), (10.0, "USD")]


def test_tender_items_give_text_but_never_money():
    (row,) = extract_ocds(_release(tender={"id": "t1", "items": [_item("VENDA COHESIVA", 1500, 27.0)]}))
    assert row["description"] == "VENDA COHESIVA"
    assert "value_amount" not in row


def test_no_text_anywhere_is_not_assessable_not_negative_evidence():
    clf = NLPClassifier(QUERIES).classify({"buyer_name": "Intendencia de Prueba"})
    assert clf.relevance == "not_assessable" and clf.genai_evidence_type is None
    assert INSUFFICIENT_TEXT_FLAG in clf.review_flags and not needs_review(clf.review_flags)


def test_text_without_a_match_is_still_absence():
    clf = NLPClassifier(QUERIES).classify({"description": "CARRO DE LIMPIEZA"})
    assert (clf.relevance, clf.genai_evidence_type) == ("no", "confirms_absence")


def test_item_text_reaches_the_classifier():
    (row,) = extract_ocds(_release(awards=[{"id": "a1", "items": [
        _item("Licencias de ChatGPT Enterprise", 10, 30.0, "USD")]}]))
    clf = NLPClassifier(QUERIES).classify(row)
    assert clf.relevance in ("yes", "unclear")   # ChatGPT is context-required in query set v1.0
    assert "ChatGPT" in (clf.genai_evidence or "")
