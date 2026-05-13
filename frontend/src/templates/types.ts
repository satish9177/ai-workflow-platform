export interface Placeholder {
  key: string;
  label: string;
  type: "text" | "email" | "textarea";
  required: boolean;
  hint?: string;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  required_integrations: string[];
  placeholders: Placeholder[];
  workflow_definition: object;
}
