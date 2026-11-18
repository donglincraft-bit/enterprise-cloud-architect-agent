"""Multi-Agent ADK Orchestration: Coordinator, Sequential, Parallel, and Loop agents."""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from consulting_agent.guardrails import before_model_guardrail, before_tool_guardrail
from consulting_agent.observability import (
    after_agent_telemetry,
    after_model_telemetry,
    after_tool_telemetry,
    before_agent_telemetry,
)
from consulting_agent.tools import (
    approve_proposal_quality,
    check_compliance_requirements,
    estimate_cloud_workload_tco,
    save_engagement_artifact,
)

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

RETRY_CONFIG = types.GenerateContentConfig(
    temperature=0.2,
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=5, initial_delay=1.0)
    ),
)

# 1. Isolated Google Search Sub-Agent (wrapped via AgentTool so custom tools coexist cleanly)
market_research_subagent = LlmAgent(
    name="market_research_subagent",
    model=MODEL_NAME,
    description="Searches public web sources for company initiatives, cloud announcements, and benchmarks.",
    instruction=(
        "Use google_search to gather concise, factual context on the client's industry, "
        "recent AI/cloud initiatives, and regulatory landscape in 4 bullet points."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[google_search],
)

# 2. Stage 1 of Pipeline: Discovery & Problem Framing
discovery_agent = LlmAgent(
    name="discovery_agent",
    model=MODEL_NAME,
    description="Frames client business objectives, workload assumptions, and industry context.",
    instruction=(
        "You are a Principal Cloud Consulting Lead. Analyze the user's request and extract: "
        "(1) Business problem & KPIs, (2) Estimated compute/storage/GPU scale, "
        "(3) Industry & region (defaulting to {user:preferred_industry?} if relevant). "
        "Optionally call market_research_subagent when external company/industry facts help. "
        "Produce a structured brief."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[AgentTool(agent=market_research_subagent)],
    output_key="discovery_summary",
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    before_model_callback=before_model_guardrail,
    after_model_callback=after_model_telemetry,
)

# 3. Stage 2 of Pipeline: Parallel Specialist Analysis (Architecture + FinOps + Compliance)
cloud_architect_agent = LlmAgent(
    name="cloud_architect_agent",
    model=MODEL_NAME,
    description="Designs target Google Cloud & Vertex AI reference architecture.",
    instruction=(
        "Based on the discovery brief:\n{discovery_summary?}\n\n"
        "Design a production Google Cloud architecture covering ingress/networking, compute "
        "(Cloud Run / GKE / Vertex AI Agent Engine), data layer (BigQuery / AlloyDB / Cloud Storage), "
        "and SRE observability (Cloud Trace, Cloud Logging, SLOs)."
    ),
    generate_content_config=RETRY_CONFIG,
    output_key="architecture_design",
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    after_model_callback=after_model_telemetry,
)

finops_estimator_agent = LlmAgent(
    name="finops_estimator_agent",
    model=MODEL_NAME,
    description="Calculates GCP workload TCO and Committed Use Discount (CUD) savings.",
    instruction=(
        "Based on the discovery brief:\n{discovery_summary?}\n\n"
        "Infer reasonable vCPU, storage_tb, and gpu_count sizing if not explicitly stated, "
        "and ALWAYS call `estimate_cloud_workload_tco` to compute monthly/annual costs and 3-year CUD savings. "
        "Summarize the assumptions and ROI clearly."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[estimate_cloud_workload_tco],
    output_key="financial_estimate",
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    before_tool_callback=before_tool_guardrail,
    after_tool_callback=after_tool_telemetry,
    after_model_callback=after_model_telemetry,
)

security_compliance_agent = LlmAgent(
    name="security_compliance_agent",
    model=MODEL_NAME,
    description="Determines mandatory IAM, encryption, VPC-SC, and Model Armor security controls.",
    instruction=(
        "Based on the discovery brief:\n{discovery_summary?}\n\n"
        "ALWAYS call `check_compliance_requirements` for the client's industry and region, "
        "then summarize the zero-trust security and AI governance controls."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[check_compliance_requirements],
    output_key="compliance_audit",
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    after_tool_callback=after_tool_telemetry,
    after_model_callback=after_model_telemetry,
)

parallel_analysis_stage = ParallelAgent(
    name="parallel_analysis_stage",
    description="Runs architecture design, FinOps TCO modeling, and security compliance concurrently.",
    sub_agents=[
        cloud_architect_agent,
        finops_estimator_agent,
        security_compliance_agent,
    ],
)

# 4. Stage 3 of Pipeline: Iterative Proposal Synthesis & Executive QA Loop
proposal_drafter_agent = LlmAgent(
    name="proposal_drafter_agent",
    model=MODEL_NAME,
    description="Synthesizes specialist outputs into an executive cloud transformation proposal.",
    instruction=(
        "Synthesize an executive-ready Google Cloud Transformation Proposal in Markdown using:\n"
        "- Discovery: {discovery_summary?}\n"
        "- Architecture: {architecture_design?}\n"
        "- FinOps TCO: {financial_estimate?}\n"
        "- Security & Compliance: {compliance_audit?}\n"
        "- Prior Executive Review Feedback (if any): {critique_feedback?}\n\n"
        "Include: Executive Summary, Target Architecture, Itemized TCO & CUD Savings Table, "
        "Security & Governance Controls, and a 30-60-90 Day Delivery Roadmap. "
        "Call `save_engagement_artifact` once drafted."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[save_engagement_artifact],
    output_key="draft_proposal",
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    after_tool_callback=after_tool_telemetry,
    after_model_callback=after_model_telemetry,
)

executive_critic_agent = LlmAgent(
    name="executive_critic_agent",
    model=MODEL_NAME,
    description="Audits the draft proposal against enterprise rubric and exits loop when score >= 85.",
    instruction=(
        "Review the draft proposal:\n{draft_proposal?}\n\n"
        "Score it from 0 to 100 across: (1) Clear KPI alignment, (2) Concrete GCP architecture, "
        "(3) Quantified USD TCO & CUD savings, (4) Security/Model Armor controls, (5) 30-60-90 roadmap. "
        "ALWAYS call `approve_proposal_quality` with your `quality_score` and `review_notes`. "
        "If score >= 85, present the final approved proposal cleanly to the user."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[approve_proposal_quality],
    output_key="executive_review",
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    after_tool_callback=after_tool_telemetry,
    after_model_callback=after_model_telemetry,
)

proposal_refinement_loop = LoopAgent(
    name="proposal_refinement_loop",
    description="Iteratively drafts and critiques the executive proposal until quality_score >= 85.",
    sub_agents=[proposal_drafter_agent, executive_critic_agent],
    max_iterations=2,
)

engagement_pipeline = SequentialAgent(
    name="engagement_pipeline",
    description="End-to-end enterprise discovery, parallel specialist analysis, and QA proposal loop.",
    sub_agents=[
        discovery_agent,
        parallel_analysis_stage,
        proposal_refinement_loop,
    ],
)

# 5. Fast-Path Specialist for quick standalone TCO/compliance questions
quick_advisory_agent = LlmAgent(
    name="quick_advisory_agent",
    model=MODEL_NAME,
    description="Handles quick standalone TCO cost questions or compliance lookups without a full proposal.",
    instruction=(
        "Answer quick standalone GCP sizing or compliance questions concisely using "
        "`estimate_cloud_workload_tco` and `check_compliance_requirements`."
    ),
    generate_content_config=RETRY_CONFIG,
    tools=[estimate_cloud_workload_tco, check_compliance_requirements],
    before_model_callback=before_model_guardrail,
    before_tool_callback=before_tool_guardrail,
    after_tool_callback=after_tool_telemetry,
    after_model_callback=after_model_telemetry,
)

# 6. Root Coordinator Agent
root_agent = LlmAgent(
    name="enterprise_consulting_coordinator",
    model=MODEL_NAME,
    description="Root orchestrator routing requests between quick advisory lookups and full transformation proposals.",
    instruction=(
        "You are the Enterprise Cloud Consulting Coordinator.\n"
        "- For quick, single-point TCO estimates or single compliance checks, delegate to `quick_advisory_agent`.\n"
        "- For architecture designs, migration plans, multi-part enterprise assessments, or executive proposals, "
        "delegate to `engagement_pipeline`.\n"
        "Always maintain an executive, consultative tone."
    ),
    generate_content_config=RETRY_CONFIG,
    sub_agents=[engagement_pipeline, quick_advisory_agent],
    before_agent_callback=before_agent_telemetry,
    after_agent_callback=after_agent_telemetry,
    before_model_callback=before_model_guardrail,
    after_model_callback=after_model_telemetry,
)
