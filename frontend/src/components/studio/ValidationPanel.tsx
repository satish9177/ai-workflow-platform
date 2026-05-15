export type ValidationIssue = {
  path: string;
  message: string;
};

type ValidationPanelProps = {
  issues: ValidationIssue[];
  backendError?: string;
  successMessage?: string;
};

export default function ValidationPanel({ issues, backendError, successMessage }: ValidationPanelProps) {
  return (
    <div className="card space-y-3">
      <div>
        <h3 className="text-lg font-semibold">Validation</h3>
        <p className="text-sm text-slate-500">Frontend checks run locally. Backend validation appears after save.</p>
      </div>

      {successMessage && <div className="rounded-md bg-green-50 p-3 text-sm text-green-700">{successMessage}</div>}
      {backendError && <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{backendError}</div>}

      {!backendError && issues.length === 0 && (
        <div className="rounded-md bg-green-50 p-3 text-sm text-green-700">No validation issues found.</div>
      )}

      {issues.length > 0 && (
        <ul className="space-y-2">
          {issues.map((issue) => (
            <li className="rounded-md border border-red-100 bg-red-50 p-3 text-sm text-red-700" key={`${issue.path}-${issue.message}`}>
              <span className="font-mono text-xs">{issue.path}</span>
              <span className="block">{issue.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
