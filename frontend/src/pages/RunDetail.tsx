import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../api/client";

type StepResult = {
  id: string;
  step_id: string;
  step_type: string;
  status: string;
  output?: unknown;
  duration_ms?: number | null;
};

type RunDetailResponse = {
  id: string;
  workflow_id: string;
  status: string;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  step_results: StepResult[];
};

const statusClass: Record<string, string> = {
  pending: "badge-gray",
  running: "badge-blue",
  paused: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function preview(output: unknown) {
  if (output == null) {
    return "";
  }
  return JSON.stringify(output).slice(0, 100);
}

export default function RunDetail() {
  const { id } = useParams();
  const { data, refetch } = useQuery({
    queryKey: ["run", id],
    queryFn: async () => (await api.get<RunDetailResponse>(`/api/v1/runs/${id}`)).data,
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "paused" ? 3000 : false;
    },
  });

  async function cancelRun() {
    await api.post(`/api/v1/runs/${id}/cancel`);
    await refetch();
  }

  async function retryRun() {
    await api.post(`/api/v1/runs/${id}/retry`);
    await refetch();
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Run Detail</h2>
        <p className="font-mono text-xs text-slate-500">{id}</p>
      </div>
      <div className="card space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Status</span>
          <span className={statusClass[data?.status || "pending"] || "badge-gray"}>{data?.status || "loading"}</span>
        </div>
        <p className="text-sm text-slate-600">Started: {formatDate(data?.started_at)}</p>
        <p className="text-sm text-slate-600">Completed: {formatDate(data?.completed_at)}</p>
        {data?.error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{data.error}</p>}
        <div className="flex gap-2">
          {data?.status === "running" && (
            <button className="btn-danger" onClick={cancelRun}>Cancel</button>
          )}
          {data?.status === "failed" && (
            <button className="btn-primary" onClick={retryRun}>Retry</button>
          )}
        </div>
      </div>
      <div className="card overflow-hidden p-0">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="table-header">Step ID</th>
              <th className="table-header">Type</th>
              <th className="table-header">Status</th>
              <th className="table-header">Duration</th>
              <th className="table-header">Output Preview</th>
            </tr>
          </thead>
          <tbody>
            {data?.step_results?.map((step) => (
              <tr key={step.id}>
                <td className="table-cell">{step.step_id}</td>
                <td className="table-cell">{step.step_type}</td>
                <td className="table-cell">{step.status}</td>
                <td className="table-cell">{step.duration_ms ?? "-"}</td>
                <td className="table-cell max-w-md font-mono text-xs">{preview(step.output)}</td>
              </tr>
            ))}
            {data?.step_results?.length === 0 && (
              <tr>
                <td className="table-cell" colSpan={5}>No step results yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
