"""Build hook: ship the signed codebook inside the wheel (RC-D-019 D3, T-030).

All metadata lives in ``pyproject.toml``; this file only adds one build step.

The codebook of record is ``codebook/codebook.yaml`` at the repository root,
outside the ``g3o`` package, so ``[tool.setuptools.package-data]`` cannot name
it, and a non-editable wheel used to ship without it. ``load_codebook()`` then
had nothing to read. The file stays where it is (its path is part of the signed
record); this step copies its bytes unchanged into the built package as
``g3o/codebook/data/codebook.yaml``, which ``g3o.codebook.loader`` reads when
the checkout file is not there. A byte copy keeps the release hash: the file is
CRLF and ``-text`` in git, and no newline conversion happens here.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

SIGNED_CODEBOOK = Path("codebook") / "codebook.yaml"
PACKAGED_CODEBOOK = Path("g3o") / "codebook" / "data" / "codebook.yaml"


class BuildPyWithCodebook(build_py):
    def run(self) -> None:
        super().run()
        if getattr(self, "editable_mode", False):
            # Editable installs read the checkout file directly.
            return
        target = Path(self.build_lib) / PACKAGED_CODEBOOK
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SIGNED_CODEBOOK, target)

    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        outputs = list(super().get_outputs(include_bytecode))
        if not getattr(self, "editable_mode", False):
            outputs.append(str(Path(self.build_lib) / PACKAGED_CODEBOOK))
        return outputs


setup(cmdclass={"build_py": BuildPyWithCodebook})
