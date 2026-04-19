/* api.ts — TypeScript interfaces mirroring backend Pydantic schemas 1:1 */

//analyze schemas
export interface AnalyzeRequest {
  text: string;
  title?: string;
  publication_date?: string | null;
  source?: string;
  pipeline?: "spacy" | "llm";
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
  processing_time_ms: number;
}

//compare schemas
export interface CompareRequest {
  text: string;
  title?: string;
  publication_date?: string | null;
  source?: string;
}

export interface PipelineResult {
  pipeline: string;
  score: number;
  label: string;
  summary: string;
  n_claims: number;
  n_inconsistencies: number;
  coherence_factor: number;
  inconsistency_details: Record<string, unknown>[];
  fact_annotations: Record<string, unknown>[];
  timeline: TimelineEvent[];
  processing_time_ms: number;
}

export interface CompareResponse {
  pipeline_a: PipelineResult;
  pipeline_b: PipelineResult;
  score_delta: number;
  agreement: string;
}

//health schema
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
