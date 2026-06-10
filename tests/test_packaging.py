"""Packaging invariants (review F10).

A non-editable ``pip install .`` ships only what ``find_packages`` discovers
plus what ``[tool.setuptools.package-data]`` lists. The Stage 5/6 LLM clients
load their prompt assets from disk *at import time*
(``g3o.{extract,validate}.client``), so a prompt directory that is either not a
real package (missing ``__init__.py``) or not declared in package-data produces
a wheel that imports fine in editable mode (CI's ``test`` job) but raises
``FileNotFoundError`` from a clean wheel install. F10 was exactly this: the
``g3o.validate.prompts`` directory had neither.

These tests guard the unit-test-visible half of that invariant; the CI
``wheel-install`` job exercises the full non-editable install.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = REPO_ROOT / "g3o"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _prompt_packages() -> list[Path]:
    """Every ``prompts/`` directory under ``g3o/`` that ships ``*.md`` assets.

    Scoped to directories literally named ``prompts`` (the LLM prompt assets
    loaded from disk at import) — module ``README.md`` files are documentation,
    not runtime package-data, and are excluded.
    """
    return sorted(
        p for p in PKG_ROOT.rglob("prompts") if p.is_dir() and any(p.glob("*.md"))
    )


def _package_data_block() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    marker = "[tool.setuptools.package-data]"
    assert marker in text, f"{marker} missing from pyproject.toml"
    start = text.index(marker)
    # The block runs to the next top-level table header.
    rest = text[start + len(marker) :]
    end = rest.find("\n[")
    return rest if end == -1 else rest[:end]


def test_prompt_dirs_discovered() -> None:
    """Sanity: we actually found the prompt-shipping packages we expect."""
    dotted = {
        ".".join(p.relative_to(REPO_ROOT).parts) for p in _prompt_packages()
    }
    assert "g3o.extract.prompts" in dotted
    assert "g3o.validate.prompts" in dotted


@pytest.mark.parametrize("prompt_dir", _prompt_packages(), ids=lambda p: p.name and str(p))
def test_prompt_package_is_real_package(prompt_dir: Path) -> None:
    """Each prompt dir must have ``__init__.py`` so ``find_packages`` ships it."""
    init = prompt_dir / "__init__.py"
    assert init.exists(), (
        f"{prompt_dir.relative_to(REPO_ROOT)} ships *.md but has no __init__.py; "
        f"find_packages will not discover it and a non-editable wheel drops its "
        f"prompts (review F10)."
    )


@pytest.mark.parametrize("prompt_dir", _prompt_packages(), ids=lambda p: p.name and str(p))
def test_prompt_package_declared_in_package_data(prompt_dir: Path) -> None:
    """Each prompt dir's dotted package name must appear in package-data."""
    dotted = ".".join(prompt_dir.relative_to(REPO_ROOT).parts)
    block = _package_data_block()
    assert f'"{dotted}"' in block, (
        f"{dotted} ships *.md but is not listed in [tool.setuptools.package-data]; "
        f"a non-editable wheel will omit its prompts (review F10)."
    )


def test_prompt_packages_importable() -> None:
    """The prompt packages and the clients that load them import cleanly."""
    importlib.import_module("g3o.extract.prompts")
    importlib.import_module("g3o.validate.prompts")
    extract_client = importlib.import_module("g3o.extract.client")
    validate_client = importlib.import_module("g3o.validate.client")
    assert extract_client.SYSTEM_MESSAGE
    assert validate_client.SYSTEM_MESSAGE
