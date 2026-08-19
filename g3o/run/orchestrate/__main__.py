"""``python -m g3o.run.orchestrate`` — see :mod:`g3o.run.orchestrate.cli`.

Exits with the CLI's return value rather than falling off the end, so the shell
scripts and the joint gate that read these codes get them (the same fix
``python -m g3o`` needed: an exit status that is not propagated is a failure that
reports success).
"""

from __future__ import annotations

import sys

from g3o.run.orchestrate.cli import main

if __name__ == "__main__":
    sys.exit(main())
