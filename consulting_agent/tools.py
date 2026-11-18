"""Domain FunctionTools with strict typing, docstrings, and ToolContext state persistence."""

from __future__ import annotations

from typing import Any

from google.adk.tools.tool_context import ToolContext

from consulting_agent.schemas import WorkloadSizingInput

_CUD_DISCOUNT_RATES: dict[int, float] = {
    0: 0.0,
    1: 0.37,
    3: 0.55,
}

_INDUSTRY_CONTROLS: dict[str, list[str]] = {
    "fsi": [
        "Assured Workloads for Financial Services",
        "Cloud KMS Customer-Managed Encryption Keys (CMEK) with Cloud HSM",
        "VPC Service Controls perimeter around BigQuery & Vertex AI",
        "Model Armor prompt-injection & DLP screening",
        "Access Transparency & Key Access Justifications",
    ],
    "healthcare": [
        "HIPAA BAA & Assured Workloads boundary",
        "Cloud DLP de-identification pipeline for PHI",
        "CMEKs + VPC Service Controls + Audit Logs (Data Access enabled)",
        "Model Armor PII/PHI output redaction",
    ],
    "retail": [
        "PCI-DSS segmented VPC & Cloud Armor WAF",
        "Vertex AI Search & Conversation IAM least-privilege",
        "Secret Manager rotation & Binary Authorization on Cloud Run",
    ],
    "general": [
        "Organization Policy constraints (constraints/iam.disableServiceAccountKeyCreation)",
        "Workload Identity Federation for keyless GitHub Actions CI/CD",
        "Cloud Armor + IAP zero-trust ingress",
        "Cloud Trace & Cloud Logging centralized audit sink",
    ],
}


def estimate_cloud_workload_tco(
    monthly_vcpu: int,
    storage_tb: float,
    gpu_count: int = 0,
    commitment_years: int = 3,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Estimates monthly and annual Google Cloud TCO and Committed Use Discount (CUD) savings.

    Args:
        monthly_vcpu: Total vCPU cores provisioned across GKE / Cloud Run / GCE.
        storage_tb: Persistent SSD and Cloud Storage volume in terabytes.
        gpu_count: Number of NVIDIA L4 / H100 class GPUs for AI inference.
        commitment_years: CUD commitment term in years (0 for on-demand, 1, or 3).
        tool_context: ADK ToolContext used to persist financial estimates in session state.

    Returns:
        A dictionary with itemized on-demand vs. discounted monthly/annual USD costs.
    """
    normalized_years = commitment_years if commitment_years in _CUD_DISCOUNT_RATES else 3
    validated = WorkloadSizingInput(
        monthly_vcpu=monthly_vcpu,
        storage_tb=storage_tb,
        gpu_count=gpu_count,
        commitment_years=normalized_years,  # type: ignore[arg-type]
    )

    compute_on_demand = validated.monthly_vcpu * 31.50
    gpu_on_demand = validated.gpu_count * 780.00
    storage_monthly = validated.storage_tb * 23.00

    discount = _CUD_DISCOUNT_RATES[validated.commitment_years]
    discounted_compute_gpu = (compute_on_demand + gpu_on_demand) * (1.0 - discount)
    net_monthly_usd = round(discounted_compute_gpu + storage_monthly, 2)
    on_demand_monthly_usd = round(compute_on_demand + gpu_on_demand + storage_monthly, 2)
    annual_savings_usd = round((on_demand_monthly_usd - net_monthly_usd) * 12, 2)

    tshirt_tier = (
        "Small (Pilot)"
        if net_monthly_usd < 5_000
        else "Medium (Departmental)"
        if net_monthly_usd < 25_000
        else "Large (Enterprise Production)"
    )

    result: dict[str, Any] = {
        "status": "success",
        "tshirt_tier": tshirt_tier,
        "commitment_years": validated.commitment_years,
        "cud_discount_pct": int(discount * 100),
        "on_demand_monthly_usd": on_demand_monthly_usd,
        "net_monthly_usd": net_monthly_usd,
        "net_annual_usd": round(net_monthly_usd * 12, 2),
        "estimated_annual_cud_savings_usd": annual_savings_usd,
    }

    if tool_context is not None:
        tool_context.state["latest_tco_estimate"] = result
        history = list(tool_context.state.get("user:sizing_history", []))
        history.append({"vcpu": monthly_vcpu, "net_monthly_usd": net_monthly_usd})
        tool_context.state["user:sizing_history"] = history[-10:]

    return result


def check_compliance_requirements(
    industry: str,
    data_residency_region: str = "asia-east1",
    handles_pii: bool = True,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Maps customer industry and residency requirements to mandatory Google Cloud security controls.

    Args:
        industry: Target industry vertical (e.g. 'fsi', 'healthcare', 'retail', 'general').
        data_residency_region: Required GCP region for data residency (e.g. 'asia-east1', 'us-central1').
        handles_pii: Whether the workload processes PII/PHI or regulated customer records.
        tool_context: ADK ToolContext used to store compliance posture in session state.

    Returns:
        A structured compliance posture dictionary with mandatory controls and residency policy.
    """
    key = industry.strip().lower()
    matched_key = next((k for k in _INDUSTRY_CONTROLS if k in key), "general")
    controls = list(_INDUSTRY_CONTROLS[matched_key])
    if handles_pii and "Cloud DLP inspection & Model Armor PII redaction" not in controls:
        controls.append("Cloud DLP inspection & Model Armor PII redaction")

    posture: dict[str, Any] = {
        "status": "success",
        "normalized_industry": matched_key,
        "data_residency_region": data_residency_region,
        "org_policy_location_constraint": f"in:{data_residency_region}-locations",
        "handles_pii": handles_pii,
        "mandatory_controls": controls,
    }

    if tool_context is not None:
        tool_context.state["compliance_posture"] = posture
        tool_context.state["user:preferred_industry"] = matched_key

    return posture


def save_engagement_artifact(
    artifact_title: str,
    executive_summary: str,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Persists a structured consulting deliverable into session state for downstream retrieval.

    Args:
        artifact_title: Title of the architecture or proposal deliverable.
        executive_summary: Concise markdown summary of the approved deliverable.
        tool_context: ADK ToolContext for state storage.

    Returns:
        Confirmation dictionary containing stored artifact count.
    """
    entry = {"title": artifact_title, "summary": executive_summary}
    if tool_context is not None:
        artifacts = list(tool_context.state.get("saved_artifacts", []))
        artifacts.append(entry)
        tool_context.state["saved_artifacts"] = artifacts
        return {"status": "success", "stored_count": len(artifacts), "title": artifact_title}
    return {"status": "success", "stored_count": 1, "title": artifact_title}


def approve_proposal_quality(
    quality_score: int,
    review_notes: str,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Evaluates the draft proposal score and exits the refinement LoopAgent when score >= 85.

    Args:
        quality_score: Integer rubric score from 0 to 100 across architecture, TCO, and security.
        review_notes: Actionable feedback or sign-off justification.
        tool_context: ADK ToolContext used to signal loop escalation when approved.

    Returns:
        Approval status dictionary indicating whether the refinement loop is complete.
    """
    approved = quality_score >= 85
    if tool_context is not None:
        tool_context.state["last_quality_score"] = quality_score
        tool_context.state["critique_feedback"] = review_notes
        if approved:
            tool_context.actions.escalate = True
    return {
        "status": "approved" if approved else "needs_revision",
        "quality_score": quality_score,
        "review_notes": review_notes,
    }
