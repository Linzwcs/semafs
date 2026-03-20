# Agent Memory (MCP)

`semafs serve` exposes SemaFS as an MCP stdio service for agent memory workflows.

## 1. Start Server

```bash
semafs serve --provider openai --db data/agent_memory.db
```

## 2. Exposed MCP Tools

- `write(content, hint?, payload_json?, sweep?, sweep_limit?)`
- `read(path)`
- `list(path)`
- `tree(path="root", max_depth=3)`
- `stats()`
- `sweep(limit?)`

## 3. Recommended Agent Pattern

1. Write frequently with contextual payload.
2. Read/list/tree for retrieval and navigation.
3. Run periodic sweep for backlog maintenance.

## 4. Payload Convention (Suggested)

```json
{
  "source": "agent",
  "session_id": "sess_xxx",
  "trace_id": "trace_xxx",
  "topic": "preferences"
}
```

## 5. Operational Notes

- `serve` requires the DB file to already exist.
- keep DB lifecycle (rotation/backup) explicit in production.
- use `--base-url` when routing through OpenAI-compatible gateways.
