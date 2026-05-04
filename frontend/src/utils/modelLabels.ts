/* modelLabels.ts — human-readable display names for pipeline models */

export const MODEL_LABELS: Record<string, string> = {
  "en_core_web_trf": "en_core_web_trf (Transformer)",
  "en_core_web_lg": "en_core_web_lg (Large vectors)",
  "en_core_web_sm": "en_core_web_sm (Small)",
  "llama3": "Llama 3 (8B)",
  "mistral": "Mistral (7B)",
  "sciphi/triplex": "Triplex (3.8B, KG fine-tuned)",
};

export function getModelLabel(model: string): string {
  return MODEL_LABELS[model] ?? model;
}
