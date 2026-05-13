import { useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchIntegrations } from "../api/integrations";
import IntegrationCard from "../components/integrations/IntegrationCard";
import { KNOWN_INTEGRATIONS } from "../components/integrations/knownIntegrations";

export default function Integrations() {
  const queryClient = useQueryClient();
  const { data, error, isLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: () => fetchIntegrations(),
  });

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Integrations</h2>
        <p className="text-sm text-slate-500">Configure external services used in your workflows.</p>
      </div>

      {isLoading && <div className="card">Loading...</div>}
      {error && <div className="card text-sm text-red-700">Failed to load integrations.</div>}

      {!isLoading && !error && (
        <div className="grid gap-4">
          {KNOWN_INTEGRATIONS.map((config) => (
            <IntegrationCard
              config={config}
              integrations={(data || []).filter((item) => item.id && item.integration_type === config.id)}
              key={config.id}
              onSaveSuccess={() => queryClient.invalidateQueries({ queryKey: ["integrations"] })}
            />
          ))}
        </div>
      )}
    </section>
  );
}
