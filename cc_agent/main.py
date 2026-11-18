import os
import sys
from pathlib import Path

sys.path.append("../..")

# Air-gapped installs: dify_plugin's recalc_llm_max_tokens path calls
# tiktoken.encoding_for_model("gpt2"), which would otherwise download the vocab
# files on first use. Resolve them from the bundled cache instead; tiktoken
# reads TIKTOKEN_CACHE_DIR lazily at call time, so setting it here is enough.
os.environ.setdefault(
    "TIKTOKEN_CACHE_DIR",
    str(Path(__file__).resolve().parent / "_assets" / "tiktoken_cache"),
)

from dify_plugin import DifyPluginEnv, Plugin

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv may be absent in some packaged runtimes
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent / ".env")

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=240, MAX_INVOCATION_TIMEOUT=900))

if __name__ == "__main__":
    plugin.run()
