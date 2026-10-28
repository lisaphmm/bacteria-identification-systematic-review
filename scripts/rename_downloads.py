"""Rename manually downloaded PDFs to <Record_ID>.pdf and move them into papers/pdfs/.

Put new downloads in 'unrenamed downloaded papers/' (project root), then run from the project root:
    python scripts/rename_downloads.py            # dry run: shows what would happen
    python scripts/rename_downloads.py --apply    # move new papers, delete byte-identical duplicates

Matching uses the PDF title metadata, the file name, a DOI fragment in the file name and, as a last resort,
the text of the first page. Anything uncertain, conflicting or not on the included list is left in place.
"""
import argparse, difflib, hashlib, re, subprocess, unicodedata, warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "unrenamed downloaded papers"
PDFS = ROOT / "papers" / "pdfs"
INCLUDED = ROOT / "results" / "final" / "final_included_papers.csv"
norm = lambda t: re.sub(r"[^a-z0-9 ]", "", re.sub(r"[\s_\-‐]+", " ", unicodedata.normalize("NFKD", str(t)).lower()))  # NFKD expands ligatures (fi, fl)
sha = lambda p: hashlib.sha1(p.read_bytes()).hexdigest()


def first_page(path):
    try:
        from pypdf import PdfReader
        warnings.filterwarnings("ignore")
        return norm(PdfReader(str(path)).pages[0].extract_text() or "")[:3000]
    except Exception:
        return ""


def match(path, inc):
    """Return (Record_ID, how) or (None, reason)."""
    base = path.stem
    tail_hits = [r.Record_ID for r in inc.itertuples() if len(r.DOI.split("/")[-1]) > 8 and r.DOI.split("/")[-1].lower() in base.lower()]
    if len(tail_hits) == 1:
        return tail_hits[0], "doi-in-filename"
    meta = subprocess.run(["mdls", "-name", "kMDItemTitle", "-raw", str(path)], capture_output=True, text=True).stdout
    for label, t in (("pdf-title", norm(meta)), ("filename", norm(base))):
        if len(t) < 12 or meta in ("(null)", "untitled") and label == "pdf-title":
            continue
        sc = inc.n.map(lambda x: 1.0 if t in x else difflib.SequenceMatcher(None, t, x[:len(t) + 10] if label == "filename" else x).ratio())
        i = sc.idxmax()
        if sc[i] >= 0.9:
            return inc.Record_ID[i], label
    text = first_page(path)
    hits = [r.Record_ID for r in inc.itertuples() if len(r.n) > 25 and r.n[:60] in text]
    if len(hits) == 1:
        return hits[0], "first-page-text"
    return None, "no confident match"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    inc = pd.read_csv(INCLUDED, dtype=str, keep_default_na=False)
    inc["n"] = inc.Title.map(norm)
    have = {sha(p): p.stem for p in PDFS.glob("*.pdf")}
    moved, dup, left = [], [], []
    seen_new = {}
    for f in sorted(SRC.iterdir()):
        if f.name.startswith("."):
            continue
        if f.suffix.lower() != ".pdf":
            junk = f.suffix.lower() == ".html" and b"Security verification" in f.read_bytes()[:3000]
            (dup if junk else left).append((f.name, "bot-check page, not a paper" if junk else "not a PDF"))
            if junk and a.apply:
                f.unlink()
            continue
        h = sha(f)
        if h in have:  # byte-identical copy already in papers/pdfs
            dup.append((f.name, f"identical to {have[h]}.pdf"))
            if a.apply:
                f.unlink()
            continue
        rid, how = match(f, inc)
        if rid is None:
            left.append((f.name, how))
        elif (PDFS / f"{rid}.pdf").exists():
            left.append((f.name, f"{rid} already has a different PDF - check by hand"))
        elif rid in seen_new and seen_new[rid][1] == h:
            dup.append((f.name, f"identical to another new file for {rid}"))
            if a.apply:
                f.unlink()
        elif rid in seen_new:
            left.append((f.name, f"two different files match {rid} - check by hand"))
        else:
            seen_new[rid] = (f, h)
            have[h] = rid  # so a second identical copy is recognised as a duplicate
            moved.append((f.name, f"{rid}.pdf ({how})"))
            if a.apply:
                f.rename(PDFS / f"{rid}.pdf")
    for title, rows in (("MOVE / RENAME", moved), ("DUPLICATE or junk (delete)", dup), ("LEFT FOR YOU", left)):
        print(f"\n{title}: {len(rows)}")
        for n, why in rows:
            print(f"  {n[:70]}  ->  {why}")
    print("\n" + ("APPLIED" if a.apply else "DRY RUN (nothing changed)"))


if __name__ == "__main__":
    main()
