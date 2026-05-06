"""
Prepare instruction-tuning dataset for fakenews-ner fine-tuning.

Uses SpacyExtractor (en_core_web_trf) as a silver-label teacher to annotate
articles, then formats each article as an instruction/input/output triplet
matching the LLMExtractor prompt schema.

Usage:
    python training/prepare_dataset.py
    python training/prepare_dataset.py --input-dir data/datasets/liar --max-articles 500
    python training/prepare_dataset.py --input-dir my_articles/ --split-ratio 0.85
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Repo root must be on sys.path so backend imports resolve
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.pipeline.extraction.llm_extractor import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
from backend.pipeline.graph.models import Article, TemporalFact


def fact_to_dict(fact: TemporalFact) -> dict:
    """Convert a TemporalFact to the JSON schema expected by the LLM."""
    time_expr = ""
    if fact.time_point:
        time_expr = fact.time_point.raw_text
    elif fact.time_start:
        time_expr = fact.time_start.raw_text

    return {
        "subject": fact.subject.text,
        "subject_type": fact.subject.entity_type.value,
        "predicate": fact.predicate.value,
        "object": fact.object.text,
        "object_type": fact.object.entity_type.value,
        "time_expression": time_expr,
        "time_start": fact.time_start.date_string if fact.time_start else None,
        "time_end": fact.time_end.date_string if fact.time_end else None,
        "time_point": fact.time_point.date_string if fact.time_point else None,
        "source_sentence": fact.source_sentence,
        "confidence": round(fact.extraction_confidence, 2),
    }


def load_articles_tsv(tsv_path: Path, max_articles: int) -> list[Article]:
    """Load articles from a LIAR-style TSV file (no header row).

    Column layout: id, label, statement, subject, speaker, job, state,
    party, counts x5, context
    """
    articles = []
    with open(tsv_path, encoding="utf-8") as f:
        for line in f:
            if len(articles) >= max_articles:
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            text = parts[2].strip()
            if not text:
                continue
            speaker = parts[4].strip() if len(parts) > 4 else ""
            articles.append(Article(text=text, title=speaker))
    return articles


def load_articles_txt(txt_dir: Path, max_articles: int) -> list[Article]:
    """Load articles from a directory of plain-text .txt files."""
    articles = []
    for p in sorted(txt_dir.glob("*.txt")):
        if len(articles) >= max_articles:
            break
        text = p.read_text(encoding="utf-8").strip()
        if text:
            articles.append(Article(text=text, title=p.stem))
    return articles


def load_articles(input_dir: Path, max_articles: int) -> list[Article]:
    """Auto-detect TSV files or .txt files in the input directory."""
    tsv_files = sorted(input_dir.glob("*.tsv")) + sorted(input_dir.glob("*.csv"))
    if tsv_files:
        logger.info(f"Found TSV file(s): {[f.name for f in tsv_files]}")
        articles: list[Article] = []
        for tsv in tsv_files:
            articles.extend(load_articles_tsv(tsv, max_articles - len(articles)))
            if len(articles) >= max_articles:
                break
        return articles

    txt_files = list(input_dir.glob("*.txt"))
    if txt_files:
        logger.info(f"Found {len(txt_files)} .txt file(s)")
        return load_articles_txt(input_dir, max_articles)

    logger.warning(f"No .tsv or .txt files found in {input_dir}")
    return []


def build_example(article: Article, facts: list[TemporalFact]) -> dict:
    """Format a single article + its silver facts as an instruction example."""
    pub_date_str = (
        article.publication_date.strftime("%Y-%m-%d")
        if article.publication_date else "unknown"
    )
    user_input = USER_PROMPT_TEMPLATE.format(
        title=article.title or "(untitled)",
        pub_date=pub_date_str,
        text=article.text[:4000],
    )
    output_json = json.dumps([fact_to_dict(f) for f in facts], ensure_ascii=False)
    return {
        "instruction": SYSTEM_PROMPT,
        "input": user_input,
        "output": output_json,
    }


def write_jsonl(examples: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    logger.info(f"Wrote {len(examples)} examples to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare instruction-tuning data for fakenews-ner"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=_REPO_ROOT / "data" / "datasets" / "liar",
        help="Directory containing .tsv or .txt article files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Directory to write train.jsonl and eval.jsonl",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=200,
        help="Maximum number of articles to process",
    )
    parser.add_argument(
        "--split-ratio",
        type=float,
        default=0.8,
        help="Fraction of examples to use for training (rest goes to eval)",
    )
    args = parser.parse_args()

    if not args.input_dir.exists():
        logger.error(f"Input directory not found: {args.input_dir}")
        logger.error("Place LIAR .tsv files in data/datasets/liar/ or pass --input-dir")
        sys.exit(1)

    logger.info(f"Loading articles from {args.input_dir}")
    articles = load_articles(args.input_dir, args.max_articles)
    if not articles:
        logger.error("No articles loaded. Exiting.")
        sys.exit(1)
    logger.info(f"Loaded {len(articles)} articles")

    logger.info("Initialising SpacyExtractor (en_core_web_trf) — loading model once...")
    extractor = SpacyExtractor(model_name="en_core_web_trf")

    # Fail fast if model can't load
    try:
        _ = extractor.nlp
    except Exception as e:
        print(f"FATAL: Cannot load spaCy model: {e}")
        print("Run: python -m spacy download en_core_web_trf")
        sys.exit(1)

    examples: list[dict] = []
    skipped = 0

    for i, article in enumerate(articles, start=1):
        try:
            facts = extractor.extract(article)
        except Exception as e:
            logger.warning(f"Article {i}: extraction error — {e}")
            skipped += 1
            continue

        if not facts:
            skipped += 1
            continue

        examples.append(build_example(article, facts))

        if i % 20 == 0:
            logger.info(f"Progress: {i}/{len(articles)} — {len(examples)} usable so far")

    logger.info(
        f"Finished: {len(examples)} usable examples, {skipped} skipped (no temporal facts)"
    )

    split = int(len(examples) * args.split_ratio)
    train_examples = examples[:split]
    eval_examples = examples[split:]

    write_jsonl(train_examples, args.output_dir / "train.jsonl")
    write_jsonl(eval_examples, args.output_dir / "eval.jsonl")

    logger.info(f"Dataset ready: {len(train_examples)} train / {len(eval_examples)} eval")


if __name__ == "__main__":
    main()
