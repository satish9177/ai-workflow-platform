import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";

type Run = {
  id: string;
  workflow_id: string;
  status: string;
  created_at: string;
};

const statusClass: Record<string, string> = {
  pending: "badge-gray",
  running: "badge-blue",
  paused: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

export default function Runs() {
  const { data, isLoading } = useQuery({
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
            {isLoading && (
              <tr>
                <td className="table-cell" colSpan={4}>Loading runs...</td>
              </tr>
            )}
            {data?.map((run) => (
              <tr key={run.id}>
                <td className="table-cell">
                  <span className={statusClass[run.status] || "badge-gray"}>{run.status}</span>
                </td>
                <td className="table-cell font-mono text-xs">{run.workflow_id}</td>
                <td className="table-cell">{new Date(run.created_at).toLocaleString()}</td>
                <td className="table-cell">
                  <Link className="text-sm font-medium text-blue-700 hover:underline" to={`/runs/${run.id}`}>
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
