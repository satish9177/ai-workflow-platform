import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { deleteIntegration, saveIntegration, testIntegration, type IntegrationStatus } from "../../api/integrations";
import type { KnownIntegration } from "./knownIntegrations";

type Props = {
  config: KnownIntegration;
  integrations: IntegrationStatus[];
  onSaveSuccess: () => void;
};

export default function IntegrationCard({ config, integrations, onSaveSuccess }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [showValues, setShowValues] = useState<Record<string, boolean>>({});
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [deleteError, setDeleteError] = useState("");
  const [testMessage, setTestMessage] = useState<Record<string, string>>({});

  const saveMutation = useMutation({
    mutationFn: saveIntegration,
    onSuccess: () => {
      clearForm();
      onSaveSuccess();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteIntegration,
    onSuccess: () => {
      setDeleteError("");
      onSaveSuccess();
    },
    onError: () => setDeleteError("Failed to delete. It may be used by a workflow."),
  });
  const testMutation = useMutation({
    mutationFn: testIntegration,
    onSuccess: (result, id) => {
      setTestMessage((current) => ({ ...current, [id]: result.message }));
      onSaveSuccess();
    },
    onError: (_error, id) => {
      setTestMessage((current) => ({ ...current, [id]: "Failed to test connection." }));
      onSaveSuccess();
    },
  });

  function clearForm() {
    setEditingId(null);
    setDisplayName("");
    setFieldValues({});
    setShowValues({});
    setValidationErrors({});
    saveMutation.reset();
  }

  function startCreate() {
    clearForm();
    setDisplayName(`${config.name} Integration`);
    setEditingId("new");
  }

  function startEdit(integration: IntegrationStatus) {
    clearForm();
    setDisplayName(integration.display_name);
    setEditingId(integration.id || null);
  }

  function save() {
    const nextErrors: Record<string, string> = {};
    if (!displayName.trim()) {
      nextErrors.display_name = "Display name is required";
    }
    for (const field of config.credentialFields) {
      if (field.required === false) {
        continue;
      }
      if (editingId === "new" && !fieldValues[field.key]?.trim()) {
        nextErrors[field.key] = `${field.label} is required`;
      }
    }

    setValidationErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    const credentials = Object.fromEntries(
      Object.entries(fieldValues).filter(([, value]) => value.trim()),
    );
    saveMutation.mutate({
      id: editingId === "new" ? undefined : editingId || undefined,
      integration_type: config.id,
      display_name: displayName,
      credentials,
    });
  }

  const isEditing = editingId !== null;
  const statusClass = {
    connected: "badge-green",
    failed: "badge-red",
    unknown: "badge-gray",
  };

  return (
    <article className="card space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{config.name}</h3>
          <p className="text-sm text-slate-500">{config.description}</p>
        </div>
        <button className="btn-primary" onClick={startCreate} type="button">
          Add {config.name}
        </button>
      </div>

      {integrations.length === 0 && <p className="text-sm text-slate-500">No {config.name} integrations configured yet.</p>}

      <div className="space-y-3">
        {integrations.map((integration) => (
          <div className="rounded-md border border-slate-200 p-4" key={integration.id || integration.name}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium">{integration.display_name}</p>
                <p className="text-sm text-slate-500">{integration.integration_type}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span className={integration.credentials_set ? "badge-green" : "badge-gray"}>
                    {integration.credentials_set ? "credentials set" : "credentials missing"}
                  </span>
                  <span className={statusClass[integration.status as keyof typeof statusClass] || "badge-gray"}>
                    {integration.status}
                  </span>
                </div>
                {integration.last_tested_at && (
                  <p className="mt-2 text-xs text-slate-500">
                    Last tested: {new Date(integration.last_tested_at).toLocaleString()}
                  </p>
                )}
                {(integration.last_error || testMessage[integration.id || ""]) && (
                  <p className="mt-2 text-sm text-red-700">
                    {integration.last_error || testMessage[integration.id || ""]}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                {integration.id && (
                  <button
                    className="btn-secondary"
                    disabled={testMutation.isPending || !integration.credentials_set}
                    onClick={() => testMutation.mutate(integration.id as string)}
                    type="button"
                  >
                    {testMutation.isPending ? "Testing..." : "Test Connection"}
                  </button>
                )}
                <button className="btn-secondary" onClick={() => startEdit(integration)} type="button">
                  Edit
                </button>
                {integration.id && (
                  <button
                    className="btn-secondary"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(integration.id as string)}
                    type="button"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {deleteError && <p className="text-sm text-red-700">{deleteError}</p>}

      {isEditing && config.authType === "oauth" && (
        <div className="space-y-2 rounded-md border border-slate-200 p-4">
          <button className="btn-secondary" disabled type="button">
            Connect with {config.name}
          </button>
          <p className="text-sm text-slate-500">Coming soon</p>
          <button className="btn-secondary" onClick={clearForm} type="button">
            Cancel
          </button>
        </div>
      )}

      {isEditing && (config.authType === "webhook" || config.authType === "smtp") && (
        <div className="space-y-4 rounded-md border border-slate-200 p-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700" htmlFor={`${config.id}-display-name`}>
              Display name
            </label>
            <input
              className="input"
              id={`${config.id}-display-name`}
              onChange={(event) => {
                setDisplayName(event.target.value);
                setValidationErrors((current) => ({ ...current, display_name: "" }));
              }}
              value={displayName}
            />
            {validationErrors.display_name && <p className="text-sm text-red-700">{validationErrors.display_name}</p>}
          </div>

          {editingId !== "new" && (
            <p className="text-sm text-slate-500">Enter a new credential value to replace the existing one.</p>
          )}

          {config.credentialFields.map((field) => {
            const isVisible = Boolean(showValues[field.key]);
            return (
              <div className="space-y-1" key={field.key}>
                <label className="text-sm font-medium text-slate-700" htmlFor={`${config.id}-${field.key}`}>
                  {field.label}
                </label>
                <div className="flex gap-2">
                  <input
                    className="input"
                    id={`${config.id}-${field.key}`}
                    onChange={(event) => {
                      setFieldValues((current) => ({ ...current, [field.key]: event.target.value }));
                      setValidationErrors((current) => ({ ...current, [field.key]: "" }));
                    }}
                    placeholder={field.placeholder}
                    type={isVisible ? "text" : field.type || "password"}
                    value={fieldValues[field.key] || ""}
                  />
                  <button
                    aria-label={`Show/hide ${field.label}`}
                    className="btn-secondary"
                    onClick={() => setShowValues((current) => ({ ...current, [field.key]: !current[field.key] }))}
                    type="button"
                  >
                    {isVisible ? "Hide" : "Show"}
                  </button>
                </div>
                {field.hint && <p className="text-sm text-slate-500">{field.hint}</p>}
                {validationErrors[field.key] && <p className="text-sm text-red-700">{validationErrors[field.key]}</p>}
              </div>
            );
          })}

          {saveMutation.isError && (
            <p className="text-sm text-red-700">Failed to save. Check the value and try again.</p>
          )}

          <div className="flex gap-2">
            <button className="btn-secondary" disabled={saveMutation.isPending} onClick={clearForm} type="button">
              Cancel
            </button>
            <button className="btn-primary" disabled={saveMutation.isPending} onClick={save} type="button">
              {editingId === "new" ? "Connect" : "Save"}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
