import { useEffect, useState } from "react";

import type { ExecutionTreeNode } from "./buildExecutionTree";
import StepCard from "./StepCard";

type StepNodeProps = {
  node: ExecutionTreeNode;
  autoExpandedKeys: Set<string>;
  depth?: number;
};

export default function StepNode({ node, autoExpandedKeys, depth = 0 }: StepNodeProps) {
  const autoExpanded = autoExpandedKeys.has(node.step.step_key);
  const [expanded, setExpanded] = useState(autoExpanded);
  const hasChildren = node.children.length > 0;

  useEffect(() => {
    if (autoExpanded) {
      setExpanded(true);
    }
  }, [autoExpanded]);

  return (
    <div className="space-y-2">
      <div style={{ marginLeft: `${Math.min(depth, 6) * 18}px` }}>
        <StepCard
          expanded={expanded}
          hasChildren={hasChildren}
          onToggle={() => setExpanded((current) => !current)}
          step={node.step}
        />
      </div>
      {expanded && hasChildren && (
        <div className="space-y-2 border-l border-slate-200 pl-3" style={{ marginLeft: `${Math.min(depth, 6) * 18 + 10}px` }}>
          {node.children.map((child) => (
            <StepNode autoExpandedKeys={autoExpandedKeys} depth={depth + 1} key={child.step.id} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}
