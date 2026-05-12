import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { saveIntegration, type IntegrationStatus } from "../../api/integrations";
import type { KnownIntegration } from "./knownIntegrations";

type Props = {
  config: KnownIntegration;
  serverData?: IntegrationStatus;
  onSaveSuccess: () => void;
};

export default function IntegrationCard({ config, serverData, onSaveSuccess }: Props) {
  const [editing, setEditing] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [showValues, setShowValues] = useState<Record<string, boolean>>({});
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const isConfigured = Boolean(serverData?.has_credentials);

  const mutation = useMutation({
    mutationFn: saveIntegration,
    onSuccess: () => {
      clearForm();
      setEditing(false);
      onSaveSuccess();
    },
  });

  function clearForm() {
    setFieldValues({});
    setShowValues({});
    setValidationErrors({});
    mutation.reset();
  }

  function cancel() {
    clearForm();
    setEditing(false);
  }

  function save() {
    const nextErrors: Record<string, string> = {};
    for (const field of config.credentialFields) {
      if (!fieldValues[field.key]?.trim()) {
        nextErrors[field.key] = `${field.label} is required`;
      }
    }

    setValidationErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    mutation.mutate({
      name: config.id,
      credentials: fieldValues,
    });
  }

  return (
    <article className="card space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{config.name}</h3>
          <p className="text-sm text-slate-500">{config.description}</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <span className={`h-2.5 w-2.5 rounded-full ${isConfigured ? "bg-green-500" : "bg-slate-300"}`} />
          {isConfigured ? "Configured" : "Not configured"}
        </div>
      </div>

      {!editing && (
        <button className="btn-secondary" onClick={() => setEditing(true)} type="button">
          {isConfigured ? "Edit" : "Configure"}
        </button>
      )}

      {editing && config.authType === "oauth" && (
        <div className="space-y-2">
          <button className="btn-secondary" disabled type="button">
            Connect with {config.name}
          </button>
          <p className="text-sm text-slate-500">Coming soon</p>
          <button className="btn-secondary" onClick={cancel} type="button">
            Cancel
          </button>
        </div>
      )}

      {editing && config.authType === "webhook" && (
        <div className="space-y-4">
          {isConfigured && (
            <p className="text-sm text-slate-500">Enter a new value to replace the existing one.</p>
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
                    type={isVisible ? "text" : "password"}
                    value={fieldValues[field.key] || ""}
                  />
                  <button
                    aria-label={`Show/hide ${field.label}`}
                    className="btn-secondary"
                    onClick={() =>
                      setShowValues((current) => ({ ...current, [field.key]: !current[field.key] }))
                    }
                    type="button"
                  >
                    {isVisible ? "Hide" : "Show"}
                  </button>
                </div>
                {validationErrors[field.key] && (
                  <p className="text-sm text-red-700">{validationErrors[field.key]}</p>
                )}
              </div>
            );
          })}

          {mutation.isError && (
            <p className="text-sm text-red-700">Failed to save. Check the value and try again.</p>
          )}

          <div className="flex gap-2">
            <button className="btn-secondary" disabled={mutation.isPending} onClick={cancel} type="button">
              Cancel
            </button>
            <button className="btn-primary" disabled={mutation.isPending} onClick={save} type="button">
              {isConfigured ? "Save" : "Connect"}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
