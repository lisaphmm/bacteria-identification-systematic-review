"""Study selection counts (Table 3.1, 3.2, Figure 1) and the Gemini vs Mistral comparison (Table 3.3, Figure 2).

Reads  : data/deduplicated/*, data/screening_input/*, results/final/final_results.csv,
         results/full_run/final_decisions.csv + usage_log.csv, results/pilot/pilot_manual_check.xlsx,
         results/fulltext/fulltext_screening_decisions.csv
Writes : report_outputs/tables/*.csv, report_outputs/figures/figure1_prisma.png, figure2_llm_comparison.png
Run from the project root:  python report_outputs/code/01_selection_and_llm_comparison.py
"""
import math, os
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch
from common import *

style()
R = lambda *p: os.path.join(ROOT, *p)
dedup = pd.read_csv(R("data", "deduplicated", "deduplicated_papers.csv"), dtype=str)
log = pd.read_csv(R("data", "deduplicated", "deduplication_log.csv"), dtype=str)
excl = pd.read_csv(R("data", "screening_input", "excluded_records.csv"), dtype=str)
fin = pd.read_csv(R("results", "final", "final_results.csv"), dtype=str, keep_default_na=False)
dec = pd.read_csv(R("results", "full_run", "final_decisions.csv"), dtype=str, keep_default_na=False)
ft = pd.read_csv(R("results", "fulltext", "fulltext_screening_decisions.csv"), dtype=str, keep_default_na=False)
use = pd.read_csv(R("results", "full_run", "usage_log.csv"))

# ------------------------------------------------------------------ counts
exports = {"Scopus": 11516, "PubMed": 362, "SpringerLink": 242, "IEEE Xplore": 68, "Embase": 25}  # rows read by deduplicate.py
assert sum(exports.values()) == len(dedup) + len(log), "export total does not match deduplication output"
pre = excl[~excl.Reason.str.startswith("Removed")]
post = excl[excl.Reason.str.startswith("Removed")]
removed_ids = set(post.Primary_ID)
dec["removed_after_tiab"] = dec.Primary_ID.isin(removed_ids)
dec = dec.merge(fin[["Record_ID", "Final"]], on="Record_ID", how="left")
dec["ref_pos"] = (dec.Final == "include") | dec.removed_after_tiab        # included at title/abstract stage (human-resolved)
n_screened, n_tiab_inc = len(dec), int(dec.ref_pos.sum())
n_not_retrieved = int(post.Reason.str.contains("not accessible").sum())
n_lang = int(post.Reason.str.contains("English").sum())
n_nobact = int(post.Reason.str.contains("E5").sum())
n_assessed = len(ft)
n_ft_exc = int((ft.FullText_Decision == "Exclude").sum())
n_ft_inc = int((ft.FullText_Decision == "Include").sum())
n_agar = int(((ft.FullText_Decision == "Include") & (ft.Agar_plate_colony_images == "Yes")).sum())
assert n_tiab_inc == n_not_retrieved + n_lang + n_nobact + n_assessed, (n_tiab_inc, n_not_retrieved, n_lang, n_nobact, n_assessed)
reasons = ft[ft.FullText_Decision == "Exclude"].groupby(["Exclusion_code", "Exclusion_reason"]).size().reset_index(name="Reports")
reasons = reasons.sort_values("Reports", ascending=False)
reasons.to_csv(os.path.join(TABLES, "table_3_2_fulltext_exclusions.csv"), index=False)

# Table 3.1 search yield by database
t31 = pd.DataFrame({"Database": list(exports), "Records exported": list(exports.values())})
t31["Duplicates removed"] = t31.Database.map(log.Removed_Source.value_counts()).fillna(0).astype(int)
t31["Unique records kept"] = t31.Database.map(dedup.Primary_Database.value_counts()).fillna(0).astype(int)
t31["Removed before screening"] = t31.Database.map(pre.Primary_Database.value_counts()).fillna(0).astype(int)
t31["Screened (title/abstract)"] = t31.Database.map(dec.Primary_Database.value_counts()).fillna(0).astype(int)
t31["Included at title/abstract"] = t31.Database.map(dec[dec.ref_pos].Primary_Database.value_counts()).fillna(0).astype(int)
inc_ids = set(ft[ft.FullText_Decision == "Include"].Record_ID)
t31["Included after full text"] = t31.Database.map(dec[dec.Record_ID.isin(inc_ids)].Primary_Database.value_counts()).fillna(0).astype(int)
tot = t31.drop(columns="Database").sum(); tot["Database"] = "Total"
t31 = pd.concat([t31, pd.DataFrame([tot])[t31.columns]], ignore_index=True)
t31.to_csv(os.path.join(TABLES, "table_3_1_search_yield.csv"), index=False)
print(t31.to_string())

flow = {
 "identified": sum(exports.values()), "duplicates": len(log), "unique": len(dedup),
 "pre_before2015": int((pre.Reason == "Published before 2015").sum()), "pre_noabs": int((pre.Reason == "No abstract").sum()),
 "pre_after": int(pre.Reason.str.startswith("Published after").sum()), "screened": n_screened,
 "tiab_excluded": n_screened - n_tiab_inc, "sought": n_tiab_inc, "not_retrieved": n_not_retrieved,
 "removed_lang": n_lang, "removed_nobact": n_nobact, "assessed": n_assessed, "ft_excluded": n_ft_exc,
 "included": n_ft_inc, "included_agar": n_agar,
}
pd.Series(flow).rename("n").to_csv(os.path.join(TABLES, "figure1_prisma_counts.csv"))
print(flow)

# ------------------------------------------------------------------ Figure 1: PRISMA 2020
fig, ax = plt.subplots(figsize=(7.4, 9.2)); ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
def box(x, y, w, h, text, fc="#FFFFFF", bold=False, size=8.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", fc=fc, ec=MUTED, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=INK, fontweight="bold" if bold else "normal", linespacing=1.35)
def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=0.9))
L, Rr = 4, 56; W, WR = 44, 40
box(L, 87, W, 11, f"Records identified from 5 databases\n(n = {flow['identified']:,})\nScopus {exports['Scopus']:,}; PubMed {exports['PubMed']};\nSpringerLink {exports['SpringerLink']}; IEEE Xplore {exports['IEEE Xplore']}; Embase {exports['Embase']}", "#EAF3FA", size=7.4)
box(Rr, 88, WR, 10, f"Duplicates removed\n(n = {flow['duplicates']}; DOI 401, title 3)")
box(L, 72, W, 9, f"Unique records\n(n = {flow['unique']:,})")
box(Rr, 70, WR, 13, f"Removed before screening (n = {flow['pre_before2015']+flow['pre_noabs']+flow['pre_after']:,})\nPublished before 2015: {flow['pre_before2015']:,}\nNo abstract: {flow['pre_noabs']}\nAfter 13 Oct 2026 cut-off: {flow['pre_after']}")
box(L, 55, W, 9, f"Records screened: title and abstract\n(Gemini + Mistral, human check)\n(n = {flow['screened']:,})")
box(Rr, 55, WR, 9, f"Excluded at title/abstract\n(n = {flow['tiab_excluded']:,})")
box(L, 39, W, 9, f"Reports sought for retrieval\n(n = {flow['sought']})")
box(Rr, 36, WR, 15, f"Not assessed (n = {flow['not_retrieved']+flow['removed_lang']+flow['removed_nobact']})\nFull text not accessible: {flow['not_retrieved']}\nNot in English: {flow['removed_lang']}\nNo bacteria analysed: {flow['removed_nobact']}")
box(L, 22, W, 9, f"Reports assessed for eligibility\n(n = {flow['assessed']})")
rs = reasons.set_index("Exclusion_code").Reports
box(Rr, 14, WR, 20, f"Excluded at full text (n = {flow['ft_excluded']})\nE6 deep learning not used: {rs.get('E6',0)}\nE5 no bacteria analysed: {rs.get('E5',0)}\nE7 task not eligible: {rs.get('E7',0)}\nE3 review / not original: {rs.get('E3',0)}\nE8, E9, E10: {rs.get('E8',0)}, {rs.get('E9',0)}, {rs.get('E10',0)}")
box(L, 5, W, 11, f"Studies included in the review\n(n = {flow['included']})\nof which agar plate colony images: {flow['included_agar']}", "#E6F4EC", bold=True)
for y1, y2 in [(88, 81), (72, 64), (55, 48), (39, 31), (22, 16)]:
    arrow(L + W / 2, y1, L + W / 2, y2)
for y in [93, 76.5, 59.5, 43.5, 24]:
    arrow(L + W, y, Rr, y)
save(fig, "figure1_prisma.png")

# ------------------------------------------------------------------ LLM comparison
labs = ["include", "check_manually", "exclude"]
def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b); po = (a == b).mean()
    pe = sum((a == l).mean() * (b == l).mean() for l in set(a) | set(b)); return po, (po - pe) / (1 - pe)
def metrics(pred_pos, truth):
    tp = int((pred_pos & truth).sum()); fp = int((pred_pos & ~truth).sum()); fn = int((~pred_pos & truth).sum()); tn = int((~pred_pos & ~truth).sum())
    sens = tp / (tp + fn); spec = tn / (tn + fp); prec = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * prec * sens / (prec + sens) if prec + sens else float("nan")
    return dict(TP=tp, FP=fp, FN=fn, TN=tn, Sensitivity=sens, Specificity=spec, Precision=prec, F1=f1, Accuracy=(tp + tn) / len(truth))
truth = dec.ref_pos.values
rows = []
for model, col in [("Gemini", "d_gemini"), ("Mistral", "d_mistral")]:
    for rule, pos in [("include only", dec[col] == "include"), ("include + check manually", dec[col].isin(["include", "check_manually"]))]:
        m = metrics(pos.values, truth); m.update(Model=model, Rule=rule, Records_flagged=int(pos.sum())); rows.append(m)
both = (dec.d_gemini == "include") & (dec.d_mistral == "include")
either = dec.d_gemini.isin(["include", "check_manually"]) | dec.d_mistral.isin(["include", "check_manually"])
for name, pos in [("Both include", both), ("Either include / check manually (records sent to human)", either)]:
    m = metrics(pos.values, truth); m.update(Model="Combined", Rule=name, Records_flagged=int(pos.sum())); rows.append(m)
t32 = pd.DataFrame(rows)[["Model", "Rule", "Records_flagged", "TP", "FP", "FN", "TN", "Sensitivity", "Specificity", "Precision", "F1", "Accuracy"]]
t32.to_csv(os.path.join(TABLES, "table_3_3_llm_performance.csv"), index=False)
print(t32.round(4).to_string())

# agreement
po, kap3 = kappa(dec.d_gemini, dec.d_mistral)
bin_g = dec.d_gemini.eq("exclude"); bin_m = dec.d_mistral.eq("exclude")
po_b, kap_b = kappa(bin_g.map({True: "exc", False: "inc"}), bin_m.map({True: "exc", False: "inc"}))
cm = pd.crosstab(dec.d_gemini, dec.d_mistral).reindex(index=labs, columns=labs, fill_value=0)
cm.to_csv(os.path.join(TABLES, "figure2a_agreement_matrix.csv"))
both_exc = dec[(dec.d_gemini == "exclude") & (dec.d_mistral == "exclude")]
same_code = (both_exc.r_gemini == both_exc.r_mistral).mean()
codes = pd.DataFrame({"Gemini": dec[dec.d_gemini == "exclude"].r_gemini.value_counts(), "Mistral": dec[dec.d_mistral == "exclude"].r_mistral.value_counts()}).fillna(0).astype(int)
codes = codes.sort_values("Gemini", ascending=False); codes.to_csv(os.path.join(TABLES, "figure2b_exclusion_codes.csv"))
# McNemar (exact) on correct vs wrong, rule = include + check manually
pg = dec.d_gemini.isin(["include", "check_manually"]).values; pm = dec.d_mistral.isin(["include", "check_manually"]).values
cg, cmis = (pg == truth), (pm == truth)
b, c = int((cg & ~cmis).sum()), int((~cg & cmis).sum()); n = b + c
p_mc = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n) if n else 1.0
# conditional: what happened to the records a model included
cond = []
for model, col in [("Gemini", "d_gemini"), ("Mistral", "d_mistral")]:
    s = dec[dec[col] == "include"]
    cond.append(dict(Model=model, Included=len(s), Included_at_tiab=int(s.ref_pos.sum()), Included_after_fulltext=int(s.Record_ID.isin(inc_ids).sum())))
pd.DataFrame(cond).to_csv(os.path.join(TABLES, "llm_precision_through_fulltext.csv"), index=False)
# disagreement structure
dis = dec[dec.d_gemini != dec.d_mistral].copy(); dis["pair"] = "Gemini " + dis.d_gemini + " / Mistral " + dis.d_mistral
dis_tab = dis.groupby("pair").agg(Records=("Record_ID", "size"), Included_at_tiab=("ref_pos", "sum")).reset_index().sort_values("Records", ascending=False)
dis_tab["Share_included"] = dis_tab.Included_at_tiab / dis_tab.Records
dis_tab.to_csv(os.path.join(TABLES, "table_3_3b_disagreement_outcomes.csv"), index=False)
# pilot against the reviewer's 100 blind decisions
pm_ = pd.read_excel(R("results", "pilot", "pilot_manual_check.xlsx"), dtype=str)[["Record_ID", "Human_Decision"]]
pil = pm_.merge(dec[["Record_ID", "d_gemini", "d_mistral"]], on="Record_ID")
prow = []
for model, col in [("Gemini", "d_gemini"), ("Mistral", "d_mistral")]:
    po_p, k_p = kappa(pil.Human_Decision, pil[col].replace({"check_manually": "include"}))
    tp = int(((pil.Human_Decision == "include") & pil[col].isin(["include", "check_manually"])).sum())
    prow.append(dict(Model=model, Records=len(pil), Reviewer_includes=int((pil.Human_Decision == "include").sum()), Included_by_model=tp,
                     Percent_agreement=po_p, Kappa=k_p))
pd.DataFrame(prow).to_csv(os.path.join(TABLES, "table_3_3c_pilot_vs_reviewer.csv"), index=False)
# usage
u = use.groupby("model").agg(Requests=("n_records", "size"), Records=("n_records", "sum"), Input_tokens=("input_tokens", "sum"),
                              Output_tokens=("output_tokens", "sum"), Seconds_total=("seconds", "sum"), Failed_requests=("status", lambda s: int((s != "ok").sum()))).reset_index()
okc = use[use.status == "ok"].groupby("model").agg(Successful_requests=("n_records", "size"), Records_screened=("n_records", "sum"), Seconds_ok=("seconds", "sum")).reset_index()
u = u.merge(okc, on="model"); u["Seconds_per_successful_request"] = u.Seconds_ok / u.Successful_requests
u.to_csv(os.path.join(TABLES, "table_3_3d_usage.csv"), index=False)
summary = dict(agreement_3class=po, kappa_3class=kap3, agreement_binary=po_b, kappa_binary=kap_b, n_both_exclude=len(both_exc),
               same_exclusion_code_share=same_code, mcnemar_b=b, mcnemar_c=c, mcnemar_p=p_mc, n=len(dec), positives=int(truth.sum()),
               gemini_check=int((dec.d_gemini == "check_manually").sum()), mistral_check=int((dec.d_mistral == "check_manually").sum()))
pd.Series(summary).to_csv(os.path.join(TABLES, "llm_agreement_summary.csv"), header=["value"])
print(summary); print(cond); print(dis_tab); print(pd.DataFrame(prow)); print(u); print(cm); print(codes)

# ------------------------------------------------------------------ Figure 2
fig, axs = plt.subplots(1, 2, figsize=(9.2, 3.9), gridspec_kw={"width_ratios": [1, 1.15]})
ax = axs[0]
mat = cm.values.astype(float)
ax.imshow(np.log10(mat + 1), cmap="Blues", vmin=0, vmax=4.2)
for i in range(3):
    for j in range(3):
        v = int(mat[i, j]); ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=9, color="white" if np.log10(v + 1) > 2.6 else INK)
nice = {"include": "Include", "check_manually": "Check\nmanually", "exclude": "Exclude"}
ax.set_xticks(range(3)); ax.set_xticklabels([nice[l] for l in labs]); ax.set_yticks(range(3)); ax.set_yticklabels([nice[l].replace("\n", " ") for l in labs])
ax.set_xlabel("Mistral decision"); ax.set_ylabel("Gemini decision"); ax.xaxis.set_label_position("bottom")
ax.set_title(f"a  Agreement on {len(dec):,} records\n{po:.1%} agree, kappa {kap3:.2f}", loc="left", fontsize=9.5, fontweight="bold")
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)
ax = axs[1]
top = codes.head(8)
y = np.arange(len(top)); h = 0.36
ax.barh(y - h / 2, top.Gemini, height=h, color=C["blue"], label="Gemini")
ax.barh(y + h / 2, top.Mistral, height=h, color=C["orange"], label="Mistral")
for yy, g, m in zip(y, top.Gemini, top.Mistral):
    ax.text(g + 40, yy - h / 2, f"{g:,}", va="center", fontsize=7.5, color=INK); ax.text(m + 40, yy + h / 2, f"{m:,}", va="center", fontsize=7.5, color=INK)
lab_codes = {"E4": "E4 not image data", "E5": "E5 no bacteria", "E6": "E6 no deep learning", "E3": "E3 not original research", "E7": "E7 task not eligible",
             "E2": "E2 preprint", "E9": "E9 simulated only", "E10": "E10 hardware only", "E13": "E13 not English", "E8": "E8 no evaluation"}
ax.set_yticks(y); ax.set_yticklabels([lab_codes.get(c, c) for c in top.index]); ax.invert_yaxis()
ax.set_xlabel("Records excluded"); ax.legend(frameon=False, loc="lower right")
ax.set_title("b  Exclusion codes assigned", loc="left", fontsize=9.5, fontweight="bold")
ax.set_xlim(0, top.values.max() * 1.15)
fig.tight_layout(); save(fig, "figure2_llm_comparison.png")
