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

# The v2.7 path reads the signed codebook and its generated outputs at run time
# (RC-D-019 D3); both must come from the wheel, not the checkout.
from g3o.codebook import loader  # noqa: E402
from g3o.extract import pass2_support, request_v27  # noqa: E402

cb = loader.load_codebook()
if loader.default_codebook_path() != loader.PACKAGED_CODEBOOK:
    raise SystemExit(f"codebook not read from the wheel: {loader.default_codebook_path()}")
request_v27.build_system_prompt(cb)
pass2_support.build_system_prompt(cb)
print(f"OK: codebook {cb.sha256} and generated sections load from the installed wheel")
