"""Baseline-uri ML (TF-IDF) pentru detectia fake news, comparate cu pipeline-ul TCS.

Antreneaza si evalueaza Logistic Regression, Random Forest si SVM linear cu
cross-validation stratificata 5-fold pe textul articolelor din benchmark.
Compara F1-ul mediu al fiecarui model cu F1=0.393 obtinut de pipeline-ul TCS.

Rulare: python evaluation/run_baseline.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
BENCHMARK_FILE = EVAL_DIR / "benchmark_articles.json"

TCS_F1 = 0.393  # F1 de referinta al pipeline-ului TCS (threshold=0.70)
N_FOLDS = 5
RANDOM_STATE = 42


# // section load

def load_dataset() -> tuple[list[str], np.ndarray]:
    """Incarca textele articolelor si etichetele expected_fake."""
    if not BENCHMARK_FILE.exists():
        print(f"Fisier benchmark negasit: {BENCHMARK_FILE}")
        sys.exit(1)
    with open(BENCHMARK_FILE, encoding="utf-8") as f:
        data = json.load(f)
    texts = [a.get("text", "") for a in data]
    labels = np.array([1 if a.get("expected_fake", False) else 0 for a in data])
    print(f"Incarcat {len(texts)} articole "
          f"({int(labels.sum())} fake / {int((labels == 0).sum())} true)")
    return texts, labels


# // section models

def build_models() -> dict[str, Pipeline]:
    """Construieste pipeline-urile TF-IDF + clasificator pentru fiecare model."""
    def vectorizer() -> TfidfVectorizer:
        return TfidfVectorizer(max_features=5000, ngram_range=(1, 2))

    return {
        "LogisticRegression": Pipeline([
            ("tfidf", vectorizer()),
            ("clf", LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)),
        ]),
        "RandomForest": Pipeline([
            ("tfidf", vectorizer()),
            ("clf", RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)),
        ]),
        "SVM-linear": Pipeline([
            ("tfidf", vectorizer()),
            ("clf", SVC(kernel="linear", C=1.0, random_state=RANDOM_STATE)),
        ]),
    }


# // section evaluate

def evaluate_model(model: Pipeline, texts: list[str], labels: np.ndarray) -> dict:
    """Cross-validation stratificata 5-fold; returneaza media +/- std pentru P/R/F1/Acc."""
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    texts_arr = np.array(texts, dtype=object)

    metrics = {"precision": [], "recall": [], "f1": [], "accuracy": []}
    for train_idx, test_idx in skf.split(texts_arr, labels):
        X_train = list(texts_arr[train_idx])
        X_test = list(texts_arr[test_idx])
        y_train, y_test = labels[train_idx], labels[test_idx]

        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics["precision"].append(precision_score(y_test, y_pred, zero_division=0))
        metrics["recall"].append(recall_score(y_test, y_pred, zero_division=0))
        metrics["f1"].append(f1_score(y_test, y_pred, zero_division=0))
        metrics["accuracy"].append(accuracy_score(y_test, y_pred))

    return {
        k: {"mean": round(float(np.mean(v)), 4), "std": round(float(np.std(v)), 4)}
        for k, v in metrics.items()
    }


# // section print

def print_results(results: dict) -> None:
    print(f"\n{'='*70}")
    print(f"  BASELINE ML  ({N_FOLDS}-fold stratified CV, TF-IDF max_features=5000)")
    print(f"{'='*70}")
    print(f"  {'Model':<20}  {'P':>13}  {'R':>13}  {'F1':>13}  {'Acc':>13}")
    print(f"  {'-'*62}")
    for name, m in results.items():
        print(f"  {name:<20}  "
              f"{m['precision']['mean']:.3f}±{m['precision']['std']:.3f}  "
              f"{m['recall']['mean']:.3f}±{m['recall']['std']:.3f}  "
              f"{m['f1']['mean']:.3f}±{m['f1']['std']:.3f}  "
              f"{m['accuracy']['mean']:.3f}±{m['accuracy']['std']:.3f}")
    print(f"  {'-'*62}")


def print_comparison(results: dict) -> None:
    print(f"\n  Comparatie cu TCS (F1={TCS_F1:.3f}):")
    beats = []
    for name, m in results.items():
        f1 = m["f1"]["mean"]
        delta = f1 - TCS_F1
        verdict = "BATE TCS" if delta > 0 else "sub TCS"
        sign = "+" if delta >= 0 else ""
        print(f"    {name:<20} F1={f1:.3f}  ({sign}{delta:.3f})  -> {verdict}")
        if delta > 0:
            beats.append((name, f1, delta))
    print()
    if beats:
        beats.sort(key=lambda t: t[1], reverse=True)
        for name, f1, delta in beats:
            print(f"  {name} bate TCS cu +{delta:.3f} F1 ({f1:.3f} vs {TCS_F1:.3f}).")
    else:
        print(f"  Niciun baseline nu depaseste TCS F1={TCS_F1:.3f}.")
    print()


# // section save

def save_results(results: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "baseline_results.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "tcs_f1_reference": TCS_F1,
        "n_folds": N_FOLDS,
        "vectorizer": {"max_features": 5000, "ngram_range": [1, 2]},
        "models": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    return output_path


# // section main

def main() -> None:
    texts, labels = load_dataset()
    models = build_models()

    results = {}
    for name, model in models.items():
        print(f"  Evaluez {name}...")
        results[name] = evaluate_model(model, texts, labels)

    print_results(results)
    print_comparison(results)

    output_path = save_results(results)
    print(f"  Rezultate salvate: {output_path}")


if __name__ == "__main__":
    main()
