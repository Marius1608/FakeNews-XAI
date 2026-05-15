/* client.ts — Axios instance and typed API functions */

import axios from "axios";
import type {
  AnalyzeRequest, AnalyzeResponse,
  ArticlesResponse,
  BatchRequest, BatchResponse,
  CompareRequest, CompareResponse,
  CrossArticleResponse,
  HealthResponse, ModelsResponse,
} from "../types";

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

export async function analyzeBatch(req: BatchRequest): Promise<BatchResponse> {
  const { data } = await apiClient.post<BatchResponse>("/analyze-batch", req);
  return data;
}

export async function getArticles(): Promise<ArticlesResponse> {
  const { data } = await apiClient.get<ArticlesResponse>("/articles");
  return data;
}

export async function deleteArticle(articleId: string): Promise<void> {
  await apiClient.delete(`/articles/${encodeURIComponent(articleId)}`);
}

export async function crossCheckArticle(articleId: string): Promise<CrossArticleResponse> {
  const { data } = await apiClient.get<CrossArticleResponse>("/articles/cross-check", {
    params: { article_id: articleId },
  });
  return data;
}

export interface UploadResponse {
  text: string;
  filename: string;
  file_type: string;
  char_count: number;
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<UploadResponse>("/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 30_000,
  });
  return data;
}

export default apiClient;
