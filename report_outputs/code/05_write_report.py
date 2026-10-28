"""Write the report sections into protocol/Systematic Review.docx.

Source  : protocol/Systematic Review (backup before round 2).docx   (so the script can be re-run safely)
Output  : protocol/Systematic Review.docx
Inputs  : report_outputs/tables/*.csv, report_outputs/figures/*.png
Cites   : markers like [[R00313]] become numbered references [n] in order of first appearance;
          reference text comes from results/fulltext/references_ieee.csv.
Run from the project root after scripts 00 to 03:  python report_outputs/code/05_write_report.py
Sections left untouched on purpose: Abstract, 1.1 Background, 2.4.3, 2.6, 2.7, 3.6, 4.2.
"""
import copy, os, re
import pandas as pd
import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph
from common import ROOT, TABLES, FIGS

SRC = os.path.join(ROOT, "protocol", "Systematic Review (backup before round 2).docx")
OUT = os.path.join(ROOT, "protocol", "Systematic Review.docx")
d = docx.Document(SRC)
T = lambda name: pd.read_csv(os.path.join(TABLES, name), keep_default_na=False)

# ------------------------------------------------------------------ helpers
def find(start, style=None, nth=0):
    hits = [p for p in d.paragraphs if p.text.strip().startswith(start) and (style is None or p.style.name == style)]
    if len(hits) <= nth:
        raise KeyError(start)
    return hits[nth]

def clear(p):
    for r in list(p.runs):
        r._r.getparent().remove(r._r)

def set_text(p, text, bold_prefix=None):
    clear(p)
    if bold_prefix:
        p.add_run(bold_prefix).bold = True
    p.add_run(text)
    return p

def new_par(after_el, text="", style="Normal", bold_prefix=None):
    new = OxmlElement("w:p")
    after_el.addnext(new)
    p = Paragraph(new, d._body)
    p.style = d.styles[style]
    if bold_prefix:
        p.add_run(bold_prefix).bold = True
    if text:
        p.add_run(text)
    return p

def chain(after_el, items):
    """Insert several paragraphs in order after after_el; items = [(text, style)]. Returns the last paragraph."""
    last = after_el
    for text, style in items:
        last = new_par(last, text, style)._p
    return Paragraph(last, d._body)

def picture(after_el, name, width):
    p = new_par(after_el)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(os.path.join(FIGS, name), width=Inches(width))
    return p

def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill); tcPr.append(shd)

def table(after_el, header, rows, widths, size=8, align_right=()):
    t = d.add_table(rows=1 + len(rows), cols=len(header))
    t.style = d.styles["Table Grid"]; t.autofit = False
    for ci, h in enumerate(header):
        c = t.rows[0].cells[ci]; c.text = ""
        r = c.paragraphs[0].add_run(h); r.bold = True; r.font.size = Pt(size); shade(c, "E7EEF7")
    for ri, row in enumerate(rows, start=1):
        for ci, v in enumerate(row):
            c = t.rows[ri].cells[ci]; c.text = ""
            r = c.paragraphs[0].add_run(str(v)); r.font.size = Pt(size)
            if ci in align_right:
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for ci, w in enumerate(widths):
        t.columns[ci].width = Inches(w)
    tblPr = t._tbl.tblPr
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
    for row in t.rows:
        for ci, w in enumerate(widths):
            row.cells[ci].width = Inches(w)
        for c in row.cells:
            for p in c.paragraphs:
                p.paragraph_format.space_after = Pt(0); p.paragraph_format.space_before = Pt(0)
    # repeat header row
    trPr = t.rows[0]._tr.get_or_add_trPr(); h = OxmlElement("w:tblHeader"); h.set(qn("w:val"), "true"); trPr.append(h)
    after_el.addnext(t._tbl)
    blank = OxmlElement("w:p"); t._tbl.addnext(blank)
    return Paragraph(blank, d._body)

pct = lambda x, n=1: f"{x * 100:.{n}f}%"

# ------------------------------------------------------------------ numbers from the tables
t31 = T("table_3_1_search_yield.csv"); t32 = T("table_3_2_fulltext_exclusions.csv"); t33 = T("table_3_3_llm_performance.csv")
t33b = T("table_3_3b_disagreement_outcomes.csv"); t33c = T("table_3_3c_pilot_vs_reviewer.csv"); t33d = T("table_3_3d_usage.csv")
cond = T("llm_precision_through_fulltext.csv"); summ = T("llm_agreement_summary.csv").set_index("Unnamed: 0").value
g = lambda m, rule: t33[(t33.Model == m) & (t33.Rule == rule)].iloc[0]
gs, gf, ms, mf = g("Gemini", "include only"), g("Gemini", "include + check manually"), g("Mistral", "include only"), g("Mistral", "include + check manually")
both_r = g("Combined", "Both include"); either_r = t33[t33.Model == "Combined"].iloc[1]
cg, cm_ = cond.set_index("Model").loc["Gemini"], cond.set_index("Model").loc["Mistral"]
ug, um = t33d.set_index("model").loc["gemini"], t33d.set_index("model").loc["mistral"]
dis = t33b.set_index("pair")

# ------------------------------------------------------------------ 2.3 eligibility: replace the open question
p = find("Stage 1 accepted bacterial images")
set_text(p, "Stage 1 and Stage 2 both accepted bacterial images of any type (agar plate and colony photographs, light, fluorescence and electron microscopy, Gram stain), because abstracts often omit the imaging type. Stage 2 flagged the studies whose images show agar plate colonies. The results report these 52 studies next to the full set of 206.")
t23 = d.tables[3]
for cell in t23.rows[1].cells[1:2]:
    cell.paragraphs[0].runs[0].text = "Images of bacteria, including agar plate and colony images (flagged as a subgroup) and microscopy images. Mixed-organism images count if the model analyses bacteria."

# ------------------------------------------------------------------ 2.4 and 2.4.1
p = find("Selection has two stages.")
set_text(p, "Selection ran in two stages. Stage 1 screened titles and abstracts with two LLMs and a human reviewer (Section 2.4.1). Stage 2 screened full texts by code-assisted reading, followed by a human hand-check of a random half (Section 2.4.2). Section 2.4.4 explains how we compared the two LLMs.")
p = find("Two LLMs from different vendors screened every record")
set_text(p, "Two LLMs from different vendors screened every record, and neither saw the other's output: Gemini (gemini-3.1-pro-preview, thinking budget of 512 tokens) and Mistral (mistral-large-4). Both ran through the vendor API at temperature 0. Each request carried 20 records, each with title, abstract (cut at 2,500 characters), year, source, document type and keywords, plus the fixed system prompt tiab-v2 (Annex A). A script retried requests that hit rate limits or time-outs and wrote every response to a checkpoint file.")
p = find("The prompt turns the eligibility criteria")  # unchanged text, kept as written in round 1
p = find("Before the full run we screened a pilot")
set_text(p, "Before the full run, we screened a pilot of 300 records, drawn at random and stratified by source database (seed 42), on 17 October 2026. One human reviewer screened 100 of these records blind to the model output and resolved the pilot records that the models flagged. We computed percent agreement and Cohen's kappa between the two models and between each model and the reviewer, and the recall of each model against the reviewer's inclusions. The reviewer approved the pilot, and the full run of the remaining 8,556 records took place on 17 and 18 October 2026.")
p = find("When both models returned the same decision")
set_text(p, "When both models returned the same decision, that decision stood. A record went to the human reviewer when the models disagreed or when either model returned check manually. The reviewer read the abstract of each such record, decided include or exclude, and recorded a reason. The reviewer could also overturn a unanimous model decision. The repository holds the model identifiers, run dates, settings, token usage and raw outputs for every record (Annex A).")

# ------------------------------------------------------------------ 2.4.2 full-text screening
h242 = find("2.4.2. Stage 2", "Heading 3")
b = [find("[Reviewers, independence"), find("[Inaccessible full texts"), find("[Coded reasons for exclusion")]
texts = [
 "Stage 2 applied the exclusion codes of Table 2.3 to the full text of each report. We retrieved PDFs through each record's DOI from open-access sources. Reports without an accessible full text left the review with code E12 (full text not accessible), and reports found to be in a language other than English left with code E13.",
 "First, we screened the full texts by code. A Python script (fulltext_screening.py) extracted the text of each PDF and counted deep learning terms (for example CNN, ResNet, YOLO, U-Net, transformer), shallow ML terms (for example SVM, random forest, k-NN) and evaluation metric terms. The counts ranked the papers for reading and cross-checked each decision. An LLM then read the abstract and methods of every paper and assigned include or exclude, one exclusion code and a one-line reason, which the script stores for each paper. The script also marked whether the images showed agar plate colonies.",
 "Second, a human reviewer reads and hand-checks a random half of the 354 papers to test whether the LLM-assisted decisions are right. We draw the sample once, as a simple random sample without replacement (177 papers, seed 42). The reviewer reads each sampled paper without seeing the LLM decision, then records include or exclude and a reason. We compare the two sets of decisions with percent agreement, Cohen's kappa, and the precision and recall of the LLM-assisted include decisions. Where the reviewer and the LLM-assisted decision differ, the reviewer's decision replaces it.",
 "Each exclusion carries one code. The counts per code feed the PRISMA diagram (Figure 1) and Table 3.2.",
]
for bp, tx in zip(b + [None], texts[:3]):
    pass
for bp, tx in zip(b, texts[:3]):
    set_text(bp, tx); bp.style = d.styles["Normal"]
new_par(b[2]._p, texts[3])

# 2.4.4 comparison of the two LLMs (after the untouched 2.4.3 block)
h243 = find("2.4.3. Evidence tiers", "Heading 3")
ph243 = find("[Decide whether to classify studies")
h244 = new_par(ph243._p, "2.4.4. Comparison of the two LLMs", "Heading 3")
chain(h244._p, [
 ("We compared Gemini and Mistral on all 8,856 screened records. We measured agreement between the models with percent agreement and Cohen's kappa on the three decisions (include, check manually, exclude), and counted which exclusion codes each model used. We measured accuracy against the final decision after human resolution (395 records included, 8,461 excluded), as sensitivity, specificity, precision, F1 and overall accuracy. We scored two rules: include only, and include or check manually, because the pipeline sends check-manually records to the reviewer. We tested whether the two models differ in correct classification with an exact McNemar test.", "Normal"),
 ("This reference has a limit. The reviewer read the records that the models disagreed on or flagged, but not the records that both models excluded, so those count as true negatives and the sensitivity figures are upper bounds. Two further checks do not share this limit: the 100 pilot records the reviewer screened blind, and the share of each model's includes that survived full-text screening. We also report requests, tokens and run time from the usage log.", "Normal"),
])

# ------------------------------------------------------------------ 2.5 data extraction
p = find("[Top-down checklist")
set_text(p, "We extracted data from the full texts of the 206 included studies into one table (extraction_table.xlsx). An LLM read each paper (abstract, methods, results and data statement) and filled the fields below. A field that a paper does not report holds N/A. A second reviewer has not yet checked the table.")
bul = [find("Bibliographic:"), find("Dataset:"), find("Acquisition and preprocessing:"), find("Model:"), find("Outcomes:")]
vals = [("Bibliographic:", " authors, year, journal, DOI, country of the author affiliations."),
        ("Dataset:", " organisms, type of data, how the data were collected, dataset name and size, data availability."),
        ("Factors:", " acquisition, preprocessing, augmentation and other factors the authors tied to performance, plus scope notes for borderline studies."),
        ("Model:", " model or system, validation scheme, code availability."),
        ("Outcomes:", " reference standard; accuracy, precision, recall or sensitivity, specificity, F1, AUC, mAP, IoU or Dice, counting error; other reported outcomes.")]
for bp, (lab, tx) in zip(bul, vals):
    set_text(bp, tx, bold_prefix=lab)
new_par(bul[-1]._p, "From the free text we coded model family, reference-standard category, evaluation design, data and code availability, genera and examined factors with keyword rules (00_features.py, Annex A). For accuracy we took the first headline value for the best model on test or validation data, and corrected 15 entries by hand where the rule picked the wrong number. Studies without a single comparable accuracy value stay out of the accuracy summaries. The values are not harmonised for dataset, metric definition or data split.")

# ------------------------------------------------------------------ 3.1 study selection
p = find("[Counts by database")
n_sc = t31[t31.Database == "Scopus"].iloc[0]
set_text(p, "The searches returned 12,213 records (Table 3.1). Removing 404 duplicates left 11,809 records, and 2,953 more left before screening (2,893 published before 2015, 48 without an abstract, 12 published after the cut-off). The two LLMs and the reviewer screened 8,856 titles and abstracts and kept 395. We could not retrieve the full text of 38 of these, and 3 more left because they were not in English (2) or did not analyse bacteria (1), which left 354 reports for full-text assessment (Figure 1). Full-text screening excluded 148 reports, mostly because the model was not deep learning (95) or because the images showed no bacteria (25) (Table 3.2). The review includes 206 studies, 52 of them on agar plate colony images. Scopus alone supplied 191 of the 206 included studies, PubMed 8, IEEE Xplore 6 and Embase 1; SpringerLink supplied none.")
cap = find("Table 3.1. Search yield")
hdr = ["Database", "Records exported", "Duplicates removed", "Unique kept", "Removed before screening", "Screened", "Included at title/abstract", "Included after full text"]
rows = [[r.Database] + [f"{int(r[c]):,}" for c in t31.columns[1:]] for _, r in t31.iterrows()]
after = table(cap._p, hdr, rows, [1.0, 0.8, 0.8, 0.7, 0.85, 0.7, 0.85, 0.8], size=8, align_right=range(1, 8))
set_text(cap, "Table 3.1. Search yield and study flow by database. A record found in several databases counts under the first of PubMed, IEEE Xplore, Embase, SpringerLink and Scopus that holds it.")
fig1cap = find("Figure 1. PRISMA")
pic = picture(fig1cap._p.getprevious(), "figure1_prisma.png", 4.5)
set_text(fig1cap, "Figure 1. PRISMA 2020 flow diagram.")
cap2 = find("Table 3.2. Reports excluded")
set_text(cap2, "Table 3.2. Reports excluded at the full-text stage (n = 148).")
rows = [[r.Exclusion_code, r.Exclusion_reason, int(r.Reports)] for _, r in t32.iterrows()]
rows.append(["", "Total", int(t32.Reports.sum())])
after = table(cap2._p, ["Code", "Reason", "Reports"], rows, [0.6, 5.0, 0.8], size=8.5, align_right=(2,))
p = find("[Add LLM-screening validation")
set_text(p, "[Hand-check result: agreement between the LLM-assisted full-text decisions and the human decisions in the random half (n = 177); fill in after the reviewer completes the check (fulltext_handcheck_agreement.csv).]")
h311 = new_par(p._p, "3.1.1. Gemini versus Mistral at title and abstract screening", "Heading 3")
pa = new_par(h311._p, f"The two models gave the same decision for 8,420 of 8,856 records ({pct(summ.agreement_3class)}; kappa {summ.kappa_3class:.2f}). Both excluded 8,075 records and both included 260 (Figure 2a). Both models excluded for the same reason code in {pct(summ.same_exclusion_code_share, 0)} of the 8,075 shared exclusions. Mistral returned check manually for 283 records and Gemini for 125, and they agreed on 85.")
pb = new_par(pa._p, "The models differed in how they applied the criteria (Figure 2b). Gemini excluded 965 records for lack of deep learning (E6) against 403 for Mistral, while Mistral sent more records with an unstated method to manual check. Mistral also used the hardware-only code E10 for 18 records, and Gemini never used it.")
cap33 = new_par(pb._p, "Table 3.3. Accuracy of each model and of the combined rules at title and abstract screening, against the final decision after human resolution (395 included, 8,461 excluded). Include or check manually counts a check-manually record as positive.", "Caption")
pct1 = lambda x: f"{x * 100:.1f}"
rows = []
for lab, r in [("Gemini, include only", gs), ("Gemini, include or check manually", gf), ("Mistral, include only", ms), ("Mistral, include or check manually", mf),
               ("Both include", both_r), ("Either flags (sent to reviewer)", either_r)]:
    rows.append([lab, int(r.Records_flagged), int(r.TP), int(r.FP), int(r.FN), pct1(r.Sensitivity), pct1(r.Specificity), pct1(r.Precision), pct1(r.F1), pct1(r.Accuracy)])
after = table(cap33._p, ["Model and rule", "Flagged", "TP", "FP", "FN", "Sens. (%)", "Spec. (%)", "Prec. (%)", "F1 (%)", "Acc. (%)"], rows,
              [1.9, 0.55, 0.4, 0.4, 0.4, 0.55, 0.55, 0.55, 0.5, 0.5], size=8, align_right=range(1, 10))
note = new_par(after._p, "Both-include and either-flags rows partly follow from the pipeline itself: the reviewer did not read the 8,075 records that both models excluded, so those rows overstate sensitivity.")
note.runs[0].italic = True
figp = picture(note._p, "figure2_llm_comparison.png", 6.3)
figc = new_par(figp._p, "Figure 2. Agreement between Gemini and Mistral on 8,856 records (a) and exclusion codes each model assigned (b).", "Caption")
p1 = new_par(figc._p, f"Against the final decision, Gemini's include decisions had a sensitivity of {pct(gs.Sensitivity)} and a precision of {pct(gs.Precision)}, and Mistral's had {pct(ms.Sensitivity)} and {pct(ms.Precision)} (Table 3.3). Counting check manually as a positive raised sensitivity to {pct(gf.Sensitivity)} for Gemini and {pct(mf.Sensitivity)} for Mistral, and the number of flagged records to {int(gf.Records_flagged)} and {int(mf.Records_flagged)}. Sending every record that either model flagged to the reviewer meant reading {int(either_r.Records_flagged)} of 8,856 records (8.8%). The two models did not differ in how often they classified a record correctly (exact McNemar test, {int(summ.mcnemar_b)} against {int(summ.mcnemar_c)} discordant records, p = {summ.mcnemar_p:.2f}).")
p2 = new_par(p1._p, f"The 100-record pilot that the reviewer screened blind gives an independent check. The reviewer included 2 records, and both models flagged both. Each model agreed with the reviewer on 96 of 100 records (kappa 0.48) and flagged 4 of the 98 records the reviewer excluded. Two inclusions cannot support a recall estimate: the 95% confidence interval for 2 of 2 runs from 16% to 100%.")
p3 = new_par(p2._p, f"The disagreements show what each model adds. Of the 197 records where Gemini excluded and Mistral asked for a manual check, 59 (30%) ended up included, so Mistral's caution recovered inclusions that Gemini would have dropped. Of the 128 records that Gemini included and Mistral excluded, only 2 (1.6%) ended up included. Of the {int(cg.Included)} records Gemini included, {int(cg.Included_after_fulltext)} ({pct(cg.Included_after_fulltext / cg.Included, 0)}) survived full-text screening, against {int(cm_.Included_after_fulltext)} of {int(cm_.Included)} ({pct(cm_.Included_after_fulltext / cm_.Included, 0)}) for Mistral.")
p4 = new_par(p3._p, f"Mistral cost more to run. Gemini completed 447 requests in {ug.Seconds_ok / 3600:.1f} hours ({ug.Seconds_per_successful_request:.0f} s per request) after {int(ug.Failed_requests):,} rate-limit retries, and used {ug.Input_tokens / 1e6:.2f} million input and {ug.Output_tokens / 1e6:.2f} million output tokens. Mistral completed 444 requests in {um.Seconds_ok / 3600:.1f} hours ({um.Seconds_per_successful_request:.0f} s per request) after 7 time-outs, and used {um.Input_tokens / 1e6:.2f} million input and {um.Output_tokens / 1e6:.2f} million output tokens, 3.4 times the output of Gemini.")

# ------------------------------------------------------------------ renumber captions + 3.2 characteristics
set_text(find("Table 3.3. Overview of the"), "Table 3.4. Overview of the 52 studies that analysed agar plate colony images: organisms, task, model, reference standard and best reported accuracy (as extracted). Supplementary Table S1 lists all 206 included studies.")
set_text(find("Figure 2. Publication trends."), "Figure 3. Publication trends of the 206 included studies, split by image type.")
set_text(find("Figure 3. Bacterial species"), "Figure 4. Genera analysed (a), model families (b) and tasks (c).")
set_text(find("Table 3.4. Species and datasets"), "Table 3.5. Datasets, data and code availability, and validation design.")
set_text(find("Figure 4. Reported accuracy"), "Figure 5. Best reported accuracy by reference standard (a) and model family (b).")
set_text(find("Table 3.5. Studies that varied"), "Table 3.6. Agar plate studies that examined acquisition, preprocessing or augmentation factors, with the factors and outcomes as extracted.")
set_text(find("Figure 5. Effect of acquisition"), "Figure 6. Share of studies that report each acquisition, preprocessing or modelling factor.")
set_text(find("Table 3.6. Studies comparing morphology"), "Table 3.7. Studies that use morphology, texture, topology or motility features.")
set_text(find("Figure 6. QUADAS-2"), "Figure 7. QUADAS-2 results.")
set_text(find("Table 3.7. Methodological quality"), "Table 3.8. Methodological quality (QUADAS-2) of each included study (L, Low; U, Unclear; H, High).")

# 3.2.1
h321 = find("3.2.1. Publication trends", "Heading 3")
fig3cap = find("Figure 3. Publication trends")
t_a = new_par(h321._p, "The number of included studies grew after 2021: 185 of 206 (90%) appeared in 2022 or later, 54 in 2025 and 50 in 2026 up to the search cut-off (Figure 3). Agar plate colony studies followed the same curve, with 32 of the 52 (62%) published in 2025 or 2026. CNN classifiers were the primary model family in 107 studies (52%), object detectors such as YOLO and R-CNN in 54 (26%), segmentation networks in 23 (11%), transformers in 15 (7%), generative models in 3 and LLM or vision-language systems in 4 (Figure 4b). None of those 4 studies used an LLM or vision-language model to read bacterial images. They used the Segment Anything Model for annotation or augmentation [[R01124]] [[R02813]], a large-model distillation step in a colony detector [[R00363]], or a pathology foundation model [[R02417]].")
picture(fig3cap._p.getprevious(), "figure3_publication_trends.png", 5.2)
# 3.2.2
h322 = find("3.2.2. Species, tasks", "Heading 3")
fig4cap = find("Figure 4. Genera analysed")
new_par(h322._p, "Classification or identification was the task in 141 studies (68%), detection in 77 (37%), segmentation in 40 (19%), counting in 26 (13%), antimicrobial susceptibility testing in 21 (10%) and training-data generation in 9 (4%); tasks overlap (Figure 4c). Escherichia appeared in 70 studies (34%), Staphylococcus in 38 (18%), Mycobacterium in 30 (15%, none on agar plates), Pseudomonas in 25 (12%), Bacillus in 21 and Klebsiella in 17 (Figure 4a). Among the 52 agar plate studies, Escherichia (28), Staphylococcus (13) and Pseudomonas (13) led. Besides agar plates (52 studies, 25%), the images came from acid-fast smears (27), fluorescence microscopy (27), Gram-stain microscopy (24), microfluidic or time-lapse imaging (21), histopathology slides (14) and hyperspectral imaging (13); a study can fall in several groups. Table 3.4 lists the 52 agar plate studies.")
picture(fig4cap._p.getprevious(), "figure4_genera_models_tasks.png", 6.5)
t34 = T("table_3_4_agar_plate_studies.csv")
rows = [[f"[[{r['Record ID']}]]", r.Year, r.Organisms, r.Task, r.Model, r["Reference standard"], r["Best reported accuracy (as extracted)"]] for _, r in t34.iterrows()]
cap34 = find("Table 3.4. Overview")
after = table(cap34._p, ["Ref.", "Year", "Organisms", "Task", "Model", "Reference standard", "Best reported accuracy"], rows, [0.45, 0.4, 1.2, 0.7, 1.35, 1.1, 1.3], size=7)

# 3.3 RQ1
p = find("[Species/genera studied")
t35 = T("table_3_5_datasets_availability_validation.csv")
set_text(p, "The evidence rests on a few genera. Escherichia, Staphylococcus and Pseudomonas lead the agar plate studies, and colony-level species identification covered at most 32 species per study: a 32-species urine pathogen system reached 90.6% top-1 accuracy [[R04157]], a 10-species system on 418 strains exceeded 98% [[R01626]], and a hologram-based system identified 86.6% of 232 test isolates to species level [[R00810]].")
q1 = new_par(p._p, "Few public datasets recur. AGAR appears in 7 studies, all on agar plates (for example [[R00313]] and [[R04141]]). DIBaS appears in 14 studies, none on agar plates, because it holds microscopy images. Other public sets serve one or two studies, such as a 24-class colony dataset on Figshare used in [[R00812]] and [[R02594]]. Seventy-five studies (36%) share their data publicly and 50 (24%) share on request only; the agar plate studies share more often (24 of 52, 46%). Code is public in 35 studies (17%) (Table 3.5).")
q2 = new_par(q1._p, "A single headline accuracy was extractable for 114 studies (55%). The median was 95.0% (IQR 90.0 to 98.5; range 43 to 100). The 26 agar plate studies had a median of 96.7% (IQR 90.7 to 98.7) and the other 88 studies 94.4% (88.4 to 98.2). Accuracy depended on the reference standard (Figure 5a). Studies that measured against manual annotation or counts (n = 68) had a median of 97.4%, studies that used known strain or dataset labels (n = 22) 94.7%, and studies that used culture, biochemical tests or plate counts (n = 17) 90.0% (IQR 80.0 to 92.0). Only 3 of 206 studies used MALDI-TOF and 5 used sequencing or PCR as the reference standard. By model family, transformers had the highest median (98.0%, n = 11), followed by CNN classifiers (95.0%, n = 75), object detectors (93.9%, n = 13) and segmentation networks (90.7%, n = 11) (Figure 5b). Datasets, metrics and data splits differ between studies, so these medians describe what authors reported and do not rank the models.")
q3 = new_par(q2._p, "Validation design limits how far these numbers travel. Authors stated independent, external or held-out validation in 49 studies (24%) and cross-validation in 37 (18%); the rest used one split or gave too little detail. The external tests show the gap: a urine-plate YOLO model scored 0.99 internally and 100% on a 91-image external set [[R01401]], while a hologram system misidentified 17 of 64 external strains at species level [[R00810]].")
cap35 = find("Table 3.5. Datasets")
rows = [[r.Item, f"{int(r['All included (n=206)'])} ({r['All included (%)']:.0f}%)" if r.Item != "Studies" else "206", f"{int(r['Agar plate studies (n=52)'])} ({r['Agar plate studies (%)']:.0f}%)" if r.Item != "Studies" else "52"] for _, r in t35.iterrows()]
table(cap35._p, ["Item", "All included (n = 206)", "Agar plate studies (n = 52)"], rows, [3.6, 1.45, 1.45], size=8.5, align_right=(1, 2))
fig5cap = find("Figure 5. Best reported")
picture(fig5cap._p.getprevious(), "figure5_accuracy.png", 6.5)

# 3.4 RQ2
p = find("[Acquisition devices and conditions")
set_text(p, "The extraction recorded which factors each study examined or listed as influencing performance. Species, strain or concentration appeared in 55 studies (27%), augmentation or synthetic data in 48 (23%), image or patch size in 37 (18%), preprocessing in 33 (16%) and imaging device or magnification in 31 (15%) (Figure 6). Agar plate studies more often examined the growth medium or background (15 studies, 29%), incubation time (15, 29%) and illumination (11, 21%). Table 3.6 lists the 42 agar plate studies that examined at least one acquisition, preprocessing or augmentation factor.")
r1 = new_par(p._p, "The extraction holds the factors but seldom a paired accuracy for each level of a factor, so we can quantify an effect only where authors printed one. Three agar plate studies tested a mismatch between training and test conditions, and accuracy fell in all three. A two-agar study reported 100% accuracy under controlled imaging and 72.9 to 83.2% under uncontrolled imaging [[R02743]]. A second study reached 96.7% in-domain and 86% when trained on controlled and tested on uncontrolled images [[R05626]]. A third reported cross-condition accuracy of 0.19 to 0.56 across glass types and lighting, against 0.99 for its best model [[R02143]]. Domain adaptation recovered part of the loss: a domain-adversarial network raised accuracy in new magnifications and modalities by up to 54.5% [[R02609]].")
r2 = new_par(r1._p, "Augmentation and preprocessing helped where authors tested them. Accuracy rose from 91.4% to 97.1% with augmentation in hyperspectral viability imaging [[R02750]], RGB input gave 93.0% against 59% for grayscale in stained-sample classification [[R05195]], and pre-training lifted a ResNet-18 from 98.57% to 99.70% [[R06371]]. Three agar plate studies trained colony detectors from 25 to 100 real images plus synthetic colonies [[R02531]] [[R02813]] [[R04805]]. None of the studies we extracted removed the loss under changed conditions, and only 13 of the 52 agar plate studies stated independent, external or held-out validation.")
cap36 = find("Table 3.6. Agar plate studies")
t36 = T("table_3_6_agar_studies_acquisition_preprocessing.csv")
rows = [[f"[[{r['Record ID']}]]", r["Factors examined or varied (as extracted)"], r["Other reported outcomes (as extracted)"]] for _, r in t36.iterrows()]
table(cap36._p, ["Ref.", "Factors examined or varied", "Other reported outcomes"], rows, [0.5, 2.6, 3.4], size=7)
fig6cap = find("Figure 6. Share of studies")
picture(fig6cap._p.getprevious(), "figure6_factors_examined.png", 5.6)

# 3.5 RQ3
p = find("[Studies using shape, margin")
set_text(p, "Eleven studies used morphology, texture, topology or motility features, 4 of them on agar plates (Table 3.7). Few compared feature-based models with raw-image models. A leakage-aware study fused handcrafted morphology descriptors with CNN outputs and reported balanced accuracy of 0.950 to 0.970 for the fusion models against 0.550 for morphology alone [[R01073]]; the extraction holds no raw-image-only value for the same split. In hyperspectral imaging, the spectral profile alone reached 85% and the binary mask (morphology) alone 27%, against 92% for the fused network [[R04927]]. A CNN scored 0.98 in biofilm detection, and two forest models on Haralick texture and colour features scored slightly lower [[R06695]]. The other studies paired topological features with EfficientNet [[R02126]], classified swarming patterns [[R02939]] or fitted shape descriptors after deep localisation [[R04273]], and none reported a raw-image comparison.")
new_par(p._p, "The data do not let us test H1. No included study compared the same deep model with and without morphology or motility features on the same agar plate images. Where handcrafted features stood alone, they scored below deep models or below fusion models. Whether adding them to a raw-image model helps remains open.")
cap37 = find("Table 3.7. Studies that use")
t37 = T("table_3_7_morphology_motility_features.csv")
rows = [[f"[[{r['Record ID']}]]", r.Year, r["Agar plate images"], r["Feature type and model"], r["Comparison with raw-image model"], r["Result as extracted"]] for _, r in t37.iterrows()]
table(cap37._p, ["Ref.", "Year", "Agar", "Feature type and model", "Comparison with raw-image model", "Result as extracted"], rows, [0.45, 0.4, 0.4, 2.0, 1.55, 1.7], size=7)

# ------------------------------------------------------------------ 4 Discussion
b = [find("[Accuracy against reference standards"), find("[Species and dataset coverage"), find("[Acquisition, preprocessing and augmentation (RQ2)"),
     find("[Morphology/motility features versus"), find("[Role of LLM/VLM"), find("[Methodological quality and reporting")]
vals = [
 ("Accuracy against reference standards (main question). ", "Authors report a median headline accuracy of 95.0% (IQR 90.0 to 98.5; n = 114) and 96.7% for agar plate studies (n = 26). Accuracy is highest against manual annotation or known labels (97.4%, 94.7%) and lowest against culture-based references (90.0%). Only 3 studies used MALDI-TOF and 5 used sequencing or PCR, so accuracy against the strongest reference standards is barely tested."),
 ("Species and dataset coverage (RQ1). ", "Escherichia (34% of studies) and Staphylococcus (18%) dominate. AGAR serves 7 studies and DIBaS 14. Data are public in 36% of studies and code in 17%."),
 ("Acquisition, preprocessing and augmentation (RQ2). ", "Accuracy fell when test conditions differed from training conditions in the 3 agar plate studies that reported such a test, to 72.9 to 83.2%, 86% and 0.19 to 0.56. Augmentation and domain adaptation recovered part of the loss, and none removed it."),
 ("Morphology and motility features versus raw-image models (RQ3). ", "No study isolates the contribution of morphology or motility features to a deep model, so H1 stays untested."),
 ("Role of LLM and vision-language systems. ", "No included study used an LLM or vision-language model to identify bacteria in images. As screening tools, Gemini and Mistral agreed on 95.1% of 8,856 records (kappa 0.59) and neither was more accurate overall, but each missed records the other caught, and 501 records still needed a human decision."),
 ("Methodological quality and reporting. ", "Independent or external validation appears in 24% of studies, and 155 of 206 (75%) do not state code availability. The risk-of-bias assessment appears in Section 3.6."),
]
for bp, (lab, tx) in zip(b, vals):
    set_text(bp, tx, bold_prefix=lab)

p = find("[Strengths: transparent process")
set_text(p, "The review has three strengths. Every record carries its decision, reason code and model output in the repository, so a reader can trace any exclusion. Two LLMs from different vendors screened each record without seeing each other, a pilot measured them against a human reviewer, and a human resolved every disputed record. The search covered five databases and 12,213 records, and the review includes 206 studies.")
l1 = new_par(p._p, "The review has limits. We included English-language journal articles only. Scopus supplied 191 of the 206 included studies, and our SpringerLink and Embase exports hold far fewer records than the search logs report (242 of 5,473 and 25 of 4,019), so we may have missed studies. The search strings contain no LLM or agar terms. We could not retrieve 38 reports, which left the review. The human reviewer did not read the 8,075 records that both LLMs excluded, and the blind pilot held only 2 inclusions, so we cannot state the recall of the screening step with precision. An LLM carried out the full-text screening and the data extraction, the hand-check covers a random half of the papers [update once the hand-check is complete], and no second reviewer has checked the extraction table. Headline accuracies come from free text and are not harmonised, and datasets, metrics and splits differ too much to pool. The 2026 count stops at 13 October.")
p = find("[Short answer to the main question")
set_text(p, "Deep learning models report high accuracy when they identify, detect or count bacteria in images: a median of 95.0% across 114 studies and 96.7% across 26 agar plate studies. The evidence does not yet support unsupervised use in the laboratory. It rests on a few genera and datasets (RQ1), and only a quarter of the studies state independent or external validation. Accuracy fell by more than 10 percentage points when test conditions differed from training conditions (RQ2). No study tests whether morphology or motility features add to a raw-image model (RQ3), and few studies measure against MALDI-TOF or sequencing. Future studies should test on independent plates and imaging conditions, report against MALDI-TOF or sequencing, share data and code, and compare feature-based models with raw-image baselines.")

# ------------------------------------------------------------------ Declarations and Annex A
p = find("Data and code availability.")
set_text(p, " The extraction table, coded variables, screening decisions, scripts and the code that draws every table and figure are in the project repository (folders results, scripts and report_outputs). [Add repository URL.]", bold_prefix="Data and code availability.")
p = find("[Repository link and description")
set_text(p, "The repository holds everything needed to rebuild the tables and figures. Run the scripts in report_outputs/code in numeric order from the project root: 00_features.py, 01_selection_and_llm_comparison.py, 02_included_studies.py and 03_fulltext_handcheck_sample.py, and 04_handcheck_agreement.py after the hand-check. Python 3 with pandas, numpy, matplotlib and openpyxl is enough. The screening scripts need the API keys listed in the README.")
capA = find("Table A1. Contents")
rowsA = [("protocol/", "Search strategy and criteria (.xlsx), this review document, screening prompt tiab-v2"),
 ("data/raw, data/deduplicated, data/screening_input", "Database exports, deduplicated records and log, records sent to screening and records removed before it"),
 ("results/pilot, results/full_run, results/final", "Pilot and full-run model outputs, reviewer decisions, final title and abstract decisions, PRISMA counts"),
 ("results/fulltext", "Full-text screening decisions, extraction table (206 studies), raw extraction, IEEE references"),
 ("scripts/", "Pipeline: deduplication, screening, full-text screening, extraction table, download and reference tools"),
 ("report_outputs/tables", "Data behind every table and figure, coded extraction table, hand-check sample"),
 ("report_outputs/figures", "Figures 1 to 6 as PNG"),
 ("report_outputs/code", "Scripts that build the tables, figures and this document's text")]
table(capA._p, ["Folder", "Contents"], rowsA, [2.4, 4.1], size=8.5)

# ------------------------------------------------------------------ citations and references
refs = pd.read_csv(os.path.join(ROOT, "results", "fulltext", "references_ieee.csv"), encoding="utf-8-sig").set_index("Record_ID").Reference
order = []
def number(m):
    rid = m.group(1)
    if rid not in order:
        order.append(rid)
    return f"[{order.index(rid) + 1}]"
body = d.element.body
for p_el in body.iter(qn("w:p")):
    for t_el in p_el.iter(qn("w:t")):
        if t_el.text and "[[" in t_el.text:
            t_el.text = re.sub(r"\[\[(R\d+)\]\]", number, t_el.text)
            t_el.text = t_el.text.replace("] [", "], [")
p = find("[Numbered references in the order cited")
set_text(p, f"[1] {refs[order[0]]}")
last = p
for i, rid in enumerate(order[1:], start=2):
    last = new_par(last._p, f"[{i}] {refs[rid]}")
for q in [p] + ([last] if last is not p else []):
    pass
d.save(OUT)
left = sum(1 for t_el in body.iter(qn("w:t")) if t_el.text and "[[" in t_el.text)
print("saved", OUT, "| cited", len(order), "| unresolved markers", left)
