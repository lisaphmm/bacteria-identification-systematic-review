"""Tables and figures for the 206 included studies (Results 3.2 to 3.5).

Reads  : report_outputs/tables/extraction_coded.csv (run 00_features.py first)
Writes : report_outputs/tables/table_3_*.csv, supplementary table, report_outputs/figures/figure3..6 *.png
Run from the project root:  python report_outputs/code/02_included_studies.py
"""
import os, re, textwrap
import numpy as np
import pandas as pd
from common import *

style()
d = pd.read_csv(os.path.join(TABLES, "extraction_coded.csv"), keep_default_na=False)
bool_cols = [c for c in d.columns if c.startswith(("fam_", "gen_", "fac_")) or c in
             ("agar", "ext_valid", "cross_val", "data_public", "data_request", "code_public", "ds_AGAR", "ds_DIBaS", "morph_feat", "llm_vlm", "multi_species_agnostic", "fam_any_specific")]
for c in bool_cols:
    d[c] = d[c].astype(str).eq("True")
d["acc_pct"] = pd.to_numeric(d["acc_pct"], errors="coerce")
N, NA = len(d), int(d.agar.sum())
ag = d[d.agar]

def short(s, n=70):
    s = re.sub(r"\s+", " ", str(s)).strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(",;:( ")
    return cut + "…"

# ------------------------------------------------------------------ Figure 3: publication trends
yr = d.groupby(["year", "agar"]).size().unstack(fill_value=0).reindex(range(2016, 2027), fill_value=0)
yr.columns = ["Other bacterial images", "Agar plate colony images"]
yr["Total"] = yr.sum(axis=1)
yr.to_csv(os.path.join(TABLES, "figure3_publication_trends.csv"))
fig, ax = plt.subplots(figsize=(6.6, 3.5))
x = np.arange(len(yr))
ax.bar(x, yr["Other bacterial images"], color=C["sky"], width=0.68, label="Other bacterial images (n = %d)" % (N - NA))
ax.bar(x, yr["Agar plate colony images"], bottom=yr["Other bacterial images"], color=C["blue"], width=0.68, label="Agar plate colony images (n = %d)" % NA)
for xi, t in zip(x, yr.Total):
    if t: ax.text(xi, t + 0.8, str(int(t)), ha="center", fontsize=8)
ax.set_xticks(x); ax.set_xticklabels([str(y) if y != 2026 else "2026*" for y in yr.index])
ax.set_ylabel("Included studies"); ax.legend(frameon=False, loc="upper left")
ax.text(1.0, -0.2, "* 2026 covers records up to the 13 October 2026 search cut-off.", transform=ax.transAxes, ha="right", fontsize=7, color=MUTED)
save(fig, "figure3_publication_trends.png")

# ------------------------------------------------------------------ Figure 4: genera, model families, tasks
gen_cols = [c for c in d.columns if c.startswith("gen_")]
gen = pd.DataFrame({"Studies": d[gen_cols].sum().rename(lambda c: c[4:]), "Agar studies": ag[gen_cols].sum().rename(lambda c: c[4:])})
gen = gen[gen.Studies > 0].sort_values("Studies", ascending=False)
gen.to_csv(os.path.join(TABLES, "figure4a_genera.csv"))
fam = pd.DataFrame({"Studies (primary family)": d.model_family.value_counts(), "Agar studies": ag.model_family.value_counts()}).fillna(0).astype(int)
fam_multi = pd.Series({c[4:]: int(d[c].sum()) for c in d.columns if c.startswith("fam_") and c != "fam_any_specific"}, name="Studies using family (multi-label)")
fam = fam.join(fam_multi); fam.to_csv(os.path.join(TABLES, "figure4b_model_families.csv"))
tasks = {"Classification / identification": "Classification", "Detection": "Detection", "Segmentation": "Segmentation", "Counting / quantification": "Counting",
         "Antimicrobial susceptibility": "AST", "Data generation / augmentation": "Data generation"}
tk = pd.DataFrame({k: {"Studies": int(d.task_cat.str.contains(re.escape(k)).sum()), "Agar studies": int(ag.task_cat.str.contains(re.escape(k)).sum())} for k in tasks}).T
tk.loc["Other"] = [int((d.task_cat == "Other").sum()), int((ag.task_cat == "Other").sum())]
tk = tk.sort_values("Studies", ascending=False); tk.to_csv(os.path.join(TABLES, "figure4c_tasks.csv"))

fig, axs = plt.subplots(1, 3, figsize=(10.4, 3.9), gridspec_kw={"width_ratios": [1.15, 1.05, 0.9]})
def hbar(ax, df, col_all, col_ag, title, labels=None, top=None):
    df = df.head(top) if top else df
    y = np.arange(len(df))
    ax.barh(y, df[col_all], color=C["sky"], height=0.62, label="All included (n = %d)" % N)
    ax.barh(y, df[col_ag], color=C["blue"], height=0.62, label="Agar plate studies (n = %d)" % NA)
    for yy, a, b in zip(y, df[col_all], df[col_ag]):
        ax.text(a + df[col_all].max() * 0.015, yy, str(int(a)), va="center", fontsize=7.5)
    ax.set_yticks(y); ax.set_yticklabels(labels if labels is not None else df.index, fontsize=8); ax.invert_yaxis()
    ax.set_title(title, loc="left", fontsize=9.5, fontweight="bold"); ax.set_xlim(0, df[col_all].max() * 1.16); ax.set_xlabel("Studies")
hbar(axs[0], gen, "Studies", "Agar studies", "a  Genera analysed", top=12)
famp = fam.sort_values("Studies (primary family)", ascending=False)
labs = [textwrap.fill(i, 24) for i in famp.index]
hbar(axs[1], famp, "Studies (primary family)", "Agar studies", "b  Model family", labels=labs)
hbar(axs[2], tk, "Studies", "Agar studies", "c  Task (multi-label)")
h_, l_ = axs[0].get_legend_handles_labels()
fig.legend(h_, l_, frameon=False, loc="lower center", ncol=2, fontsize=8, bbox_to_anchor=(0.5, -0.04))
fig.tight_layout(); save(fig, "figure4_genera_models_tasks.png")

# ------------------------------------------------------------------ Table 3.4: the agar plate studies
t34 = ag.sort_values(["year", "id"], ascending=[False, True])[["id", "year", "species", "task_cat", "model", "ref", "acc", "data_avail", "code"]].copy()
t34 = pd.DataFrame({"Record ID": t34.id, "Year": t34.year, "Organisms": t34.species.map(lambda s: short(s, 60)), "Task": t34.task_cat.map(lambda s: s.replace("Classification / identification", "Classif.").replace("Counting / quantification", "Counting").replace("Antimicrobial susceptibility", "AST").replace("Data generation / augmentation", "Data gen.")),
                    "Model": t34.model.map(lambda s: short(s, 55)), "Reference standard": t34.ref.map(lambda s: short(s, 50)),
                    "Best reported accuracy (as extracted)": t34.acc.map(lambda s: "Not reported" if s in ("N/A", "Not extracted (model-specific per strain)") else short(s, 45)),
                    "Data / code": t34.apply(lambda r: ("Data public" if r.data_avail and re.search(r"public|zenodo|figshare|kaggle|github|mendeley", r.data_avail, re.I) else ("Data on request" if re.search("request", r.data_avail, re.I) else "Data not shared/stated")) + "; " + ("code public" if re.search(r"public|github|zenodo|replication", r.code, re.I) else "code not stated"), axis=1)})
t34.to_csv(os.path.join(TABLES, "table_3_4_agar_plate_studies.csv"), index=False)

# ------------------------------------------------------------------ Table 3.4b: the other (non-agar) included studies, so that every included study is cited
oth = d[~d.agar].sort_values(["year", "id"], ascending=[False, True])
t34b = pd.DataFrame({"Record ID": oth.id, "Year": oth.year, "Organisms": oth.species.map(lambda s: short(s, 60)),
                     "Task": oth.task_cat.map(lambda s: s.replace("Classification / identification", "Classif.").replace("Counting / quantification", "Counting").replace("Antimicrobial susceptibility", "AST").replace("Data generation / augmentation", "Data gen.")),
                     "Model": oth.model.map(lambda s: short(s, 55)), "Reference standard": oth.ref.map(lambda s: short(s, 50)),
                     "Best reported accuracy (as extracted)": oth.acc.map(lambda s: "Not reported" if s in ("N/A", "Not extracted (model-specific per strain)") else short(s, 45))})
t34b.to_csv(os.path.join(TABLES, "table_3_4b_other_image_studies.csv"), index=False)
sup = d.drop(columns=[c for c in d.columns if c.startswith(("fam_",))]).copy()
sup.to_csv(os.path.join(TABLES, "supplementary_table_S1_all_included_coded.csv"), index=False, encoding="utf-8-sig")

# ------------------------------------------------------------------ Table 3.5: species, datasets, availability, validation
def share(mask, base): return f"{int(mask.sum())} ({mask.sum() / len(base):.0%})"
rows = [
 ("Studies", N, NA),
 ("Name AGAR dataset", int(d.ds_AGAR.sum()), int(ag.ds_AGAR.sum())),
 ("Name DIBaS dataset", int(d.ds_DIBaS.sum()), int(ag.ds_DIBaS.sum())),
 ("Data public (repository or named public dataset)", int(d.data_public.sum()), int(ag.data_public.sum())),
 ("Data on request only", int((d.data_request & ~d.data_public).sum()), int((ag.data_request & ~ag.data_public).sum())),
 ("Code public", int(d.code_public.sum()), int(ag.code_public.sum())),
 ("Independent, external or held-out validation stated", int(d.ext_valid.sum()), int(ag.ext_valid.sum())),
 ("Cross-validation stated", int(d.cross_val.sum()), int(ag.cross_val.sum())),
 ("Species-agnostic or multi-species task", int(d.multi_species_agnostic.sum()), int(ag.multi_species_agnostic.sum())),
]
t35 = pd.DataFrame(rows, columns=["Item", "All included (n=%d)" % N, "Agar plate studies (n=%d)" % NA])
t35["All included (%)"] = (t35.iloc[:, 1] / N * 100).round(1); t35["Agar plate studies (%)"] = (t35.iloc[:, 2] / NA * 100).round(1)
t35.to_csv(os.path.join(TABLES, "table_3_5_datasets_availability_validation.csv"), index=False)
ctry = d.country.replace("N/A", np.nan).dropna().str.split(" / ").explode().value_counts().head(10).rename("Studies (any author affiliation)")
ctry.to_csv(os.path.join(TABLES, "countries_top10.csv"))
def _norm_cat(t):
    t = t.strip(); l = t.lower()
    if re.match(r"(not |classification by|digitized whole|environmental / soil|antimicrobial susceptibility)", l): return None   # qualifier text, not a category
    if l.startswith("agar plate"): return "Agar plate colonies"
    if "histopath" in l: return "Histopathology / WSI"
    if l.startswith("afb"): return "AFB / TB smear microscopy"
    if "gram" in l: return "Gram-stain microscopy"
    if l.startswith("fluorescence") or "uv-c fluorescence" in l: return "Fluorescence microscopy" if "macroscopic" not in l else "Other imaging (macroscopic, other)"
    if l == "urine": return "Urine"
    if "scatter" in l or "speckle" in l or "lens-free" in l: return "Lens-free / holographic / scatter"
    for c in ["Other microscopy", "Microfluidic / time-lapse", "Hyperspectral / spectral", "Biofilm imaging", "Environmental sample", "Electron microscopy"]:
        if l.startswith(c.lower()): return c
    return "Other imaging (macroscopic, other)"
import re
_c = d.data_cat.map(lambda s: sorted({x for x in (_norm_cat(t) for t in s.split("; ")) if x}))
d["data_cat_norm"] = _c.map("; ".join)
cats = _c.explode().value_counts().rename("Studies"); cats.to_csv(os.path.join(TABLES, "data_categories.csv"))

# ------------------------------------------------------------------ accuracy summaries + Figure 5
acc = d.dropna(subset=["acc_pct"]).copy()
def summ(g):
    q = g.acc_pct.quantile([.25, .5, .75]); return pd.Series({"n": len(g), "Median": q[.5], "Q1": q[.25], "Q3": q[.75], "Min": g.acc_pct.min(), "Max": g.acc_pct.max()})
s_ref = acc.groupby("ref_cat").apply(summ).sort_values("n", ascending=False)
s_fam = acc.groupby("model_family").apply(summ).sort_values("n", ascending=False)
s_ag = acc.groupby(acc.agar.map({True: "Agar plate colony images", False: "Other bacterial images"})).apply(summ)
for name, s in [("ref", s_ref), ("family", s_fam), ("agar", s_ag)]:
    s.round(2).to_csv(os.path.join(TABLES, f"figure5_accuracy_by_{name}.csv"))
acc[["id", "year", "agar", "ref_cat", "model_family", "acc_pct", "acc"]].to_csv(os.path.join(TABLES, "figure5_accuracy_points.csv"), index=False)
overall = summ(acc.assign(x=1)); overall.round(2).to_csv(os.path.join(TABLES, "accuracy_overall.csv"))
print("accuracy overall", overall.round(1).to_dict()); print(s_ref.round(1)); print(s_fam.round(1)); print(s_ag.round(1))

rng = np.random.default_rng(7)
fig, axs = plt.subplots(1, 2, figsize=(10.2, 3.9), sharex=True)
for ax, col, order_df, title in [(axs[0], "ref_cat", s_ref, "a  By reference standard"), (axs[1], "model_family", s_fam, "b  By model family")]:
    order = [i for i in order_df.index if order_df.loc[i, "n"] >= 3]
    for k, cat in enumerate(order):
        g = acc[acc[col] == cat]
        ax.boxplot(g.acc_pct, positions=[k], vert=False, widths=0.5, showfliers=False, patch_artist=True,
                   boxprops=dict(facecolor="#F2F2F2", edgecolor=MUTED, lw=0.8), medianprops=dict(color=INK, lw=1.4), whiskerprops=dict(color=MUTED, lw=0.8), capprops=dict(color=MUTED, lw=0.8))
        yy = k + rng.uniform(-0.17, 0.17, len(g))
        ax.scatter(g.acc_pct[~g.agar], yy[~g.agar.values], s=14, color=C["sky"], edgecolor="white", lw=0.4, zorder=3)
        ax.scatter(g.acc_pct[g.agar], yy[g.agar.values], s=16, color=C["blue"], edgecolor="white", lw=0.4, zorder=4)
    ax.set_yticks(range(len(order))); ax.set_yticklabels([f"{textwrap.fill(o, 26)}\n(n = {int(order_df.loc[o, 'n'])})" for o in order], fontsize=7.8); ax.invert_yaxis()
    ax.set_xlabel("Best reported accuracy (%), as extracted"); ax.set_title(title, loc="left", fontsize=9.5, fontweight="bold"); ax.set_xlim(40, 101)
    ax.axvline(100, color=GRID, lw=0.8)
axs[1].scatter([], [], s=16, color=C["blue"], label="Agar plate colony images"); axs[1].scatter([], [], s=14, color=C["sky"], label="Other bacterial images")
axs[1].legend(frameon=False, loc="lower left", fontsize=7.5)
fig.tight_layout(); save(fig, "figure5_accuracy.png")

# ------------------------------------------------------------------ RQ2 factors: Figure 6 and Table 3.6
fac_cols = [c for c in d.columns if c.startswith("fac_")]
fac = pd.DataFrame({"All included": d[fac_cols].sum().rename(lambda c: c[4:]), "Agar plate studies": ag[fac_cols].sum().rename(lambda c: c[4:])})
fac["All included (%)"] = (fac["All included"] / N * 100).round(1); fac["Agar plate studies (%)"] = (fac["Agar plate studies"] / NA * 100).round(1)
fac = fac.sort_values("All included", ascending=False); fac.to_csv(os.path.join(TABLES, "figure6_factors_examined.csv"))
fig, ax = plt.subplots(figsize=(7.4, 3.9)); y = np.arange(len(fac)); h = 0.38
ax.barh(y - h / 2, fac["All included (%)"], height=h, color=C["sky"], label="All included (n = %d)" % N)
ax.barh(y + h / 2, fac["Agar plate studies (%)"], height=h, color=C["blue"], label="Agar plate studies (n = %d)" % NA)
for yy, a, b in zip(y, fac["All included (%)"], fac["Agar plate studies (%)"]):
    ax.text(a + 0.6, yy - h / 2, f"{a:.0f}%", va="center", fontsize=7.5); ax.text(b + 0.6, yy + h / 2, f"{b:.0f}%", va="center", fontsize=7.5)
ax.set_yticks(y); ax.set_yticklabels(fac.index, fontsize=8); ax.invert_yaxis(); ax.set_xlabel("Share of studies that report the factor (%)")
ax.set_xlim(0, max(fac["All included (%)"].max(), fac["Agar plate studies (%)"].max()) * 1.15); ax.legend(frameon=False, loc="lower right", fontsize=7.5)
fig.tight_layout(); save(fig, "figure6_factors_examined.png")

acq = ["fac_Incubation / growth time", "fac_Illumination / lighting", "fac_Imaging device / modality / magnification", "fac_Image resolution / patch or crop size",
       "fac_Medium / background / plate type", "fac_Preprocessing (filtering, normalisation)", "fac_Data augmentation / synthetic data"]
m = ag[ag[acq].any(axis=1)].sort_values(["year", "id"], ascending=[False, True])
t36 = pd.DataFrame({"Record ID": m.id, "Year": m.year, "Factors examined or varied (as extracted)": m.factors.map(lambda s: short(s, 95)),
                    "Categories": m.apply(lambda r: "; ".join(c[4:].split(" (")[0] for c in acq if r[c]), axis=1),
                    "Other reported outcomes (as extracted)": m.other.map(lambda s: "Not reported" if s == "N/A" else short(s, 95))})
t36.to_csv(os.path.join(TABLES, "table_3_6_agar_studies_acquisition_preprocessing.csv"), index=False)

# ------------------------------------------------------------------ Table 3.7: morphology / motility features (curated)
RQ3 = {
 "R01073": ("Handcrafted morphology descriptors fused with CNN probabilities or embeddings", "Yes: morphology-only vs fusion vs CNN branches"),
 "R04927": ("Spectral and morphological information fused in BI-Net", "Yes: spectral alone, binary mask (morphology) alone, fusion"),
 "R06695": ("Haralick texture and colour features with isolation forest and deep random forest", "Yes: CNN vs texture-feature models"),
 "R04320": ("Colony morphology and complexity, image-processing features, with transfer-learning CNNs", "No direct feature versus raw-image test extracted"),
 "R02126": ("Persistent-homology (topological) features with EfficientNet", "Not extracted"),
 "R00815": ("Extracted image features with regression, and Swin Transformer on time-lapse swarm images", "Not extracted"),
 "R02939": ("Swarming (motility) pattern classified by a CNN with attention", "Attention ablation only"),
 "R04273": ("Elliptic Fourier shape descriptors with SVM after U-Net localisation", "Not extracted"),
 "R03780": ("Cell contour sequences analysed by a ResNet-style network", "Not extracted"),
 "R00411": ("Cell morphology versus graph features in a cell-graph network (mouse lung tissue)", "Yes: morphology versus graph features"),
 "R04850": ("CNN-extracted features with classical classifiers on colony images", "Compares classifier combinations"),
}
rows = []
for rid, (feat, cmp_) in RQ3.items():
    r = d[d.id == rid].iloc[0]
    rows.append({"Record ID": rid, "Year": r.year, "Agar plate images": "Yes" if r.agar else "No", "Feature type and model": feat,
                 "Comparison with raw-image model": cmp_, "Result as extracted": short(r.acc if r.acc != "N/A" else r.other, 110)})
pd.DataFrame(rows).to_csv(os.path.join(TABLES, "table_3_7_morphology_motility_features.csv"), index=False)

# LLM / VLM studies
llm = d[d.llm_vlm][["id", "year", "agar", "model", "task_cat"]]; llm.to_csv(os.path.join(TABLES, "llm_vlm_studies.csv"), index=False)
print("done", N, NA)
