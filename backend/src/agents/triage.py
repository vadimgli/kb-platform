"""Primary Triage Agent for Tier 1 conversational multi-agent routing."""

from pathlib import Path
from src.agents.llm_agent import LlmAgent
from src.agents.specialists.base import BaseSpecialistSubAgent
from src.agents.specialists.scoping import ScopingSpecialistSubAgent
from src.core.config import config
from src.core.logging_config import get_logger
from src.models.schemas import (
  ChatSessionState,
  ChatSessionTurn,
  ChatTurnRequest,
  ChatTurnResponse,
)

logger = get_logger("artifactforge.agents.triage")

DEFAULT_PROMPT = (
  Path(__file__).parent.parent / "prompts" / "triage_prompt_v1.yaml"
)


class PrimaryTriageAgent(LlmAgent):
  """Primary conversational front-door agent with dynamic sub-agent handoffs."""

  def __init__(
    self,
    prompt_path: str = str(DEFAULT_PROMPT),
    sub_agents: list[BaseSpecialistSubAgent] | None = None,
  ) -> None:
    super().__init__(
      prompt_path=prompt_path,
      model_name=config.planner_model,
    )
    self.sub_agents: dict[str, BaseSpecialistSubAgent] = {}
    default_specialists = sub_agents or [ScopingSpecialistSubAgent()]
    for sa in default_specialists:
      self.register_sub_agent(sa)

  def register_sub_agent(self, specialist: BaseSpecialistSubAgent) -> None:
    """Registers a new domain specialist sub-agent."""
    self.sub_agents[specialist.agent_name] = specialist
    logger.info("Registered specialist sub-agent: '%s'", specialist.agent_name)

  async def route_and_process(
    self,
    turn_req: ChatTurnRequest,
    session_state: ChatSessionState,
  ) -> ChatTurnResponse:
    """Evaluates intent, manages session handoff, and dispatches turn."""
    logger.info(
      "TriageAgent evaluating turn for session '%s' (active: '%s')",
      session_state.session_id,
      session_state.active_agent,
    )

    # 1. Check if an active specialist is already engaged
    active_name = session_state.active_agent
    if active_name != "triage_agent" and active_name in self.sub_agents:
      specialist = self.sub_agents[active_name]
      response = await specialist.handle_turn(
        user_message=turn_req.message,
        session_state=session_state,
      )
      self._record_turns(session_state, turn_req, response)
      return response

    # 2. Evaluate intent for initial delegation
    msg_lower = turn_req.message.lower()
    target_specialist_name = "scoping_specialist"  # Default primary capability

    if target_specialist_name in self.sub_agents:
      logger.info(
        "Handoff / Transfer: Transferring session pointer to '%s'",
        target_specialist_name,
      )
      session_state.active_agent = target_specialist_name
      specialist = self.sub_agents[target_specialist_name]
      response = await specialist.handle_turn(
        user_message=turn_req.message,
        session_state=session_state,
      )
      self._record_turns(session_state, turn_req, response)
      return response

    # 3. Fallback general triage response
    fallback_reply = (
      "Hello! I am ArtifactForge. I can help you synthesize and refine "
      "project deliverables, such as the In-Scope Responsibilities Matrix."
    )
    fallback_resp = ChatTurnResponse(
      session_id=session_state.session_id,
      client_id=session_state.client_id,
      active_agent="triage_agent",
      reply=fallback_reply,
    )
    self._record_turns(session_state, turn_req, fallback_resp)
    return fallback_resp

  def _record_turns(
    self,
    session_state: ChatSessionState,
    turn_req: ChatTurnRequest,
    response: ChatTurnResponse,
  ) -> None:
    """Appends user and agent turns to conversation history."""
    session_state.history.append(
      ChatSessionTurn(
        role="user",
        agent_name="user",
        message=turn_req.message,
      )
    )
    session_state.history.append(
      ChatSessionTurn(
        role="agent",
        agent_name=response.active_agent,
        message=response.reply,
        deliverables=response.deliverables,
        actions_taken=response.actions_taken,
        doc_url=response.doc_url,
      )
    )
