import type { StepExecution } from "../../types/api";

export type ExecutionTreeNode = {
  step: StepExecution;
  children: ExecutionTreeNode[];
};

function timestamp(step: StepExecution): number {
  const value = step.started_at || step.completed_at || step.created_at;
  return value ? Date.parse(value) || Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER;
}

function sortNodes(nodes: ExecutionTreeNode[]) {
  nodes.sort((a, b) => {
    const timeDiff = timestamp(a.step) - timestamp(b.step);
    if (timeDiff !== 0) {
      return timeDiff;
    }
    return a.step.step_key.localeCompare(b.step.step_key);
  });
  nodes.forEach((node) => sortNodes(node.children));
}

function closestDottedParent(stepKey: string, keys: Set<string>, parentStepId?: string | null): string | null {
  const parts = stepKey.split(".");
  for (let index = parts.length - 1; index > 0; index -= 1) {
    const candidate = parts.slice(0, index).join(".");
    if (keys.has(candidate) && (!parentStepId || candidate === parentStepId || candidate.startsWith(`${parentStepId}.`))) {
      return candidate;
    }
  }
  return null;
}

export function buildExecutionTree(stepExecutions: StepExecution[]): ExecutionTreeNode[] {
  const nodes = new Map<string, ExecutionTreeNode>();
  const keys = new Set(stepExecutions.map((step) => step.step_key));

  stepExecutions.forEach((step) => {
    nodes.set(step.step_key, { step, children: [] });
  });

  const roots: ExecutionTreeNode[] = [];

  stepExecutions.forEach((step) => {
    const node = nodes.get(step.step_key);
    if (!node) {
      return;
    }

    const inferredParent = closestDottedParent(step.step_key, keys, step.parent_step_id);
    const parentKey = inferredParent || (step.parent_step_id && keys.has(step.parent_step_id) ? step.parent_step_id : null);
    const parent = parentKey ? nodes.get(parentKey) : undefined;

    if (parent && parent.step.step_key !== step.step_key) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  });

  sortNodes(roots);
  return roots;
}

export function collectAutoExpandedKeys(nodes: ExecutionTreeNode[]): Set<string> {
  const expanded = new Set<string>();
  const importantStatuses = new Set(["failed", "running", "awaiting_approval", "auto_rejected", "partially_paused"]);

  function visit(node: ExecutionTreeNode, ancestors: string[]) {
    const hasImportantStatus = importantStatuses.has(node.step.status);
    node.children.forEach((child) => visit(child, [...ancestors, node.step.step_key]));
    const childExpanded = node.children.some((child) => expanded.has(child.step.step_key));
    if (hasImportantStatus || childExpanded) {
      ancestors.forEach((key) => expanded.add(key));
      expanded.add(node.step.step_key);
    }
  }

  nodes.forEach((node) => visit(node, []));
  return expanded;
}
