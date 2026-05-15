import type { KeyboardEvent } from "react";

type WorkflowEditorProps = {
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
};

export default function WorkflowEditor({ value, onChange, onSave }: WorkflowEditorProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      onSave();
    }
  }

  return (
    <textarea
      className="min-h-[640px] w-full resize-y rounded-lg border border-slate-300 bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-100 outline-none focus:border-slate-500"
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={handleKeyDown}
      spellCheck={false}
      value={value}
    />
  );
}
