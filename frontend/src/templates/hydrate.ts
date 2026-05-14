import type { WorkflowTemplate } from "./types";

export function hydrate(definition: object, values: Record<string, string>): object {
  let serialized = JSON.stringify(definition);
  for (const [key, value] of Object.entries(values)) {
    serialized = serialized.replaceAll(`{{${key}}}`, value);
  }
  return JSON.parse(serialized) as object;
}

export function getMissingPlaceholders(
  template: WorkflowTemplate,
  values: Record<string, string>,
): string[] {
  return template.placeholders
    .filter((placeholder) => placeholder.required && !values[placeholder.key]?.trim())
    .map((placeholder) => placeholder.key);
}
