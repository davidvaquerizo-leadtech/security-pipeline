#!/usr/bin/env bash
# Gate tests. Builds throwaway git repos at run time (no secret-like
# string is committed to this repo) and checks the exit codes.
#   clean repo            -> 0
#   secret in the tree    -> 1   (dir mode)
#   secret after base     -> 1   (range mode, like a pull request)
#   secret before base    -> 0   (range mode ignores old history)
#   LEAA_FAIL_ON=none     -> 0
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

[ "$fails" = 0 ] && echo "all gate tests passed" || { echo "$fails test(s) failed"; exit 1; }
