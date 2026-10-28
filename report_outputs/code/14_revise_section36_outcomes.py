"""Revise only Results 3.6, using the supplied examples as presentation references.

All judgements and analyses remain unchanged. The first run freezes the current
manuscript so later author edits outside this snapshot are not silently replaced.
"""
from copy import deepcopy
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import csv, hashlib, json, shutil
from lxml import etree
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from docx.table import Table

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'protocol/Systematic Review.docx'
BACKUP = ROOT / 'protocol/Systematic Review (backup before section 3.6 revision 2026-10-28).docx'
OUT = ROOT / 'results/final/quadas2_review'
if not BACKUP.exists():
    shutil.copy2(REPORT, BACKUP)
d = Document(BACKUP)
start = next(p._p for p in d.paragraphs if p.text.startswith('3.6. Quality Assessment'))
end = next(p._p for p in d.paragraphs if p.text == '4. Discussion')
nodes = []
n = start.getnext()
while n is not end:
    nodes.append(n)
    n = n.getnext()
tables = [deepcopy(n) for n in nodes if n.tag == qn('w:tbl')]
images = [deepcopy(n) for n in nodes if n.xpath('.//w:drawing')]
assert len(tables) == len(images) == 2

def outside_bytes():
    return b''.join(etree.tostring(n, method='c14n') for n in d.element.body
                    if n not in nodes)

outside_before = outside_bytes()
for n in nodes:
    n.getparent().remove(n)
cursor = start
saved_text = ['3.6. Quality Assessment and Risk of Bias']

def para(text, heading=False, caption=False):
    global cursor
    el = OxmlElement('w:p')
    cursor.addnext(el)
    p = Paragraph(el, d._body)
    p.style = d.styles['Caption' if caption else 'Normal']
    p.add_run(text)
    if heading:
        p.runs[0].bold = True
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(3)
    if caption:
        p.paragraph_format.keep_with_next = text.startswith('Table')
    cursor = el
    saved_text.append(text)

def insert(el):
    global cursor
    cursor.addnext(el)
    cursor = el

summary = json.loads((OUT / 'analysis_summary.json').read_text())
assert summary['n'] == 206 and summary['overall_risk'] == {'U': 122, 'H': 82, 'L': 2}
with (OUT / 'manual_assessments.tsv').open(newline='', encoding='utf-8-sig') as f:
    decisions = list(csv.DictReader(f, delimiter='\t'))
assert len(decisions) == 206
for domain, counts in summary['domains'].items():
    assert {k: sum(r[domain] == k for r in decisions) for k in counts} == counts

para('All 206 included reports were appraised with the adapted QUADAS-2 (Table 3.9; Figure 8). Overall risk of bias was High in 82 reports (39.8%; Wilson 95% CI 33.4-46.6%), Unclear in 122 (59.2%; 52.4-65.7%) and Low in 2 (1.0%; 0.3-3.5%). The two overall Low-risk reports were R00004 and R05464. Unclear ratings indicate insufficient information to establish whether the required safeguards were present. The most frequent reporting gaps concerned source sampling, separation of biological source units between data partitions, and reference-standard independence. These findings derive from the single-AI source appraisal described in Section 2.6; independent human verification has not been completed.')
para('Table 3.9. Adapted QUADAS-2 results for 206 reports: risk of bias in four domains and overall, and applicability concerns in three domains and overall. Values are n (%); percentages use all 206 reports and may differ from 100% in total because of rounding.', caption=True)
insert(tables[0])
insert(images[0])
para('Figure 8. Distribution of adapted QUADAS-2 risk-of-bias and applicability ratings across 206 reports. Green, Low; orange, High; yellow, Unclear. Small segments are labelled by count only; complete percentages are in Table 3.9. Applicability concerns are assessed separately from risk of bias.', caption=True)

para('Sample selection (D1)', heading=True)
para('Sample selection was Low risk in 4 reports (1.9%), High in 35 (17.0%) and Unclear in 167 (81.1%). High ratings reflected exclusions of difficult or reference-discordant samples, including early or mixed cultures, poor-quality images and samples with unresolved expert labels. The predominance of Unclear ratings reflected limited descriptions of recruitment, source-unit sampling and exclusions. This domain therefore provided the least reassurance about the representativeness of the evaluated samples.')

para('Index test and model evaluation (D2)', heading=True)
para('Index-test risk was Low in 53 reports (25.7%), High in 45 (21.8%) and Unclear in 108 (52.4%). This domain had the largest number of High ratings. Identified mechanisms included use of test performance to guide training or model selection, and random partitioning of correlated crops or augmented copies. For example, R01980 stopped training after test accuracy exceeded a target, while R02940 used test accuracy for early stopping. Better-protected evaluations included an independent 76-strain test in R01626 and experiment-level holdouts in R01853. Study IDs refer to the source-linked records in Supplementary Table S3.')

para('Reference standard (D3)', heading=True)
para('Reference-standard risk was Low in 68 reports (33.0%), High in 10 (4.9%) and Unclear in 128 (62.1%). High ratings included evaluation against unconfirmed algorithm-generated masks, clinical infection labels inferred from organism categories, and revision of reference diagnoses after inspection of model disagreements. Low ratings required a valid reference for the actual outcome and adequate independence from the index model. Expert masks and manual counts could support segmentation or counting, whereas organism identification required an appropriate identity reference. Limited reporting of verification and reference independence accounted for many Unclear judgements.')

para('Flow and timing (D4)', heading=True)
para('Flow and timing was Low risk in 128 reports (62.1%), High in 31 (15.0%) and Unclear in 47 (22.8%). High ratings reflected losses or exclusions that restricted the reported performance to a selected evaluable subset, inconsistent evaluation denominators, or incomplete reference verification. For example, R03920 excluded 34 scanning failures from 320 slides before accuracy analysis. Performance calculated after such failures are removed describes the successfully processed subset and may overstate performance across all attempted samples.')

para('Applicability concerns', heading=True)
para('Overall applicability concern was Low in 64 reports (31.1%), High in 94 (45.6%) and Unclear in 48 (23.3%). Sample applicability contributed the most High ratings (87; 42.2%), reflecting restrictions in organism spectrum or sampling relative to the intended use. Index-test applicability was Low in 205 reports (99.5%) under the broad bacterial-image scope of this review. Reference applicability was High in 13 reports (6.3%), where the reference-defined outcome did not adequately match the intended target. A compatible task or image pipeline therefore did not, by itself, establish that the evaluated sample spectrum and reference definitions supported the proposed use.')

para('Agar-plate subgroup', heading=True)
para('Among the 52 agar-plate reports, overall risk was High in 16 (30.8%) and Unclear in 36 (69.2%); none was overall Low. Among the other 154 reports, 66 (42.9%) were High, 86 (55.8%) Unclear and 2 (1.3%) Low. These are descriptive report-level distributions; repeated use of public datasets means that reports do not necessarily represent independent cohorts. Supplementary Figure S1a-d presents the ratings for every report, and Supplementary Table S3 provides the seven domain/applicability rationales, signalling answers and source locations.')

para('Sensitivity analysis by overall risk of bias', heading=True)
para('Table 3.10. Sensitivity analysis of extracted headline accuracy by overall risk of bias. Reports indicates subset size; accuracy n indicates reports with numeric accuracy. Values are median % (25th-75th percentile). These are descriptive summaries of heterogeneous outcomes.', caption=True)
# Keep this short table together, including its heading and caption.
for row in Table(tables[1], d._body).rows[:-1]:
    for cell in row.cells:
        for p in cell.paragraphs:
            p.paragraph_format.keep_with_next = True
insert(tables[1])
para('Across the 126 reports with a numeric headline accuracy, the median was 95.03% (IQR 88.88-98.52%). Excluding High-risk reports retained 124 reports, of which 74 provided an accuracy value; the median was 95.25% (90.15-98.43%). The High-risk group contributed 52 values, with a median of 94.98% (87.98-98.54%). In the agar-plate subgroup, the median was 96.50% (90.97-98.52%; n = 29), increasing to 97.05% (91.43-98.85%; n = 20) after exclusion of High-risk reports. Individual values are displayed in Figure 9.')
Paragraph(cursor, d._body).paragraph_format.space_before = Pt(6)
insert(images[1])
para('Figure 9. Extracted headline accuracy by overall risk of bias. Points denote reports; black overlays show the median and IQR. Outcomes vary in definition, target, dataset and evaluation unit.', caption=True)
para('Excluding High-risk reports left 122 Unclear and only two Low-risk reports; the similar medians therefore provide limited evidence about robustness to bias. Accuracy values were reused from the earlier extraction. Heterogeneous targets, thresholds and evaluation units precluded an inferential risk-group comparison, bivariate random-effects meta-analysis, I² estimation and diagnostic publication-bias testing.')

# Prove that the rest of the manuscript was preserved byte-for-byte at body XML level.
new_nodes = []
n = start.getnext()
while n is not end:
    new_nodes.append(n)
    n = n.getnext()
nodes = new_nodes
assert outside_bytes() == outside_before
assert len(d.tables) == 16
d.save(REPORT)
(OUT / 'section36_outcomes.txt').write_text('\n\n'.join(saved_text) + '\n', encoding='utf-8')
(OUT / 'section36_revision.json').write_text(json.dumps({
    'date': '2026-10-28', 'scope': 'Only Section 3.6',
    'reference_documents': ['EXAMPLE.docx, Section 3.5', 'EXAMPLE2.pdf, page 11'],
    'reference_use': 'Domain-by-domain presentation from EXAMPLE.docx. EXAMPLE2.pdf did not perform QUADAS-2 and supplied no rating rules or results.',
    'outside_section_body_xml_unchanged': True,
    'ratings_and_figure_data_unchanged': True,
    'backup': str(BACKUP.relative_to(ROOT)),
    'report_sha256': hashlib.sha256(REPORT.read_bytes()).hexdigest(),
}, indent=2), encoding='utf-8')
print(REPORT)
