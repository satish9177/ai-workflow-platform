# Workflows

Workflows are stored as JSON step lists in PostgreSQL. API validation keeps the step format lightweight and predictable.

Every step requires:

- `id`: non-empty string
- `type`: one of `llm`, `tool`, `approval`, `condition`

## Step Types

### LLM

Runs a prompt through OpenAI and stores conversation turns.

```json
{
  "id": "summarize",
  "type": "llm",
  "prompt": "Summarize this payload: {{ trigger_data }}",
  "model": "gpt-4o-mini"
}
```

### Tool

Runs a registered tool. Requires `tool` and `action`.

```json
{
  "id": "fetch",
  "type": "tool",
  "tool": "http_request",
  "action": "execute",
  "params": {
    "method": "GET",
    "url": "https://example.com"
  }
}
```

### Approval

Pauses execution until a human approves or rejects.

```json
{
  "id": "manager_approval",
  "type": "approval",
  "approver_email": "manager@example.com"
}
```

### Condition

Evaluates a safe expression against run context.

```json
{
  "id": "has_results",
  "type": "condition",
  "condition": "fetch.data|length > 0",
  "if_true": "manager_approval",
  "if_false": null
}
```

## Manual Workflow Example

```json
{
  "name": "Manual HTTP Review",
  "description": "Fetch data and ask for approval.",
  "trigger_type": "manual",
  "trigger_config": {},
  "steps": [
    {
      "id": "fetch",
      "type": "tool",
      "tool": "http_request",
      "action": "execute",
      "params": {
        "method": "GET",
        "url": "https://example.com"
      }
    },
    {
      "id": "review",
      "type": "approval",
      "approver_email": "developer@example.com"
    }
  ]
}
```

## Cron Workflow Example

```json
{
  "name": "Every Minute Check",
  "trigger_type": "cron",
  "trigger_config": {
    "cron": "* * * * *"
  },
  "steps": [
    {
      "id": "fetch",
      "type": "tool",
      "tool": "http_request",
      "action": "execute",
      "params": {
        "url": "https://example.com"
      }
    }
  ]
}
```

## Webhook Workflow Example

```json
{
  "name": "Webhook Intake",
  "trigger_type": "webhook",
  "trigger_config": {
    "webhook_token": "replace-with-random-token"
  },
  "steps": [
    {
      "id": "summarize",
      "type": "llm",
      "prompt": "Summarize webhook payload: {{ trigger_data }}"
    }
  ]
}
```
