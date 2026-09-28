# leaa-security-scan — one image for GitHub Actions, Bitbucket Pipelines,
# and Codemagic. No secrets inside. Multi-arch (linux/amd64, linux/arm64).
# Base pinned by multi-arch index digest (python:3.12-slim-bookworm).
# checkov:skip=CKV_DOCKER_2: CLI image run once per CI job; no long-lived service to health-check
# checkov:skip=CKV_DOCKER_3: root is required to write reports into the CI-mounted checkout (see below)
FROM python:3.14-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56

ARG LEAA_VERSION=dev

# git: secret scan in history mode. curl + ca-certificates: tool install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'

COPY tools/ /opt/leaa/tools/
RUN bash /opt/leaa/tools/install.sh /opt/leaa \
 && rm -rf /root/.cache

COPY bin/ /opt/leaa/bin/
COPY lib/ /opt/leaa/lib/

ENV PATH=/opt/leaa/bin:$PATH \
    LEAA_HOME=/opt/leaa \
    LEAA_VERSION=$LEAA_VERSION \
    SEMGREP_ENABLE_VERSION_CHECK=0 \
    SEMGREP_SEND_METRICS=off

LABEL org.opencontainers.image.title="leaa-security-scan" \
      org.opencontainers.image.source="https://github.com/davidvaquerizo-leadtech/security-pipeline" \
      org.opencontainers.image.licenses="Apache-2.0"

# CI systems mount the checkout and call `leaa-scan` themselves.
# Runs as root on purpose: GitHub container jobs and Bitbucket steps need
# write access to the mounted checkout for the report directory.
WORKDIR /src
# nosemgrep: dockerfile.security.missing-user.missing-user
CMD ["leaa-scan"]
