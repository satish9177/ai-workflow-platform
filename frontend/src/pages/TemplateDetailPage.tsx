import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { fetchIntegrations } from "../api/integrations";
import { getMissingPlaceholders, hydrate } from "../templates/hydrate";
import { TEMPLATES } from "../templates";

export default function TemplateDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const template = TEMPLATES.find((item) => item.id === id);
  const [values, setValues] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data: integrations } = useQuery({
    queryKey: ["integrations"],
    queryFn: () => fetchIntegrations(),
  });
  const configured = new Set(integrations?.filter((item) => item.credentials_set).map((item) => item.integration_type) || []);

  if (!template) {
    return (
      <section className="space-y-4">
        <Link className="text-sm font-medium text-blue-700 hover:underline" to="/templates">
          Back to templates
        </Link>
        <div className="card">Template not found</div>
      </section>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!template) {
      return;
    }

    const missing = getMissingPlaceholders(template, values);
    const nextErrors = Object.fromEntries(missing.map((key) => [key, "This field is required"]));
    setFieldErrors(nextErrors);
    setSubmitError("");
    if (missing.length > 0) {
      return;
    }

    setIsSubmitting(true);
    try {
      const workflow = hydrate(template.workflow_definition, values);
      await api.post("/api/v1/workflows/", workflow);
      navigate("/workflows");
    } catch {
      setSubmitError("Failed to create workflow. Check the values and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="space-y-4">
      <Link className="text-sm font-medium text-blue-700 hover:underline" to="/templates">
        Back to templates
      </Link>

      <div>
        <h2 className="text-2xl font-semibold">{template.name}</h2>
        <p className="text-sm text-slate-500">{template.description}</p>
      </div>

      <div className="card space-y-3">
        <h3 className="text-lg font-semibold">Integration status</h3>
        <div className="flex flex-wrap gap-2">
          {template.required_integrations.map((integration) =>
            configured.has(integration) ? (
              <span className="rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-700" key={integration}>
                ✓ {integration}
              </span>
            ) : (
              <Link
                className="rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800 hover:underline"
                key={integration}
                to="/integrations"
              >
                {integration} — Configure →
              </Link>
            ),
          )}
        </div>
      </div>

      <form className="card space-y-4" onSubmit={submit}>
        {template.placeholders.map((placeholder) => (
          <div className="space-y-1" key={placeholder.key}>
            <label className="text-sm font-medium text-slate-700" htmlFor={placeholder.key}>
              {placeholder.label}
              {placeholder.required && <span className="text-red-700"> *</span>}
            </label>
            {placeholder.type === "textarea" ? (
              <textarea
                className="input min-h-28"
                id={placeholder.key}
                onChange={(event) => {
                  setValues((current) => ({ ...current, [placeholder.key]: event.target.value }));
                  setFieldErrors((current) => ({ ...current, [placeholder.key]: "" }));
                }}
                value={values[placeholder.key] || ""}
              />
            ) : (
              <input
                className="input"
                id={placeholder.key}
                onChange={(event) => {
                  setValues((current) => ({ ...current, [placeholder.key]: event.target.value }));
                  setFieldErrors((current) => ({ ...current, [placeholder.key]: "" }));
                }}
                type={placeholder.type}
                value={values[placeholder.key] || ""}
              />
            )}
            {placeholder.hint && <p className="text-sm text-slate-500">{placeholder.hint}</p>}
            {fieldErrors[placeholder.key] && <p className="text-sm text-red-700">{fieldErrors[placeholder.key]}</p>}
          </div>
        ))}

        {submitError && <p className="text-sm text-red-700">{submitError}</p>}

        <button className="btn-primary" disabled={isSubmitting} type="submit">
          Create Workflow
        </button>
      </form>
    </section>
  );
}
