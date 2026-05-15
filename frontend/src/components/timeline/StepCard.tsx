import StatusBadge from "../StatusBadge";
import type { StepExecution } from "../../types/api";
import { formatDate } from "../../utils/date";
import ApprovalWait from "./ApprovalWait";
import ErrorPanel from "./ErrorPanel";
import ForeachView from "./ForeachView";
import ParallelView from "./ParallelView";
import PayloadInspector from "./PayloadInspector";
import RetryInfo from "./RetryInfo";
import SwitchView from "./SwitchView";

type StepCardProps = {
  step: StepExecution;
  expanded: boolean;
  hasChildren: boolean;
  onToggle: () => void;
};

const borderClass: Record<string, string> = {
  pending: "border-slate-200",
  queued: "border-slate-200",
  running: "border-blue-200 bg-blue-50",
  awaiting_approval: "border-yellow-200 bg-yellow-50",
  partially_paused: "border-yellow-200 bg-yellow-50",
  completed: "border-green-200",
  failed: "border-red-200 bg-red-50",
  cancelled: "border-slate-300 bg-slate-50",
  skipped: "border-slate-200 bg-slate-50 opacity-80",
  auto_approved: "border-green-200 bg-green-50",
  auto_rejected: "border-red-200 bg-red-50",
};

export default function StepCard({ step, expanded, hasChildren, onToggle }: StepCardProps) {
  return (
    <div className={`rounded-md border p-4 ${borderClass[step.status] || borderClass.pending}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button
              aria-label={expanded ? "Collapse step" : "Expand step"}
              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 disabled:opacity-40"
              disabled={!hasChildren && !step.input_preview && !step.output_preview && !step.error_details}
              onClick={onToggle}
              type="button"
            >
              {expanded ? "-" : "+"}
            </button>
            <h3 className="font-semibold">{step.step_label || step.step_key}</h3>
            <StatusBadge status={step.status} />
            <RetryInfo step={step} />
          </div>
          <p className="mt-1 font-mono text-xs text-slate-500">{step.step_key}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
            <span>Type: {step.step_type}</span>
            {step.tool_name && <span>Tool: {step.tool_name}</span>}
            {step.provider && <span>Provider: {step.provider}</span>}
            {step.model && <span>Model: {step.model}</span>}
            {step.duration_ms != null && <span>Duration: {step.duration_ms}ms</span>}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3">
          <div className="grid gap-2 text-sm text-slate-600 md:grid-cols-2">
            <p>Started: {formatDate(step.started_at)}</p>
            <p>Completed: {formatDate(step.completed_at)}</p>
            <p>Attempt: {step.attempt_number}/{step.max_attempts}</p>
            {step.parent_step_id && <p>Parent: {step.parent_step_id}</p>}
          </div>
          <SwitchView step={step} />
          <ForeachView step={step} />
          <ParallelView step={step} />
          <ApprovalWait step={step} />
          <ErrorPanel error={step.error_details} />
          <PayloadInspector error={step.error_details} input={step.input_preview} output={step.output_preview} />
        </div>
      )}
    </div>
  );
}
