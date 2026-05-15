import { useState } from "react";

function stringify(value?: Record<string, unknown> | null) {
  return value ? JSON.stringify(value, null, 2) : "";
}

function PreviewSection({ title, value }: { title: string; value?: Record<string, unknown> | null }) {
  const [showAll, setShowAll] = useState(false);
  const [copied, setCopied] = useState(false);
  const formatted = stringify(value);
  const isLong = formatted.length > 1400;
  const visible = isLong && !showAll ? `${formatted.slice(0, 1400)}\n...[truncated]` : formatted;

  async function copy() {
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
          <button className="text-xs font-medium text-blue-700 hover:underline" onClick={copy} type="button">
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
      {formatted ? (
        <>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-slate-100 p-3 text-xs text-slate-700">{visible}</pre>
          {isLong && (
            <button className="mt-2 text-xs font-medium text-blue-700 hover:underline" onClick={() => setShowAll(!showAll)} type="button">
              {showAll ? "Show less" : "Show more"}
            </button>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-500">No preview available.</p>
      )}
    </div>
  );
}

export default function PayloadInspector({
  input,
  output,
  error,
}: {
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <PreviewSection title="Input Preview" value={input} />
      <PreviewSection title="Output Preview" value={output} />
      <PreviewSection title="Error Details" value={error} />
    </div>
  );
}
