"""Experiment-only code. **Nothing under ``g3o/run`` may import this package.**

Modules here exist to support a named, PI-authorised measurement and are never
on a production path. That is not a convention kept by comment: two tests in
``tests/test_parent_chain_experiment.py`` enforce it —
``test_no_production_module_imports_the_experiment_package`` walks the import
graph, and ``test_default_frame_build_does_not_read_the_crosswalk_csvs`` traces
every file a default frame build opens.

The rule for adding to this package: an experiment module may import from
``g3o`` freely, and no module outside it may import from here. If a thing here
turns out to be needed in production, it is promoted deliberately — moved out,
given its own PR and its own ruling — not imported across the line.
"""

from __future__ import annotations

__all__: list[str] = []
