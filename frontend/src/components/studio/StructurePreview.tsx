type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function labelForStep(step: JsonObject) {
  const id = typeof step.id === "string" ? step.id : "missing-id";
  const type = typeof step.type === "string" ? step.type : "missing-type";
  return `${id} [${type}]`;
}

function StepNode({ step, depth = 0 }: { step: JsonObject; depth?: number }) {
  const type = typeof step.type === "string" ? step.type : "";
  const indent = { paddingLeft: `${depth * 16}px` };

  return (
    <li>
      <div className="rounded px-2 py-1 font-mono text-xs text-slate-700" style={indent}>
        {labelForStep(step)}
      </div>

      {type === "parallel_group" && Array.isArray(step.steps) && (
        <ul>
          {step.steps.filter(isObject).map((child, index) => (
            <StepNode depth={depth + 1} key={`${String(child.id)}-${index}`} step={child} />
          ))}
        </ul>
      )}

      {type === "foreach" && isObject(step.step) && (
        <ul>
          <li>
            <div className="px-2 py-1 font-mono text-xs text-slate-500" style={{ paddingLeft: `${(depth + 1) * 16}px` }}>
              iteration
            </div>
            <StepNode depth={depth + 2} step={step.step} />
          </li>
        </ul>
      )}

      {type === "switch" && isObject(step.branches) && (
        <ul>
          {Object.entries(step.branches).map(([branchKey, branchSteps]) => (
            <li key={branchKey}>
              <div className="px-2 py-1 font-mono text-xs text-blue-700" style={{ paddingLeft: `${(depth + 1) * 16}px` }}>
                {branchKey}
              </div>
              {Array.isArray(branchSteps) &&
                branchSteps.filter(isObject).map((child, index) => (
                  <StepNode depth={depth + 2} key={`${branchKey}-${String(child.id)}-${index}`} step={child} />
                ))}
            </li>
          ))}
          {Array.isArray(step.default) && (
            <li>
              <div className="px-2 py-1 font-mono text-xs text-blue-700" style={{ paddingLeft: `${(depth + 1) * 16}px` }}>
                default
              </div>
              {step.default.filter(isObject).map((child, index) => (
                <StepNode depth={depth + 2} key={`default-${String(child.id)}-${index}`} step={child} />
              ))}
            </li>
          )}
        </ul>
      )}
    </li>
  );
}

export default function StructurePreview({ document }: { document: unknown }) {
  const steps = isObject(document) && Array.isArray(document.steps) ? document.steps.filter(isObject) : [];

  return (
    <div className="card space-y-3">
      <div>
        <h3 className="text-lg font-semibold">Structure Preview</h3>
        <p className="text-sm text-slate-500">Read-only hierarchy generated from the JSON document.</p>
      </div>
      {steps.length === 0 ? (
        <p className="text-sm text-slate-500">No steps to preview.</p>
      ) : (
        <ul className="space-y-1">
          <li>
            <div className="rounded bg-slate-100 px-2 py-1 font-mono text-xs font-semibold text-slate-700">workflow</div>
            <ul>
              {steps.map((step, index) => (
                <StepNode depth={1} key={`${String(step.id)}-${index}`} step={step} />
              ))}
            </ul>
          </li>
        </ul>
      )}
    </div>
  );
}
