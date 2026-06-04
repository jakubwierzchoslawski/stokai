"""
Unit tests for MemoryService — evidence gate logic and record_* methods.

TASK-008 tests: propose_semantic_fact evidence gate
TASK-012 tests: record_workflow_start, record_agent_invocation, record_tool_call,
                record_user_feedback
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocationCreate,
    ToolCallCreate,
    WorkflowRun,
    WorkflowStatus,
)
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    UserFeedback,
    UserFeedbackCreate,
)
from src.ai.memory.schemas.semantic_schemas import SemanticFactStaging, SemanticFactStagingCreate


# ── Factory helpers ───────────────────────────────────────────────────────────


def _make_workflow_run(tenant_id: uuid.UUID | None = None) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=uuid.uuid4(),
        workflow_type="mode_b_analysis",
        tenant_id=tenant_id or uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        status=WorkflowStatus.RUNNING,
    )


def _make_staging(evidence_count: int = 1) -> SemanticFactStaging:
    return SemanticFactStaging(
        staging_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        fact_text="Apple expanding in Southeast Asia",
        evidence_count=evidence_count,
        source_invocation_ids=[],
        created_at=datetime.now(tz=timezone.utc),
    )


def _build_service(
    episodic=None,
    semantic=None,
    procedural=None,
    feedback=None,
    improvement=None,
    embedding_fn=None,
    session=None,
):
    from src.ai.memory.services.memory_service import MemoryService

    return MemoryService(
        episodic_repo=episodic or AsyncMock(),
        semantic_repo=semantic or AsyncMock(),
        procedural_repo=procedural or AsyncMock(),
        feedback_repo=feedback or AsyncMock(),
        improvement_repo=improvement or AsyncMock(),
        embedding_fn=embedding_fn,
        session=session,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TASK-008 — Evidence gate
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_propose_semantic_fact_new_fact_creates_staging_row():
    """First proposal: no staging row → stage_fact called, committed=False."""
    entity_id = uuid.uuid4()
    staging = _make_staging(evidence_count=1)
    staging.entity_id = entity_id

    semantic_repo = AsyncMock()
    semantic_repo.stage_fact = AsyncMock(return_value=staging)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    svc = _build_service(semantic=semantic_repo, session=session)

    fact_create = SemanticFactStagingCreate(
        entity_id=entity_id,
        fact_text="New fact about Apple",
        source_invocation_id=uuid.uuid4(),
    )
    result = await svc.propose_semantic_fact(fact_create)

    semantic_repo.stage_fact.assert_called_once()
    assert result.evidence_count == 1
    assert result.committed is False  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_propose_semantic_fact_second_time_increments_evidence_count():
    """Second proposal: staging row exists → increment_evidence, committed=False."""
    entity_id = uuid.uuid4()
    existing_staging = _make_staging(evidence_count=1)
    existing_staging.entity_id = entity_id

    incremented_staging = _make_staging(evidence_count=2)
    incremented_staging.staging_id = existing_staging.staging_id
    incremented_staging.entity_id = entity_id

    semantic_repo = AsyncMock()
    semantic_repo.increment_evidence = AsyncMock(return_value=incremented_staging)

    # Simulate finding existing staging row in DB
    from src.ai.memory.models.semantic_models import SemanticFactStaging as StagingORM
    staging_orm = MagicMock(spec=StagingORM)
    staging_orm.staging_id = existing_staging.staging_id
    staging_orm.entity_id = entity_id
    staging_orm.fact_text = "Apple expanding in Southeast Asia"
    staging_orm.evidence_count = 1
    staging_orm.source_invocation_ids = []
    staging_orm.created_at = datetime.now(tz=timezone.utc)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = staging_orm
    session.execute = AsyncMock(return_value=result_mock)

    svc = _build_service(semantic=semantic_repo, session=session)

    fact_create = SemanticFactStagingCreate(
        entity_id=entity_id,
        fact_text="Apple expanding in Southeast Asia",
        source_invocation_id=uuid.uuid4(),
    )
    result = await svc.propose_semantic_fact(fact_create)

    semantic_repo.increment_evidence.assert_called_once()
    assert result.evidence_count == 2
    assert result.committed is False  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_propose_semantic_fact_third_time_triggers_commit():
    """Third proposal: evidence_count reaches 3 → commit_fact called, committed=True."""
    entity_id = uuid.uuid4()
    existing_staging = _make_staging(evidence_count=2)
    existing_staging.entity_id = entity_id

    committed_staging = _make_staging(evidence_count=3)
    committed_staging.staging_id = existing_staging.staging_id
    committed_staging.entity_id = entity_id

    from src.ai.memory.schemas.semantic_schemas import SemanticFact
    committed_fact = SemanticFact(
        fact_id=uuid.uuid4(),
        entity_id=entity_id,
        fact_text="Apple expanding in Southeast Asia",
        embedding=[0.0] * 1536,
        evidence_count=3,
        last_confirmed=datetime.now(tz=timezone.utc),
        source_invocations=committed_staging.source_invocation_ids,
        created_at=datetime.now(tz=timezone.utc),
    )

    semantic_repo = AsyncMock()
    semantic_repo.increment_evidence = AsyncMock(return_value=committed_staging)
    semantic_repo.commit_fact = AsyncMock(return_value=committed_fact)

    from src.ai.memory.models.semantic_models import SemanticFactStaging as StagingORM
    staging_orm = MagicMock(spec=StagingORM)
    staging_orm.staging_id = existing_staging.staging_id
    staging_orm.entity_id = entity_id
    staging_orm.fact_text = "Apple expanding in Southeast Asia"
    staging_orm.evidence_count = 2
    staging_orm.source_invocation_ids = []
    staging_orm.created_at = datetime.now(tz=timezone.utc)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = staging_orm
    session.execute = AsyncMock(return_value=result_mock)

    mock_embedding_fn = AsyncMock(return_value=[0.1] * 1536)
    svc = _build_service(semantic=semantic_repo, session=session, embedding_fn=mock_embedding_fn)

    fact_create = SemanticFactStagingCreate(
        entity_id=entity_id,
        fact_text="Apple expanding in Southeast Asia",
        source_invocation_id=uuid.uuid4(),
    )
    result = await svc.propose_semantic_fact(fact_create)

    semantic_repo.commit_fact.assert_called_once()
    mock_embedding_fn.assert_called_once()
    assert result.committed is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_committed_fact_is_queryable_via_query_semantic_memory():
    """query_semantic_memory delegates to semantic_repo.query_facts."""
    from src.ai.memory.schemas.semantic_schemas import SemanticFact
    fact = SemanticFact(
        fact_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        fact_text="Test fact",
        embedding=[0.1] * 1536,
        evidence_count=3,
        last_confirmed=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
    )

    semantic_repo = AsyncMock()
    semantic_repo.query_facts = AsyncMock(return_value=[fact])

    svc = _build_service(semantic=semantic_repo)

    results = await svc.query_semantic_memory(query_embedding=[0.1] * 1536, limit=5)

    semantic_repo.query_facts.assert_called_once_with(
        embedding=[0.1] * 1536, limit=5, exclude_decayed=True
    )
    assert len(results) == 1


@pytest.mark.asyncio
async def test_embedding_fn_only_called_when_evidence_count_reaches_3():
    """Embedding function must NOT be called for first or second proposals."""
    entity_id = uuid.uuid4()
    staging = _make_staging(evidence_count=1)
    staging.entity_id = entity_id

    semantic_repo = AsyncMock()
    semantic_repo.stage_fact = AsyncMock(return_value=staging)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    mock_embedding_fn = AsyncMock(return_value=[0.1] * 1536)
    svc = _build_service(semantic=semantic_repo, session=session, embedding_fn=mock_embedding_fn)

    fact_create = SemanticFactStagingCreate(
        entity_id=entity_id,
        fact_text="Apple expanding in Southeast Asia",
        source_invocation_id=uuid.uuid4(),
    )
    await svc.propose_semantic_fact(fact_create)

    mock_embedding_fn.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# TASK-012 — record_* methods
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_record_workflow_start_returns_workflow_run_with_generated_id():
    from src.ai.memory.interfaces.i_memory_service import WorkflowContext
    tenant_id = uuid.uuid4()
    workflow_run = _make_workflow_run(tenant_id)

    episodic_repo = AsyncMock()
    episodic_repo.append_workflow_run = AsyncMock(return_value=workflow_run)

    svc = _build_service(episodic=episodic_repo)

    ctx = WorkflowContext(workflow_type="mode_b_analysis", tenant_id=tenant_id)
    result = await svc.record_workflow_start(ctx)

    episodic_repo.append_workflow_run.assert_called_once()
    assert result.workflow_id is not None
    assert isinstance(result.workflow_id, uuid.UUID)


@pytest.mark.asyncio
async def test_record_agent_invocation_delegates_correctly():
    from src.ai.memory.schemas.episodic_schemas import AgentInvocation
    workflow_id = uuid.uuid4()
    agent_inv = AgentInvocation(
        invocation_id=uuid.uuid4(),
        workflow_id=workflow_id,
        agent_role_id="relevance-analyst",
        started_at=datetime.now(tz=timezone.utc),
    )

    episodic_repo = AsyncMock()
    episodic_repo.append_agent_invocation = AsyncMock(return_value=agent_inv)

    svc = _build_service(episodic=episodic_repo)

    inv_create = AgentInvocationCreate(
        workflow_id=workflow_id, agent_role_id="relevance-analyst"
    )
    result = await svc.record_agent_invocation(inv_create)

    episodic_repo.append_agent_invocation.assert_called_once_with(inv_create)
    assert result.workflow_id == workflow_id


@pytest.mark.asyncio
async def test_record_tool_call_delegates_and_references_invocation_id():
    from src.ai.memory.schemas.episodic_schemas import ToolCall
    invocation_id = uuid.uuid4()
    tool_call = ToolCall(
        tool_call_id=uuid.uuid4(),
        invocation_id=invocation_id,
        tool_name="fetch_price_data",
        called_at=datetime.now(tz=timezone.utc),
    )

    episodic_repo = AsyncMock()
    episodic_repo.append_tool_call = AsyncMock(return_value=tool_call)

    svc = _build_service(episodic=episodic_repo)

    call_create = ToolCallCreate(invocation_id=invocation_id, tool_name="fetch_price_data")
    result = await svc.record_tool_call(call_create)

    episodic_repo.append_tool_call.assert_called_once_with(call_create)
    assert result.invocation_id == invocation_id


@pytest.mark.asyncio
async def test_record_user_feedback_thumbs_down_inserts_without_elevated_permissions():
    """Any authenticated role can submit feedback — no role check needed."""
    feedback_row = UserFeedback(
        feedback_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        report_id=uuid.uuid4(),
        feedback_type=FeedbackType.THUMBS_DOWN,
        source=FeedbackSource.IN_APP,
        submitted_at=datetime.now(tz=timezone.utc),
    )

    feedback_repo = AsyncMock()
    feedback_repo.append_feedback = AsyncMock(return_value=feedback_row)

    svc = _build_service(feedback=feedback_repo)

    fb_create = UserFeedbackCreate(
        tenant_id=uuid.uuid4(),
        report_id=uuid.uuid4(),
        feedback_type=FeedbackType.THUMBS_DOWN,
        source=FeedbackSource.IN_APP,
    )
    result = await svc.record_user_feedback(fb_create)

    feedback_repo.append_feedback.assert_called_once_with(fb_create)
    assert result.feedback_type == "thumbs_down"


@pytest.mark.asyncio
async def test_record_user_feedback_invalid_feedback_type_raises_value_error():
    """Invalid feedback_type must be rejected before touching any repository."""
    feedback_repo = AsyncMock()
    svc = _build_service(feedback=feedback_repo)

    # Bypass the FeedbackType enum by creating a raw object
    fb_create = MagicMock()
    fb_create.feedback_type = "INVALID_TYPE"  # not a valid FeedbackType
    # Make hasattr(fb_create.feedback_type, "value") return False
    type(fb_create.feedback_type).value = property(
        side_effect=AttributeError
    )

    with pytest.raises((ValueError, AttributeError)):
        await svc.record_user_feedback(fb_create)

    feedback_repo.append_feedback.assert_not_called()
