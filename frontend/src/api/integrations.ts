import { api } from "./client";

const integrationsPath = "/api/v1/integrations";

export interface IntegrationStatus {
  id: string | null;
  name: string;
  integration_type: string;
  display_name: string;
  is_enabled: boolean;
  status: string;
  last_tested_at?: string | null;
  last_error?: string | null;
  credentials_set: boolean;
  has_credentials: boolean;
}

export interface SaveIntegrationPayload {
  id?: string;
  integration_type: string;
  display_name: string;
  credentials?: Record<string, string>;
}

export interface TestIntegrationResponse {
  success: boolean;
  status: "connected" | "failed" | "unknown" | string;
  message: string;
}

export async function fetchIntegrations(type?: string): Promise<IntegrationStatus[]> {
  const params = type ? { type } : undefined;
  return (await api.get<IntegrationStatus[]>(integrationsPath, { params })).data;
}

export async function fetchIntegration(id: string): Promise<IntegrationStatus> {
  return (await api.get<IntegrationStatus>(`${integrationsPath}/${id}`)).data;
}

export async function saveIntegration(payload: SaveIntegrationPayload): Promise<IntegrationStatus> {
  if (payload.id) {
    const body: { display_name: string; credentials?: Record<string, string> } = {
      display_name: payload.display_name,
    };
    if (payload.credentials && Object.keys(payload.credentials).length > 0) {
      body.credentials = payload.credentials;
    }
    return (
      await api.patch<IntegrationStatus>(`${integrationsPath}/${payload.id}`, body)
    ).data;
  }

  return (
    await api.post<IntegrationStatus>(integrationsPath, {
      integration_type: payload.integration_type,
      display_name: payload.display_name,
      credentials: payload.credentials,
      config: {},
    })
  ).data;
}

export async function deleteIntegration(id: string): Promise<{ deleted: boolean }> {
  return (await api.delete<{ deleted: boolean }>(`${integrationsPath}/${id}`)).data;
}

export async function testIntegration(id: string): Promise<TestIntegrationResponse> {
  return (await api.post<TestIntegrationResponse>(`${integrationsPath}/${id}/test`)).data;
}
