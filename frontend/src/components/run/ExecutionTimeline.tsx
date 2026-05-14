import type { StepExecution } from "../../types/api";
import TimelineStep from "./TimelineStep";

export default function ExecutionTimeline({
  steps,
  failedStepKey,
}: {
  steps: StepExecution[];
  failedStepKey?: string | null;
}) {
  return (
    <div className="card space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Execution Timeline</h3>
        <p className="text-sm text-slate-500">Step-by-step execution state for this run.</p>
      </div>

      {steps.length === 0 ? (
        <p className="text-sm text-slate-500">No step executions yet.</p>
      ) : (
        <div className="space-y-3">
          {steps.map((step) => (
            <TimelineStep key={step.id} defaultExpanded={step.step_key === failedStepKey} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}
