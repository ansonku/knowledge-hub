# AI Knowledge Hub — Codex implementation plan v2.0

Implement in small reviewed milestones. Do not advance to production exposure without security gates.

## M0 — Scaffold
- Django project with custom User model, DRF, PostgreSQL migrations; Vue 3 TS Vite PrimeVue Pinia Router; Nginx and Compose for local dev.
- `.env.example`, health checks, dev scripts, lint/test commands, migration workflow.
- Acceptance: `docker compose up --build` starts stack; frontend can call backend health endpoint; database survives restart.

## M1 — Identity/RBAC
- Admin-created accounts, pending activation, SMTP one-time 24h activation links, secure password reset, Django session login/logout, Google OIDC with authenticated self-linking only, optional TOTP and 10 recovery codes, admin reset workflow and audit.
- RBAC Admin/Editor/Viewer enforced in backend.
- Tests: unauthorized signup rejected; no Google auto-provisioning/email-based link; expired/reused activation invalid; disabled user blocked; MFA cannot be bypassed via Google/password/reset; role permissions tested.

## M2 — Documents/categories/uploads
- Category tree, tags, document CRUD, per-file batch new uploads only, explicit per-document new-version upload, immutable version storage, SHA-256 duplicate warning/override, concurrency and failure recovery.
- Tests: same filename never overwrites; batch partial failure; duplicate skip and forced override; simultaneous uploads unique versions; path traversal rejected.

## M3 — Readers and preview
- Standard/Wide/Full Page modes with persisted preference; Markdown view/edit/split with GFM/Mermaid/KaTeX; HTML iframe preview with strict sandbox, CSP and authorization.
- Tests: mode persistence, HTML interactive smoke test, blocked same-origin access, direct preview URL sandbox, CSRF/API denial, denied file access.
- SECURITY GATE: preview cannot be enabled for public use without documented threat model and browser-based adversarial tests.

## M4 — Version history
- Timeline, Monaco diff for text, preview prior version, download, restore by creating a new version, audit.
- Tests: restore never mutates old versions; old hashes stable; Viewer cannot restore; concurrent restore safe.

## M5 — Search and trash
- Metadata and extracted-text search; PostgreSQL indexes, Chinese search evaluation; soft delete/restore; Admin-only permanent delete; audit logs.
- Tests: trashed docs hidden from default search, all versions restored, unauthorized permanent delete blocked.

## M6 — Article publication and anonymous reading
- Migrate existing articles to Private and default new uploads to Private. Store the confirmed published version and public title separately from the internal current version and title.
- Add an Admin-only publish, publish replacement, and withdraw workflow with version confirmation and audit. Trashing withdraws immediately. Restoring from trash returns the article to Private.
- Use the library as the homepage. Signed-out visitors can search the Public article list and open its shareable reading routes. Show a sign-in link in the header and display member controls according to the signed-in role. Use dedicated read-only public endpoints for the published snapshot with no browser or CDN caching. Member library permissions continue to apply to source downloads, version history, categories, and tags.
- Reuse the Markdown reader. Present HTML as sanitized static content with no uploaded JavaScript or automatic external resource requests. Keep runnable preview behind the existing gate.
- First acceptance: an Admin publishes one article and a visitor can read it from the home page in an incognito session.
- Tests: defaults and migration, Admin-only publishing, published content stays pinned across edits/uploads/restores, public queries do not reveal Private or trashed content, direct public URLs return 404 immediately after withdrawal, trash restore keeps Private, and public HTML remains static.

## M7 — NAS deployment and hardening
- Production Compose/Nginx, host cloudflared integration (no duplicate daemon), NAS bind mounts, SMTP/OAuth secrets, backup and restoration scripts, security headers, monitoring.
- Tests: login via public domain, Google callback, activation email, backups/restoration, host loopback binding, negative preview security suite.
- Release can offer static public HTML. Keep executable HTML preview disabled unless the browser security gate passes, or use an independently verified preview site on a separate registrable domain.

## Delivery discipline
For each milestone: implement code + migrations + tests + documentation; run automated tests; provide a concise change summary, risks, and exact commands to reproduce. Ask before changing previously approved product decisions.


## Development host change (v2.1)
Ubuntu 26.04 LTS is the primary development system. M0 acceptance must include Docker Compose startup and smoke tests on Ubuntu.
