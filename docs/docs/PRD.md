# AI Knowledge Hub — PRD v2.1

完整正式產品規格以 [FINAL_MVP_SPEC_v2.1.md](FINAL_MVP_SPEC_v2.1.md) 為準。

# AI Knowledge Hub — Product Requirements (MVP v2.1)

Status: approved baseline, 2026-11-21. This document records product decisions; implementation is not yet complete.

## Goal
A multi-user, NAS-hosted knowledge library for AI-generated HTML and Markdown technical articles, accessible at `https://hub.sharegram.cc`, with immutable document history and comfortable reading.

## Users and permissions
- Admin: read/search/download, create/upload, edit/version, manage categories/tags, preview/compare/restore, trash, permanently delete, manage users/roles.
- Editor: all document operations except permanent deletion and user/role administration.
- Viewer: read/search/download, preview/compare history; cannot mutate documents.
- Shared library; editors can modify all documents in MVP. Enforce permissions in API and server-side service layer, not only UI.

## Identity and account lifecycle
- Support Django password login AND Google OAuth 2.0/OpenID Connect via django-allauth.
- No public signup and no Google auto-provisioning; only Admin creates user accounts.
- Admin creates inactive/pending account; system emails single-use activation URL (recommended 24h expiry), user sets password and activates account. Resend invalidates earlier links.
- Google linking is initiated only by an already authenticated user from profile settings, after fresh authentication; never link merely because email addresses match. Bind Google provider stable `sub` to the approved Django user. No account auto-merge.
- Django manages user session and RBAC for either login method; Google authentication does not confer permissions.
- Optional TOTP MFA; when enabled, require MFA after either password or Google authentication, before a full session is issued. Issue 10 single-use recovery codes, store only verifiers/hashes, display once. Prevent MFA bypass through password reset, account linking, alternate login, or partial sessions.
- Admin can reset MFA only after independent identity verification; log actor, reason, target, timestamp, and notify affected user. No immediate fully authenticated session after reset.
- Admin can disable users, change roles, and trigger secure password reset. No public self-registration.
- Email and SMTP configuration are environment-based; do not store credentials in git.

## Documents
- Supported formats: `.html`, `.md` (UTF-8). Original source preserved.
- Logical hierarchical categories, manual tags, editable titles prefilled from filenames.
- Batch upload creates NEW documents only; one Document UUID and v1 per accepted file. Per-file progress/errors; one failed file does not roll back unrelated successes.
- To update an existing document, enter that document and explicitly upload a new file. Never infer version identity from filename. MVP versions retain original document format.
- SHA-256 identical to current version: warn and default to skip; an explicit confirmation can force a new version. On batch new-document upload, warn on exact duplicates in library but never silently merge.
- DocumentVersion is immutable: version number, file path, hash, size, change note, creator, source, creation time, restored-from version. Restoring v2 when v5 is current creates v6; never overwrite earlier versions.
- Concurrency-safe version numbers and file/database consistency; failed writes must be recoverable and not leave a version pointing at missing content.
- Trash is soft delete of document and all its versions; restore preserves history. Admin alone can permanently delete.

## Reader and authoring
- Three reader modes: Standard (category sidebar + article + TOC), Wide (hide sidebars, constrained readable width), Full Page (hide sidebars, maximize article width while retaining toolbar). Top-right layout selector and quick maximize; persist user preference. Defaults HTML Full Page, Markdown Standard.
- Markdown view/edit/split; Monaco editor; GFM, Mermaid, KaTeX, syntax highlighting. Saving edits creates a new immutable version.
- HTML source uploaded externally; no in-app HTML editing in MVP. Preserve embedded CSS/JS/base64 and interactive behavior subject to preview security.
- Version history: timeline, Monaco diff where applicable, version preview, metadata, download, restore confirmation and audit.
- Search across title, category, tags, and extracted document text. PostgreSQL full-text initially; test Chinese tokenization and improve if insufficient.

## HTML preview — approved MVP with mandatory security gate
- Same host (`hub.sharegram.cc`) but strictly sandboxed iframe with `allow-scripts` only; NEVER `allow-same-origin` together with scripts.
- Default compatibility mode allows HTTPS external resources, subject to security policy; do not imply it prevents third-party data exfiltration.
- Every executable preview response must itself include restrictive CSP `sandbox allow-scripts` so direct navigation does not escape sandbox, and appropriate `frame-ancestors`, navigation/form/object/base restrictions. Preview cannot receive or expose Django session, CSRF tokens, or reusable credentials in markup, URLs, or JavaScript.
- Preview retrieval must authorize the requested document/version, use short-lived purpose-scoped access, and must not grant uploaded JS access to authenticated APIs. Prevent unsafe direct/raw file URLs and unrestricted inline rendering on main origin.
- Explicit test gate before public deployment: iframe escape, direct preview URL, CSRF/cookie request behavior, CSP enforcement, cross-origin resource behavior, access control, token leakage, redirects/popups/downloads, malicious HTML and XSS.
- If isolation cannot be verified, disable executable preview for public deployment or migrate to a separate site (different registrable domain). A same-origin path alone is NOT an isolation boundary.

## Deployment
- NAS: UGREEN DXP6800 Pro / UGOS Pro. Docker Compose: Nginx, Django, PostgreSQL; isolated preview handling as required.
- Nginx serves built Vue SPA and proxies API; host loopback bind proposed `127.0.0.1:18080:80` after port check.
- Existing cloudflared runs on NAS host; add `hub.sharegram.cc` -> `http://localhost:18080`. Do not deploy another cloudflared container. No public database/backend port.
- Persist document files and PostgreSQL on verified NAS bind mounts. Back up both, retain generations, perform restoration drills. HTTPS via Cloudflare Tunnel; secure cookies, CSRF, throttling, headers, logging.

## Provisional operational defaults
- 50 MB per file, 20 files per batch; configurable.
- No automatic trash purge in MVP.
- Final NAS path, SMTP provider, OAuth secrets, port availability, backup schedule/retention and public preview security acceptance are deployment gates, not blockers for local feature development.
