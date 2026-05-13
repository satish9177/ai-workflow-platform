import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import ExecutionTimeline from "../components/run/ExecutionTimeline";
import RunHeader from "../components/run/RunHeader";
import RunErrorSummary from "../components/run/RunErrorSummary";
import type { RunTimeline } from "../types/api";

export default function RunDetail() {
  const { id } = useParams();
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["run-timeline", id],
    queryFn: async () => (await api.get<RunTimeline>(`/api/v1/runs/${id}/timeline`)).data,
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
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
      {isLoading && <div className="card">Loading...</div>}
      {error && <div className="card text-sm text-red-700">{getErrorMessage(error)}</div>}
      {!isLoading && !error && !data && <div className="card text-sm text-slate-500">Run not found.</div>}
      {!isLoading && !error && data && (
        <>
          <RunHeader run={data.run} onCancel={cancelRun} onRetry={retryRun} />
          {data.run.status === "failed" && (
            <RunErrorSummary failedStep={data.steps.find((step) => step.step_key === data.failed_step_key)} />
          )}
          <ExecutionTimeline failedStepKey={data.failed_step_key} steps={data.steps} />
        </>
      )}
    </section>
  );
}
