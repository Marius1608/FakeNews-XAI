export const MODEL_LABELS: Record<string, string> = {
  "en_core_web_trf": "spaCy Transformer",
  "en_core_web_lg": "spaCy Large",
  "en_core_web_sm": "spaCy Small",
  "sciphi/triplex": "Triplex (KG extraction)",
  "fakenews-ner": "FakeNews-NER (custom)",
  "llama3": "Llama 3",
  "mistral": "Mistral",
};

export const MODEL_DESCRIPTIONS: Record<string, string> = {
  "en_core_web_trf": "RoBERTa-based NER — highest accuracy",
  "en_core_web_lg": "Word vector NER — faster, slightly less accurate",
  "en_core_web_sm": "Word vector NER — lightweight",
  "sciphi/triplex": "Specialized for Knowledge Graph triplet extraction",
  "fakenews-ner": "Custom fine-tuned for temporal political NER",
  "llama3": "General-purpose large language model",
  "mistral": "Efficient open-source language model",
};

export function getModelLabel(model: string): string {
  return MODEL_LABELS[model] ?? model;
}

export function getModelDescription(model: string): string {
  return MODEL_DESCRIPTIONS[model] ?? "";
}
