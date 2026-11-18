"""OpenTelemetry distributed tracing, structured JSON logging, and ADK telemetry callbacks."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


class StructuredJsonFormatter(logging.Formatter):
    """Formats Python log records as Cloud Logging compatible JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        span_ctx = trace.get_current_span().get_span_context()
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "trace_id": format(span_ctx.trace_id, "032x") if span_ctx.is_valid else "none",
            "span_id": format(span_ctx.span_id, "016x") if span_ctx.is_valid else "none",
        }
        extra_fields = getattr(record, "structured_data", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, default=str)


def configure_observability(service_name: str = "enterprise-cloud-architect-agent") -> trace.Tracer:
    """Initializes structured JSON logging and OpenTelemetry tracing."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        root_logger.addHandler(handler)
    root_logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    current_provider = trace.get_tracer_provider()
    if not isinstance(current_provider, TracerProvider):
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        if os.environ.get("OTEL_EXPORTER_GCP_TRACE", "FALSE").upper() == "TRUE":
            try:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

                provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
            except (ImportError, OSError, RuntimeError) as exc:  # pragma: no cover
                root_logger.warning("Falling back to local trace provider: %s", exc)
        elif os.environ.get("OTEL_CONSOLE_EXPORT", "FALSE").upper() == "TRUE":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)


logger = logging.getLogger("consulting_agent.telemetry")
tracer = configure_observability()


class TelemetryMetricsStore:
    """In-process operational counters for /metrics inspection and automated health checks."""

    def __init__(self) -> None:
        self.agent_invocations: int = 0
        self.model_calls: int = 0
        self.tool_calls: int = 0
        self.guardrail_blocks: int = 0
        self.total_tokens: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "agent_invocations": self.agent_invocations,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "guardrail_blocks": self.guardrail_blocks,
            "total_tokens": self.total_tokens,
        }


METRICS = TelemetryMetricsStore()


def before_agent_telemetry(callback_context: Any) -> None:
    """Records agent start timestamp in transient turn state."""
    METRICS.agent_invocations += 1
    agent_name = getattr(callback_context, "agent_name", "unknown_agent")
    callback_context.state[f"temp:start_ts:{agent_name}"] = time.perf_counter()
    logger.info(
        "Agent execution started",
        extra={"structured_data": {"event": "agent_start", "agent_name": agent_name}},
    )


def after_agent_telemetry(callback_context: Any) -> None:
    """Computes and logs agent execution latency."""
    agent_name = getattr(callback_context, "agent_name", "unknown_agent")
    start_ts = callback_context.state.get(f"temp:start_ts:{agent_name}")
    latency_ms = round((time.perf_counter() - start_ts) * 1000, 2) if start_ts else 0.0
    logger.info(
        "Agent execution completed",
        extra={
            "structured_data": {
                "event": "agent_complete",
                "agent_name": agent_name,
                "latency_ms": latency_ms,
            }
        },
    )


def after_model_telemetry(callback_context: Any, llm_response: Any) -> None:
    """Extracts token usage metadata from LLM responses for cost & quota observability."""
    METRICS.model_calls += 1
    usage = getattr(llm_response, "usage_metadata", None)
    total_tokens = getattr(usage, "total_token_count", 0) or 0
    METRICS.total_tokens += int(total_tokens)
    logger.info(
        "Model response received",
        extra={
            "structured_data": {
                "event": "model_complete",
                "agent_name": getattr(callback_context, "agent_name", "unknown"),
                "total_tokens": total_tokens,
            }
        },
    )


def after_tool_telemetry(
    tool: Any, args: dict[str, Any], tool_context: Any, tool_response: Any
) -> None:
    """Logs tool execution completion and argument keys without leaking raw secrets."""
    METRICS.tool_calls += 1
    tool_name = getattr(tool, "name", str(tool))
    logger.info(
        "Tool call finished",
        extra={
            "structured_data": {
                "event": "tool_complete",
                "tool_name": tool_name,
                "arg_keys": sorted(args.keys()),
                "status": tool_response.get("status", "ok")
                if isinstance(tool_response, dict)
                else "ok",
            }
        },
    )
