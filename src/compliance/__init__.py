"""
compliance — Cross-cutting compliance and auditability module for StokAI.

Enforces REQ-N-012 obligations:
  - Episodic completeness checks (ComplianceCheckService)
  - Company recommendation track record queries (ComplianceCheckService)
  - Celery beat task for hourly integrity checks (compliance_tasks)
  - Read-only compliance API router (compliance_router)
"""
