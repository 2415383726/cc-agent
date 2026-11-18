"""Dify-host orchestration around the Pi harness."""

from __future__ import annotations

import asyncio
import collections
import logging
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pi_agent_core.messages import ToolResultMessage
from pi_agent_core.types import Model, StreamOptions
from pi_agent_harness.compaction import CompactionSettings, compact_preparation, prepare_compaction
from pi_agent_harness.messages import CustomMessage
from pi_agent_harness.session.memory_storage import MemorySessionStorage
from pi_agent_harness.session.session import Session
from pi_agent_harness.types import AgentHarnessResources, SessionMetadata, SessionTreeEntry

from .artifacts import Artifact
from .budget import RunLedger
from .config import RequestContext, RuntimeConfig, parse_request
from .errors import PiError
from .harness import PiHarness
from .mcp import McpRuntime, parse_servers
from .native import NativeEvents, clip, native_log, public_state_ref, run_state_payload
from .observer import NativeObserver
from .session_io import SessionIO
from .skills import SkillCatalog
from .state import (
    PiState,
    build_storage,
    decode_state,
    encode_state,
    export_session,
    now_iso,
    sanitize_entries,
    state_summary,
)
from .stream import DifyModelStream, error_code_from_message
from .threads import start_real_thread, stdlib_original
from .tools import ToolRuntime

_SENTINEL = object()


def _start_worker_thread(target: Any) -> None:
    """Start ``target`` on a genuine OS thread.

    ``threading.Thread.start`` is not enough: the host's gevent patch also
    replaces ``_thread.start_new_thread``, so even a pre-patch Thread body would
    run as a greenlet inside the hub thread and inherit that thread's asyncio
    state.
    """
    start_real_thread(target, name="pi-strategy-run")


def install_atomic_stdout() -> None:
    """Make each stdout frame an atomic write+flush.

    The SDK emits one JSON frame per response with separate ``write``/``flush``
    calls. That is safe while everything runs on the host greenlet, but a Pi run
    owns its own OS thread for asyncio, so two threads can interleave and merge
    two frames into one line, which the daemon then rejects as malformed JSON.
    """
    stream = sys.stdout
    if getattr(stream, "_pi_atomic", False):
        logging.getLogger("pi_strategy.runtime").info("atomic stdout already installed")
        return
    allocate_lock = stdlib_original("_thread", "allocate_lock")
    lock = allocate_lock() if allocate_lock is not None else threading.Lock()

    class _AtomicStdout:
        _pi_atomic = True

        def write(self, data: str) -> int:
            with lock:
                written = stream.write(data)
                stream.flush()
            return len(data) if written is None else written

        def flush(self) -> None:
            with lock:
                stream.flush()

        def __getattr__(self, name: str) -> Any:
            return getattr(stream, name)

    wrapper = _AtomicStdout()
    sys.stdout = wrapper  # type: ignore[assignment]
    # Handlers captured the original stream at import time; rebind them so log
    # lines share the same frame lock as protocol responses.
    for logger_name in ("", "pi_strategy.runtime"):
        for handler in logging.getLogger(logger_name).handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and getattr(handler, "stream", None) is stream
            ):
                handler.setStream(wrapper)
    logging.getLogger("pi_strategy.runtime").info(
        "atomic stdout installed (real_lock=%s, stream=%s)",
        allocate_lock is not None,
        type(stream).__name__,
    )
    # Belt and braces: the SDK writer is the only protocol frame producer, so
    # locking it also covers any path that holds a different stream object.
    try:
        from dify_plugin.core.server.stdio.response_writer import (  # type: ignore[import-not-found]
            StdioResponseWriter,
        )

        def _atomic_write(self: Any, data: str) -> None:
            with lock:
                stream.write(data)
                stream.flush()

        StdioResponseWriter.write = _atomic_write  # type: ignore[method-assign]
        logging.getLogger("pi_strategy.runtime").info("sdk stdio writer locked")
    except Exception:
        logging.getLogger("pi_strategy.runtime").info("sdk stdio writer patch unavailable")


class RunStream:
    """Synchronous iterator over a background asyncio run.

    Dify's AgentStrategy API is a sync generator. The Pi harness is async, so one
    request owns one OS thread and one event loop; the Dify session is only
    touched on that thread. Closing the iterator cooperatively aborts the run.

    Items cross from the run thread to the consuming greenlet through a deque
    polled with a cooperative sleep: a stdlib ``queue.Queue.get`` would block the
    host's gevent hub, while gevent's own queue cannot be used across threads.
    """

    POLL_SECONDS = 0.01

    def __init__(self, runtime: PiStrategyRuntime, parameters: dict[str, Any]):
        self._runtime = runtime
        self._parameters = parameters
        self._items: collections.deque[Any] = collections.deque()
        self.run_id = f"run_{uuid4().hex[:20]}"
        self._stop = threading.Event()
        self._finished = False
        self._started = False

    def __iter__(self) -> RunStream:
        return self

    def __next__(self) -> dict[str, Any]:
        if not self._started:
            self._started = True
            _start_worker_thread(self._target)
        while True:
            try:
                item = self._items.popleft()
            except IndexError:
                if self._finished:
                    raise StopIteration from None
                # Cooperative under the host's gevent patch, a plain sleep otherwise.
                time.sleep(self.POLL_SECONDS)
                continue
            if item is _SENTINEL:
                raise StopIteration
            if isinstance(item, BaseException):
                raise item
            return item

    def _emit(self, item: Any) -> None:
        # deque.append is atomic under the GIL and safe across OS threads.
        self._items.append(item)

    def _target(self) -> None:
        try:
            asyncio.run(
                self._runtime.execute_async(
                    self._parameters, self._emit, self._stop, run_id=self.run_id
                )
            )
        except BaseException:
            # Crash diagnostics: the strategy emits safe failure events downstream,
            # so without this log the root cause never reaches any surface. The
            # traceback goes into the message body because the daemon-visible
            # formatter only renders record.getMessage().
            logging.getLogger("pi_strategy.runtime").error(
                "pi_strategy run %s crashed in worker thread:\n%s",
                self.run_id,
                traceback.format_exc(),
            )
            self._emit(_safe_failure_message("agent_failed", "runtime", run_id=self.run_id))
            self._emit({"type": "text", "content": "The Pi agent run failed."})
        finally:
            self._emit(_SENTINEL)
            self._finished = True

    def close(self) -> None:
        self._stop.set()
        if not self._started:
            return
        # Never join from a greenlet: a blocking join would stall the host's hub
        # for the whole timeout, so wait cooperatively instead.
        deadline = time.monotonic() + 5.0
        while not self._finished and time.monotonic() < deadline:
            time.sleep(0.05)


@dataclass(slots=True)
class _Setup:
    harness: PiHarness
    stream: DifyModelStream
    tools: ToolRuntime
    observer: NativeObserver
    model: Model
    skills: SkillCatalog
    mcp: McpRuntime | None
    io: SessionIO
    session_storage: MemorySessionStorage
    compaction: CompactionSettings


class PiStrategyRuntime:
    def __init__(self, session: Any):
        self.session = session
        self._harness: PiHarness | None = None
        self._stop: threading.Event | None = None
        self._stopped = False

    # -- public API ---------------------------------------------------------

    def run(self, parameters: dict[str, Any]) -> RunStream:
        return RunStream(self, parameters)

    async def execute_async(
        self, parameters: dict[str, Any], emit: Any, stop: threading.Event, *, run_id: str = ""
    ) -> None:
        self._stop = stop
        watcher = asyncio.create_task(self._watch_stop(stop))
        request: RequestContext | None = None
        events: NativeEvents | None = None
        ledger: RunLedger | None = None
        state: PiState | None = None
        setup: _Setup | None = None
        try:
            request = parse_request(parameters)
            events = NativeEvents(run_id=run_id or f"run_{uuid4().hex[:20]}")
            ledger = RunLedger(request.runtime, events.run_id)
            _run_log(
                events,
                emit,
                "Run started",
                {"conversation_id": request.conversation_id, "run_id": events.run_id},
            )
            load = decode_state(request.agent_state)
            if load.error:
                await self._fail(
                    request,
                    None,
                    events,
                    emit,
                    ledger,
                    PiError("invalid_state", "state", load.error),
                )
                return
            state = load.state or PiState.fresh(request.session_id)
            if (
                state.session_id
                and request.conversation_id
                and state.session_id != request.conversation_id
            ):
                await self._fail(
                    request,
                    None,
                    events,
                    emit,
                    ledger,
                    PiError(
                        "invalid_state", "state", "The saved state belongs to another conversation."
                    ),
                )
                return
            state.session_id = state.session_id or request.session_id
            state.run_id = events.run_id

            setup = await self._setup(request, state, events, emit, ledger)
            if setup is None:
                return
            await self._execute_turn(request, state, setup, events, emit, ledger)
        except asyncio.CancelledError:
            # A host stop cancels the running task; CancelledError is a
            # BaseException and must not fall through to the crash path, which
            # would skip state saving. Finish as a cooperative stop instead.
            # Found live: stopping while MCP setup was still opening produced
            # "The Pi agent run failed." with no state saved.
            logging.getLogger("pi_strategy.runtime").info(
                "pi_strategy run %s cancelled by host stop", events.run_id if events else ""
            )
            if request is not None and events is not None and ledger is not None:
                try:
                    await asyncio.shield(
                        self._finalize(
                            request,
                            state,
                            events,
                            emit,
                            ledger,
                            status="stopped",
                            answer="The run was stopped. Completed tool results were preserved.",
                            error=None,
                            setup=setup,
                        )
                    )
                except asyncio.CancelledError:
                    pass
            else:
                emit(
                    _safe_failure_message(
                        "agent_failed",
                        "runtime",
                        run_id=events.run_id if events is not None else "",
                    )
                )
        except PiError as exc:
            logging.getLogger("pi_strategy.runtime").error(
                "pi_strategy run %s hit PiError: %s (code=%s stage=%s)\n%s",
                events.run_id if events else "",
                exc.message,
                exc.code,
                exc.stage,
                traceback.format_exc(),
            )
            if request is not None and events is not None and ledger is not None:
                await self._fail(request, state, events, emit, ledger, exc)
            else:
                emit(
                    _safe_failure_message(
                        exc.code, exc.stage, run_id=events.run_id if events is not None else ""
                    )
                )
        except Exception:
            logging.getLogger("pi_strategy.runtime").error(
                "pi_strategy run %s failed in execute_async:\n%s",
                events.run_id if events else "",
                traceback.format_exc(),
            )
            if request is not None and events is not None and ledger is not None:
                await self._fail(
                    request,
                    state,
                    events,
                    emit,
                    ledger,
                    PiError("agent_failed", "runtime", "The Pi agent run failed."),
                )
            else:
                emit(
                    _safe_failure_message(
                        "agent_failed",
                        "runtime",
                        run_id=events.run_id if events is not None else "",
                    )
                )
        finally:
            watcher.cancel()
            if setup is not None:
                await setup.stream.close()
                try:
                    await setup.harness.close()
                except Exception:
                    pass
                if setup.mcp is not None:
                    await setup.mcp.close()
            self._harness = None

    # -- setup --------------------------------------------------------------

    async def _setup(
        self,
        request: RequestContext,
        state: PiState,
        events: NativeEvents,
        emit: Any,
        ledger: RunLedger,
    ) -> _Setup | None:
        if request.model is None:
            await self._fail(
                request,
                state,
                events,
                emit,
                ledger,
                PiError("invalid_configuration", "config", "A Dify model is required."),
            )
            return None
        try:
            servers = parse_servers(request.mcp_servers_config)
        except PiError as exc:
            await self._fail(request, state, events, emit, ledger, exc)
            return None
        mcp = McpRuntime(servers, request.runtime)
        if servers:
            try:
                await mcp.open()
            except Exception:
                await mcp.close()
                await self._fail(
                    request,
                    state,
                    events,
                    emit,
                    ledger,
                    PiError("invalid_configuration", "mcp", "Remote MCP connection failed."),
                )
                return None

        try:
            observer = NativeObserver(events, emit, request.runtime)
            # One bridge per run: every blocking Dify session call goes through
            # it so a stalled provider or tool can be abandoned on stop.
            session_io = SessionIO()
            skills = SkillCatalog.load(
                app_yaml=request.app_skills_yaml,
                builtin_dir=Path(__file__).resolve().parent.parent / "skills",
                available_tools=self._available_tool_names(request.tools, mcp),
            )
            if skills.diagnostics:
                observer.activity(
                    "activity",
                    {
                        "activity": "skills.discovered",
                        "count": len(skills.eligible()),
                        "diagnostics": len(skills.diagnostics),
                    },
                )
            for error in mcp.errors:
                observer.activity("mcp.error", error)

            artifacts: list[Artifact] = []

            def artifact_sink(artifact: Artifact) -> dict[str, Any]:
                artifact.id = f"art_{events.run_id}_{len(artifacts) + 1}"
                artifacts.append(artifact)
                meta = {
                    "filename": artifact.name,
                    "mime_type": artifact.mime_type,
                    "size": artifact.size,
                }
                if artifact.data is not None:
                    emit({"type": "blob", "blob": artifact.data, "meta": meta})
                return artifact.public()

            tools = ToolRuntime(
                session=self.session,
                config=request.runtime,
                ledger=ledger,
                skills=skills,
                mcp=mcp,
                artifact_sink=artifact_sink,
                activity_sink=observer.activity,
                dify_tools=request.tools,
                stop_requested=self._stop_requested,
                session_io=session_io,
            )
            # Re-check active skills against current eligibility.
            eligible = skills.eligible_names()
            state.active_skills = [
                skill for skill in state.active_skills if str(skill.get("name")) in eligible
            ]
            storage = build_storage(state)
            model = _model_from_request(request, request.runtime)
            stream = DifyModelStream(
                session=self.session,
                model_config=request.model,
                ledger=ledger,
                config=request.runtime,
                model=model,
                thinking_tags=request.runtime.thinking_tags,
                preserve_reasoning_content=request.runtime.preserve_reasoning_content,
                stop_requested=self._stop_requested,
                io=session_io,
            )
            system_prompt = _system_prompt(request, skills)
            compaction = CompactionSettings(
                enabled=request.runtime.compaction_enabled,
                reserve_tokens=request.runtime.compaction_reserve_tokens,
                keep_recent_tokens=request.runtime.compaction_keep_recent_tokens,
                auto_compact=request.runtime.auto_compact,
            )
            setup = _Setup(
                harness=None,  # type: ignore[arg-type]
                stream=stream,
                tools=tools,
                observer=observer,
                model=model,
                skills=skills,
                mcp=mcp,
                io=session_io,
                session_storage=storage,
                compaction=compaction,
            )
            setup.harness = self._make_harness(
                setup, storage, request, events, emit, ledger, system_prompt
            )
            return setup

        except BaseException:
            await mcp.close()
            raise

    def _make_harness(
        self,
        setup: _Setup,
        storage: MemorySessionStorage,
        request: RequestContext,
        events: NativeEvents,
        emit: Any,
        ledger: RunLedger,
        system_prompt: str,
    ) -> PiHarness:
        session = Session(storage)
        harness = PiHarness(
            session=session,
            model=setup.model,
            stream_fn=setup.stream,
            tools=setup.tools.agent_tools(),
            resources=AgentHarnessResources(skills=setup.skills.pi_skills()),
            system_prompt=system_prompt,
            compaction=setup.compaction,
            max_turns=max(4, request.runtime.max_model_requests + 2),
            tool_timeout=request.runtime.tool_timeout_seconds,
            stop_predicate=lambda: ledger.exhausted() or self._stop_requested(),
        )
        harness.subscribe(setup.observer)
        harness.on("tool_result", _tool_result_error_hook)
        harness.on("context", _skill_context_hook(setup.skills))
        self._harness = harness
        setup.harness = harness
        setup.session_storage = storage
        return harness

    def _available_tool_names(self, dify_tools: list[Any], mcp: McpRuntime) -> set[str]:
        from .tools import build_specs

        return {spec.name for spec in build_specs(dify_tools, mcp)}

    # -- turn execution -----------------------------------------------------

    async def _execute_turn(
        self,
        request: RequestContext,
        state: PiState,
        setup: _Setup,
        events: NativeEvents,
        emit: Any,
        ledger: RunLedger,
    ) -> None:
        recovery_used = False
        status: str
        answer = ""
        error: dict[str, Any] | None = None
        retry_mode = "prompt"
        retry_text = request.query
        resume_message: CustomMessage | None = None

        while True:
            try:
                if retry_mode == "resume":
                    if resume_message is None:
                        raise PiError("agent_failed", "runtime", "The continuation is missing.")
                    assistant = await setup.harness.resume_with(resume_message)
                else:
                    assistant = await self._prompt_with_activation(
                        setup, request, retry_text, events, emit
                    )
            except Exception:
                if self._stop_requested():
                    # A host stop can surface as an aborted harness turn; it is
                    # a cooperative stop, not a failure.
                    status = "stopped"
                    answer = "The run was stopped. Completed tool results were preserved."
                    break
                status = "failed"
                error = {
                    "code": "agent_failed",
                    "stage": "runtime",
                    "message": "The Pi agent run failed.",
                }
                break
            code = error_code_from_message(assistant)
            if code == "context_overflow" and not recovery_used:
                recovery_used = True
                retry = await self._recover_overflow(
                    request, setup, events, emit, ledger, retry_mode
                )
                if retry is None:
                    status = "context_overflow"
                    answer = (
                        "The conversation exceeds the model context and could not be recovered."
                    )
                    error = {
                        "code": "context_overflow",
                        "stage": "model",
                        "message": "The context overflow recovery failed.",
                    }
                    break
                try:
                    await setup.harness.close()
                except Exception:
                    pass
                setup.harness = self._make_harness(
                    setup,
                    retry,
                    request,
                    events,
                    emit,
                    ledger,
                    _system_prompt(request, setup.skills),
                )
                if retry_mode != "resume" or resume_message is None:
                    resume_message = CustomMessage(
                        customType="pi.continuation",
                        content=(
                            "The context was compacted after an overflow. Continue the current "
                            "task from the preserved user request and tool results; do not "
                            "repeat completed tool operations."
                        ),
                        display=False,
                        details={"kind": "context_compaction", "reason": "context_overflow"},
                        timestamp=int(time.time() * 1000),
                    )
                    retry_mode = "resume"
                continue
            if code:
                status = _status_for_code(code)
                answer = _answer_for_code(code)
                error = {"code": code, "stage": "model", "message": answer}
            elif self._stopped or (self._stop is not None and self._stop.is_set()):
                status = "stopped"
                answer = "The run was stopped. Completed tool results were preserved."
            elif ledger.finish_reason:
                status = "budget_exhausted"
                answer = _answer_for_code("budget_exhausted")
                error = {
                    "code": "budget_exhausted",
                    "stage": "budget",
                    "message": answer,
                    "reason": ledger.finish_reason,
                }
            else:
                status = "completed"
                answer = _assistant_answer(assistant) or "The run completed without a text answer."
            break

        # Merge skills activated during the run.
        active = {str(item.get("name")): item for item in state.active_skills}
        for activation in setup.tools.activated_skills:
            active[activation["name"]] = {**activation, "activated_at": now_iso()}
        state.active_skills = list(active.values())
        await self._finalize(
            request,
            state,
            events,
            emit,
            ledger,
            status=status,
            answer=answer,
            error=error,
            setup=setup,
        )

    async def _prompt_with_activation(
        self, setup: _Setup, request: RequestContext, query: str, events: NativeEvents, emit: Any
    ) -> Any:
        text = query
        prefix = request.runtime.user_skill_prefix
        if text.lstrip().startswith(prefix):
            head, _, rest = text.lstrip()[len(prefix) :].partition(" ")
            try:
                activation = setup.skills.activate(head.strip(), activated_by="user")
            except PiError as exc:
                setup.observer.activity(
                    "skill.rejected", {"skill": head.strip(), "reason": exc.message}
                )
                text = rest.strip() or text
            else:
                setup.tools.activated_skills.append(
                    {
                        "name": activation.skill.name,
                        "source": activation.skill.source,
                        "activated_by": "user",
                    }
                )
                setup.observer.activity(
                    "skill.activate",
                    {
                        "skill": activation.skill.name,
                        "source": activation.skill.source,
                        "activated_by": "user",
                    },
                )
                await setup.harness.append_message(
                    CustomMessage(
                        customType="pi.skill",
                        content=activation.text,
                        display=False,
                        details={"kind": "skill_activation", "skill": activation.skill.name},
                        timestamp=int(time.time() * 1000),
                    )
                )
                text = rest.strip() or "Please proceed using the activated skill."
        return await setup.harness.prompt(text)

    async def _recover_overflow(
        self,
        request: RequestContext,
        setup: _Setup,
        events: NativeEvents,
        emit: Any,
        ledger: RunLedger,
        retry_mode: str,
    ) -> MemorySessionStorage | None:
        if self._harness is None:
            return None
        try:
            entries, leaf, _created = await export_session(self._harness.session)
            filtered = _drop_trailing_request(entries, leaf, retry_mode)
            if filtered is None:
                return None
            metadata = SessionMetadata(id=request.session_id, createdAt=now_iso())
            storage = MemorySessionStorage(metadata, filtered[0], filtered[1])
            session = Session(storage)
            branch = await session.get_branch()
            preparation = prepare_compaction(branch, setup.compaction)
            keep_tokens = setup.compaction.keep_recent_tokens
            while preparation is None and keep_tokens > 1:
                keep_tokens = max(1, keep_tokens // 4)
                preparation = prepare_compaction(
                    branch, setup.compaction.model_copy(update={"keep_recent_tokens": keep_tokens})
                )
            if preparation is None:
                return None
            setup.observer.activity(
                "compaction.start",
                {
                    "tokens_before": preparation.tokensBefore,
                    "messages_kept": len(preparation.keptMessages),
                    "reason": "context_overflow",
                },
            )
            result = await compact_preparation(
                preparation, setup.stream, setup.model, None, StreamOptions()
            )
            if not result.summary.strip():
                return None
            await session.append_compaction(
                result.summary, result.firstKeptEntryId, result.tokensBefore, result.details
            )
            setup.observer.activity(
                "compaction.end",
                {
                    "tokens_before": result.tokensBefore,
                    "summary_chars": len(result.summary),
                    "first_kept_entry_id": result.firstKeptEntryId,
                    "reason": "context_overflow",
                },
            )
            return storage
        except Exception:
            return None

    # -- finalization -------------------------------------------------------

    async def _fail(
        self,
        request: RequestContext,
        state: PiState | None,
        events: NativeEvents,
        emit: Any,
        ledger: RunLedger,
        error: PiError,
    ) -> None:
        await self._finalize(
            request,
            state,
            events,
            emit,
            ledger,
            status="failed",
            answer=error.message,
            error=error.public(events.run_id),
            setup=None,
        )

    async def _finalize(
        self,
        request: RequestContext,
        state: PiState | None,
        events: NativeEvents,
        emit: Any,
        ledger: RunLedger,
        *,
        status: str,
        answer: str,
        error: dict[str, Any] | None,
        setup: _Setup | None,
    ) -> None:
        stats = ledger.snapshot().as_dict()
        state_ref: dict[str, Any] | None = None
        saved_value = ""
        save_error: str | None = None
        if state is not None:
            if setup is not None and self._harness is not None:
                try:
                    entries, leaf, _created = await export_session(self._harness.session)
                    state.entries = sanitize_entries(entries, leaf)
                    state.leaf_id = leaf
                except Exception:
                    pass
            state.last_answer = clip(answer, 8_000)
            state.last_status = status
            state.stats = _merge_stats(state.stats, events.run_id, status, stats)
            state.revision += 1
            save = encode_state(state, max_encoded_bytes=request.runtime.state_max_encoded_bytes)
            if save.persisted:
                saved_value = save.value
                state_ref = public_state_ref(
                    conversation_id=request.session_id,
                    revision=save.revision,
                    run_id=events.run_id,
                    encoded_bytes=save.encoded_bytes,
                    payload_bytes=save.payload_bytes,
                    persisted=True,
                    compacted=save.compacted,
                )
            else:
                state.revision -= 1
                save_error = save.error or "state_save_failed"
                status = "state_save_failed"
                saved_value = request.agent_state or ""
                state_ref = public_state_ref(
                    conversation_id=request.session_id,
                    revision=state.revision,
                    run_id=events.run_id,
                    encoded_bytes=save.encoded_bytes,
                    payload_bytes=save.payload_bytes,
                    persisted=False,
                    error=save_error,
                    compacted=save.compacted,
                )
        if save_error:
            status = "state_save_failed"
            error = error or {
                "code": "state_save_failed",
                "stage": "state",
                "message": (
                    "The new Pi state could not be saved safely; the previous state was kept "
                    "and this run is not reported as completed."
                ),
            }
            answer = error["message"]
        summary: dict[str, Any] | None = None
        if state is not None:
            if save_error is None and "save" in locals():
                summary = state_summary(state)
                summary["encoded_bytes"] = save.encoded_bytes
                summary["delivery_status"] = "encoded"
            else:
                summary = {
                    "revision": state.revision,
                    "run_id": events.run_id,
                    "delivery_status": "failed",
                    "error": save_error or "state_save_failed",
                }
        payload = run_state_payload(
            status=status,
            stats=stats,
            answer=answer,
            state_ref=state_ref,
            state_summary=summary,
            error=error,
        )
        # State before terminal, mirroring cc_agent's native finalize: the
        # agent_state variable first, then visible feedback text (completed
        # answers were already streamed as deltas), then the run log, the final
        # answer log + `answer` variable, and one JSON terminal payload.
        if saved_value:
            emit({"type": "state", "name": "agent_state", "value": saved_value})
        is_error_status = status in {"failed", "state_save_failed"}
        if status != "completed" and answer:
            emit(events.text(answer))
        _run_log(
            events,
            emit,
            "Run error" if is_error_status else "Run finished",
            payload,
            is_error=is_error_status,
        )
        if status == "completed" and answer:
            _run_log(
                events,
                emit,
                "Final answer",
                {"kind": "pi_strategy.final_answer", "answer": answer, "status": status},
            )
        if answer:
            emit({"type": "state", "name": "answer", "value": answer})
        emit(events.json(payload))

    def _stop_requested(self) -> bool:
        return self._stopped or (self._stop is not None and self._stop.is_set())

    async def _watch_stop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            await asyncio.sleep(0.2)
        self._stopped = True
        harness = self._harness
        if harness is not None:
            try:
                await harness.abort()
            except Exception:
                pass


def _run_log(
    events: NativeEvents, emit: Any, label: str, data: Any, *, is_error: bool = False
) -> None:
    logged = events.log(label, data, is_error=is_error)
    if logged is not None:
        emit(logged)


def _safe_failure_message(code: str, stage: str, run_id: str = "") -> dict[str, Any]:
    # Crash-path output for failures before a run built its NativeEvents.
    return native_log(
        "Run error",
        {
            "code": code,
            "stage": stage,
            "run_id": run_id or "run_unknown",
            "message": "The Pi agent run failed.",
        },
        is_error=True,
    )


def _model_from_request(request: RequestContext, config: RuntimeConfig) -> Model:
    raw = request.model
    model_id = str(
        _get(raw, "model")
        or _get(raw, "model_id")
        or _get(raw, "name")
        or _get(raw, "model_name")
        or "dify-model"
    )
    return Model(
        provider="dify",
        model_id=model_id,
        api="dify",
        context_window=config.context_window,
        supports_images=False,
        reasoning=True,
    )


def _system_prompt(request: RequestContext, skills: SkillCatalog) -> str:
    parts = [
        "You are Pi Strategy, running inside a Dify Agent Strategy.",
        "Use only the tools provided in this request. Never claim access to a shell, local "
        "files, or a workspace that is not exposed as a tool.",
        "Tools execute immediately when you call them; there is no approval step and no user "
        "confirmation to wait for.",
        "Do not invent reasoning, tool activity, files or skill progress. Report only what "
        "actually happened.",
        "If a tool result says an execution outcome is unknown, tell the user to verify the "
        "business result before repeating a write operation.",
    ]
    instruction = (request.instruction or "").strip()
    if instruction:
        parts.extend(["", "Application instruction:", instruction])
    if request.files:
        parts.extend(["", "Attached file metadata (metadata only; not read content):"])
        for item in request.files[:30]:
            parts.append(
                f"- {item.get('name') or item.get('filename') or item.get('id') or 'file'}"
                f" ({item.get('mime_type') or item.get('type') or 'unknown'}, "
                f"{item.get('size', 'unknown')} bytes, id={item.get('id') or 'n/a'})"
            )
    section = skills.system_section()
    if section:
        parts.append(section)
    return "\n".join(parts)


def _tool_result_error_hook(event: Any) -> dict[str, Any] | None:
    details = getattr(event, "details", None)
    if not isinstance(details, dict):
        return None
    if details.get("is_error") or details.get("status") in {"error", "unknown"}:
        return {"is_error": True}
    return None


def _skill_context_hook(skills: SkillCatalog) -> Any:
    async def hook(event: Any) -> dict[str, Any]:
        eligible = skills.eligible_names()
        messages = []
        for message in getattr(event, "messages", []) or []:
            if isinstance(message, dict):
                details = message.get("details")
                custom_type = message.get("customType")
            else:
                details = getattr(message, "details", None)
                custom_type = getattr(message, "customType", None)
            withheld = None
            if (
                isinstance(message, ToolResultMessage)
                and isinstance(details, dict)
                and details.get("kind") == "skill_activation"
                and details.get("skill") not in eligible
            ):
                withheld = [
                    {
                        "type": "text",
                        "text": (
                            "[The previously activated skill is no longer eligible; "
                            "its instructions are withheld.]"
                        ),
                    }
                ]
            elif (
                custom_type == "pi.skill"
                and isinstance(details, dict)
                and details.get("skill") not in eligible
            ):
                withheld = (
                    "[The previously activated skill is no longer eligible; "
                    "its instructions are withheld.]"
                )
            if withheld is not None:
                if isinstance(message, dict):
                    message = {**message, "content": withheld}
                else:
                    message = message.model_copy(update={"content": withheld})
            messages.append(message)
        return {"messages": messages}

    return hook


def _assistant_answer(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", [])
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()


def _status_for_code(code: str) -> str:
    return {
        "budget_exhausted": "budget_exhausted",
        "context_overflow": "context_overflow",
        "context_too_large": "context_too_large",
        "aborted": "stopped",
    }.get(code, "failed")


def _answer_for_code(code: str) -> str:
    return {
        "budget_exhausted": "The execution budget for this turn is exhausted.",
        "context_overflow": "The conversation exceeds the model context window.",
        "context_too_large": "The fixed prompt content is larger than the model context window.",
        "aborted": "The run was stopped.",
        "provider_failed": "The model provider failed before returning a usable answer.",
    }.get(code, "The model request failed.")


def _merge_stats(
    previous: dict[str, Any], run_id: str, status: str, stats: dict[str, Any]
) -> dict[str, Any]:
    totals = previous.get("totals") if isinstance(previous.get("totals"), dict) else {}
    usage = stats.get("usage") or {}
    reported = usage.get("reported") or {}
    merged_totals = {
        "model_requests": int(totals.get("model_requests", 0))
        + int(stats.get("model_requests", 0)),
        "tool_calls": int(totals.get("tool_calls", 0)) + int(stats.get("tool_calls", 0)),
        "reported_tokens": int(totals.get("reported_tokens", 0))
        + int(reported.get("total_tokens", 0)),
        "estimated_tokens": int(totals.get("estimated_tokens", 0))
        + int(usage.get("estimated_tokens", 0)),
        "turns": int(totals.get("turns", 0)) + 1,
    }
    return {
        "totals": merged_totals,
        "last_run": {"run_id": run_id, "status": status, "finished_at": now_iso(), "stats": stats},
    }


def _drop_trailing_request(
    entries: list[dict[str, Any]], leaf: str | None, retry_mode: str
) -> tuple[list[SessionTreeEntry], str | None] | None:
    from pi_agent_harness.types import SessionTreeEntryAdapter

    try:
        parsed = [SessionTreeEntryAdapter.validate_python(item) for item in entries]
    except Exception:
        return None
    by_id = {entry.id: entry for entry in parsed}
    path: list[SessionTreeEntry] = []
    current = by_id.get(leaf) if leaf else None
    while current is not None:
        path.append(current)
        current = by_id.get(current.parentId) if current.parentId else None
    path.reverse()
    # Drop trailing error assistant messages.
    while path:
        last = path[-1]
        if (
            last.type == "message"
            and last.message.get("role") == "assistant"
            and last.message.get("stopReason") in {"error", "aborted"}
        ):
            path.pop()
            continue
        break
    if retry_mode == "resume":
        while (
            path
            and path[-1].type == "custom_message"
            and getattr(path[-1], "customType", "") in {"pi.continuation"}
        ):
            path.pop()
    # A prompt retry keeps the current user request and every completed tool
    # call/result. The retry is a continuation message, not a second user prompt,
    # so no completed tool is replayed.
    if not path:
        return None
    repaired: list[SessionTreeEntry] = []
    previous: str | None = None
    for entry in path:
        entry = entry.model_copy(update={"parentId": previous})
        repaired.append(entry)
        previous = entry.id
    return repaired, repaired[-1].id


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
