"""
ai.workflows.event_deep_dive.nodes — all 8 graph nodes for the Event Deep-Dive workflow.

Node execution order (PLAN-F-010):
  1. fetch_event_full              (DeterministicNode)
  2. fetch_market_reaction_so_far  (DeterministicNode)
  3. run_exposure_analysts         (DeterministicNode — asyncio.gather fan-out)
  4. event_deep_dive_agent         (AgentNode)
  5. historical_context_agent      (AgentNode)
  6. recommendation_synthesizer    (AgentNode)
  7. narrative_writer              (AgentNode — last AgentNode)
  8. evaluate_quality              (DeterministicNode — terminal quality gate)
"""
