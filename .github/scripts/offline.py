"""Run a Python check without socket egress, including during import/collection.

CI also uses a Linux network namespace: this Python audit hook alone does not
isolate native extensions or child processes. Package downloads happen before
that namespace is entered; no provider credentials are supplied by the workflow.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


class NetworkForbidden(RuntimeError):
    """A check attempted real network I/O instead of using a fixture."""


def deny_network(event: str, args: tuple) -> None:
    # CPython emits these before DNS, connection and datagram operations.
    if event in {
        "socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
        "socket.gethostbyaddr", "socket.getnameinfo", "socket.sendto",
        "socket.sendmsg", "socket.bind",
    }:
        raise NetworkForbidden(f"offline check blocked {event}")


def main() -> None:
    args = sys.argv[1:]
    if not args or (args[0] == "-m" and len(args) < 2):
        raise SystemExit("usage: offline.py -m MODULE [ARGS...] | SCRIPT [ARGS...]")
    sys.addaudithook(deny_network)
    if args[0] == "-m":
        # Match `python -m` module resolution without requiring an editable install.
        sys.path.insert(0, str(Path.cwd()))
        sys.argv = args[1:]
        runpy.run_module(args[1], run_name="__main__", alter_sys=True)
    else:
        sys.path.insert(0, str(Path(args[0]).resolve().parent))
        sys.argv = args
        runpy.run_path(args[0], run_name="__main__")


if __name__ == "__main__":
    main()
