from __future__ import annotations

from typing import Any


def commit_workspace(session: Any) -> dict[str, Any]:
    session.commit()
    return session.activity_payload()
