# Codex working agreement — AI Knowledge Hub

Read `docs/PRD.md`, `docs/ARCHITECTURE.md`, and `docs/IMPLEMENTATION_PLAN.md` before coding.

- Work milestone-by-milestone. Start at M0; don't implement all features in one giant change.
- Prioritize security, tests, maintainable structure, and migrations. Keep frontend and backend separated.
- Never weaken backend RBAC based on frontend visibility. No public registration or Google auto-provisioning.
- Never auto-match versions by filename. Preserve immutable historical files; restoration creates a new version.
- Treat uploaded HTML as untrusted executable content. Do not render unsandboxed on the main site; preserve iframe and HTTP CSP sandbox. Do not assert same-origin preview is safe without the documented public deployment security gate.
- Never log secrets, MFA seeds, recovery codes, raw OAuth tokens, session cookies, or activation tokens. Keep credentials out of repository.
- Never invent NAS paths or assume cloudflared is in Docker; verify actual UGOS Pro environment before deployment.
- Before each milestone, provide a brief plan. After changes, list files changed, migrations, test results, and outstanding risks.
- If an architectural ambiguity affects security or data loss, stop and ask for a decision instead of guessing.

First task: implement M0 only, including compose, Django custom User model from first migration, Vue app skeleton, Nginx routing, sample env, basic health endpoint, and tests.


## v2.1 mandatory baseline
- Development host is Ubuntu 26.04 LTS; do not assume macOS or Homebrew.
- Read docs/FINAL_MVP_SPEC_v2.1.md before planning or editing.
- Do not compromise the public-launch HTML sandbox security gate.
