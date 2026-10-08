#!/usr/bin/env bash
# Gate tests. Builds throwaway git repos at run time (no secret-like
# string is committed to this repo) and checks the exit codes.
#   clean repo            -> 0
#   secret in the tree    -> 1   (dir mode)
#   secret after base     -> 1   (range mode, like a pull request)
#   secret before base    -> 0   (range mode ignores old history)
#   LEAA_FAIL_ON=none     -> 0
#   Xcode SPM lock file   -> packages scanned once, even when .gitignore
#                            hides it from the osv-scanner walk (LEAA-2694)
set -uo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fails=0
fake() { printf 'api_key = "%s"\n' "$(head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)"; }
commit() { git add -A && git -c user.email=t@example.invalid -c user.name=test commit -qm "$1"; }
expect() { # expect <name> <code> <cmd...>
  local name="$1" want="$2"; shift 2
  "$@" >/dev/null 2>"$work/$name.err"; local got=$?
  if [ "$got" = "$want" ]; then echo "PASS $name (exit $got)"
  else echo "FAIL $name: want $want got $got"; cat "$work/$name.err"; fails=$((fails+1)); fi
}

mkdir "$work/clean" && cd "$work/clean" && git init -q
printf 'requests>=2.0,<3\n' > requirements.txt; printf 'print("ok")\n' > app.py; commit init
expect clean 0 leaa-scan

mkdir "$work/leaky" && cd "$work/leaky" && git init -q
printf 'print("ok")\n' > app.py; fake > config.py; commit init
expect leaky-dir 1 leaa-scan
expect gate-none 0 env LEAA_FAIL_ON=none leaa-scan

mkdir "$work/pr" && cd "$work/pr" && git init -q
printf 'print("ok")\n' > app.py; commit base; base="$(git rev-parse HEAD)"
fake > new.py; commit leak
expect pr-new-secret 1 env LEAA_BASE_REF="$base" leaa-scan

mkdir "$work/old" && cd "$work/old" && git init -q
fake > old.py; commit old; git rm -q old.py; commit remove; base="$(git rev-parse HEAD)"
printf 'print("ok")\n' > app.py; commit change
expect pr-old-history 0 env LEAA_BASE_REF="$base" leaa-scan

# Xcode SPM lock file (LEAA-2694). The .gitignore follows rosseca/ereasy:
# it ignores App.xcodeproj/** and re-includes only Package.resolved. Git
# tracks the file, but osv-scanner's recursive walk skips it.
spm_lock() { cat <<'EOF'
{
  "pins" : [
    { "identity" : "alamofire", "kind" : "remoteSourceControl",
      "location" : "https://github.com/Alamofire/Alamofire.git",
      "state" : { "revision" : "f455c2975872ccd2d9c81594c658af65716e9b9a", "version" : "5.9.1" } },
    { "identity" : "swift-nio", "kind" : "remoteSourceControl",
      "location" : "https://github.com/apple/swift-nio.git",
      "state" : { "revision" : "0000000000000000000000000000000000000000", "version" : "2.29.0" } }
  ],
  "version" : 2
}
EOF
}
check() { # check <name> <python condition>; s = summary.json, n / unique = SPM results
  if python3 - "$2" <<'EOF'
import json, sys
s = json.load(open("security-reports/summary.json"))
sarif = json.load(open("security-reports/osv-scanner.sarif"))
spm = [(l["physicalLocation"]["artifactLocation"]["uri"], r["ruleId"])
       for run in sarif["runs"] for r in run.get("results") or [] for l in r.get("locations") or []
       if l["physicalLocation"]["artifactLocation"]["uri"].endswith("/swiftpm/Package.resolved")]
n, unique = len(spm), len(set(spm))
sys.exit(0 if eval("(" + sys.argv[1] + ")") else 1)
EOF
  then echo "PASS $1"; else echo "FAIL $1: $2"; cat security-reports/.osv*.log; fails=$((fails+1)); fi
}
spm_dir=App.xcodeproj/project.xcworkspace/xcshareddata/swiftpm
fast="semgrep checkov zizmor actionlint"

mkdir "$work/spm-ignored" && cd "$work/spm-ignored" && git init -q && mkdir -p "$spm_dir"
spm_lock > "$spm_dir/Package.resolved"; printf 'print("ok")\n' > app.py
printf '%s\n' 'App.xcodeproj/**' '!App.xcodeproj/project.xcworkspace' 'App.xcodeproj/project.xcworkspace/*' \
  '!App.xcodeproj/project.xcworkspace/xcshareddata' 'App.xcodeproj/project.xcworkspace/xcshareddata/*' \
  "!$spm_dir" "$spm_dir/*" "!$spm_dir/Package.resolved" > .gitignore
commit init
expect spm-ignored 0 env LEAA_SKIP="$fast" leaa-scan
check spm-ignored-counted 's["tools"]["osv-scanner"]["note"] == "spm=1" and n > 0 and n == unique
  and "Package.resolved file and found 2 packages" in open("security-reports/.osv-spm.log").read()'

mkdir "$work/spm-plain" && cd "$work/spm-plain" && git init -q && mkdir -p "$spm_dir"
spm_lock > "$spm_dir/Package.resolved"; commit init
expect spm-plain 0 env LEAA_SKIP="$fast" leaa-scan
check spm-plain-no-double-count 'n > 0 and n == unique and not any("swiftpm" in l for l in open("security-reports/.osv.log"))'

[ "$fails" = 0 ] && echo "all gate tests passed" || { echo "$fails test(s) failed"; exit 1; }
