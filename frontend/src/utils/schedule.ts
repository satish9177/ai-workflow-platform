interface PresetOption {
  label: string;
  cron: string;
}

export const SCHEDULE_PRESETS: PresetOption[] = [
  { label: "Every 15 minutes", cron: "*/15 * * * *" },
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Every day at midnight", cron: "0 0 * * *" },
  { label: "Every day at 9am", cron: "0 9 * * *" },
  { label: "Every Monday at 9am", cron: "0 9 * * 1" },
  { label: "Custom", cron: "custom" },
];

export function cronToLabel(cron_expression: string): string {
  const preset = SCHEDULE_PRESETS.find((option) => option.cron === cron_expression);
  return preset?.label || cron_expression;
}

export function buildTriggerPayload(
  mode: "manual" | "cron",
  cronExpression: string,
): { trigger_type: string; trigger_config: object } {
  if (mode === "manual") {
    return { trigger_type: "manual", trigger_config: {} };
  }

  return { trigger_type: "cron", trigger_config: { cron_expression: cronExpression } };
}
