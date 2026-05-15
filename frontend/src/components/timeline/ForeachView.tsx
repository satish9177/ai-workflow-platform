import type { StepExecution } from "../../types/api";

export default function ForeachView({ step }: { step: StepExecution }) {
  const output = step.output_preview || {};
  const results = Array.isArray(output.results) ? output.results : undefined;

  if (step.step_type !== "foreach" && step.foreach_index == null) {
    return null;
  }

  return (
    <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
      {step.step_type === "foreach" && (
        <div className="grid gap-1 md:grid-cols-3">
          <p>Completed: {String(output.completed_count ?? "-")}</p>
          <p>Failed: {String(output.failed_count ?? "-")}</p>
          <p>Results: {results ? results.length : "-"}</p>
        </div>
      )}
      {step.foreach_index != null && (
        <div className="mt-1">
          <p>Iteration: {step.foreach_index}</p>
          {step.foreach_item !== undefined && (
            <pre className="mt-2 max-h-32 overflow-auto rounded bg-white p-2 text-xs">{JSON.stringify(step.foreach_item, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}
