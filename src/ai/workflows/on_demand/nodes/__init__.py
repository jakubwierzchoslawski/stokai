"""
ai.workflows.on_demand.nodes — DeterministicNode and AgentNode implementations.

Node execution order:
  1. fetch_company_state      (DeterministicNode)
  2. fetch_active_events      (DeterministicNode)
  3. exposure_analyst         (AgentNode)
  4. historical_context       (AgentNode)
  5. anomaly_detector         (AgentNode)
  6. recommendation_synthesizer (AgentNode)
  7. narrative_writer         (AgentNode)
  8. evaluate_quality         (DeterministicNode — terminal quality gate)
"""
