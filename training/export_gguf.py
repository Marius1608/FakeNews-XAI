"""
Merge LoRA adapter with the base model and export to GGUF Q4_K_M format.

The resulting .gguf file can be registered directly in Ollama via register_ollama.sh
or register_ollama.ps1.

Usage:
    python training/export_gguf.py
    python training/export_gguf.py --adapter-dir training/output/fakenews-ner-lora
    python training/export_gguf.py --output training/output/fakenews-ner.gguf
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_ADAPTER_DIR = Path(__file__).parent / "output" / "fakenews-ner-lora"
DEFAULT_OUTPUT = Path(__file__).parent / "output" / "fakenews-ner.gguf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge LoRA adapter and export to GGUF for Ollama"
    )
    parser.add_argument(
        "--adapter-dir",
        type=Path,
        default=DEFAULT_ADAPTER_DIR,
        help="Directory containing the saved LoRA adapter (output of train_qlora.py)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the exported .gguf file",
    )
    parser.add_argument(
        "--quantization",
        default="q4_k_m",
        choices=["q4_k_m", "q8_0", "f16"],
        help="GGUF quantization type (q4_k_m recommended for 8 GB VRAM inference)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.adapter_dir.exists():
        raise FileNotFoundError(
            f"Adapter directory not found: {args.adapter_dir}\n"
            "Run train_qlora.py first."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading adapter from : {args.adapter_dir}")
    logger.info(f"Output GGUF path     : {args.output}")
    logger.info(f"Quantization         : {args.quantization}")

    from unsloth import FastLanguageModel

    # Reload the adapter (unsloth re-attaches it to the base model automatically)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.adapter_dir),
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    logger.info("Merging adapter weights into base model...")

    # save_pretrained_gguf merges, quantizes, and writes the .gguf in one step
    model.save_pretrained_gguf(
        str(args.output.with_suffix("")),
        tokenizer,
        quantization_method=args.quantization,
    )

    # unsloth appends the quantization suffix; rename to the clean target path
    candidate = args.output.parent / f"{args.output.stem}-{args.quantization}.gguf"
    if candidate.exists() and candidate != args.output:
        candidate.rename(args.output)
        logger.info(f"Renamed {candidate.name} -> {args.output.name}")

    logger.info(f"Export complete: {args.output}")
    logger.info("Next step: run register_ollama.sh (or .ps1) to load into Ollama")


if __name__ == "__main__":
    main()
