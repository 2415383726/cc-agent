from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

TASK_STATUSES = ("pending", "in_progress", "completed", "canceled")
TASK_UPDATE_STATUSES = (*TASK_STATUSES, "deleted")

_STATUS_ALIASES = {
    "open": "pending",
    "todo": "pending",
    "queued": "pending",
    "started": "in_progress",
    "in-progress": "in_progress",
    "in progress": "in_progress",
    "working": "in_progress",
    "done": "completed",
    "resolved": "completed",
    "complete": "completed",
    "finished": "completed",
    "cancelled": "canceled",
    "cancel": "canceled",
    "blocked": "pending",
}


def load_tasks(value: str | list[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = _load_json_like(value)
    if isinstance(payload, dict):
        payload = payload.get("tasks", [])
    if not isinstance(payload, list):
        return []
    return [_normalize_task(item) for item in payload if isinstance(item, dict)]


def create_task(tasks: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    task_id = str(_first_value(data, ["task_id", "taskId", "id"]) or _next_task_id(tasks))
    now = _now()
    subject = str(_first_value(data, ["subject", "title", "name", "content"]) or "Untitled task")
    task = {
        "id": task_id,
        "subject": subject,
        "title": subject,
        "description": str(data.get("description") or ""),
        "status": normalize_status(data.get("status"), default="pending"),
        "active_form": str(_first_value(data, ["active_form", "activeForm"]) or ""),
        "owner": str(data.get("owner") or ""),
        "blocks": _string_list(data.get("blocks")),
        "blocked_by": _string_list(_first_value(data, ["blocked_by", "blockedBy"])),
        "metadata": data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        "created_at": str(data.get("created_at") or now),
        "updated_at": str(data.get("updated_at") or now),
    }
    for key, value in data.items():
        if key not in _RESERVED_INPUT_KEYS and key not in task:
            task[key] = value
    tasks.append(task)
    _replace_blocks(tasks, task, task["blocks"])
    _replace_blocked_by(tasks, task, task["blocked_by"])
    return task


def update_task(tasks: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    task = _find_task(tasks, data, include_deleted=True)
    if task is None:
        task_id = str(_first_value(data, ["task_id", "taskId", "id"]) or "")
        title = str(_first_value(data, ["title", "subject"]) or "")
        raise KeyError(f"task not found: {task_id or title}")

    _normalize_task_in_place(task)
    changed = False

    if _has_any(data, ["subject", "title"]):
        subject = str(_first_value(data, ["subject", "title"]) or task.get("subject") or "")
        if subject and subject != task.get("subject"):
            task["subject"] = subject
            task["title"] = subject
            changed = True

    if "description" in data and str(data.get("description") or "") != task.get("description"):
        task["description"] = str(data.get("description") or "")
        changed = True

    if _has_any(data, ["active_form", "activeForm"]):
        active_form = str(_first_value(data, ["active_form", "activeForm"]) or "")
        if active_form != task.get("active_form"):
            task["active_form"] = active_form
            changed = True

    if "owner" in data and str(data.get("owner") or "") != task.get("owner"):
        task["owner"] = str(data.get("owner") or "")
        changed = True

    if "metadata" in data and isinstance(data.get("metadata"), dict):
        metadata = dict(task.get("metadata") or {})
        for key, value in data["metadata"].items():
            if value is None:
                metadata.pop(str(key), None)
            else:
                metadata[str(key)] = value
        if metadata != task.get("metadata"):
            task["metadata"] = metadata
            changed = True

    if "status" in data:
        status = normalize_status(data.get("status"), default=str(task.get("status") or "pending"))
        if status == "deleted":
            delete_task(tasks, str(task.get("id") or ""))
            return task
        if status != task.get("status"):
            task["status"] = status
            changed = True

    if "blocks" in data:
        changed = _replace_blocks(tasks, task, _string_list(data.get("blocks"))) or changed
    if _has_any(data, ["blocked_by", "blockedBy"]):
        changed = _replace_blocked_by(tasks, task, _string_list(_first_value(data, ["blocked_by", "blockedBy"]))) or changed
    if _has_any(data, ["add_blocks", "addBlocks"]):
        changed = _add_blocks(tasks, task, _string_list(_first_value(data, ["add_blocks", "addBlocks"]))) or changed
    if _has_any(data, ["add_blocked_by", "addBlockedBy"]):
        changed = _add_blocked_by(
            tasks,
            task,
            _string_list(_first_value(data, ["add_blocked_by", "addBlockedBy"])),
        ) or changed

    for key, value in data.items():
        if key not in _RESERVED_INPUT_KEYS and key not in task:
            task[key] = value
            changed = True

    if changed or data:
        task["updated_at"] = _now()
    return task


def get_task(tasks: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    task = _find_task(tasks, data, include_deleted=False)
    if task is not None:
        return _normalize_task_in_place(task)
    task_id = str(_first_value(data, ["task_id", "taskId", "id"]) or "")
    title = str(_first_value(data, ["title", "subject"]) or "")
    raise KeyError(f"task not found: {task_id or title}")


def list_tasks(tasks: list[dict[str, Any]], include_deleted: bool = False) -> list[dict[str, Any]]:
    visible = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        normalized = _normalize_task_in_place(task)
        if not include_deleted and normalized.get("status") == "deleted":
            continue
        visible.append(normalized)
    return visible


def delete_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    task = _find_task_by_id(tasks, task_id, include_deleted=True)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    _normalize_task_in_place(task)
    task["status"] = "deleted"
    task["blocks"] = []
    task["blocked_by"] = []
    task["updated_at"] = _now()
    for other in tasks:
        if not isinstance(other, dict) or other is task:
            continue
        _normalize_task_in_place(other)
        other["blocks"] = [item for item in other.get("blocks", []) if item != task_id]
        other["blocked_by"] = [item for item in other.get("blocked_by", []) if item != task_id]
    return task


def format_task_detail(task: dict[str, Any]) -> str:
    task = _normalize_task(dict(task))
    lines = [
        f"Task #{task.get('id')}: {task.get('subject')}",
        f"Status: {task.get('status')}",
        f"Description: {task.get('description') or ''}",
    ]
    if task.get("owner"):
        lines.append(f"Owner: {task.get('owner')}")
    if task.get("active_form"):
        lines.append(f"Active form: {task.get('active_form')}")
    if task.get("blocked_by"):
        lines.append("Blocked by: " + ", ".join(f"#{item}" for item in task["blocked_by"]))
    if task.get("blocks"):
        lines.append("Blocks: " + ", ".join(f"#{item}" for item in task["blocks"]))
    if task.get("metadata"):
        lines.append("Metadata: " + json.dumps(task["metadata"], ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def format_task_list(tasks: list[dict[str, Any]]) -> str:
    visible = list_tasks(tasks)
    if not visible:
        return "No tasks found"
    completed = {str(task.get("id")) for task in visible if task.get("status") == "completed"}
    lines = []
    for task in visible:
        blockers = [item for item in task.get("blocked_by", []) if item not in completed]
        owner = f" ({task.get('owner')})" if task.get("owner") else ""
        blocked = f" [blocked by {', '.join(f'#{item}' for item in blockers)}]" if blockers else ""
        lines.append(f"#{task.get('id')} [{task.get('status')}] {task.get('subject')}{owner}{blocked}")
    return "\n".join(lines)


def normalize_status(value: Any, default: str = "pending") -> str:
    if value in (None, ""):
        return default
    status = str(value).strip().lower()
    status = _STATUS_ALIASES.get(status, status)
    if status in TASK_UPDATE_STATUSES:
        return status
    return default


def _next_task_id(tasks: list[dict[str, Any]]) -> str:
    numbers = []
    for task in tasks:
        try:
            numbers.append(int(str(task.get("id"))))
        except (TypeError, ValueError):
            continue
    return str((max(numbers) if numbers else 0) + 1)


def _find_task(tasks: list[dict[str, Any]], data: dict[str, Any], include_deleted: bool = False) -> dict[str, Any] | None:
    task_id = str(_first_value(data, ["task_id", "taskId", "id"]) or "")
    title = str(_first_value(data, ["title", "subject"]) or "")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        _normalize_task_in_place(task)
        if not include_deleted and task.get("status") == "deleted":
            continue
        if str(task.get("id") or "") == task_id:
            return task
        if title and (task.get("title") == title or task.get("subject") == title):
            return task
    return None


def _find_task_by_id(tasks: list[dict[str, Any]], task_id: str, include_deleted: bool = False) -> dict[str, Any] | None:
    for task in tasks:
        if not isinstance(task, dict):
            continue
        _normalize_task_in_place(task)
        if str(task.get("id") or "") == str(task_id):
            if include_deleted or task.get("status") != "deleted":
                return task
    return None


def _resolve_task_ref(tasks: list[dict[str, Any]], value: Any) -> str:
    ref = str(value)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        _normalize_task_in_place(task)
        if ref in {str(task.get("id") or ""), str(task.get("subject") or ""), str(task.get("title") or "")}:
            return str(task.get("id") or ref)
    return ref


def _replace_blocks(tasks: list[dict[str, Any]], task: dict[str, Any], values: Any) -> bool:
    task_id = str(task.get("id") or "")
    old = set(_string_list(task.get("blocks")))
    new = _unique_strings(_resolve_task_ref(tasks, item) for item in _string_list(values))
    for blocked_id in old:
        _remove_dependency(tasks, task_id, blocked_id)
    changed = _string_list(task.get("blocks")) != new
    task["blocks"] = []
    for blocked_id in new:
        _add_dependency(tasks, task_id, blocked_id)
    return changed or set(new) != old


def _replace_blocked_by(tasks: list[dict[str, Any]], task: dict[str, Any], values: Any) -> bool:
    task_id = str(task.get("id") or "")
    old = set(_string_list(task.get("blocked_by")))
    new = _unique_strings(_resolve_task_ref(tasks, item) for item in _string_list(values))
    for blocker_id in old:
        _remove_dependency(tasks, blocker_id, task_id)
    changed = _string_list(task.get("blocked_by")) != new
    task["blocked_by"] = []
    for blocker_id in new:
        _add_dependency(tasks, blocker_id, task_id)
    return changed or set(new) != old


def _add_blocks(tasks: list[dict[str, Any]], task: dict[str, Any], values: Any) -> bool:
    changed = False
    task_id = str(task.get("id") or "")
    for value in _string_list(values):
        changed = _add_dependency(tasks, task_id, _resolve_task_ref(tasks, value)) or changed
    return changed


def _add_blocked_by(tasks: list[dict[str, Any]], task: dict[str, Any], values: Any) -> bool:
    changed = False
    task_id = str(task.get("id") or "")
    for value in _string_list(values):
        changed = _add_dependency(tasks, _resolve_task_ref(tasks, value), task_id) or changed
    return changed


def _add_dependency(tasks: list[dict[str, Any]], blocker_id: str, blocked_id: str) -> bool:
    changed = False
    blocker = _find_task_by_id(tasks, blocker_id, include_deleted=True)
    blocked = _find_task_by_id(tasks, blocked_id, include_deleted=True)
    if blocker is not None and blocked_id not in blocker.get("blocks", []):
        blocker["blocks"].append(blocked_id)
        changed = True
    if blocked is not None and blocker_id not in blocked.get("blocked_by", []):
        blocked["blocked_by"].append(blocker_id)
        changed = True
    return changed


def _remove_dependency(tasks: list[dict[str, Any]], blocker_id: str, blocked_id: str) -> bool:
    changed = False
    blocker = _find_task_by_id(tasks, blocker_id, include_deleted=True)
    blocked = _find_task_by_id(tasks, blocked_id, include_deleted=True)
    if blocker is not None:
        before = list(blocker.get("blocks", []))
        blocker["blocks"] = [item for item in before if item != blocked_id]
        changed = changed or blocker["blocks"] != before
    if blocked is not None:
        before = list(blocked.get("blocked_by", []))
        blocked["blocked_by"] = [item for item in before if item != blocker_id]
        changed = changed or blocked["blocked_by"] != before
    return changed


def _load_json_like(value: Any) -> Any:
    if not value:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value


def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    return _normalize_task_in_place(dict(task))


def _normalize_task_in_place(task: dict[str, Any]) -> dict[str, Any]:
    subject = str(task.get("subject") or task.get("title") or task.get("name") or task.get("content") or "Untitled task")
    task["id"] = str(task.get("id") or "")
    task["subject"] = subject
    task["title"] = str(task.get("title") or subject)
    task["description"] = str(task.get("description") or "")
    task["status"] = normalize_status(task.get("status"), default="pending")
    task["active_form"] = str(task.get("active_form") or task.get("activeForm") or "")
    task["owner"] = str(task.get("owner") or "")
    task["blocks"] = _string_list(task.get("blocks"))
    task["blocked_by"] = _string_list(task.get("blocked_by") if "blocked_by" in task else task.get("blockedBy"))
    task["metadata"] = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    task.setdefault("created_at", "")
    task.setdefault("updated_at", "")
    return task


def _string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return _unique_strings(str(item) for item in value if item not in (None, ""))
    return [str(value)]


def _unique_strings(values: Any) -> list[str]:
    result = []
    seen = set()
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _first_value(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _has_any(data: dict[str, Any], keys: list[str]) -> bool:
    return any(key in data for key in keys)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_RESERVED_INPUT_KEYS = {
    "id",
    "task_id",
    "taskId",
    "subject",
    "title",
    "name",
    "content",
    "description",
    "status",
    "active_form",
    "activeForm",
    "owner",
    "blocks",
    "blocked_by",
    "blockedBy",
    "add_blocks",
    "addBlocks",
    "add_blocked_by",
    "addBlockedBy",
    "metadata",
    "created_at",
    "updated_at",
}
