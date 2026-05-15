import type { StepExecution } from "../../types/api";

export default function ApprovalWait({ step }: { step: StepExecution }) {
  if (step.step_type !== "approval") {
    return null;
  }

  const input = step.input_preview || {};
  const output = step.output_preview || {};

  return (
    <div className="rounded-md bg-yellow-50 p-3 text-sm text-yellow-900">
      <div className="grid gap-1 md:grid-cols-2">
        <p>Approver: {String(input.approver_email ?? "-")}</p>
        <p>Approval status: {String(output.status ?? step.status)}</p>
        {output.timed_out !== undefined && <p>Timed out: {String(output.timed_out)}</p>}
        {output.timeout_action !== undefined && <p>Timeout action: {String(output.timeout_action)}</p>}
      </div>
    </div>
  );
}
