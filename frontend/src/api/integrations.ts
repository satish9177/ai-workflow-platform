import { api } from "./client";

export interface IntegrationStatus {
  name: string;
  is_enabled: boolean;
  has_credentials: boolean;
}

export interface SaveIntegrationPayload {
  name: string;
  credentials: Record<string, string>;
}

export async function fetchIntegrations(): Promise<IntegrationStatus[]> {
  return (await api.get<IntegrationStatus[]>("/api/v1/integrations")).data;
}

export async function saveIntegration(payload: SaveIntegrationPayload): Promise<IntegrationStatus> {
  return (
    await api.put<IntegrationStatus>(`/api/v1/integrations/${payload.name}`, {
      credentials: payload.credentials,
      config: {},
    })
  ).data;
}
