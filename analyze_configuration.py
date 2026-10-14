#!/usr/bin/env python3
"""Steps 10-14: dimension scores, descriptive stats, Kruskal-Wallis tests, k-means.

Usage:
    python analyze_configuration.py [configuration.csv] [data/results]

Requires: pandas, numpy, scipy, scikit-learn
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kruskal
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "configuration.csv"
OUTDIR = Path(sys.argv[2] if len(sys.argv) > 2 else "data/results")
OUTDIR.mkdir(parents=True, exist_ok=True)

DIMENSIONS = [
    "access_restrictiveness",
    "content_permissiveness",
    "classification_capacity",
    "knowledge_capacity",
    "visibility_calibration",
]

# ---------------------------------------------------------------- helpers
def to_bool(v):
    """CSV string -> 1.0 / 0.0 / NaN."""
    s = str(v).strip().lower()
    if s in ("true", "1"):
        return 1.0
    if s in ("false", "0"):
        return 0.0
    return np.nan


def mean_available(parts):
    """Average of the non-NaN components; NaN if none are available."""
    vals = [p for p in parts if p is not None and not np.isnan(p)]
    return float(np.mean(vals)) if vals else np.nan


def clip01(x):
    return np.nan if np.isnan(x) else float(min(max(x, 0.0), 1.0))


SUBREDDIT_TYPE_RESTRICTIVENESS = {
    "public": 0.0, "user": 0.0,
    "restricted": 0.5, "gold_restricted": 0.5,
    "private": 1.0, "archived": 1.0, "employees_only": 1.0,
}
SUBMISSION_TYPE_PERMISSIVENESS = {"any": 1.0, "link": 0.5, "self": 0.5}
MAX_HIDE_MINS = 1440  # Reddit's upper bound for comment_score_hide_mins (24h)


def log_len_score(lengths, ref_max):
    """log(1+len) scaled by log(1+ref_max); keeps long outliers from dominating."""
    if ref_max <= 0:
        return lengths * 0.0
    return np.log1p(lengths) / np.log1p(ref_max)


# ---------------------------------------------------------------- Step 10
def compute_scores(df):
    # access_restrictiveness: higher = more locked down
    def access(r):
        t = str(r["subreddit_type"]).strip().lower()
        allow_disc = to_bool(r["allow_discovery"])
        return mean_available([
            SUBREDDIT_TYPE_RESTRICTIVENESS.get(t, np.nan),
            to_bool(r["restrict_posting"]),
            to_bool(r["restrict_commenting"]),
            to_bool(r["disable_contributor_requests"]),
            np.nan if np.isnan(allow_disc) else 1.0 - allow_disc,  # discovery off = more restrictive
            to_bool(r["quarantine"]),
        ])

    # content_permissiveness: higher = allows more kinds of content
    def content(r):
        st = str(r["submission_type"]).strip().lower()
        return mean_available([
            to_bool(r["allow_images"]),
            to_bool(r["allow_videos"]),
            to_bool(r["allow_galleries"]),
            to_bool(r["allow_videogifs"]),
            to_bool(r["allow_polls"]),
            SUBMISSION_TYPE_PERMISSIVENESS.get(st, np.nan),
            to_bool(r["over18"]),  # NSFW allowed = more permissive
        ])

    # classification_capacity: share of flair/tagging tools switched on
    def classification(r):
        return mean_available([
            to_bool(r["link_flair_enabled"]),
            to_bool(r["user_flair_enabled_in_sr"]),
            to_bool(r["can_assign_link_flair"]),
            to_bool(r["can_assign_user_flair"]),
            to_bool(r["original_content_tag_enabled"]),
            to_bool(r["spoilers_enabled"]),
        ])

    df["access_restrictiveness"] = df.apply(access, axis=1)
    df["content_permissiveness"] = df.apply(content, axis=1)
    df["classification_capacity"] = df.apply(classification, axis=1)

    # knowledge_capacity: wiki flag + log-scaled text lengths (scaled by sample max)
    submit_len = df["submit_text"].fillna("").astype(str).str.len().astype(float)
    desc_len = df["description"].fillna("").astype(str).str.len().astype(float)
    submit_score = log_len_score(submit_len, submit_len.max())
    desc_score = log_len_score(desc_len, desc_len.max())
    wiki = df["wiki_enabled"].map(to_bool)
    df["knowledge_capacity"] = pd.concat([wiki, submit_score, desc_score], axis=1).mean(axis=1, skipna=True)

    # visibility_calibration: how deliberately comment/media display is tuned
    def visibility(r):
        try:
            hide = clip01(float(r["comment_score_hide_mins"]) / MAX_HIDE_MINS)
        except (TypeError, ValueError):
            hide = np.nan
        sort = str(r["suggested_comment_sort"]).strip().lower()
        sort_set = 0.0 if sort in ("", "none", "null", "nan") else 1.0  # explicit default sort chosen?
        return mean_available([
            hide,
            to_bool(r["collapse_deleted_comments"]),
            sort_set,
            to_bool(r["show_media"]),
            to_bool(r["show_media_preview"]),
        ])

    df["visibility_calibration"] = df.apply(visibility, axis=1)
    for d in DIMENSIONS:
        df[d] = df[d].round(6)
    return df


# ---------------------------------------------------------------- Step 11
def descriptive_stats(df):
    rows = []
    for d in DIMENSIONS:
        s = df[d].dropna()
        rows.append({
            "dimension": d,
            "count": int(s.count()),
            "mean": s.mean(),
            "std": s.std(ddof=1),
            "min": s.min(),
            "q1": s.quantile(0.25),
            "median": s.median(),
            "q3": s.quantile(0.75),
            "max": s.max(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Steps 12-13
def holm(pvals):
    """Holm-Bonferroni adjusted p-values (NaN-safe)."""
    p = np.array(pvals, dtype=float)
    out = np.full_like(p, np.nan)
    idx = [i for i in np.argsort(p) if not np.isnan(p[i])]
    m = len(idx)
    running = 0.0
    for rank, i in enumerate(idx):
        running = max(running, (m - rank) * p[i])
        out[i] = min(running, 1.0)
    return out


def kruskal_by(df, group_col, exclude=()):
    sub = df[~df[group_col].isin(exclude)]
    rows = []
    for d in DIMENSIONS:
        groups = [g[d].dropna().values for _, g in sub.groupby(group_col) if g[d].notna().any()]
        n_groups, n_total = len(groups), int(sum(len(g) for g in groups))
        stat = p = np.nan
        if n_groups >= 2:
            try:
                stat, p = kruskal(*groups)
            except ValueError:  # e.g. all values identical
                pass
        rows.append({"dimension": d, "statistic": stat, "p_value": p,
                     "n_groups": n_groups, "n_total": n_total})
    out = pd.DataFrame(rows)
    out["p_value_holm"] = holm(out["p_value"])
    return out


# ---------------------------------------------------------------- Step 14
def cluster(df):
    data = df.dropna(subset=DIMENSIONS).copy()
    X = StandardScaler().fit_transform(data[DIMENSIONS].values)
    n, n_distinct = len(data), len(np.unique(X, axis=0))
    k_max = min(10, n - 1, n_distinct)
    diag = []
    best = None
    for k in range(2, k_max + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        try:
            sil = silhouette_score(X, km.labels_)
        except ValueError:
            sil = np.nan
        diag.append({"k": k, "silhouette": sil, "inertia": km.inertia_})
        if not np.isnan(sil) and (best is None or sil > best[1]):
            best = (k, sil, km.labels_)
    diag = pd.DataFrame(diag)
    if best is None:
        raise SystemExit("Not enough distinct score profiles to cluster (need at least 3).")
    best_k, _, labels = best
    diag["chosen"] = diag["k"] == best_k
    data["cluster"] = labels
    data["best_k"] = best_k
    cols = ["subreddit_name", "language", "disease_category", "sample_group"] + DIMENSIONS + ["cluster", "best_k"]
    return data[cols].sort_values(["cluster", "subreddit_name"]), diag


# ---------------------------------------------------------------- main
def main():
    df = pd.read_csv(CONFIG, dtype=str, keep_default_na=False)

    # Step 10 (idempotent: overwrites the five columns if they already exist)
    df = compute_scores(df)
    df.to_csv(CONFIG, index=False)
    print(f"Step 10: wrote {len(DIMENSIONS)} score columns to {CONFIG} ({len(df)} rows)")

    # Step 11
    descriptive_stats(df).to_csv(OUTDIR / "descriptive_stats.csv", index=False)
    print("Step 11: descriptive_stats.csv")

    # Step 12
    kruskal_by(df, "disease_category").to_csv(OUTDIR / "kruskal_disease.csv", index=False)
    print("Step 12: kruskal_disease.csv")

    # Step 13 (communities with unknown language are not a real group, so excluded)
    kruskal_by(df, "language", exclude=("unknown",)).to_csv(OUTDIR / "kruskal_language.csv", index=False)
    print("Step 13: kruskal_language.csv")

    # Step 14
    labels, diag = cluster(df)
    labels.to_csv(OUTDIR / "cluster_analysis.csv", index=False)
    diag.to_csv(OUTDIR / "cluster_diagnostics.csv", index=False)
    print(f"Step 14: cluster_analysis.csv + cluster_diagnostics.csv (best k = {int(labels['best_k'].iloc[0])})")


if __name__ == "__main__":
    main()
