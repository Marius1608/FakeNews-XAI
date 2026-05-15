/* api.ts — TypeScript interfaces mirroring backend Pydantic schemas 1:1 */

// models schema
export interface ModelsResponse {
  spacy: { default: string; models: string[] };
  llm: { default: string; models: string[] };
}

// analyze schemas
export interface AnalyzeRequest {
  text: string;
  title?: string;
  publication_date?: string | null;
  source?: string;
  pipeline?: "spacy" | "llm";
  model?: string;
  persist?: boolean;
}

export interface InconsistencyResponse {
  type: string;
  severity: string;
  severity_label: string;
  description: string;
  evidence: string | null;
  verified_by: string;
  sentence_indices: number[];
}

export interface FactAnnotationResponse {
  sentence_idx: number;
  subject: string;
  predicate: string;
  object: string;
  time: string;
  status: string;
  color: string;
  confidence: number;
  extractor: string;
  inconsistencies: string[];
}

export interface TimelineEvent {
  year: number | null;
  label: string;
  has_inconsistency: boolean;
  inconsistency_type: string | null;
  inconsistency_description: string | null;
  inconsistency_severity: string | null;
  verified_by: string | null;
  sentence_idx: number;
  confidence: number;
  extractor: string;
}

export interface AnalyzeResponse {
  score: number;
  label: string;
  summary: string;
  n_claims: number;
  n_inconsistencies: number;
  coherence_factor: number;
  inconsistency_details: InconsistencyResponse[];
  fact_annotations: FactAnnotationResponse[];
  timeline: TimelineEvent[];
  pipeline: string;
  model: string;
  processing_time_ms: number;
  article_id?: string | null;
  cross_article_inconsistencies?: InconsistencyResponse[];
  llm_explanation?: string | null;
}

// batch schemas
export interface BatchArticle {
  text: string;
  title?: string;
  publication_date?: string;
  source?: string;
}

export interface BatchRequest {
  articles: BatchArticle[];
  pipeline: string;
  model?: string;
  persist: boolean;
  compare_with_neo4j?: boolean;
}

export interface BatchArticleResult {
  article_id: string;
  title: string;
  score: number;
  label: string;
  summary: string;
  n_claims: number;
  n_inconsistencies: number;
  n_cross_article_inconsistencies: number;
  cross_article_conflicts: InconsistencyResponse[];
  processing_time_ms: number;
  error?: string | null;
}

export interface BatchResponse {
  results: BatchArticleResult[];
  total_articles: number;
  total_cross_article_conflicts: number;
  avg_score: number;
  neo4j_enabled: boolean;
  persisted: boolean;
}

// article history schemas
export interface StoredArticle {
  article_id: string;
  title: string | null;
  source: string | null;
  analyzed_at: string | null;
  fact_count: number;
}

export interface ArticlesResponse {
  articles: StoredArticle[];
  neo4j_enabled: boolean;
}

// compare schemas
export interface CompareRequest {
  text: string;
  title?: string;
  publication_date?: string | null;
  source?: string;
  pipeline_a: string;
  model_a?: string;
  pipeline_b: string;
  model_b?: string;
}

export interface PipelineResult {
  pipeline: string;
  model: string;
  score: number;
  label: string;
  summary: string;
  n_claims: number;
  n_inconsistencies: number;
  coherence_factor: number;
  inconsistency_details: InconsistencyResponse[];
  fact_annotations: FactAnnotationResponse[];
  timeline: TimelineEvent[];
  processing_time_ms: number;
}

export interface CompareResponse {
  pipeline_a: PipelineResult;
  pipeline_b: PipelineResult;
  score_delta: number;
  agreement: string;
  model_a: string;
  model_b: string;
}

// cross-article check schemas
export interface CrossArticleConflict {
  entity: string;
  description: string;
  conflicting_article_title: string;
  conflicting_article_date: string;
}

export interface CrossArticleResponse {
  article_id: string;
  conflicts: CrossArticleConflict[];
  checked_against: number;
}

// health schema
export interface PipelineAComponent {
  model: string;
  type: "spacy";
}

export interface PipelineBComponent {
  host: string;
  model: string;
  type: "ollama";
}

export interface HealthResponse {
  status: string;
  components: {
    pipeline_a: PipelineAComponent;
    pipeline_b: PipelineBComponent;
  };
}
