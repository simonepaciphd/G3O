"""Local T-030 runtime binding; does not enable the unfinished new-run route.

Build the coder configurations and extractor requests from the same explicit
settings used in the immutable instrument. The caller must supply the signed
approval reference. This is not proof of provider execution or PI acceptance.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from pathlib import Path
from typing import Any

from g3o.classify.jev_activity_code import ActivityCoderConfig, part_combine_adapter
from g3o.classify.jev_page_code import PageCoderConfig
from g3o.classify.questions.v27 import JEV_QUESTION_SET_VERSION, load_set
from g3o.codebook.loader import load_codebook
from g3o.common import page_chunks, support_check
from g3o.common.instrument import build_instrument, canonical_json, sha256_text, write_instrument
from g3o.common.jev_record import load_classifier_rules
from g3o.common.storage_fields import CODEBOOK_SHA256, FIELDS
from g3o.extract import pass2_support, request_v27
from g3o.extract.anthropic_client import ExtractorJob, build_params


@dataclass(frozen=True)
class RuntimeSettings:
    jev_model: str
    extractor_model: str
    extractor_effort: str
    extractor_max_tokens: int
    reserved_tokens: int
    reference_year: int
    approval_reference: str

    def __post_init__(self) -> None:
        for name in ("jev_model", "extractor_model", "extractor_effort", "approval_reference"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be explicitly supplied")
        if type(self.extractor_max_tokens) is not int or self.extractor_max_tokens <= 0:
            raise ValueError("extractor_max_tokens must be positive")
        if type(self.reserved_tokens) is not int or not 0 <= self.reserved_tokens < page_chunks.JEV_STATE_TOKEN_LIMIT:
            raise ValueError("reserved_tokens must leave room inside the approved budget")
        if type(self.reference_year) is not int or not 1000 <= self.reference_year <= 9999:
            raise ValueError("reference_year must be the explicit run calendar year")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_revision() -> str:
    # Content identity covers uncommitted source too; never certify a dirty tree
    # using only its last commit. Ignore bytecode and machine-local caches.
    root = Path(__file__).resolve().parents[2]
    files = {p.relative_to(root).as_posix(): _file_hash(p)
             for p in root.rglob("*") if p.is_file()
             and p.suffix in {".py", ".json", ".md", ".yaml", ".yml"}
             and "__pycache__" not in p.parts}
    return "package-sha256:" + sha256_text(canonical_json(files))


@dataclass(frozen=True)
class BoundRuntime:
    settings: RuntimeSettings
    instrument_id: str
    page_config: PageCoderConfig
    activity_config: ActivityCoderConfig
    pass1_system: str
    pass2_system: str

    def _configure(self, job: ExtractorJob, system: str) -> ExtractorJob:
        params = build_params(
            system=system, user=job.params["messages"][0]["content"],
            output_schema=job.params["output_config"]["format"]["schema"],
            model=self.settings.extractor_model, effort=self.settings.extractor_effort,
            max_tokens=self.settings.extractor_max_tokens,
        )
        return replace(job, params=params, metadata={**job.metadata, "setup_pointer": self.instrument_id})

    def stage6_config(self) -> Any:
        """The T-026 Stage 6 configuration bound to this same instrument and settings."""
        from g3o.validate.stage6_v27 import Stage6Config

        a = self.activity_config
        return Stage6Config(rules=a.rules, setup_pointer=self.instrument_id, configured_model=a.configured_model,
                            combiner=a.combiner, reference_year=a.reference_year,
                            reserved_tokens=self.settings.reserved_tokens, estimator=self.page_config.estimator)

    def pass1_job(self, page: request_v27.Pass1Page, plan: request_v27.RequestPlan) -> ExtractorJob:
        return self._configure(request_v27.build_job(page, plan, system=self.pass1_system), self.pass1_system)

    def pass2_job(self, page: pass2_support.Pass2Page, plan: pass2_support.Pass2Plan) -> ExtractorJob:
        return self._configure(pass2_support.build_job(page, plan, system=self.pass2_system), self.pass2_system)


def bind_runtime(run_dir: Path, settings: RuntimeSettings) -> BoundRuntime:
    """Bind before producing rows; reject a changed setup on resume.

    A crash after writing the instrument and before writing the binding marker
    is safe to resume. Both files are immutable/exclusive and byte-verified.
    The presweep entry point still needs to consume this binding (T-030).
    """
    cb = load_codebook()
    if cb.sha256 != CODEBOOK_SHA256:
        raise ValueError("runtime codebook differs from signed r13")
    installed_matcher = version("rapidfuzz")
    if installed_matcher != support_check.PINNED_RAPIDFUZZ:
        raise ValueError("runtime matcher differs from approved RapidFuzz version")
    estimator = page_chunks.TokenEstimator()
    estimator.assert_approved()
    pass1_system = request_v27.build_system_prompt(cb)
    pass2_system = pass2_support.build_system_prompt(cb)
    generated = Path(__file__).resolve().parents[2] / "codebook" / "generated"
    questions = {name: load_set(name) for name in ("page", "activity", "institution")}
    question_hashes = {name: sha256_text(canonical_json(doc)) for name, doc in questions.items()}
    prompt_hashes = {"pass1": sha256_text(pass1_system), "pass2": sha256_text(pass2_system)}
    for name in ("extract_output_contract.md", "validate_output_contract.md", "jev_questions.json"):
        prompt_hashes[name] = _file_hash(generated / name)
    chunker_hash = _file_hash(Path(page_chunks.__file__))
    payload: dict[str, Any] = {
        "schema_version": "g3o-instrument-v1", "codebook_release": "2.7",
        "codebook_sha256": cb.sha256,
        "codebook_item_hashes": {key: val["schema"]["x-item-hash"] for key, val in FIELDS.items()
                                  if "x-item-hash" in val["schema"]},
        # SPEC D-001 / DEC-013 a: these labels live only in the setup record.
        "extract_contract_label": "v2.7", "validate_contract_label": "v1.5",
        "question_set_version": JEV_QUESTION_SET_VERSION,
        "question_hashes": question_hashes, "prompt_hashes": prompt_hashes,
        "configured_jev_model": settings.jev_model, "extractor_model_id": settings.extractor_model,
        "extractor_prompt_sha256": sha256_text(pass1_system),
        "extractor_configuration": {
            "model": settings.extractor_model, "effort": settings.extractor_effort,
            "max_tokens": settings.extractor_max_tokens,
            "pass1_schema_sha256": sha256_text(canonical_json(request_v27.output_schema())),
            "pass2_schema_sha256": sha256_text(canonical_json(pass2_support.output_schema())),
            "reference_year": settings.reference_year, "reserved_tokens": settings.reserved_tokens,
            "max_split_depth": page_chunks.DEFAULT_MAX_SPLIT_DEPTH,
            "matcher_word_rule_cutoff": support_check.WORD_RULE_CUTOFF,
            "matcher_decision": support_check.MATCH_DECISION,
        },
        "chunker_version": "page_chunks-sha256:" + chunker_hash,
        "estimator_version": "estimator-sha256:" + sha256_text(canonical_json(asdict(estimator))),
        "token_budget": page_chunks.JEV_STATE_TOKEN_LIMIT,
        "matcher_library": "rapidfuzz", "matcher_version": installed_matcher,
        "matcher_threshold": support_check.MATCH_THRESHOLD,
        "chosen_answer_confidence_threshold": 0.8,
        "producer_code_revision": _package_revision(),
        "instrument_approval_reference": settings.approval_reference,
    }
    record = build_instrument(payload)
    marker = run_dir / "instrument-binding.json"
    marker_raw = (canonical_json({"instrument_id": record["instrument_id"]}) + "\n").encode("utf-8")
    if marker.exists() and marker.read_bytes() != marker_raw:
        raise ValueError("resume instrument differs from the executed configuration or source")
    # Validate/construct every runtime object before publishing the binding.
    rules = load_classifier_rules(cb.raw, expected_sha256=cb.sha256)
    bound = BoundRuntime(
        settings, record["instrument_id"],
        PageCoderConfig(rules, record["instrument_id"], settings.jev_model,
                        settings.reserved_tokens, estimator=estimator, codebook=cb),
        ActivityCoderConfig(rules, record["instrument_id"], settings.jev_model,
                            part_combine_adapter(cb), settings.reference_year),
        pass1_system, pass2_system,
    )
    write_instrument(run_dir / "final" / "instruments", payload)
    try:
        with marker.open("xb") as stream:
            stream.write(marker_raw)
    except FileExistsError:
        if marker.read_bytes() != marker_raw:
            raise ValueError("concurrent run binding differs") from None
    return bound