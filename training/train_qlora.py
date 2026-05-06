"""
QLoRA fine-tuning of Mistral-7B for temporal fact extraction (fakenews-ner).

Requires unsloth and a CUDA-capable GPU. Designed for RTX 4060 Laptop (8 GB VRAM)
using 4-bit quantization. Adapter weights are saved to --output-dir and can be
merged + exported with export_gguf.py.

Usage:
    python training/train_qlora.py
    python training/train_qlora.py --epochs 5 --lr 1e-4
    python training/train_qlora.py --base-model unsloth/llama-3-8b-Instruct-bnb-4bit
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BASE_MODEL = "unsloth/mistral-7b-instruct-v0.3-bnb-4bit"
DEFAULT_DATA_DIR = Path(__file__).parent / "data"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output" / "fakenews-ner-lora"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QLoRA fine-tuning for fakenews-ner on RTX 4060 (8 GB VRAM)"
    )
    parser.add_argument(
        "--base-model",
        default=DEFAULT_BASE_MODEL,
        help="Hugging Face model ID or local path (must be 4-bit bnb quantized for 8 GB VRAM)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing train.jsonl and eval.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save LoRA adapter weights",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    return parser.parse_args()


def load_dataset(data_dir: Path):
    """Load train/eval JSONL files as Hugging Face datasets."""
    from datasets import load_dataset as hf_load_dataset

    train_path = data_dir / "train.jsonl"
    eval_path = data_dir / "eval.jsonl"

    if not train_path.exists():
        raise FileNotFoundError(
            f"Training data not found at {train_path}. "
            "Run prepare_dataset.py first."
        )

    data_files = {"train": str(train_path)}
    if eval_path.exists():
        data_files["eval"] = str(eval_path)

    dataset = hf_load_dataset("json", data_files=data_files)
    logger.info(
        f"Dataset loaded — train: {len(dataset['train'])} examples"
        + (f", eval: {len(dataset['eval'])} examples" if "eval" in dataset else "")
    )
    return dataset


def format_prompt(example: dict) -> dict:
    """Convert instruction/input/output dict to a single formatted text field.

    Uses the Mistral instruct template: [INST] system + user [/INST] assistant
    """
    prompt = (
        f"[INST] {example['instruction']}\n\n{example['input']} [/INST] "
        f"{example['output']}"
    )
    return {"text": prompt}


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Base model : {args.base_model}")
    logger.info(f"Data dir  : {args.data_dir}")
    logger.info(f"Output dir : {args.output_dir}")
    logger.info(f"Epochs     : {args.epochs}  LR: {args.lr}")

    # Lazy imports — unsloth rewrites CUDA kernels at import time
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments

    # Load 4-bit quantized base model
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=2048,
        dtype=None,       # auto-detect: float16 on Ampere+
        load_in_4bit=True,
    )
    logger.info("Base model loaded")

    # Apply LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    logger.info("LoRA adapters applied")

    dataset = load_dataset(args.data_dir)
    dataset = dataset.map(format_prompt)

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        learning_rate=args.lr,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if "eval" in dataset else "no",
        load_best_model_at_end=("eval" in dataset),
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("eval"),
        dataset_text_field="text",
        max_seq_length=2048,
        args=training_args,
    )

    logger.info("Starting training...")
    trainer.train()

    model.save_pretrained(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    logger.info(f"Adapter weights saved to {args.output_dir}")
    logger.info("Next step: run export_gguf.py to merge and export to GGUF")


if __name__ == "__main__":
    main()
