import type { StepExecution } from "../../types/api";

function errorText(errorDetails?: Record<string, unknown> | null) {
  if (!errorDetails) {
    return "";
  }
  const message = errorDetails.message;
  return typeof message === "string" ? message : JSON.stringify(errorDetails);
}

export default function RunErrorSummary({ failedStep }: { failedStep?: StepExecution }) {
  if (!failedStep) {
    return null;
  }

  const message = errorText(failedStep.error_details);

  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-4">
      <p className="text-sm font-semibold text-red-800">Run failed at {failedStep.step_label || failedStep.step_key}</p>
      <p className="mt-1 font-mono text-xs text-red-700">{failedStep.step_key}</p>
      {failedStep.attempt_number > 1 && (
        <p className="mt-2 text-sm text-red-700">
          Attempt {failedStep.attempt_number} of {failedStep.max_attempts}
        </p>
      )}
      {message && <p className="mt-2 text-sm text-red-700">{message}</p>}
    </div>
  );
}
