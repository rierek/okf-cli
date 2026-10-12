#!/usr/bin/env python3
"""Run the okf skill evals (skills/okf/evals/evals.json) with headless omp agents.

One command:   python3 scripts/skill-eval.py --models haiku=claude-haiku-4-5,big=claude-sonnet-5-5
Fixture check: python3 scripts/skill-eval.py --materialise-only
Everything runs in a fresh tmpdir per scenario x model with a fake HOME: nothing
touches ~/Obsidian/Knowledge-Catalogue or real agent configs (only the omp auth DB
is copied into the fake HOME). Stdlib only.

Scenario schema (evals.json):
  id, name, workflow, base?        base = key of top-level "bases" (shared file sets)
  files [{path, content}]          written under <work>/
  setup [shell]                    run in <work> with okf-cli on PATH, git identity set
  prompt                           {CLI_PY} = absolute path of cli/okf-cli.py
  no_path_cli                      true: okf-cli is NOT on PATH (fallback invocation test)
  routing {must_read, also_read, must_not_read}  reference files under skills/okf/references/; must_read and
                                   must_not_read decide routing pass/fail, also_read (the table's "Also read") is only reported
  checks [{type, desc, ...}]       programmatic outcome checks, see CHECKS below
  expected_output, assertions      prose, documentation only
"""
import argparse, concurrent.futures as cf, datetime, fnmatch, glob, hashlib, json, os
import re, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "okf"
EVALS = SKILL / "evals" / "evals.json"
RESULTS = SKILL / "evals" / "RESULTS.md"
CLI_PY = REPO / "cli" / "okf-cli.py"
SKILL_DIR = SKILL  # --skill-dir overrides (baseline runs against an exported older skill)
AUTH_DB = Path.home() / ".omp" / "agent" / "agent.db"
TOOLS = "read,bash,edit,write,grep,glob"
SYSTEM_NOTE = ("Non-interactive run: nobody can answer questions. Where you would ask the user, "
               "state your assumption in your final reply and continue. Work only inside the "
               "current directory unless a path is given.")
REF_NAMES = r"\b(context-bundles|create-bundle|integrate-project-knowledge|maintain-catalogue|migrate-bundle-to-v0\.2|write-concepts)\.md"
BEGIN, END = "<!-- results:begin -->", "<!-- results:end -->"


# ---------------------------------------------------------------- materialise
def sh(cmd, cwd, env, timeout=120):
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


def materialise(sc, bases, root, with_cli=True):
    """Create <root>/{work,home,bin}; return (work, env, head_map)."""
    work, home, bindir = root / "work", root / "home", root / "bin"
    for d in (work, home / ".omp" / "agent", bindir):
        d.mkdir(parents=True, exist_ok=True)
    (home / ".gitconfig").write_text(
        "[user]\n name = Eval\n email = eval@example.invalid\n[commit]\n gpgsign = false\n"
        "[init]\n defaultBranch = main\n")
    if AUTH_DB.exists():
        shutil.copy(AUTH_DB, home / ".omp" / "agent" / "agent.db")
    wrapper = bindir / "okf-cli"
    wrapper.write_text(f'#!/bin/sh\nexec python3 "{CLI_PY}" "$@"\n')
    wrapper.chmod(0o755)
    env = dict(os.environ, HOME=str(home), GIT_TERMINAL_PROMPT="0",
               PATH=(f"{bindir}:" if with_cli and not sc.get("no_path_cli") else "") + env_path_without_okf())
    env.pop("OKF_ROOT", None)
    files = list(bases.get(sc.get("base"), [])) if sc.get("base") else []
    over = {f["path"]: f for f in sc.get("files", [])}
    files = [f for f in files if f["path"] not in over] + list(over.values())
    for f in files:
        p = work / f["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f["content"].replace("{WORK}", str(work.resolve())))
    # the skill without evals/ (no answer key in reach)
    skill_dst = work / ".omp" / "skills" / "okf"
    shutil.copytree(SKILL_DIR, skill_dst, ignore=shutil.ignore_patterns("evals"))
    for cmd in sc.get("setup", []):
        r = sh(cmd.replace("{WORK}", str(work.resolve())).replace("{CLI_PY}", str(CLI_PY)), work, env)
        if r.returncode != 0:
            raise RuntimeError(f"setup failed: {cmd!r}\n{r.stdout}{r.stderr}")
    heads = {}
    for g in work.glob("*/.git"):
        r = sh(f"git -C '{g.parent}' rev-parse HEAD", work, env)
        heads[g.parent.name] = r.stdout.strip()
    return work, env, heads


def env_path_without_okf():
    """PATH minus any dir that carries a real okf-cli, so only the tmp wrapper counts."""
    out = []
    for d in os.environ.get("PATH", "").split(":"):
        if d and not (Path(d) / "okf-cli").exists():
            out.append(d)
    return ":".join(out)


def snapshot(work):
    snap = {}
    for p in sorted(work.rglob("*")):
        rel = p.relative_to(work).as_posix()
        if rel.startswith(".omp") or "/.git/" in "/" + rel + "/" or "/.fts" in "/" + rel or ".tagvec" in rel:
            continue
        if p.is_file() and not p.is_symlink():
            snap[rel] = hashlib.sha1(p.read_bytes()).hexdigest()
    return snap


# ---------------------------------------------------------------- transcript
def parse_transcript(path):
    cmds, reads, answer, cost, ncalls = [], [], "", 0.0, 0
    calls = []
    for line in Path(path).read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "tool_execution_start":
            ncalls += 1
            a, name = ev.get("args") or {}, ev.get("toolName")
            calls.append((name, a))
            if name == "bash":
                cmds.append(a.get("command", ""))
            else:
                p = a.get("path") or a.get("file_path") or ""
                reads.append((name, str(p)))
        elif t == "message_end" and ev["message"].get("role") == "assistant":
            txt = "".join(c.get("text", "") for c in ev["message"].get("content", []) if c.get("type") == "text")
            if txt.strip():
                answer = txt
            cost += (ev["message"].get("usage", {}).get("cost", {}) or {}).get("total", 0) or 0
    cmds = cmds + [f"READ {p}" for _, p in reads]
    refs = set()
    for c in cmds:  # read-tool paths are in cmds as "READ <path>"; bare names catch `cd references && cat x.md`
        refs.update(m + ".md" for m in re.findall(REF_NAMES, c))
    skill_read = any(re.search(r"SKILL\.md|skill://okf", p) for _, p in reads) or any("SKILL.md" in c for c in cmds)
    return dict(cmds=cmds, refs=refs, answer=answer, cost=cost, ncalls=ncalls, skill_read=skill_read, calls=calls)


# ---------------------------------------------------------------- checks
def fm(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def run_check(ck, ctx):
    """Return None when the check passes, else a failure message."""
    work, env, tr, t = ctx["work"], ctx["env"], ctx["tr"], ck["type"]
    rx = lambda s: re.compile(s, re.M | re.S if ck.get("dotall") else re.M)
    if t in ("file_exists", "file_absent"):
        ok = (work / ck["path"]).exists() or (work / ck["path"]).is_symlink()
        return None if ok == (t == "file_exists") else f"{t} {ck['path']}"
    if t in ("file_contains", "file_not_contains", "fm_contains", "fm_not_contains"):
        p = work / ck["path"]
        if not p.is_file():
            return f"{t}: {ck['path']} missing"
        txt = p.read_text(errors="replace")
        if t.startswith("fm_"):
            txt = fm(txt)
        found = bool(rx(ck["regex"]).search(txt))
        return None if found == (not t.endswith("not_contains")) else f"{t} {ck['path']} /{ck['regex']}/"
    if t == "files_not_contains":
        bad = [f for f in glob.glob(str(work / ck["glob"]), recursive=True)
               if Path(f).is_file() and rx(ck["regex"]).search(Path(f).read_text(errors="replace"))]
        return None if not bad else f"files_not_contains /{ck['regex']}/ in {[Path(b).relative_to(work).as_posix() for b in bad]}"
    if t == "files_contains":
        fs = [f for f in glob.glob(str(work / ck["glob"]), recursive=True) if Path(f).is_file()]
        hit = [f for f in fs if rx(ck["regex"]).search(Path(f).read_text(errors="replace"))]
        return None if len(hit) >= ck.get("min", 1) else f"files_contains /{ck['regex']}/ in {ck['glob']}: {len(hit)} hit(s)"
    if t == "glob_count":
        n = len([f for f in glob.glob(str(work / ck["glob"]), recursive=True)])
        return None if ck.get("min", 0) <= n <= ck.get("max", 10**9) else f"glob_count {ck['glob']} = {n}"
    if t == "cmd":
        r = sh(ck["run"], work, env)
        if "exit" in ck and ck["exit"] != "any":
            if (r.returncode == 0) != (ck["exit"] == 0):
                return f"cmd {ck['run']!r} exit {r.returncode}: {(r.stdout + r.stderr)[-200:]!r}"
        if "stdout_regex" in ck and not rx(ck["stdout_regex"]).search(r.stdout):
            return f"cmd {ck['run']!r} stdout lacks /{ck['stdout_regex']}/: {r.stdout[-200:]!r}"
        if "stdout_not_regex" in ck and rx(ck["stdout_not_regex"]).search(r.stdout):
            return f"cmd {ck['run']!r} stdout has /{ck['stdout_not_regex']}/"
        if "stderr_not_regex" in ck and rx(ck["stderr_not_regex"]).search(r.stderr):
            return f"cmd {ck['run']!r} stderr has /{ck['stderr_not_regex']}/"
        return None
    if t == "transcript_cmd":
        n = len(re.findall(ck["regex"], "\n".join(tr["cmds"]), re.M))
        want = ck.get("present", True)
        return None if (n > 0) == want else f"transcript_cmd /{ck['regex']}/ {'absent' if want else 'present'} ({n} hit)"
    if t == "cmd_order":
        cmds = tr["cmds"]
        idx = lambda r: next((i for i, c in enumerate(cmds) if re.search(r, c)), None)
        a, b = idx(ck["first"]), idx(ck["then"])
        if b is None:
            return None if ck.get("optional_then") else f"cmd_order: /{ck['then']}/ never ran"
        return None if a is not None and a < b else f"cmd_order: /{ck['first']}/ not before /{ck['then']}/"
    if t == "answer":
        found = bool(re.search(ck["regex"], tr["answer"], re.I | re.S))
        return None if found == ck.get("present", True) else f"answer {'lacks' if ck.get('present', True) else 'has'} /{ck['regex']}/"
    if t == "tree_unchanged":
        before, after = ctx["snap0"], snapshot(work)
        ign = ck.get("ignore", [])
        diff = [k for k in set(before) | set(after) if before.get(k) != after.get(k)
                and not any(fnmatch.fnmatch(k, g) for g in ign)]
        return None if not diff else f"tree changed: {sorted(diff)[:6]}"
    if t == "git_head_unchanged":
        d = ck.get("dir", "cat")
        now = sh(f"git -C '{d}' rev-parse HEAD", work, env).stdout.strip()
        return None if now == ctx["heads"].get(d) else f"git HEAD of {d} moved (commit made)"
    return f"unknown check type {t}"


def grade(sc, tr, ctx):
    ctx["tr"] = tr
    rt = sc.get("routing", {})
    miss = [r for r in rt.get("must_read", []) if r not in tr["refs"]]
    bad = [r for r in rt.get("must_not_read", []) if r in tr["refs"]]
    routing_ok = not miss and not bad
    also = [r for r in rt.get("also_read", []) if r not in tr["refs"]]
    fails = []
    if not tr["skill_read"]:
        fails.append("skill never loaded (SKILL.md not read)")
    for ck in sc.get("checks", []):
        try:
            f = run_check(ck, ctx)
        except Exception as e:  # a broken check must show up, not pass
            f = f"check error {e!r}"
        if f:
            fails.append((ck.get("desc") or "") + " | " + f if ck.get("desc") else f)
    return dict(routing_ok=routing_ok, routing_missing=miss, routing_forbidden=bad, routing_also_missing=also,
                outcome_ok=not fails, fails=fails, refs=sorted(tr["refs"]), cost=tr["cost"], calls=tr["ncalls"])


# ---------------------------------------------------------------- run
def run_one(sc, bases, model, thinking, outdir, keep, timeout):
    label = f"{sc['id']}__{model['name']}"
    root = Path(tempfile.mkdtemp(prefix=f"okfeval-{label}-"))
    rec = dict(id=sc["id"], model=model["name"], model_id=model["id"])
    try:
        work, env, heads = materialise(sc, bases, root)
        snap0 = snapshot(work)
        prompt = sc["prompt"].replace("{CLI_PY}", str(CLI_PY))
        tpath = outdir / f"{label}.jsonl"
        cmd = ["omp", "-p", "--no-session", "--cwd", str(work), "--model", model["id"], "--thinking", thinking,
               "--tools", TOOLS, "--no-rules", "--no-extensions", "--skills", "okf",
               "--append-system-prompt", SYSTEM_NOTE, "--mode", "json", prompt]
        t0 = time.time()
        try:
            with open(tpath, "w") as out:
                subprocess.run(cmd, cwd=work, env=env, stdout=out, stderr=subprocess.PIPE, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
        rec["secs"] = round(time.time() - t0)
        tr = parse_transcript(tpath)
        g = grade(sc, tr, dict(work=work, env=env, snap0=snap0, heads=heads))
        if timed_out:
            g["outcome_ok"] = False
            g["fails"].append("timeout")
        if tr["ncalls"] == 0:
            g["outcome_ok"] = False
            g["fails"].append("agent made no tool call (model unavailable or auth failure?)")
        rec.update(g)
        rec["skill_loaded"] = tr["skill_read"]
        (outdir / f"{label}.answer.txt").write_text(tr["answer"])
        if keep:
            shutil.copytree(work, outdir / f"{label}.work", symlinks=True, ignore=shutil.ignore_patterns(".omp"))
    except Exception as e:
        rec.update(routing_ok=False, outcome_ok=False, fails=[f"runner error: {e}"], refs=[], cost=0, calls=0)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return rec


def mark(b):
    return "pass" if b else "FAIL"


def write_results(recs, models, thinking, only, path):
    scs = {s["id"]: s for s in json.loads(EVALS.read_text())["evals"]}
    names = [m["name"] for m in models]
    lines = [f"Run {datetime.date.today()} · thinking `{thinking}` · "
             + ", ".join(f"{m['name']} = `{m['id']}`" for m in models)
             + f" · {len(only)} scenarios · routing = required references opened (R), outcome = programmatic checks (O)", "",
             "| scenario | workflow | " + " | ".join(f"{n} R / O" for n in names) + " | notes |",
             "|---|---|" + "---|" * (len(names) + 1)]
    tot = {n: [0, 0, 0, 0] for n in names}
    for sid in only:
        row, notes = [], []
        for n in names:
            r = next((x for x in recs if x["id"] == sid and x["model"] == n), None)
            if not r:
                row.append("-"); continue
            row.append(f"{mark(r['routing_ok'])} / {mark(r['outcome_ok'])}")
            tot[n][0] += 1; tot[n][1] += r["routing_ok"]; tot[n][2] += r["outcome_ok"]; tot[n][3] += r.get("skill_loaded", False)
            if not r["outcome_ok"] or not r["routing_ok"]:
                msg = "; ".join(r["fails"][:3])
                if r["routing_missing"]:
                    msg += f"; missing refs {r['routing_missing']}"
                if r.get("routing_also_missing"):
                    msg += f"; also-read missed {r['routing_also_missing']}"
                if r["routing_forbidden"]:
                    msg += f"; forbidden refs {r['routing_forbidden']}"
                notes.append(f"{n}: {msg[:300]}".replace("|", "\\|").replace("\n", " "))
        lines.append(f"| {sid} | {scs[sid].get('workflow', '')} | " + " | ".join(row) + " | " + "<br>".join(notes) + " |")
    lines += ["", "| model | scenarios | SKILL.md opened | routing pass | outcome pass |", "|---|---|---|---|---|"]
    for n in names:
        c = tot[n]
        lines.append(f"| {n} | {c[0]} | {c[3]}/{c[0]} | {c[1]}/{c[0]} | {c[2]}/{c[0]} |")
    block = f"{BEGIN}\n" + "\n".join(lines) + f"\n{END}"
    old = path.read_text() if path.exists() else "# okf skill eval results\n\nReproduce: `just skill-eval`.\n\n"
    if BEGIN in old:
        new = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), lambda _: block, old, flags=re.S)
    else:
        new = old.rstrip() + "\n\n## Latest run\n\n" + block + "\n"
    path.write_text(new)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="small=claude-haiku-4-5,large=claude-sonnet-5-5", help="name=id,name=id")
    ap.add_argument("--thinking", default="low")
    ap.add_argument("--only", default="", help="comma list of scenario ids (prefix match)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", default="", help="dir for transcripts (default: tmp)")
    ap.add_argument("--keep", action="store_true", help="keep final work trees next to transcripts")
    ap.add_argument("--results", default=str(RESULTS), help="results file ('' = do not write)")
    ap.add_argument("--skill-dir", default="", help="skill directory to expose to the agent (default: skills/okf); e.g. an exported older revision for before/after runs")
    ap.add_argument("--rescore", default="", help="DIR of an earlier run: re-grade routing from its transcripts (outcome checks need the work tree and are kept), write DIR/records.json")
    ap.add_argument("--merge", default="", help="records.json of an earlier run: keep its records, replace those re-run now (targeted re-runs)")
    ap.add_argument("--materialise-only", action="store_true", help="build every fixture and run its setup; no agent")
    a = ap.parse_args()
    global SKILL_DIR
    if a.skill_dir:
        SKILL_DIR = Path(a.skill_dir).resolve()
    data = json.loads(EVALS.read_text())
    bases = data.get("bases", {})
    scs = data["evals"]
    if a.only:
        pre = a.only.split(",")
        scs = [s for s in scs if any(s["id"].startswith(p) for p in pre)]
    if a.rescore:
        d = Path(a.rescore)
        recs = json.loads((d / "records.json").read_text())
        by = {s["id"]: s for s in data["evals"]}
        for r in recs:
            tr = parse_transcript(d / f"{r['id']}__{r['model']}.jsonl")
            rt = by[r["id"]].get("routing", {})
            r["refs"] = sorted(tr["refs"])
            r["routing_missing"] = [x for x in rt.get("must_read", []) if x not in tr["refs"]]
            r["routing_forbidden"] = [x for x in rt.get("must_not_read", []) if x in tr["refs"]]
            r["routing_also_missing"] = [x for x in rt.get("also_read", []) if x not in tr["refs"]]
            r["routing_ok"] = not r["routing_missing"] and not r["routing_forbidden"]
            r["skill_loaded"] = tr["skill_read"]
        (d / "records.json").write_text(json.dumps(recs, indent=1, default=list))
        print("rescored", len(recs), "records in", d)
        sys.exit(0)
    if a.materialise_only:
        bad = 0
        for s in scs:
            root = Path(tempfile.mkdtemp(prefix="okfeval-mat-"))
            try:
                materialise(s, bases, root)
                print("ok  ", s["id"])
            except Exception as e:
                bad += 1
                print("FAIL", s["id"], str(e)[:300])
            shutil.rmtree(root, ignore_errors=True)
        sys.exit(1 if bad else 0)
    models = [dict(name=n, id=i) for n, i in (x.split("=", 1) for x in a.models.split(","))]
    outdir = Path(a.out or tempfile.mkdtemp(prefix="okfeval-run-"))
    outdir.mkdir(parents=True, exist_ok=True)
    print("transcripts:", outdir, flush=True)
    recs, lock = [], threading.Lock()

    def job(s, m):
        r = run_one(s, bases, m, a.thinking, outdir, a.keep, a.timeout)
        with lock:
            recs.append(r)
            print(f"{r['id']:34} {m['name']:6} R:{mark(r['routing_ok'])} O:{mark(r['outcome_ok'])} "
                  f"{r.get('secs', 0)}s ${r.get('cost', 0):.3f} {'; '.join(r['fails'][:2])[:160]}", flush=True)
            (outdir / "records.json").write_text(json.dumps(recs, indent=1, default=list))

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda sm: job(*sm), [(s, m) for s in scs for m in models]))
    if a.results:
        allrecs, ids = recs, [s["id"] for s in scs]
        if a.merge:
            fresh = {(r["id"], r["model"]) for r in recs}
            allrecs = [r for r in json.loads(Path(a.merge).read_text()) if (r["id"], r["model"]) not in fresh] + recs
            ids = [s["id"] for s in data["evals"]]
        write_results(allrecs, models, a.thinking, ids, Path(a.results))
        print("results ->", a.results)
    ok = all(r["outcome_ok"] and r["routing_ok"] for r in recs)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
