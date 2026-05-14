"""Input — Dataset loaders pentru LIAR (TSV), FakeNewsNet (JSON), VER-1 (CSV)."""

from __future__ import annotations
from backend.pipeline.graph.models import Article
from backend.config import DATASETS_DIR

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


_LIAR2_LABEL_MAP = {
    "0": "true",
    "1": "mostly-true",
    "2": "half-true",
    "3": "barely-true",
    "4": "false",
    "5": "pants-fire",
}


def load_liar(
    filepath: Optional[Path] = None,
    split: str = "test",
    max_articles: Optional[int] = None,
) -> list[Article]:
    """LIAR / LIAR2: PolitiFact statements.

    Supports both formats:
    - LIAR original: {split}.tsv, tab-delimited, no header, 14+ columns, string labels
    - LIAR2:         {split}.csv, comma-delimited, header on row 0, numeric labels (0-5)
    Column mapping (both formats): col[1]=label, col[2]=statement, col[4]=speaker/source.
    """
    if filepath is None:
        filepath_csv = DATASETS_DIR / "liar" / f"{split}.csv"
        filepath_tsv = DATASETS_DIR / "liar" / f"{split}.tsv"
        filepath = filepath_csv if filepath_csv.exists() else filepath_tsv

    if not filepath.exists():
        logger.warning(f"LIAR file not found: {filepath}")
        return []

    delimiter = "," if filepath.suffix == ".csv" else "\t"
    logger.info(f"LIAR [{split}]: loading from {filepath.name} (delimiter={delimiter!r})")

    articles = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=delimiter)
        if filepath.suffix == ".csv":
            next(reader, None)  # LIAR2 CSV has a header row; original TSV does not
        for row in reader:
            if len(row) < 3:
                continue
            source_col = row[4] if len(row) > 4 else "unknown"
            raw_label = row[1].strip()
            label = _LIAR2_LABEL_MAP.get(raw_label, raw_label)
            article = Article(
                text=row[2], title=row[2][:80], publication_date=None,
                source=f"liar-{source_col}", label=label, dataset="LIAR",
            )
            articles.append(article)
            if max_articles and len(articles) >= max_articles:
                break

    logger.info(f"LIAR [{split}]: loaded {len(articles)} articles from {filepath.name}")
    return articles


def load_fakenewsnet(
    base_dir: Optional[Path] = None,
    source: str = "politifact",
    label: str = "fake",
    max_articles: Optional[int] = None,
) -> list[Article]:
    """FakeNewsNet: JSON articles with timestamps (politifact/gossipcop, fake/real)."""
    if base_dir is None:
        base_dir = DATASETS_DIR / "fakenewsnet"
    data_dir = base_dir / source / label
    if not data_dir.exists():
        logger.warning(f"FakeNewsNet directory not found: {data_dir}")
        return []

    articles = []
    for article_dir in sorted(data_dir.iterdir()):
        if not article_dir.is_dir():
            continue
        json_file = article_dir / "news content.json"
        if not json_file.exists():
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            pub_date = None
            if data.get("publish_date"):
                try:
                    pub_date = datetime.fromisoformat(str(data["publish_date"]))
                except (ValueError, TypeError):
                    pass

            text = data.get("text", "")
            if not text.strip():
                continue

            article = Article(
                text=text, title=data.get("title", ""), publication_date=pub_date,
                source=source, url=data.get("url", ""), label=label, dataset="FakeNewsNet",
            )
            articles.append(article)
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Error reading {json_file}: {e}")
            continue

        if max_articles and len(articles) >= max_articles:
            break

    logger.info(f"FakeNewsNet [{source}/{label}]: loaded {len(articles)} articles")
    return articles


def load_ver1(
    filepath: Optional[Path] = None,
    max_articles: Optional[int] = None,
) -> list[Article]:
    """VER-1 (Cheres & Groza): Eastern Europe disinformation, CSV."""
    if filepath is None:
        filepath = DATASETS_DIR / "ver1" / "ver1.csv"
    if not filepath.exists():
        logger.warning(f"VER-1 file not found: {filepath}")
        return []

    articles = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row.get("text", "")
            if not text.strip():
                continue
            article = Article(
                text=text, title=text[:80], publication_date=None,
                source="veridica.ro", label=row.get("label", "disinformation"),
                dataset="VER-1",
            )
            articles.append(article)
            if max_articles and len(articles) >= max_articles:
                break

    logger.info(f"VER-1: loaded {len(articles)} articles")
    return articles


def load_dataset(name: str, max_articles: Optional[int] = None, **kwargs) -> list[Article]:
    """Dispatcher: load_dataset('liar'), load_dataset('fakenewsnet', source='politifact')."""
    loaders = {"liar": load_liar, "fakenewsnet": load_fakenewsnet, "ver1": load_ver1}
    if name.lower() not in loaders:
        raise ValueError(f"Unknown dataset: {name}. Available: {list(loaders.keys())}")
    return loaders[name.lower()](max_articles=max_articles, **kwargs)
