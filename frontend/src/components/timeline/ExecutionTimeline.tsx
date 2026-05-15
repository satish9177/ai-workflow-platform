import { useMemo } from "react";

import type { StepExecution } from "../../types/api";
import { buildExecutionTree, collectAutoExpandedKeys } from "./buildExecutionTree";
import StepNode from "./StepNode";

export default function ExecutionTimeline({ steps }: { steps: StepExecution[] }) {
  const tree = useMemo(() => buildExecutionTree(steps), [steps]);
  const autoExpandedKeys = useMemo(() => collectAutoExpandedKeys(tree), [tree]);

  return (
    <div className="card space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Execution Timeline</h3>
        <p className="text-sm text-slate-500">Nested execution tree for linear steps, branches, foreach iterations, switch routes, and approvals.</p>
      </div>

      {steps.length === 0 ? (
        <p className="text-sm text-slate-500">No step executions yet.</p>
      ) : (
        <div className="space-y-3">
          {tree.map((node) => (
            <StepNode autoExpandedKeys={autoExpandedKeys} key={node.step.id} node={node} />
          ))}
        </div>
      )}
    </div>
  );
}
