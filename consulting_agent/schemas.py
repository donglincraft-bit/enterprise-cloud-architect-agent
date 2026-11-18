"""Pydantic v2 data contracts for tool inputs, API payloads, and structured outputs."""

from typing import Literal
from pydantic import BaseModel, Field


class WorkloadSizingInput(BaseModel):
    """Validated input parameters for GCP workload TCO estimation."""

    monthly_vcpu: int = Field(..., ge=1, le=100_000, description="Total vCPUs required")
    storage_tb: float = Field(..., ge=0.1, le=50_000.0, description="Persistent storage in TB")
    gpu_count: int = Field(default=0, ge=0, le=4096, description="Accelerator GPUs for AI serving")
    commitment_years: Literal[0, 1, 3] = Field(
        default=3, description="Committed Use Discount term in years (0=On-Demand, 1=1yr, 3=3yr)"
    )


class ChatRequest(BaseModel):
    """HTTP request payload for the /chat endpoint."""

    user_id: str = Field(default="enterprise_user", min_length=1, max_length=128)
    session_id: str = Field(default="default_session", min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=16_000)
    preferred_industry: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    """Structured HTTP response returned by the /chat endpoint."""

    session_id: str
    response: str
    trace_id: str
    state_snapshot: dict[str, object] = Field(default_factory=dict)
