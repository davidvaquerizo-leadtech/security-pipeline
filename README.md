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

**Commit your lock file.** The dependency scan reads lock files, not manifests. Without a lock file it cannot check your dependencies, and the summary says `no lock file found`.

| Stack | Commit this file | Note |
|---|---|---|
| Flutter / Dart app | `pubspec.lock` | Libraries often do not commit it; apps must. |
| iOS (SwiftPM) | `Package.resolved` | Xcode: keep it under `*.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/` or the package root. |
| iOS (CocoaPods) | `Podfile.lock` | |
| Android (Gradle) | `gradle.lockfile` | Turn on Gradle dependency locking (`dependencyLocking { lockAllConfigurations() }`, then `./gradlew dependencies --write-locks`). |
| Node | `package-lock.json`, `yarn.lock`, or `pnpm-lock.yaml` | |
| Python | `requirements*.txt` (ranges are resolved automatically) or `poetry.lock` / `uv.lock` | |

semgrep skips vendored and generated folders: `third_party`, `vendor`, `node_modules`, `Pods`, `Carthage`, `.dart_tool`, `build`, `dist`, `.gradle`. The dependency scan still reads vendored lock files.

Tool versions and sha256 checksums: [`tools/versions.env`](tools/versions.env). Python tools are hash-locked: [`tools/requirements-*.txt`](tools/).

## Add it to your repo

Pick the adapter for the place where your pull request lives.

| Your repo is on | Your CI | Use |
|---|---|---|
| GitHub | GitHub Actions or Codemagic | [`adapters/github-actions.yml`](adapters/github-actions.yml) |
| Bitbucket | Bitbucket Pipelines | [`adapters/bitbucket-pipelines.yml`](adapters/bitbucket-pipelines.yml) |
| Bitbucket or GitHub | Codemagic only | [`adapters/codemagic.yaml`](adapters/codemagic.yaml) |

1. Copy the adapter into your repo.
2. The adapters are pinned to the current release (below). Keep the pins. A release bump comes as a PR from IT Security, or you copy the new values.
3. Open a pull request. Check the **Security Scan** result and the `security-reports` artifact.

### Current release

| Item | Value |
|---|---|
| Image | `ghcr.io/davidvaquerizo-leadtech/security-pipeline@sha256:c20595bc2e72631b08de8188bdabda122e5583832d35a709d9d491c905bd5757` |
| Reusable workflow commit | `e2423d35b2318ea6c9591a8a4752ac6de10b9297` |
| Released | 2026-09-23 (CI run 35885375234, attempt 2) |
| Platforms | linux/amd64, linux/arm64 |

The adapters in [`adapters/`](adapters/) already use these values.

Verify the signature before you pin a new digest:

```sh
cosign verify \
  --certificate-identity "https://github.com/davidvaquerizo-leadtech/security-pipeline/.github/workflows/ci.yml@refs/heads/main" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/davidvaquerizo-leadtech/security-pipeline@sha256:c20595bc2e72631b08de8188bdabda122e5583832d35a709d9d491c905bd5757
```

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

- A release publishes on every merge to `main` (or `workflow_dispatch` on `main`) while the repo variable `PUBLISH_ENABLED` is `true`. Then update the table above and the adapters in one PR.

- `tests/run.sh` checks the gate (clean, secret in tree, secret in a pull request, old history, gate off).
- CI builds the image on amd64 and arm64, runs the tests inside it, and scans this repo.
- Change a tool version: edit `tools/versions.env` with the upstream checksums, or re-lock `tools/requirements-*.txt` with the command at the top of each file.
