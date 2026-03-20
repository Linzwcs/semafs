# Writing Memories

Use the latest write API to append knowledge fragments.

## API

```python
leaf_id = await semafs.write(
    content="Completed sprint planning",
    hint="root.work",
    payload={"source": "meeting", "date": "2026-03-20"},
)
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `content` | `str` | Required fragment text |
| `hint` | `str \| None` | Preferred entry path (defaults to `root`) |
| `payload` | `dict \| None` | Optional metadata JSON |

### Return

- Returns leaf node id (`str`).

## How Placement Works

- `hint` is an entry path, not a guaranteed final leaf path.
- The configured `placer` decides target category.
- With `HintPlacer`, content stays at the hinted path.

## Metadata Guidelines

```python
await semafs.write(
    content="API docs updated",
    hint="root.engineering.docs",
    payload={
        "source": "git",
        "author": "alice",
        "tags": ["docs", "api"],
        "confidence": 0.93,
    },
)
```

Use payload for provenance and filtering context, not for large text blobs.

## Batch Writing Pattern

```python
for text in [
    "User prefers async status updates",
    "Meeting notes should be concise",
    "Focus hours: 9-11am",
]:
    await semafs.write(content=text, hint="root.work")

# Optional: sweep overloaded categories
await semafs.sweep(limit=20)
```

## Current vs Old API

Use this now:

- `write(content=..., hint=..., payload=...)`

Do not use old examples like:

- `write(path=..., content=...)`
- `maintain()`

## Next Steps

- [Reading & Querying](./reading) - Get structured context back
- [Maintenance](./maintenance) - Event-driven reconcile and `sweep(limit)`
- [Core Concepts](./concepts) - Node lifecycle and path rules
