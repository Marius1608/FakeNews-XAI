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


def load_liar(
    filepath: Optional[Path] = None,
    split: str = "test",
    max_articles: Optional[int] = None,
) -> list[Article]:
    """LIAR: 12.8K declaratii PolitiFact. TSV cu 14 coloane."""
    if filepath is None:
        filepath = DATASETS_DIR / "liar" / f"{split}.tsv"
    if not filepath.exists():
        logger.warning(f"Fisierul LIAR nu exista: {filepath}")
        return []

    articles = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 14:
                continue
            article = Article(
                text=row[2], title=row[2][:80], publication_date=None,
                source=f"liar-{row[4]}", label=row[1], dataset="LIAR",
            )
            articles.append(article)
            if max_articles and len(articles) >= max_articles:
                break

    logger.info(f"LIAR [{split}]: s-au incarcat {len(articles)} articole")
    return articles


def load_fakenewsnet(
    base_dir: Optional[Path] = None,
    source: str = "politifact",
    label: str = "fake",
    max_articles: Optional[int] = None,
) -> list[Article]:
    """FakeNewsNet: articole JSON cu timestamps (politifact/gossipcop, fake/real)."""
    if base_dir is None:
        base_dir = DATASETS_DIR / "fakenewsnet"
    data_dir = base_dir / source / label
    if not data_dir.exists():
        logger.warning(f"Directorul FakeNewsNet nu exista: {data_dir}")
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
            logger.debug(f"Eroare la citirea {json_file}: {e}")
            continue

        if max_articles and len(articles) >= max_articles:
            break

    logger.info(f"FakeNewsNet [{source}/{label}]: s-au incarcat {len(articles)} articole")
    return articles


def load_ver1(
    filepath: Optional[Path] = None,
    max_articles: Optional[int] = None,
) -> list[Article]:
    """VER-1 (Cheres & Groza): dezinformare Europa de Est, CSV."""
    if filepath is None:
        filepath = DATASETS_DIR / "ver1" / "ver1.csv"
    if not filepath.exists():
        logger.warning(f"Fisierul VER-1 nu exista: {filepath}")
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

    logger.info(f"VER-1: s-au incarcat {len(articles)} articole")
    return articles


def load_dataset(name: str, max_articles: Optional[int] = None, **kwargs) -> list[Article]:
    """Dispatcher: load_dataset("liar"), load_dataset("fakenewsnet", source="politifact")."""
    loaders = {"liar": load_liar, "fakenewsnet": load_fakenewsnet, "ver1": load_ver1}
    if name.lower() not in loaders:
        raise ValueError(f"Dataset necunoscut: {name}. Disponibile: {list(loaders.keys())}")
    return loaders[name.lower()](max_articles=max_articles, **kwargs)