import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

type Workflow = {
  id: string;
  name: string;
  trigger_type: string;
  is_active: boolean;
  created_at: string;
  steps: Record<string, unknown>[];
};

export default function Workflows() {
  const { data, isLoading, refetch } = useQuery({
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
            {isLoading && (
              <tr>
                <td className="table-cell" colSpan={5}>Loading workflows...</td>
              </tr>
            )}
            {data?.map((workflow) => (
              <tr key={workflow.id}>
                <td className="table-cell font-medium">{workflow.name}</td>
                <td className="table-cell">{workflow.trigger_type}</td>
                <td className="table-cell">
                  <span className={workflow.is_active ? "badge-green" : "badge-gray"}>
                    {workflow.is_active ? "active" : "inactive"}
                  </span>
                </td>
                <td className="table-cell">{new Date(workflow.created_at).toLocaleString()}</td>
                <td className="table-cell">
                  <div className="flex gap-2">
                    <button className="btn-secondary" onClick={() => triggerRun(workflow.id)}>Trigger Run</button>
                    <button className="btn-secondary" onClick={() => toggle(workflow.id)}>Toggle</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
