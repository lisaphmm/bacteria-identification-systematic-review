"""Build the screening input from the deduplicated records.

deduplicated_papers.csv -> drop records without an abstract, before 2015, or after the 2026-10-13 cut-off
-> excluded_records.csv (every exclusion with its reason) and to_screen.csv (what the LLMs screen).
Metadata (DocType, keywords, language, exact date) is re-joined from the raw database exports.
"""
import csv, re, unicodedata
import pandas as pd

CUTOFF = pd.Timestamp("2026-10-13")


def norm_title(t):
    t = unicodedata.normalize("NFKD", str(t or "")).lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"<[^>]+>", "", t))


def norm_doi(d):
    d = str(d or "").strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d.rstrip("/.") if d not in ("nan", "") else ""


meta = []


def add(**kw):
    kw["doi"] = norm_doi(kw.get("doi"))
    kw["tkey"] = norm_title(kw.get("title"))
    meta.append(kw)


# Scopus
for _, r in pd.read_csv("scopus.csv", dtype=str).iterrows():
    kws = "; ".join(str(r[c]) for c in ("Author Keywords", "Index Keywords") if pd.notna(r[c]))
    add(doi=r["DOI"], title=r["Title"], doctype=r["Document Type"], stage=r["Publication Stage"],
        keywords=kws, language="", date="")

# IEEE Xplore
for _, r in pd.read_csv("ieeexplore.csv", dtype=str).iterrows():
    kws = "; ".join(str(r[c]) for c in ("Author Keywords", "IEEE Terms") if c in r and pd.notna(r[c]))
    add(doi=r["DOI"], title=r["Document Title"], doctype=r["Document Identifier"], stage="",
        keywords=kws, language="", date=r["Online Date"])

# SpringerLink
for _, r in pd.read_csv("springerlink.csv", dtype=str).iterrows():
    add(doi=r["Item DOI"], title=r["Item Title"], doctype=r["Content Type"], stage="",
        keywords="", language="", date="")

# PubMed (MEDLINE format)
for rec in re.split(r"\n\s*\n", open("pubmed.txt", encoding="utf-8").read()):
    if "PMID-" not in rec:
        continue
    fields, cur = {}, None
    for line in rec.split("\n"):
        m = re.match(r"^([A-Z]{2,4})\s*- (.*)$", line)
        if m:
            cur = m.group(1)
            fields.setdefault(cur, []).append(m.group(2))
        elif cur and line.startswith("      "):
            fields[cur][-1] += " " + line.strip()
    doi = next((v.replace("[doi]", "").strip() for v in fields.get("LID", []) + fields.get("AID", [])
                if v.endswith("[doi]")), "")
    date = ""
    if fields.get("DEP"):
        date = fields["DEP"][0]
    elif fields.get("DP") and re.match(r"^\d{4} \w{3} \d{1,2}", fields["DP"][0]):
        date = fields["DP"][0]
    add(doi=doi, title=" ".join(fields.get("TI", [])), doctype="; ".join(fields.get("PT", [])), stage="",
        keywords="; ".join(fields.get("OT", []) + fields.get("MH", [])), language="; ".join(fields.get("LA", [])),
        date=date)

# Embase (key,value rows; records separated by blank lines)
for blk in re.split(r"\n\s*\n", open("embase.csv", encoding="utf-8-sig").read()):
    row = {rec[0].strip().upper(): rec[1] for rec in csv.reader(blk.splitlines()) if len(rec) >= 2}
    if "TITLE" not in row:
        continue
    kws = "; ".join(row[k] for k in ("AUTHOR KEYWORDS", "EMTREE DRUG INDEX TERMS", "EMTREE MEDICAL INDEX TERMS") if row.get(k))
    add(doi=row.get("DOI", ""), title=row["TITLE"], doctype=row.get("PUBLICATION TYPE", ""),
        stage="AiP" if row.get("AIP/IP ENTRY DATE") else "", keywords=kws,
        language=row.get("LANGUAGE OF ARTICLE", ""), date=row.get("DATE OF PUBLICATION", ""))

m = pd.DataFrame(meta)
by_doi = m[m.doi != ""].drop_duplicates("doi").set_index("doi")
by_title = m[m.tkey != ""].drop_duplicates("tkey").set_index("tkey")

dedup = pd.read_csv("deduplicated_papers.csv", dtype={"Year": int})
no_abs = dedup.Abstract.fillna("").str.strip().str.len() == 0
cols = ["Primary_ID", "Primary_Database", "Year", "Title", "DOI"]
excluded = [dedup[no_abs][cols].assign(Reason="No abstract")]
d = dedup[~no_abs].reset_index(drop=True)
d.insert(0, "Record_ID", [f"R{i:05d}" for i in range(1, len(d) + 1)])

rows = []
for _, r in d.iterrows():
    k = norm_doi(r["DOI"])
    hit = by_doi.loc[k] if k and k in by_doi.index else by_title.loc[norm_title(r["Title"])] \
        if norm_title(r["Title"]) in by_title.index else None
    rows.append({"DocType": "", "Pub_Stage": "", "Keywords": "", "Language": "", "Pub_Date": ""} if hit is None else
                {"DocType": hit.doctype, "Pub_Stage": hit.stage, "Keywords": hit.keywords,
                 "Language": hit.language, "Pub_Date": hit.date})
d = pd.concat([d, pd.DataFrame(rows)], axis=1)
d["_date"] = pd.to_datetime(d["Pub_Date"], errors="coerce", format="mixed")

pre = d[d.Year < 2015]
late = d[(d.Year > 2026) | ((d.Year == 2026) & (d._date > CUTOFF))]
excluded += [pre[cols].assign(Reason="Published before 2015"),
             late[cols].assign(Reason="Published after 2026-10-13 (cut-off)")]
pd.concat(excluded, ignore_index=True).to_csv("excluded_records.csv", index=False)

keep = d.drop(pre.index).drop(late.index)
conf = re.compile(r"conference|proceeding|symposium|workshop|arxiv|biorxiv|medrxiv|ssrn|research square|preprint", re.I)
doc = re.compile(r"review|editorial|comment|letter|news|erratum|retract|conference|proceeding", re.I)


def flags(r):
    f = []
    if conf.search(str(r["Journal"])):
        f.append("journal_conf_or_preprint")
    if doc.search(str(r["DocType"])):
        f.append("doctype_review_or_conf")
    if "press" in str(r["Pub_Stage"]).lower() or r["Pub_Stage"] == "AiP":
        f.append("in_press")
    if r["Year"] == 2026 and pd.isna(r["_date"]):
        f.append("2026_no_exact_date")
    return ";".join(f)


keep = keep.assign(Flags=keep.apply(flags, axis=1)).drop(columns=["_date"])
keep.to_csv("to_screen.csv", index=False)
print(f"{len(dedup)} deduplicated -> {len(keep)} to screen; excluded {len(dedup) - len(keep)} "
      f"(no abstract {int(no_abs.sum())}, before 2015 {len(pre)}, after cut-off {len(late)})")
