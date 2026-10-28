"""Rebuild results/final/included_papers.xlsx from final_results.csv and refresh its 'Downloaded' tick-box column.

A paper is ticked only if papers/pdfs/<Record_ID>.pdf exists, starts with the PDF signature and is >= 20 KB.
Re-run after every download round: python scripts/update_download_sheet.py
"""
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "results" / "final" / "included_papers.xlsx"
PDFS = ROOT / "papers" / "pdfs"


def valid_pdf(path):
    if not path.exists() or path.stat().st_size < 20_000:
        return False
    with open(path, "rb") as f:
        return b"%PDF" in f.read(1024)  # some PDFs start with a blank line before the signature


final = pd.read_csv(ROOT / "results" / "final" / "final_results.csv", dtype=str, keep_default_na=False)
df = final[final.Final == "include"].copy()
df["DOI_link"] = df.DOI.map(lambda x: f"https://doi.org/{x}" if x else "")
df["Decision_Source"] = df.Human_Decision.map(lambda h: "manual check" if h else "both models agreed")
df = df[["Record_ID", "Title", "Authors", "Year", "Journal", "DOI", "DOI_link", "Primary_Database", "Stage",
         "Decision_Source", "Abstract"]].sort_values(["Year", "Record_ID"], ascending=[False, True]).reset_index(drop=True)
ok = df.Record_ID.map(lambda i: valid_pdf(PDFS / f"{i}.pdf"))
df.insert(1, "Downloaded", ok.map({True: "☑", False: "☐"}))
df.insert(2, "PDF_File", [f"{i}.pdf" if o else "" for i, o in zip(df.Record_ID, ok)])

with pd.ExcelWriter(XLSX, engine="openpyxl") as w:
    df.to_excel(w, index=False, sheet_name="Included")
ws = load_workbook(XLSX)["Included"]
cols = list(df.columns)
green, red = PatternFill("solid", fgColor="C6EFCE"), PatternFill("solid", fgColor="FFC7CE")
for c in ws[1]:
    c.font = Font(bold=True)
ws.freeze_panes = "C2"
ws.auto_filter.ref = ws.dimensions
for i, name in enumerate(cols, 1):
    letter = ws.cell(1, i).column_letter
    ws.column_dimensions[letter].width = {"Title": 60, "Abstract": 90, "Journal": 30, "Authors": 30,
                                          "Downloaded": 12, "PDF_File": 14}.get(name, 18)
    for cell in ws[letter][1:]:
        if name in ("Title", "Abstract", "Authors"):
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        if name == "Downloaded":
            cell.alignment = Alignment(horizontal="center", vertical="top")
            cell.font = Font(size=14)
            cell.fill = green if cell.value == "☑" else red
ws.title = "Included"
wb = ws.parent
wb.save(XLSX)
print(f"{int(ok.sum())} of {len(df)} papers ticked (valid PDF on disk)")
