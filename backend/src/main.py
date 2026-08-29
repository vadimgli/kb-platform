"""ArtifactForge Multi-Agent Service Entry Point."""

from __future__ import annotations

from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.a2a.server import create_a2a_router
from src.agents.executor import ExecutorAgent
from src.agents.planner import PlannerAgent
from src.agents.registry import agent_registry
from src.capabilities.registry import capability_registry
from src.core.config import config
from src.gateway.router import gateway_router

app = FastAPI(
  title="ArtifactForge Multi-Agent Platform",
  description="Enterprise Deliverables & Scoping Engine",
  version="1.0.0",
)

allowed_origins = (
  config.cors_origins_list if config.cors_origins_list else ["*"]
)
app.add_middleware(
  CORSMiddleware,
  allow_origins=allowed_origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# 1. Register Core Agents in AgentRegistry
planner_agent = PlannerAgent()
executor_agent = ExecutorAgent()

agent_registry.register_agent(
  name="planner",
  agent=planner_agent,
  skills=capability_registry.export_as_a2a_skills(),
)
agent_registry.register_agent(
  name="executor",
  agent=executor_agent,
)

# 2. Mount Enterprise Agent Gateway
app.include_router(gateway_router, prefix="/api/v1")

# 3. Mount A2A Agent Card & Protocol Endpoints
a2a_router = create_a2a_router(
  agent=planner_agent,
  agent_name="artifactforge_agent",
  description="In-Scope Scoping Deliverables Engine",
  skills=capability_registry.export_as_a2a_skills(),
)
app.include_router(a2a_router)


@app.get("/healthz", tags=["Health"])
async def health_check() -> dict[str, str]:
  """Liveness probe for Google Cloud Run."""
  return {"status": "ok", "service": "artifactforge-api"}


@app.get("/readyz", tags=["Health"])
async def readiness_check() -> dict[str, Any]:
  """Readiness probe checking configuration and service availability."""
  return {
    "status": "ready",
    "project_id": config.gcp_project_id,
    "location": config.gcp_location,
    "planner_model": config.planner_model or config.default_model,
    "executor_model": config.executor_model or config.lightweight_model,
    "capabilities": [c.capability_id for c in capability_registry.list_all()],
  }
