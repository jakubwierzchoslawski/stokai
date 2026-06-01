"""PipelineStep Protocol — the interface every step must satisfy.

Single Responsibility: defines only the execution contract.
Interface Segregation: a single ``execute`` method; steps that need
  additional collaborators receive them via their ``__init__``, not here.
"""
from __future__ import annotations

from typing import Protocol

from src.event_pipeline.pipeline_state import PipelineState


class PipelineStep(Protocol):
    """Structural protocol for all 13 Mode A pipeline steps.

    Each step receives the current ``PipelineState`` and must return an updated
    ``PipelineState``.  Steps must not raise bare exceptions — wrap any
    unexpected error in ``PipelineHalt`` before propagating.
    """

    step_name: str  # e.g. "s04_classify"

    async def execute(self, state: PipelineState) -> PipelineState:
        """Execute this step and return the updated state.

        Parameters
        ----------
        state:
            The current pipeline context.

        Returns
        -------
        PipelineState
            Updated context to be passed to the next step.

        Raises
        ------
        PipelineHalt
            Any step-level failure that should halt the entire pipeline.
        """
        ...
