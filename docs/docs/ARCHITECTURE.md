# AI Knowledge Hub — Architecture v2.1

## Components
```text
Browser (Vue 3 + TS + Vite + PrimeVue + Pinia + Vue Router)
  | HTTPS hub.sharegram.cc (Cloudflare Tunnel, existing host cloudflared)
NAS loopback :18080 -> Docker Nginx
  |-- /             Django: signed in -> /app/, visitors -> /articles/
  |-- /app/         Vue SPA, member workspace
  |-- /articles/     Vue SPA, public portal (SEO head injected via X-Hub-Head + sub_filter)
  |-- /read/        Vue SPA, member reading portal (same layout, all active documents)
  |-- /api/public/   published article list, body, nav, popular; anonymous view counter
  |-- /api/read/    member reading list, body, nav (CanReadLibrary)
  |-- /api/         Django REST Framework (session auth, CSRF, RBAC)
  |-- /accounts/    django-allauth password / Google OIDC / TOTP
  `-- /preview/...  authorized preview handler + HTTP CSP sandbox
Django -> PostgreSQL (metadata, users, versions, audit, search)
Django -> NAS bind-mounted immutable version files
Django -> SMTP for activation/reset/security notifications
```

## Stack
- Python/Django/DRF, django-allauth with Google provider and MFA/TOTP support or audited compatible MFA package.
- Vue 3, TypeScript, Vite, PrimeVue, Monaco, Markdown renderer with GFM/Mermaid/KaTeX.
- PostgreSQL; Nginx; Docker Compose. Pin exact versions after compatibility review.

## Data model outline
- User(UUID, email unique, username, display_name, role, is_active, activation state, timestamps); use custom Django user model from initial migration.
- SocialAccount from allauth: provider, provider_uid (`sub`), linked user.
- Category(UUID, parent nullable, name, slug, ordering).
- Tag(UUID, name unique).
- Document(UUID, title, format, category FK, tags M2M, current_version FK nullable, visibility (Private by default), published_version FK nullable, published_title, published_at, is_trashed, created_by, timestamps).
- DocumentVersion(UUID, document FK, version_number, storage_path, sha256, byte_size, change_note, source, restored_from FK nullable, created_by, created_at). Unique(document, version_number); immutable records.
- AuditLog(UUID, actor, action, target_type, target_id, metadata with redaction, created_at).
- Optional one-use activation/reset token records (prefer Django secure signed/password-reset tokens and server-side invalidation semantics).
- TOTP/recovery: use supported security package; encrypt TOTP secret at rest, hash recovery codes, rate-limit verification.

## Upload transaction strategy
1. Validate role, extension, size, MIME/content policy, quota, and format.
2. Stage upload in non-public temporary directory; compute SHA-256 and safely extract searchable text.
3. Acquire per-document lock for version update; check current version and duplicates; require explicit override when identical.
4. Allocate monotonically increasing version number; atomically move staged file to immutable path; commit DB metadata/current pointer in transaction, with cleanup/reconciliation for partial failures.
5. Audit; respond per-file success/failure. Never infer existing document by filename.

Storage example (verify NAS mount first):
`documents/<document_uuid>/versions/v0001.html`
`documents/<document_uuid>/versions/v0002.html`

## Article publication (M6)
- Use separate public list and reading endpoints. Validate Public status, a published version belonging to the requested document, and the active trash state on every request. Return the same 404 response for an unavailable article and an unknown public URL.
- Resolve the title and content from the published snapshot. Internal readers continue to use the current version. Public responses expose only the published title and body. The public query scope uses the published snapshot and omits internal metadata and member downloads.
- Publish and withdraw through Admin-only, CSRF-protected service operations. Lock the document and update the publication state and audit in one transaction. Keep the published pointer independent of internal version changes. Clear publication when trashing and restore from trash as Private.
- Render public Markdown with the existing safe Markdown reader. Serve public HTML through a static, sanitized reading view that removes executable content and automatic external loads. Keep original uploads in protected storage. Set public list and reading responses to `Cache-Control: no-store` and configure the CDN to bypass caching.
- Test public and member access separately. Include anonymous direct links, withheld draft versions, immediate withdrawal, trash and restore, unauthorized publication, and browser checks for public HTML.

## Member reading portal (P5d)
- `/api/read/` serves every active (non-trashed) document to readers with `CanReadLibrary`, reusing the public collection tree and card shapes plus a `public` flag and version number. Never cached.
- HTML bodies use the same sanitized static reading view as the public site, mounted in a `sandbox=""` iframe; original uploads are never returned. Public endpoints are unchanged and still expose published snapshots only.

## Popular public articles (P5e)
- `ArticleViewDaily` stores only `(document, day, count)`. The browser posts at most one view per article per day (sessionStorage) with `credentials: 'omit'`; the member portal and workspace never post.
- The anonymous counter accepts published articles only and is rate limited per client address taken from Nginx's `X-Hub-Client-IP`. Throttle cache keys are SHA-256 hashed and expire; no address is persisted.
- `/api/public/popular/` ranks currently published articles by 30-day totals (top 5, hidden below 3) and never returns counts. The per-document 30-day trend is Admin-only.

## Preview security boundary: high-risk design
- The same-origin preview choice is provisional for MVP only and requires a security gate before external use.
- Set iframe `sandbox="allow-scripts"` (no `allow-same-origin`, no forms, popups, top-navigation, downloads unless separately approved).
- Set response header `Content-Security-Policy: sandbox allow-scripts; ...` on *every* executable preview response, including when directly navigated. CSP must be designed and browser-tested for compatibility, with restrictive `base-uri`, `form-action`, `object-src`, and appropriate `frame-ancestors`/navigation constraints.
- Since user content is served under the same host, avoid authentication cookies being attached to preview fetches where possible; rely on server authorization, SameSite/Secure/HttpOnly cookies, CSRF, Fetch Metadata, method restrictions and API authorization. Opaque origin alone does not stop network requests or cookie attachment.
- Preview URLs/tokens must be short-lived, purpose-limited, and not expose reusable credentials to untrusted JS. A signed token embedded in HTML/JS or URL may be exfiltrated by external scripts; use a carefully reviewed bootstrap/fetch architecture.
- Default compatibility mode may allow HTTPS CDN/image/font/script connections; this is NOT a guarantee of preventing data exfiltration. Do not promise complete confinement without a different-site boundary and further controls.
- Never use `v-html` or unsandboxed `srcdoc` to mount uploaded HTML in Vue. Never serve raw uploads through unprotected Nginx aliases.
- Gate public rollout on adversarial browser testing; fallback is disabling executable preview or moving it to a different registrable domain.

## Auth/security
- Session auth, CSRF protection for mutations, secure HttpOnly cookies, origin validation, login rate limits, secure password reset.
- Pre-approved user only; Google linking must originate from authenticated fresh user session, and map Google `sub` without email-based auto-linking.
- Enforce TOTP after either primary login when enabled; 10 single-use recovery codes; admin reset requires verified process, audit, notification and step-up before sensitive changes.
- Apply RBAC to every API endpoint, file download, version history, preview and restore.

## Production readiness (M7)
- Verify actual UGOS Pro mount paths, UID/GID, permissions, disk free space, localhost port, cloudflared route, backup/restore and email deliverability.
- Configure Google OAuth authorized redirect URI from actual allauth route, e.g. `https://hub.sharegram.cc/accounts/google/login/callback/` after routing validation.


## Ubuntu 26.04 development environment
- Ubuntu 26.04 LTS is the primary development host (not macOS).
- Prefer Docker Engine + Compose plugin; keep Python/Node/PostgreSQL/Nginx containerized.
- Dev access at localhost:18080; use a separate OAuth client for local redirects.
- Validate linux/amd64 and linux/arm64 image compatibility against the NAS.
