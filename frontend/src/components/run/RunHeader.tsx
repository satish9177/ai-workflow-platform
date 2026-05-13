import StatusBadge from "../StatusBadge";
import type { Run } from "../../types/api";
import { formatDate } from "../../utils/date";

type RunHeaderProps = {
  run?: Run;
  onCancel: () => void;
  onRetry: () => void;
};

export default function RunHeader({ run, onCancel, onRetry }: RunHeaderProps) {
  return (
    <div className="card space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Status</span>
        <StatusBadge status={run?.status} />
      </div>
      <p className="text-sm text-slate-600">Workflow: {run?.workflow_id || "-"}</p>
      <p className="text-sm text-slate-600">Started: {formatDate(run?.started_at)}</p>
      <p className="text-sm text-slate-600">Completed: {formatDate(run?.completed_at)}</p>
      {run?.error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{run.error}</p>}
      <div className="flex gap-2">
        {run?.status === "running" && (
          <button className="btn-danger" onClick={onCancel}>
            Cancel
          </button>
        )}
        {run?.status === "failed" && (
          <button className="btn-primary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
