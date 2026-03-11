# Writing Memories

Learn how to write knowledge fragments to SemaFS.

## Basic Write

```python
fragment_id = await semafs.write(
    path="root.work",
    content="Completed sprint planning meeting",
    payload={"source": "meeting", "date": "2024-03-15"}
)
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Target category path |
| `content` | `str` | Knowledge content |
| `payload` | `dict` | Optional metadata |

### Return Value

Returns the fragment ID (UUID string) for tracking.

## Path Resolution

When you write to a path, SemaFS finds the **deepest existing category**:

```python
# Existing structure:
# root/
# └── work/

await semafs.write("root.work.meetings.standup", "Daily standup notes")
# Result: Fragment created under "root.work" (deepest existing)
# Name: "_frag_abc123"
# Parent path: "root.work"
```

If the exact path exists and is a CATEGORY, the fragment is created there.

## Fragment Naming

Fragments are automatically named with a random suffix:

```python
# Fragment names follow pattern: _frag_{8_hex_chars}
"_frag_a1b2c3d4"
"_frag_e5f6g7h8"
```

During maintenance, fragments are renamed to meaningful names by the LLM.

## Metadata (Payload)

The `payload` parameter stores arbitrary JSON metadata:

```python
await semafs.write(
    path="root.work",
    content="API documentation updated",
    payload={
        "source": "commit",
        "author": "alice",
        "commit_sha": "abc123",
        "confidence": 0.95,
        "tags": ["documentation", "api"]
    }
)
```

Metadata is preserved through merge and move operations.

## Write and Maintain

For immediate organization, call `maintain()` after writing:

```python
# Write multiple fragments
await semafs.write("root.food", "Love dark roast coffee")
await semafs.write("root.food", "Ethiopian beans are best")
await semafs.write("root.food", "No sugar please")

# Organize immediately
await semafs.maintain()

# Fragments are now merged/grouped
```

## Batch Writing

For multiple writes, consider batching:

```python
import asyncio

fragments = [
    ("root.work", "Sprint planning done", {}),
    ("root.work", "API docs updated", {}),
    ("root.personal", "Buy coffee beans", {}),
]

# Write all fragments
ids = await asyncio.gather(*[
    semafs.write(path, content, payload)
    for path, content, payload in fragments
])

# Single maintenance pass
await semafs.maintain()
```

## Forcing LLM Analysis

To force LLM reorganization (even under threshold), use `_force_llm` in payload:

```python
await semafs.write(
    path="root.important",
    content="Critical insight that needs smart organization",
    payload={"_force_llm": True}
)

# maintain() will use LLM regardless of node count
await semafs.maintain()
```

## Transaction Safety

Each write is atomic:

```python
async with factory.begin() as uow:
    # All changes in this block are atomic
    semafs = SemaFS(factory, strategy)
    await semafs.write("root.work", "Note 1", {})
    await semafs.write("root.work", "Note 2", {})
    # Commits automatically on exit
```

If any write fails, all changes in the transaction roll back.

## Best Practices

### 1. Write to Appropriate Depth

```python
# Good: Write to existing category
await semafs.write("root.work", "Meeting notes")

# Better: Be specific if category exists
await semafs.write("root.work.meetings", "Standup notes")
```

### 2. Include Useful Metadata

```python
await semafs.write(
    path="root.research",
    content="Interesting paper on transformers",
    payload={
        "source": "arxiv",
        "url": "https://arxiv.org/...",
        "read_date": "2024-03-15"
    }
)
```

### 3. Batch Related Writes

```python
# Process all meeting notes together
for note in meeting_notes:
    await semafs.write("root.meetings", note)

# Single maintenance pass
await semafs.maintain()
```

### 4. Avoid Duplicate Content

The LLM will merge duplicates, but it's more efficient to dedupe before writing:

```python
# Check if similar content exists
existing = await semafs.view_tree("root.work", max_depth=1)
# ... dedupe logic ...
await semafs.write("root.work", new_content, {})
```

## Next Steps

- [Reading & Querying](./reading) - Retrieve your knowledge
- [Maintenance](./maintenance) - How organization works
- [Core Concepts](./concepts) - Understand the data model
