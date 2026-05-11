import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

type Approval = {
  id: string;
  run_id: string;
  step_id: string;
  status: string;
  context?: Record<string, unknown> | null;
  approver_email: string;
  expires_at: string;
  token?: string;
};

function contextPreview(context?: Record<string, unknown> | null) {
  if (!context) {
    return "{}";
  }
  return JSON.stringify(context).slice(0, 160);
}

export default function Approvals() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["approvals"],
    queryFn: async () => (await api.get<Approval[]>("/api/v1/approvals/pending")).data,
    refetchInterval: 10000,
  });

  async function approve(token: string) {
    await api.post(`/api/v1/approvals/${token}/approve`);
    alert("Approval accepted");
    await refetch();
  }

  async function reject(token: string) {
    await api.post(`/api/v1/approvals/${token}/reject`);
    alert("Approval rejected");
    await refetch();
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Pending Approvals</h2>
        <p className="text-sm text-slate-500">Developer-only approval queue.</p>
      </div>
      {isLoading && <div className="card">Loading approvals...</div>}
      <div className="grid gap-4">
        {data?.map((approval) => (
          <article className="card space-y-3" key={approval.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm text-slate-500">Run ID</p>
                <p className="font-mono text-xs">{approval.run_id}</p>
              </div>
              <span className="badge-yellow">{approval.status}</span>
            </div>
            <p className="text-sm text-slate-600">Expires: {new Date(approval.expires_at).toLocaleString()}</p>
            <pre className="overflow-auto rounded-md bg-slate-100 p-3 text-xs">{contextPreview(approval.context)}</pre>
            {!approval.token && <p className="text-sm text-red-700">Token not exposed by API</p>}
            <div className="flex gap-2">
              <button className="btn-primary" disabled={!approval.token} onClick={() => approval.token && approve(approval.token)}>
                Approve
              </button>
              <button className="btn-danger" disabled={!approval.token} onClick={() => approval.token && reject(approval.token)}>
                Reject
              </button>
            </div>
          </article>
        ))}
        {data?.length === 0 && <div className="card">No pending approvals.</div>}
      </div>
    </section>
  );
}
