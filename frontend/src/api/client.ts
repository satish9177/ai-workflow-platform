import axios, { AxiosError } from "axios";

import type { LlmProvider, LlmProviderModels } from "../types/api";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

type FastApiValidationError = {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
};

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<FastApiValidationError>;
    if (!axiosError.response) {
      return "Network error. Please check the API connection.";
    }

    const detail = axiosError.response.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg || "Validation error").join(", ");
    }
    return axiosError.message || "Request failed.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong.";
}

export async function fetchProviders(): Promise<LlmProvider[]> {
  return (await api.get<LlmProvider[]>("/api/v1/llm/providers")).data;
}

export async function fetchProviderModels(providerId: string): Promise<LlmProviderModels> {
  return (await api.get<LlmProviderModels>(`/api/v1/llm/providers/${providerId}/models`)).data;
}
