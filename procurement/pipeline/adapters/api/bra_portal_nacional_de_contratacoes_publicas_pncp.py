"""Adapter: Brazil - Portal Nacional de Contratacoes Publicas (PNCP).

Verified live 2026-08-07 (partial verification — see notes below, not a full
production sign-off):
  - Public query endpoint, no API key: GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao
  - Required params: dataInicial, dataFinal (YYYYMMDD), codigoModalidadeContratacao,
    pagina, tamanhoPagina (>= 10).
  - Response: {"data": [...], "totalRegistros": int, "totalPaginas": int, ...}.

CORRECTION: config/sources.yaml carried is_ocds=true for this source (from the
tracker's OCDS column). Measured: this endpoint returns PNCP's own native JSON
shape (objetoCompra, orgaoEntidade, valorTotalEstimado, ...), not an OCDS
release. Third parties (e.g. Transparencia Brasil) republish PNCP data as OCDS
separately; this pipeline reads PNCP's own API directly, so it is NOT an OCDS
source here. is_ocds corrected to false and base_url corrected to the real
endpoint (was a tracker landing-page URL) — see asset-registry.csv.

NOT YET DONE (plumbing/QC probe only, per PI go-ahead 2026-08-04): full rate-limit
measurement, robots.txt/ToS review, complete pagination coverage, and Portuguese
coverage of the pagina/modalidade space. verification_status stays
unverified_snapshot; this adapter runs only via --allow-unverified --limit N.

No free-text keyword parameter exists on this endpoint. Per docs/architecture.md
§5a ("otherwise return all records and let the classifier filter downstream"),
search() returns recent notices across a small set of common modalities and
leaves the relevance call to the classifier, rather than guessing at a client-side
pre-filter this source was never built to support.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests

from ...core.base import SourceAdapter
from ...core.models import GenAIQuerySet, Hit, RawRecord

log = logging.getLogger(__name__)

BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
PAGE_SIZE = 10  # API's documented minimum for tamanhoPagina

# Common modalities under Lei 14.133/2021 (Brazil's procurement law). Not
# exhaustive — chosen to cover the two shapes most likely to surface software/
# service purchases: open competitive (6) and the faster waiver/sole-source
# routes (8, 9) governments use for smaller or specialized buys.
MODALITY_CODES = {
    6: "Pregao - Eletronico",
    8: "Dispensa de Licitacao",
    9: "Inexigibilidade de Licitacao",
}

# PNCP modalidadeId -> extension procedure_type (spec §4.2). A codelist
# translation of Brazil's legal modalities, not an inference from free text.
# Anything not listed here stays "unknown" (see extract()).
MODALIDADE_TO_PROCEDURE_TYPE = {
    4: "open",             # Concorrencia - open competitive call
    6: "open",             # Pregao Eletronico - competitive, open to all bidders
    8: "direct_award",     # Dispensa - waiver of competition
    9: "direct_award",     # Inexigibilidade - competition legally not required (sole source)
}

CACHE_DIR = Path("data_cache") / "bra_portal_nacional_de_contratacoes_publicas_pncp"


def _cache_raw(native_id: str, payload: dict) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = native_id.replace("/", "_")
    path = CACHE_DIR / f"{safe_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _fetch_page(modalidade: int, data_inicial: str, data_final: str, pagina: int) -> dict:
    resp = requests.get(
        BASE_URL,
        params={
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "codigoModalidadeContratacao": modalidade,
            "pagina": pagina,
            "tamanhoPagina": PAGE_SIZE,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _as_date(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    head = value.strip()[:10]
    return head if len(head) == 10 and head[4] == "-" and head[7] == "-" else None


class Adapter(SourceAdapter):
    access_mode = "api"
    is_ocds = False  # corrected — see module docstring

    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        """Recent notices across a small set of modalities, most recent first.

        Bounded to the last 90 days and max_pages_per_modality pages so this
        stays a probe, not a pull — the calling CLI's --limit stops consumption
        early regardless, but this bound also protects a source we have not
        rate-limit-tested yet.
        """
        today = datetime.now(timezone.utc).date()
        window_start = today - timedelta(days=90)
        data_final = today.strftime("%Y%m%d")
        data_inicial = window_start.strftime("%Y%m%d")

        max_pages_per_modality = 5
        for modalidade in MODALITY_CODES:
            for pagina in range(1, max_pages_per_modality + 1):
                try:
                    payload = _fetch_page(modalidade, data_inicial, data_final, pagina)
                except requests.RequestException as exc:
                    log.error("PNCP fetch failed (modalidade=%s pagina=%s): %s",
                              modalidade, pagina, exc)
                    break

                rows = payload.get("data") or []
                if not rows:
                    break  # no more pages for this modality/window

                for row in rows:
                    native_id = str(row.get("numeroControlePNCP") or "")
                    if not native_id:
                        continue
                    yield Hit(source_id=self.source_id, native_id=native_id, ref=row)

                total_paginas = payload.get("totalPaginas") or 1
                if pagina >= total_paginas:
                    break
                time.sleep(0.5)  # polite pacing — untested rate limit, be conservative

    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        """search() already returned full payloads (in Hit.ref); wrap + cache them."""
        for hit in hits:
            payload = hit.ref if isinstance(hit.ref, dict) else {}
            raw_payload_ref = _cache_raw(hit.native_id, payload)
            yield RawRecord(
                source_id=self.source_id,
                native_id=hit.native_id,
                payload=payload,
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                raw_payload_ref=raw_payload_ref,
            )

    def extract(self, raw: RawRecord) -> dict:
        """PNCP native JSON -> intermediate field dict (see module docstring)."""
        p = raw.payload if isinstance(raw.payload, dict) else {}

        orgao = p.get("orgaoEntidade") or {}
        unidade = p.get("unidadeOrgao") or {}
        modalidade_id = p.get("modalidadeId")

        # This endpoint is publication-stage only (no award data) — every
        # record is a tender for adoption_stage purposes (ruling D2/D3).
        notice_type = "tender"

        value_amount = p.get("valorTotalHomologado")
        value_is_estimated = False
        if value_amount is None:
            value_amount = p.get("valorTotalEstimado")
            value_is_estimated = value_amount is not None

        title = p.get("objetoCompra")
        info = p.get("informacaoComplementar")
        description = f"{title}\n\n{info}" if title and info else title

        fields = {
            "native_id": raw.native_id,
            "notice_type": notice_type,
            "title": title,
            "description": description,
            "buyer_name": orgao.get("razaoSocial"),
            # CNPJ is Brazil's federal registry id for legal entities — a real
            # tier-2 matching signal (spec §4.4), not derived or guessed.
            "buyer_national_id": orgao.get("cnpj"),
            "publication_date": _as_date(p.get("dataPublicacaoPncp")),
            "url": p.get("linkSistemaOrigem") or None,
            "value_amount": value_amount,
            "value_is_estimated": value_is_estimated,
            "value_covers": "single_award",
            "procedure_type": MODALIDADE_TO_PROCEDURE_TYPE.get(modalidade_id, "unknown"),
        }
        # Municipality/state context is real, evidenced detail this native API
        # carries and OCDS's generic buyer.name would not — kept in description
        # rather than invented as a new field outside spec §4.
        location_bits = [unidade.get("municipioNome"), unidade.get("ufSigla")]
        location = ", ".join(b for b in location_bits if b)
        if location and fields["description"]:
            fields["description"] = f"{fields['description']}\n\nLocal: {location}"

        return {k: v for k, v in fields.items() if v is not None}
