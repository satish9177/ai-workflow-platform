import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchProviderModels, fetchProviders } from "../api/client";

export default function Providers() {
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);

  const {
    data: providers,
    error: providersError,
    isLoading: providersLoading,
  } = useQuery({
    queryKey: ["providers"],
    queryFn: fetchProviders,
  });

  const selectedProviderName = providers?.find((provider) => provider.id === selectedProvider)?.name;

  const {
    data: models,
    error: modelsError,
    isLoading: modelsLoading,
  } = useQuery({
    queryKey: ["provider-models", selectedProvider],
    queryFn: () => fetchProviderModels(selectedProvider!),
    enabled: selectedProvider !== null,
  });

  function toggleProvider(providerId: string) {
    setSelectedProvider((current) => (current === providerId ? null : providerId));
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">LLM Providers</h2>
        <p className="text-sm text-slate-500">Browse registered LLM providers and their available models.</p>
      </div>

      {providersLoading && <div className="card">Loading providers...</div>}
      {providersError && <div className="card text-sm text-red-700">Failed to load providers.</div>}

      {!providersLoading && !providersError && (
        <div className="card space-y-5">
          <div className="flex flex-wrap gap-3">
            {providers?.map((provider) => {
              const isSelected = selectedProvider === provider.id;
              return (
                <button
                  className={`rounded-lg border bg-white p-4 text-left ${
                    isSelected ? "border-blue-500" : "border-slate-200 hover:border-slate-300"
                  }`}
                  key={provider.id}
                  onClick={() => toggleProvider(provider.id)}
                  type="button"
                >
                  <p className="text-base font-semibold">{provider.name}</p>
                  <p className="text-sm text-slate-500">{provider.id}</p>
                </button>
              );
            })}
          </div>

          {selectedProvider ? (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">Models - {selectedProviderName || selectedProvider}</h3>
              {modelsLoading && <p className="text-sm text-slate-600">Loading models...</p>}
              {modelsError && <p className="text-sm text-red-700">Failed to load models.</p>}
              {models && (
                <ul className="rounded-md border border-slate-200">
                  {models.models.map((model) => (
                    <li className="border-b border-slate-100 px-4 py-3 text-sm last:border-b-0" key={model}>
                      {model}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-600">Select a provider to see available models.</p>
          )}
        </div>
      )}
    </section>
  );
}
