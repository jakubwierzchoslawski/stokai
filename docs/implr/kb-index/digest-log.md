# digest-log
# Append-only run history for doc-ingest. Newest entry first.
# Format: see kb-index-schema.md § digest-log entry.

## Run 1 — 2026-06-02T00:00:00Z

```yaml
run_at: 2026-06-02T00:00:00Z
trigger: manual
mode: default
files_processed:
  - path: docs/kb/architectural_considerations.md
    checksum: eb14e952c74f04a1c44f12aee13ecc55
    action: new
    digest_written: true
  - path: docs/kb/system_description.md
    checksum: 18189a5fc42d3b090a14b67fdd9eb23e
    action: new
    digest_written: true
  - path: docs/kb/ui_design.md
    checksum: 658153c855e3b69bc90624b223744025
    action: new
    digest_written: true
domains_rebuilt: [root]
master_synthesis_rebuilt: true
contradictions_detected:
  - id: C-001
    type: hard-conflict
    domain: root
    source_a: architectural_considerations.md
    source_b: system_description.md
    summary: "Morning Brief trigger time: 05:30 vs 06:00"
  - id: C-002
    type: hard-conflict
    domain: root
    source_a: architectural_considerations.md
    source_b: system_description.md
    summary: "Total MVP cost: $430-520/month vs $268/month"
  - id: C-003
    type: soft-conflict
    domain: root
    source_a: architectural_considerations.md
    source_b: system_description.md
    summary: "Classification LLM: Claude Haiku 4.5 vs Azure OpenAI GPT-4o-mini"
  - id: C-004
    type: soft-conflict
    domain: root
    source_a: system_description.md
    source_b: ui_design.md
    summary: "MARKET_REGISTRY: code dict vs DB-backed admin-editable table"
  - id: C-005
    type: scope-overlap
    domain: root
    source_a: architectural_considerations.md
    source_b: architectural_considerations.md
    summary: "Reactive Pipeline step count: 12 (body) vs 13 (Decision Summary header)"
  - id: C-006
    type: scope-overlap
    domain: root
    source_a: architectural_considerations.md
    source_b: ui_design.md
    summary: "Twitter/X: primary real-time pipeline trigger vs off-by-default admin toggle"
warnings: []
```
