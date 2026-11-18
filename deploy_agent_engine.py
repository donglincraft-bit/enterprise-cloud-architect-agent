"""Deploys root_agent directly to Vertex AI Agent Engine (Reasoning Engine)."""

from __future__ import annotations

import argparse
import vertexai
from vertexai import agent_engines
from consulting_agent.agent import root_agent


def deploy(project: str, location: str, staging_bucket: str | None = None) -> None:
    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)
    remote_app = agent_engines.create(
        agent_engine=root_agent,
        requirements=[
            "google-adk>=1.15.0",
            "google-genai>=1.35.0",
            "pydantic>=2.9.0",
            "opentelemetry-api>=1.28.0",
            "opentelemetry-sdk>=1.28.0",
        ],
        display_name="enterprise-cloud-architect-copilot",
        description="Multi-Agent Enterprise Cloud Architecture, FinOps TCO & Compliance Co-Pilot",
    )
    print(f"Deployed Vertex AI Agent Engine resource: {remote_app.resource_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy ADK agent to Vertex AI Agent Engine")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--location", default="us-central1", help="GCP Region")
    parser.add_argument("--staging-bucket", default=None, help="Optional GCS gs:// bucket")
    args = parser.parse_args()
    deploy(args.project, args.location, args.staging_bucket)
