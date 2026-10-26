import sys
from pathlib import Path

sys.path.append("../..")

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
