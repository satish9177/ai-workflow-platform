function messageFrom(error?: Record<string, unknown> | null) {
  if (!error) {
    return "";
  }
  return typeof error.message === "string" ? error.message : JSON.stringify(error);
}

export default function ErrorPanel({ error }: { error?: Record<string, unknown> | null }) {
  const message = messageFrom(error);
  const type = typeof error?.type === "string" ? error.type : typeof error?.error_type === "string" ? error.error_type : "";
  const details = error?.traceback || error?.details;

  if (!error) {
    return null;
  }

  return (
    <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
      {type && <p className="font-semibold">{type}</p>}
      {message && <p>{message}</p>}
      {details !== undefined && (
        <details className="mt-2">
          <summary className="cursor-pointer font-medium">Traceback/details</summary>
          <pre className="mt-2 whitespace-pre-wrap rounded bg-red-100 p-2 text-xs">
            {typeof details === "string" ? details : JSON.stringify(details, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
