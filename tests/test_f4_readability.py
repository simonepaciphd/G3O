"""Offline tests for scripts/spikes/f4/readability.py (synthetic data only)."""
import gzip
import importlib.util
import io
import json
import tarfile
from pathlib import Path

_P = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "f4" / "readability.py"
_spec = importlib.util.spec_from_file_location("readability", _P)
rd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rd)


def test_measures_clean_multiscript_text():
    m = rd.measures("Council AI policy.\n人工智能政策 นโยบาย")
    assert m["replacement_share"] == 0 and m["nonprint_share"] == 0
    assert m["letter_share"] > 0.9 and m["signatures"] == ""
    assert rd.flags(m) == []


def test_measures_binary_noise():
    text = "%PDF-1.7\n1 0 obj\n<<>>\nstream\n\x00\x01�� endstream endobj"
    m = rd.measures(text)
    assert m["replacement_share"] > 0.03 and m["nonprint_share"] > 0.03
    assert set(m["signatures"].split(";")) >= {"pdf_header", "pdf_objects", "null"}
    f = rd.flags(m)
    assert "binary_signature" in f and "replacement>1%" in f


def test_letter_share_counts_marks_and_ignores_whitespace():
    assert rd.measures("ก่  \n ข้")["letter_share"] == 1.0   # Thai consonant + tone mark
    assert rd.measures("12 34")["letter_share"] == 0.0


def test_empty_and_whitespace():
    assert rd.flags(rd.measures("")) == ["empty"]
    m = rd.measures("   \n")
    assert m["letter_share"] is None and "letters<10%" in rd.flags(m)


def test_sample_escapes_controls():
    s = rd.sample("ab\x00c|d�" + "x" * 200)
    assert "\\x00" in s and "\\x7c" in s and "\n" not in s
    assert "�" in s   # U+FFFD is printable, so it is kept as is
    assert s.startswith("ab")


def test_member_id_forms():
    assert rd._member_id("RS-008", "r20260830T114940Z-32ea-scrape",
                         "institutions/94/INST-1/scrape/abc.json.gz") == "RS-008:r20260830T114940Z-32ea:INST-1:abc"
    assert rd._member_id("RS-009", "x", "r20260903T1-aa/institutions/94/INST-2/scrape/d.json.gz") == \
        "RS-009:r20260903T1-aa:INST-2:d"


def _gz(rec):
    return gzip.compress(json.dumps(rec).encode())


def test_scan_end_to_end(tmp_path):
    drive = tmp_path / "drive"
    pulled = drive / rd.REL_RS009
    pulled.mkdir(parents=True)
    with tarfile.open(pulled / rd.RS009_TARS[0], "w") as t:
        for i, text in enumerate(["Plain readable page", "��� binary", "Plain readable page"]):
            data = _gz({"url": f"u{i}", "text": text, "title": "", "content_type": "pdf", "fetch_metadata": {}})
            ti = tarfile.TarInfo(f"r20260903T1-aa/institutions/00/INST-{i}/scrape/h{i}.json.gz")
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    rows, info = rd.scan(rd.iter_sources(drive, None))
    assert len(rows) == 3
    assert [r["duplicate_of_earlier"] for r in rows] == [False, False, True]
    assert rows[1]["sample_120"] and not rows[0]["sample_120"]
    assert not any(r["has_bytes_field"] for r in rows)
    assert any(m.startswith("RS-008") for m in info["missing_sources"])
    s = rd.summarize(rows)
    assert s["flag_counts"]["all_unique_text"]["replacement>10%"] == 1
    assert s["by_source"]["RS-009"]["pages"] == 3
    md = rd.render_md(rows, s, {"generated_at": "t", **info})
    assert "0 flagged pages have stored bytes locally" in md
