/* client.ts — Axios instance and typed API functions */

import axios from "axios";
import type {
  AnalyzeRequest, AnalyzeResponse,
  ArticlesResponse,
  BatchRequest, BatchResponse,
  CompareRequest, CompareResponse,
  CrossArticleResponse,
  HealthResponse, ModelsResponse,
  ParametersResponse,
  RSSFeedsResponse,
  VerifyRequest, VerifyResponse,
} from "../types";

// Empty string → relative URLs → same origin (works on HF Spaces single-port).
// Set REACT_APP_API_URL to override (e.g. http://localhost:8000 for local dev).
const BASE_URL = process.env.REACT_APP_API_URL || "";

// axios instance
const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: {
    "Content-Type": "application/json",
  },
});

// /analyze-batch and /compare can run the LLM pipeline over many articles and
// easily exceed the default 120s — per-request timeout, the global one stays short
const LONG_RUNNING_TIMEOUT = 600_000;

// typed API functions
export async function analyzeArticle(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  const { data } = await apiClient.post<AnalyzeResponse>("/analyze", req);
  return data;
}

export async function comparePipelines(req: CompareRequest): Promise<CompareResponse> {
  const { data } = await apiClient.post<CompareResponse>("/compare", req, {
    timeout: LONG_RUNNING_TIMEOUT,
  });
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
  const { data } = await apiClient.post<BatchResponse>("/analyze-batch", req, {
    timeout: LONG_RUNNING_TIMEOUT,
  });
  return data;
}

export async function getArticles(): Promise<ArticlesResponse> {
  const { data } = await apiClient.get<ArticlesResponse>("/articles");
  return data;
}

export async function deleteArticle(articleId: string): Promise<void> {
  await apiClient.delete(`/articles/${encodeURIComponent(articleId)}`);
}

export async function verifyArticle(articleId: string, req: VerifyRequest): Promise<VerifyResponse> {
  const { data } = await apiClient.post<VerifyResponse>(
    `/articles/${encodeURIComponent(articleId)}/verify`,
    req,
  );
  return data;
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

// runtime config: RSS feeds
export async function getRssFeeds(): Promise<RSSFeedsResponse> {
  const { data } = await apiClient.get<RSSFeedsResponse>("/config/rss-feeds");
  return data;
}

export async function updatePredefinedFeeds(flags: Record<string, boolean>): Promise<RSSFeedsResponse> {
  const { data } = await apiClient.put<RSSFeedsResponse>("/config/rss-feeds/predefined", flags);
  return data;
}

export async function addCustomFeed(url: string): Promise<RSSFeedsResponse> {
  const { data } = await apiClient.post<RSSFeedsResponse>("/config/rss-feeds/custom", { url });
  return data;
}

export async function deleteCustomFeed(index: number): Promise<RSSFeedsResponse> {
  const { data } = await apiClient.delete<RSSFeedsResponse>(`/config/rss-feeds/custom/${index}`);
  return data;
}

export async function resetRssFeeds(): Promise<RSSFeedsResponse> {
  const { data } = await apiClient.post<RSSFeedsResponse>("/config/rss-feeds/reset");
  return data;
}

// runtime config: operational parameters
export async function getParameters(): Promise<ParametersResponse> {
  const { data } = await apiClient.get<ParametersResponse>("/config/parameters");
  return data;
}

export async function updateParameters(updates: Record<string, number>): Promise<ParametersResponse> {
  const { data } = await apiClient.put<ParametersResponse>("/config/parameters", updates);
  return data;
}

export async function resetParameters(): Promise<ParametersResponse> {
  const { data } = await apiClient.post<ParametersResponse>("/config/parameters/reset");
  return data;
}

export default apiClient;
