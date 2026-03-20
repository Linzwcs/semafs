# Writing

`SemaFS.write(content, hint=None, payload=None)` is the canonical write entrypoint.

## 1. Write Semantics

A write does not directly finalize structure. It stages a `PENDING` leaf first, then event-driven maintenance may reorganize and promote.

Internal flow (`engine/intake.py`):

1. Route target via `placer.place(...)`.
2. Validate resolved target category in transactional reader.
3. Allocate unique placeholder leaf name (`leaf_<6hex>` style).
4. Create `NodeType.LEAF` with `NodeStage.PENDING`.
5. Register new node in UoW and commit.
6. Publish `Placed` after successful commit.

## 2. Hint Behavior

- `hint=None`: route recursively from `root`.
- `hint="root.work"`: route recursively within that subtree.

So hint is a routing start path, not a forced final destination.

## 3. Payload Enrichment

`Intake.write` augments payload with:

- `_ingested_at`: UTC ingestion timestamp
- `_placement`: source, target path, reasoning, and decision steps

This creates a built-in audit trail for placement decisions.

## 4. Python Example

```python
leaf_id = await fs.write(
    content="User preference: prefers structured output",
    hint="root.preferences",
    payload={"source": "chat_session", "session_id": "s_001"},
)
```

## 5. CLI Example

```bash
semafs write "User preference: prefers structured output" \
  --hint root.preferences \
  --payload '{"source":"chat_session","session_id":"s_001"}' \
  --provider openai \
  --db data/demo.db
```

## 6. Typical Failures

- `Target category not found`: invalid hint or route target
- path format errors from `NodePath` validation
- provider-level API failures in adapter calls

Debug sequence:

1. Verify category paths via `semafs tree root ...`.
2. Retry with `--hint root` for baseline routing.
3. Inspect stored payload for `_placement` trail.
