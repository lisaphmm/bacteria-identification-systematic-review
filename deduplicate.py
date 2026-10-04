#!/usr/bin/env python3
"""
deduplicate.py

Deduplicates bibliographic records across 5 databases:
  1. PubMed (pubmed.txt)
  2. IEEE Xplore (ieeexplore.csv)
  3. Embase (embase.csv)
  4. SpringerLink (springerlink.csv)
  5. Scopus (scopus.csv)

Deduplication Strategy:
  - Step 1: Exact match by normalized DOI
  - Step 2: Exact match by normalized Title (for remaining records)
  - Missing metadata (e.g., abstracts, DOIs, years) in retained records
    is enriched from any duplicate records removed.
  - Multi-database membership and all original IDs are tracked for PRISMA reporting.

Outputs:
  - deduplicated_papers.csv: All unique papers with full metadata and source tracking.
  - deduplication_log.csv: Full audit log of all duplicate records removed.
"""

import csv
import os
import re
import sys
import unicodedata
from collections import Counter


def norm_doi(d):
    """Normalize DOI for robust matching."""
    if not d:
        return ""
    d = d.strip()
    d = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.I)
    return d.strip().rstrip("/.").lower()


def norm_title(t):
    """Normalize Title for robust matching across databases."""
    if not t:
        return ""
    # Unicode decomposition
    t = unicodedata.normalize("NFKD", t)
    # Remove HTML/XML tags
    t = re.sub(r"<[^>]+>", "", t)
    # Remove non-alphanumeric characters, keeping spaces
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", t)
    return " ".join(t.lower().split())


def load_pubmed(filepath):
    """Parse PubMed MEDLINE format text file."""
    records = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Warning: {filepath} not found.", file=sys.stderr)
        return records

    entries = re.split(r"\n(?=PMID\s*-\s*)", text.strip())
    for entry in entries:
        if not entry.strip():
            continue
        data = {}
        curr = None
        for line in entry.split("\n"):
            if len(line) >= 6 and line[4] == "-" and line[0:4].strip():
                curr = line[0:4].strip()
                val = line[6:].strip()
                if curr in data:
                    data[curr] += " " + val
                else:
                    data[curr] = val
            elif line.startswith("      ") and curr:
                data[curr] += " " + line.strip()

        pmid = data.get("PMID", "").strip()
        title = data.get("TI", "").strip() or data.get("BTI", "").strip()
        lid = data.get("LID", "")
        aid = data.get("AID", "")
        doi = ""
        m = re.search(r"([^\s]+)\s+\[doi\]", lid) or re.search(r"([^\s]+)\s+\[doi\]", aid)
        if m:
            doi = m.group(1).strip()

        year = ""
        dp = data.get("DP", "")
        m_yr = re.search(r"\b(19\d\d|20\d\d)\b", dp)
        if m_yr:
            year = m_yr.group(1)

        records.append({
            "Primary_Database": "PubMed",
            "ID": f"PMID:{pmid}",
            "Title": title,
            "Authors": data.get("AU", ""),
            "Year": year,
            "Journal": data.get("JT", "") or data.get("TA", ""),
            "DOI": doi,
            "Abstract": data.get("AB", ""),
            "_norm_doi": norm_doi(doi),
            "_norm_title": norm_title(title),
            "_all_sources": ["PubMed"],
            "_all_ids": [f"PMID:{pmid}"],
        })
    return records


def load_ieeexplore(filepath):
    """Parse IEEE Xplore CSV file."""
    records = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [fn.strip('\ufeff"') for fn in (reader.fieldnames or [])]
            for i, row in enumerate(reader):
                doi = row.get("DOI", "").strip()
                title = row.get("Document Title", "").strip()
                pdf_link = row.get("PDF Link", "")
                m = re.search(r"arnumber=(\d+)", pdf_link)
                arnum = m.group(1) if m else str(i + 1)
                eid = f"IEEE:{arnum}"
                records.append({
                    "Primary_Database": "IEEE Xplore",
                    "ID": eid,
                    "Title": title,
                    "Authors": row.get("Authors", "").strip(),
                    "Year": row.get("Publication Year", "").strip(),
                    "Journal": row.get("Publication Title", "").strip(),
                    "DOI": doi,
                    "Abstract": row.get("Abstract", "").strip(),
                    "_norm_doi": norm_doi(doi),
                    "_norm_title": norm_title(title),
                    "_all_sources": ["IEEE Xplore"],
                    "_all_ids": [eid],
                })
    except FileNotFoundError:
        print(f"Warning: {filepath} not found.", file=sys.stderr)
        return records
    return records


def load_embase(filepath):
    """Parse Embase field-value block CSV file."""
    records = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Warning: {filepath} not found.", file=sys.stderr)
        return records

    blocks = text.split("\n\n")
    for i, block in enumerate(blocks):
        block_clean = block.strip()
        if not block_clean:
            continue
        r = {}
        reader = csv.reader(block_clean.splitlines())
        for row in reader:
            if not row or not any(row):
                continue
            field = row[0].strip('\ufeff"').strip()
            val = row[1:] if len(row) > 2 else (row[1] if len(row) == 2 else "")
            r[field] = val

        title = r.get("TITLE", "")
        if isinstance(title, list):
            title = " ".join(title)
        doi = r.get("DOI", "")
        if isinstance(doi, list):
            doi = doi[0]
        authors = r.get("AUTHOR NAMES", "")
        if isinstance(authors, list):
            authors = "; ".join(authors)

        eid = f"EMBASE:{i+1}"
        records.append({
            "Primary_Database": "Embase",
            "ID": eid,
            "Title": title.strip(),
            "Authors": authors,
            "Year": str(r.get("PUBLICATION YEAR", "")),
            "Journal": str(r.get("SOURCE", "")),
            "DOI": doi.strip(),
            "Abstract": str(r.get("ABSTRACT", "")),
            "_norm_doi": norm_doi(doi),
            "_norm_title": norm_title(title),
            "_all_sources": ["Embase"],
            "_all_ids": [eid],
        })
    return records


def load_springerlink(filepath=None):
    """Parse SpringerLink CSV file (prefers springerlink_abstracts.csv if available)."""
    if filepath is None:
        filepath = "springerlink_abstracts.csv" if os.path.exists("springerlink_abstracts.csv") else "springerlink.csv"

    records = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [fn.strip('\ufeff"') for fn in (reader.fieldnames or [])]
            for i, row in enumerate(reader):
                doi = row.get("Item DOI", "").strip()
                title = row.get("Item Title", "").strip()
                journal = row.get("Publication Title", "").strip() or row.get("Book Series Title", "").strip()
                eid = f"SPRINGER:{i+1}"
                records.append({
                    "Primary_Database": "SpringerLink",
                    "ID": eid,
                    "Title": title,
                    "Authors": row.get("Authors", "").strip(),
                    "Year": row.get("Publication Year", "").strip(),
                    "Journal": journal,
                    "DOI": doi,
                    "Abstract": row.get("Abstract", "").strip(),
                    "_norm_doi": norm_doi(doi),
                    "_norm_title": norm_title(title),
                    "_all_sources": ["SpringerLink"],
                    "_all_ids": [eid],
                })
    except FileNotFoundError:
        print(f"Warning: {filepath} not found.", file=sys.stderr)
        return records
    return records


def load_scopus(filepath):
    """Parse Scopus standard CSV file."""
    records = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [fn.strip('\ufeff"') for fn in (reader.fieldnames or [])]
            for i, row in enumerate(reader):
                eid = row.get("EID", f"SCOPUS:{i+1}")
                records.append({
                    "Primary_Database": "Scopus",
                    "ID": eid,
                    "Title": row.get("Title", "").strip(),
                    "Authors": row.get("Authors", ""),
                    "Year": row.get("Year", ""),
                    "Journal": row.get("Source title", ""),
                    "DOI": row.get("DOI", "").strip(),
                    "Abstract": "",
                    "_norm_doi": norm_doi(row.get("DOI", "")),
                    "_norm_title": norm_title(row.get("Title", "")),
                    "_all_sources": ["Scopus"],
                    "_all_ids": [eid],
                })
    except FileNotFoundError:
        print(f"Warning: {filepath} not found.", file=sys.stderr)
        return records
    return records


def enrich_record(target, source):
    """Enrich target record with metadata from duplicate source if missing."""
    for field in ["Abstract", "Year", "Journal", "Authors", "DOI"]:
        if not target.get(field, "").strip() and source.get(field, "").strip():
            target[field] = source[field].strip()


def run_deduplication():
    print("5-DATABASE BIBLIOGRAPHIC DEDUPLICATION PIPELINE")
    print("\nLoading datasets...")
    pubmed = load_pubmed("pubmed.txt")
    ieeexplore = load_ieeexplore("ieeexplore.csv")
    embase = load_embase("embase.csv")
    springer_file = "springerlink_abstracts.csv" if os.path.exists("springerlink_abstracts.csv") else "springerlink.csv"
    springerlink = load_springerlink(springer_file)
    scopus = load_scopus("scopus.csv")

    springer_abs_cnt = sum(1 for r in springerlink if r.get("Abstract"))
    initial_counts = {
        "PubMed": len(pubmed),
        "IEEE Xplore": len(ieeexplore),
        "Embase": len(embase),
        f"SpringerLink ({'with abstracts' if springer_abs_cnt else 'raw'})": len(springerlink),
        "Scopus": len(scopus),
    }
    total_initial = sum(initial_counts.values())

    for db_name, cnt in initial_counts.items():
        print(f"  {db_name:30}: {cnt:,} records")
    print(f"  {'Total Initial':30}: {total_initial:,} records")

    # Combine in priority order: PubMed, IEEE Xplore, Embase, SpringerLink, Scopus
    all_records = pubmed + ieeexplore + embase + springerlink + scopus

    # Step 1: Deduplicate by DOI
    doi_map = {}
    kept_after_doi = []
    removed_doi = []

    for r in all_records:
        d = r["_norm_doi"]
        if d:
            if d in doi_map:
                kept_r = doi_map[d]
                if r["Primary_Database"] not in kept_r["_all_sources"]:
                    kept_r["_all_sources"].append(r["Primary_Database"])
                kept_r["_all_ids"].append(r["ID"])
                enrich_record(kept_r, r)
                removed_doi.append({
                    "Removed_ID": r["ID"],
                    "Removed_Source": r["Primary_Database"],
                    "Removed_Title": r["Title"],
                    "Removed_DOI": r["DOI"],
                    "Reason": "Duplicate DOI",
                    "Matched_Key": d,
                    "Retained_ID": kept_r["ID"],
                    "Retained_Source": kept_r["Primary_Database"],
                    "Retained_Title": kept_r["Title"],
                })
            else:
                doi_map[d] = r
                kept_after_doi.append(r)
        else:
            kept_after_doi.append(r)

    print(f"\nStep 1 (Deduplication by DOI):")
    print(f"  Records removed:   {len(removed_doi):,}")
    print(f"  Records remaining: {len(kept_after_doi):,}")

    # Step 2: Deduplicate by Title
    title_map = {}
    final_kept = []
    removed_title = []

    for r in kept_after_doi:
        t = r["_norm_title"]
        if t:
            if t in title_map:
                kept_r = title_map[t]
                if r["Primary_Database"] not in kept_r["_all_sources"]:
                    kept_r["_all_sources"].append(r["Primary_Database"])
                kept_r["_all_ids"].append(r["ID"])
                enrich_record(kept_r, r)
                removed_title.append({
                    "Removed_ID": r["ID"],
                    "Removed_Source": r["Primary_Database"],
                    "Removed_Title": r["Title"],
                    "Removed_DOI": r["DOI"],
                    "Reason": "Duplicate Title",
                    "Matched_Key": t,
                    "Retained_ID": kept_r["ID"],
                    "Retained_Source": kept_r["Primary_Database"],
                    "Retained_Title": kept_r["Title"],
                })
            else:
                title_map[t] = r
                final_kept.append(r)
        else:
            final_kept.append(r)

    print(f"\nStep 2 (Deduplication by Title):")
    print(f"  Records removed:   {len(removed_title):,}")
    print(f"  Records remaining: {len(final_kept):,}")

    total_removed = len(removed_doi) + len(removed_title)
    abstract_count = sum(1 for r in final_kept if r.get("Abstract", "").strip())
    print(f"\nOverall Summary:")
    print(f"  Total records removed: {total_removed:,}")
    print(f"  Final unique records:  {len(final_kept):,}")
    print(f"  Records with abstract: {abstract_count:,} ({abstract_count / len(final_kept) * 100:.1f}%)")

    # Source overlap summary
    source_patterns = Counter("; ".join(r["_all_sources"]) for r in final_kept)
    print(f"\nDatabase Distribution of Unique Records:")
    for pat, cnt in source_patterns.most_common():
        print(f"  {pat:35}: {cnt:,}")

    # Save deduplicated records
    output_fields = [
        "Primary_Database", "All_Databases", "Primary_ID", "All_IDs",
        "Title", "Authors", "Year", "Journal", "DOI", "Abstract"
    ]
    with open("deduplicated_papers.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        for r in final_kept:
            row = {
                "Primary_Database": r.get("Primary_Database", ""),
                "All_Databases": "; ".join(r.get("_all_sources", [])),
                "Primary_ID": r.get("ID", ""),
                "All_IDs": "; ".join(r.get("_all_ids", [])),
                "Title": r.get("Title", ""),
                "Authors": r.get("Authors", ""),
                "Year": r.get("Year", ""),
                "Journal": r.get("Journal", ""),
                "DOI": r.get("DOI", ""),
                "Abstract": r.get("Abstract", ""),
            }
            writer.writerow(row)
    print(f"\n[OK] Exported deduplicated records to 'deduplicated_papers.csv'")

    # Save removal log
    log_fields = [
        "Removed_ID", "Removed_Source", "Removed_Title", "Removed_DOI",
        "Reason", "Matched_Key", "Retained_ID", "Retained_Source", "Retained_Title"
    ]
    with open("deduplication_log.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=log_fields)
        writer.writeheader()
        for r in removed_doi + removed_title:
            writer.writerow(r)
    print(f"[OK] Exported duplicate removal log to 'deduplication_log.csv'")
    print("=" * 60)


if __name__ == "__main__":
    run_deduplication()
    
