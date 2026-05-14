export type KnownIntegration = {
  id: string;
  name: string;
  description: string;
  authType: "webhook" | "oauth" | "smtp";
  credentialFields: {
    key: string;
    label: string;
    placeholder: string;
    type?: "text" | "password";
    required?: boolean;
    hint?: string;
  }[];
};

export const KNOWN_INTEGRATIONS: KnownIntegration[] = [
  {
    id: "slack",
    name: "Slack",
    description: "Send messages to Slack channels via webhook",
    authType: "webhook",
    credentialFields: [
      {
        key: "webhook_url",
        label: "Webhook URL",
        placeholder: "https://hooks.slack.com/services/...",
      },
    ],
  },
  {
    id: "discord",
    name: "Discord",
    description: "Send messages to Discord channels via webhook",
    authType: "webhook",
    credentialFields: [
      {
        key: "webhook_url",
        label: "Webhook URL",
        placeholder: "https://discord.com/api/webhooks/...",
      },
    ],
  },
  {
    id: "smtp",
    name: "Email (SMTP)",
    description: "Send emails via any SMTP server. Works with Gmail, Outlook, or custom mail servers.",
    authType: "smtp",
    credentialFields: [
      {
        key: "host",
        label: "SMTP Host",
        type: "text",
        placeholder: "smtp.gmail.com",
        required: true,
      },
      {
        key: "port",
        label: "Port",
        type: "text",
        placeholder: "587",
        required: true,
        hint: "Use 587 for STARTTLS (recommended) or 465 for SSL.",
      },
      {
        key: "username",
        label: "Username",
        type: "text",
        placeholder: "you@gmail.com",
        required: true,
      },
      {
        key: "password",
        label: "Password",
        type: "password",
        placeholder: "",
        required: true,
        hint: "Gmail users: use an App Password, not your Google account password. Generate one at myaccount.google.com/apppasswords",
      },
      {
        key: "from_name",
        label: "From Name",
        type: "text",
        placeholder: "Workflow Bot",
        required: false,
      },
      {
        key: "from_email",
        label: "From Email",
        type: "text",
        placeholder: "you@gmail.com",
        required: true,
      },
    ],
  },
];
