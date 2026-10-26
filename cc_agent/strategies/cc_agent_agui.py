from __future__ import annotations

try:
    from core import profiles as _profiles
    from strategies import base as _base
except ImportError:  # pragma: no cover - used by local tests/imports
    from cc_agent.core import profiles as _profiles
    from cc_agent.strategies import base as _base


class CCAgentAgUiStrategy(_base.BaseCCAgentStrategy):
    strategy_profile = _profiles.AGUI_STRATEGY_PROFILE