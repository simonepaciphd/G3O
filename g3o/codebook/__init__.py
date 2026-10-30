"""Codebook package: loader, generators and generator checks (T-013, RC-D-002 A).

The codebook of record is ``codebook/codebook.yaml`` (D-001, R-007). This
package reads it, builds the generated artefacts from it, and runs generator
checks 1-16 of ``planning/t010/item-template.md`` §4.

Generators only assemble signed text. They never rewrite it (R-025): every
slot ``text`` is copied byte for byte, and the only additions are fixed
scaffolding (headings, item ids, hashes, numbering) plus JSON string escaping
in ``.json`` outputs, which is the one declared escaping step (check 3).
"""

from g3o.codebook.loader import Codebook, load_codebook

__all__ = ["Codebook", "load_codebook"]
