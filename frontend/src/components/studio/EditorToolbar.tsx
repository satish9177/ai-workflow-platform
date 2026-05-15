type EditorToolbarProps = {
  title: string;
  dirty: boolean;
  saving: boolean;
  running: boolean;
  onValidate: () => void;
  onSave: () => void;
  onRun: () => void;
  onFormat: () => void;
};

export default function EditorToolbar({
  title,
  dirty,
  saving,
  running,
  onValidate,
  onSave,
  onRun,
  onFormat,
}: EditorToolbarProps) {
  return (
    <div className="card flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-sm uppercase tracking-wide text-slate-500">Workflow Studio</p>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-2xl font-semibold">{title || "Untitled workflow"}</h2>
          <span className={dirty ? "badge-yellow" : "badge-green"}>{dirty ? "Unsaved changes" : "Saved"}</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="btn-secondary" onClick={onFormat} type="button">
          Format JSON
        </button>
        <button className="btn-secondary" onClick={onValidate} type="button">
          Validate
        </button>
        <button className="btn-primary" disabled={saving} onClick={onSave} type="button">
          {saving ? "Saving..." : "Save"}
        </button>
        <button className="btn-secondary" disabled={running} onClick={onRun} type="button">
          {running ? "Running..." : "Run"}
        </button>
      </div>
    </div>
  );
}
