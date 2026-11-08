import sys
from pathlib import Path

sys.path.append("../..")

from dify_plugin import DifyPluginEnv, Plugin

try:
    from pi_agent.runtime import install_atomic_stdout
except ImportError:  # pragma: no cover - packaged runtime keeps the package root on sys.path
    install_atomic_stdout = None  # type: ignore[assignment]

# Pi runs own an OS thread each (see RunStream); without this the SDK's separate
# write/flush calls can merge two JSON frames into a single line.
if install_atomic_stdout is not None:
    install_atomic_stdout()

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv may be absent in packaged runtimes
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent / ".env")

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=240, MAX_INVOCATION_TIMEOUT=900))

if __name__ == "__main__":
    plugin.run()
