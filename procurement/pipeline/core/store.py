"""Write extraction intermediates to the local staging database.

Staging lives in outputs/staging/ in two forms:
  - procurement_intermediate.csv    (portable, diffable, human-readable)
  - procurement_staging.sqlite      (queryable, schema-enforced, dedup by record_id)
Per-source extracts land in outputs/per_source/<source_id>.csv for QC.

Three tables, all keyed on record_id (spec §2, §4, §5):
  records      1 row per procurement record   (procurement_record.schema.json)
  extensions   1 row per record, 1:1          (procurement_extension.schema.json)
  links        N rows per record, RESOLVED    (institution_link.schema.json)
  review       1 row per unresolved record    (institution_review.schema.json)

Idempotent: upsert on record_id so re-running a source never duplicates rows.
Links are keyed on (record_id, institution_uid, role) because one procurement
legitimately has several.

Every row is validated against its JSON schema BEFORE it is written. A record
that fails validation raises; staging errors are never silently dropped.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import fields as dataclass_fields
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from .models import ExtensionRecord, InstitutionLink, InstitutionReview, ProcurementRecord

SCHEMA_DIR = Path(__file__).parents[2] / "config" / "schema"

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date")
def _is_iso_date(value) -> bool:
    if not isinstance(value, str):
        return True
    try:
        date.fromisoformat(value)
        return len(value) == 10
    except ValueError:
        return False


@FORMAT_CHECKER.checks("date-time")
def _is_iso_datetime(value) -> bool:
    if not isinstance(value, str):
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "T" in value and parsed.tzinfo is not None
    except ValueError:
        return False


@FORMAT_CHECKER.checks("uri")
def _is_uri(value) -> bool:
    if not isinstance(value, str):
        return True
    parsed = urlsplit(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme not in {"http", "https"}))

_TABLES = {
    "records": (ProcurementRecord, "procurement_record.schema.json", ("record_id",)),
    "extensions": (ExtensionRecord, "procurement_extension.schema.json", ("record_id",)),
    "links": (InstitutionLink, "institution_link.schema.json",
              ("record_id", "institution_uid", "role")),
    "review": (InstitutionReview, "institution_review.schema.json", ("record_id",)),
}


class ValidationError(Exception):
    """A record did not conform to its schema. Never swallowed."""


def _columns(model) -> list[str]:
    return [f.name for f in dataclass_fields(model)]


def _sql_type(value_type: str) -> str:
    return "TEXT"   # SQLite is dynamically typed; the JSON schema is the contract.


class StagingStore:
    """Storage for candidates and extension candidates before contract mapping.

    This is deliberately not named a master: without a resolved institution,
    review-confirmed relevance, and the 39-field crosswalk, these rows cannot
    enter G3O's contract-conformant primary table.
    """

    def __init__(self, out_dir: str = "outputs/staging"):
        self.out_dir = Path(out_dir)
        self.per_source_dir = self.out_dir.parent / "per_source"
        self.csv_path = self.out_dir / "procurement_intermediate.csv"
        self.sqlite_path = self.out_dir / "procurement_staging.sqlite"
        self._validators: dict[str, Draft202012Validator] = {}
        self._conn: sqlite3.Connection | None = None

    # -- infrastructure ---------------------------------------------------- #

    def _validator(self, table: str) -> Draft202012Validator:
        if table not in self._validators:
            _, schema_file, _ = _TABLES[table]
            with open(SCHEMA_DIR / schema_file, "r", encoding="utf-8") as fh:
                self._validators[table] = Draft202012Validator(
                    json.load(fh), format_checker=FORMAT_CHECKER)
        return self._validators[table]

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.sqlite_path)
            self._conn.row_factory = sqlite3.Row
            self._create_tables(self._conn)
        return self._conn

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        for table, (model, _, key) in _TABLES.items():
            cols = _columns(model)
            col_sql = ", ".join(f'"{c}" {_sql_type(c)}' for c in cols)
            key_sql = ", ".join(f'"{k}"' for k in key)
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{table}" ({col_sql}, PRIMARY KEY ({key_sql}))'
            )
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- validation -------------------------------------------------------- #

    def validate(self, table: str, row: dict) -> None:
        errors = sorted(self._validator(table).iter_errors(row), key=lambda e: e.path)
        if errors:
            detail = "; ".join(
                f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
                for e in errors[:5]
            )
            raise ValidationError(f"{table} row failed schema validation — {detail}")

    # -- writes ------------------------------------------------------------ #

    def _upsert(self, table: str, row: dict) -> None:
        self.validate(table, row)
        model, _, key = _TABLES[table]
        cols = _columns(model)
        conn = self.connect()
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f'"{c}"=excluded."{c}"' for c in cols if c not in key)
        key_sql = ", ".join(f'"{k}"' for k in key)
        conn.execute(
            f'INSERT INTO "{table}" ({", ".join(chr(34)+c+chr(34) for c in cols)}) '
            f"VALUES ({placeholders}) "
            f"ON CONFLICT({key_sql}) DO UPDATE SET {updates}",
            [_encode(row.get(c)) for c in cols],
        )
        conn.commit()

    def upsert(self, record: ProcurementRecord) -> None:
        """Insert or update one procurement record, keyed by record_id."""
        self._upsert("records", record.to_dict())

    def upsert_extension(self, extension: ExtensionRecord) -> None:
        """Insert or update the extension row joined 1:1 on record_id (spec §4)."""
        self._upsert("extensions", extension.to_dict())

    def upsert_link(self, link: InstitutionLink) -> None:
        """Insert or update one record-to-institution link (spec §5).

        Guards the standing rule: institution_uid must be the master's
        persistent key. A positional-looking id is rejected here rather than
        silently repointing at the wrong institution on the next master rebuild.
        """
        uid = link.institution_uid
        if uid is not None and str(uid).isdigit():
            raise ValidationError(
                f"institution_uid {uid!r} looks like a positional row index. "
                "Never key to master_row_id — wait for the persistent key "
                "(spec §5). Pass the persistent key or leave it None for review."
            )
        self._upsert("links", link.to_dict())

    def upsert_review(self, review: InstitutionReview) -> None:
        """Insert or update a review-queue row (PI ruling Q5c, 2026-08-04).

        Unresolved candidates live here, never in the link table, so every
        institution_link row is a confirmed match by construction.
        """
        self._upsert("review", review.to_dict())

    # -- exports ----------------------------------------------------------- #

    def export_csv(self, table: str = "records", path: Path | None = None) -> Path:
        """Write the portable CSV view of a table."""
        model, _, _ = _TABLES[table]
        cols = _columns(model)
        default_paths = {
            "records": self.csv_path,
            "extensions": self.out_dir / "procurement_extension_candidates.csv",
            "links": self.out_dir / "institution_links.csv",
            "review": self.out_dir / "institution_review_queue.csv",
        }
        target = path or default_paths[table]
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connect().execute(f'SELECT * FROM "{table}"').fetchall()
        with open(target, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: _decode_for_csv(row[c]) for c in cols})
        return target

    def export_per_source(self, source_id: str) -> Path:
        """Write outputs/per_source/<source_id>.csv for QC before merge."""
        cols = _columns(ProcurementRecord)
        self.per_source_dir.mkdir(parents=True, exist_ok=True)
        target = self.per_source_dir / f"{source_id}.csv"
        rows = self.connect().execute(
            'SELECT * FROM "records" WHERE source_id = ?', (_encode(source_id),)
        ).fetchall()
        with open(target, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: _decode_for_csv(row[c]) for c in cols})
        return target

    # -- reads (QC) -------------------------------------------------------- #

    def count(self, table: str = "records") -> int:
        return self.connect().execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    def iter_rows(self, table: str = "records") -> Iterable[dict]:
        for row in self.connect().execute(f'SELECT * FROM "{table}"'):
            yield {k: _decode(row[k]) for k in row.keys()}


def _encode(value):
    """Store JSON so booleans and numbers survive the round trip intact —
    SQLite would otherwise hand back 0/1 for a bool and break re-validation."""
    return None if value is None else json.dumps(value)


def _decode(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _decode_for_csv(value):
    decoded = _decode(value)
    return "" if decoded is None else decoded
