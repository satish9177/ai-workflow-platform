import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { fetchIntegrations } from "../api/integrations";
import { TEMPLATES } from "../templates";

export default function TemplatesPage() {
  const navigate = useNavigate();
  const { data, error, isLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: fetchIntegrations,
  });
  const configured = new Set(data?.filter((item) => item.has_credentials).map((item) => item.name) || []);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Templates</h2>
        <p className="text-sm text-slate-500">Create common workflows from a guided starting point.</p>
      </div>

      {isLoading && <div className="card">Loading...</div>}
      {error && <div className="card text-sm text-red-700">Failed to load integrations.</div>}

      {!isLoading && !error && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {TEMPLATES.map((template) => (
            <article className="card flex flex-col gap-4" key={template.id}>
              <div className="space-y-2">
                <h3 className="text-lg font-semibold">{template.name}</h3>
                <p className="text-sm text-slate-500">{template.description}</p>
              </div>

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

              <button className="btn-primary mt-auto" onClick={() => navigate(`/templates/${template.id}`)} type="button">
                Use template
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
