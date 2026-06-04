---
req_id: REQ-N-010
slug: n-ai-accuracy-calibration
title: AI Recommendation Accuracy Calibration
type: non-functional
nfr_category: Reliability
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "evaluation-framework: Tier 3 calibration is part of evaluation framework" }
  - { id: "", reason: "four-layer-memory-subsystem: recommendation_outcome rows in Layer 1 provide calibration data" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [ai, quality, calibration, accuracy]
  story_points:
  components: [evaluation, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — AI Recommendation Accuracy Calibration

## Domain Context
AI recommendations must be verifiably accurate over time, not just subjectively convincing. Tier 3 daily ex-post calibration measures whether high-confidence recommendations are more accurate than low-confidence ones, providing the ground truth for continuous improvement.

## Summary
Tier 3 ex-post calibration must run daily; CORR(confidence, actual_t1d × direction_sign) must be significantly positive over rolling 30-day windows; results reviewed weekly; calibration dashboard visible to admin.

## Detailed Description
As specified in architectural-considerations-digest.md business rules 37, 52, 53, 60, 61:

**Daily ex-post calibration job:**
- Runs once per day
- Joins ai_recommendation rows with actual price changes (actual_t1d, actual_t1w from price_bar data fetched next day)
- Computes: CORR(confidence, actual_t1d × direction_sign) — positive CORR means higher-confidence calls are more often directionally correct
- Tracks: per-action-signal accuracy, mean confidence vs mean accuracy

**Weekly review requirement:**
- Results reviewed by human operator weekly
- If CORR over 30-day rolling window is not significantly positive (threshold configurable), improvement loop is triggered
- Review recorded in admin calibration dashboard

**Significantly positive definition:** CORR ≥ 0.3 over a 30-day rolling window with at least 30 recommendations. Below this threshold triggers the improvement loop.

## Desired Outcome
The system's confidence scores are honest predictors of directional accuracy: a recommendation with confidence 0.8 should be correct more often than one with confidence 0.5.

## Acceptance Criteria
- [ ] AC-001: Given the daily Tier 3 calibration job runs, it produces a calibration_result row for the previous day with CORR(confidence, actual_t1d × direction_sign) computed from all recommendations made that day that now have actual_t1d data available.
- [ ] AC-002: Given 30 days of calibration results with at least 30 recommendations, CORR ≥ 0.3 over the rolling window; if CORR falls below 0.3, the admin calibration dashboard displays a warning flag triggering the improvement loop.
- [ ] AC-003: Given the admin calibration dashboard, it displays a 30-day rolling CORR chart, per-action-signal accuracy breakdown, and a human-readable assessment of calibration health.
- [ ] AC-004: Given a new ai_recommendation row is created, the actual_t1d field is populated the following trading day via the calibration job, closing the feedback loop.

## Out of Scope
- Automated model retraining based on calibration results (human review required)
- Intraday calibration (daily is sufficient for MVP)

## NFR-Specific Fields

### Measurable Target
- CORR(confidence, actual_t1d × direction_sign): must be ≥ 0.3 over 30-day rolling window with ≥30 recommendations
- Calibration job must run daily (verified by job execution log in admin panel)
- Weekly human review: recorded in admin dashboard; improvement loop triggered if CORR < 0.3

### Verification Method
- Method: Automated daily calibration job with CORR computation; admin dashboard review
- Tool/Process: Celery scheduled task; PostgreSQL CORR() function; admin calibration dashboard
- Frequency: Daily (job execution); weekly (human review)
- Owner: Data Science / Product Owner

### Category Rationale
Reliability NFR because if AI confidence is not calibrated against actual outcomes, the confidence score loses its meaning as a routing signal for HIL and auto-send decisions. Uncalibrated confidence scores erode user trust.

## Subtasks
- [ ] ST-001: Implement daily calibration job with CORR computation — complexity: M
- [ ] ST-002: Implement actual_t1d and actual_t1w back-fill from next-day price data — complexity: M
- [ ] ST-003: Implement weekly review flag and improvement loop trigger — complexity: S
- [ ] ST-004: Admin calibration dashboard with 30-day CORR chart — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rules 37, 52, 53, 60, 61; Non-Functional Signals | Tier 3 daily calibration, CORR metric, weekly review, actual_t1d tracking |
