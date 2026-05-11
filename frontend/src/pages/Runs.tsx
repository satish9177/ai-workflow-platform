import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import type { Run } from "../types/api";
import { formatDate } from "../utils/date";

export default function Runs() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: async () => (await api.get<Run[]>("/api/v1/runs?limit=50")).data,
    refetchInterval: 5000,
  });

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Runs</h2>
        <p className="text-sm text-slate-500">Recent workflow execution history.</p>
      </div>
      {isLoading && <div className="card">Loading...</div>}
      {error && <div className="card text-sm text-red-700">{getErrorMessage(error)}</div>}
      <div className="card overflow-hidden p-0">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="table-header">Status</th>
              <th className="table-header">Workflow ID</th>
              <th className="table-header">Created</th>
              <th className="table-header">Detail</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((run) => (
              <tr key={run.id}>
                <td className="table-cell">
                  <StatusBadge status={run.status} />
                </td>
                <td className="table-cell font-mono text-xs">{run.workflow_id}</td>
                <td className="table-cell">{formatDate(run.created_at)}</td>
                <td className="table-cell">
                  <Link className="text-sm font-medium text-blue-700 hover:underline" to={`/runs/${run.id}`}>
                    View
                  </Link>
                </td>
              </tr>
            ))}
            {!isLoading && !error && data?.length === 0 && (
              <tr>
                <td className="table-cell" colSpan={4}>No runs found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
