import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";
import SplitPane from "../components/shared/SplitPane";
import EditorToolbar from "../components/studio/EditorToolbar";
import StepSnippets, { type StepSnippet } from "../components/studio/StepSnippets";
import StructurePreview from "../components/studio/StructurePreview";
import ValidationPanel, { type ValidationIssue } from "../components/studio/ValidationPanel";
import WorkflowEditor from "../components/studio/WorkflowEditor";
import type { Workflow } from "../types/api";

type WorkflowDocument = {
  name: string;
  description?: string | null;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  steps: Record<string, unknown>[];
};

const SUPPORTED_STEP_TYPES = new Set([
  "llm",
  "tool",
  "approval",
  "parallel_group",
  "foreach",
  "switch",
  "condition",
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function defaultWorkflowDocument(): WorkflowDocument {
  return {
    name: "New Workflow",
    description: "",
    trigger_type: "manual",
    trigger_config: {},
    steps: [],
  };
}

function workflowToDocument(workflow: Workflow): WorkflowDocument {
  return {
    name: workflow.name,
    description: workflow.description || "",
    trigger_type: workflow.trigger_type,
    trigger_config: workflow.trigger_config || {},
    steps: workflow.steps || [],
  };
}

function formatDocument(document: unknown) {
  return JSON.stringify(document, null, 2);
}

function parseEditorJson(text: string): { value?: unknown; error?: string } {
  try {
    return { value: JSON.parse(text) };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Invalid JSON" };
  }
}

function validateStep(step: unknown, path: string, issues: ValidationIssue[]) {
  if (!isObject(step)) {
    issues.push({ path, message: "Step must be an object." });
    return;
  }

  if (typeof step.id !== "string" || !step.id.trim()) {
    issues.push({ path: `${path}.id`, message: "Step id is required." });
  }

  if (typeof step.type !== "string" || !step.type.trim()) {
    issues.push({ path: `${path}.type`, message: "Step type is required." });
    return;
  }

  if (!SUPPORTED_STEP_TYPES.has(step.type)) {
    issues.push({ path: `${path}.type`, message: `Unsupported step type: ${step.type}` });
    return;
  }

  if (step.type === "parallel_group") {
    if (!Array.isArray(step.steps) || step.steps.length === 0) {
      issues.push({ path: `${path}.steps`, message: "parallel_group requires a non-empty steps array." });
    } else {
      step.steps.forEach((child, index) => validateStep(child, `${path}.steps[${index}]`, issues));
    }
  }

  if (step.type === "foreach") {
    if (!("items" in step)) {
      issues.push({ path: `${path}.items`, message: "foreach requires items." });
    }
    if (!isObject(step.step)) {
      issues.push({ path: `${path}.step`, message: "foreach requires a child step object." });
    } else {
      validateStep(step.step, `${path}.step`, issues);
    }
  }

  if (step.type === "switch") {
    if (typeof step.on !== "string" || !step.on.trim()) {
      issues.push({ path: `${path}.on`, message: "switch requires a non-empty on value." });
    }
    if (!isObject(step.branches) || Object.keys(step.branches).length === 0) {
      issues.push({ path: `${path}.branches`, message: "switch requires branches." });
    } else {
      Object.entries(step.branches).forEach(([branchKey, branchSteps]) => {
        if (!Array.isArray(branchSteps) || branchSteps.length === 0) {
          issues.push({ path: `${path}.branches.${branchKey}`, message: "Branch must be a non-empty step array." });
          return;
        }
        branchSteps.forEach((child, index) => validateStep(child, `${path}.branches.${branchKey}[${index}]`, issues));
      });
    }
    if ("default" in step) {
      if (!Array.isArray(step.default) || step.default.length === 0) {
        issues.push({ path: `${path}.default`, message: "default branch must be a non-empty step array." });
      } else {
        step.default.forEach((child, index) => validateStep(child, `${path}.default[${index}]`, issues));
      }
    }
  }
}

function validateWorkflowDocument(value: unknown): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!isObject(value)) {
    return [{ path: "$", message: "Workflow document must be a JSON object." }];
  }

  if (typeof value.name !== "string" || !value.name.trim()) {
    issues.push({ path: "name", message: "Workflow name is required." });
  }
  if (typeof value.trigger_type !== "string" || !value.trigger_type.trim()) {
    issues.push({ path: "trigger_type", message: "trigger_type is required." });
  }
  if (!isObject(value.trigger_config)) {
    issues.push({ path: "trigger_config", message: "trigger_config must be an object." });
  }
  if (!Array.isArray(value.steps)) {
    issues.push({ path: "steps", message: "steps must be an array." });
  } else {
    value.steps.forEach((step, index) => validateStep(step, `steps[${index}]`, issues));
  }

  return issues;
}

function toWorkflowPayload(value: unknown): WorkflowDocument {
  if (!isObject(value)) {
    throw new Error("Workflow document must be an object.");
  }
  return {
    name: String(value.name || ""),
    description: typeof value.description === "string" ? value.description : value.description === null ? null : "",
    trigger_type: String(value.trigger_type || "manual"),
    trigger_config: isObject(value.trigger_config) ? value.trigger_config : {},
    steps: Array.isArray(value.steps) ? value.steps.filter(isObject) : [],
  };
}

export default function WorkflowStudioPage() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isNew = id === "new" || location.pathname === "/workflows/new/studio";
  const [editorText, setEditorText] = useState(formatDocument(defaultWorkflowDocument()));
  const [dirty, setDirty] = useState(false);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([]);
  const [backendError, setBackendError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const workflowQuery = useQuery({
    queryKey: ["workflow", id],
    queryFn: async () => (await api.get<Workflow>(`/api/v1/workflows/${id}`)).data,
    enabled: Boolean(id) && !isNew,
  });

  useEffect(() => {
    if (workflowQuery.data) {
      setEditorText(formatDocument(workflowToDocument(workflowQuery.data)));
      setDirty(false);
      setBackendError("");
      setSuccessMessage("");
      setValidationIssues([]);
    }
  }, [workflowQuery.data]);

  const parsed = useMemo(() => parseEditorJson(editorText), [editorText]);
  const parsedDocument = parsed.value;
  const title = isObject(parsedDocument) && typeof parsedDocument.name === "string" ? parsedDocument.name : workflowQuery.data?.name || "New Workflow";

  function setText(value: string) {
    setEditorText(value);
    setDirty(true);
    setSuccessMessage("");
  }

  function validateCurrent() {
    setBackendError("");
    if (parsed.error) {
      setValidationIssues([{ path: "$", message: parsed.error }]);
      return false;
    }
    const issues = validateWorkflowDocument(parsed.value);
    setValidationIssues(issues);
    return issues.length === 0;
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!validateCurrent()) {
        throw new Error("Fix validation errors before saving.");
      }
      const payload = toWorkflowPayload(parsed.value);
      if (isNew) {
        return (await api.post<Workflow>("/api/v1/workflows/", payload)).data;
      }
      return (await api.put<Workflow>(`/api/v1/workflows/${id}`, payload)).data;
    },
    onSuccess: async (workflow) => {
      setDirty(false);
      setBackendError("");
      setSuccessMessage("Workflow saved.");
      setEditorText(formatDocument(workflowToDocument(workflow)));
      await queryClient.invalidateQueries({ queryKey: ["workflows"] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", workflow.id] });
      if (isNew) {
        navigate(`/workflows/${workflow.id}/studio`, { replace: true });
      }
    },
    onError: (error) => {
      setSuccessMessage("");
      setBackendError(getErrorMessage(error));
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      if (dirty) {
        throw new Error("Save the workflow before running it.");
      }
      if (!id || isNew) {
        throw new Error("Save the new workflow before running it.");
      }
      return (await api.post<{ run_id: string; status: string }>(`/api/v1/workflows/${id}/run`, { trigger_data: {} })).data;
    },
    onSuccess: (result) => {
      navigate(`/runs/${result.run_id}`);
    },
    onError: (error) => {
      setBackendError(getErrorMessage(error));
    },
  });

  function formatJson() {
    if (parsed.error) {
      setValidationIssues([{ path: "$", message: parsed.error }]);
      return;
    }
    setText(formatDocument(parsed.value));
  }

  function insertSnippet(snippet: StepSnippet) {
    const current = parseEditorJson(editorText);
    if (current.error || !isObject(current.value)) {
      void navigator.clipboard?.writeText(JSON.stringify(snippet.value, null, 2));
      setBackendError("Editor JSON is invalid. Snippet copied to clipboard instead.");
      return;
    }
    const document = { ...current.value };
    const steps = Array.isArray(document.steps) ? [...document.steps] : [];
    steps.push(snippet.value);
    document.steps = steps;
    setText(formatDocument(document));
  }

  if (workflowQuery.isLoading) {
    return <div className="card">Loading...</div>;
  }

  if (!isNew && (workflowQuery.error || !workflowQuery.data)) {
    return <div className="card text-sm text-red-700">{workflowQuery.error ? getErrorMessage(workflowQuery.error) : "Workflow not found"}</div>;
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link className="text-sm font-medium text-blue-700 hover:underline" to={isNew ? "/workflows" : `/workflows/${id}`}>
          {isNew ? "Back to workflows" : "Back to workflow detail"}
        </Link>
        {!isNew && (
          <Link className="text-sm font-medium text-blue-700 hover:underline" to={`/workflows/${id}`}>
            View settings
          </Link>
        )}
      </div>

      <EditorToolbar
        dirty={dirty}
        onFormat={formatJson}
        onRun={() => runMutation.mutate()}
        onSave={() => saveMutation.mutate()}
        onValidate={validateCurrent}
        running={runMutation.isPending}
        saving={saveMutation.isPending}
        title={title}
      />

      <SplitPane
        left={<WorkflowEditor onChange={setText} onSave={() => saveMutation.mutate()} value={editorText} />}
        right={
          <div className="space-y-4">
            <StructurePreview document={parsedDocument} />
            <ValidationPanel backendError={backendError} issues={validationIssues} successMessage={successMessage} />
          </div>
        }
      />

      <StepSnippets onInsert={insertSnippet} />
    </section>
  );
}
