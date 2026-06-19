export const MODEL_LABELS: Record<string, string> = {
  "en_core_web_trf": "spaCy Transformer",
  "Qwen/Qwen3-1.7B": "Qwen3-1.7B (Pipeline B)",
};

export const MODEL_DESCRIPTIONS: Record<string, string> = {
  "en_core_web_trf": "RoBERTa-based NER - highest accuracy",
  "Qwen/Qwen3-1.7B": "Qwen3 1.7B — spaCy-llm pipeline for temporal fact extraction",
};

export function getModelLabel(model: string): string {
  return MODEL_LABELS[model] ?? model;
}

export function getModelDescription(model: string): string {
  return MODEL_DESCRIPTIONS[model] ?? "";
}
