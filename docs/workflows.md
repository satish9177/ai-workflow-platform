# Workflows

Workflows are JSON documents stored in PostgreSQL. The backend validates step shape with Pydantic before saving. Runtime execution is handled by the orchestration engine documented in [orchestration.md](orchestration.md).

## Common Step Fields

Every step requires:

- `id`: non-empty string unique within its immediate scope.
- `type`: one of `llm`, `tool`, `approval`, `condition`, `parallel_group`, `foreach`, `switch`.

Step IDs become part of persisted execution identity. For nested containers, the executor creates dotted keys from parent and child IDs.

## Template Rendering

Workflow fields that accept user data use recursive Jinja-style rendering:

```json
{
  "text": "{{ trigger_data.body.message }}"
}
```

Supported context includes:

- `trigger_data.body`
- `trigger_data.headers`
- `trigger_data.query_params`
- prior step outputs
- `output_as` aliases
- `foreach.item`
- `foreach.index`
- switch metadata such as `route.__branch__`

Missing variables render as empty strings.

## LLM Step

Runs a prompt through the configured LLM provider abstraction.

```json
{
  "id": "summarize",
  "type": "llm",
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "prompt": "Summarize: {{ trigger_data.body.message }}",
  "output_as": "summary_result"
}
```

LLM output is stored under the step ID and `output_as` alias when provided.

## Tool Step

Runs a registered tool through `ToolRegistry`.

```json
{
  "id": "send_slack",
  "type": "tool",
  "tool": "slack",
  "action": "send_message",
  "integration_id": "integration-uuid",
  "params": {
    "text": "{{ summary_result.response }}"
  }
}
```

Integration credentials are resolved from the integrations table. Tool abstractions and provider implementations are intentionally separate. For example, `tool="email"` can use an integration with `integration_type="smtp"`.

## Approval Step

Pauses execution until a human approves or rejects.

```json
{
  "id": "manager_approval",
  "type": "approval",
  "approver_email": "manager@example.com",
  "message": "Approve this message?",
  "timeout_seconds": 300,
  "timeout_action": "reject"
}
```

`timeout_action` may be `approve` or `reject`. Timeout handling only applies while the approval is still pending.

## Condition Step

Evaluates a safe expression and returns branch metadata. This is not a graph edge system.

```json
{
  "id": "has_items",
  "type": "condition",
  "condition": "items|length > 0",
  "if_true": "continue",
  "if_false": null
}
```

For real inline branching, use `switch`.

## Switch Step

`switch` is a scoped inline container. It renders `on`, selects exactly one branch, executes that branch sequentially, then returns to the parent workflow.

```json
{
  "id": "route_by_priority",
  "type": "switch",
  "on": "{{ triage_result.response }}",
  "on_no_match": "skip",
  "branches": {
    "urgent": [
      {
        "id": "send_alert",
        "type": "tool",
        "tool": "slack",
        "action": "send_message",
        "params": {
          "text": "{{ triage_result.response }}"
        }
      }
    ],
    "normal": [
      {
        "id": "send_email",
        "type": "tool",
        "tool": "email",
        "action": "send_email",
        "params": {
          "to": "ops@example.com",
          "subject": "Workflow update",
          "body": "{{ triage_result.response }}"
        }
      }
    ]
  },
  "default": [
    {
      "id": "fallback_notify",
      "type": "tool",
      "tool": "slack",
      "action": "send_message",
      "params": {
        "text": "No route matched."
      }
    }
  ]
}
```

Skipped branches create branch container timeline rows, but skipped child steps are not created.

## Parallel Group

Executes child branches concurrently via ARQ jobs and merges after all branches are terminal.

```json
{
  "id": "notify_group",
  "type": "parallel_group",
  "fail_fast": false,
  "steps": [
    {
      "id": "slack",
      "type": "tool",
      "tool": "slack",
      "action": "send_message",
      "params": {
        "text": "{{ summary_result.response }}"
      }
    },
    {
      "id": "email",
      "type": "tool",
      "tool": "email",
      "action": "send_email",
      "params": {
        "to": "ops@example.com",
        "subject": "Summary",
        "body": "{{ summary_result.response }}"
      }
    }
  ]
}
```

Branch outputs merge under deterministic branch keys.

## Foreach

Resolves items once, persists them, then runs one child step per item with bounded concurrency.

```json
{
  "id": "approve_each",
  "type": "foreach",
  "items": "{{ trigger_data.body.items }}",
  "item_variable": "item",
  "index_variable": "index",
  "concurrency_limit": 2,
  "fail_fast": false,
  "step": {
    "id": "approve",
    "type": "approval",
    "approver_email": "manager@example.com",
    "message": "Approve {{ foreach.item.name }}?"
  }
}
```

V2 supports foreach depth 1 only.

## Retry Configuration

Tool and LLM steps can use step-level retry/backoff:

```json
{
  "id": "notify",
  "type": "tool",
  "tool": "slack",
  "action": "send_message",
  "params": {
    "text": "Hello"
  },
  "retry": {
    "max_attempts": 3,
    "backoff_seconds": 2
  }
}
```

Provider errors from LLM calls are classified as retryable or non-retryable. Non-retryable provider errors fail immediately.

## Trigger Examples

Manual:

```json
{
  "name": "Manual workflow",
  "trigger_type": "manual",
  "trigger_config": {},
  "steps": []
}
```

Cron:

```json
{
  "name": "Hourly workflow",
  "trigger_type": "cron",
  "trigger_config": {
    "cron_expression": "0 * * * *",
    "cron": "0 * * * *"
  },
  "steps": []
}
```

Webhook:

```json
{
  "name": "Webhook intake",
  "trigger_type": "webhook",
  "trigger_config": {
    "secret": "shared-secret"
  },
  "steps": [
    {
      "id": "summarize",
      "type": "llm",
      "prompt": "Summarize {{ trigger_data.body.message }}"
    }
  ]
}
```
