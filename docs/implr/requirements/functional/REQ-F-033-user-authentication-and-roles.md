---
req_id: REQ-F-033
slug: user-authentication-and-roles
title: User Authentication and Role-Based Access Control
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
  - system-description-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, auth, security]
  story_points:
  components: [authentication, security]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — User Authentication and Role-Based Access Control

## Domain Context
Even in single-user MVP, login is required. The user table must have a role field (admin/operator/end_user) from day 1. Admin panel access is gated by role. JWT access + refresh tokens. OAuth2 deferred to post-MVP.

## Summary
The system must implement username/password authentication with JWT access and refresh tokens, bcrypt password hashing (rounds ≥12), a role field (admin/operator/end_user) on the user table from day one, rate limiting on auth endpoints, and role-based access control gating the admin panel.

## Detailed Description
As specified in ui-design-digest.md business rules 38, 59 and system-description-digest.md business rule 16:

**Authentication:**
- Username/password login (email + password)
- Password hashed with bcrypt, rounds ≥ 12
- On success: return JWT access token (short-lived, e.g. 15 min) + refresh token (long-lived, e.g. 7 days)
- Refresh endpoint: validate refresh token → issue new access token
- Logout: invalidate refresh token

**JWT Claims:**
- user_id, tenant_id, role, issued_at, expires_at
- Access token signed with RS256 (asymmetric) or HS256 (symmetric, acceptable for MVP)

**Rate Limiting:**
- Login endpoint: max 10 attempts per IP per minute
- Refresh endpoint: max 30 attempts per IP per minute
- Exceeded rate limit → HTTP 429

**Role-Based Access Control:**
- Role field: admin | operator | end_user (on user table from day 1)
- Admin panel endpoints require admin or operator role → HTTP 403 for end_user
- Feature endpoints accessible by all authenticated users
- Tenant isolation: tenant_id on every user data table enforced at query layer (multi-tenant schema from day 1)

**OAuth2:** Deferred to post-MVP. No OAuth2 providers in MVP.

## Desired Outcome
Every user must authenticate before accessing any application feature, admin functions are protected by role, and tenant data isolation is enforced at the data layer from the first deployment.

## Acceptance Criteria
- [ ] AC-001: Given a user submits valid credentials, the system returns a JWT access token and a refresh token; the access token expires in ≤15 minutes.
- [ ] AC-002: Given incorrect credentials, the system returns HTTP 401 and does not reveal whether the email or password was wrong.
- [ ] AC-003: Given a login endpoint receives more than 10 requests from the same IP within 60 seconds, subsequent requests receive HTTP 429 until the window resets.
- [ ] AC-004: Given a request to any admin panel endpoint with a JWT containing role=end_user, the response is HTTP 403 Forbidden.
- [ ] AC-005: Given the user table is created, it includes a role column of type enum(admin, operator, end_user) and a tenant_id column; both are non-nullable.
- [ ] AC-006: Given a user's password is stored, it is hashed with bcrypt at ≥12 rounds; no plaintext or reversible encoding is present in the database.

## Out of Scope
- OAuth2 / social login (deferred to post-MVP)
- Two-factor authentication (post-MVP)
- Session-based authentication (JWT only)

## Open Questions
| # | Question | Source of Ambiguity | Raised | Resolved |
|---|----------|--------------------|--------|----------|
| 1 | What is the precise boundary between MVP username/password auth and the "OAuth2 production" auth mentioned in system-description-digest.md? When does the OAuth2 migration trigger? | root-synthesis Ambiguities Detected: "OAuth2 scope: MVP username/password vs OAuth2 boundary undefined" | 2026-06-02 | ☐ |

## Data Models
```
user:
  user_id: UUID (PK)
  tenant_id: UUID (non-nullable)
  email: string (unique)
  password_hash: string (bcrypt ≥12 rounds)
  role: enum(admin, operator, end_user) (non-nullable)
  created_at: timestamp
  updated_at: timestamp

refresh_token:
  token_id: UUID (PK)
  user_id: UUID (FK → user)
  token_hash: string
  issued_at: timestamp
  expires_at: timestamp
  revoked_at: timestamp | null
```

## Process Sequence
1. User POST /auth/login with email + password
2. Lookup user by email; verify bcrypt hash
3. On success: generate JWT access token + refresh token; store refresh_token row
4. Return tokens to client
5. Client sends Authorization: Bearer {access_token} on subsequent requests
6. Protected endpoints validate JWT; role check for admin/operator gates
7. On access token expiry: POST /auth/refresh with refresh_token → new access token

## Subtasks
- [ ] ST-001: Implement user table migration with role + tenant_id from day 1 — complexity: S
- [ ] ST-002: Implement login endpoint with bcrypt verify and JWT issuance — complexity: M
- [ ] ST-003: Implement JWT middleware (validate, extract claims) — complexity: M
- [ ] ST-004: Implement refresh token endpoint — complexity: S
- [ ] ST-005: Implement rate limiting on auth endpoints — complexity: S
- [ ] ST-006: Implement role-based access control decorator/middleware — complexity: M
- [ ] ST-007: Unit tests for auth flows, rate limiting, role enforcement — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | Business Rules 38, 59; Architecture Signals | Role field from day 1, admin panel role gate, tenant_id on all tables |
| system-description-digest.md | Business Rules 16 | tenant_id from day one, row-level isolation |
