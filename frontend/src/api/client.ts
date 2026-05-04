/* client.ts — Axios instance and typed API functions */

import axios from "axios";
import type { AnalyzeRequest, AnalyzeResponse, CompareRequest, CompareResponse, HealthResponse, ModelsResponse } from "../types";

// axios instance
const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL ?? "http://localhost:8000",
  timeout: 120_000,
  headers: {
    "Content-Type": "application/json",
  },
});

// typed API functions
export async function analyzeArticle(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  const { data } = await apiClient.post<AnalyzeResponse>("/analyze", req);
  return data;
}

export async function comparePipelines(req: CompareRequest): Promise<CompareResponse> {
  const { data } = await apiClient.post<CompareResponse>("/compare", req);
  return data;
}

export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/health");
  return data;
}

export async function getModels(): Promise<ModelsResponse> {
  const { data } = await apiClient.get<ModelsResponse>("/models");
  return data;
}

export default apiClient;
