import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import WorkflowStepEditor from "../components/workflow/WorkflowStepEditor";
import type { Workflow } from "../types/api";
import { buildTriggerPayload, cronToLabel, SCHEDULE_PRESETS } from "../utils/schedule";

export default function WorkflowDetailPage() {
  const { id } = useParams();
  const [showForm, setShowForm] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState(SCHEDULE_PRESETS[0].cron);
  const [customCron, setCustomCron] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [webhookError, setWebhookError] = useState("");
  const [webhookCopied, setWebhookCopied] = useState(false);
  const { data: workflow, error, isLoading, refetch } = useQuery({
    queryKey: ["workflow", id],
    queryFn: async () => (await api.get<Workflow>(`/api/v1/workflows/${id}`)).data,
    enabled: Boolean(id),
  });

  function resetForm() {
    setShowForm(false);
    setSelectedPreset(SCHEDULE_PRESETS[0].cron);
    setCustomCron("");
    setErrorMessage("");
  }

  function startEditing() {
    const currentCron = String(workflow?.trigger_config?.cron_expression || workflow?.trigger_config?.cron || "");
    const preset = SCHEDULE_PRESETS.find((option) => option.cron === currentCron);
    setSelectedPreset(preset?.cron || "custom");
    setCustomCron(preset ? "" : currentCron);
    setErrorMessage("");
    setShowForm(true);
  }

  async function updateSchedule(mode: "manual" | "cron", cronExpression: string) {
    if (!workflow) {
      return;
    }

    const payload = {
      name: workflow.name,
      description: workflow.description,
      steps: workflow.steps,
      ...buildTriggerPayload(mode, cronExpression),
    };

    await api.put(`/api/v1/workflows/${workflow.id}`, payload);
    await refetch();
  }

  async function saveWebhookSecret(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workflow) {
      return;
    }

    const secret = webhookSecret.trim();
    const triggerConfig = { ...(workflow.trigger_config || {}) };
    if (secret) {
      triggerConfig.secret = secret;
    } else {
      delete triggerConfig.secret;
    }

    try {
      setWebhookError("");
      await api.put(`/api/v1/workflows/${workflow.id}`, {
        name: workflow.name,
        description: workflow.description,
        steps: workflow.steps,
        trigger_type: "webhook",
        trigger_config: triggerConfig,
      });
      setWebhookSecret("");
      await refetch();
    } catch (error) {
      setWebhookError(getErrorMessage(error));
    }
  }

  async function copyWebhookUrl(webhookUrl: string) {
    if (!navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(webhookUrl);
    setWebhookCopied(true);
    window.setTimeout(() => setWebhookCopied(false), 1200);
  }

  async function removeSchedule() {
    try {
      setErrorMessage("");
      await updateSchedule("manual", "");
      resetForm();
    } catch {
      setErrorMessage("Failed to remove schedule. Try again.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cronExpression = selectedPreset === "custom" ? customCron.trim() : selectedPreset;
    if (!cronExpression) {
      setErrorMessage("Cron expression is required");
      return;
    }

    try {
      setErrorMessage("");
      await updateSchedule("cron", cronExpression);
      resetForm();
    } catch (error) {
      setErrorMessage(getErrorMessage(error) || "Failed to save schedule. Try again.");
    }
  }

  if (isLoading) {
    return <div className="card">Loading...</div>;
  }

  if (error || !workflow) {
    return <div className="card text-sm text-red-700">{error ? getErrorMessage(error) : "Workflow not found"}</div>;
  }

  const currentCron = String(workflow.trigger_config?.cron_expression || workflow.trigger_config?.cron || "");
  const webhookUrl = `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/api/v1/webhooks/${workflow.webhook_id}`;
  const webhookSecretConfigured = Boolean(workflow.trigger_config?.secret);

  return (
    <section className="space-y-4">
      <Link className="text-sm font-medium text-blue-700 hover:underline" to="/workflows">
        Back to workflows
      </Link>

      <div className="card space-y-2">
        <h2 className="text-2xl font-semibold">{workflow.name}</h2>
        {workflow.description && <p className="text-sm text-slate-500">{workflow.description}</p>}
        <p className="text-sm text-slate-600">Trigger: {workflow.trigger_type}</p>
      </div>

      <WorkflowStepEditor workflow={workflow} onSaved={refetch} />

      <div className="card space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Schedule</h3>
          {workflow.trigger_type === "cron" ? (
            <p className="text-sm text-slate-600">{cronToLabel(currentCron)}</p>
          ) : (
            <p className="text-sm text-slate-600">No schedule configured.</p>
          )}
        </div>

        {!showForm && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" onClick={startEditing} type="button">
              {workflow.trigger_type === "cron" ? "Edit schedule" : "Add schedule"}
            </button>
            {workflow.trigger_type === "cron" && (
              <button className="btn-secondary" onClick={removeSchedule} type="button">
                Remove schedule
              </button>
            )}
          </div>
        )}

        {showForm && (
          <form className="space-y-4" onSubmit={submit}>
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700" htmlFor="repeat">
                Repeat
              </label>
              <select
                className="input"
                id="repeat"
                onChange={(event) => setSelectedPreset(event.target.value)}
                value={selectedPreset}
              >
                {SCHEDULE_PRESETS.map((preset) => (
                  <option key={preset.label} value={preset.cron}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </div>

            {selectedPreset === "custom" && (
              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-700" htmlFor="cron-expression">
                  Cron expression
                </label>
                <input
                  className="input"
                  id="cron-expression"
                  onChange={(event) => setCustomCron(event.target.value)}
                  type="text"
                  value={customCron}
                />
                <p className="text-sm text-slate-500">
                  Example: 0 9 * * 1-5 (weekdays at 9am). Schedules run in server time (UTC).
                </p>
              </div>
            )}

            <p className="text-sm text-slate-500">Schedules run in server time (UTC).</p>
            {errorMessage && <p className="text-sm text-red-700">{errorMessage}</p>}

            <div className="flex gap-2">
              <button className="btn-primary" type="submit">
                Save schedule
              </button>
              <button className="btn-secondary" onClick={resetForm} type="button">
                Cancel
              </button>
            </div>
          </form>
        )}

        {!showForm && errorMessage && <p className="text-sm text-red-700">{errorMessage}</p>}
      </div>

      <div className="card space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Webhook Trigger</h3>
          <p className="text-sm text-slate-600">External systems can POST JSON to this endpoint to trigger the workflow.</p>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-700">Webhook URL</p>
          <div className="flex flex-wrap gap-2">
            <code className="rounded bg-slate-100 px-3 py-2 text-xs text-slate-700">{webhookUrl}</code>
            <button className="btn-secondary" onClick={() => copyWebhookUrl(webhookUrl)} type="button">
              {webhookCopied ? "Copied" : "Copy"}
            </button>
          </div>
          {workflow.trigger_type !== "webhook" && (
            <p className="text-sm text-amber-700">Save a webhook secret below to switch this workflow to webhook trigger mode.</p>
          )}
        </div>

        <form className="space-y-3" onSubmit={saveWebhookSecret}>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700" htmlFor="webhook-secret">
              Optional webhook secret
            </label>
            <input
              className="input"
              id="webhook-secret"
              onChange={(event) => setWebhookSecret(event.target.value)}
              placeholder={webhookSecretConfigured ? "Enter a new secret to replace or leave blank to remove" : "abc123"}
              type="password"
              value={webhookSecret}
            />
            <p className="text-sm text-slate-500">
              When configured, callers must send X-Webhook-Secret with the same value.
            </p>
          </div>
          {webhookError && <p className="text-sm text-red-700">{webhookError}</p>}
          <button className="btn-primary" type="submit">
            {webhookSecretConfigured ? "Update webhook settings" : "Enable webhook trigger"}
          </button>
        </form>

        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-700">Example request</p>
          <pre className="overflow-auto rounded-md bg-slate-100 p-3 text-xs text-slate-700">
{`curl -X POST "${webhookUrl}" \\
  -H "Content-Type: application/json" \\
  -H "X-Webhook-Secret: ${webhookSecretConfigured ? "<your-secret>" : "optional"}" \\
  -d '{"event":"created","source":"custom-app"}'`}
          </pre>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-700">Use webhook data in workflow templates</p>
          <p className="text-sm text-slate-500">
            Webhook payloads are available as trigger_data in LLM prompts, tool params, and approval messages.
          </p>
          <pre className="overflow-auto rounded-md bg-slate-100 p-3 text-xs text-slate-700">
{`{{ trigger_data.body.message }}
{{ trigger_data.headers.x_github_event }}
{{ trigger_data.query_params.customer_id }}`}
          </pre>
        </div>
      </div>
    </section>
  );
}
