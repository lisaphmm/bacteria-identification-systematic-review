#!/usr/bin/env python3
"""
add_abstracts.py

Fetches publication abstracts for DOIs from a CSV file (e.g. springerlink.csv)
using a multi-tier API pipeline:
  1. Springer Nature OpenAccess API (using SPRINGER_API_KEY)
  2. CrossRef API (using --email for polite pool)
  3. Europe PMC API
  4. OpenAlex API
  5. Semantic Scholar API

Usage:
  python add_abstracts.py springerlink.csv springerlink_abstracts.csv --email ngoc.ptx@vinuni.edu
"""

import argparse
import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request


def create_ssl_context():
    """Create an SSL context that works reliably on macOS."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl._create_unverified_context()
    except Exception:
        return ssl.create_default_context()


SSL_CTX = create_ssl_context()


def clean_xml_tags(text):
    """Remove XML/JATS tags like <jats:p>, <italic>, etc."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split()).strip()


def extract_springer_abstract(record):
    """Extract abstract text from a Springer Nature API record."""
    ab = record.get("abstract")
    if not ab:
        return ""
    if isinstance(ab, str):
        return clean_xml_tags(ab)
    if isinstance(ab, dict):
        p = ab.get("p", "")
        if isinstance(p, list):
            return clean_xml_tags(" ".join(str(item) for item in p))
        elif isinstance(p, str):
            return clean_xml_tags(p)
        return clean_xml_tags(" ".join(str(v) for v in ab.values() if isinstance(v, str)))
    return ""


def reconstruct_openalex_abstract(inverted_index):
    """Reconstruct abstract string from OpenAlex inverted index."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions).strip()


def http_get_json(url, headers=None, timeout=12):
    """Perform HTTP GET request and return JSON object or None."""
    req_headers = {
        "User-Agent": "BacteriaIdentificationTool/1.0",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw)
    except Exception:
        return None
    return None


def fetch_abstract(doi, api_key="", email=""):
    """
    Fetch abstract for a given DOI using multi-tier fallback.
    Returns: (abstract_text, source_name)
    """
    if not doi:
        return "", "None"

    norm_doi = doi.strip()
    norm_doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", norm_doi, flags=re.I).strip()

    user_agent = f"BacteriaIdentification/1.0 (mailto:{email})" if email else "BacteriaIdentification/1.0"

    # Tier 1A: Springer Nature OpenAccess API
    if api_key:
        oa_url = f"https://api.springernature.com/openaccess/json?q=doi:{norm_doi}&api_key={api_key}"
        data = http_get_json(oa_url, headers={"User-Agent": user_agent})
        if data and data.get("records"):
            ab = extract_springer_abstract(data["records"][0])
            if ab:
                return ab, "Springer-OA"

        # Tier 1B: Springer Nature Meta API
        meta_url = f"https://api.springernature.com/meta/v1/json?q=doi:{norm_doi}&api_key={api_key}"
        data = http_get_json(meta_url, headers={"User-Agent": user_agent})
        if data and data.get("records"):
            ab = extract_springer_abstract(data["records"][0])
            if ab:
                return ab, "Springer-Meta"

    # Tier 2: CrossRef API
    encoded_doi = urllib.parse.quote(norm_doi, safe="")
    cr_url = f"https://api.crossref.org/works/{encoded_doi}"
    data = http_get_json(cr_url, headers={"User-Agent": user_agent})
    if data and "message" in data:
        raw_ab = data["message"].get("abstract", "")
        if raw_ab:
            ab = clean_xml_tags(raw_ab)
            if len(ab) > 40:
                return ab, "CrossRef"

    # Tier 3: Europe PMC API
    epmc_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{encoded_doi}&format=json"
    data = http_get_json(epmc_url, headers={"User-Agent": user_agent})
    if data and data.get("resultList", {}).get("result"):
        raw_ab = data["resultList"]["result"][0].get("abstractText", "")
        if raw_ab:
            ab = clean_xml_tags(raw_ab)
            if len(ab) > 40:
                return ab, "EuropePMC"

    # Tier 4: OpenAlex API
    oa_alex_url = f"https://api.openalex.org/works/https://doi.org/{norm_doi}"
    if email:
        oa_alex_url += f"?mailto={urllib.parse.quote(email)}"
    data = http_get_json(oa_alex_url, headers={"User-Agent": user_agent})
    if data and "abstract_inverted_index" in data:
        ab = reconstruct_openalex_abstract(data.get("abstract_inverted_index"))
        if len(ab) > 40:
            return ab, "OpenAlex"

    # Tier 5: Semantic Scholar API
    s2_url = f"https://api.semanticscholar.org/graph/v1/paper/{encoded_doi}?fields=abstract"
    data = http_get_json(s2_url, headers={"User-Agent": user_agent})
    if data and data.get("abstract"):
        ab = clean_xml_tags(data["abstract"])
        if len(ab) > 40:
            return ab, "SemanticScholar"

    return "", "Not Found"


def main():
    parser = argparse.ArgumentParser(description="Fetch abstracts for bibliographic CSV by DOI.")
    parser.add_argument("input_csv", help="Path to input CSV (e.g. springerlink.csv)")
    parser.add_argument("output_csv", help="Path to output CSV (e.g. springerlink_abstracts.csv)")
    parser.add_argument("--email", default="", help="Contact email for CrossRef/OpenAlex polite pool")
    parser.add_argument("--api-key", default="", help="Springer Nature API key (or set SPRINGER_API_KEY env)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("SPRINGER_API_KEY", "")
    email = args.email.strip().rstrip(".")

    if not os.path.exists(args.input_csv):
        print(f"Error: Input file '{args.input_csv}' not found.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("ABSTRACT FETCHER PIPELINE")
    print("=" * 60)
    print(f"Input file : {args.input_csv}")
    print(f"Output file: {args.output_csv}")
    print(f"API Key    : {'Configured' if api_key else 'None'}")
    print(f"Email      : {email if email else 'None'}")
    print("-" * 60)

    rows = []
    with open(args.input_csv, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            rows.append(r)

    if not fieldnames:
        print("Error: Could not read CSV header.", file=sys.stderr)
        sys.exit(1)

    if "Abstract" not in fieldnames:
        fieldnames.append("Abstract")

    total = len(rows)
    print(f"Loaded {total:,} records from '{args.input_csv}'\n")

    found_count = 0
    sources_count = {}

    for idx, row in enumerate(rows, start=1):
        doi = row.get("Item DOI", "") or row.get("DOI", "") or ""
        title = (row.get("Item Title", "") or row.get("Title", "") or "Untitled")[:50]
        existing_abs = row.get("Abstract", "").strip()

        if existing_abs:
            print(f"[{idx}/{total}] Already has abstract: {title}...")
            found_count += 1
            sources_count["Existing"] = sources_count.get("Existing", 0) + 1
            continue

        if not doi.strip():
            print(f"[{idx}/{total}] Skipping (no DOI): {title}...")
            row["Abstract"] = ""
            continue

        ab, source = fetch_abstract(doi, api_key=api_key, email=email)
        row["Abstract"] = ab

        if ab:
            found_count += 1
            sources_count[source] = sources_count.get(source, 0) + 1
            print(f"[{idx}/{total}] [✓ {source}] ({len(ab):,} chars) {title}...")
        else:
            print(f"[{idx}/{total}] [✗ Not Found] {doi} - {title}...")

        # Small delay to be polite to APIs
        time.sleep(0.1)

    print("\n" + "=" * 60)
    print("FETCH SUMMARY")
    print("=" * 60)
    print(f"Total processed: {total:,}")
    print(f"Abstracts found: {found_count:,} ({found_count / total * 100:.1f}%)")
    print(f"Missing        : {total - found_count:,}")
    print("\nBreakdown by Source:")
    for src, cnt in sorted(sources_count.items(), key=lambda x: -x[1]):
        print(f"  {src:18}: {cnt:,}")

    with open(args.output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"\n[OK] Successfully saved output to '{args.output_csv}'")
    print("=" * 60)


if __name__ == "__main__":
    main()
