#!/usr/bin/env python3
"""
CloudLens Codebase Audit v2 — evidence collector for independent review.

Every figure in the report is produced by a command or file scan in THIS run.
The script never estimates, never edits source files, never calls a cloud API,
and redacts anything resembling a secret before writing output.

Usage (from the repository root, with the project virtualenv):
    python cloudlens_audit_v2.py                      # static checks only (fast)
    python cloudlens_audit_v2.py --run-tests          # + full pytest run (JUnit)
    python cloudlens_audit_v2.py --run-tests --coverage --probe-startup
    python cloudlens_audit_v2.py --run-tests --coverage --probe-startup --timeout 3600

Outputs in ./audit_output/:
    AUDIT_REPORT.md   - paste this back for review (human readable)
    audit_full.json   - complete machine-readable evidence
    raw/              - raw stdout/stderr of every command executed

Sections:
    1 Git & commit discipline      8  Allow-list / exception register
    2 Size & structure              9  Evidence integrity (fat/, docs, README)
    3 Tests (collect, run, skips)  10  Deployment artefacts & tools present
    4 Coverage (optional)          11  API, Web routes & screens
    5 Quality gates                12  Docs & traceability
    6 Persistence & fail-closed    13  Spec pattern checks (v1 checks + new)
    7 Security checks              14  Findings summary (RED / AMBER / GREEN)
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = "2.0"
ROOT = Path.cwd()
OUT = ROOT / "audit_output"
RAW = OUT / "raw"
SELF = Path(__file__).name
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", "audit_output", ".next", "coverage", "test-results",
             "playwright-report", "htmlcov"}
CODE_EXT = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
            ".jsx": "JavaScript", ".sql": "SQL", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
            ".md": "Markdown", ".toml": "TOML", ".sh": "Shell", ".ps1": "PowerShell", ".tpl": "Template"}
APP_DIRS = ("api", "domain", "connectors", "normalisation", "workers")
SECRET_RX = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret)"
                       r"(\s*[:=]\s*)(['\"]?)[^\s'\",]{6,}")
FINDINGS = []  # (severity, area, message)


def finding(sev, area, msg):
    FINDINGS.append({"severity": sev, "area": area, "message": msg})


def redact(s):
    s = SECRET_RX.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}***REDACTED***", s or "")
    return re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                  "***REDACTED PRIVATE KEY***", s, flags=re.S)


def run(name, cmd, timeout=300, env=None):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                           shell=isinstance(cmd, str), encoding="utf-8", errors="replace",
                           env={**os.environ, **(env or {})})
        out, err, rc = p.stdout, p.stderr, p.returncode
    except FileNotFoundError as e:
        out, err, rc = "", f"NOT FOUND: {e}", -1
    except subprocess.TimeoutExpired:
        out, err, rc = "", f"TIMEOUT after {timeout}s", -2
    dur = round(time.time() - t0, 1)
    RAW.mkdir(parents=True, exist_ok=True)
    shown = cmd if isinstance(cmd, str) else " ".join(map(str, cmd))
    (RAW / f"{name}.txt").write_text(
        redact(f"$ {shown}\nexit={rc} duration={dur}s\n\n--- STDOUT ---\n{out}\n--- STDERR ---\n{err}"),
        encoding="utf-8")
    return {"cmd": shown, "exit": rc, "duration_s": dur, "stdout": redact(out), "stderr": redact(err)}


def walk_files():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            yield Path(dp) / f


def rel(p):
    return str(p.relative_to(ROOT)).replace("\\", "/")


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def python_exe():
    for c in [ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python",
              ROOT / "venv" / "Scripts" / "python.exe", ROOT / "venv" / "bin" / "python"]:
        if c.exists():
            return str(c)
    return sys.executable


def in_dirs(r, dirs):
    return any(r == d or r.startswith(d.rstrip("/") + "/") for d in dirs)


def is_test_path(r):
    return r.startswith("tests/") or "/tests/" in r or Path(r).name.startswith("test_")


_TEXTS = None


def texts():
    global _TEXTS
    if _TEXTS is None:
        _TEXTS = {}
        for p in walk_files():
            if p.suffix.lower() in CODE_EXT and p.name != SELF and not rel(p).startswith("audit_output"):
                if p.stat().st_size < 3_000_000:
                    _TEXTS[rel(p)] = read(p)
    return _TEXTS


def grep(rx, dirs=None, exclude_tests=False, flags=0, limit=30):
    crx = re.compile(rx, flags)
    hits, files = [], set()
    for r, t in texts().items():
        if dirs and not in_dirs(r, dirs):
            continue
        if exclude_tests and is_test_path(r):
            continue
        for i, line in enumerate(t.splitlines(), 1):
            if crx.search(line):
                files.add(r)
                if len(hits) < limit:
                    hits.append(f"{r}:{i}: {redact(line.strip())[:170]}")
    return {"files": sorted(files), "file_count": len(files), "examples": hits}


# ============================================================ 1 GIT
def sec_git():
    r = {}
    r["head"] = run("git_head", ["git", "rev-parse", "HEAD"])["stdout"].strip()
    r["branch"] = run("git_branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"])["stdout"].strip()
    r["remote"] = run("git_remote", ["git", "remote", "-v"])["stdout"].strip().splitlines()[:1]
    c = run("git_count", ["git", "rev-list", "--count", "HEAD"])["stdout"].strip()
    r["commit_count"] = int(c) if c.isdigit() else None
    dirty = [l for l in run("git_status", ["git", "status", "--porcelain"])["stdout"].splitlines()
             if l.strip() and "audit_output" not in l and SELF not in l]
    r["uncommitted_files"] = len(dirty)
    r["uncommitted_sample"] = dirty[:20]
    ahead = run("git_ahead", ["git", "rev-list", "--count", "@{u}..HEAD"])
    r["unpushed_commits"] = ahead["stdout"].strip() if ahead["exit"] == 0 else "no upstream"
    log = run("git_log", ["git", "log", "--pretty=format:%h|%ad|%s", "--date=short"])["stdout"].splitlines()
    r["last_25_commits"] = log[:25]
    refs = {}
    for line in log:
        for m in re.findall(r"(?i)\b(?:prompt|r)[\s_-]*(\d{2}[A-Z]?|00R|SEC|QUAL|ROLES|PERSIST(?:\s*tier\s*\d)?|DATA|RUN|OBS|CT|OPS|UI|FEAT|PERF|DOC|FINAL)\b", line):
            refs.setdefault(m.upper(), []).append(line.split("|")[0])
    r["prompt_ids_in_commits"] = {k: v[:4] for k, v in sorted(refs.items())}
    stats = run("git_shortstat", ["git", "log", "-15", "--shortstat", "--pretty=format:@@%h|%s"])["stdout"]
    big = []
    for block in stats.split("@@")[1:]:
        head, _, rest = block.partition("\n")
        m = re.search(r"(\d+) files? changed(?:, (\d+) insertions?)?", rest)
        if m:
            files_changed = int(m.group(1)); ins = int(m.group(2) or 0)
            big.append({"commit": head[:90], "files": files_changed, "insertions": ins})
    r["recent_commit_sizes"] = big
    for b in big:
        if b["files"] > 150 or len(re.findall(r"R-[A-Z]+|Prompt \d", b["commit"])) >= 3:
            finding("AMBER", "Git", f"Very large or multi-prompt commit: {b['commit']} ({b['files']} files, +{b['insertions']}) — hard to review; one prompt per commit expected")
    if r["uncommitted_files"]:
        finding("AMBER", "Git", f"{r['uncommitted_files']} uncommitted files — audit does not reflect a committed state")
    for pid in ["SEC", "QUAL", "ROLES", "PERSIST", "DATA"]:
        if not any(k.startswith(pid) for k in refs):
            finding("AMBER", "Git", f"No commit message references R-{pid}; no commit-level evidence it was executed")
    return r


# ============================================================ 2 SIZE
def sec_size():
    by_top, by_lang, tot = {}, {}, {"files": 0, "loc": 0}
    for r, t in texts().items():
        top = r.split("/")[0] if "/" in r else "(root)"
        lang = CODE_EXT[Path(r).suffix.lower()]
        loc = sum(1 for l in t.splitlines() if l.strip())
        for d, k in ((by_top, top), (by_lang, lang)):
            d.setdefault(k, {"files": 0, "loc": 0}); d[k]["files"] += 1; d[k]["loc"] += loc
        tot["files"] += 1; tot["loc"] += loc
    kids = {}
    for top in ["api", "domain", "connectors", "normalisation", "masterdata", "db", "web", "tests",
                "ops", "scripts", "docs", "workers", "fat"]:
        d = ROOT / top
        kids[top] = sorted(x.name for x in d.iterdir() if x.is_dir() and x.name not in SKIP_DIRS) if d.is_dir() else "MISSING"
    return {"total": tot, "by_top_level": dict(sorted(by_top.items(), key=lambda x: -x[1]["loc"])),
            "by_language": dict(sorted(by_lang.items(), key=lambda x: -x[1]["loc"])), "children": kids}


# ============================================================ 3 TESTS
def sec_tests(py, run_tests, timeout):
    r = {}
    c = run("pytest_collect", [py, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "-p", "no:randomly"], timeout=900)
    ids = [l.strip() for l in c["stdout"].splitlines() if "::" in l]
    r["collected"] = len(ids)
    r["collect_exit"] = c["exit"]
    r["collection_errors"] = len(re.findall(r"(?m)^ERROR ", c["stdout"] + c["stderr"]))
    per = {}
    for i in ids:
        parts = i.split("::")[0].replace("\\", "/").split("/")
        k = parts[1] if parts[0] == "tests" and len(parts) > 2 else parts[0]
        per[k] = per.get(k, 0) + 1
    r["by_directory"] = dict(sorted(per.items(), key=lambda x: -x[1]))
    for d in ("dr", "upgrade", "load", "rbac", "security", "e2e"):
        if per.get(d, 0) <= 3:
            finding("AMBER", "Tests", f"tests/{d} has only {per.get(d, 0)} tests — thin evidence for that test level")
    if run_tests:
        junit = OUT / "junit.xml"
        t = run("pytest_run", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly",
                               "-rs", f"--junitxml={junit}"], timeout=timeout)
        r["run_exit"], r["run_duration_s"] = t["exit"], t["duration_s"]
        r["summary_line"] = (t["stdout"] or "").strip().splitlines()[-1:] if t["stdout"] else [t["stderr"][-300:]]
        r["skip_reasons"] = [l.strip()[:200] for l in t["stdout"].splitlines() if l.startswith("SKIPPED")][:20]
        if junit.exists():
            try:
                root = ET.parse(junit).getroot()
                suites = [root] if root.tag == "testsuite" else list(root)
                agg = {k: sum(int(s.get(k, 0)) for s in suites) for k in ["tests", "failures", "errors", "skipped"]}
                agg["passed"] = agg["tests"] - agg["failures"] - agg["errors"] - agg["skipped"]
                r["junit"] = agg
                r["failed"] = [f'{tc.get("classname")}::{tc.get("name")}' for tc in root.iter("testcase")
                               if tc.find("failure") is not None or tc.find("error") is not None][:50]
                slow = sorted(((float(tc.get("time", 0)), f'{tc.get("classname")}::{tc.get("name")}')
                               for tc in root.iter("testcase")), reverse=True)[:10]
                r["slowest_10"] = [f"{s:.1f}s {n}" for s, n in slow]
                if agg["failures"] or agg["errors"]:
                    finding("RED", "Tests", f"{agg['failures']} failed, {agg['errors']} errors")
            except Exception as e:
                r["junit_error"] = repr(e)
        else:
            finding("RED", "Tests", "Test run produced no JUnit file (crash or timeout) — see raw/pytest_run.txt")
        # randomised order check (detects shared state between tests)
        chk = run("pytest_randomly_check", [py, "-c", "import pytest_randomly"], timeout=60)
        if chk["exit"] != 0:
            r["random_order"] = "pytest-randomly NOT INSTALLED (pip install pytest-randomly to enable)"
        else:
            rr = run("pytest_random", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "randomly",
                                       "--maxfail=5"], timeout=timeout)
            r["random_order"] = {"exit": rr["exit"], "tail": rr["stdout"].strip().splitlines()[-1:]}
            if rr["exit"] != 0:
                finding("AMBER", "Tests", "Suite fails in random order — hidden shared state between tests")
    return r


# ============================================================ 4 COVERAGE
def sec_coverage(py, enabled, timeout):
    if not enabled:
        return {"status": "not run (use --coverage)"}
    targets = [d for d in ("domain", "api", "connectors", "normalisation", "masterdata", "workers") if (ROOT / d).is_dir()]
    args = [py, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider", "-o", "addopts="]
    for t in targets:
        args += [f"--cov={t}"]
    args += ["--cov-report=term", f"--cov-report=xml:{OUT / 'coverage.xml'}"]
    c = run("coverage", args, timeout=timeout)
    total = re.search(r"(?m)^TOTAL\s+\d+\s+\d+\s+(?:\d+\s+\d+\s+)?(\d+)%", c["stdout"])
    res = {"exit": c["exit"], "targets": targets, "total_percent": int(total.group(1)) if total else None}
    low = []
    for line in c["stdout"].splitlines():
        m = re.match(r"^(\S+\.py)\s+(\d+)\s+\d+\s+(?:\d+\s+\d+\s+)?(\d+)%", line)
        if m and int(m.group(2)) >= 40 and int(m.group(3)) < 50:
            low.append(f"{m.group(1)} {m.group(3)}% ({m.group(2)} stmts)")
    res["low_coverage_files_first_25"] = low[:25]
    if res["total_percent"] is not None and res["total_percent"] < 70:
        finding("AMBER", "Coverage", f"Total coverage {res['total_percent']}% across {', '.join(targets)}")
    if res["total_percent"] is None:
        finding("AMBER", "Coverage", "Coverage could not be measured (pytest-cov missing or run failed)")
    return res


# ============================================================ 5 GATES
def sec_gates(py):
    g = {}
    for name, script in [("layering", "scripts/check_layering.py"),
                         ("no_hardcoded_constants", "scripts/check_no_hardcoded_constants.py")]:
        if (ROOT / script).exists():
            res = run(f"gate_{name}", [py, script])
            g[name] = {"exit": res["exit"], "tail": (res["stdout"] + res["stderr"]).strip().splitlines()[-4:]}
            if res["exit"] != 0:
                finding("RED", "Gates", f"{name} gate failed (exit {res['exit']})")
        else:
            g[name] = "SCRIPT NOT FOUND"; finding("AMBER", "Gates", f"{script} not found")
    res = run("gate_ruff", [py, "-m", "ruff", "check", ".", "--statistics"])
    g["ruff"] = {"exit": res["exit"], "tail": (res["stdout"] + res["stderr"]).strip().splitlines()[-6:]}
    res = run("gate_ruff_F", [py, "-m", "ruff", "check", ".", "--select", "F821,F811,F841,F401", "--output-format=concise"])
    g["ruff_F_errors"] = [l for l in res["stdout"].splitlines() if re.search(r":\d+:\d+: F", l)][:30]
    if any(":F821" in x.replace(" F821", ":F821") or " F821 " in x for x in g["ruff_F_errors"]):
        finding("RED", "Gates", "Undefined names (F821) present — code will crash on that path")
    if (ROOT / "web" / "package.json").exists():
        tsc = shutil.which("npx") or shutil.which("npx.cmd")
        if tsc:
            res = run("web_typecheck", "npx --prefix web tsc --noEmit -p web", timeout=600)
            errs = len(re.findall(r"error TS\d+", res["stdout"] + res["stderr"]))
            g["web_typecheck"] = {"exit": res["exit"], "ts_errors": errs}
            if errs:
                finding("AMBER", "Gates", f"TypeScript type errors in web/: {errs}")
        else:
            g["web_typecheck"] = "npx NOT INSTALLED"
    return g


# ============================================================ 6 PERSISTENCE & FAIL-CLOSED
DICT_STATE = r"self\._[a-z_]+\s*:\s*dict\[|self\._[a-z_]+\s*=\s*\{\}|self\._store\s*=|_items\s*:\s*dict"


def sec_persistence(py, probe):
    r = {}
    dict_hold = grep(DICT_STATE, dirs=("domain", "api", "connectors", "workers"), exclude_tests=True, limit=0)
    sql_repo = grep(r"class\s+Sql\w*Repository|class\s+\w*SqlRepository|class\s+Postgres\w*Repository", dirs=("domain", "db"), limit=40)
    session_use = grep(r"AsyncSession|async_sessionmaker|sessionmaker\(|get_session\(|Session\(", dirs=("domain", "api", "db", "workers"), exclude_tests=True, limit=0)
    inmem_cls = grep(r"class\s+InMemory\w+", dirs=("domain",), exclude_tests=True, limit=0)
    r["files_holding_state_in_dicts"] = dict_hold["file_count"]
    r["dict_holder_files"] = dict_hold["files"][:120]
    r["sql_repository_classes_files"] = sql_repo["file_count"]
    r["sql_repository_examples"] = sql_repo["examples"][:20]
    r["files_using_db_session"] = session_use["file_count"]
    r["inmemory_classes_files"] = inmem_cls["file_count"]
    repo_files = [f for f in texts() if f.startswith("domain/") and f.endswith("repository.py")]
    sql_in_repo = [f for f in repo_files if re.search(r"AsyncSession|select\(|insert\(|text\(", texts()[f])]
    r["repository_py_files"] = len(repo_files)
    r["repository_py_using_sql"] = len(sql_in_repo)
    r["repository_py_dict_only"] = sorted(set(repo_files) - set(sql_in_repo))[:80]
    migs = sorted(rel(p) for p in walk_files() if "migrations" in p.parts and p.suffix == ".py"
                  and ("versions" in p.parts or re.match(r"^\d", p.name)))
    r["migration_files"] = migs
    mt = "\n".join(read(ROOT / m) for m in migs)
    tbl = re.findall(r"create_table\(\s*['\"](\w+)['\"]|CREATE TABLE(?: IF NOT EXISTS)?\s+(?:\w+\.)?\"?(\w+)", mt, re.I)
    r["tables_created_in_migrations"] = sorted({a or b for a, b in tbl})
    r["rls_policies_in_migrations"] = len(re.findall(r"(?i)CREATE POLICY|ENABLE ROW LEVEL SECURITY", mt))
    r["set_tenant_setting_in_code"] = grep(r"app\.current_tenant|set_config\(", dirs=("domain", "db", "api"), exclude_tests=True)["file_count"]
    guard = grep(r"(?i)(CLOUDLENS_ENV|environment).{0,80}(production|staging)", dirs=("api", "domain", "workers"), exclude_tests=True, limit=15)
    r["env_guard_examples"] = guard["examples"]
    if r["repository_py_files"] and r["repository_py_using_sql"] < r["repository_py_files"] / 2:
        finding("RED", "Persistence", f"Only {r['repository_py_using_sql']} of {r['repository_py_files']} repository.py files use SQL — most state is in memory and lost on restart")
    if r["files_holding_state_in_dicts"] > 20:
        finding("RED", "Persistence", f"{r['files_holding_state_in_dicts']} non-test files hold state in Python dicts")
    if r["set_tenant_setting_in_code"] == 0 and r["rls_policies_in_migrations"]:
        finding("AMBER", "Persistence", "RLS policies exist but no code sets app.current_tenant — RLS likely not enforced at runtime")
    if probe:
        r["startup_probes"] = {}
        script = ("import sys\n"
                  "try:\n"
                  "    from fastapi.testclient import TestClient\n"
                  "    from api.cloudlens_api.main import app\n"
                  "    with TestClient(app) as c:\n"
                  "        print('HEALTH', c.get('/api/v1/health').status_code)\n"
                  "except (ImportError, ModuleNotFoundError) as e:\n"
                  "    print('PROBE_INCONCLUSIVE import failed', str(e)[:200])\n"
                  "except SystemExit as e:\n"
                  "    print('REFUSED_TO_START exit', e.code)\n"
                  "except Exception as e:\n"
                  "    print('REFUSED_TO_START', type(e).__name__, str(e)[:200])\n")
        for envname in ("production", "staging"):
            res = run(f"probe_startup_{envname}", [py, "-c", script], timeout=180,
                      env={"CLOUDLENS_ENV": envname, "VAULT_ADDR": "http://127.0.0.1:1", "DATABASE_URL": "postgresql+asyncpg://x:x@127.0.0.1:1/x"})
            line = next((l for l in (res["stdout"] + "\n" + res["stderr"]).splitlines() if "HEALTH" in l or "REFUSED" in l or "PROBE_" in l), (res["stderr"] or res["stdout"])[-200:])
            r["startup_probes"][envname] = line
            if "HEALTH 200" in line:
                finding("RED", "Fail-closed", f"In {envname} mode with no Vault/DB reachable the API still starts and /health returns 200 — must refuse to start")
    return r


# ============================================================ 7 SECURITY
def sec_security():
    r = {}
    r["superuser_literal_in_app_code"] = grep(r"admin@jyotirmoyb\.com", dirs=APP_DIRS + ("web/src",), exclude_tests=True)
    r["email_identity_comparison"] = grep(r"\.email\s*==\s*['\"][^'\"]+@|['\"][^'\"]+@[^'\"]+['\"]\s*==\s*\w+\.email", dirs=APP_DIRS, exclude_tests=True)
    r["email_literals_in_app_code"] = grep(r"['\"][\w.+-]+@[\w-]+\.[\w.]+['\"]", dirs=APP_DIRS + ("web/src",), exclude_tests=True, limit=25)
    r["secret_like_defaults"] = grep(r"(?i)(token|secret|password|passwd|api_key|client_secret)\w*\s*[:=][^\n]{0,40}default\s*=\s*['\"][^'\"]{4,}['\"]|(token|secret|password)\s*:\s*str\s*=\s*['\"][^'\"]{4,}['\"]", dirs=APP_DIRS, exclude_tests=True)
    r["inmemory_secret_fallback"] = grep(r"(?i)fallback.{0,40}(in.?memory|InMemorySecretStore)|_fallback_store", dirs=("domain",), exclude_tests=True)
    r["health_check_always_true"] = grep(r"def health_check\(self\)[^\n]*:\s*$", dirs=("domain",), exclude_tests=True)
    always_true = []
    for f in r["health_check_always_true"]["files"]:
        t = texts()[f]
        for m in re.finditer(r"def health_check\(self\)[^\n]*:\s*\n(\s+)(return True)", t):
            always_true.append(f)
    r["health_check_returns_constant_true"] = sorted(set(always_true))
    r["break_glass_endpoints"] = grep(r"break.?glass", dirs=("api",), exclude_tests=True, flags=re.I)
    r["break_glass_provision_route"] = grep(r"break.?glass/provision", dirs=("api", "docs"), flags=re.I)
    r["secret_returned_or_printed"] = grep(r"(?i)(return|print|logger\.\w+)\(?[^\n]{0,40}\b(secret|password)\b(?!_ref)", dirs=APP_DIRS, exclude_tests=True)
    r["cors_wildcard"] = grep(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]", dirs=("api",), exclude_tests=True)
    r["debug_true"] = grep(r"(?i)\bdebug\s*=\s*True\b", dirs=APP_DIRS, exclude_tests=True)
    r["verify_false"] = grep(r"verify\s*=\s*False", dirs=APP_DIRS, exclude_tests=True)
    r["sql_string_format"] = grep(r"(?i)(execute|text)\(\s*f['\"].*(select|insert|update|delete)", dirs=APP_DIRS, exclude_tests=True)
    if r["superuser_literal_in_app_code"]["file_count"]:
        finding("RED", "Security", "Superuser email literal in application code")
    if r["email_identity_comparison"]["file_count"]:
        finding("RED", "Security", "Identity decided by comparing an email to a literal")
    if r["inmemory_secret_fallback"]["file_count"]:
        finding("RED", "Security", "Secret store has an in-memory fallback — credentials may silently live in process memory")
    if r["health_check_returns_constant_true"]:
        finding("RED", "Security", f"health_check() returns constant True in: {', '.join(r['health_check_returns_constant_true'][:5])}")
    if r["secret_like_defaults"]["file_count"]:
        finding("RED", "Security", "Secret-like default values in code")
    if r["break_glass_provision_route"]["file_count"]:
        finding("AMBER", "Security", "A break-glass provision route still referenced — only one break-glass path is allowed")
    for k, sev in [("cors_wildcard", "AMBER"), ("debug_true", "AMBER"), ("verify_false", "AMBER"), ("sql_string_format", "RED")]:
        if r[k]["file_count"]:
            finding(sev, "Security", f"{k.replace('_', ' ')}: {r[k]['file_count']} file(s)")
    r["sample_people_in_app_code"] = grep(r"(alice|bob|carol|dave)@example\.com|@company\.com|@enterprise\.com", dirs=APP_DIRS, exclude_tests=True)
    if r["sample_people_in_app_code"]["file_count"]:
        finding("AMBER", "Data", f"Sample people/emails embedded in {r['sample_people_in_app_code']['file_count']} production code file(s) — should live only in the Demo Mode generator")
    return r


# ============================================================ 8 ALLOW-LIST
def sec_allowlist():
    r = {}
    for cand in ["docs/configuration/exception_register.json", "docs/configuration/exception_register.md"]:
        p = ROOT / cand
        if p.exists():
            t = read(p)
            r["file"] = cand
            if cand.endswith(".json"):
                try:
                    data = json.loads(t)
                    items = data if isinstance(data, list) else data.get("exceptions") or data.get("entries") or []
                    r["count"] = len(items)
                    by = {}
                    for it in items:
                        k = str(it.get("file") or it.get("path") or "?").split("/")[0:2]
                        k = "/".join(k)
                        by[k] = by.get(k, 0) + 1
                    r["by_area"] = dict(sorted(by.items(), key=lambda x: -x[1])[:20])
                    r["missing_reason_or_reviewer"] = sum(1 for it in items if not (it.get("reason") or it.get("rationale")) or not (it.get("reviewer") or it.get("approved_by")))
                except Exception as e:
                    r["parse_error"] = repr(e)
            sensitive = [l.strip()[:180] for l in t.splitlines() if re.search(r"(?i)reconcil|tolerance|statement|threshold|@|token|secret|password|tenant|admin", l)]
            r["sensitive_entries_first_30"] = sensitive[:30]
            break
    if "count" in r:
        if r["count"] > 25:
            finding("AMBER", "Gates", f"Hard-coding gate passes with {r['count']} allow-listed exceptions — review whether findings were exempted rather than fixed")
        if r.get("missing_reason_or_reviewer"):
            finding("AMBER", "Gates", f"{r['missing_reason_or_reviewer']} exceptions lack a reason or reviewer")
    lit = grep(r"Decimal\(\s*['\"]\d+(\.\d+)?['\"]\s*\)", dirs=("domain/cost/reconciliation", "domain/statements", "domain/thresholds"), exclude_tests=True)
    r["decimal_literals_in_financial_logic"] = lit
    cmp_lit = grep(r"(>=|<=|>|<)\s*Decimal\(\s*['\"]\d", dirs=("domain",), exclude_tests=True)
    r["comparisons_against_decimal_literals"] = cmp_lit
    if cmp_lit["file_count"]:
        finding("AMBER", "Mandate M2", f"Thresholds compared against Decimal literals in {cmp_lit['file_count']} file(s) — should come from master data")
    return r


# ============================================================ 9 EVIDENCE INTEGRITY
def sec_evidence():
    r = {}
    fat = ROOT / "fat"
    r["fat_files"] = sorted(f"{rel(p)} ({p.stat().st_size} B)" for p in fat.rglob("*") if p.is_file()) if fat.is_dir() else "fat/ MISSING"
    imgs = [p for p in (fat.rglob("*") if fat.is_dir() else []) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    img_info = []
    for p in imgs:
        b = p.read_bytes()[:65536]
        markers = [m for m in [b"Playwright", b"HeadlessChrome", b"Chrome", b"Skia", b"c2pa", b"C2PA", b"jumb",
                               b"DALL", b"Imagen", b"Midjourney", b"Stable Diffusion", b"Gemini", b"trainedAlgorithmicMedia",
                               b"Adobe", b"Exif"] if m in b]
        log = run(f"img_log_{p.stem}", ["git", "log", "--format=%h %ad %s", "--date=short", "--", rel(p)])["stdout"].strip()
        img_info.append({"file": rel(p), "bytes": p.stat().st_size, "embedded_markers": [m.decode() for m in markers], "git_log": log[:200]})
        ai = [m for m in markers if m in (b"c2pa", b"C2PA", b"jumb", b"DALL", b"Imagen", b"Midjourney", b"Stable Diffusion", b"Gemini", b"trainedAlgorithmicMedia")]
        if ai:
            finding("RED", "Evidence", f"{rel(p)} carries AI-generation / content-credential markers {[m.decode() for m in ai]} — not valid test evidence")
        elif not markers:
            finding("AMBER", "Evidence", f"{rel(p)} has no browser/tool provenance markers — confirm it is a real capture")
    r["images"] = img_info
    # numbers in evidence that do not come from any generated output
    num_rx = r"(\d+(\.\d+)?\s?(s|ms|m|min|%)\b|\$\s?\d[\d,]*(\.\d+)?|ROI|\d+(\.\d+)?\s?[x×]\b)"
    claims = grep(num_rx, dirs=("fat", "README.md", "docs/cost-register.md"), limit=60)
    r["numeric_claims_sample"] = claims["examples"]
    hard_in_scripts = grep(r"(?i)(rto|rpo|restore|failover|latency|p95|roi|saving|per.?day|cost)[^\n]{0,40}[=:]\s*['\"]?\$?\d[\d,.]*", dirs=("scripts",), exclude_tests=True, limit=30)
    r["metric_values_hardcoded_in_scripts"] = hard_in_scripts
    if hard_in_scripts["file_count"]:
        finding("RED", "Evidence", f"Metric values (RTO/RPO/latency/cost/ROI) appear hard-coded in {hard_in_scripts['file_count']} script(s) that generate FAT evidence — they must be measured, not written")
    # claims of tool usage without the tool installed
    tool_claims = {"helm": r"helm (lint|install|template)", "kubeconform": r"kubeconform", "gitleaks": r"gitleaks",
                   "trivy": r"trivy", "k6": r"\bk6\b", "zap": r"(?i)owasp zap|zap-baseline", "cosign": r"cosign (sign|verify)",
                   "kubectl": r"kubectl"}
    r["tool_claims"] = {}
    for tool, rx in tool_claims.items():
        mentioned = grep(rx, dirs=("fat", "README.md", "docs"), limit=3)["file_count"]
        installed = bool(shutil.which(tool) or shutil.which(tool + ".exe") or (tool == "zap" and shutil.which("zap-baseline.py")))
        r["tool_claims"][tool] = {"mentioned_in_evidence_files": mentioned, "installed_on_this_machine": installed}
        if mentioned and not installed:
            finding("AMBER", "Evidence", f"Evidence/docs cite '{tool}' results but {tool} is not installed here — results cannot have been produced on this machine")
    r["agent_named_pen_test"] = [rel(p) for p in walk_files() if re.search(r"(?i)penetration.?test", p.name)]
    if r["agent_named_pen_test"]:
        finding("AMBER", "Evidence", f"File named as a penetration test: {r['agent_named_pen_test']} — must not be presented as an independent pen test (SEC-024)")
    acc = ROOT / "fat" / "ACCEPTANCE.md"
    if acc.exists():
        t = read(acc)
        r["acceptance_status_counts"] = {s: len(re.findall(rf"\b{s}\b", t)) for s in ["PASS", "FAIL", "UNVERIFIED", "NOT TESTABLE"]}
        rows = {m: re.search(rf"[^\n]*{m}[^\n]*", t) for m in ["AC-040", "AC-101", "AC-103", "AC-104"]}
        r["acceptance_key_rows"] = {k: (v.group(0)[:200] if v else "absent") for k, v in rows.items()}
        if rows["AC-040"] and "PASS" in rows["AC-040"].group(0):
            finding("RED", "Evidence", "AC-040 (two closed billing periods reconciled) marked PASS — impossible without live billing periods")
        if rows["AC-104"] and "PASS" in rows["AC-104"].group(0):
            finding("RED", "Evidence", "AC-104 (independent pen test findings resolved) marked PASS — no independent test exists")
    return r


# ============================================================ 10 DEPLOYMENT
def sec_deploy():
    r = {}
    ops = ROOT / "ops"
    r["ops_tree"] = sorted(rel(p) for p in ops.rglob("*") if p.is_file())[:150] if ops.is_dir() else "MISSING"
    charts = [p.parent for p in ROOT.rglob("Chart.yaml") if not any(s in p.parts for s in SKIP_DIRS)]
    r["helm_charts"] = [rel(c) for c in charts]
    r["helm_templates"] = {rel(c): sorted(x.name for x in (c / "templates").glob("*")) if (c / "templates").is_dir() else [] for c in charts}
    vals = [p for c in charts for p in c.glob("values*.y*ml")]
    sec_in_values = []
    for v in vals:
        for i, line in enumerate(read(v).splitlines(), 1):
            if re.search(r"(?i)(password|secret|token|apikey|api_key)\s*:\s*['\"]?[^\s'\"#{}]{6,}", line) and "vault:" not in line and "secretRef" not in line:
                sec_in_values.append(f"{rel(v)}:{i}: {redact(line.strip())[:120]}")
    r["possible_secrets_in_values"] = sec_in_values[:20]
    if sec_in_values:
        finding("RED", "Deployment", f"Possible secret values in Helm values files: {len(sec_in_values)}")
    r["dockerfiles"] = sorted(rel(p) for p in walk_files() if p.name.lower().startswith("dockerfile"))
    root_user = [d for d in r["dockerfiles"] if not re.search(r"(?m)^\s*USER\s+(?!root)", read(ROOT / d))]
    r["dockerfiles_without_non_root_user"] = root_user
    if root_user:
        finding("AMBER", "Deployment", f"Dockerfiles without a non-root USER: {root_user}")
    r["compose_services"] = []
    for cf in list(ROOT.glob("ops/docker-compose*.y*ml")) + list(ROOT.glob("docker-compose*.y*ml")):
        r["compose_services"] += [f"{cf.name}:{s}" for s in re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):\s*$", read(cf))]
    tools = {}
    for t, args in {"docker": ["docker", "--version"], "helm": ["helm", "version", "--short"], "kubectl": ["kubectl", "version", "--client"],
                    "kubeconform": ["kubeconform", "-v"], "gitleaks": ["gitleaks", "version"], "trivy": ["trivy", "--version"],
                    "k6": ["k6", "version"], "cosign": ["cosign", "version"], "node": ["node", "--version"], "pnpm": ["pnpm", "--version"]}.items():
        if shutil.which(args[0]) or shutil.which(args[0] + ".exe") or shutil.which(args[0] + ".cmd"):
            res = run(f"tool_{t}", args, timeout=30)
            tools[t] = (res["stdout"] or res["stderr"]).strip().splitlines()[0][:80] if (res["stdout"] or res["stderr"]) else f"exit {res['exit']}"
        else:
            tools[t] = "NOT INSTALLED"
    r["tools_on_machine"] = tools
    if tools.get("helm") != "NOT INSTALLED" and charts:
        lint = run("helm_lint", ["helm", "lint", str(charts[0])], timeout=120)
        r["helm_lint"] = {"exit": lint["exit"], "tail": (lint["stdout"] + lint["stderr"]).strip().splitlines()[-3:]}
        if lint["exit"] != 0:
            finding("RED", "Deployment", "helm lint failed")
    elif charts:
        r["helm_lint"] = "helm NOT INSTALLED — chart not validated"
    if not charts:
        finding("AMBER", "Deployment", "No Helm chart found (Chart.yaml)")
    wk = texts()
    beat = grep(r"beat_schedule|PersistentScheduler|DatabaseScheduler|crontab\(", dirs=("workers", "domain"), limit=10)
    tasks = sorted(set(m for f, t in wk.items() if f.startswith("workers/") or f.startswith("domain/")
                       for m in re.findall(r"@\w+\.task\(\s*name\s*=\s*['\"]([^'\"]+)", t)))
    r["celery_tasks"] = tasks
    r["beat_schedule_examples"] = beat["examples"]
    if len(tasks) < 8:
        finding("AMBER", "Runtime", f"Only {len(tasks)} Celery tasks registered — scheduled ingestion/evaluation may be missing")
    if not beat["file_count"]:
        finding("AMBER", "Runtime", "No Celery beat schedule found — nothing runs automatically")
    return r


# ============================================================ 11 API & WEB
def sec_api_web():
    r = {}
    routes = []
    for f, t in texts().items():
        if f.startswith("api/") and f.endswith(".py"):
            prefix = re.search(r"APIRouter\([^)]*prefix\s*=\s*['\"]([^'\"]+)", t)
            pre = prefix.group(1) if prefix else ""
            for i, l in enumerate(t.splitlines(), 1):
                m = re.search(r"@\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]*)", l)
                if m:
                    routes.append(f"{m.group(1).upper():6} {pre}{m.group(2)}")
    r["route_count"] = len(routes)
    groups = {}
    for x in routes:
        seg = x.split()[1].split("/")
        key = "/".join(seg[:4]) if len(seg) > 3 else x.split()[1]
        groups[key] = groups.get(key, 0) + 1
    r["routes_by_prefix"] = dict(sorted(groups.items(), key=lambda x: -x[1])[:60])
    unauth = []
    for f, t in texts().items():
        if f.startswith("api/") and "routes" in f:
            for m in re.finditer(r"@\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]*)[^\n]*\n(?:\s*@[^\n]*\n)*\s*(?:async\s+)?def\s+\w+\(([^)]*)\)", t, re.S):
                params = m.group(3)
                if not re.search(r"Depends|tenant_context|current_user|auth", params) and "health" not in m.group(2) and m.group(2) not in ("/", "/about", "/oidc/login", "/saml/login", "/token/refresh"):
                    unauth.append(f"{f}: {m.group(1).upper()} {m.group(2)}")
    r["routes_without_visible_auth_dependency_first_40"] = unauth[:40]
    r["routes_without_visible_auth_dependency_count"] = len(unauth)
    if len(unauth) > 10:
        finding("AMBER", "Security", f"{len(unauth)} routes have no visible auth/tenant dependency in their signature — verify they are protected by middleware")
    pages = ROOT / "web" / "src" / "pages"
    r["web_pages"] = sorted(rel(p).replace("web/src/pages/", "") for p in pages.rglob("*.tsx")) if pages.is_dir() else "MISSING"
    router = grep(r"<Route\b|createBrowserRouter|path:\s*['\"]/", dirs=("web/src",), limit=80)
    r["web_route_definitions"] = router["examples"]
    r["web_route_count"] = len(router["examples"])
    if (ROOT / "web" / "src" / "pages" / "DesignSystemShowcase.tsx").exists():
        dev_guard = grep(r"DesignSystemShowcase", dirs=("web/src",), limit=10)
        r["design_showcase_refs"] = dev_guard["examples"]
    screens = {"S-01 Login": "Login", "S-02 Landing": "Landing", "S-03 Executive": "Executive", "S-04 Provider": "Provider",
               "S-05 Hierarchy": "Hierarchy", "S-06 Inventory": "Inventory", "S-07 Resource": "ResourceDetail",
               "S-08 Cost": "CostExplorer", "S-09 Usage": "Usage", "S-10 Runtime": "Runtime", "S-11 Dependency": "Dependency",
               "S-12 Budget": "BudgetManagement", "S-13 Policy": "Policy", "S-14 Onboarding": "Onboarding",
               "S-15 Connectors": "Connector", "S-16 Admin": "Admin", "S-17 RBAC": "Rbac|Users", "S-18 Audit": "Audit",
               "S-19 Reports": "Report", "S-20 Settings": "Settings", "S-21 Estimator": "Estimator", "S-22 Quota": "Quota",
               "S-23 Provisioning": "Provisioning", "S-24 Tasks": "Remediation|Task", "S-25 Statements": "Statement|Showback",
               "S-26 Planning": "Planning", "S-27 Commitments": "Commitment", "Control Tower": "ControlTower"}
    names = " ".join(r["web_pages"]) if isinstance(r["web_pages"], list) else ""
    r["screen_presence"] = {k: bool(re.search(v, names, re.I)) for k, v in screens.items()}
    missing = [k for k, v in r["screen_presence"].items() if not v]
    if missing:
        finding("AMBER", "Web", f"Screens without a matching page file: {', '.join(missing)}")
    e2e = [rel(p) for p in (ROOT / "web").rglob("*.spec.ts")] if (ROOT / "web").is_dir() else []
    r["playwright_specs"] = [x for x in e2e if "node_modules" not in x][:40]
    return r


# ============================================================ 12 DOCS
def sec_docs():
    d = {}
    docs = ROOT / "docs"
    d["files"] = sorted(rel(p) for p in docs.rglob("*") if p.is_file()) if docs.is_dir() else "MISSING"
    names = [Path(x).stem.replace("-", "_") for x in d["files"]] if isinstance(d["files"], list) else []
    d["duplicate_doc_names"] = sorted({n for n in names if names.count(n) > 1})
    if d["duplicate_doc_names"]:
        finding("AMBER", "Docs", f"Duplicate documents: {d['duplicate_doc_names']}")
    rtm = docs / "requirement_traceability_matrix.md"
    if rtm.exists():
        t = read(rtm)
        ids = re.findall(r"\b(BR|FR|PR|CST|USE|RUN|DEP|CON|API|SEC|NFR|DR|AC)-\d{3}\b", t)
        d["rtm_ids_by_prefix"] = {k: ids.count(k) for k in sorted(set(ids))}
        d["rtm_distinct_ids"] = len(set(re.findall(r"\b(?:BR|FR|PR|CST|USE|RUN|DEP|CON|API|SEC|NFR|DR|AC)-\d{3}\b", t)))
        st = re.findall(r"(?i)\b(implemented - unverified|unverified|verified|implemented|partial|deferred|not implemented|pass|fail)\b", t)
        d["rtm_status_words"] = {s.lower(): st.count(s) for s in set(st)}
        d["rtm_rows_with_test_reference"] = len(re.findall(r"tests/[\w/]+\.py", t))
    reg = docs / "requirements-register.md"
    if reg.exists():
        acs = set(int(x) for x in re.findall(r"AC-(\d{3})", read(reg)))
        d["register_ac_count"] = len(acs)
    readme = ROOT / "README.md"
    if readme.exists():
        t = read(readme)
        d["readme_claims"] = [l.strip()[:160] for l in t.splitlines() if re.search(r"(?i)\b(rto|rpo|roi|\d+ ?(tests|passed)|retained for|\$\d|zero[- ]downtime|production[- ]ready)\b", l)][:25]
    return d


# ============================================================ 13 SPEC CHECKS
SPEC = [
 ("ROLES_BBP_NINE", r"\b(SUPER_ADMIN|PLATFORM_ADMIN|CLOUD_ADMINISTRATOR|FINOPS_ADMINISTRATOR|FINANCE_USER|IT_OPERATIONS_USER|APPLICATION_OWNER|READ_ONLY_USER|AUDITOR)\s*=", ("domain",), 9),
 ("ROLES_NON_BBP", r"\b(GLOBAL_ADMIN|TENANT_ADMIN|FINOPS_ADMIN|FINOPS_ANALYST|FINOPS_VIEWER|CLOUD_ARCHITECT|DEVELOPER|SECURITY_AUDITOR|TENANT_USER)\s*=", ("domain",), 0),
 ("ALERT_IDS", r"\bAL-(\d{2})\b", None, 20),
 ("POLICY_IDS", r"\bPOL-(\d{2})\b", None, 18),
 ("REQ_PREFIXES", r"\b(PR|CST|USE|RUN|DEP|CON)-\d{3}\b", ("docs",), 6),
 ("PLATFORM_OBSERVE", r"platform\.observe|PLATFORM_OBSERVE", ("domain", "api", "masterdata"), 1),
 ("ACT_AS_TENANT", r"(?i)act[_-]as", ("api", "domain"), 1),
 ("CONTROL_TOWER", r"(?i)control[_-]?tower", ("api", "domain", "web/src"), 1),
 ("DEMO_MODE", r"(?i)demo[_ ]?mode", ("api", "domain", "web/src"), 1),
 ("SIMULATOR", r"(?i)class\s+\w*Simulator\w*", ("connectors",), 1),
 ("QUOTA", r"(?i)\bquota", ("domain", "api"), 1),
 ("PROVISIONING_GATE", r"(?i)provisioning[_ ]?(request|gate)", ("domain", "api"), 1),
 ("SHOWBACK", r"(?i)showback", ("domain", "api"), 1),
 ("BULK_IMPORT_DRYRUN", r"(?i)dry[_-]?run", ("domain", "api"), 1),
 ("MASTER_REGISTRY", r"SYSTEM_MASTER_REGISTRY|MasterRegistry", ("masterdata", "domain"), 1),
 ("MAINTENANCE_MODE", r"(?i)maintenance[_ ]?mode", ("domain", "api"), 1),
 ("SESSION_REVOKE", r"(?i)/sessions|revoke_session", ("api",), 1),
 ("FIRST_SYNC", r"(?i)first[_ ]?sync", ("api", "domain", "connectors"), 1),
 ("ALERT_DELIVERY_TEST", r"(?i)alert[_ ]?delivery[_ ]?test|test[_ ]?alert", ("api", "domain"), 1),
 ("PROVIDER_SDK_LEAK", r"(?m)^\s*(from|import)\s+(boto3|botocore|azure\.|google\.cloud|oci)\b", ("api", "domain", "normalisation", "masterdata", "workers"), 0),
 ("TODO_FIXME", r"\b(TODO|FIXME|XXX)\b", APP_DIRS + ("web/src",), None),
 ("NOT_IMPLEMENTED_OUTSIDE_ABSTRACT", r"raise NotImplementedError", ("domain", "api", "workers"), None),
 ("PASS_ONLY_FUNCTIONS", r"def \w+\([^)]*\)[^:]*:\s*pass\s*$", APP_DIRS, None),
]


def sec_spec():
    out = {}
    for cid, rx, dirs, expect in SPEC:
        g = grep(rx, dirs=dirs, exclude_tests=cid not in ("ALERT_IDS", "POLICY_IDS", "REQ_PREFIXES"), limit=12)
        toks = set()
        crx = re.compile(rx)
        for f in g["files"]:
            for m in crx.finditer(texts()[f]):
                toks.add(m.group(1) if m.groups() else m.group(0))
        res = {"files": g["file_count"], "distinct": len(toks), "tokens": sorted(map(str, toks))[:25], "examples": g["examples"][:6], "expect": expect}
        if cid == "ALERT_IDS":
            res["missing"] = [f"AL-{i:02d}" for i in range(1, 21) if f"{i:02d}" not in toks]
        if cid == "POLICY_IDS":
            res["missing"] = [f"POL-{i:02d}" for i in range(1, 19) if f"{i:02d}" not in toks]
        if cid == "REQ_PREFIXES":
            res["missing"] = [p for p in ["PR", "CST", "USE", "RUN", "DEP", "CON"] if p not in toks]
        out[cid] = res
        if expect == 0 and g["file_count"]:
            finding("AMBER" if cid != "PROVIDER_SDK_LEAK" else "RED", "Spec", f"{cid}: expected none, found {g['file_count']} file(s)")
        elif expect and expect > 1 and res["distinct"] < expect:
            finding("AMBER", "Spec", f"{cid}: expected {expect}, found {res['distinct']}")
        elif expect == 1 and not g["file_count"]:
            finding("AMBER", "Spec", f"{cid}: not found")
    return out


# ============================================================ REPORT
def _blank(k, err):
    e = {"files": [], "file_count": 0, "examples": []}
    base = {"git": {}, "size": {"total": {"files": 0, "loc": 0}, "by_top_level": {}, "by_language": {}, "children": {}},
            "tests": {}, "coverage": {"status": "collector error"}, "gates": {},
            "persistence": {"repository_py_files": 0, "repository_py_using_sql": 0, "files_holding_state_in_dicts": 0,
                            "files_using_db_session": 0, "inmemory_classes_files": 0, "sql_repository_classes_files": 0,
                            "migration_files": [], "tables_created_in_migrations": [], "rls_policies_in_migrations": 0,
                            "set_tenant_setting_in_code": 0},
            "security": {**{x: e for x in ["superuser_literal_in_app_code", "email_identity_comparison", "secret_like_defaults",
                            "inmemory_secret_fallback", "break_glass_provision_route", "secret_returned_or_printed", "cors_wildcard",
                            "debug_true", "verify_false", "sql_string_format", "sample_people_in_app_code", "email_literals_in_app_code"]},
                         "health_check_returns_constant_true": []},
            "allowlist": {"comparisons_against_decimal_literals": e},
            "evidence": {"fat_files": [], "images": [], "tool_claims": {}, "metric_values_hardcoded_in_scripts": e, "numeric_claims_sample": []},
            "deploy": {"helm_charts": [], "helm_templates": {}, "possible_secrets_in_values": [], "dockerfiles": [],
                       "dockerfiles_without_non_root_user": [], "compose_services": [], "celery_tasks": [], "beat_schedule_examples": [],
                       "tools_on_machine": {}},
            "api_web": {"route_count": 0, "routes_without_visible_auth_dependency_count": 0, "routes_by_prefix": {},
                        "routes_without_visible_auth_dependency_first_40": [], "web_pages": [], "web_route_count": 0,
                        "playwright_specs": [], "screen_presence": {}},
            "docs": {"files": [], "duplicate_doc_names": []}, "spec": {}}[k]
    base["_collector_error"] = (err or {}).get("collector_error") if isinstance(err, dict) else None
    return base


def md(data):
    for k in ['git','size','tests','coverage','gates','persistence','security','allowlist','evidence','deploy','api_web','docs','spec']:
        if not isinstance(data.get(k), dict) or 'collector_error' in data.get(k, {}):
            data[k] = _blank(k, data.get(k))
    L = []; a = L.append
    g = data["git"]
    a(f"# CloudLens Audit Report v{VERSION}\n")
    a(f"Generated **{data['generated_utc']} UTC** | repo `{ROOT.name}` | HEAD `{g.get('head','')[:12]}` | branch `{g.get('branch')}` | python `{data['python']}`\n")
    a("> Every figure below was produced by a command or file scan in this run. Raw outputs: `audit_output/raw/`. Flags: `--run-tests` " +
      ("ON" if data["flags"]["run_tests"] else "OFF") + ", `--coverage` " + ("ON" if data["flags"]["coverage"] else "OFF") +
      ", `--probe-startup` " + ("ON" if data["flags"]["probe_startup"] else "OFF") + "\n")
    reds = [f for f in FINDINGS if f["severity"] == "RED"]; ambers = [f for f in FINDINGS if f["severity"] == "AMBER"]
    a(f"## 0. Findings summary — RED {len(reds)} | AMBER {len(ambers)}\n")
    a("| # | Severity | Area | Finding |\n|---|---|---|---|")
    for i, f in enumerate(reds + ambers, 1):
        a(f"| {i} | {f['severity']} | {f['area']} | {f['message']} |")
    a("\n## 1. Git")
    a(f"- Commits **{g.get('commit_count')}** | uncommitted **{g.get('uncommitted_files')}** | unpushed **{g.get('unpushed_commits')}**")
    a(f"- Prompt IDs in commit messages: `{', '.join(g.get('prompt_ids_in_commits', {}).keys()) or 'none'}`")
    a("- Recent commit sizes:\n```\n" + "\n".join(f"{c['files']:>4} files +{c['insertions']:<7} {c['commit']}" for c in g.get("recent_commit_sizes", [])) + "\n```")
    a("Last 15 commits:\n```\n" + "\n".join(g.get("last_25_commits", [])[:15]) + "\n```")
    if g.get("uncommitted_sample"):
        a("Uncommitted:\n```\n" + "\n".join(g["uncommitted_sample"]) + "\n```")
    s = data["size"]
    a(f"\n## 2. Size\n- Files **{s['total']['files']}** | non-blank lines **{s['total']['loc']}**\n\n| Top-level | Files | LOC |\n|---|---|---|")
    for k, v in list(s["by_top_level"].items())[:18]:
        a(f"| {k} | {v['files']} | {v['loc']} |")
    a("\n| Language | Files | LOC |\n|---|---|---|")
    for k, v in s["by_language"].items():
        a(f"| {k} | {v['files']} | {v['loc']} |")
    a("\nKey directories:")
    for k, v in s["children"].items():
        a(f"- **{k}/**: {v if isinstance(v, str) else ', '.join(v) or '(files only)'}")
    t = data["tests"]
    a(f"\n## 3. Tests\n- Collected **{t.get('collected')}** | collection errors **{t.get('collection_errors')}** | collect exit {t.get('collect_exit')}")
    if "junit" in t:
        j = t["junit"]
        a(f"- EXECUTED: **{j['tests']}** | passed **{j['passed']}** | failed **{j['failures']}** | errors **{j['errors']}** | skipped **{j['skipped']}** | {t.get('run_duration_s')}s")
    else:
        a("- Tests not executed in this run (use `--run-tests`)." if not data["flags"]["run_tests"] else f"- Run problem: {t.get('summary_line')}")
    if t.get("random_order"):
        a(f"- Random-order run: `{t['random_order']}`")
    if t.get("failed"):
        a("- Failing:\n```\n" + "\n".join(t["failed"]) + "\n```")
    if t.get("skip_reasons"):
        a("- Skipped (reasons):\n```\n" + "\n".join(t["skip_reasons"]) + "\n```")
    a("\n| Test directory | Tests |\n|---|---|")
    for k, v in t.get("by_directory", {}).items():
        a(f"| {k} | {v} |")
    if t.get("slowest_10"):
        a("\nSlowest tests:\n```\n" + "\n".join(t["slowest_10"]) + "\n```")
    c = data["coverage"]
    a(f"\n## 4. Coverage\n- {c if 'status' in c else 'Total: **' + str(c.get('total_percent')) + '%** over ' + ', '.join(c.get('targets', []))}")
    if c.get("low_coverage_files_first_25"):
        a("- Files under 50% (40+ statements):\n```\n" + "\n".join(c["low_coverage_files_first_25"]) + "\n```")
    a("\n## 5. Quality gates")
    for k, v in data["gates"].items():
        if k == "ruff_F_errors":
            if v: a("- **ruff F-class findings**:\n```\n" + "\n".join(v) + "\n```")
            continue
        a(f"- **{k}**: " + (v if isinstance(v, str) else f"exit {v.get('exit')} — " + " / ".join(v.get("tail", [])[-2:]) + (f" (TS errors {v['ts_errors']})" if "ts_errors" in v else "")))
    p = data["persistence"]
    a(f"\n## 6. Persistence and fail-closed startup")
    a(f"- `domain/**/repository.py` files: **{p['repository_py_files']}** | using SQL: **{p['repository_py_using_sql']}**")
    a(f"- Non-test files holding state in Python dicts: **{p['files_holding_state_in_dicts']}** | files using a DB session: **{p['files_using_db_session']}** | files with `class InMemory*`: **{p['inmemory_classes_files']}** | files with `class Sql*Repository`: **{p['sql_repository_classes_files']}**")
    a(f"- Migrations: **{len(p['migration_files'])}** | tables created: **{len(p['tables_created_in_migrations'])}** | RLS statements: **{p['rls_policies_in_migrations']}** | code that sets `app.current_tenant`: **{p['set_tenant_setting_in_code']}** file(s)")
    a("- Migration files:\n```\n" + "\n".join(p["migration_files"]) + "\n```")
    if p.get("repository_py_dict_only"):
        a("- repository.py files with NO SQL (in-memory):\n```\n" + "\n".join(p["repository_py_dict_only"][:60]) + "\n```")
    if p.get("startup_probes"):
        a("- Startup probe with no Vault/DB reachable (expect REFUSED):")
        for k, v in p["startup_probes"].items():
            a(f"  - `{k}`: `{v}`")
    if p.get("env_guard_examples"):
        a("- Environment guards found:\n```\n" + "\n".join(p["env_guard_examples"][:10]) + "\n```")
    se = data["security"]
    a("\n## 7. Security checks\n| Check | Files | Examples |\n|---|---|---|")
    for k in ["superuser_literal_in_app_code", "email_identity_comparison", "secret_like_defaults", "inmemory_secret_fallback",
              "break_glass_provision_route", "secret_returned_or_printed", "cors_wildcard", "debug_true", "verify_false",
              "sql_string_format", "sample_people_in_app_code", "email_literals_in_app_code"]:
        v = se[k]
        ex = "<br>".join(x.replace("|", "\\|") for x in v["examples"][:3])
        a(f"| {k} | {v['file_count']} | {ex} |")
    a(f"\n- `health_check()` returning constant True: {se['health_check_returns_constant_true'] or 'none'}")
    al = data["allowlist"]
    a("\n## 8. Hard-coding exception register")
    a(f"- File: `{al.get('file', 'not found')}` | entries: **{al.get('count', 'n/a')}** | missing reason/reviewer: **{al.get('missing_reason_or_reviewer', 'n/a')}**")
    if al.get("by_area"):
        a(f"- By area: `{al['by_area']}`")
    if al.get("sensitive_entries_first_30"):
        a("- Entries touching sensitive areas:\n```\n" + "\n".join(al["sensitive_entries_first_30"]) + "\n```")
    a(f"- Comparisons against Decimal literals: **{al['comparisons_against_decimal_literals']['file_count']}** file(s)\n```\n" + "\n".join(al["comparisons_against_decimal_literals"]["examples"][:8]) + "\n```")
    ev = data["evidence"]
    a("\n## 9. Evidence integrity (fat/, README, docs)")
    a("- fat/ files:\n```\n" + ("\n".join(ev["fat_files"]) if isinstance(ev["fat_files"], list) else ev["fat_files"]) + "\n```")
    for im in ev["images"]:
        a(f"- Image `{im['file']}` ({im['bytes']} B) markers: `{im['embedded_markers'] or 'none'}` | git: `{im['git_log']}`")
    a("- Tool claims vs tools installed here:\n\n| Tool | Mentioned in fat/docs/README | Installed |\n|---|---|---|")
    for k, v in ev["tool_claims"].items():
        a(f"| {k} | {v['mentioned_in_evidence_files']} file(s) | {v['installed_on_this_machine']} |")
    m = ev["metric_values_hardcoded_in_scripts"]
    a(f"- Metric values hard-coded in scripts: **{m['file_count']}** file(s)\n```\n" + "\n".join(m["examples"][:15]) + "\n```")
    if ev.get("acceptance_status_counts"):
        a(f"- fat/ACCEPTANCE.md status words: `{ev['acceptance_status_counts']}`")
        for k, v in ev["acceptance_key_rows"].items():
            a(f"  - {k}: `{v}`")
    a("- Numeric claims in fat/README/cost register (sample):\n```\n" + "\n".join(ev["numeric_claims_sample"][:25]) + "\n```")
    dp = data["deploy"]
    a("\n## 10. Deployment and runtime")
    a(f"- Helm charts: `{dp['helm_charts'] or 'none'}`")
    for ch, tp in dp["helm_templates"].items():
        a(f"  - {ch} templates ({len(tp)}): {', '.join(tp[:40])}")
    a(f"- helm lint: `{dp.get('helm_lint', 'n/a')}`")
    a(f"- Possible secrets in values files: {len(dp['possible_secrets_in_values'])}")
    a(f"- Dockerfiles: {dp['dockerfiles']} | without non-root USER: {dp['dockerfiles_without_non_root_user'] or 'none'}")
    a(f"- Compose services: {', '.join(dp['compose_services']) or 'none'}")
    a(f"- Celery tasks registered ({len(dp['celery_tasks'])}): {', '.join(dp['celery_tasks'])}")
    a("- Beat schedule evidence:\n```\n" + ("\n".join(dp["beat_schedule_examples"][:8]) or "none") + "\n```")
    a("- Tools on this machine:\n\n| Tool | Version |\n|---|---|")
    for k, v in dp["tools_on_machine"].items():
        a(f"| {k} | {v} |")
    aw = data["api_web"]
    a(f"\n## 11. API and Web\n- API routes: **{aw['route_count']}** | routes with no visible auth dependency: **{aw['routes_without_visible_auth_dependency_count']}**")
    a("- Routes by prefix:\n```\n" + "\n".join(f"{v:>4} {k}" for k, v in aw["routes_by_prefix"].items()) + "\n```")
    if aw["routes_without_visible_auth_dependency_first_40"]:
        a("- No visible auth dependency (verify middleware):\n```\n" + "\n".join(aw["routes_without_visible_auth_dependency_first_40"]) + "\n```")
    a(f"- Web pages ({len(aw['web_pages']) if isinstance(aw['web_pages'], list) else 0}): {', '.join(aw['web_pages']) if isinstance(aw['web_pages'], list) else aw['web_pages']}")
    a(f"- Web route definitions found: **{aw['web_route_count']}** | Playwright specs: {len(aw['playwright_specs'])}")
    a("- Screen presence:\n\n| Screen | Page file |\n|---|---|")
    for k, v in aw["screen_presence"].items():
        a(f"| {k} | {'yes' if v else '**NO**'} |")
    dc = data["docs"]
    a("\n## 12. Docs and traceability")
    a(f"- Docs: {len(dc['files']) if isinstance(dc['files'], list) else dc['files']} files | duplicates: {dc['duplicate_doc_names'] or 'none'}")
    for k in ["rtm_distinct_ids", "rtm_ids_by_prefix", "rtm_status_words", "rtm_rows_with_test_reference", "register_ac_count"]:
        if k in dc: a(f"- {k}: `{dc[k]}`")
    if dc.get("readme_claims"):
        a("- README statements containing figures/claims (each needs a source):\n```\n" + "\n".join(dc["readme_claims"]) + "\n```")
    a("\n## 13. Specification pattern checks\n| Check | Files | Distinct | Expect | Notes |\n|---|---|---|---|---|")
    for k, v in data["spec"].items():
        note = ("missing: " + (", ".join(v["missing"]) or "none")) if "missing" in v else ", ".join(v["tokens"][:8])
        a(f"| {k} | {v['files']} | {v['distinct']} | {v['expect'] if v['expect'] is not None else '-'} | {note[:140]} |")
    a("\n---\nEnd of report. Paste this whole file back for review. Attach `audit_output/audit_full.json` if asked.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="CloudLens evidence audit v2")
    ap.add_argument("--run-tests", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--probe-startup", action="store_true")
    ap.add_argument("--timeout", type=int, default=2400)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
    py = python_exe()
    print(f"[audit v{VERSION}] repo={ROOT} python={py}", flush=True)
    data = {"version": VERSION, "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "python": py, "flags": {"run_tests": a.run_tests, "coverage": a.coverage, "probe_startup": a.probe_startup}}
    steps = [("git", sec_git), ("size", sec_size), ("tests", lambda: sec_tests(py, a.run_tests, a.timeout)),
             ("coverage", lambda: sec_coverage(py, a.coverage, a.timeout)), ("gates", lambda: sec_gates(py)),
             ("persistence", lambda: sec_persistence(py, a.probe_startup)), ("security", sec_security),
             ("allowlist", sec_allowlist), ("evidence", sec_evidence), ("deploy", sec_deploy),
             ("api_web", sec_api_web), ("docs", sec_docs), ("spec", sec_spec)]
    for key, fn in steps:
        print(f"[audit] {key} ...", flush=True)
        try:
            data[key] = fn()
        except Exception as e:
            import traceback
            data[key] = {"collector_error": repr(e), "trace": traceback.format_exc()[-1500:]}
            finding("AMBER", "Audit", f"collector '{key}' errored: {e!r}")
    data["findings"] = FINDINGS
    (OUT / "audit_full.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    try:
        rep = md(data)
    except Exception as e:
        import traceback
        rep = f"# CloudLens Audit Report v{VERSION}\n\nRendering failed: {e!r}\n```\n{traceback.format_exc()}\n```\nSee audit_full.json."
    (OUT / "AUDIT_REPORT.md").write_text(rep, encoding="utf-8")
    r = sum(1 for f in FINDINGS if f["severity"] == "RED"); am = sum(1 for f in FINDINGS if f["severity"] == "AMBER")
    print(f"[audit] done -> {OUT / 'AUDIT_REPORT.md'} ({len(rep)} chars) | RED {r} | AMBER {am}", flush=True)


if __name__ == "__main__":
    main()
