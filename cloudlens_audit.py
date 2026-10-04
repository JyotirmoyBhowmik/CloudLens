#!/usr/bin/env python3
"""
CloudLens Codebase Audit — evidence collector.
Collects FACTS by running commands and scanning files. Never estimates.
Usage (repo root):  python cloudlens_audit.py [--run-tests] [--timeout 3600]
Outputs: audit_output/AUDIT_REPORT.md, audit_output/audit_full.json, audit_output/raw/
Read-only; no cloud calls; secrets redacted.
"""
import argparse, json, os, re, subprocess, sys, time, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path.cwd()
OUT = ROOT / "audit_output"
RAW = OUT / "raw"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", "audit_output", ".next", "coverage"}
CODE_EXT = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
            ".jsx": "JavaScript", ".sql": "SQL", ".yaml": "YAML", ".yml": "YAML",
            ".json": "JSON", ".md": "Markdown", ".toml": "TOML", ".sh": "Shell", ".ps1": "PowerShell"}
SECRET_RX = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret)"
                       r"(\s*[:=]\s*)(['\"]?)[^\s'\",]{6,}")

def redact(s: str) -> str:
    s = SECRET_RX.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}***REDACTED***", s)
    s = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
               "***REDACTED PRIVATE KEY***", s, flags=re.S)
    return s

def run(name, cmd, timeout=300):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                           shell=isinstance(cmd, str), encoding="utf-8", errors="replace")
        out, err, rc = p.stdout, p.stderr, p.returncode
    except FileNotFoundError as e:
        out, err, rc = "", f"NOT FOUND: {e}", -1
    except subprocess.TimeoutExpired:
        out, err, rc = "", f"TIMEOUT after {timeout}s", -2
    dur = round(time.time() - t0, 1)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.txt").write_text(
        redact(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}\nexit={rc} duration={dur}s\n\n--- STDOUT ---\n{out}\n--- STDERR ---\n{err}"),
        encoding="utf-8")
    return {"cmd": cmd if isinstance(cmd, str) else " ".join(cmd), "exit": rc,
            "duration_s": dur, "stdout": redact(out), "stderr": redact(err)}

def walk_files():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            yield Path(dp) / f

def read(p: Path):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def python_exe():
    for cand in [ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python",
                 ROOT / "venv" / "Scripts" / "python.exe", ROOT / "venv" / "bin" / "python"]:
        if cand.exists():
            return str(cand)
    return sys.executable

def git_facts():
    r = {}
    r["head"] = run("git_head", ["git", "rev-parse", "HEAD"])["stdout"].strip()
    r["branch"] = run("git_branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"])["stdout"].strip()
    r["remote"] = run("git_remote", ["git", "remote", "-v"])["stdout"].strip().splitlines()[:2]
    cnt = run("git_count", ["git", "rev-list", "--count", "HEAD"])["stdout"].strip()
    r["commit_count"] = int(cnt) if cnt.isdigit() else None
    r["status_dirty_files"] = len([l for l in run("git_status", ["git", "status", "--porcelain"])["stdout"].splitlines() if l.strip() and "audit_output" not in l])
    log = run("git_log", ["git", "log", "--pretty=format:%h|%ad|%s", "--date=short"])["stdout"].splitlines()
    r["last_40_commits"] = log[:40]
    refs = {}
    for line in log:
        for m in re.findall(r"(?i)\bprompt[\s_-]*(\d{2}[A-Z]?|00R)\b", line):
            refs.setdefault(m.upper(), []).append(line.split("|")[0])
    r["prompt_ids_in_commit_messages"] = {k: v[:5] for k, v in sorted(refs.items())}
    return r

def tree_facts():
    by_top, by_lang, total = {}, {}, {"files": 0, "loc": 0}
    for p in walk_files():
        rel = p.relative_to(ROOT)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        lang = CODE_EXT.get(p.suffix.lower())
        if not lang:
            continue
        loc = sum(1 for l in read(p).splitlines() if l.strip())
        by_top.setdefault(top, {"files": 0, "loc": 0})
        by_top[top]["files"] += 1; by_top[top]["loc"] += loc
        by_lang.setdefault(lang, {"files": 0, "loc": 0})
        by_lang[lang]["files"] += 1; by_lang[lang]["loc"] += loc
        total["files"] += 1; total["loc"] += loc
    subdirs = {}
    for top in ["api", "domain", "connectors", "normalisation", "masterdata", "db", "web", "tests", "ops", "scripts", "docs", "workers"]:
        d = ROOT / top
        if d.is_dir():
            subdirs[top] = sorted(x.name for x in d.iterdir() if x.is_dir() and x.name not in SKIP_DIRS)
        else:
            subdirs[top] = "MISSING"
    return {"by_top_level": dict(sorted(by_top.items(), key=lambda x: -x[1]["loc"])),
            "by_language": by_lang, "total": total, "key_dir_children": subdirs}

def test_facts(py, run_tests, timeout):
    r = {}
    c = run("pytest_collect", [py, "-m", "pytest", "--collect-only", "-q"], timeout=600)
    m = re.search(r"(\d+)\s+tests?\s+collected", c["stdout"] + c["stderr"])
    if not m:
        lines = [l for l in c["stdout"].splitlines() if "::" in l]
        r["collected"] = len(lines) if lines else None
    else:
        r["collected"] = int(m.group(1))
    r["collect_exit"] = c["exit"]
    r["collect_errors"] = len(re.findall(r"(?m)^ERROR ", c["stdout"]))
    per_dir = {}
    for l in c["stdout"].splitlines():
        if "::" in l:
            parts = l.split("::")[0].replace("\\", "/").split("/")
            key = "/".join(parts[:2]) if parts[0] == "tests" and len(parts) > 2 else parts[0]
            per_dir[key] = per_dir.get(key, 0) + 1
    r["collected_by_directory"] = dict(sorted(per_dir.items()))
    if run_tests:
        OUT.mkdir(parents=True, exist_ok=True)
        junit = OUT / "junit.xml"
        t = run("pytest_run", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               f"--junitxml={junit}"], timeout=timeout)
        r["run_exit"] = t["exit"]
        r["run_duration_s"] = t["duration_s"]
        if junit.exists():
            try:
                root = ET.parse(junit).getroot()
                suites = [root] if root.tag == "testsuite" else list(root)
                agg = {k: sum(int(s.get(k, 0)) for s in suites) for k in ["tests", "failures", "errors", "skipped"]}
                agg["passed"] = agg["tests"] - agg["failures"] - agg["errors"] - agg["skipped"]
                r["junit_totals"] = agg
                failed = []
                for tc in root.iter("testcase"):
                    if tc.find("failure") is not None or tc.find("error") is not None:
                        failed.append(f'{tc.get("classname")}::{tc.get("name")}')
                r["failed_tests_first_50"] = failed[:50]
            except Exception as e:
                r["junit_parse_error"] = str(e)
        r["pytest_summary_line"] = (t["stdout"] or "").strip().splitlines()[-3:]
    return r

def quality_gates(py):
    g = {}
    for name, script in [("layering", "scripts/check_layering.py"),
                         ("no_hardcoded_constants", "scripts/check_no_hardcoded_constants.py")]:
        if (ROOT / script).exists():
            res = run(f"gate_{name}", [py, script])
            g[name] = {"exit": res["exit"], "tail": (res["stdout"] + res["stderr"]).strip().splitlines()[-5:]}
        else:
            g[name] = "SCRIPT NOT FOUND"
    res = run("gate_ruff", [py, "-m", "ruff", "check", ".", "--statistics"])
    g["ruff"] = {"exit": res["exit"], "tail": (res["stdout"] + res["stderr"]).strip().splitlines()[-8:]}
    return g

GREP_CHECKS = [
 ("ROLES_ENUM", "Role enum members (expect 9 BBP roles)",
  r"(?i)\b(SUPER_?ADMIN|SUPERUSER|PLATFORM_ADMIN|CLOUD_ADMIN(?:ISTRATOR)?|FINOPS_ADMIN(?:ISTRATOR)?|FINANCE_USER|IT_OPERATIONS_USER|IT_OPS_USER|APPLICATION_OWNER|APP_OWNER|READ_ONLY(?:_USER)?|AUDITOR|BUDGET_OWNER|ENGINEERING_LEAD|DEVELOPER)\b\s*=",
  ("domain", "api", "masterdata"), "9 distinct BBP roles"),
 ("ALERT_TYPES", "Alert type identifiers AL-01..AL-20", r"\bAL-?(\d{2})\b", None, "AL-01 to AL-20 present"),
 ("POLICIES", "Policy identifiers POL-01..POL-18", r"\bPOL-?(\d{2})\b", None, "POL-01 to POL-18 present"),
 ("SUPERUSER_LITERAL_IN_CODE", "Superuser address as literal in application code",
  r"admin@jyotirmoyb\.com", ("api", "domain", "connectors", "normalisation", "web/src", "workers"),
  "ZERO hits in code; present only in seed/master data"),
 ("SUPERUSER_IN_SEED", "Superuser address in master data / seed files",
  r"admin@jyotirmoyb\.com", ("masterdata", "db", "ops", "docs"), ">=1 hit in seed/master data"),
 ("DEMO_MODE", "Demo Mode implementation (Prompt 47)", r"(?i)demo[_ ]?mode", None, "present in domain/api/web"),
 ("SIMULATOR", "Provider simulator (Prompt 47)", r"(?i)simulator", ("connectors",), "present"),
 ("QUOTA", "Quota / headroom (Prompt 54)", r"(?i)\b(quota|headroom)\b", ("domain", "connectors", "api"), "present"),
 ("PROVISIONING_GATE", "Provisioning gate (Prompt 55)", r"(?i)provisioning[_ ]?(request|gate)", ("domain", "api"), "present"),
 ("SHOWBACK", "Showback statements (Prompt 52)", r"(?i)showback|statement_line|dispute", ("domain", "api"), "present"),
 ("BULK_IMPORT", "Bulk import framework (Prompt 53)", r"(?i)dry[_ ]?run|import_run|ImportRun", ("domain", "api"), "present"),
 ("MASTER_REGISTRY", "Master data registry (Prompt 45)", r"(?i)master[_ ]?(data)?[_ ]?registry|MasterRegistry", ("masterdata", "domain"), "present"),
 ("FIRST_SYNC_PROGRESS", "First-sync progress / alert delivery test (Prompt 15B)",
  r"(?i)first[_ ]?sync|alert[_ ]?(delivery[_ ]?)?test|test[_ ]?alert", None, "present"),
 ("REQ_PREFIXES", "Requirement prefixes PR/CST/USE/RUN/DEP/CON (Prompt 00R)",
  r"\b(PR|CST|USE|RUN|DEP|CON)-\d{3}\b", ("docs",), "all six prefixes present"),
 ("BREAK_GLASS", "Break-glass handling (Prompt 49B)", r"(?i)break[_ -]?glass", None, "exactly one path"),
 ("OPENBAO_VAULT", "Secret store integration", r"(?i)\b(openbao|hvac|vault)\b", ("domain", "api", "ops", "connectors"), "present"),
 ("CRED_ENCRYPT_IN_DB", "Credential encryption in app code (D-7)",
  r"(?i)(AESGCM|AES-?256-?GCM|Fernet|encrypt_secret|ciphertext)", ("domain", "db", "api"), "review: should be reference-only"),
 ("RECON_TOLERANCE_LITERAL", "Reconciliation tolerance literals (D-5)",
  r"(?i)(tolerance|variance)[^\n]{0,60}(100(\.0+)?|0\.001|0\.1)\b", ("domain",), "ZERO literals; from master data"),
 ("CRON_0200", "Fixed 02:00 ingestion schedule (D-6)",
  r"(\"0 2 \* \* \*\"|'0 2 \* \* \*'|02:00)", ("domain", "workers", "ops", "api", "connectors"), "configurable per connector"),
 ("RETENTION_90", "90-day retention literal (D-4)", r"(?i)(retention|retain)[^\n]{0,40}\b90\b", None, "35-day DB PITR per BBP"),
 ("MANDATES", "Mandate wording in docs (D-3)", r"(?i)(\b6 core mandates\b|mandate m[1-6])", ("docs", "README.md"),
  "3 mandates: M1 master data, M2 no hard-coding, M3 demo"),
 ("TODO_FIXME", "TODO / FIXME / NotImplemented markers",
  r"(?i)\b(TODO|FIXME|XXX|NotImplementedError|pass\s*#\s*stub)\b", ("api", "domain", "connectors", "normalisation", "web/src"), "low"),
 ("PROVIDER_SDK_ABOVE_CONNECTORS", "Provider SDK import outside connectors/",
  r"(?m)^\s*(from|import)\s+(boto3|botocore|azure\.|google\.cloud|oci)\b", ("api", "domain", "normalisation", "masterdata"), "ZERO"),
]

def path_ok(rel, filt):
    if not filt:
        return True
    rel = rel.replace("\\", "/")
    return any(rel == f or rel.startswith(f.rstrip("/") + "/") for f in filt)

def grep_facts():
    files = [p for p in walk_files() if p.suffix.lower() in CODE_EXT]
    texts = {str(p.relative_to(ROOT)).replace("\\", "/"): read(p) for p in files}
    results = {}
    for cid, desc, rx, filt, expect in GREP_CHECKS:
        crx = re.compile(rx)
        hits, distinct = [], set()
        for rel, txt in texts.items():
            if not path_ok(rel, filt) or rel.startswith("audit_output") or rel == "cloudlens_audit.py":
                continue
            for i, line in enumerate(txt.splitlines(), 1):
                for m in crx.finditer(line):
                    tok = m.group(1) if m.groups() else m.group(0)
                    distinct.add(str(tok).upper())
                    if len(hits) < 25:
                        hits.append(f"{rel}:{i}: {redact(line.strip())[:160]}")
        results[cid] = {"description": desc, "expectation": expect,
                        "hit_count_capped_examples": len(hits), "distinct_tokens": sorted(distinct)[:60],
                        "examples": hits}
    al = {t for t in results["ALERT_TYPES"]["distinct_tokens"] if t.isdigit()}
    results["ALERT_TYPES"]["missing_of_01_20"] = [f"AL-{i:02d}" for i in range(1, 21) if f"{i:02d}" not in al]
    po = {t for t in results["POLICIES"]["distinct_tokens"] if t.isdigit()}
    results["POLICIES"]["missing_of_01_18"] = [f"POL-{i:02d}" for i in range(1, 19) if f"{i:02d}" not in po]
    pref = set(results["REQ_PREFIXES"]["distinct_tokens"])
    results["REQ_PREFIXES"]["missing_prefixes"] = [p for p in ["PR", "CST", "USE", "RUN", "DEP", "CON"] if p not in pref]
    return results

def docs_facts():
    d = {}
    docs = ROOT / "docs"
    d["files"] = sorted(str(p.relative_to(ROOT)) for p in docs.rglob("*") if p.is_file()) if docs.is_dir() else "MISSING"
    rtm = docs / "requirement_traceability_matrix.md"
    if docs.is_dir() and rtm.exists():
        t = read(rtm)
        ids = re.findall(r"\b(BR|FR|PR|CST|USE|RUN|DEP|CON|API|SEC|NFR|DR|AC)-\d{3}\b", t)
        d["rtm_requirement_ids_by_prefix"] = {k: ids.count(k) for k in sorted(set(ids))}
        d["rtm_distinct_requirement_ids"] = len(set(re.findall(r"\b(?:BR|FR|PR|CST|USE|RUN|DEP|CON|API|SEC|NFR|DR|AC)-\d{3}\b", t)))
        status = re.findall(r"(?i)\b(implemented|partially implemented|partial|deferred|not implemented|verified|pending|unverified)\b", t)
        d["rtm_status_words"] = {s.lower(): status.count(s) for s in set(status)}
        acs = set(int(x) for x in re.findall(r"\bAC-(\d{3})\b", t))
        d["rtm_ac_missing_001_104"] = [f"AC-{i:03d}" for i in range(1, 105) if i not in acs]
        d["rtm_ac_missing_110_127"] = [f"AC-{i:03d}" for i in range(110, 128) if i not in acs]
    else:
        d["rtm"] = "NOT FOUND at docs/requirement_traceability_matrix.md"
    return d

def api_facts():
    routes = []
    for p in walk_files():
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if p.suffix == ".py" and rel.startswith("api"):
            for i, l in enumerate(read(p).splitlines(), 1):
                m = re.search(r"@\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)", l)
                if m:
                    routes.append(f"{m.group(1).upper()} {m.group(2)}  ({rel}:{i})")
    return {"route_decorator_count": len(routes), "routes_first_120": routes[:120]}

def web_facts():
    views, pages = ROOT / "web" / "src" / "views", ROOT / "web" / "src" / "pages"
    d = views if views.is_dir() else pages if pages.is_dir() else None
    if not d:
        return {"views": "web/src/views or web/src/pages NOT FOUND"}
    files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.suffix in {".tsx", ".jsx", ".ts"})
    return {"view_dir": str(d.relative_to(ROOT)), "view_file_count": len(files), "view_files": files}

def migration_facts():
    mig = [p for p in walk_files() if "migrations" in p.parts and p.suffix == ".py" and "versions" in p.parts]
    txt = "\n".join(read(p) for p in mig)
    return {"migration_files": len(mig),
            "mentions_partition": len(re.findall(r"(?i)partition", txt)),
            "mentions_row_level_security": len(re.findall(r"(?i)row level security|ENABLE ROW LEVEL SECURITY|CREATE POLICY", txt)),
            "mentions_audit_append_only": len(re.findall(r"(?i)(revoke\s+(update|delete)|prevent.*(update|delete)|append[_ ]only)", txt))}

def md_report(data):
    L = []; a = L.append
    a(f"# CloudLens Audit Report\n\nGenerated: {data['generated_utc']} UTC  |  Repo root: `{ROOT.name}`  |  HEAD: `{data['git'].get('head','')[:12]}`  |  Branch: `{data['git'].get('branch')}`\n")
    a("> Every number below was produced by a command or file scan in this run. Raw outputs are in `audit_output/raw/`.\n")
    g = data["git"]
    a(f"## 1. Git\n- Commits: **{g.get('commit_count')}**  |  Uncommitted files: **{g.get('status_dirty_files')}**")
    a(f"- Prompt IDs referenced in commit messages: `{', '.join(g.get('prompt_ids_in_commit_messages', {}).keys()) or 'none'}`")
    a("\nLast 15 commits:\n```\n" + "\n".join(g.get("last_40_commits", [])[:15]) + "\n```\n")
    t = data["tree"]
    a(f"## 2. Size\n- Code files: **{t['total']['files']}**  |  Non-blank lines: **{t['total']['loc']}**")
    a("\n| Top-level | Files | LOC |\n|---|---|---|")
    for k, v in list(t["by_top_level"].items())[:15]:
        a(f"| {k} | {v['files']} | {v['loc']} |")
    a("\n| Language | Files | LOC |\n|---|---|---|")
    for k, v in sorted(t["by_language"].items(), key=lambda x: -x[1]["loc"]):
        a(f"| {k} | {v['files']} | {v['loc']} |")
    a("\nKey directory children:")
    for k, v in t["key_dir_children"].items():
        a(f"- **{k}/**: {v if isinstance(v, str) else ', '.join(v) or '(no subdirs)'}")
    ts = data["tests"]
    a(f"\n## 3. Tests\n- Collected (pytest --collect-only): **{ts.get('collected')}**  |  collection errors: **{ts.get('collect_errors')}**  |  exit: {ts.get('collect_exit')}")
    if "junit_totals" in ts:
        j = ts["junit_totals"]
        a(f"- EXECUTED: tests **{j['tests']}**, passed **{j['passed']}**, failed **{j['failures']}**, errors **{j['errors']}**, skipped **{j['skipped']}**  (duration {ts.get('run_duration_s')}s)")
        if ts.get("failed_tests_first_50"):
            a("- Failing tests (first 50):\n```\n" + "\n".join(ts["failed_tests_first_50"]) + "\n```")
    else:
        a("- Tests NOT executed in this run (use --run-tests).")
    a("\n| Test directory | Collected |\n|---|---|")
    for k, v in ts.get("collected_by_directory", {}).items():
        a(f"| {k} | {v} |")
    a("\n## 4. Quality gates")
    for k, v in data["gates"].items():
        a(f"- **{k}**: {v if isinstance(v, str) else 'exit ' + str(v['exit']) + ' — ' + ' / '.join(v['tail'][-2:])}")
    a("\n## 5. Specification checks (pattern scans)\n| Check | Expectation | Distinct tokens / hits | Notes |\n|---|---|---|---|")
    for cid, r in data["grep"].items():
        note = ""
        if "missing_of_01_20" in r: note = "missing: " + (", ".join(r["missing_of_01_20"]) or "none")
        if "missing_of_01_18" in r: note = "missing: " + (", ".join(r["missing_of_01_18"]) or "none")
        if "missing_prefixes" in r: note = "missing: " + (", ".join(r["missing_prefixes"]) or "none")
        tok = ", ".join(r["distinct_tokens"][:12]) if r["distinct_tokens"] else "-"
        a(f"| {cid} | {r['expectation']} | {r['hit_count_capped_examples']} hits; {tok[:120]} | {note} |")
    a("\nExamples for review-sensitive checks:")
    for cid in ["ROLES_ENUM", "SUPERUSER_LITERAL_IN_CODE", "CRED_ENCRYPT_IN_DB", "RECON_TOLERANCE_LITERAL",
                "CRON_0200", "RETENTION_90", "MANDATES", "PROVIDER_SDK_ABOVE_CONNECTORS"]:
        ex = data["grep"][cid]["examples"][:6]
        if ex:
            a(f"\n**{cid}**\n```\n" + "\n".join(ex) + "\n```")
    d = data["docs"]
    a("\n## 6. Docs and traceability")
    if isinstance(d.get("files"), list):
        a("- Docs: " + ", ".join(Path(x).name for x in d["files"][:40]))
    for k in ["rtm_distinct_requirement_ids", "rtm_requirement_ids_by_prefix", "rtm_status_words", "rtm"]:
        if k in d: a(f"- {k}: `{d[k]}`")
    if "rtm_ac_missing_001_104" in d:
        a(f"- AC missing from RTM (001-104): **{len(d['rtm_ac_missing_001_104'])}**  |  (110-127): **{len(d['rtm_ac_missing_110_127'])}** -> {', '.join(d['rtm_ac_missing_110_127'])}")
    ap = data["api"]
    a(f"\n## 7. API\n- Route decorators found: **{ap['route_decorator_count']}**\n```\n" + "\n".join(ap["routes_first_120"][:60]) + "\n```")
    w = data["web"]
    a(f"\n## 8. Web\n- {w.get('view_dir', w.get('views'))}: **{w.get('view_file_count', '-')}** view files")
    if w.get("view_files"): a("```\n" + "\n".join(w["view_files"][:60]) + "\n```")
    m = data["migrations"]
    a(f"\n## 9. Database migrations\n- Migration files: **{m['migration_files']}**  |  partition mentions: {m['mentions_partition']}  |  RLS mentions: {m['mentions_row_level_security']}  |  append-only audit mentions: {m['mentions_audit_append_only']}")
    a("\n---\nEnd of report. Paste this file back for review; attach `audit_full.json` if asked.")
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-tests", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
    py = python_exe()
    print(f"[audit] repo={ROOT} python={py}")
    data = {"generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "python": py}
    for key, fn in [("git", git_facts), ("tree", tree_facts),
                    ("tests", lambda: test_facts(py, args.run_tests, args.timeout)),
                    ("gates", lambda: quality_gates(py)), ("grep", grep_facts), ("docs", docs_facts),
                    ("api", api_facts), ("web", web_facts), ("migrations", migration_facts)]:
        print(f"[audit] collecting {key} ...")
        try:
            data[key] = fn()
        except Exception as e:
            data[key] = {"collector_error": repr(e)}
    (OUT / "audit_full.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    try:
        rep = md_report(data)
    except Exception as e:
        rep = f"# CloudLens Audit Report\n\nReport rendering failed: {e!r}. See audit_full.json."
    (OUT / "AUDIT_REPORT.md").write_text(rep, encoding="utf-8")
    print(f"[audit] done -> {OUT / 'AUDIT_REPORT.md'}  ({len(rep)} chars)")

if __name__ == "__main__":
    main()
