"""Pipeline exception hierarchy.

All exceptions that can halt the Mode A pipeline are subclasses of
``PipelineHalt``.  The executor catches ``PipelineHalt`` subclasses and uses
them to set the correct ``pipeline_status`` on the raw event record:

  - ``DuplicateEvent``      → pipeline_status = "duplicate"
  - any other ``PipelineHalt`` → pipeline_status = "failed"

Single Responsibility: this module contains only exception definitions.
"""
from __future__ import annotations


class PipelineHalt(Exception):
    """Base exception for any condition that halts the pipeline.

    Parameters
    ----------
    step_name:
        The ``PipelineStep.step_name`` value of the step that raised.
    detail:
        Human-readable error detail logged internally (never sent to clients).
    """

    def __init__(self, step_name: str, detail: str) -> None:
        self.step_name = step_name
        self.detail = detail
        super().__init__(f"[{step_name}] {detail}")


class DuplicateEvent(PipelineHalt):
    """Raised by Step 2 (DEDUPLICATE) when the event fingerprint is already present.

    The executor catches this subclass and sets ``pipeline_status = duplicate``
    instead of ``failed``.
    """


class ClassificationError(PipelineHalt):
    """Raised when the LLM classification response cannot be used."""


class InvalidCategoryError(ClassificationError):
    """Raised when the LLM returns a category not in the 6-value enum."""


class InvalidIntensityError(ClassificationError):
    """Raised when the LLM returns an intensity value outside 1–5."""
