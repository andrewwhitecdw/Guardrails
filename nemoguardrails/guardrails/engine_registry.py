# SPDX-FileCopyrightText: Copyright (c) 2023-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Engine registry for IORails engine.

Manages a collection of ModelEngine and APIEngine instances, one per configured
model type. Each engine owns its own RetryClient with per-model settings.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

from nemoguardrails.guardrails.api_engine import APIEngine
from nemoguardrails.guardrails.base_engine import BaseEngine
from nemoguardrails.guardrails.guardrails_types import get_request_id, truncate
from nemoguardrails.guardrails.model_engine import ModelEngine
from nemoguardrails.guardrails.telemetry import api_call_span
from nemoguardrails.guardrails.tool_schema import ToolExchange, ToolResult, Toolset
from nemoguardrails.llm.models.instrumented import instrument_llm_model
from nemoguardrails.rails.llm.config import Model, RailsConfigData
from nemoguardrails.types import ChatMessage, LLMModel, LLMResponse, LLMResponseChunk

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

log = logging.getLogger(__name__)

_EngineT = TypeVar("_EngineT", bound=BaseEngine)


class _ModelEngineAdapter:
    def __init__(self, engine: ModelEngine) -> None:
        self._engine = engine

    @property
    def model_name(self) -> str:
        return self._engine.model_name

    @property
    def provider_name(self) -> Optional[str]:
        return self._engine.model_config.engine

    @property
    def provider_url(self) -> Optional[str]:
        return self._engine.base_url

    @staticmethod
    def _messages(prompt: str | list[ChatMessage] | list[dict]) -> list[dict]:
        if isinstance(prompt, str):
            return [{"role": "user", "content": prompt}]
        return [message.to_dict() if isinstance(message, ChatMessage) else message for message in prompt]

    def _params(self, stop: Optional[list[str]], kwargs: dict[str, Any]) -> dict[str, Any]:
        params = {**self._engine.body_param_defaults, **kwargs}
        if stop is not None:
            params["stop"] = stop
        return params

    async def generate_async(
        self,
        prompt: str | list[ChatMessage],
        *,
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return await self._engine.chat_completion(self._messages(prompt), **self._params(stop, kwargs))

    async def stream_async(
        self,
        prompt: str | list[ChatMessage],
        *,
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[LLMResponseChunk, None]:
        stream = self._engine.stream_chat_completion(self._messages(prompt), **self._params(stop, kwargs))
        async with aclosing(stream):
            async for chunk in stream:
                yield chunk


class EngineRegistry:
    """Registry of ModelEngine and APIEngine instances for IORails.

    Creates one engine per configured model or API service, keyed by name.
    Each engine owns its own HTTP client with per-model retry and timeout settings.
    """

    def __init__(
        self,
        models: list[Model],
        rails_config_data: RailsConfigData,
        tracer: Optional["Tracer"] = None,
        metrics_enabled: bool = False,
        content_capture_enabled: bool = False,
    ) -> None:
        """Build one engine per configured model and API service.

        When *tracer* is provided, LLM and API calls produce OTEL spans; when
        ``None`` the span helpers become no-ops.

        When *metrics_enabled* is True, LLM calls emit the OTEL GenAI
        client-side metrics (``gen_ai.client.token.usage``,
        ``gen_ai.client.operation.duration``, plus the streaming
        chunk-timing metrics).  Defaults to False so callers that don't
        opt in get no metric emissions even if a MeterProvider is
        configured globally.

        When *content_capture_enabled* is True, LLM call spans carry
        input/output message content per the OTEL GenAI content-capture
        contract.  Defaults to False; should only be True when
        ``tracer`` is also set, since capture on a no-op span is wasted
        work.
        """
        self._engines: dict[str, BaseEngine] = {}
        self._models: dict[str, LLMModel] = {}
        self._running = False
        self._tracer = tracer

        for model_config in models:
            engine = ModelEngine(model_config)
            self._engines[model_config.type] = engine
            self._models[model_config.type] = instrument_llm_model(
                _ModelEngineAdapter(engine),
                tracer=tracer,
                metrics_enabled=metrics_enabled,
                content_capture_enabled=content_capture_enabled,
                default_request_params=engine.body_param_defaults,
            )
            log.info(
                "Registered model engine: type=%s, model=%s, base_url=%s",
                model_config.type,
                model_config.model,
                engine.base_url,
            )

        jailbreak_config = rails_config_data.jailbreak_detection
        if jailbreak_config and jailbreak_config.nim_base_url:
            if "jailbreak_detection" in self._engines:
                raise ValueError(
                    "Engine name 'jailbreak_detection' is already registered as a model engine. "
                    "Cannot register the jailbreak detection API engine with the same name."
                )
            api_engine = APIEngine.from_jailbreak_config(jailbreak_config)
            self._engines["jailbreak_detection"] = api_engine
            log.info(
                "Registered API engine: name=%s, url=%s",
                "jailbreak_detection",
                api_engine.url,
            )

    async def start(self) -> None:
        """Start all engine clients. Call this during service startup."""
        if self._running:
            return

        started: list[BaseEngine] = []

        for name, engine in self._engines.items():
            try:
                await engine.start()
                started.append(engine)
            except Exception as e:
                log.error("Error starting engine %s: %s", name, e)
                for eng in started:
                    try:
                        await eng.stop()
                    except Exception:
                        pass
                raise RuntimeError(f"Failed to start engine: Engine {name}: exception {e}") from e

        self._running = True

    async def stop(self) -> None:
        """Stop all engine clients. Call this during service shutdown."""
        if not self._running:
            return

        engine_errors: dict[str, Exception] = {}
        try:
            for name, engine in self._engines.items():
                try:
                    await engine.stop()
                except Exception as e:
                    engine_errors[name] = e
                    log.error("Error stopping engine %s: %s", name, e)
        finally:
            self._running = False

        if engine_errors:
            engine_error_string = ", ".join(
                f"Engine {name}: exception {exception}" for name, exception in engine_errors.items()
            )
            raise RuntimeError(f"Failed to stop engines: {engine_error_string}")

    def _get_engine(self, name: str, expected_type: type[_EngineT]) -> _EngineT:
        """Look up an engine by name, verifying its type."""
        if name not in self._engines:
            available = list(self._engines.keys())
            raise KeyError(f"No engine configured with name '{name}'. Available: {available}")
        engine = self._engines[name]
        if not isinstance(engine, expected_type):
            raise TypeError(f"Engine '{name}' is {type(engine).__name__}, expected {expected_type.__name__}")
        return engine

    def provider_name(self, model_type: str) -> str:
        """Return the provider/engine name (e.g. 'nim', 'openai') for a model engine."""
        return self._get_engine(model_type, ModelEngine).model_config.engine or "unknown"

    async def model_call(self, model_type: str, messages: list[dict], **kwargs: Any) -> LLMResponse:
        """Route a chat completion request to the named model engine.

        Returns the structured ``LLMResponse`` from the engine — content,
        reasoning (when the provider exposes it), usage, finish reason.
        Callers that only want the assistant text should access ``.content``.

        When metrics are enabled, emits ``gen_ai.client.operation.duration``
        (with ``error.type`` on exception) and ``gen_ai.client.token.usage``
        (one observation each for ``input`` and ``output`` token types,
        only when ``LLMResponse.usage`` is populated).

        Raises:
            KeyError: If no engine is registered with the given name.
            TypeError: If the named engine is not a ModelEngine.
        """
        req_id = get_request_id()
        log.debug("[%s] Model engine '%s' messages: %s", req_id, model_type, truncate(messages))

        self._get_engine(model_type, ModelEngine)
        prompt = cast(list[ChatMessage], messages)
        result = await self._models[model_type].generate_async(prompt, **kwargs)

        log.debug("[%s] Model engine '%s' response: %s", req_id, model_type, truncate(result))
        return result

    async def stream_model_call(
        self, model_type: str, messages: list[dict], **kwargs: Any
    ) -> AsyncGenerator[LLMResponseChunk, None]:
        """Stream chat completion chunks from the named model engine.

        Yields ``LLMResponseChunk`` objects. The surrounding
        ``llm_call_span`` wraps the full generator lifetime: it opens
        before the first chunk and closes when the generator exhausts or
        raises.

        When metrics are enabled, emits ``gen_ai.client.operation.duration``
        for the full stream lifetime (with ``error.type`` on exception)
        and ``gen_ai.client.token.usage`` after stream completion using
        the ``UsageInfo`` carried on the terminal SSE chunk (when the
        provider returns one — controlled by ``include_usage_in_stream``,
        defaults to True for OpenAI-compatible engines).  No token
        observation is emitted on early consumer cancellation or on
        provider error mid-stream.

        The LLM CLIENT span receives ``gen_ai.request.*`` attributes
        (including ``gen_ai.request.stream=True``) before the first chunk,
        and ``gen_ai.response.*`` / ``gen_ai.usage.*`` attributes
        accumulated across the chunks after natural exhaustion.  Like the
        token metric, the response attrs are skipped on cancellation or a
        mid-stream provider error.  These span attrs are independent of
        whether metrics are enabled.

        Raises:
            KeyError: If no engine is registered with the given name.
            TypeError: If the named engine is not a ModelEngine.
        """
        req_id = get_request_id()
        log.debug("[%s] Model engine '%s' stream messages: %s", req_id, model_type, truncate(messages))

        self._get_engine(model_type, ModelEngine)
        prompt = cast(list[ChatMessage], messages)
        stream = cast(AsyncGenerator[LLMResponseChunk, None], self._models[model_type].stream_async(prompt, **kwargs))
        async with aclosing(stream):
            async for chunk in stream:
                yield chunk

    def parse_tools(self, model_type: str, llm_params: Optional[dict]) -> Toolset:
        """Parse the tool block in ``llm_params`` for the named model engine.

        Delegates to the engine's ``parse_tools`` so the provider-specific shape
        (keyed on the engine) is normalized into a ``Toolset`` for the tool rails.

        Raises:
            KeyError: If no engine is registered with the given name.
            TypeError: If the named engine is not a ModelEngine.
        """
        engine = self._get_engine(model_type, ModelEngine)
        return engine.parse_tools({**engine.body_param_defaults, **(llm_params or {})})

    def extract_tool_results(self, model_type: str, messages: list[dict]) -> list[ToolResult]:
        """Extract incoming tool results from ``messages`` for the named model engine.

        Delegates to the engine's ``extract_tool_results`` so the provider's
        tool-result messages are normalized into the ``ToolResult`` list the
        ToolResultRail consumes.

        Raises:
            KeyError: If no engine is registered with the given name.
            TypeError: If the named engine is not a ModelEngine.
        """
        engine = self._get_engine(model_type, ModelEngine)
        return engine.extract_tool_results(messages)

    def extract_tool_exchanges(self, model_type: str, messages: list[dict]) -> list[ToolExchange]:
        """Group ``messages`` into per-turn ``(tool_calls, tool_results)`` exchanges.

        Delegates to the engine's ``extract_tool_exchanges`` so each tool result is
        validated against its own turn's calls. This keeps ``call_id`` linkage
        turn-local, which ``RailsManager.are_tool_results_safe`` relies on so that ids
        reused across turns (spec-allowed) are not flagged as ambiguous duplicates.

        Raises:
            KeyError: If no engine is registered with the given name.
            TypeError: If the named engine is not a ModelEngine.
        """
        engine = self._get_engine(model_type, ModelEngine)
        return engine.extract_tool_exchanges(messages)

    async def api_call(self, api_name: str, message: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Route an API request to the named API engine.

        Raises:
            KeyError: If no engine is registered with the given name.
            TypeError: If the named engine is not an APIEngine.
        """
        req_id = get_request_id()
        log.debug("[%s] API engine '%s' request: %s", req_id, api_name, truncate(message))

        with api_call_span(self._tracer, api_name):
            api_engine = self._get_engine(api_name, APIEngine)
            response = await api_engine.call(message, **kwargs)

        log.debug("[%s] API engine '%s' response: %s", req_id, api_name, truncate(response))
        return response

    async def __aenter__(self):
        """Async context manager entry: start all engine clients."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit: stop all engine clients."""
        await self.stop()
