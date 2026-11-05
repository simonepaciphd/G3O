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


# ---------------------------------------------------------------------------
# Codebook in the wheel (RC-D-019 D3, carried to T-030)
# ---------------------------------------------------------------------------
#
# The v2.7 path reads ``codebook/codebook.yaml`` (outside the package) and
# ``g3o/codebook/generated/*.{md,json}`` at run time. ``setup.py`` copies the
# former into the build as ``g3o/codebook/data/codebook.yaml``; package-data
# ships the latter. The test below builds the wheel, unpacks it and loads the
# codebook through the installed-package path, outside the checkout.

SIGNED_CODEBOOK = REPO_ROOT / "codebook" / "codebook.yaml"


def test_codebook_generated_declared_in_package_data() -> None:
    assert '"g3o.codebook.generated"' in _package_data_block()


def test_checkout_resolves_the_checkout_codebook() -> None:
    from g3o.codebook import loader

    assert loader.default_codebook_path() == SIGNED_CODEBOOK.resolve()
    assert not loader.PACKAGED_CODEBOOK.exists(), (
        "g3o/codebook/data/codebook.yaml is a build output and must not sit in the checkout"
    )


_WHEEL_PROBE = r"""
import hashlib, json, sys
sys.path.insert(0, sys.argv[1])
import g3o
from g3o.codebook import loader
from g3o.extract import pass2_support, request_v27
cb = loader.load_codebook()
request_v27.build_system_prompt(cb)
pass2_support.build_system_prompt(cb)
print(json.dumps({
    "g3o": g3o.__file__,
    "path": str(loader.default_codebook_path()),
    "sha256": cb.sha256,
    "sections": len(request_v27._generated_sections()),
}))
"""


def test_wheel_ships_codebook_and_generated(tmp_path: Path) -> None:
    import json
    import subprocess
    import sys
    import zipfile

    pytest.importorskip("setuptools")
    from g3o.classify.questions.v27.build import SIGNED_CODEBOOK_SHA256

    out = tmp_path / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation",
         "--no-index", "-q", "-w", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    (wheel,) = out.glob("g3o-*.whl")
    site = tmp_path / "site"
    with zipfile.ZipFile(wheel) as z:
        names = set(z.namelist())
        assert z.read("g3o/codebook/data/codebook.yaml") == SIGNED_CODEBOOK.read_bytes()
        for gen in (REPO_ROOT / "g3o" / "codebook" / "generated").iterdir():
            if gen.suffix in (".md", ".json"):
                name = f"g3o/codebook/generated/{gen.name}"
                assert name in names, f"{name} missing from the wheel"
                assert z.read(name) == gen.read_bytes()
        z.extractall(site)

    # Run outside the checkout so it cannot mask missing wheel contents.
    probe = subprocess.run(
        [sys.executable, "-c", _WHEEL_PROBE, str(site)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr[-2000:]
    got = json.loads(probe.stdout.strip().splitlines()[-1])
    assert Path(got["g3o"]).resolve().is_relative_to(site.resolve())
    assert Path(got["path"]).resolve() == (site / "g3o/codebook/data/codebook.yaml").resolve()
    assert got["sha256"] == SIGNED_CODEBOOK_SHA256
    assert got["sections"] > 0
