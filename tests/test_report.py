#!/usr/bin/env python3
"""report.py unit test: the top-findings list is sorted across scanners."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

home = pathlib.Path(os.environ.get("LEAA_HOME", pathlib.Path(__file__).resolve().parent.parent))


def sarif(results, rules=()):
    return {"runs": [{"tool": {"driver": {"rules": list(rules)}}, "results": results}]}


def res(rule, level="warning", uri="f.py"):
    return {"ruleId": rule, "level": level, "message": {"text": rule},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": 1}}}]}


with tempfile.TemporaryDirectory() as d:
    out = pathlib.Path(d)
    (out / ".status").write_text("gitleaks\tok\t\nsemgrep\tok\t\nosv-scanner\tfindings\t\n")
    (out / "gitleaks.sarif").write_text(json.dumps(sarif([])))
    # 30 MEDIUM semgrep results come first in scanner order ...
    (out / "semgrep.sarif").write_text(json.dumps(sarif([res(f"sg-{i}") for i in range(30)])))
    # ... and one CRITICAL (CVSS 9.8) from a later scanner, plus one suppressed.
    crit = res("CVE-TEST-1", uri="pnpm-lock.yaml")
    sup = res("sg-suppressed")
    sup["suppressions"] = [{"kind": "inSource"}]
    (out / "osv-scanner.sarif").write_text(json.dumps(sarif(
        [crit, sup], [{"id": "CVE-TEST-1", "properties": {"security-severity": "9.8"}}])))
    rc = subprocess.run([sys.executable, str(home / "lib/report.py"), str(out), "secrets"],
                        capture_output=True, text=True).returncode
    summary = json.loads((out / "summary.json").read_text())
    md = (out / "summary.md").read_text()
    first = [l for l in md.splitlines() if l.startswith("| CRITICAL") or l.startswith("| MEDIUM")][0]
    checks = {
        "gate passes (no secrets)": rc == 0,
        "critical counted": summary["totals"]["CRITICAL"] == 1,
        "suppressed not counted": summary["tools"]["osv-scanner"]["suppressed"] == 1
        and summary["tools"]["osv-scanner"]["total"] == 1,
        "critical is first in the top list": first.startswith("| CRITICAL | osv-scanner | `CVE-TEST-1`"),
    }
    bad = [k for k, ok in checks.items() if not ok]
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    sys.exit(1 if bad else 0)
