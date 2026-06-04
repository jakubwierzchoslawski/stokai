---
req_id: REQ-N-006
slug: n-multitenancy-security
title: Multi-Tenancy and Security Isolation
type: non-functional
nfr_category: Security
status: approved
complexity: L
tdd_required: true
source_docs:
  - system-description-digest.md
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "user-authentication-and-roles: JWT and role field foundation" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, security, multitenancy]
  story_points:
  components: [security, data-access]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Multi-Tenancy and Security Isolation

## Domain Context
Multi-tenant schema is mandatory from day one even for single-tenant MVP, to avoid costly retrofit at Phase 5. Row-level isolation prevents IDOR vulnerabilities. Credentials are never stored as plaintext.

## Summary
Every user data table must carry tenant_id enforced at query level; all queries must include tenant_id filter to prevent cross-tenant data access; credentials stored as vault references only; rate limiting enforced on public mutation endpoints; JWT tokens must use standard expiry controls.

## Detailed Description
As specified in system-description-digest.md business rule 16 and ui-design-digest.md business rules 38, 59 and architecture signals:

**tenant_id on all user tables:** Every table containing user-associated data must include a tenant_id column (non-nullable). Added from day one even in single-tenant MVP.

**Row-level isolation:** Every SELECT/UPDATE/DELETE query against user-data tables must include WHERE tenant_id = :current_tenant_id. Repository pattern enforces this; bare SQL without tenant filter must fail code review.

**IDOR prevention:** Resources accessible via URL (e.g. /portfolio/{id}, /company/{id}) must validate that the requested resource belongs to the requesting user's tenant.

**Rate limiting on mutation endpoints:**
- POST /auth/login: 10/minute per IP
- POST /auth/refresh: 30/minute per IP
- POST /portfolio/positions: 100/minute per user
- Admin mutation endpoints: 60/minute per admin user

**JWT security:**
- Access tokens: short-lived (≤15 min)
- Refresh tokens: stored hashed; one-time use rotation
- No sensitive data in JWT payload beyond user_id, tenant_id, role

**Credentials:** source_config table stores vault references (credentials_ref), never raw API keys. Admin panel never displays decrypted credentials.

## Desired Outcome
No user can access another tenant's data; credentials are never exposed in plaintext; rate limiting prevents credential stuffing and API abuse.

## Acceptance Criteria
- [ ] AC-001: Given a repository method that queries user data, it always includes a tenant_id parameter in the WHERE clause; a test asserting that omitting tenant_id raises an error is present and passing.
- [ ] AC-002: Given a user with tenant_id=A attempts to access a resource belonging to tenant_id=B via a guessed URL parameter, the response is HTTP 403 or HTTP 404 (no resource disclosed).
- [ ] AC-003: Given source_config rows in the database, the credentials_ref column contains vault path references only; no column contains a raw API key string.
- [ ] AC-004: Given the login endpoint receives 11 requests from the same IP within 60 seconds, the 11th request receives HTTP 429; the rate limit window resets after 60 seconds.
- [ ] AC-005: Given a JWT access token is issued, it expires within 15 minutes; presenting an expired token returns HTTP 401.

## Out of Scope
- Database-level row security policies (application-level tenant filter is sufficient for MVP)
- Penetration testing (post-launch)

## NFR-Specific Fields

### Measurable Target
- 0 IDOR vulnerabilities: all resource endpoints include tenant ownership validation (verified by code review + automated tests)
- 0 plaintext credentials in source_config (verified by DB schema inspection)
- Rate limit enforced: login ≤10/min/IP, refresh ≤30/min/IP (verified by automated tests)
- JWT access token max TTL: 15 minutes

### Verification Method
- Method: Code review of all repository methods for tenant_id filter; automated security tests for IDOR; DB schema inspection
- Tool/Process: pytest security tests; automated IDOR scan via test suite; bandit static analysis
- Frequency: Per release (code review + tests); quarterly (manual IDOR audit)
- Owner: Security / QA

### Category Rationale
Security NFR because multi-tenant isolation failure leads to data breach across user portfolios. IDOR and credential exposure are OWASP Top 10 risks directly applicable to this system.

## Subtasks
- [ ] ST-001: Add tenant_id (non-nullable) to all user data table migrations — complexity: M
- [ ] ST-002: Implement repository base class enforcing tenant_id filter — complexity: M
- [ ] ST-003: Implement IDOR validation on resource ownership checks — complexity: M
- [ ] ST-004: Implement rate limiting middleware on auth and mutation endpoints — complexity: M
- [ ] ST-005: Security tests for IDOR and tenant isolation — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | Business Rule 16; Non-Functional Signals | tenant_id from day one, row-level isolation |
| ui-design-digest.md | Business Rules 38, 59; Architecture Signals | Admin panel role gate, vault references for credentials, role field from day 1 |
