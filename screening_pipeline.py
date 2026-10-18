"""Dual-LLM (Gemini + Mistral) title/abstract screening.

Subcommands: check-models, screen, pilot-files, compare, export, finalize.
Run `python screening_pipeline.py <command> -h` for options.
"""
import argparse, json, os, random, re, threading, time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import requests

import config as C

DECISIONS = {"include", "exclude", "check_manually"}
lock = threading.Lock()


# ---------- setup helpers ----------
def load_env():
    if C.ENV_FILE.exists():
        for line in C.ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def api_key(model):
    key = os.environ.get(C.MODELS[model]["key_env"], "")
    if not key:
        raise SystemExit(f"Missing {C.MODELS[model]['key_env']}. Add it to {C.ENV_FILE.name}.")
    return key


def est_tokens(text):
    return len(text) // 4 + 1


def results_path(model, kind="results"):
    return C.ROOT / f"{kind}_{model}.jsonl"


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append_jsonl(path, rows):
    with lock, open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()


def log_usage(model, kind, n, tin, tout, secs, status):
    path = C.ROOT / "usage_log.csv"
    with lock, open(path, "a") as f:
        if f.tell() == 0:
            f.write("time,model,kind,n_records,input_tokens,output_tokens,seconds,status\n")
        f.write(f"{datetime.now().isoformat(timespec='seconds')},{model},{kind},{n},{tin},{tout},{secs:.1f},{status}\n")


# ---------- rate limiting ----------
class Limiter:
    """Sliding 60 s window for requests and tokens, plus a concurrency semaphore."""

    def __init__(self, cfg):
        self.rpm, self.tpm = cfg["rpm"], cfg["tpm"]
        self.sem = threading.BoundedSemaphore(cfg["max_concurrent"])
        self.events = deque()  # (time, tokens)
        self.mu = threading.Lock()
        self.n429 = 0
        self.peak_rpm = self.peak_tpm = 0

    def wait(self, tokens):
        while True:
            with self.mu:
                now = time.time()
                while self.events and now - self.events[0][0] > 60:
                    self.events.popleft()
                reqs, toks = len(self.events), sum(t for _, t in self.events)
                if reqs < self.rpm and (toks + tokens <= self.tpm or reqs == 0):
                    self.events.append((now, tokens))
                    self.peak_rpm = max(self.peak_rpm, reqs + 1)
                    self.peak_tpm = max(self.peak_tpm, toks + tokens)
                    return
            time.sleep(1)


class RateLimited(Exception):
    def __init__(self, retry_after=None):
        self.retry_after = retry_after


# ---------- provider calls ----------
def call_gemini(system, user, cfg):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['id']}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 16000,
            "thinkingConfig": {"thinkingBudget": cfg["thinking_budget"]},
        },
    }
    r = requests.post(url, params={"key": api_key("gemini")}, json=body, timeout=300)
    if r.status_code == 429:
        if "per_day" in r.text or "PerDay" in r.text:  # daily quota: retrying is pointless
            raise SystemExit("Gemini DAILY quota exhausted. Re-run `screen` later (progress is saved), "
                             "or raise the limit by enabling billing / a higher tier.")
        raise RateLimited(r.headers.get("Retry-After"))
    r.raise_for_status()
    j = r.json()
    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"].get("parts", []))
    u = j.get("usageMetadata", {})
    return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)


def call_mistral(system, user, cfg):
    body = {
        "model": cfg["id"],
        "temperature": 0,
        "top_p": 1,  # Mistral Large 4 rejects temperature 0 unless top_p is 1
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    r = requests.post("https://api.mistral.ai/v1/chat/completions", json=body, timeout=300,
                      headers={"Authorization": f"Bearer {api_key('mistral')}"})
    if r.status_code == 429:
        raise RateLimited(r.headers.get("Retry-After"))
    r.raise_for_status()
    j = r.json()
    u = j.get("usage", {})
    content = j["choices"][0]["message"]["content"]
    if isinstance(content, list):  # reasoning models return chunks; keep only the answer text
        content = "".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return content, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def call_mock(system, user, cfg):
    ids = re.findall(r"^ID: (\S+)", user, re.M)
    out = [{"id": i, "d": random.choice(["include", "exclude", "check_manually"]),
            "r": None, "c": "mock"} for i in ids]
    for o in out:
        o["r"] = {"include": None, "exclude": "E6", "check_manually": "DL?"}[o["d"]]
    return json.dumps({"results": out}), est_tokens(system + user), 50


CALLERS = {"gemini": call_gemini, "mistral": call_mistral}


def parse_results(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("results", [])
    return data


# ---------- message building ----------
def record_block(r, other=None):
    abstract = str(r["Abstract"])[:C.ABSTRACT_MAX_CHARS]
    lines = [f"ID: {r['Record_ID']}", f"Title: {r['Title']}",
             f"Year: {r['Year']} | Source: {r['Journal']} | DocType: {r.get('DocType', '')} | Flags: {r.get('Flags', '')}"]
    if str(r.get("Language", "")).strip() and str(r.get("Language")) != "nan":
        lines.append(f"Language field: {r['Language']}")
    kw = str(r.get("Keywords", ""))
    if kw and kw != "nan":
        lines.append(f"Keywords: {kw[:400]}")
    lines.append(f"Abstract: {abstract}")
    if other:
        lines.append(f"Other reviewer: decision={other['d']}, reason={other['r']}, comment={other['c']}")
    return "\n".join(lines)


# ---------- screening engine ----------
def run_batches(model, recs, system, outpath, kind, limiter, mock=False, others=None):
    """recs: list of record dicts. Appends validated results to outpath. Returns (n_ok, n_failed_ids)."""
    cfg = C.MODELS[model]
    caller = call_mock if mock else CALLERS[model]
    failed, done_count = [], [0]

    def one_call(batch):
        user = "\n---\n".join(record_block(r, others.get(r["Record_ID"]) if others else None) for r in batch)
        tokens = est_tokens(system + user)
        delay = C.BACKOFF_START
        for attempt in range(C.MAX_RETRIES):
            with limiter.sem:
                limiter.wait(tokens)
                t0 = time.time()
                try:
                    text, tin, tout = caller(system, user, cfg)
                    items = parse_results(text)
                    log_usage(model, kind, len(batch), tin, tout, time.time() - t0, "ok")
                    return items
                except RateLimited as e:
                    limiter.n429 += 1
                    wait = float(e.retry_after) if e.retry_after else delay
                    log_usage(model, kind, len(batch), 0, 0, time.time() - t0, "429")
                except Exception as e:  # network, bad JSON, HTTP errors
                    wait = delay
                    detail = getattr(getattr(e, "response", None), "text", "") or str(e)
                    detail = re.sub(r"[\s,]+", " ", detail)[:120]
                    log_usage(model, kind, len(batch), 0, 0, time.time() - t0, f"error:{type(e).__name__}:{detail}")
                    if getattr(getattr(e, "response", None), "status_code", 0) in (400, 401, 403, 404):
                        raise SystemExit(f"{model}: non-retryable API error: {detail}")
            time.sleep(min(wait, C.BACKOFF_MAX) + random.random())
            delay = min(delay * 2, C.BACKOFF_MAX)
        return []

    def process(batch):
        pending = batch
        for _ in range(C.MAX_RETRIES):
            ids = {r["Record_ID"] for r in pending}
            items = one_call(pending)
            good, seen = [], set()
            for it in items:
                if (isinstance(it, dict) and it.get("id") in ids and it["id"] not in seen
                        and it.get("d") in DECISIONS):
                    seen.add(it["id"])
                    good.append({"id": it["id"], "d": it["d"], "r": it.get("r"), "c": str(it.get("c", ""))[:300],
                                 "model": cfg["id"], "prompt": C.PROMPT_VERSION})
            append_jsonl(outpath, good)
            with lock:
                done_count[0] += len(good)
                print(f"  [{model}/{kind}] {done_count[0]} records done", end="\r", flush=True)
            pending = [r for r in pending if r["Record_ID"] not in seen]
            if not pending:
                return
            if len(pending) > 1 and not good:
                mid = len(pending) // 2  # split a batch that keeps failing
                process(pending[:mid])
                process(pending[mid:])
                return
        with lock:
            failed.extend(r["Record_ID"] for r in pending)

    batches = [recs[i:i + C.BATCH_SIZE] for i in range(0, len(recs), C.BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=cfg["max_concurrent"]) as ex:
        list(ex.map(process, batches))
    print()
    return done_count[0], failed


def load_system(extra=""):
    return C.PROMPT_FILE.read_text() + extra


def load_screen_df():
    return pd.read_csv(C.TO_SCREEN, dtype=str, keep_default_na=False)


def pilot_ids():
    p = C.ROOT / "pilot_300.csv"
    return list(pd.read_csv(p, dtype=str)["Record_ID"]) if p.exists() else None


def make_pilot(df):
    """Stratified (by database) random sample, fixed seed. Saved once; reused afterwards."""
    p = C.ROOT / "pilot_300.csv"
    if p.exists():
        return pd.read_csv(p, dtype=str, keep_default_na=False)
    frac = C.PILOT_SIZE / len(df)
    parts = [g.sample(n=max(1, round(len(g) * frac)), random_state=C.SEED) for _, g in df.groupby("Primary_Database")]
    pilot = pd.concat(parts)
    if len(pilot) > C.PILOT_SIZE:
        pilot = pilot.sample(n=C.PILOT_SIZE, random_state=C.SEED)
    elif len(pilot) < C.PILOT_SIZE:
        rest = df.drop(pilot.index)
        pilot = pd.concat([pilot, rest.sample(n=C.PILOT_SIZE - len(pilot), random_state=C.SEED)])
    pilot = pilot.sort_values("Record_ID")
    pilot.to_csv(p, index=False)
    return pilot


# ---------- commands ----------
def cmd_check_models(a):
    ok = True
    g = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     params={"key": api_key("gemini"), "pageSize": 200}, timeout=30)
    g.raise_for_status()
    names = [m["name"].split("/")[-1] for m in g.json().get("models", [])]
    print("Gemini models containing 'pro':", [n for n in names if "pro" in n])
    if C.MODELS["gemini"]["id"] not in names:
        print(f"!! Gemini model {C.MODELS['gemini']['id']} not available"); ok = False
    m = requests.get("https://api.mistral.ai/v1/models",
                     headers={"Authorization": f"Bearer {api_key('mistral')}"}, timeout=30)
    m.raise_for_status()
    ids = sorted(x["id"] for x in m.json()["data"])
    print("Mistral models containing 'large':", [i for i in ids if "large" in i])
    if C.MODELS["mistral"]["id"] not in ids:
        print(f"!! Mistral model {C.MODELS['mistral']['id']} not available"); ok = False
    if not ok:
        raise SystemExit("Pick the correct model IDs in config.py (ask Lisa if unsure).")
    print("Model IDs OK.")


def cmd_screen(a):
    df = load_screen_df()
    pilot = make_pilot(df)
    if a.pilot:
        df = pilot
    elif not C.PILOT_APPROVED:
        raise SystemExit("Full run is locked: set PILOT_APPROVED = True in config.py after checking the pilot papers.")
    system = load_system()
    models = [a.model] if a.model else list(C.MODELS)
    if a.dry_run:
        first = df.head(C.BATCH_SIZE).to_dict("records")
        user = "\n---\n".join(record_block(r) for r in first)
        n_batches = -(-len(df) // C.BATCH_SIZE)
        print(f"{len(df)} records -> {n_batches} requests per model. First request about "
              f"{est_tokens(system + user)} input tokens (system prompt about {est_tokens(system)}).")
        print(user[:1500])
        return
    results = {}
    def run(model):
        done = {r["id"] for r in read_jsonl(results_path(model))}
        todo = [r for r in df.to_dict("records") if r["Record_ID"] not in done]
        print(f"{model}: {len(done)} already done, {len(todo)} to screen")
        limiter = Limiter(C.MODELS[model])
        ok, failed = run_batches(model, todo, system, results_path(model), "screen", limiter, mock=a.mock)
        results[model] = (ok, failed, limiter)
    threads = [threading.Thread(target=run, args=(m,)) for m in models]
    [t.start() for t in threads]; [t.join() for t in threads]
    for m, (ok, failed, lim) in results.items():
        print(f"{m}: {ok} screened, {len(failed)} failed (re-run to retry), 429 errors: {lim.n429}, "
              f"peak {lim.peak_rpm} req/min, ~{lim.peak_tpm} tokens/min")
        if failed:
            print("  failed IDs:", ", ".join(failed[:20]), "..." if len(failed) > 20 else "")


def merged(df=None):
    """One row per record with both models' decisions."""
    df = load_screen_df() if df is None else df
    out = df.copy()
    for m in C.MODELS:
        res = {r["id"]: r for r in read_jsonl(results_path(m))}
        for k in ("d", "r", "c"):
            out[f"{k}_{m}"] = out["Record_ID"].map(lambda i: (res.get(i) or {}).get(k))
    return out


def kappa(a, b):
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((list(a).count(l) / n) * (list(b).count(l) / n) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def cmd_compare(a):
    m = merged()
    m = m.dropna(subset=["d_gemini", "d_mistral"])
    m["agreement"] = m.d_gemini == m.d_mistral
    m["reason_agreement"] = m.r_gemini.fillna("") == m.r_mistral.fillna("")
    m.to_csv(C.ROOT / "comparison.csv", index=False)
    print(f"{len(m)} records screened by both models. Agreement {m.agreement.mean():.1%}, "
          f"Cohen's kappa {kappa(m.d_gemini, m.d_mistral):.3f}")
    print(pd.crosstab(m.d_gemini, m.d_mistral, rownames=["gemini"], colnames=["mistral"]))


def cmd_pilot_files(a):
    df = load_screen_df()
    pilot = make_pilot(df)
    m = merged(pilot)
    m.to_csv(C.ROOT / "pilot_results_all300.csv", index=False)
    cols = ["Record_ID", "Title", "Year", "Journal", "Abstract"]
    sample = pilot.sample(n=C.PILOT_MANUAL_SIZE, random_state=C.SEED)[cols].copy()
    sample["Human_Decision"] = ""
    sample["Human_Reason"] = ""
    write_xlsx({"Manual_Check": sample}, C.ROOT / "pilot_manual_check.xlsx", dropdown_col="Human_Decision")
    both = m.dropna(subset=["d_gemini", "d_mistral"])
    print(f"Pilot records {len(m)}; screened by both models: {len(both)}")
    for mod in C.MODELS:
        print(mod, m[f"d_{mod}"].value_counts(dropna=False).to_dict())
    if len(both):
        print(f"Agreement {(both.d_gemini == both.d_mistral).mean():.1%}, kappa {kappa(both.d_gemini, both.d_mistral):.3f}")
    u = pd.read_csv(C.ROOT / "usage_log.csv") if (C.ROOT / "usage_log.csv").exists() else None
    if u is not None:
        s = u[(u.kind == "screen") & (u.status == "ok")]
        for mod, g in s.groupby("model"):
            per = (g.input_tokens.sum() + g.output_tokens.sum()) / max(1, g.n_records.sum())
            total = len(load_screen_df())
            price = C.PRICE_PER_M.get(mod)
            cost = ""
            if price:
                cost = f", ~${(g.input_tokens.sum() * price[0] + g.output_tokens.sum() * price[1]) / 1e6 / g.n_records.sum() * total:.0f} for full run"
            print(f"{mod}: {per:.0f} tokens/record -> ~{per * total / 1e6:.1f}M tokens for {total} records{cost}")
    print("Wrote pilot_manual_check.xlsx (blind 100) and pilot_results_all300.csv (keep aside until you finish).")


def final_table():
    """One row per screened record. Models disagree -> check_manually (no model cross-check)."""
    m = merged().dropna(subset=["d_gemini", "d_mistral"]).copy()
    pilot_set = set(pilot_ids() or [])
    pilot_final = {}
    p = C.ROOT / "pilot_final.csv"
    if p.exists():
        pf = pd.read_csv(p, dtype=str, keep_default_na=False)
        pilot_final = dict(pf[pf.Final.isin(["include", "exclude"])][["Record_ID", "Final"]].values)
    cats, why, stage = [], [], []
    for _, r in m.iterrows():
        g, mi = r.d_gemini, r.d_mistral
        stage.append("pilot" if r.Record_ID in pilot_set else "full")
        if r.Record_ID in pilot_final:
            cats.append(pilot_final[r.Record_ID]); why.append("pilot: final decision (Lisa and/or both models)")
        elif g == mi:
            cats.append(g); why.append(r.r_gemini if g == "exclude" else ("DL?" if g == "check_manually" else ""))
        else:
            cats.append("check_manually")
            why.append(f"models disagree: Gemini={g} {r.r_gemini or ''}, Mistral={mi} {r.r_mistral or ''}")
    m["Stage"], m["Final_Category"], m["Final_Reason"] = stage, cats, why
    m["Models_Agree"] = m.d_gemini == m.d_mistral
    return m


def write_xlsx(sheets, path, dropdown_col=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook(); wb.remove(wb.active)
    for name, df in sheets.items():
        ws = wb.create_sheet(name[:31])
        ws.append(list(df.columns))
        for row in df.itertuples(index=False):
            ws.append(["" if (isinstance(v, float) and pd.isna(v)) or v is None else v for v in row])
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        widths = {"Title": 60, "Abstract": 90, "Journal": 30}
        for i, col in enumerate(df.columns, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = widths.get(col, 18)
            if col in ("Title", "Abstract"):
                for cell in ws[ws.cell(1, i).column_letter][1:]:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        col = dropdown_col or ("Human_Decision" if "Human_Decision" in df.columns else None)
        if col and col in df.columns and len(df):
            dv = DataValidation(type="list", formula1='"include,exclude,check_manually"', allow_blank=True)
            ws.add_data_validation(dv)
            letter = ws.cell(1, list(df.columns).index(col) + 1).column_letter
            dv.add(f"{letter}2:{letter}{len(df) + 1}")
    wb.save(path)


def cmd_export(a):
    f = final_table()
    f.to_csv(C.ROOT / "final_decisions.csv", index=False)
    show = ["Record_ID", "Title", "Year", "Journal", "DOI", "Primary_Database", "Abstract"]
    models = ["d_gemini", "r_gemini", "c_gemini", "d_mistral", "r_mistral", "c_mistral"]
    hum = {"Human_Decision": "", "Human_Reason": ""}
    cm = f[f.Final_Category == "check_manually"]
    cm[show + ["Final_Reason"] + models].to_csv(C.ROOT / "check_manually_papers.csv", index=False)
    exc = f[(f.Final_Category == "exclude") & (f.Stage == "full")]
    n_audit = min(len(exc), max(C.AUDIT_MIN, int(len(exc) * C.AUDIT_FRACTION)))
    audit = exc.sample(n=n_audit, random_state=C.SEED) if n_audit else exc
    sheets = {
        "Summary": f.groupby(["Stage", "Final_Category"]).size().reset_index(name="Records"),
        "1_Check_Manually": cm[show + ["Final_Reason"] + models].assign(**hum),
        "2_Audit_Excluded": audit[show + ["Final_Reason"] + models].assign(**hum),
        "3_Included": f[(f.Final_Category == "include") & (f.Stage == "full")][show + models].assign(**hum),
        "All_Decisions": f[["Stage"] + show + models + ["Final_Category", "Final_Reason"]],
    }
    write_xlsx(sheets, C.ROOT / "screening_review.xlsx")
    print(f.groupby(["Stage", "Final_Category"]).size().to_string())
    print("Wrote final_decisions.csv, check_manually_papers.csv, screening_review.xlsx")


def cmd_finalize(a):
    """Lisa's decisions in screening_review.xlsx override the models. Writes the final results file."""
    f = final_table()
    human = {}
    for sheet in ("1_Check_Manually", "2_Audit_Excluded", "3_Included"):
        h = pd.read_excel(C.ROOT / "screening_review.xlsx", sheet_name=sheet, dtype=str)
        for _, r in h.dropna(subset=["Human_Decision"]).iterrows():
            human[r["Record_ID"]] = r["Human_Decision"]
    f["Human_Decision"] = f.Record_ID.map(human).fillna("")
    f["Final"] = f.apply(lambda r: r.Human_Decision if r.Human_Decision in ("include", "exclude") else r.Final_Category, axis=1)
    f.loc[f.Final == "check_manually", "Final"] = "unresolved"
    cols = ["Record_ID", "Stage", "Title", "Authors", "Year", "Journal", "DOI", "Primary_Database", "Abstract",
            "d_gemini", "r_gemini", "d_mistral", "r_mistral", "Models_Agree", "Human_Decision", "Final", "Final_Reason"]
    f[cols].to_csv(C.ROOT / "final_results.csv", index=False)
    inc = f[f.Final == "include"]
    inc[cols].to_csv(C.ROOT / "final_included_papers.csv", index=False)
    by_reason = pd.read_csv(C.EXCLUDED).Reason.value_counts().to_dict()
    lines = [("Excluded before screening", by_reason),
             ("Screened (pilot + full)", f.groupby("Stage").size().to_dict()),
             ("Final decisions", f.Final.value_counts().to_dict()),
             ("Final included", len(inc))]
    with open(C.ROOT / "prisma_counts.txt", "w") as fh:
        for k, v in lines:
            fh.write(f"{k}: {v}\n"); print(f"{k}: {v}")
    print("Wrote final_results.csv (pilot + full), final_included_papers.csv, prisma_counts.txt")
    if (f.Final == "unresolved").any():
        print(f"WARNING: {(f.Final == 'unresolved').sum()} papers still unresolved (check_manually without your decision)")


def cmd_pilot_check(a):
    """Excel sheet with the pilot papers either model flagged check_manually."""
    d = pd.read_csv(C.ROOT / "pilot_results_all300.csv", dtype=str, keep_default_na=False)
    x = d[(d.d_gemini == "check_manually") | (d.d_mistral == "check_manually")].copy()
    blind = pd.read_excel(C.ROOT / "pilot_manual_check.xlsx", dtype=str).set_index("Record_ID")
    x["Human_Decision"] = x.Record_ID.map(lambda i: blind.Human_Decision.get(i, "") if i in blind.index else "")
    x["Human_Reason"] = ""
    cols = ["Record_ID", "Title", "Year", "Journal", "Abstract", "d_gemini", "c_gemini", "d_mistral", "c_mistral",
            "Human_Decision", "Human_Reason"]
    write_xlsx({"Check_Manually": x[cols]}, C.ROOT / "pilot_check_manually.xlsx")
    print(f"{len(x)} papers -> pilot_check_manually.xlsx ({int((x.Human_Decision != '').sum())} already decided in your blind sheet)")


def cmd_merge_pilot(a):
    """One table for all 300 pilot papers: models + Lisa's decisions + Final."""
    d = pd.read_csv(C.ROOT / "pilot_results_all300.csv", dtype=str, keep_default_na=False)
    human = {}
    for fname in ("pilot_manual_check.xlsx", "pilot_check_manually.xlsx"):
        h = pd.read_excel(C.ROOT / fname, dtype=str)
        for _, r in h.dropna(subset=["Human_Decision"]).iterrows():
            human[r["Record_ID"]] = r["Human_Decision"]
    extra = C.ROOT / "pilot_review_decisions.csv"  # decisions Lisa gave in chat for model-disagreement papers
    if extra.exists():
        human.update(dict(pd.read_csv(extra, dtype=str)[["Record_ID", "Human_Decision"]].values))
    d["Human_Decision"] = d.Record_ID.map(human).fillna("")
    def final(r):
        if r.Human_Decision in ("include", "exclude"):
            return r.Human_Decision
        if r.d_gemini == r.d_mistral and r.d_gemini != "check_manually":
            return r.d_gemini
        return "needs_review"
    d["Final"] = d.apply(final, axis=1)
    d.to_csv(C.ROOT / "pilot_final.csv", index=False)
    print(d.Final.value_counts().to_dict())
    print("Wrote pilot_final.csv (all", len(d), "pilot papers)")


def main():
    load_env()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-models")
    s = sub.add_parser("screen")
    s.add_argument("--pilot", action="store_true", help="only the 300 pilot records")
    s.add_argument("--model", choices=list(C.MODELS))
    s.add_argument("--dry-run", action="store_true", help="show request size, no API calls")
    s.add_argument("--mock", action="store_true", help="fake model answers to test the plumbing")
    sub.add_parser("pilot-files")
    sub.add_parser("pilot-check")
    sub.add_parser("merge-pilot")
    sub.add_parser("compare")
    sub.add_parser("export")
    sub.add_parser("finalize")
    a = p.parse_args()
    {"check-models": cmd_check_models, "screen": cmd_screen, "pilot-files": cmd_pilot_files, "pilot-check": cmd_pilot_check, "merge-pilot": cmd_merge_pilot,
     "compare": cmd_compare, "export": cmd_export, "finalize": cmd_finalize}[a.cmd](a)


if __name__ == "__main__":
    main()
