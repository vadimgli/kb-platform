# Agent Operating Guidelines & Architecture Blueprint (AGENT.md)
# Enterprise Google ADK Multi-Agent Framework

This document defines the engineering standards, prompt versioning lifecycle, and multi-agent orchestration patterns used in this codebase. All future agents, subagents, and scaffolding must strictly adhere to these Google ADK enterprise standards.

---

## 🏛️ 1. Versioned Prompt Lifecycle (`src/prompts/`)

Instead of hardcoding raw strings or prompt templates inside Python source files, all agent system instructions MUST be versioned declaratively in YAML or Markdown files under `src/prompts/`.

### Schema (`src/prompts/planner_prompt_v1.yaml`)

```yaml
version: "1.0"
name: "planner_prompt_v1"
description: "System instructions for ADK PlannerAgent diagnosing domain anomalies"
system_instruction: |
  You are an expert AI Assistant and Reasoning Diagnostic Copilot.
  By default, act as an intelligent, conversational Gemini assistant using the provided Short-Term Memory and Long-Term Memory Bank.

  MULTIMODAL VISION MANDATE:
  - You are a native MULTIMODAL AI Assistant capable of analyzing attached images, dashboards, and error logs.
  - Formulate 2 to 4 numbered diagnostic execution steps grounded in official RAG Documentation citations.
```

---

## 🤖 2. Base Agent Class & GenAI Client (`src/agents/llm_agent.py`)

All agents inherit from `BaseLLMAgent` (or `LlmAgent`), which handles prompt loading, lazy GenAI client initialization, token counting, and estimated cost calculations via Google GenAI SDK (`google-genai`):

```python
from typing import Any
from google import genai
import yaml
from src.core.config import config


class LlmAgent:
  """Base class for all ADK agents in the Planner-Executor architecture."""

  def __init__(
    self,
    prompt_path: str,
    model: str = "gemini-2.5-flash",
    **kwargs: Any,
  ) -> None:
    self.prompt_path = prompt_path
    self.model = model
    self.system_instruction = self._load_prompt(prompt_path)
    self._client: genai.Client | None = None

  def _load_prompt(self, path: str) -> str:
    """Loads system instructions from versioned YAML/Markdown files."""
    with open(path, "r", encoding="utf-8") as f:
      if path.endswith(".yaml") or path.endswith(".yml"):
        data = yaml.safe_load(f)
        if "system_instruction" not in data:
          raise ValueError(
            f"YAML at {path} must contain 'system_instruction' key."
          )
        return str(data["system_instruction"]).strip()
      return f.read().strip()

  @property
  def client(self) -> genai.Client:
    """Lazy-loads Google GenAI Client with Application Default Credentials (ADC)."""
    if self._client is None:
      self._client = genai.Client(
        vertexai=True,
        project=config.gcp_project_id,
        location=config.gcp_location,
      )
    return self._client
```

---

## 🧠 3. Diagnostic Reasoning Agent (`src/agents/planner.py`)

The **Planner Agent** handles task breakdown, multi-modal vision inspection, and RAG synthesis. It enforces strict **Pydantic Structured Output** (`ExecutionPlan`) via Gemini JSON Mode:

```python
from typing import Any
from google.genai import types
from src.agents.llm_agent import LlmAgent
from src.models.schemas import ExecutionPlan


class PlannerAgent(LlmAgent):
  """Plans diagnostic workflows grounded in RAG runbooks and incident context."""

  def __init__(self, prompt_path: str = "src/prompts/planner_prompt_v1.yaml"):
    super().__init__(prompt_path=prompt_path, model="gemini-2.5-flash")

  async def generate_plan(
    self,
    query: str,
    context_snippets: list[dict[str, Any]],
    image_bytes: bytes | None = None,
  ) -> ExecutionPlan:
    contents = [
      f"User Incident Query: {query}",
      f"Retrieved RAG Documentation:\n{context_snippets}",
    ]
    if image_bytes:
      contents.append(
        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
      )

    # Google GenAI Structured JSON Schema Mode
    response = await self.client.aio.models.generate_content(
      model=self.model,
      contents=contents,
      config=types.GenerateContentConfig(
        system_instruction=self.system_instruction,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=ExecutionPlan,  # Pydantic Enforcement
      ),
    )
    return ExecutionPlan.model_validate_json(response.text)
```

---

## ⚡ 4. Deterministic Action Syntax Agent (`src/agents/executor.py`)

The **Executor Agent** uses asymmetric model tiering (**Gemini 2.5 Flash-Lite** or **Gemini 3.5 Flash-Lite**) with `temperature=0.0` for sub-150ms deterministic action formatting:

```python
import json
from google.genai import types
from src.agents.llm_agent import LlmAgent
from src.models.schemas import AgentAction


class ExecutorAgent(LlmAgent):
  """Formats diagnostic steps into safe, flag-accurate domain actions."""

  def __init__(self, prompt_path: str = "src/prompts/executor_prompt_v1.yaml"):
    super().__init__(prompt_path=prompt_path, model="gemini-2.5-flash-lite")

  async def generate_actions(
    self, steps: list[str], target_context: str = "default"
  ) -> list[AgentAction]:
    contents = [
      f"Target Context: {target_context}",
      "Steps to Translate:\n" + "\n".join(f"- {s}" for s in steps),
    ]
    response = await self.client.aio.models.generate_content(
      model=self.model,
      contents=contents,
      config=types.GenerateContentConfig(
        system_instruction=self.system_instruction,
        temperature=0.0,  # Zero-temperature for deterministic syntax
        response_mime_type="application/json",
        response_schema=list[AgentAction],
      ),
    )
    return [
      AgentAction.model_validate(a) for a in json.loads(response.text)
    ]
```

---

## 🔄 5. Multi-Agent Sequencing & Orchestration (`src/main.py`)

The API gateway coordinates the end-to-end execution flow with DLP sanitization, RAG retrieval, multi-agent hand-offs, and AST safety guardrails:

```python
@app.post("/api/v1/query", response_model=ExecutionPlan)
async def query_agent(request: AgentQueryRequest):
  # 1. DLP Guardrail PII & Credential Redaction
  sanitized_query, _ = sanitize_user_prompt_with_dlp_and_model_armor(
    request.query
  )
  request.query = sanitized_query

  # 2. RAG Retrieval from Vertex AI Search
  rag_snippets = await rag_service.search_documentation(request.query)

  # 3. Agent 1: Diagnostic Reasoning (PlannerAgent)
  plan = await planner_agent.generate_plan(
    query=request.query,
    context_snippets=rag_snippets,
    image_bytes=request.image_data,
  )

  # 4. Agent 2: Action Synthesis (ExecutorAgent)
  actions = await executor_agent.generate_actions(
    steps=plan.steps, target_context=request.target_context
  )

  # 5. AST Guardrails Risk Labeling (LOW / MEDIUM / HIGH)
  for act in actions:
    act.risk_level = classify_action_risk(act.payload)
  plan.actions = actions

  return plan
```

---

## 🛡️ 6. Core Engineering Principles

1. **Zero-Permission Advisory Security**:
   * The backend service account NEVER holds direct cluster or infrastructure mutation permissions. All actions are advisory and executed by authorized human operators.
2. **Asymmetric Model Tiering**:
   * Complex reasoning & vision -> **Gemini Flash / Pro** (`temperature=0.1`).
   * Syntax formatting & schema output -> **Gemini Flash-Lite** (`temperature=0.0`).
3. **Deterministic Evaluation Rubrics**:
   * Every release is evaluated against a 150+ Golden Scenario dataset with programmatic rubric scoring:
     $$\\text{Score} = 0.35 \\times S_{\\text{action}} + 0.25 \\times S_{\\text{kw}} + 0.25 \\times S_{\\text{risk}} + 0.15 \\times S_{\\text{safety}}$$
4. **Asynchronous Non-Blocking Telemetry**:
   * BigQuery analytics rows and Cloud Trace OpenTelemetry spans are logged in a background `ThreadPoolExecutor` with 0ms user streaming latency penalty.
