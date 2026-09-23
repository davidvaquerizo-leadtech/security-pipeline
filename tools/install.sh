#!/usr/bin/env bash
# Install the pinned scanner set into a prefix (default /opt/leaa).
# Used by the Dockerfile. Also works natively on a Linux host without
# Docker (amd64 or arm64). Every download is sha256-checked.
#
#   tools/install.sh [prefix]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prefix="${1:-/opt/leaa}"
mkdir -p "$prefix"
prefix="$(cd "$prefix" && pwd)"
# shellcheck source=versions.env
. "$here/versions.env"

case "$(uname -m)" in
  x86_64|amd64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) echo "install.sh: unsupported CPU $(uname -m)" >&2; exit 1 ;;
esac

bin="$prefix/bin"
mkdir -p "$bin"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# fetch <url> <sha256> <dest>
fetch() {
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c - >/dev/null
  echo "verified $(basename "$1")"
}
pick() { local v="${1}_SHA256_${arch}"; echo "${!v}"; }

# gitleaks (asset names use x64 / arm64)
ga=$([ "$arch" = amd64 ] && echo x64 || echo arm64)
fetch "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${ga}.tar.gz" \
  "$(pick GITLEAKS)" "$tmp/gitleaks.tgz"
tar -xzf "$tmp/gitleaks.tgz" -C "$tmp" gitleaks
install -m 0755 "$tmp/gitleaks" "$bin/gitleaks"

# osv-scanner (single binary)
fetch "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_linux_${arch}" \
  "$(pick OSV_SCANNER)" "$tmp/osv-scanner"
install -m 0755 "$tmp/osv-scanner" "$bin/osv-scanner"

# zizmor + uv (Rust target triples)
triple=$([ "$arch" = amd64 ] && echo x86_64 || echo aarch64)-unknown-linux-gnu
fetch "https://github.com/zizmorcore/zizmor/releases/download/v${ZIZMOR_VERSION}/zizmor-${triple}.tar.gz" \
  "$(pick ZIZMOR)" "$tmp/zizmor.tgz"
tar -xzf "$tmp/zizmor.tgz" -C "$tmp"
install -m 0755 "$tmp/zizmor" "$bin/zizmor"

fetch "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${triple}.tar.gz" \
  "$(pick UV)" "$tmp/uv.tgz"
tar -xzf "$tmp/uv.tgz" -C "$tmp" --strip-components=1
install -m 0755 "$tmp/uv" "$bin/uv"

# actionlint
fetch "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_${arch}.tar.gz" \
  "$(pick ACTIONLINT)" "$tmp/actionlint.tgz"
tar -xzf "$tmp/actionlint.tgz" -C "$tmp" actionlint
install -m 0755 "$tmp/actionlint" "$bin/actionlint"

# semgrep + checkov: one venv each, hash-locked dependency trees.
export UV_CACHE_DIR="$tmp/uv-cache" UV_PYTHON_INSTALL_DIR="$prefix/python"
for tool in semgrep checkov; do
  venv="$prefix/venv/$tool"
  "$bin/uv" venv --quiet --python 3.12 "$venv"
  # sync = install exactly the locked tree, no re-resolve (needed for the
  # checkov asteval override in overrides-checkov.txt).
  "$bin/uv" pip sync --quiet --python "$venv/bin/python" --require-hashes \
    "$here/requirements-$tool.txt"
  # Wrapper, not a symlink: semgrep re-executes `pysemgrep` via PATH, so
  # the venv bin must come first or a stray host copy wins.
  printf '#!/bin/sh\nPATH="%s/bin:$PATH" exec "%s/bin/%s" "$@"\n' "$venv" "$venv" "$tool" > "$bin/$tool"
  chmod 0755 "$bin/$tool"
done

echo "installed into $bin:"
for t in gitleaks osv-scanner zizmor actionlint uv semgrep checkov; do
  printf '  %-12s %s\n' "$t" "$(SEMGREP_ENABLE_VERSION_CHECK=0 "$bin/$t" --version 2>&1 | grep -v -e '^$' -e 'new version' | head -1)"
done
