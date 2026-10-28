"""Remove papers from the included list and note the reason everywhere it is tracked.

    python scripts/remove_papers.py R01148 R01125 --reason "E12: full text not accessible (not open access)"

For each paper: records the decision (screening_review.xlsx, or pilot_review_decisions.csv for pilot papers),
adds a row to data/screening_input/excluded_records.csv, reruns finalize, and refreshes included_papers.xlsx
(including the Downloaded tick boxes). Any PDF already saved for the paper is reported, not deleted.
"""
import argparse, subprocess, sys
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
REVIEW = ROOT / "results" / "full_run" / "screening_review.xlsx"
PILOT_DEC = ROOT / "results" / "pilot" / "pilot_review_decisions.csv"
EXCLUDED = ROOT / "data" / "screening_input" / "excluded_records.csv"
INCLUDED_XLSX = ROOT / "results" / "final" / "included_papers.xlsx"
PDFS = ROOT / "papers" / "pdfs"


def run(*args):
    out = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(out.stderr[-800:])
    return out.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--reason", default="E12: full text not accessible (not open access)")
    ap.add_argument("--restore", action="store_true", help="put the papers back on the included list")
    ap.add_argument("--force", action="store_true", help="remove even if a PDF has already been downloaded")
    a = ap.parse_args()
    note = "Restored: full text already downloaded" if a.restore else f"{a.reason} - removed by Lisa"
    decision = "include" if a.restore else "exclude"
    final = pd.read_csv(ROOT / "results" / "final" / "final_results.csv", dtype=str, keep_default_na=False).set_index("Record_ID")
    src = pd.read_csv(ROOT / "data" / "screening_input" / "to_screen.csv", dtype=str, keep_default_na=False).set_index("Record_ID")
    ex = pd.read_csv(EXCLUDED, dtype=str, keep_default_na=False)
    wb = openpyxl.load_workbook(REVIEW)
    pilot_rows, new_ex, skipped, restore_ids = [], [], [], []
    for rid in a.ids:
        if rid not in final.index:
            raise SystemExit(f"{rid} is not a screened record")
        print(f"{rid} [{final.Stage[rid]}] {final.Title[rid][:80]} (currently {final.Final[rid]})")
        if not a.restore and not a.force and (PDFS / f"{rid}.pdf").exists():
            print(f"  skipped: papers/pdfs/{rid}.pdf is already downloaded (use --force to remove anyway)")
            skipped.append(rid)
            continue
        if final.Stage[rid] == "pilot":
            pilot_rows.append((rid, note))
        else:
            done = False
            for name in ("1_Check_Manually", "2_Audit_Excluded", "3_Included"):
                ws = wb[name]
                hdr = {c.value: c.column for c in ws[1]}
                for row in range(2, ws.max_row + 1):
                    if ws.cell(row, hdr["Record_ID"]).value == rid:
                        ws.cell(row, hdr["Human_Decision"]).value = decision
                        ws.cell(row, hdr["Human_Reason"]).value = note
                        done = True
            if not done:
                raise SystemExit(f"{rid} not found in the review workbook")
        s = src.loc[rid]
        if a.restore:
            restore_ids.append(s.Primary_ID)
        elif s.Primary_ID not in set(ex.Primary_ID):
            new_ex.append({"Primary_ID": s.Primary_ID, "Primary_Database": s.Primary_Database, "Year": s.Year,
                           "Title": s.Title, "DOI": s.DOI, "Reason": f"Removed after screening: {a.reason}"})
    wb.save(REVIEW)
    if pilot_rows:
        cur = pd.read_csv(PILOT_DEC, dtype=str)
        cur = cur[~cur.Record_ID.isin([r for r, _ in pilot_rows])]
        add = pd.DataFrame([{"Record_ID": r, "Human_Decision": decision, "Human_Reason": n} for r, n in pilot_rows])
        pd.concat([cur, add]).to_csv(PILOT_DEC, index=False)
        run("scripts/screening_pipeline.py", "merge-pilot")
    if restore_ids:
        ex = ex[~ex.Primary_ID.isin(restore_ids)]
    if new_ex or restore_ids:
        pd.concat([ex, pd.DataFrame(new_ex)], ignore_index=True).to_csv(EXCLUDED, index=False)
    print(run("scripts/screening_pipeline.py", "finalize").strip().splitlines()[-3])
    print(run("scripts/update_download_sheet.py").strip())


if __name__ == "__main__":
    main()
