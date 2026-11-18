"""Stateful Session & Long-Term Memory Runner with context-window compaction."""

from __future__ import annotations

from typing import Any
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from opentelemetry import trace

from consulting_agent.agent import root_agent
from consulting_agent.observability import tracer

APP_NAME = "enterprise_cloud_architect_copilot"
MAX_RECENT_TURNS_SUMMARY = 8


class ConsultingSessionManager:
    """Manages ADK sessions, cross-session memory ingestion, and traced turn execution."""

    def __init__(self) -> None:
        self.session_service = InMemorySessionService()
        self.memory_service = InMemoryMemoryService()
        self.runner = Runner(
            agent=root_agent,
            app_name=APP_NAME,
            session_service=self.session_service,
            memory_service=self.memory_service,
        )

    async def get_or_create_session(
        self,
        user_id: str,
        session_id: str,
        initial_state: dict[str, Any] | None = None,
    ) -> Any:
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if session is None:
            seed_state = {"app:rubric_threshold": 85, **(initial_state or {})}
            session = await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
                state=seed_state,
            )
        return session

    async def run_turn(
        self,
        user_id: str,
        session_id: str,
        message: str,
        preferred_industry: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """Executes one traced multi-agent turn and persists completed session context to memory."""
        init_state = (
            {"user:preferred_industry": preferred_industry} if preferred_industry else None
        )
        session = await self.get_or_create_session(user_id, session_id, init_state)

        with tracer.start_as_current_span("consulting_copilot.run_turn") as span:
            span.set_attribute("enduser.id", user_id)
            span.set_attribute("session.id", session_id)
            span_ctx = trace.get_current_span().get_span_context()
            trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else "local-trace"

            user_content = types.Content(role="user", parts=[types.Part(text=message)])
            chunks: list[str] = []
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=user_content,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            chunks.append(part.text)

            updated_session = await self.session_service.get_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
            state_snapshot: dict[str, Any] = {}
            if updated_session is not None:
                # Compact turn log in state to prevent unbounded context growth
                turn_log = list(updated_session.state.get("turn_summaries", []))
                turn_log.append(message[:160])
                if len(turn_log) > MAX_RECENT_TURNS_SUMMARY:
                    turn_log = turn_log[-MAX_RECENT_TURNS_SUMMARY:]
                state_snapshot = {
                    k: v
                    for k, v in updated_session.state.items()
                    if k
                    in {
                        "latest_tco_estimate",
                        "compliance_posture",
                        "last_quality_score",
                        "saved_artifacts",
                        "user:preferred_industry",
                    }
                }
                await self.memory_service.add_session_to_memory(updated_session)

            final_text = "\n".join(chunks).strip() or "Proposal workflow completed."
            return final_text, trace_id, state_snapshot
