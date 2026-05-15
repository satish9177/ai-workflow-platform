import type { StepExecution } from "../../types/api";

export default function RetryInfo({ step }: { step: StepExecution }) {
  if (step.attempt_number <= 1 && step.max_attempts <= 1) {
    return null;
  }

  return (
    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
      Attempt {step.attempt_number} of {step.max_attempts}
    </span>
  );
}
