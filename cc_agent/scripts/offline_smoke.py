"""Offline smoke for a packaged cc_agent plugin (no network, no Dify runtime).

Usage: python offline_smoke.py [package_root]

Imports every shipped module of the plugin to prove the bundled wheels provide
a complete, importable dependency set for the target architecture, then proves
tiktoken resolves gpt2 through the bundled cache instead of the network.
"""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(root))

import core  # noqa: E402
import strategies  # noqa: E402

names = {"provider.agent"}
for module in pkgutil.iter_modules(core.__path__):
    names.add(f"core.{module.name}")
for module in pkgutil.iter_modules(strategies.__path__):
    names.add(f"strategies.{module.name}")

for name in sorted(names):
    importlib.import_module(name)

cache_dir = root / "_assets" / "tiktoken_cache"
cache_files = len([p for p in cache_dir.iterdir() if p.is_file()])
os.environ["TIKTOKEN_CACHE_DIR"] = str(cache_dir)

import tiktoken  # noqa: E402

gpt2_tokens = len(tiktoken.encoding_for_model("gpt2").encode("offline smoke"))

ok = cache_files == 2 and gpt2_tokens > 0
print(
    json.dumps(
        {
            "imports": len(names),
            "tiktoken_cache_files": cache_files,
            "gpt2_tokens": gpt2_tokens,
            "ok": ok,
        }
    )
)
raise SystemExit(0 if ok else 1)
