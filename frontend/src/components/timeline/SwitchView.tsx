import type { StepExecution } from "../../types/api";

export default function SwitchView({ step }: { step: StepExecution }) {
  if (step.step_type !== "switch" && step.step_type !== "switch_branch") {
    return null;
  }

  const output = step.output_preview || {};
  const selected = output.selected_branch;

  return (
    <div className="rounded-md bg-blue-50 p-3 text-sm text-blue-800">
      {step.step_type === "switch" ? (
        <div className="grid gap-1 md:grid-cols-2">
          <p>Evaluated: {String(output.evaluated_value ?? "-")}</p>
          <p>Selected branch: {String(selected ?? "none")}</p>
          <p>Matched: {String(output.matched ?? "-")}</p>
          <p>Used default: {String(output.used_default ?? "-")}</p>
        </div>
      ) : (
        <p>{output.selected ? "Selected branch" : "Skipped branch"}</p>
      )}
    </div>
  );
}
