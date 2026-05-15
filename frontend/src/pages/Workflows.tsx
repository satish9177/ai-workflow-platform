import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import type { Workflow } from "../types/api";
import { formatDate } from "../utils/date";
import { cronToLabel } from "../utils/schedule";

export default function Workflows() {
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["workflows"],
    queryFn: async () => (await api.get<Workflow[]>("/api/v1/workflows")).data,
    refetchInterval: 10000,
  });

  async function triggerRun(id: string) {
    await api.post(`/api/v1/workflows/${id}/run`, { trigger_data: {} });
    alert("Run queued");
  }

  async function toggle(id: string) {
    await api.post(`/api/v1/workflows/${id}/toggle`);
    await refetch();
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Workflows</h2>
        <p className="text-sm text-slate-500">Create workflows through the API, then manage them here.</p>
      </div>
      <div>
        <Link className="btn-primary" to="/workflows/new/studio">New workflow in Studio</Link>
      </div>
      {isLoading && <div className="card">Loading...</div>}
      {error && <div className="card text-sm text-red-700">{getErrorMessage(error)}</div>}
      <div className="card overflow-hidden p-0">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="table-header">Name</th>
              <th className="table-header">Trigger</th>
              <th className="table-header">Active</th>
              <th className="table-header">Created</th>
              <th className="table-header">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((workflow) => (
              <tr key={workflow.id}>
                <td className="table-cell font-medium">
                  <div className="flex flex-wrap items-center gap-2">
                    <span>{workflow.name}</span>
                    {workflow.trigger_type === "cron" && (
                      <span className="badge-blue">
                        {cronToLabel(String(workflow.trigger_config?.cron_expression || workflow.trigger_config?.cron || ""))}
                      </span>
                    )}
                  </div>
                </td>
                <td className="table-cell">{workflow.trigger_type}</td>
                <td className="table-cell">
                  <span className={workflow.is_active ? "badge-green" : "badge-gray"}>
                    {workflow.is_active ? "active" : "inactive"}
                  </span>
                </td>
                <td className="table-cell">{formatDate(workflow.created_at)}</td>
                <td className="table-cell">
                  <div className="flex gap-2">
                    <Link className="btn-secondary" to={`/workflows/${workflow.id}`}>View details</Link>
                    <Link className="btn-secondary" to={`/workflows/${workflow.id}/studio`}>Open Studio</Link>
                    <button className="btn-secondary" onClick={() => triggerRun(workflow.id)}>Trigger Run</button>
                    <button className="btn-secondary" onClick={() => toggle(workflow.id)}>Toggle</button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && !error && data?.length === 0 && (
              <tr>
                <td className="table-cell" colSpan={5}>No workflows found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
