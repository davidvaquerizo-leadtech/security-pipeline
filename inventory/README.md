# Inventory (IT Security use)

Read-only tools that find where LeadTech code lives and which repos run the shared scan.

## GitHub

```sh
GITHUB_TOKEN=<read-only token> inventory/github_inventory.py <org> [<org> ...] > inventory.json
```

- It uses only `GET` calls.
- The token needs **Metadata: Read** and **Contents: Read** on the org's repos. No write permission.
- Without a token for the org, it sees only public repos.
- For each repo it reports: activity, language, the CI system (GitHub Actions, Bitbucket Pipelines, Codemagic, GitLab CI, ...), whether it calls `security-pipeline`, and `active` (not archived, not a fork, pushed in the last 180 days).

Bitbucket and Codemagic inventory: planned. They need a read-only workspace token (Bitbucket) and a Codemagic API token (see LEAA-2446).
