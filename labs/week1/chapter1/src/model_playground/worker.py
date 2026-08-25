"""C-06 RunWorker(QThread): run one model off the UI thread (SPEC section 4 / C-06).

One worker per model panel (I-010). All heavy inference happens on the worker
thread; the UI only ever receives queued signals. Signals:

    token(model_id, delta)             - per streamed chunk (the UI appends it)
    metrics_ready(model_id, metrics)   - emitted once, on settle or terminal
    structured(model_id, result)       - when structured mode ran
    crashed(model_id, message)         - an uncaught fault (E-07); also terminal

Every path emits exactly one terminal metrics_ready (COMPLETED / VALID / ERROR /
TIMED_OUT / CANCELLED) and then returns, so the run always settles and no live
worker survives a cancel (I-010). Structured mode runs parse -> validate -> retry
(R-11 / E-03) over a *collected* response; each retry re-issues generation with
an error-informed prompt.
"""

from __future__ import annotations

import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal

from .metrics import (
    CANCELLED,
    COMPLETED,
    ERROR,
    TIMED_OUT,
    VALID,
    RunMetrics,
    compute_metrics,
)
from .model import Model
from .registry import ModelRegistry
from .structured import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_S,
    ValidationResult,
    build_retry_prompt,
    parse_and_validate,
)
from .types import Message, Usage


class RunWorker(QThread):
    token = pyqtSignal(str, str)
    metrics_ready = pyqtSignal(str, object)
    structured = pyqtSignal(str, object)
    crashed = pyqtSignal(str, str)

    def __init__(
        self,
        model: Model,
        panel_id: str,
        registry: ModelRegistry,
        schema: dict | None = None,
        *,
        structured_mode: bool = False,
        streaming: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        super().__init__()
        self._model = model
        self._panel_id = panel_id
        self._registry = registry
        self._schema = schema
        self._structured_mode = structured_mode
        self._streaming = streaming
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._cancel = threading.Event()
        self._thread_id: int | None = None  # set in run(); off-thread check (I-011)
        self._messages: list[Message] = []
        self._params: dict = {}

        # -- main-thread, thread-safe controls (C-06) --

    def start_run(self, messages: list[Message], params: dict) -> None:
        self._messages = list(messages)
        self._params = dict(params)
        self._cancel.clear()
        self.start()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def thread_id(self) -> int | None:
        return self._thread_id

        # -- worker thread --

    def run(self) -> None:
        self._thread_id = threading.get_ident()
        model_id = self._model.model_id
        t_request = time.monotonic()
        try:
            spec = self._registry.get(model_id)
        except KeyError:
            self._finish(
                ERROR,
                t_request,
                t_request,
                Usage(0, 0),
                0.0,
                0.0,
                error=f"unknown model (not in registry): '{model_id}'",
            )
            return

        p_in = spec.price_input_usd_per_1k
        p_out = spec.price_output_usd_per_1k
        try:
            if self._structured_mode:
                self._run_structured(model_id, p_in, p_out)
            elif self._streaming:
                self._run_stream(model_id, p_in, p_out)
            else:
                self._run_collect(model_id, p_in, p_out)
        except Exception as exc:
            # E-07: surface the fault; NEVER abort the process or the siblings.
            try:
                self.crashed.emit(model_id, f"{type(exc).__name__}: {exc}")
            except Exception:  # noqa: S110 (a diagnostic emit must not itself raise)
                pass
            self._finish(
                ERROR,
                t_request,
                t_request,
                Usage(0, 0),
                p_in,
                p_out,
                error=f"crashed: {type(exc).__name__}: {exc}",
            )

    def _run_collect(self, model_id, p_in, p_out) -> None:
        t_request = time.monotonic()
        if self._cancel.is_set():
            self._finish(
                CANCELLED, t_request, None, Usage(0, 0), p_in, p_out, error="cancelled"
            )
            return
        resp = self._model.generate(self._messages, **self._params)
        if time.monotonic() - t_request > self._timeout_s:
            self._finish(
                TIMED_OUT,
                t_request,
                None,
                resp.usage or Usage(0, 0),
                p_in,
                p_out,
                error=f"exceeded {self._timeout_s}s",
            )
            return
        self.token.emit(model_id, resp.text)
        # non-streaming: t_first_token None => TTFT == total latency (E-04 / I-004).
        self._finish(COMPLETED, t_request, None, resp.usage or Usage(0, 0), p_in, p_out)

    def _run_stream(self, model_id, p_in, p_out) -> None:
        t_request = time.monotonic()
        t_first = None
        usage = Usage(0, 0)
        for chunk in self._model.stream(self._messages, **self._params):
            if self._cancel.is_set():
                # E-08: tear down; partial text is already streamed to the panel.
                self._finish(
                    CANCELLED, t_request, t_first, usage, p_in, p_out, error="cancelled"
                )
                return
            if time.monotonic() - t_request > self._timeout_s:
                # K-02 / E-02: preserve partial text; siblings keep running.
                self._finish(
                    TIMED_OUT,
                    t_request,
                    t_first,
                    usage,
                    p_in,
                    p_out,
                    error=f"exceeded {self._timeout_s}s",
                )
                return
            if chunk.delta:
                if t_first is None:
                    t_first = time.monotonic()
                self.token.emit(model_id, chunk.delta)
            if chunk.finished and chunk.usage is not None:
                usage = chunk.usage
        self._finish(COMPLETED, t_request, t_first, usage, p_in, p_out)

    def _run_structured(self, model_id, p_in, p_out) -> None:
        t_request = time.monotonic()
        messages_cur = list(self._messages)
        usage = Usage(0, 0)
        last: ValidationResult | None = None
        for attempt in range(self._max_retries + 1):
            if self._cancel.is_set():
                self._finish(
                    CANCELLED,
                    t_request,
                    None,
                    usage,
                    p_in,
                    p_out,
                    error="cancelled",
                    structured_result=last,
                )
                return
            if time.monotonic() - t_request > self._timeout_s:
                self._finish(
                    TIMED_OUT,
                    t_request,
                    None,
                    usage,
                    p_in,
                    p_out,
                    error=f"exceeded {self._timeout_s}s",
                    structured_result=last,
                )
                return
            resp = self._model.generate(messages_cur, **self._params)
            usage = resp.usage or Usage(0, 0)
            vr = parse_and_validate(resp.text, self._schema or {})
            last = vr
            self.token.emit(model_id, resp.text)
            if vr.ok:
                # I-009: VALID is reachable only via a validated object.
                self._finish(
                    VALID,
                    t_request,
                    None,
                    usage,
                    p_in,
                    p_out,
                    structured_result=vr,
                    retries=attempt,
                )
                return
            if attempt >= self._max_retries:
                first_reason = "; ".join(vr.errors) if vr.errors else "no output"
                self._finish(
                    ERROR,
                    t_request,
                    None,
                    usage,
                    p_in,
                    p_out,
                    error=first_reason,
                    structured_result=vr,
                    retries=self._max_retries,
                )
                return
            messages_cur = build_retry_prompt(self._messages, vr)

            # -- terminal --

    def _finish(
        self,
        status: str,
        t_request,
        t_first,
        usage: Usage,
        p_in: float,
        p_out: float,
        error: str | None = None,
        structured_result: ValidationResult | None = None,
        retries: int = 0,
    ) -> None:
        metrics = compute_metrics(
            self._panel_id,
            t_request=(t_request if t_request is not None else 0.0),
            t_first_token=t_first,
            t_complete=time.monotonic(),
            usage=usage,
            price_input=p_in,
            price_output=p_out,
            retries=retries,
            status=status,
            error=error,
        )
        if structured_result is not None:
            self.structured.emit(self._panel_id, structured_result)
        self.metrics_ready.emit(self._panel_id, metrics)


__all__ = ["RunMetrics", "RunWorker"]
