#!/usr/bin/env python3
"""Figures for the configuration analysis (steps 10-14 outputs).

Usage:
    python visualize_results.py [configuration.csv] [data/results] [data/results/figures]

Requires: pandas, numpy, matplotlib, scikit-learn
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "configuration.csv"
RESULTS = Path(sys.argv[2] if len(sys.argv) > 2 else "data/results")
FIGDIR = Path(sys.argv[3] if len(sys.argv) > 3 else RESULTS / "figures")
FIGDIR.mkdir(parents=True, exist_ok=True)

DIMS = ["access_restrictiveness", "content_permissiveness", "classification_capacity",
        "knowledge_capacity", "visibility_calibration"]
LABELS = {d: d.replace("_", " ").title() for d in DIMS}
SHORT = {"access_restrictiveness": "Access", "content_permissiveness": "Content",
         "classification_capacity": "Classification", "knowledge_capacity": "Knowledge",
         "visibility_calibration": "Visibility"}

plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 200, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10})
PALETTE = plt.get_cmap("tab10")


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGDIR / name, bbox_inches="tight")
    plt.close(fig)
    print("wrote", FIGDIR / name)


def fmt_p(p):
    if pd.isna(p):
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


# ------------------------------------------------------------------ figures
def fig_composition(df):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, col, title in zip(axes, ["language", "disease_category", "sample_group"],
                              ["Language", "Disease category", "Sample group"]):
        c = df[col].value_counts()
        bars = ax.bar(c.index, c.values, color=PALETTE(np.arange(len(c))))
        ax.bar_label(bars, padding=2)
        ax.set_title(title)
        ax.set_ylabel("Communities")
        ax.tick_params(axis="x", rotation=30)
        for t in ax.get_xticklabels():
            t.set_ha("right")
    save(fig, "fig1_sample_composition.png")


def fig_distributions(df):
    fig, axes = plt.subplots(1, 5, figsize=(17, 3.4), sharey=True)
    for ax, d in zip(axes, DIMS):
        s = df[d].dropna()
        ax.hist(s, bins=np.linspace(0, 1, 21), color="#4C72B0", edgecolor="white")
        ax.axvline(s.mean(), color="crimson", ls="--", lw=1.3, label=f"mean {s.mean():.2f}")
        ax.axvline(s.median(), color="black", ls=":", lw=1.3, label=f"median {s.median():.2f}")
        ax.set_title(SHORT[d])
        ax.set_xlim(0, 1)
        ax.set_xlabel("score")
        ax.legend(fontsize=7, frameon=False)
    axes[0].set_ylabel("Communities")
    fig.suptitle("Distribution of the five dimension scores", y=1.04)
    save(fig, "fig2_score_distributions.png")


def fig_boxes(df, group_col, kw_file, out, title, exclude=()):
    sub = df[~df[group_col].isin(exclude)]
    order = sorted(sub[group_col].unique())
    kw = pd.read_csv(kw_file).set_index("dimension") if Path(kw_file).exists() else None
    fig, axes = plt.subplots(1, 5, figsize=(18, 4.2), sharey=True)
    for ax, d in zip(axes, DIMS):
        data = [sub.loc[sub[group_col] == g, d].dropna().values for g in order]
        bp = ax.boxplot(data, patch_artist=True, showfliers=False, widths=0.6)
        for patch, i in zip(bp["boxes"], range(len(order))):
            patch.set_facecolor(PALETTE(i))
            patch.set_alpha(0.7)
        for med in bp["medians"]:
            med.set_color("black")
        rng = np.random.default_rng(0)
        for i, vals in enumerate(data, 1):  # jittered points show the real sample sizes
            ax.scatter(i + rng.uniform(-0.18, 0.18, len(vals)), vals, s=5, color="black", alpha=0.25)
        ax.set_xticks(range(1, len(order) + 1))
        ax.set_xticklabels([f"{g}\n(n={len(v)})" for g, v in zip(order, data)], fontsize=8, rotation=30, ha="right")
        sub_title = SHORT[d]
        if kw is not None and d in kw.index:
            p_col = "p_value_holm" if "p_value_holm" in kw.columns else "p_value"
            sub_title += f"\nKW p{'(Holm)' if p_col == 'p_value_holm' else ''}={fmt_p(kw.loc[d, p_col])}"
        ax.set_title(sub_title, fontsize=10)
        ax.set_ylim(-0.02, 1.02)
    axes[0].set_ylabel("Score")
    fig.suptitle(title, y=1.04)
    save(fig, out)


def fig_correlation(df):
    corr = df[DIMS].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(5.8, 5))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(5)); ax.set_xticklabels([SHORT[d] for d in DIMS], rotation=35, ha="right")
    ax.set_yticks(range(5)); ax.set_yticklabels([SHORT[d] for d in DIMS])
    for i in range(5):
        for j in range(5):
            v = corr.iloc[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color="white" if abs(v) > 0.55 else "black", fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Spearman ρ")
    ax.set_title("Correlation between dimensions")
    save(fig, "fig5_dimension_correlation.png")


def fig_cluster_diag(diag):
    fig, ax1 = plt.subplots(figsize=(6.5, 4))
    ax1.plot(diag["k"], diag["silhouette"], "o-", color="#4C72B0", label="Silhouette")
    ax1.set_xlabel("k"); ax1.set_ylabel("Silhouette score", color="#4C72B0")
    ax2 = ax1.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(diag["k"], diag["inertia"], "s--", color="#DD8452", label="Inertia")
    ax2.set_ylabel("Inertia", color="#DD8452")
    best = diag.loc[diag["silhouette"].idxmax()]
    ax1.axvline(best["k"], color="grey", ls=":")
    ax1.annotate(f"best k = {int(best['k'])}\nsilhouette {best['silhouette']:.3f}",
                 (best["k"], best["silhouette"]), textcoords="offset points", xytext=(8, -28), fontsize=9)
    ax1.set_xticks(diag["k"])
    ax1.set_title("k-means diagnostics")
    save(fig, "fig6_cluster_diagnostics.png")


def fig_cluster_profiles(cl):
    prof = cl.groupby("cluster")[DIMS].mean()
    n = cl["cluster"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(prof) + 2.2))
    im = ax.imshow(prof.values, cmap="viridis", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(5)); ax.set_xticklabels([SHORT[d] for d in DIMS])
    ax.set_yticks(range(len(prof)))
    ax.set_yticklabels([f"Cluster {c} (n={n[c]})" for c in prof.index])
    for i in range(prof.shape[0]):
        for j in range(prof.shape[1]):
            v = prof.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color="white" if v < 0.6 else "black", fontsize=9)
    fig.colorbar(im, ax=ax, label="Mean score")
    ax.set_title("Cluster profiles (archetypes)")
    save(fig, "fig7_cluster_profiles.png")


def fig_cluster_pca(cl):
    X = StandardScaler().fit_transform(cl[DIMS].values)
    pca = PCA(n_components=2, random_state=0)
    Z = pca.fit_transform(X)
    rng = np.random.default_rng(0)
    Z = Z + rng.normal(0, 0.03, Z.shape)  # tiny jitter so identical profiles don't hide each other
    fig, ax = plt.subplots(figsize=(6.5, 5.2))
    for i, c in enumerate(sorted(cl["cluster"].unique())):
        m = (cl["cluster"] == c).values
        ax.scatter(Z[m, 0], Z[m, 1], s=18, alpha=0.7, color=PALETTE(i % 10), label=f"Cluster {c} (n={m.sum()})")
    ev = pca.explained_variance_ratio_
    ax.set_xlabel(f"PC1 ({ev[0]:.0%} variance)")
    ax.set_ylabel(f"PC2 ({ev[1]:.0%} variance)")
    ax.set_title("Communities in score space (PCA projection)")
    ax.legend(fontsize=8, frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    save(fig, "fig8_cluster_pca.png")


def fig_cluster_composition(cl):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, col in zip(axes, ["disease_category", "language"]):
        ct = pd.crosstab(cl["cluster"], cl[col], normalize="index")
        bottom = np.zeros(len(ct))
        for i, c in enumerate(ct.columns):
            ax.bar(ct.index.astype(str), ct[c], bottom=bottom, label=c, color=PALETTE(i % 10))
            bottom += ct[c].values
        ax.set_xlabel("Cluster"); ax.set_ylabel("Share of cluster")
        ax.set_title(f"Cluster composition by {col.replace('_', ' ')}")
        ax.legend(fontsize=7, frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    save(fig, "fig9_cluster_composition.png")


# ------------------------------------------------------------------ main
def main():
    df = pd.read_csv(CONFIG)
    for d in DIMS:
        if d not in df.columns:
            raise SystemExit(f"{d} missing from {CONFIG}; run analyze_configuration.py first.")

    fig_composition(df)
    fig_distributions(df)
    fig_boxes(df, "disease_category", RESULTS / "kruskal_disease.csv",
              "fig3_scores_by_disease.png", "Dimension scores by disease category")
    fig_boxes(df, "language", RESULTS / "kruskal_language.csv",
              "fig4_scores_by_language.png", "Dimension scores by language (unknown excluded)",
              exclude=("unknown",))
    fig_correlation(df)

    diag_f, cl_f = RESULTS / "cluster_diagnostics.csv", RESULTS / "cluster_analysis.csv"
    if diag_f.exists() and cl_f.exists():
        diag, cl = pd.read_csv(diag_f), pd.read_csv(cl_f)
        fig_cluster_diag(diag)
        fig_cluster_profiles(cl)
        fig_cluster_pca(cl)
        fig_cluster_composition(cl)
    else:
        print("Cluster files not found; skipped figures 6-9.")


if __name__ == "__main__":
    main()
