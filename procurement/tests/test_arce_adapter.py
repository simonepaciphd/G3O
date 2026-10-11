"""Uruguay ARCE adapter: fixed date window, retries, failure accounting. Offline (fake HTTP)."""

from __future__ import annotations

import json

import pytest
import requests

from pipeline.adapters.api import ury_compras_estatales_arce_open_contracting_ocds as arce
from pipeline.core.models import Hit

RSS = b"""<rss><channel>
<item><guid>llamado-1</guid><link>http://x/ocds/release/llamado-1</link></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, status=200, content=b"", payload=None):
        self.status_code, self.content, self._payload = status, content, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(arce.time, "sleep", lambda s: None)
    return arce.Adapter({"source_id": "ury_compras_estatales_arce_open_contracting_ocds",
                         "access_mode": "api", "is_ocds": True, "cache_dir": str(tmp_path / "cache"),
                         "window_since": "2017-11", "window_until": "2018-01"})


def test_window_is_every_month_inclusive_oldest_first():
    assert arce.window_year_months("2017-11", "2018-02") == [(2017, 11), (2017, 12), (2018, 1), (2018, 2)]
    with pytest.raises(ValueError):
        arce.window_year_months("2018-02", "2017-11")


def test_search_reads_exactly_the_configured_months(adapter, monkeypatch):
    urls = []
    monkeypatch.setattr(arce.requests, "get", lambda url, **kw: urls.append(url) or FakeResponse(content=RSS))
    hits = list(adapter.search(None))
    assert [u.rsplit("/rss/", 1)[1] for u in urls] == ["2017/11", "2017/12", "2018/01"]
    assert adapter.window_months == ["2017-11", "2017-12", "2018-01"]
    assert len(hits) == 3 and adapter.search_failures == []


def test_missing_month_is_recorded_not_retried(adapter, monkeypatch):
    calls = []
    def get(url, **kw):
        calls.append(url)
        return FakeResponse(404) if url.endswith("2017/11") else FakeResponse(content=RSS)
    monkeypatch.setattr(arce.requests, "get", get)
    list(adapter.search(None))
    assert [f["month"] for f in adapter.search_failures] == ["2017-11"]
    assert adapter.search_failures[0]["attempts"] == 1 and len(calls) == 3


def test_fetch_retries_transient_errors_then_succeeds(adapter, monkeypatch):
    responses = iter([FakeResponse(503), FakeResponse(200, payload={"releases": [{"id": "llamado-1"}]})])
    monkeypatch.setattr(arce.requests, "get", lambda url, **kw: next(responses))
    (raw,) = list(adapter.fetch([Hit(adapter.source_id, "llamado-1", ref="http://x/1")]))
    assert raw.payload["releases"][0]["id"] == "llamado-1"
    assert adapter.fetch_failures == []
    assert json.load(open(raw.raw_payload_ref))["releases"][0]["id"] == "llamado-1"


def test_fetch_gives_up_after_retries_and_records_the_failure(adapter, monkeypatch):
    calls = []
    monkeypatch.setattr(arce.requests, "get", lambda url, **kw: calls.append(url) or FakeResponse(503))
    assert list(adapter.fetch([Hit(adapter.source_id, "llamado-9", ref="http://x/9")])) == []
    assert len(calls) == arce.RETRY_ATTEMPTS
    (failure,) = adapter.fetch_failures
    assert failure["native_id"] == "llamado-9" and failure["attempts"] == arce.RETRY_ATTEMPTS


def test_network_error_is_retried(adapter, monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError("reset")
    monkeypatch.setattr(arce.requests, "get", boom)
    assert list(adapter.fetch([Hit(adapter.source_id, "llamado-2", ref="http://x/2")])) == []
    assert adapter.fetch_failures[0]["attempts"] == arce.RETRY_ATTEMPTS


def test_cli_run_writes_a_manifest_with_window_failures_and_qc(tmp_path, monkeypatch):
    from pipeline.cli import build_parser
    monkeypatch.setattr(arce.time, "sleep", lambda s: None)
    rss = (b"<rss><channel>"
           b"<item><guid>llamado-1</guid><link>http://x/ocds/release/llamado-1</link></item>"
           b"<item><guid>llamado-2</guid><link>http://x/ocds/release/llamado-2</link></item>"
           b"</channel></rss>")
    release = {"releases": [{"ocid": "ocds-1", "id": "llamado-1", "tag": ["tender"],
                             "buyer": {"name": "Intendencia"},
                             "tender": {"id": "t", "items": [{"description": "SILLAS", "quantity": 2}]}}]}
    def get(url, **kw):
        if "/rss/" in url:
            return FakeResponse(content=rss)
        return FakeResponse(200, payload=release) if url.endswith("llamado-1") else FakeResponse(404)
    monkeypatch.setattr(arce.requests, "get", get)
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("sources:\n  - source_id: ury_compras_estatales_arce_open_contracting_ocds\n"
                   "    access_mode: api\n    is_ocds: true\n    country_iso3: URY\n"
                   "    verification_status: verified\n", encoding="utf-8")
    out = tmp_path / "out"
    args = build_parser().parse_args([
        "run", "ury_compras_estatales_arce_open_contracting_ocds", "--config", str(cfg),
        "--out-dir", str(out), "--since", "2026-08", "--until", "2026-08",
        "--cache-dir", str(tmp_path / "cache")])
    assert args.func(args) == 0
    (manifest_path,) = out.glob("run_manifest_*.json")
    m = json.loads(manifest_path.read_text())
    assert m["window"] == {"since": "2026-08", "until": "2026-08", "months_read": ["2026-08"]}
    assert m["counts"]["fetched"] == 1 and m["counts"]["fetch_failed"] == 1
    assert m["fetch_failures"][0]["native_id"] == "llamado-2"
    assert all(m["qc"].values())
    assert len(m["versions"]["code_sha256"]) == 64
