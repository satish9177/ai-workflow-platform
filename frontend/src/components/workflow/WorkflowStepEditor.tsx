import { FormEvent, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, getErrorMessage } from "../../api/client";
import { fetchIntegrations } from "../../api/integrations";
import type { Workflow } from "../../types/api";

type EditableStep = Record<string, unknown>;

type WorkflowStepEditorProps = {
  workflow: Workflow;
  onSaved: () => Promise<unknown>;
};

function stringifyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseJson(value: string, label: string) {
  try {
    const parsed = JSON.parse(value || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: `${label} must be a JSON object.` };
    }
    return { value: parsed as Record<string, unknown> };
  } catch {
    return { error: `${label} contains invalid JSON.` };
  }
}

function stepTitle(step: EditableStep, index: number) {
  const id = typeof step.id === "string" ? step.id : `Step ${index + 1}`;
  const type = typeof step.type === "string" ? step.type : "unknown";
  return `${index + 1}. ${id} (${type})`;
}

export default function WorkflowStepEditor({ workflow, onSaved }: WorkflowStepEditorProps) {
  const [steps, setSteps] = useState<EditableStep[]>([]);
  const [triggerType, setTriggerType] = useState(workflow.trigger_type);
  const [triggerConfigJson, setTriggerConfigJson] = useState("{}");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [expandedStep, setExpandedStep] = useState<string | null>(null);
  const [toolParamErrors, setToolParamErrors] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    setSteps(workflow.steps.map((step) => ({ ...step })));
    setTriggerType(workflow.trigger_type);
    setTriggerConfigJson(stringifyJson(workflow.trigger_config || {}));
    setWebhookSecret(String(workflow.trigger_config?.secret || ""));
    setExpandedStep(workflow.steps[0]?.id ? String(workflow.steps[0].id) : null);
    setToolParamErrors({});
    setMessage("");
    setErrorMessage("");
  }, [workflow]);

  function updateStep(index: number, updates: Record<string, unknown>) {
    setSteps((current) =>
      current.map((step, stepIndex) => (stepIndex === index ? { ...step, ...updates } : step)),
    );
  }

  function validate(nextTriggerConfig: Record<string, unknown>) {
    for (const [index, step] of steps.entries()) {
      const type = step.type;
      const label = stepTitle(step, index);

      if (type === "llm" && !String(step.prompt || "").trim()) {
        return `${label}: prompt is required.`;
      }
      if (type === "approval" && !String(step.approver_email || "").trim()) {
        return `${label}: approver_email is required.`;
      }
      if (type === "tool") {
        if (!String(step.tool || "").trim()) {
          return `${label}: tool is required.`;
        }
        if (!String(step.action || "").trim()) {
          return `${label}: action is required.`;
        }
        if (toolParamErrors[index]) {
          return `${label}: ${toolParamErrors[index]}`;
        }
      }
    }

    if (triggerType === "webhook" && webhookSecret.trim()) {
      nextTriggerConfig.secret = webhookSecret.trim();
    }
    if (triggerType === "webhook" && !webhookSecret.trim()) {
      delete nextTriggerConfig.secret;
    }

    return "";
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setErrorMessage("");

    const parsedTriggerConfig = parseJson(triggerConfigJson, "Trigger config");
    if (parsedTriggerConfig.error) {
      setErrorMessage(parsedTriggerConfig.error);
      return;
    }
    const triggerConfig = { ...(parsedTriggerConfig.value || {}) };
    const validationError = validate(triggerConfig);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    try {
      setSaving(true);
      await api.put(`/api/v1/workflows/${workflow.id}`, {
        name: workflow.name,
        description: workflow.description,
        steps,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
      });
      await onSaved();
      setMessage("Workflow saved.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card space-y-5" onSubmit={save}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Edit Workflow</h3>
          <p className="text-sm text-slate-500">Update prompts, step settings, and trigger configuration.</p>
        </div>
        <button className="btn-primary" disabled={saving} type="submit">
          {saving ? "Saving..." : "Save workflow"}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700" htmlFor="editor-trigger-type">
            Trigger type
          </label>
          <select
            className="input"
            id="editor-trigger-type"
            onChange={(event) => setTriggerType(event.target.value)}
            value={triggerType}
          >
            <option value="manual">manual</option>
            <option value="cron">cron</option>
            <option value="webhook">webhook</option>
          </select>
        </div>
        {triggerType === "webhook" && (
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700" htmlFor="editor-webhook-secret">
              Webhook secret
            </label>
            <input
              className="input"
              id="editor-webhook-secret"
              onChange={(event) => setWebhookSecret(event.target.value)}
              placeholder="Optional shared secret"
              type="password"
              value={webhookSecret}
            />
          </div>
        )}
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700" htmlFor="editor-trigger-config">
          Trigger config JSON
        </label>
        <textarea
          className="input min-h-28 font-mono"
          id="editor-trigger-config"
          onChange={(event) => setTriggerConfigJson(event.target.value)}
          value={triggerConfigJson}
        />
      </div>

      <div className="space-y-3">
        <h4 className="font-semibold">Steps</h4>
        {steps.map((step, index) => {
          const key = typeof step.id === "string" ? step.id : String(index);
          const isExpanded = expandedStep === key;
          return (
            <section className="rounded-md border border-slate-200" key={key}>
              <button
                className="flex w-full items-center justify-between px-4 py-3 text-left"
                onClick={() => setExpandedStep(isExpanded ? null : key)}
                type="button"
              >
                <span className="font-medium">{stepTitle(step, index)}</span>
                <span className="text-sm text-blue-700">{isExpanded ? "Collapse" : "Edit"}</span>
              </button>
              {isExpanded && (
                <StepFields
                  index={index}
                  onChange={updateStep}
                  onToolParamsError={(stepIndex, error) =>
                    setToolParamErrors((current) => ({ ...current, [stepIndex]: error }))
                  }
                  step={step}
                />
              )}
            </section>
          );
        })}
      </div>

      {errorMessage && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{errorMessage}</p>}
      {message && <p className="rounded-md bg-green-50 p-3 text-sm text-green-700">{message}</p>}
    </form>
  );
}

function StepFields({
  step,
  index,
  onChange,
  onToolParamsError,
}: {
  step: EditableStep;
  index: number;
  onChange: (index: number, updates: Record<string, unknown>) => void;
  onToolParamsError: (index: number, error: string) => void;
}) {
  const type = String(step.type || "");

  if (type === "llm") {
    return (
      <div className="space-y-4 border-t border-slate-200 p-4">
        <TextAreaField label="Prompt" value={String(step.prompt || "")} onChange={(value) => onChange(index, { prompt: value })} />
        <TextAreaField label="System" value={String(step.system || "")} onChange={(value) => onChange(index, { system: value })} />
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Provider" value={String(step.provider || "")} onChange={(value) => onChange(index, { provider: value })} />
          <TextField label="Model" value={String(step.model || "")} onChange={(value) => onChange(index, { model: value })} />
          <TextField label="Output as" value={String(step.output_as || "")} onChange={(value) => onChange(index, { output_as: value })} />
        </div>
        {!String(step.prompt || "").trim() && <p className="text-sm text-amber-700">Prompt is empty.</p>}
      </div>
    );
  }

  if (type === "approval") {
    return (
      <div className="space-y-4 border-t border-slate-200 p-4">
        <TextAreaField label="Message" value={String(step.message || "")} onChange={(value) => onChange(index, { message: value })} />
        <TextField label="Subject" value={String(step.subject || "")} onChange={(value) => onChange(index, { subject: value })} />
        <TextField label="Approver email" value={String(step.approver_email || "")} onChange={(value) => onChange(index, { approver_email: value })} />
      </div>
    );
  }

  if (type === "tool") {
    return <ToolFields index={index} onChange={onChange} onParamsError={onToolParamsError} step={step} />;
  }

  return (
    <div className="border-t border-slate-200 p-4 text-sm text-slate-500">
      This step type is preserved but not editable in the lightweight editor yet.
    </div>
  );
}

function ToolFields({
  step,
  index,
  onChange,
  onParamsError,
}: {
  step: EditableStep;
  index: number;
  onChange: (index: number, updates: Record<string, unknown>) => void;
  onParamsError: (index: number, error: string) => void;
}) {
  const [paramsText, setParamsText] = useState(stringifyJson(step.params || {}));
  const [jsonError, setJsonError] = useState("");
  const toolName = String(step.tool || "");
  const action = String(step.action || "");
  const integrationFilterType = toolName === "email" ? "smtp" : toolName;
  const { data: integrations = [], isLoading: integrationsLoading } = useQuery({
    queryKey: ["integrations", integrationFilterType],
    queryFn: () => fetchIntegrations(integrationFilterType),
    enabled: Boolean(integrationFilterType),
  });

  useEffect(() => {
    setParamsText(stringifyJson(step.params || {}));
    setJsonError("");
  }, [step.params]);

  function updateParams(value: string) {
    setParamsText(value);
    const parsed = parseJson(value, "Tool params");
    if (parsed.error) {
      setJsonError(parsed.error);
      onParamsError(index, parsed.error);
      return;
    }
    setJsonError("");
    onParamsError(index, "");
    onChange(index, { params: parsed.value });
  }

  function updateParamField(key: string, value: string) {
    const parsed = parseJson(paramsText, "Tool params");
    const currentParams = parsed.value || {};
    const nextParams = { ...currentParams, [key]: value };
    setParamsText(stringifyJson(nextParams));
    setJsonError("");
    onParamsError(index, "");
    onChange(index, { params: nextParams });
  }

  return (
    <div className="space-y-4 border-t border-slate-200 p-4">
      <div className="grid gap-4 md:grid-cols-3">
        <TextField label="Tool" value={String(step.tool || "")} onChange={(value) => onChange(index, { tool: value })} />
        <TextField label="Action" value={String(step.action || "")} onChange={(value) => onChange(index, { action: value })} />
        <TextField label="Output as" value={String(step.output_as || "")} onChange={(value) => onChange(index, { output_as: value })} />
      </div>
      {toolName !== "http_request" && (
        <div className="space-y-1">
          <label className="text-sm font-medium text-slate-700" htmlFor={`step-${index}-integration`}>
            Integration
          </label>
          <select
            className="input"
            id={`step-${index}-integration`}
            onChange={(event) => onChange(index, { integration_id: event.target.value || undefined })}
            value={String(step.integration_id || "")}
          >
            <option value="">Use first configured {integrationFilterType || "tool"} integration</option>
            {integrations.map((integration) => (
              <option key={integration.id || integration.name} value={integration.id || ""}>
                {integration.display_name}
              </option>
            ))}
          </select>
          {integrationsLoading && <p className="text-sm text-slate-500">Loading integrations...</p>}
          {!integrationsLoading && integrations.length === 0 && (
            <p className="text-sm text-amber-700">
              No {integrationFilterType} integrations configured.{" "}
              <Link className="font-medium underline" to="/integrations">
                Configure one
              </Link>
              .
            </p>
          )}
        </div>
      )}
      {toolName === "email" && (action === "send_email" || !action) && (
        <EmailParamsFields
          params={(step.params as Record<string, unknown>) || {}}
          onChange={updateParamField}
        />
      )}
      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Params JSON</label>
        <textarea className="input min-h-40 font-mono" onChange={(event) => updateParams(event.target.value)} value={paramsText} />
        {jsonError && <p className="text-sm text-red-700">{jsonError}</p>}
      </div>
    </div>
  );
}

function EmailParamsFields({
  params,
  onChange,
}: {
  params: Record<string, unknown>;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4">
      <TextField
        hint="Supports {{ variable }} template syntax."
        label="To"
        placeholder="recipient@example.com or {{ context.variable }}"
        value={String(params.to || "")}
        onChange={(value) => onChange("to", value)}
      />
      <TextField
        hint="Supports {{ variable }} template syntax."
        label="Subject"
        placeholder="Your workflow summary is ready"
        value={String(params.subject || "")}
        onChange={(value) => onChange("subject", value)}
      />
      <TextAreaField
        hint="Plain text. Supports {{ variable }} template syntax. HTML is not supported."
        label="Body"
        placeholder="{{ summary_result.response }}"
        value={String(params.body || "")}
        onChange={(value) => onChange("body", value)}
      />
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <input className="input" onChange={(event) => onChange(event.target.value)} placeholder={placeholder} value={value} />
      {hint && <p className="text-sm text-slate-500">{hint}</p>}
    </div>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <textarea className="input min-h-28" onChange={(event) => onChange(event.target.value)} placeholder={placeholder} value={value} />
      {hint && <p className="text-sm text-slate-500">{hint}</p>}
    </div>
  );
}
