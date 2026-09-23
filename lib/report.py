#!/usr/bin/env python3
"""Build summary.md + summary.json from the SARIF files and apply the gate.

usage: report.py <report_dir> <fail_on: secrets|none>
exit:  0 pass, 1 gate failed, 2 gate could not be evaluated
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys

SEV = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
TOOL_ORDER = ["gitleaks", "semgrep", "osv-scanner", "checkov", "zizmor", "actionlint"]


def bucket(result, rules):
    """Same mapping as the corporate.sec dashboard: CVSS-style score first,
    then SARIF level."""
    rule = rules.get(result.get("ruleId"), {})
    sev = (result.get("properties") or {}).get("security-severity") or \
        (rule.get("properties") or {}).get("security-severity")
    try:
        n = float(sev)
        return "CRITICAL" if n >= 9 else "HIGH" if n >= 7 else "MEDIUM" if n >= 4 \
            else "LOW" if n > 0 else "INFO"
    except (TypeError, ValueError):
        pass
    level = result.get("level") or (rule.get("defaultConfiguration") or {}).get("level") or "warning"
    return {"error": "HIGH", "warning": "MEDIUM", "note": "INFO"}.get(level, "INFO")


def suppressed(result):
    """SARIF in-source suppression (checkov:skip, nosemgrep, ...)."""
    return any(s.get("status", "accepted") != "rejected" for s in (result.get("suppressions") or []))


def read_sarif(path):
    counts = {s: 0 for s in SEV}
    top, n_suppressed = [], 0
    doc = json.loads(path.read_text() or "{}")
    for run in doc.get("runs", []):
        rules = {r.get("id"): r for r in (run.get("tool", {}).get("driver", {}).get("rules") or [])}
        for r in run.get("results") or []:
            if suppressed(r):
                n_suppressed += 1
                continue
            b = bucket(r, rules)
            counts[b] += 1
            loc = ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
            top.append({
                "severity": b,
                "rule": r.get("ruleId", "?"),
                "file": (loc.get("artifactLocation") or {}).get("uri", "?"),
                "line": (loc.get("region") or {}).get("startLine"),
                "message": " ".join(((r.get("message") or {}).get("text") or "").split())[:200],
            })
    top.sort(key=lambda f: SEV.index(f["severity"]))
    return counts, top, n_suppressed


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def main():
    out = pathlib.Path(sys.argv[1])
    fail_on = sys.argv[2] if len(sys.argv) > 2 else "secrets"
    status = {}
    for line in (out / ".status").read_text().splitlines():
        tool, st, note = (line.split("\t") + ["", ""])[:3]
        status[tool] = {"status": st, "note": note}

    tools, findings = {}, []
    for tool in TOOL_ORDER:
        st = status.get(tool, {"status": "skipped", "note": ""})
        entry = {**st, "counts": {s: 0 for s in SEV}, "total": 0, "suppressed": 0}
        sarif = out / f"{tool}.sarif"
        if st["status"] in ("ok", "findings") and sarif.is_file() and sarif.stat().st_size:
            try:
                counts, top, n_sup = read_sarif(sarif)
                entry["counts"], entry["total"], entry["suppressed"] = counts, sum(counts.values()), n_sup
                findings += [{"tool": tool, **f} for f in top]
            except ValueError:
                entry["status"], entry["note"] = "error", "invalid SARIF"
        if tool == "actionlint" and st["status"] == "findings":
            n = len([l for l in (out / "actionlint.txt").read_text().splitlines() if l.strip()])
            entry["counts"]["MEDIUM"], entry["total"] = n, n
        tools[tool] = entry

    # Worst first across ALL scanners, so a CRITICAL from a later scanner is
    # never pushed out of the top-25 list by an earlier scanner's findings.
    findings.sort(key=lambda f: SEV.index(f["severity"]))
    totals = {s: sum(t["counts"][s] for t in tools.values()) for s in SEV}
    secrets = tools["gitleaks"]
    if fail_on == "none":
        gate, code = "pass (gate disabled)", 0
    elif secrets["status"] in ("error", "skipped"):
        gate, code = "error: the secret scan did not run", 2
    elif secrets["total"] > 0:
        gate, code = f"FAIL: {secrets['total']} secret finding(s)", 1
    else:
        gate, code = "pass", 0

    summary = {
        "schema": 1,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "leaa_version": os.environ.get("LEAA_VERSION", "dev"),
        "platform": os.environ.get("LEAA_PLATFORM", "local"),
        "repository": git("config", "--get", "remote.origin.url"),
        "commit": git("rev-parse", "HEAD"),
        "base": os.environ.get("LEAA_BASE_RESOLVED") or None,
        "gate": {"policy": fail_on, "result": gate, "exit_code": code},
        "totals": totals,
        "tools": tools,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    icon = {"ok": "✅", "findings": "⚠️", "error": "❌", "skipped": "⚪"}
    md = ["## Security Scan", "",
          f"**Gate ({fail_on}): {gate}**. Only secrets fail the build. All other findings are advisory.", "",
          "| Scanner | Status | CRITICAL | HIGH | MEDIUM | LOW | INFO | Suppressed | Note |",
          "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for tool, t in tools.items():
        c = t["counts"]
        md.append(f"| `{tool}` | {icon.get(t['status'], '?')} {t['status']} | {c['CRITICAL']} | {c['HIGH']} | "
                  f"{c['MEDIUM']} | {c['LOW']} | {c['INFO']} | {t['suppressed']} | {t['note']} |")
    md.append(f"| **total** | | {totals['CRITICAL']} | {totals['HIGH']} | {totals['MEDIUM']} | "
              f"{totals['LOW']} | {totals['INFO']} | {sum(t['suppressed'] for t in tools.values())} | |")
    if findings:
        md += ["", "<details><summary>Top 25 findings</summary>", "",
               "| Severity | Scanner | Rule | Location | Message |", "|---|---|---|---|---|"]
        for f in findings[:25]:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            msg = f["message"].replace("|", "/")
            md.append(f"| {f['severity']} | {f['tool']} | `{f['rule']}` | `{loc}` | {msg} |")
        md += ["", "</details>"]
    md += ["", f"`leaa-scan {summary['leaa_version']}` on {summary['platform']}. "
           "Full results: the SARIF files in the report directory."]
    (out / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"[leaa-scan] gate: {gate}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
