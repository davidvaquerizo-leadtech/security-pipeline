#!/usr/bin/env python3
"""Fold the results of one osv-scanner SARIF file into another.

usage: merge_sarif.py <target.sarif> <extra.sarif>

leaa-scan runs osv-scanner twice (the recursive walk, then -L for the Xcode
SPM lock files, LEAA-2694). This keeps one osv-scanner.sarif with one run:
results are appended and rules are merged by id. The target is rewritten
in place; if it is missing or empty, the extra file becomes the target.
"""
import json
import pathlib
import sys


def load(path):
    p = pathlib.Path(path)
    if not p.is_file() or not p.stat().st_size:
        return None
    return json.loads(p.read_text())


def main():
    target, extra = sys.argv[1], sys.argv[2]
    base, add = load(target), load(extra)
    if add is None:
        return 0
    if base is None or not base.get("runs"):
        pathlib.Path(target).write_text(json.dumps(add, indent=2) + "\n")
        return 0
    run = base["runs"][0]
    driver = run.setdefault("tool", {}).setdefault("driver", {})
    rules = driver.setdefault("rules", [])
    have = {r.get("id") for r in rules}
    results = run.setdefault("results", [])
    for other in add.get("runs", []):
        for r in (other.get("tool", {}).get("driver", {}).get("rules") or []):
            if r.get("id") not in have:
                rules.append(r)
                have.add(r.get("id"))
        results.extend(other.get("results") or [])
    # ruleIndex values point into the old rule arrays; drop them, ruleId stays.
    for r in results:
        r.pop("ruleIndex", None)
    pathlib.Path(target).write_text(json.dumps(base, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
