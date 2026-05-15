export type StepSnippet = {
  id: string;
  label: string;
  value: Record<string, unknown>;
};

export const STEP_SNIPPETS: StepSnippet[] = [
  {
    id: "llm",
    label: "llm",
    value: {
      id: "summarize",
      type: "llm",
      provider: "gemini",
      model: "gemini-2.5-flash",
      prompt: "Summarize: {{ trigger_data.body.message }}",
      output_as: "summary_result",
    },
  },
  {
    id: "email",
    label: "tool email",
    value: {
      id: "send_email",
      type: "tool",
      tool: "email",
      action: "send_email",
      integration_id: "YOUR_INTEGRATION_ID",
      params: {
        to: "user@example.com",
        subject: "Workflow update",
        body: "{{ summary_result.response }}",
      },
    },
  },
  {
    id: "approval",
    label: "approval",
    value: {
      id: "approval",
      type: "approval",
      approver_email: "user@example.com",
      message: "Approve this workflow action?",
      timeout_seconds: 300,
      timeout_action: "reject",
    },
  },
  {
    id: "parallel",
    label: "parallel_group",
    value: {
      id: "notify_group",
      type: "parallel_group",
      fail_fast: false,
      steps: [
        {
          id: "send_slack",
          type: "tool",
          tool: "slack",
          action: "send_message",
          integration_id: "YOUR_INTEGRATION_ID",
          params: { text: "{{ summary_result.response }}" },
        },
      ],
    },
  },
  {
    id: "foreach",
    label: "foreach",
    value: {
      id: "process_each",
      type: "foreach",
      items: "{{ trigger_data.body.items }}",
      item_variable: "item",
      index_variable: "index",
      concurrency_limit: 2,
      fail_fast: false,
      step: {
        id: "process_item",
        type: "tool",
        tool: "slack",
        action: "send_message",
        integration_id: "YOUR_INTEGRATION_ID",
        params: { text: "Processing {{ foreach.item }}" },
      },
    },
  },
  {
    id: "switch",
    label: "switch",
    value: {
      id: "route_by_priority",
      type: "switch",
      on: "{{ triage_result.response }}",
      on_no_match: "skip",
      branches: {
        urgent: [
          {
            id: "send_alert",
            type: "tool",
            tool: "slack",
            action: "send_message",
            integration_id: "YOUR_INTEGRATION_ID",
            params: { text: "{{ triage_result.response }}" },
          },
        ],
      },
      default: [
        {
          id: "fallback_notify",
          type: "tool",
          tool: "slack",
          action: "send_message",
          integration_id: "YOUR_INTEGRATION_ID",
          params: { text: "No route matched." },
        },
      ],
    },
  },
];

type StepSnippetsProps = {
  onInsert: (snippet: StepSnippet) => void;
};

export default function StepSnippets({ onInsert }: StepSnippetsProps) {
  return (
    <div className="card flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium text-slate-700">Step snippets</span>
      {STEP_SNIPPETS.map((snippet) => (
        <button className="btn-secondary" key={snippet.id} onClick={() => onInsert(snippet)} type="button">
          {snippet.label}
        </button>
      ))}
    </div>
  );
}
