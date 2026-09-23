# security-pipeline

One security scan for every CI platform at LeadTech: **GitHub Actions**, **Bitbucket Pipelines**, and **Codemagic**.

- One scanner image. One command: `leaa-scan`.
- The scan needs **no secrets** and uploads **nothing**. Results stay in your CI run.
- **Only secrets fail the build.** All other findings are advisory.

Owner: IT Security (LEAA). Ticket: LEAA-2446.

## What it runs

| Scanner | Finds | Runs when |
|---|---|---|
| gitleaks | Secrets (API keys, tokens, private keys) | Always. **This is the gate.** |
| semgrep | Insecure code (SAST) | Always |
| osv-scanner | Known CVEs and malicious packages in dependencies | Always. Python version ranges are resolved to exact pins first. |
| checkov | Terraform, Dockerfile, Kubernetes, Helm, CloudFormation, Bicep | Only when such files exist |
| zizmor + actionlint | GitHub Actions workflow security and syntax | Only when `.github/workflows` exists |

Dependency files that osv-scanner reads include `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `pubspec.lock` (Flutter/Dart), `Podfile.lock`, `Package.resolved` (iOS), `gradle.lockfile` (Android), `go.sum`, `Cargo.lock`, `composer.lock`, and `requirements*.txt`.

Tool versions and sha256 checksums: [`tools/versions.env`](tools/versions.env). Python tools are hash-locked: [`tools/requirements-*.txt`](tools/).

## Add it to your repo

Pick the adapter for the place where your pull request lives.

| Your repo is on | Your CI | Use |
|---|---|---|
| GitHub | GitHub Actions or Codemagic | [`adapters/github-actions.yml`](adapters/github-actions.yml) |
| Bitbucket | Bitbucket Pipelines | [`adapters/bitbucket-pipelines.yml`](adapters/bitbucket-pipelines.yml) |
| Bitbucket or GitHub | Codemagic only | [`adapters/codemagic.yaml`](adapters/codemagic.yaml) |

1. Copy the adapter into your repo.
2. Replace `<DIGEST>` with the current image digest (below). For GitHub, also replace `<COMMIT_SHA>`.
3. Open a pull request. Check the **Security Scan** result and the `security-reports` artifact.

### Current release

The image is not published yet. The board decides the registry first (LEAA-2446, Q1). The adapters show GHCR as the planned location. This section will hold the digest and the commit SHA after the first release.

## Results

Each run writes `security-reports/`:

- `summary.md` — the dashboard (counts per scanner and the top 25 findings).
- `summary.json` — machine-readable counts, tool status, gate result, commit, platform, `leaa_version`.
- `<scanner>.sarif` — full results. Open them in VS Code (SARIF Viewer) or any SARIF tool.
- `resolved/` — the exact Python pins that osv-scanner scanned.

## When the build fails on a secret

1. Read the gitleaks finding in the job log or `gitleaks.sarif`. The value is redacted.
2. **If the value is a real secret:** rotate it first. Then remove it from the code.
3. **If it is not a secret** (a test value, a public identifier): add its fingerprint to `.gitleaksignore` in your repo root. Get the fingerprint from the SARIF result.
   - Pull request scans use history mode. The fingerprint is `commit:file:rule:line`.
   - Scans without a base branch use directory mode. The fingerprint is `file:rule:line`.
4. You can add a `.gitleaks.toml` in your repo root to extend the rules or add allowlists. `leaa-scan` uses it.

## Options

| Variable | Default | Meaning |
|---|---|---|
| `LEAA_FAIL_ON` | `secrets` | `secrets`: fail only on a secret. `none`: never fail (report only). |
| `LEAA_BASE_REF` | auto | Base commit for the pull request secret scan. Auto-detected on all three platforms. |
| `LEAA_GITLEAKS_MODE` | `auto` | `auto`, `full` (whole history), or `dir` (current files only). |
| `LEAA_SKIP` | empty | Scanners to skip, for example `checkov zizmor`. |
| `LEAA_REPORT_DIR` | `security-reports` | Output directory. |

Exit codes: `0` pass, `1` a secret was found, `2` the secret scan could not run.

## Without Docker

On a Linux host (amd64 or arm64) without Docker:

```sh
tools/install.sh /opt/leaa        # pinned + sha256-checked
export PATH=/opt/leaa/bin:$PWD/bin:$PATH
leaa-scan
```

## Develop

- `tests/run.sh` checks the gate (clean, secret in tree, secret in a pull request, old history, gate off).
- CI builds the image on amd64 and arm64, runs the tests inside it, and scans this repo.
- Change a tool version: edit `tools/versions.env` with the upstream checksums, or re-lock `tools/requirements-*.txt` with the command at the top of each file.
