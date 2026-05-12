export type Workflow = {
  id: string;
  name: string;
  description?: string | null;
  steps: Record<string, unknown>[];
  trigger_type: "manual" | "cron" | "webhook" | string;
  trigger_config?: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
};

export type RunStatus = "pending" | "running" | "paused" | "completed" | "failed" | "cancelled";

export type StepResult = {
  id: string;
  step_id: string;
  step_type: string;
  status: string;
  input?: Record<string, unknown> | null;
  output?: unknown;
  error?: string | null;
  duration_ms?: number | null;
  created_at?: string;
};

export type Run = {
  id: string;
  workflow_id: string;
  status: RunStatus | string;
  trigger_data?: Record<string, unknown> | null;
  context?: Record<string, unknown> | null;
  current_step?: string | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
};

export type RunDetail = Run & {
  step_results: StepResult[];
};

export type Approval = {
  id: string;
  run_id: string;
  step_id: string;
  status: string;
  context?: Record<string, unknown> | null;
  approver_email: string;
  expires_at: string;
  responded_at?: string | null;
  created_at?: string;
  token?: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
};

export type LlmProvider = {
  id: string;
  name: string;
};

export type LlmProviderModels = {
  provider: string;
  models: string[];
};
