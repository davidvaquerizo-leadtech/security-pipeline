#!/usr/bin/env python3
"""Read-only GitHub inventory for the security-pipeline rollout (LEAA-2446).

For each repo in the given orgs: activity, main language, CI system in use,
and whether it already calls the shared security scan. Uses only GET calls.
With a public token it sees public repos; with a read-only org token
(Metadata + Contents read) it sees private repos too.

usage: GITHUB_TOKEN=... github_inventory.py ORG [ORG...] > inventory.json
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MARKER = "security-pipeline"  # reusable workflow or image reference
CI_FILES = {
    "bitbucket-pipelines.yml": "bitbucket-pipelines",
    "codemagic.yaml": "codemagic",
    "codemagic.yml": "codemagic",
    ".gitlab-ci.yml": "gitlab-ci",
    "azure-pipelines.yml": "azure-pipelines",
    "Jenkinsfile": "jenkins",
    ".circleci": "circleci",
}


def get(path):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        **({"Authorization": f"token {TOKEN}"} if TOKEN else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # missing path / empty repo
            return None
        raise


def repos(org):
    page = 1
    while True:
        batch = get(f"/orgs/{org}/repos?type=all&per_page=100&page={page}") or []
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def inspect(r):
    full = r["full_name"]
    root = get(f"/repos/{full}/contents/") or []
    names = {x["name"] for x in root} if isinstance(root, list) else set()
    ci = sorted({v for k, v in CI_FILES.items() if k in names})
    workflows = []
    if ".github" in names:
        wf = get(f"/repos/{full}/contents/.github/workflows") or []
        workflows = [w["name"] for w in wf if isinstance(wf, list)]
        if workflows:
            ci.insert(0, "github-actions")
    covered = False
    for w in workflows:
        f = get(f"/repos/{full}/contents/.github/workflows/{w}")
        if f and f.get("download_url"):
            with urllib.request.urlopen(f["download_url"], timeout=30) as body:
                if MARKER in body.read().decode("utf-8", "replace"):
                    covered = True
                    break
    pushed = r.get("pushed_at") or ""
    age = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days if pushed else None
    return {
        "repo": full, "private": r["private"], "archived": r["archived"], "fork": r["fork"],
        "language": r.get("language"), "size_kb": r.get("size"), "pushed_at": pushed[:10],
        "days_since_push": age, "ci": ci or ["none"], "covered": covered,
        # "active product code" = not archived, not a fork, pushed in the last 180 days, non-empty
        "active": (not r["archived"] and not r["fork"] and age is not None and age <= 180
                   and (r.get("size") or 0) > 0),
    }


def main():
    out = {"generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "token": "set" if TOKEN else "none", "orgs": {}}
    for org in sys.argv[1:]:
        out["orgs"][org] = [inspect(r) for r in repos(org)]
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
