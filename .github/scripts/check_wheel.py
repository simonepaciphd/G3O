"""Import all modules from an installed wheel (run outside the checkout)."""
import importlib
import pkgutil

import g3o

failures = []
for module in pkgutil.walk_packages(g3o.__path__, g3o.__name__ + "."):
    try:
        importlib.import_module(module.name)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{module.name}: {exc!r}")
if failures:
    raise SystemExit("module import failures from non-editable wheel:\n  " + "\n  ".join(failures))
print("OK: all g3o modules import from the installed wheel")
