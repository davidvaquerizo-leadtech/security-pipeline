# Security policy

## Report a problem

Report a vulnerability in this scanner to **it.security@leadtech.com**. Do not open a public issue for a vulnerability.

We reply within 5 working days.

## What this repo is

This repo builds a scanner image that runs in many CI systems. Its security rules:

- No secrets in the repo or in the image.
- Every tool is pinned by version and sha256 checksum. Python tools are hash-locked.
- The base image is pinned by digest.
- GitHub Actions are pinned by commit SHA.
- Published images are signed (keyless cosign) and carry an SBOM and build provenance.
- Consumers pin the image by digest.
