from __future__ import annotations

import html
import json
from typing import Any
from uuid import uuid4

from .messages import AgentRunResult


TOOL_CARD_RESULT_MAX_LENGTH = 8000


class DifyNativeWriter:
    """Writer that produces payloads consumed directly by the Dify strategy."""

    def __init__(self, thread_id: str, run_id: str, show_tool_calls: bool = True):
        self.thread_id = thread_id or "default"
        self.run_id = run_id or f"run_{uuid4().hex}"
        self._text_emitted = False
        self.show_tool_calls = bool(show_tool_calls)
        self._tool_inputs: dict[str, dict[str, Any]] = {}
        self._reasoning_open = False

    def write_run_started(self) -> list[dict[str, Any]]:
        return [
            _log(
                "Run started",
                {
                    "threadId": self.thread_id,
                    "runId": self.run_id,
                },
            )
        ]

    def write_reasoning_delta(self, text: Any, iteration: int = 0) -> list[dict[str, Any]]:
        value = _non_empty_text(text)
        if value is None:
            return []
        content = _think_delta_text(value)
        if not self._reasoning_open:
            self._reasoning_open = True
            content = "<think>" + content
        return [{"type": "dify_text", "content": content}]

    def write_text_delta(self, text: Any, iteration: int = 0) -> list[dict[str, Any]]:
        value = _non_empty_text(text)
        if value is None:
            return []
        self._text_emitted = True
        return [{"type": "dify_text", "content": self._close_reasoning_prefix() + value}]

    def write_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._tool_inputs[str(tool_call_id or "")] = arguments if isinstance(arguments, dict) else {}
        return []

    def write_tool_result(
        self,
        tool_call_id: str,
        tool_name: str = "",
        observation: Any = None,
        *,
        output: Any = None,
        is_error: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.show_tool_calls:
            return []
        name = str(tool_name or "unknown_tool")
        tc_id = str(tool_call_id or "")
        metadata = metadata if isinstance(metadata, dict) else {}
        arguments = self._tool_inputs.get(tc_id)
        if arguments is None:
            parameters = metadata.get("parameters")
            arguments = parameters if isinstance(parameters, dict) else {}
        result = observation if observation is not None else output
        return [{"type": "dify_text", "content": self._close_reasoning_prefix() + _tool_card(name, arguments, result, is_error=is_error)}]

    def write_custom(self, name: str, value: Any) -> list[dict[str, Any]]:
        return [_log(str(name or "custom"), {"value": value})]

    def write_activity(self, activity_type: str, content: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [
            _log(
                str(activity_type or "Activity"),
                {
                    "activityType": str(activity_type or "activity"),
                    "content": content if isinstance(content, dict) else {},
                },
            )
        ]

    def write_run_finished(self, result: Any) -> list[dict[str, Any]]:
        payload = _result_payload(result)
        events = []
        error_text = _finished_error_text(result)
        if error_text:
            events.append({"type": "dify_text", "content": self._close_reasoning_prefix() + error_text})
        elif self._reasoning_open:
            events.append({"type": "dify_text", "content": self._close_reasoning_prefix()})
        events.append(_log("Run finished", payload))
        return events

    def write_run_error(self, message: Any, code: str | None = None) -> list[dict[str, Any]]:
        text = str(message or "Agent run failed")
        return [
            _log(
                "Run error",
                {
                    "message": text,
                    "code": str(code) if code else None,
                },
                is_error=True,
            ),
            {"type": "dify_text", "content": self._close_reasoning_prefix() + f"Agent run failed: {text}"},
        ]

    def close_reasoning(self) -> list[dict[str, Any]]:
        closing = self._close_reasoning_prefix()
        return [{"type": "dify_text", "content": closing}] if closing else []

    def close_text(self) -> list[dict[str, Any]]:
        return []

    def close_open_messages(self) -> list[dict[str, Any]]:
        return []

    def _close_reasoning_prefix(self) -> str:
        if not self._reasoning_open:
            return ""
        self._reasoning_open = False
        return "</think>"


def _log(label: str, raw: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "type": "dify_log",
        "label": label,
        "data": {
            "raw": raw,
            "html": _details(label, raw),
        },
        "is_error": bool(is_error),
    }


def _details(summary: str, value: Any) -> str:
    safe_summary = html.escape(str(summary or "Log"))
    safe_body = html.escape(_json_pretty(value))
    return f"<details><summary>{safe_summary}</summary><pre>{safe_body}</pre></details>"


def _finished_error_text(result: Any) -> str | None:
    metadata = getattr(result, "execution_metadata", None)
    if not isinstance(metadata, dict):
        return None
    finish_reason = str(metadata.get("finish_reason") or "")
    if finish_reason not in {"model_error", "context_overflow"} and not finish_reason.endswith("_error"):
        return None
    error = _truncate(str(metadata.get("error") or "unknown error"), 2000)
    if finish_reason == "context_overflow":
        return f"上下文超过模型限制，已停止本次调用：{error}"
    return f"模型调用失败：{error}"


def _think_delta_text(value: str) -> str:
    text = str(value or "")
    stripped = text.strip()
    if stripped.startswith("<think>") and stripped.endswith("</think>"):
        start = text.find("<think>") + len("<think>")
        end = text.rfind("</think>")
        return text[start:end]
    if stripped.startswith("<think>"):
        start = text.find("<think>") + len("<think>")
        return text[start:]
    if stripped.endswith("</think>"):
        end = text.rfind("</think>")
        return text[:end]
    return text


def _tool_card(tool_name: str, arguments: dict[str, Any], result: Any, is_error: bool = False) -> str:
    safe_name = html.escape(str(tool_name or "unknown_tool"))
    safe_params = html.escape(_json_pretty(arguments if isinstance(arguments, dict) else {}))
    safe_result = html.escape(_truncate(_display_text(result)))
    title = "运行失败" if is_error else "已运行"
    result_label = "错误" if is_error else "结果"
    body = f"参数:\n{safe_params}\n\n{result_label}:\n{safe_result}"
    return (
    '<div style="margin: 12px 0; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif;">'
        '<details style="width: 100%;">'
            
            # 【优化1】使用 display: flex 强行覆盖原生的 list-item 属性，隐藏原生黑三角，并让内容完美垂直居中
            '<summary style="padding: 10px 16px; background-color: rgba(128, 128, 128, 0.04); cursor: pointer; display: flex; align-items: center; gap: 8px; list-style: none; outline: none; user-select: none;">'
                
                # 状态绿点
                '<span style="display: block; width: 6px; height: 6px; border-radius: 50%; background-color: #10b981; box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2); flex-shrink: 0;"></span>'
                
                # 标题
                f'<span style="font-weight: 600; font-size: 13px; opacity: 0.9;">{title}</span>'
                
                # 徽章 (还原了你原版的 999px 胶囊圆角，加上截图里的 >_ 符号，并配上靛蓝色透明质感)
                '<span style="display: inline-flex; align-items: center; padding: 2px 10px; background-color: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.15); border-radius: 999px; color: #6366f1; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; font-weight: 600;">'
                    '>_&nbsp;' f'{safe_name}'
                '</span>'
                
            '</summary>'
            
            # 内容区域包裹
            '<div style="padding: 16px; border-top: 1px solid rgba(128, 128, 128, 0.15); background-color: rgba(128, 128, 128, 0.015); display: flex; flex-direction: column; gap: 14px;">'
                
                # 【优化2】恢复你原版的 参数(Params) 模块
                '<div>'
                    '<div style="font-size: 12px; font-weight: 600; opacity: 0.55; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">'
                        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>'
                        '参数 (Params)'
                    '</div>'
                    f'<pre style="margin: 0; padding: 10px 12px; background-color: rgba(128, 128, 128, 0.05); border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; opacity: 0.85;">{safe_params}</pre>'
                '</div>'
                
                # 【优化3】恢复你原版的 结果(Result) 模块，并赋予其轻微的绿色高亮，暗示执行成功
                '<div>'
                    '<div style="font-size: 12px; font-weight: 600; opacity: 0.55; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">'
                        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>'
                        '结果 (Result)'
                    '</div>'
                    f'<pre style="margin: 0; padding: 10px 12px; background-color: rgba(16, 185, 129, 0.04); border-left: 3px solid rgba(16, 185, 129, 0.4); border-radius: 0 6px 6px 0; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; opacity: 0.9;">{safe_result}</pre>'
                '</div>'
                
            '</div>'
            
        '</details>'
    '</div>'
)


def _display_text(value: Any) -> str:
    if value is None:
        return "(tool completed with no output)"
    if isinstance(value, str):
        return value
    return _json_pretty(value)


def _truncate(value: str, limit: int = TOOL_CARD_RESULT_MAX_LENGTH) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_pretty(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(value)


def _result_payload(result: Any) -> Any:
    if isinstance(result, AgentRunResult):
        return result.to_json_payload()
    if hasattr(result, "to_json_payload"):
        return result.to_json_payload()
    return result


def _non_empty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
