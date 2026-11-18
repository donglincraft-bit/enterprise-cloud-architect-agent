"""Model Armor-style input/tool guardrails preventing prompt injection and unsafe tool calls."""

from __future__ import annotations

import logging
import re
from typing import Any

from google.genai import types
from consulting_agent.observability import METRICS

logger = logging.getLogger("consulting_agent.guardrails")

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|api\s+key|secret)", re.IGNORECASE),
    re.compile(r"jailbreak|developer\s+mode\s+override", re.IGNORECASE),
)

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def inspect_prompt_safety(text: str) -> str | None:
    """Returns a rejection reason if prompt injection or raw sensitive PII is detected."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return "Blocked potential prompt-injection or instruction-override attempt."
    if _SSN_PATTERN.search(text):
        return "Blocked message containing unredacted government ID (SSN pattern)."
    return None


def before_model_guardrail(callback_context: Any, llm_request: Any) -> Any | None:
    """ADK before_model_callback that intercepts unsafe user inputs before calling Gemini."""
    contents = getattr(llm_request, "contents", None) or []
    if not contents:
        return None

    last_content = contents[-1]
    if getattr(last_content, "role", "") != "user":
        return None

    for part in getattr(last_content, "parts", None) or []:
        text = getattr(part, "text", None)
        if not text:
            continue
        violation = inspect_prompt_safety(text)
        if violation:
            METRICS.guardrail_blocks += 1
            callback_context.state["last_guardrail_violation"] = violation
            logger.warning(
                "Guardrail intercepted request",
                extra={"structured_data": {"event": "guardrail_block", "reason": violation}},
            )
            try:
                from google.adk.models.llm_response import LlmResponse

                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text=(
                                    f"Security Guardrail Notice: {violation} "
                                    "Please rephrase your enterprise cloud consulting request."
                                )
                            )
                        ],
                    )
                )
            except Exception:  # pragma: no cover
                return None
    return None


def before_tool_guardrail(
    tool: Any, args: dict[str, Any], tool_context: Any
) -> dict[str, Any] | None:
    """ADK before_tool_callback validating resource bounds on sizing/estimation tools."""
    tool_name = getattr(tool, "name", "")
    if tool_name == "estimate_cloud_workload_tco":
        vcpu = int(args.get("monthly_vcpu", 0))
        storage_tb = float(args.get("storage_tb", 0.0))
        if vcpu <= 0 or vcpu > 100_000:
            return {
                "status": "error",
                "error_message": "monthly_vcpu must be between 1 and 100,000.",
            }
        if storage_tb < 0 or storage_tb > 50_000:
            return {
                "status": "error",
                "error_message": "storage_tb must be between 0 and 50,000 TB.",
            }
    return None
