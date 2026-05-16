"""PolitiFact TCS Evaluation Script.

Downloads fact-check articles from PolitiFact using links from the local JSON dataset,
runs the TCS pipeline on each article, and compares the result against the original verdict.

Verdict binarization:
  TRUE : true, mostly-true, half-true
  FAKE : barely-true, false, pants-fire

Usage:
    python evaluation/run_politifact_eval.py --n 50
    python evaluation/run_politifact_eval.py --n 100 --offset 50
    python evaluation/run_politifact_eval.py --n 50 --pipeline llm
    python evaluation/run_politifact_eval.py --load-cache    # rerun TCS without re-downloading

Output:
    data/datasets/polifact/politifact_articles_{offset}_{end}.json  -- downloaded articles cache
    evaluation/results/politifact_eval_YYYY-MM-DD.json              -- metrics
    evaluation/figures/politifact_tcs_YYYY-MM-DD.png                -- boxplot
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

# add project root to path so backend imports work
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("politifact_eval")

# section: paths
POLITIFACT_JSON = _PROJECT_ROOT / "data" / "datasets" / "polifact" / "politifact_factcheck_data.json"
ARTICLES_DIR    = _PROJECT_ROOT / "data" / "datasets" / "polifact"
RESULTS_DIR     = _PROJECT_ROOT / "evaluation" / "results"
FIGURES_DIR     = _PROJECT_ROOT / "evaluation" / "figures"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# section: constants

# verdict → binary label
# true / mostly-true / half-true → TRUE (credible, partially correct)
# barely-true / false / pants-fire → FAKE (misleading or false)
VERDICT_TO_BINARY: dict[str, str] = {
    "true":          "TRUE",
    "mostly-true":   "TRUE",
    "half-true":     "TRUE",
    "barely-true":   "FAKE",
    "false":         "FAKE",
    "pants-fire":    "FAKE",
    "pants on fire": "FAKE",
}

# threshold below which an article is classified FAKE
FAKE_THRESHOLD = 0.55

# HTTP headers to avoid being blocked by PolitiFact
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ordered verdict categories for display
VERDICT_ORDER = ["true", "mostly-true", "half-true", "barely-true", "false", "pants-fire"]


# section: article download

def _extract_article_text(html: str) -> str:
    """Extract the main fact-check article body from PolitiFact HTML.

    Tries multiple CSS selectors in order of specificity.
    Falls back to collecting all paragraph tags if none match.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("BeautifulSoup not installed. Run: pip install beautifulsoup4")
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # try known PolitiFact content selectors
    for selector in [
        "article.m-textblock",
        "div.m-textblock",
        "div.article__text",
        "div.story-text",
        "div[class*='article']",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    # fallback: collect all non-trivial paragraphs
    paragraphs = soup.find_all("p")
    text = " ".join(
        p.get_text(strip=True)
        for p in paragraphs
        if len(p.get_text(strip=True)) > 50
    )
    return text


def download_article(url: str, timeout: int = 15) -> str | None:
    """Download and extract text from a PolitiFact fact-check page.

    Returns None if the request fails or the extracted text is too short.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        text = _extract_article_text(resp.text)
        if len(text) < 100:
            logger.warning(f"Text too short ({len(text)} chars): {url}")
            return None
        return text
    except requests.RequestException as e:
        logger.warning(f"Download error for {url}: {e}")
        return None


# section: data loading

def load_politifact_records(path: Path, n: int, offset: int = 0) -> list[dict]:
    """Load N records from the PolitiFact JSONL file, starting at offset.

    Skips records with unknown verdicts (not in VERDICT_TO_BINARY).
    """
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            if i < offset:
                continue
            if len(records) >= n:
                break
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            verdict_raw = rec.get("verdict", "").lower().strip()
            binary = VERDICT_TO_BINARY.get(verdict_raw)
            if binary is None:
                continue  # skip unknown verdict categories

            rec["verdict_binary"] = binary
            rec["verdict_raw"]    = verdict_raw
            records.append(rec)

    return records


# section: tcs pipeline

def run_tcs(
    text: str,
    title: str,
    pub_date: str | None,
    pipeline: str,
    use_wikidata: bool,
    use_web_search: bool = False,
) -> dict:
    """Run the TCS pipeline on a single article and return a result dict.

    Imports are deferred so the script can be imported without loading models.
    """
    import spacy
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.graph.models import Article

    # resolve spacy model — same logic as run_evaluation.py
    model_name = None
    if pipeline == "spacy":
        installed = spacy.util.get_installed_models()
        for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
            if preferred in installed:
                model_name = preferred
                break
        if model_name is None and installed:
            model_name = installed[0]

    orch = PipelineOrchestrator(
        use_wikidata=use_wikidata,
        use_web_search=use_web_search,
        extractor_name=pipeline,
        model_name=model_name,
        persistent_store=None,
    )

    # parse publication_date string to datetime (Article expects Optional[datetime])
    parsed_date = None
    if pub_date:
        try:
            from dateparser import parse as dp_parse
            parsed_date = dp_parse(pub_date, settings={"RETURN_AS_TIMEZONE_AWARE": False})
        except Exception:
            parsed_date = None

    article = Article(
        text=text,
        title=title or "PolitiFact Article",
        source="politifact",
        publication_date=parsed_date,
    )

    result = orch.run(article)

    return {
        "tcs":                 round(result.score, 4),
        "label":               result.label,
        "n_facts":             result.n_temporal_claims,
        "n_inconsistencies":   result.n_inconsistencies,
        "inconsistency_types": [i.inconsistency_type.value for i in result.inconsistencies],
    }


# section: main

def main(args: argparse.Namespace) -> None:
    pipeline     = args.pipeline
    n            = args.n
    offset       = args.offset
    use_wikidata   = not args.no_wikidata
    use_web_search = args.web_search
    load_cache     = args.load_cache
    delay          = args.delay

    cache_path = ARTICLES_DIR / f"politifact_articles_{offset}_{offset + n}.json"

    print("\n" + "=" * 70)
    print("  POLITIFACT TCS EVALUATION")
    print(f"  Pipeline  : {pipeline}")
    print(f"  Articles  : {n} (offset={offset})")
    print(f"  Wikidata  : {use_wikidata}")
    print(f"  Web Search: {use_web_search}")
    print(f"  Threshold : {FAKE_THRESHOLD}")
    print(f"  Cache     : {cache_path.name}")
    print("=" * 70 + "\n")

    # section: step 1 - download or load cache
    if load_cache and cache_path.exists():
        logger.info(f"Loading from cache: {cache_path}")
        with open(cache_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        logger.info(f"{len(articles)} articles loaded from cache.")
    else:
        logger.info(f"Loading metadata from {POLITIFACT_JSON.name}...")
        records = load_politifact_records(POLITIFACT_JSON, n=n, offset=offset)
        logger.info(f"{len(records)} records loaded.")

        articles: list[dict] = []
        for i, rec in enumerate(records, 1):
            url   = rec.get("factcheck_analysis_link", "")
            title = rec.get("statement", "")[:80]
            pub   = rec.get("statement_date", "")

            logger.info(f"[{i:3}/{len(records)}] Downloading: {url[:65]}...")
            text = download_article(url)

            articles.append({
                "idx":            i + offset,
                "verdict_raw":    rec["verdict_raw"],
                "verdict_binary": rec["verdict_binary"],
                "statement":      rec.get("statement", ""),
                "statement_date": pub,
                "originator":     rec.get("statement_originator", ""),
                "url":            url,
                "article_text":   text,
                "download_ok":    text is not None,
            })

            if text:
                logger.info(f"  -> {len(text)} chars downloaded")
            else:
                logger.warning(f"  -> download failed, will skip")

            if delay > 0:
                time.sleep(delay)

        # save cache so reruns skip downloading
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        logger.info(f"Cache saved: {cache_path}")

    # section: step 2 - run tcs
    print("\n" + "=" * 70)
    print("  RUNNING TCS PIPELINE")
    print("=" * 70)

    results: list[dict] = []
    skipped = 0

    for art in articles:
        if not art.get("download_ok") or not art.get("article_text"):
            logger.warning(f"[{art['idx']}] Skip — no text available")
            skipped += 1
            continue

        try:
            tcs_result = run_tcs(
                text=art["article_text"],
                title=art["statement"][:80],
                pub_date=art.get("statement_date"),
                pipeline=pipeline,
                use_wikidata=use_wikidata,
                use_web_search=use_web_search,
            )
        except Exception as e:
            logger.error(f"[{art['idx']}] TCS error: {e}")
            skipped += 1
            continue

        predicted = "FAKE" if tcs_result["tcs"] < FAKE_THRESHOLD else "TRUE"
        expected  = art["verdict_binary"]
        outcome   = (
            "TP" if predicted == "FAKE" and expected == "FAKE" else
            "TN" if predicted == "TRUE" and expected == "TRUE" else
            "FP" if predicted == "FAKE" and expected == "TRUE" else
            "FN"
        )

        row = {**art, **tcs_result, "predicted": predicted, "outcome": outcome}
        results.append(row)

        mark = "" if outcome in ("TP", "TN") else "* "
        print(
            f"  {mark}[{art['idx']:3}] {art['originator'][:22]:<22} "
            f"TCS={tcs_result['tcs']:.3f}  "
            f"exp={expected:<4}  pred={predicted:<4}  {outcome}  "
            f"facts={tcs_result['n_facts']}  inc={tcs_result['n_inconsistencies']}"
        )

    # section: step 3 - metrics
    print("\n" + "=" * 70)
    print("  METRICS")
    print("=" * 70)

    tp    = sum(1 for r in results if r["outcome"] == "TP")
    tn    = sum(1 for r in results if r["outcome"] == "TN")
    fp    = sum(1 for r in results if r["outcome"] == "FP")
    fn    = sum(1 for r in results if r["outcome"] == "FN")
    total = len(results)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / total if total > 0 else 0.0

    true_scores = [r["tcs"] for r in results if r["verdict_binary"] == "TRUE"]
    fake_scores = [r["tcs"] for r in results if r["verdict_binary"] == "FAKE"]
    avg_true    = sum(true_scores) / len(true_scores) if true_scores else 0.0
    avg_fake    = sum(fake_scores) / len(fake_scores) if fake_scores else 0.0

    # tcs per verdict category
    by_verdict: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_verdict[r["verdict_raw"]].append(r["tcs"])

    print(f"\n  Total evaluated : {total}  (skipped={skipped})")
    print(f"  TP={tp}  TN={tn}  FP={fp}  FN={fn}")
    print(f"  Precision : {precision:.4f}")
    print(f"  Recall    : {recall:.4f}")
    print(f"  F1        : {f1:.4f}")
    print(f"  Accuracy  : {accuracy:.4f}")
    print(f"  Avg TCS (TRUE) : {avg_true:.4f}")
    print(f"  Avg TCS (FAKE) : {avg_fake:.4f}")
    print(f"  Separation     : {avg_true - avg_fake:.4f}")

    print(f"\n  TCS per verdict category:")
    print(f"  {'Label':<15} {'N':>4}   {'Avg TCS':>8}   {'Min':>6}   {'Max':>6}")
    print(f"  {'-'*48}")
    for verdict in VERDICT_ORDER:
        vals = by_verdict.get(verdict, [])
        if not vals:
            continue
        print(
            f"  {verdict:<15} {len(vals):>4}   "
            f"{sum(vals)/len(vals):>8.4f}   "
            f"{min(vals):>6.3f}   "
            f"{max(vals):>6.3f}"
        )

    # section: step 4 - save results
    date_str    = datetime.now().strftime("%Y-%m-%d")
    result_path = RESULTS_DIR / f"politifact_eval_{date_str}.json"

    output = {
        "generated_at": datetime.now().isoformat(),
        "pipeline":     pipeline,
        "threshold":    FAKE_THRESHOLD,
        "use_wikidata": use_wikidata,
        "n_articles":   total,
        "n_skipped":    skipped,
        "metrics": {
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
            "accuracy":  round(accuracy, 4),
            "avg_tcs_true": round(avg_true, 4),
            "avg_tcs_fake": round(avg_fake, 4),
            "separation":   round(avg_true - avg_fake, 4),
        },
        "by_verdict": {
            k: {
                "n":   len(v),
                "avg": round(sum(v) / len(v), 4),
                "min": round(min(v), 4),
                "max": round(max(v), 4),
            }
            for k, v in by_verdict.items()
        },
        "articles": results,
    }

    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"Results saved: {result_path}")

    # section: step 5 - boxplot
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # left: TRUE vs FAKE distribution
        ax1 = axes[0]
        bp1 = ax1.boxplot(
            [true_scores, fake_scores],
            labels=["TRUE", "FAKE"],
            patch_artist=True,
        )
        bp1["boxes"][0].set_facecolor("#4CAF50")
        bp1["boxes"][1].set_facecolor("#F44336")
        ax1.axhline(y=FAKE_THRESHOLD, color="orange", linestyle="--",
                    label=f"Threshold={FAKE_THRESHOLD}")
        ax1.set_title("TCS Distribution: TRUE vs FAKE\n(PolitiFact articles)")
        ax1.set_ylabel("TCS Score")
        ax1.set_ylim(0, 1.05)
        ax1.legend()

        # right: per verdict category
        ax2 = axes[1]
        cat_data   = [by_verdict.get(v, [0.5]) for v in VERDICT_ORDER]
        cat_labels = ["true", "mostly\ntrue", "half\ntrue", "barely\ntrue", "false", "pants\nfire"]
        colors     = ["#4CAF50", "#8BC34A", "#FFC107", "#FF9800", "#F44336", "#B71C1C"]
        bp2 = ax2.boxplot(cat_data, labels=cat_labels, patch_artist=True)
        for patch, color in zip(bp2["boxes"], colors):
            patch.set_facecolor(color)
        ax2.axhline(y=FAKE_THRESHOLD, color="orange", linestyle="--",
                    label=f"Threshold={FAKE_THRESHOLD}")
        ax2.set_title("TCS per PolitiFact Verdict Category")
        ax2.set_ylabel("TCS Score")
        ax2.set_ylim(0, 1.05)
        ax2.legend()

        plt.tight_layout()
        fig_path = FIGURES_DIR / f"politifact_tcs_{date_str}.png"
        plt.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info(f"Boxplot saved: {fig_path}")

    except ImportError:
        logger.warning("matplotlib not installed — skipping boxplot")

    print("\n" + "=" * 70)
    print("  DONE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolitiFact TCS Evaluation")
    parser.add_argument("--n",           type=int,   default=50,
                        help="Number of articles to evaluate (default: 50)")
    parser.add_argument("--offset",      type=int,   default=0,
                        help="Offset in the JSONL file (default: 0)")
    parser.add_argument("--pipeline",    type=str,   default="spacy",
                        choices=["spacy", "llm"],
                        help="Extraction pipeline (default: spacy)")
    parser.add_argument("--no-wikidata", action="store_true",
                        help="Disable Wikidata external verification")
    parser.add_argument("--load-cache",  action="store_true",
                        help="Reuse previously downloaded articles (skip download step)")
    parser.add_argument("--delay",       type=float, default=1.5,
                        help="Delay between HTTP requests in seconds (default: 1.5)")
    parser.add_argument("--web-search",  action="store_true",
                        help="Enable Wikipedia web search fallback in C3b")
    args = parser.parse_args()
    main(args)