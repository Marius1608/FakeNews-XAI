"""
Dataset loaders pentru LIAR, FakeNewsNet si VER-1.

Fiecare loader citeste formatul specific al datasetului
si returneaza obiecte Article pe care pipeline-ul le poate procesa.

Formatele dataseturilor:
  - LIAR: fisier TSV cu 14 coloane (statement, label, date, etc.)
  - FakeNewsNet: directoare cu fisiere JSON (PolitiFact + GossipCop)
  - VER-1: CSV cu texte de dezinformare/propaganda din Europa de Est
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.pipeline.graph.models import Article
from backend.config import DATASETS_DIR

logger = logging.getLogger(__name__)


# ─── LIAR Dataset ─────────────────────────────────────────
def load_liar(
    filepath: Optional[Path] = None,
    split: str = "test",
    max_articles: Optional[int] = None,
) -> list[Article]:
    """
    Incarca datasetul LIAR (12.8K declaratii de pe PolitiFact).

    Format TSV cu coloanele:
      0: ID
      1: label (pants-fire, false, barely-true, half-true, mostly-true, true)
      2: statement (textul declaratiei)
      3: subject
      4: speaker
      5: speaker_job
      6: state_info
      7: party
      8-12: credit history counts
      13: context (unde a fost facuta declaratia)

    Args:
        filepath: calea catre fisierul TSV. Daca None, cauta in DATASETS_DIR.
        split: "train", "valid", sau "test"
        max_articles: limita numarul de articole incarcate (util pentru testare)

    Returns:
        Lista de Article.
    """
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
                text=row[2],                    # statement
                title=row[2][:80],              # primele 80 caractere ca titlu
                publication_date=None,          # LIAR nu are date exacte
                source=f"liar-{row[4]}",        # speaker ca sursa
                label=row[1],                   # pants-fire, false, etc.
                dataset="LIAR",
            )
            articles.append(article)

            if max_articles and len(articles) >= max_articles:
                break

    logger.info(f"LIAR [{split}]: s-au incarcat {len(articles)} articole")
    return articles


# ─── FakeNewsNet Dataset ──────────────────────────────────
def load_fakenewsnet(
    base_dir: Optional[Path] = None,
    source: str = "politifact",
    label: str = "fake",
    max_articles: Optional[int] = None,
) -> list[Article]:
    """
    Incarca datasetul FakeNewsNet (articole JSON cu timestamps).

    Structura directoarelor:
      fakenewsnet/
        politifact/
          fake/
            politifact1234/
              news content.json    ← contine title, text, url, publish_date
          real/
            ...
        gossipcop/
          fake/
          real/

    Args:
        base_dir: directorul radacina FakeNewsNet. Daca None, cauta in DATASETS_DIR.
        source: "politifact" sau "gossipcop"
        label: "fake" sau "real"
        max_articles: limita numarul de articole

    Returns:
        Lista de Article.
    """
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

            # Parseaza publication date daca exista
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
                text=text,
                title=data.get("title", ""),
                publication_date=pub_date,
                source=source,
                url=data.get("url", ""),
                label=label,
                dataset="FakeNewsNet",
            )
            articles.append(article)

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Eroare la citirea {json_file}: {e}")
            continue

        if max_articles and len(articles) >= max_articles:
            break

    logger.info(
        f"FakeNewsNet [{source}/{label}]: s-au incarcat {len(articles)} articole"
    )
    return articles


# ─── VER-1 Dataset ────────────────────────────────────────
def load_ver1(
    filepath: Optional[Path] = None,
    max_articles: Optional[int] = None,
) -> list[Article]:
    """
    Incarca datasetul VER-1 (Cheres & Groza).

    VER-1 contine texte de dezinformare si propaganda de razboi
    din Europa de Est, colectate de pe Veridica.ro (2021-2025).
    Format CSV cu coloane: text, label, category.

    Args:
        filepath: calea catre fisierul CSV. Daca None, cauta in DATASETS_DIR.
        max_articles: limita numarul de articole

    Returns:
        Lista de Article.
    """
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
                text=text,
                title=text[:80],
                publication_date=None,
                source="veridica.ro",
                label=row.get("label", "disinformation"),
                dataset="VER-1",
            )
            articles.append(article)

            if max_articles and len(articles) >= max_articles:
                break

    logger.info(f"VER-1: s-au incarcat {len(articles)} articole")
    return articles


# ─── Helper: incarca orice dataset dupa nume ──────────────
def load_dataset(
    name: str,
    max_articles: Optional[int] = None,
    **kwargs,
) -> list[Article]:
    """
    Incarca un dataset dupa nume.

    Args:
        name: "liar", "fakenewsnet", sau "ver1"
        max_articles: limita numarul de articole
        **kwargs: argumente extra specifice fiecarui loader

    Returns:
        Lista de Article.

    Exemplu:
        articles = load_dataset("liar", max_articles=100)
        articles = load_dataset("fakenewsnet", source="politifact", label="fake")
    """
    loaders = {
        "liar": load_liar,
        "fakenewsnet": load_fakenewsnet,
        "ver1": load_ver1,
    }

    if name.lower() not in loaders:
        raise ValueError(
            f"Dataset necunoscut: {name}. "
            f"Disponibile: {list(loaders.keys())}"
        )

    return loaders[name.lower()](max_articles=max_articles, **kwargs)