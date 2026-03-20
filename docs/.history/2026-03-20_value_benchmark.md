# 2026-03-20 — Value guide (`value-benchmark`)

Development note for documentation changes around [guide/value-benchmark](/guide/value-benchmark).

## Commit `2a0c42e` — *update value benchmark*

**Intent:** reduce time-stamped and checklist content that goes stale quickly, without changing product behavior.

**Removed from `docs/guide/value-benchmark.md`:**

| Section | Reason |
|--------|--------|
| **Local evidence** (pinned commit id, smoke script, regression command) | Becomes outdated on every merge; belongs in CI or release notes, not the user guide. |
| **What to Borrow From the Best OSS** | Roadmap-style ideas; better tracked in [design/evolution](/design/evolution) or issue backlog. |
| **Next Actions for Docs** | Same as above—action lists in guides rot unless someone owns them. |

**Still present after `2a0c42e`:** the longer “Value Assessment” narrative, the OSS comparison table, and “Recommended Positioning” (those were not part of that commit’s deletions).

## Follow-up edit — *Value and Limits*

The guide was further simplified to **Value and Limits**: concise bullets on engineering value (explainable shape, maintenance, UoW, replaceable components) and limits (provider requirement, SQLite default, model-dependent quality). The OSS comparison table and extended positioning copy were dropped here to keep the page maintainable and to match the VitePress sidebar title; positioning nuance can live in [introduction](/guide/introduction) and [evolution](/design/evolution) instead.

## Canonical references

- [Guide: Value and Limits](/guide/value-benchmark)
- [Evolution Roadmap](/design/evolution)
