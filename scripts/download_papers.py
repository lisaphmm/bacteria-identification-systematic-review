"""Download open-access PDFs of the included papers.

Looks up each DOI in OpenAlex (open-access locations only), downloads the PDF into papers/pdfs/<Record_ID>.pdf,
and records the outcome in papers/download_status.csv. Papers with no open-access PDF are marked
`not_open_access`; they must be fetched through a browser with the author's institutional access.
Re-running skips papers that already have a valid PDF.

Usage (from the project root): python scripts/download_papers.py [--limit N]
"""
import argparse, re, time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "papers" / "pdfs"
STATUS = ROOT / "papers" / "download_status.csv"
INCLUDED = ROOT / "results" / "final" / "final_included_papers.csv"
UA = {"User-Agent": "Mozilla/5.0 (systematic-review PDF retrieval)"}


def pdf_candidates(doi):
    r = requests.get(f"https://api.openalex.org/works/doi:{doi}", headers=UA, timeout=30)
    if r.status_code != 200:
        return []
    w = r.json()
    locs = [w.get("best_oa_location")] + (w.get("locations") or [])
    urls = []
    for loc in locs:
        u = (loc or {}).get("pdf_url")
        if u and u.startswith("https://") and u not in urls:
            urls.append(u)
    return urls


def extra_candidates(doi):
    """Second pass: Europe PMC open-access copy, then the PDF link the publisher declares on the article page."""
    urls = []
    try:
        r = requests.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                         params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "lite"}, headers=UA, timeout=30)
        for hit in r.json().get("resultList", {}).get("result", []):
            if hit.get("isOpenAccess") == "Y" and hit.get("pmcid"):
                urls.append(f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={hit['pmcid']}&blobtype=pdf")
    except (requests.RequestException, ValueError):
        pass
    try:
        r = requests.get(f"https://doi.org/{doi}", headers=UA, timeout=30, allow_redirects=True)
        m = re.search(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)', r.text, re.I) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url', r.text, re.I)
        if m and m.group(1).startswith("https://"):
            urls.append(m.group(1).replace("&amp;", "&"))
    except requests.RequestException:
        pass
    return urls


def fetch_pdf(url, dest):
    with requests.get(url, headers=UA, timeout=60, stream=True) as r:
        if r.status_code != 200:
            return None
        head = next(r.iter_content(8), b"")
        if not head.startswith(b"%PDF"):
            return None
        with open(dest, "wb") as f:
            f.write(head)
            for chunk in r.iter_content(65536):
                f.write(chunk)
    size = dest.stat().st_size
    if size < 20_000:  # too small to be a paper
        dest.unlink()
        return None
    return size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--pass2", action="store_true", help="retry the not-yet-downloaded papers with Europe PMC and publisher pages")
    a = ap.parse_args()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INCLUDED, dtype=str, keep_default_na=False)
    if a.limit:
        df = df.head(a.limit)
    done = {}
    if STATUS.exists():
        done = {r.Record_ID: r for r in pd.read_csv(STATUS, dtype=str, keep_default_na=False).itertuples()}
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        dest = PDF_DIR / f"{r.Record_ID}.pdf"
        if dest.exists() and dest.stat().st_size >= 20_000:
            prev = done[r.Record_ID].Source_URL if r.Record_ID in done else ""
            rows.append((r.Record_ID, r.DOI, "downloaded", prev, dest.name, dest.stat().st_size))
            continue
        status, src, size = "not_open_access", "", 0
        try:
            for u in (extra_candidates(r.DOI) if a.pass2 else pdf_candidates(r.DOI)):
                size = fetch_pdf(u, dest)
                if size:
                    status, src = "downloaded", u
                    break
                status = "oa_link_failed"
        except requests.RequestException as e:
            status = f"error:{type(e).__name__}"
        rows.append((r.Record_ID, r.DOI, status, src, dest.name if status == "downloaded" else "", size or 0))
        print(f"[{i}/{len(df)}] {r.Record_ID} {status}", flush=True)
        time.sleep(0.2)
    out = pd.DataFrame(rows, columns=["Record_ID", "DOI", "Status", "Source_URL", "File", "Bytes"])
    out.to_csv(STATUS, index=False)
    print(out.Status.value_counts().to_string())


if __name__ == "__main__":
    main()
