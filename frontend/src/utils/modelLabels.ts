export const MODEL_LABELS: Record<string, string> = {
  "en_core_web_trf": "spaCy Transformer",
  "Qwen/Qwen3-1.7B": "Qwen3 1.7B",
};

export const MODEL_DESCRIPTIONS: Record<string, string> = {
  "en_core_web_trf": "RoBERTa-based NER — Pipeline A (deterministic)",
  "Qwen/Qwen3-1.7B": "Local LLM — Pipeline B (temporal fact extraction)",
};

export function getModelLabel(model: string): string {
  return MODEL_LABELS[model] ?? model;
}

export function getModelDescription(model: string): string {
  return MODEL_DESCRIPTIONS[model] ?? "";
}