"""Production FastAPI service exposing /chat, /healthz, and /metrics for Cloud Run."""

from __future__ import annotations

import os

from fastapi import FastAPI

from consulting_agent.memory import ConsultingSessionManager
from consulting_agent.observability import METRICS
from consulting_agent.schemas import ChatRequest, ChatResponse

app = FastAPI(
    title="Enterprise Cloud Transformation Co-Pilot API",
    version="1.0.0",
    description="Multi-Agent ADK service with OpenTelemetry tracing, memory, and guardrails.",
)

session_manager = ConsultingSessionManager()


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Liveness and readiness probe for Cloud Run / GKE."""
    return {
        "status": "healthy",
        "service": "enterprise-cloud-architect-agent",
        "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    }


@app.get("/metrics")
async def metrics() -> dict[str, int]:
    """Operational telemetry counters for agent, model, tool, and guardrail events."""
    return METRICS.snapshot()


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    """Executes a stateful multi-agent turn and returns response + trace ID + state snapshot."""
    reply, trace_id, snapshot = await session_manager.run_turn(
        user_id=payload.user_id,
        session_id=payload.session_id,
        message=payload.message,
        preferred_industry=payload.preferred_industry,
    )
    return ChatResponse(
        session_id=payload.session_id,
        response=reply,
        trace_id=trace_id,
        state_snapshot=snapshot,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
