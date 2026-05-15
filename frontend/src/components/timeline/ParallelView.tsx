import type { StepExecution } from "../../types/api";

export default function ParallelView({ step }: { step: StepExecution }) {
  const branches = step.output_preview?.branches;

  if (step.step_type !== "parallel_group" && !step.branch_key) {
    return null;
  }

  return (
    <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
      {step.step_type === "parallel_group" && branches !== undefined && branches !== null && typeof branches === "object" && (
        <p>Branches: {Object.keys(branches as Record<string, unknown>).join(", ")}</p>
      )}
      {step.branch_key && <p>Branch key: {step.branch_key}</p>}
    </div>
  );
}
