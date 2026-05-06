# Fine-Tuning: fakenews-ner

QLoRA fine-tuning pipeline for the `fakenews-ner` model — a Mistral-7B variant
specialized for temporal fact extraction from political news articles.

The fine-tuned model is exported to GGUF and loaded into Ollama as `fakenews-ner`,
where it replaces zero-shot inference with task-specific extraction.

## Prerequisites

**Hardware:** CUDA-capable GPU with at least 8 GB VRAM (developed on RTX 4060 Laptop).

**Software:**
- Python 3.11
- CUDA 12.1+ with matching PyTorch
- Ollama (for the final registration step)

**Install training dependencies** (separate from the main backend requirements):

```bash
pip install -r training/requirements.txt
```

unsloth must be installed with the correct CUDA index. If the above fails, follow
the manual install at https://docs.unsloth.ai/get-started/installation.

## Steps

### 1 — Prepare dataset (~5 minutes)

Runs `SpacyExtractor(en_core_web_trf)` on each article to produce silver-label
temporal facts, then formats them as instruction/input/output triplets.

```bash
# Default: reads data/datasets/liar/, writes training/data/
python training/prepare_dataset.py

# Custom article directory (.txt files)
python training/prepare_dataset.py --input-dir path/to/articles/ --max-articles 300
```

**Input format:** either LIAR-style `.tsv` files (id, label, statement, ...) or
plain `.txt` files, one article per file.

**Output:** `training/data/train.jsonl` (80%) and `training/data/eval.jsonl` (20%).

Articles where spaCy extracts zero temporal facts are skipped — they provide no
training signal. Expect 100–150 usable examples from 200 articles.

### 2 — Train (~1–2 hours on RTX 4060)

```bash
python training/train_qlora.py
```

LoRA configuration: r=16, alpha=32, target modules q/k/v/o projections.
Batch size 1 with 4 gradient accumulation steps (effective batch = 4).
Adapter weights are saved to `training/output/fakenews-ner-lora/`.

Optional overrides:

```bash
python training/train_qlora.py --epochs 5 --lr 1e-4
python training/train_qlora.py --base-model unsloth/llama-3-8b-Instruct-bnb-4bit
```

### 3 — Export to GGUF (~10 minutes)

Merges the LoRA adapter into the base model and quantizes to Q4_K_M.

```bash
python training/export_gguf.py
```

Output: `training/output/fakenews-ner.gguf`

### 4 — Register in Ollama

```bash
# Linux / macOS / Git Bash
bash training/register_ollama.sh

# Windows PowerShell
.\training\register_ollama.ps1
```

This runs `ollama create fakenews-ner -f training/Modelfile`. The Modelfile points
to the `.gguf` file and embeds the system prompt with few-shot examples.

Verify the model is available:

```bash
ollama list
ollama run fakenews-ner "Extract temporal facts from: Obama was president from 2009 to 2017."
```

Once registered, set `LLM_MODELS=sciphi/triplex,fakenews-ner` and
`LLM_DEFAULT_MODEL=fakenews-ner` in `.env` to use it as the default LLM pipeline.

## File Overview

| File | Purpose |
|------|---------|
| `prepare_dataset.py` | Generate train/eval JSONL from articles using spaCy silver labels |
| `train_qlora.py` | QLoRA fine-tuning with unsloth + SFTTrainer |
| `export_gguf.py` | Merge adapter and export to GGUF Q4_K_M |
| `Modelfile` | Ollama model definition (FROM + SYSTEM prompt) |
| `register_ollama.sh` | Register GGUF in Ollama (Linux/macOS/Git Bash) |
| `register_ollama.ps1` | Register GGUF in Ollama (Windows PowerShell) |
| `data/` | Generated train.jsonl and eval.jsonl (git-ignored) |
| `output/` | LoRA adapter and GGUF file (git-ignored) |

## Expected VRAM Usage

| Stage | VRAM |
|-------|------|
| Prepare dataset (spaCy en_core_web_trf) | ~2 GB |
| Training (Mistral-7B 4-bit + LoRA) | ~7–7.5 GB |
| GGUF export (merge + quantize) | ~7 GB |
| Ollama inference (Q4_K_M) | ~5 GB |
