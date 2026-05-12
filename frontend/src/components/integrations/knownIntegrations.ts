export type KnownIntegration = {
  id: string;
  name: string;
  description: string;
  authType: "webhook" | "oauth";
  credentialFields: {
    key: string;
    label: string;
    placeholder: string;
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
];
