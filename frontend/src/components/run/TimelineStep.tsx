import { useEffect, useState } from "react";

import type { StepExecution } from "../../types/api";
import { formatDate } from "../../utils/date";

const statusClass: Record<string, { badge: string; border: string }> = {
  pending: { badge: "badge-gray", border: "border-slate-200" },
  running: { badge: "badge-blue", border: "border-blue-200 bg-blue-50" },
  completed: { badge: "badge-green", border: "border-green-200" },
  failed: { badge: "badge-red", border: "border-red-200 bg-red-50" },
  skipped: { badge: "badge-gray", border: "border-slate-200 bg-slate-50" },
  awaiting_approval: { badge: "badge-yellow", border: "border-yellow-200 bg-yellow-50" },
};

function getErrorMessage(errorDetails?: Record<string, unknown> | null) {
  if (!errorDetails) {
    return "";
  }
  const message = errorDetails.message;
  return typeof message === "string" ? message : JSON.stringify(errorDetails);
}

function getErrorType(errorDetails?: Record<string, unknown> | null) {
  if (!errorDetails) {
    return "";
  }
  const type = errorDetails.type || errorDetails.error_type;
  return typeof type === "string" ? type : "";
}

function getErrorDetails(errorDetails?: Record<string, unknown> | null) {
  if (!errorDetails) {
    return "";
  }
  const details = errorDetails.traceback || errorDetails.details;
  if (typeof details === "string") {
    return details;
  }
  return details ? JSON.stringify(details, null, 2) : "";
}

function PreviewBlock({ title, value }: { title: string; value?: Record<string, unknown> | null }) {
  const [showMore, setShowMore] = useState(false);
  const [copied, setCopied] = useState(false);
  const formatted = value ? JSON.stringify(value, null, 2) : "";
  const isLong = formatted.length > 1200;
  const visibleValue = isLong && !showMore ? `${formatted.slice(0, 1200)}\n...[truncated]` : formatted;

  async function copyPreview() {
    if (!formatted || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(formatted);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-700">{title}</h4>
        {formatted && (
          <button className="text-xs font-medium text-blue-700 hover:underline" onClick={copyPreview} type="button">
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
      {formatted ? (
        <>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-slate-100 p-3 text-xs text-slate-700">
            {visibleValue}
          </pre>
          {isLong && (
            <button className="mt-2 text-xs font-medium text-blue-700 hover:underline" onClick={() => setShowMore(!showMore)} type="button">
              {showMore ? "Show less" : "Show more"}
            </button>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-500">No preview available.</p>
      )}
    </div>
  );
}

export default function TimelineStep({
  step,
  defaultExpanded = false,
}: {
  step: StepExecution;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isFailed = step.status === "failed";
  const styles = statusClass[step.status] || statusClass.pending;
  const errorMessage = getErrorMessage(step.error_details);
  const errorType = getErrorType(step.error_details);
  const errorDetails = getErrorDetails(step.error_details);

  useEffect(() => {
    if (defaultExpanded) {
      setExpanded(true);
    }
  }, [defaultExpanded]);

  return (
    <div className={`rounded-md border p-4 ${styles.border}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{step.step_label || step.step_key}</h3>
          <p className="font-mono text-xs text-slate-500">{step.step_key}</p>
          {step.attempt_number > 1 && (
            <p className="mt-1 text-xs font-medium text-slate-600">
              Attempt {step.attempt_number} of {step.max_attempts}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={styles.badge}>{step.status}</span>
          <button className="text-sm font-medium text-blue-700 hover:underline" onClick={() => setExpanded(!expanded)} type="button">
            {expanded ? "Hide details" : "View details"}
          </button>
        </div>
      </div>

      {isFailed && errorMessage && (
        <p className="mt-3 rounded-md bg-white p-3 text-sm text-red-700">{errorMessage}</p>
      )}

      {expanded && (
        <div className="mt-3 space-y-3">
          <div className="grid gap-2 text-sm text-slate-600 md:grid-cols-2">
            <p>Status: {step.status}</p>
            <p>Type: {step.step_type}</p>
            <p>Step key: {step.step_key}</p>
            <p>
              Attempt: {step.attempt_number}/{step.max_attempts}
            </p>
            <p>Started: {formatDate(step.started_at)}</p>
            <p>Completed: {formatDate(step.completed_at)}</p>
            <p>Duration: {step.duration_ms != null ? `${step.duration_ms}ms` : "-"}</p>
            {step.tool_name && <p>Tool: {step.tool_name}</p>}
            {step.provider && <p>Provider: {step.provider}</p>}
            {step.model && <p>Model: {step.model}</p>}
          </div>

          {isFailed && (
            <div className="rounded-md bg-white p-3 text-sm text-red-700">
              {errorType && <p className="font-medium">Error type: {errorType}</p>}
              {errorMessage && <p className="mt-1">{errorMessage}</p>}
              {errorDetails && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-medium">Traceback/details</summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded bg-red-100 p-2 text-xs">{errorDetails}</pre>
                </details>
              )}
            </div>
          )}

          <div className="grid gap-3 lg:grid-cols-2">
            <PreviewBlock title="Input Preview" value={step.input_preview} />
            <PreviewBlock title="Output Preview" value={step.output_preview} />
          </div>
        </div>
      )}
    </div>
  );
}
