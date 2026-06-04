"""
ai.hil — Human-in-the-Loop (HIL) pause, resume, and action orchestration.

Components:
  hil_router.py         — Conditional LangGraph edge; checkpoints graph; creates queue item.
  hil_resume.py         — Loads checkpoint; resumes or terminates LangGraph run.
  hil_action_service.py — Applies reviewer decisions; writes Layer 4 + Layer 1 records.
  hil_timeout_task.py   — Celery beat task; terminates overdue pending items.

PLAN-F-013
"""
