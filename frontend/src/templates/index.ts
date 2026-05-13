import type { WorkflowTemplate } from "./types";

export const TEMPLATES: WorkflowTemplate[] = [
  {
    id: "slack-notification",
    name: "Slack Notification",
    description: "Send a Slack message from a manual workflow.",
    required_integrations: ["slack"],
    placeholders: [
      {
        key: "message",
        label: "Message",
        type: "textarea",
        required: true,
      },
    ],
    workflow_definition: {
      name: "Slack Notification",
      trigger_type: "manual",
      steps: [
        {
          id: "send_slack",
          type: "tool",
          tool: "slack",
          action: "send_message",
          params: {
            text: "{{message}}",
            username: "Workflow Bot",
            icon_emoji: ":rocket:",
          },
        },
      ],
    },
  },
  {
    id: "discord-notification",
    name: "Discord Notification",
    description: "Send a Discord message from a manual workflow.",
    required_integrations: ["discord"],
    placeholders: [
      {
        key: "message",
        label: "Message",
        type: "textarea",
        required: true,
      },
    ],
    workflow_definition: {
      name: "Discord Notification",
      trigger_type: "manual",
      steps: [
        {
          id: "send_discord",
          type: "tool",
          tool: "discord",
          action: "send_message",
          params: {
            text: "{{message}}",
            username: "Workflow Bot",
          },
        },
      ],
    },
  },
  {
    id: "gemini-slack-summary",
    name: "Gemini → Slack Summary",
    description: "Ask Gemini to summarize a prompt and send the result to Slack.",
    required_integrations: ["slack"],
    placeholders: [
      {
        key: "prompt",
        label: "Prompt",
        type: "textarea",
        required: true,
        hint: "Example: Summarize the customer issue professionally.",
      },
    ],
    workflow_definition: {
      name: "Gemini → Slack Summary",
      trigger_type: "manual",
      steps: [
        {
          id: "summary",
          type: "llm",
          provider: "gemini",
          model: "gemini-2.5-flash",
          prompt: "{{prompt}}",
          output_as: "summary_result",
        },
        {
          id: "send_slack",
          type: "tool",
          tool: "slack",
          action: "send_message",
          params: {
            text: "{{ summary_result.response }}",
            username: "Workflow Bot",
            icon_emoji: ":memo:",
          },
        },
      ],
    },
  },
  {
    id: "gemini-approval-slack",
    name: "Gemini → Approval → Slack",
    description: "Gemini drafts a message, waits for approval, then sends it to Slack.",
    required_integrations: ["slack"],
    placeholders: [
      {
        key: "prompt",
        label: "Prompt",
        type: "textarea",
        required: true,
      },
      {
        key: "approver_email",
        label: "Approver Email",
        type: "email",
        required: true,
        hint: "This person approves before Slack message is sent.",
      },
    ],
    workflow_definition: {
      name: "Gemini → Approval → Slack",
      trigger_type: "manual",
      steps: [
        {
          id: "draft",
          type: "llm",
          provider: "gemini",
          model: "gemini-2.5-flash",
          prompt: "{{prompt}}",
          output_as: "draft_result",
        },
        {
          id: "approval_step",
          type: "approval",
          approver_email: "{{approver_email}}",
          message: "Approve this AI-generated Slack message?",
        },
        {
          id: "send_slack",
          type: "tool",
          tool: "slack",
          action: "send_message",
          params: {
            text: "{{ draft_result.response }}",
            username: "Workflow Bot",
            icon_emoji: ":white_check_mark:",
          },
        },
      ],
    },
  },
  {
    id: "gemini-approval-discord",
    name: "Gemini → Approval → Discord",
    description: "Gemini drafts a message, waits for approval, then sends it to Discord.",
    required_integrations: ["discord"],
    placeholders: [
      {
        key: "prompt",
        label: "Prompt",
        type: "textarea",
        required: true,
      },
      {
        key: "approver_email",
        label: "Approver Email",
        type: "email",
        required: true,
        hint: "This person approves before Discord message is sent.",
      },
    ],
    workflow_definition: {
      name: "Gemini → Approval → Discord",
      trigger_type: "manual",
      steps: [
        {
          id: "draft",
          type: "llm",
          provider: "gemini",
          model: "gemini-2.5-flash",
          prompt: "{{prompt}}",
          output_as: "draft_result",
        },
        {
          id: "approval_step",
          type: "approval",
          approver_email: "{{approver_email}}",
          message: "Approve this AI-generated Discord message?",
        },
        {
          id: "send_discord",
          type: "tool",
          tool: "discord",
          action: "send_message",
          params: {
            text: "{{ draft_result.response }}",
            username: "Workflow Bot",
          },
        },
      ],
    },
  },
];
