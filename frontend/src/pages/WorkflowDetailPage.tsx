import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import type { Workflow } from "../types/api";
import { buildTriggerPayload, cronToLabel, SCHEDULE_PRESETS } from "../utils/schedule";

export default function WorkflowDetailPage() {
  const { id } = useParams();
  const [showForm, setShowForm] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState(SCHEDULE_PRESETS[0].cron);
  const [customCron, setCustomCron] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
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
    </section>
  );
}
